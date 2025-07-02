#!/usr/bin/env python3
import os
from typing import Any, Dict, Optional, Tuple, List # Added for type hinting

from openpilot.system.hardware import TICI
USBGPU: bool = "USBGPU" in os.environ
if USBGPU:
  os.environ['AMD'] = '1'
  os.environ['AMD_IFACE'] = 'USB'
elif TICI:
  from openpilot.selfdrive.modeld.runners.tinygrad_helpers import qcom_tensor_from_opencl_address
  os.environ['QCOM'] = '1'
else:
  os.environ['LLVM'] = '1'
  os.environ['JIT'] = '2'
from tinygrad.tensor import Tensor
from tinygrad.dtype import dtypes
import time
import pickle
import numpy as np
import cereal.messaging as messaging
from cereal import car, log
from pathlib import Path
from setproctitle import setproctitle
from cereal.messaging import PubMaster, SubMaster
from msgq.visionipc import VisionIpcClient, VisionStreamType, VisionBuf
from opendbc.car.car_helpers import get_demo_car_params
from openpilot.common.swaglog import cloudlog
from openpilot.common.params import Params
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.realtime import config_realtime_process, DT_MDL
from openpilot.common.transformations.camera import DEVICE_CAMERAS
from openpilot.common.transformations.model import get_warp_matrix
from openpilot.system import sentry
from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper
from openpilot.selfdrive.controls.lib.drive_helpers import get_accel_from_plan, smooth_value
from openpilot.selfdrive.modeld.parse_model_outputs import Parser
from openpilot.selfdrive.modeld.fill_model_msg import fill_model_msg, fill_pose_msg, PublishState
from openpilot.selfdrive.modeld.constants import ModelConstants, Plan
from openpilot.selfdrive.modeld.models.commonmodel_pyx import DrivingModelFrame, CLContext
from openpilot.common.params import Params as CommonParams # Renamed to avoid conflict

PROCESS_NAME: str = "selfdrive.modeld.modeld"
SEND_RAW_PRED: str | None = os.getenv('SEND_RAW_PRED')

LAT_SMOOTH_SECONDS: float = 0.0
LONG_SMOOTH_SECONDS: float = 0.0
MIN_LAT_CONTROL_SPEED: float = 0.3


def get_action_from_model(model_output: Dict[str, np.ndarray], prev_action: log.ModelDataV2.Action.Reader,
                          lat_action_t: float, long_action_t: float, v_ego: float) -> log.ModelDataV2.Action.Builder:
    plan: np.ndarray = model_output['plan'][0]
    desired_accel: float
    should_stop: bool
    desired_accel, should_stop = get_accel_from_plan(plan[:,Plan.VELOCITY][:,0],
                                                     plan[:,Plan.ACCELERATION][:,0],
                                                     ModelConstants.T_IDXS,
                                                     action_t=long_action_t)
    desired_accel = smooth_value(desired_accel, prev_action.desiredAcceleration, LONG_SMOOTH_SECONDS)

    desired_curvature: float = model_output['desired_curvature'][0, 0]
    if v_ego > MIN_LAT_CONTROL_SPEED:
      desired_curvature = smooth_value(desired_curvature, prev_action.desiredCurvature, LAT_SMOOTH_SECONDS)
    else:
      desired_curvature = prev_action.desiredCurvature

    action_builder = log.ModelDataV2.Action.new_message()
    action_builder.desiredCurvature = float(desired_curvature)
    action_builder.desiredAcceleration = float(desired_accel)
    action_builder.shouldStop = bool(should_stop)
    return action_builder

class FrameMeta:
  frame_id: int = 0
  timestamp_sof: int = 0
  timestamp_eof: int = 0

  def __init__(self, vipc: Optional[VisionIpcClient] = None) -> None:
    if vipc is not None:
      self.frame_id, self.timestamp_sof, self.timestamp_eof = vipc.frame_id, vipc.timestamp_sof, vipc.timestamp_eof

class ModelState:
  frames: Dict[str, DrivingModelFrame]
  # inputs: Dict[str, np.ndarray] # This seems unused
  # output: np.ndarray # This seems unused
  prev_desire: np.ndarray  # for tracking the rising edge of the pulse
  vision_input_shapes: Dict[str, Tuple[int, ...]]
  vision_input_names: List[str]
  vision_output_slices: Dict[str, slice]
  policy_input_shapes: Dict[str, Tuple[int, ...]]
  policy_output_slices: Dict[str, slice]
  full_features_buffer: np.ndarray
  full_desire: np.ndarray
  full_prev_desired_curv: np.ndarray
  temporal_idxs: slice
  numpy_inputs: Dict[str, np.ndarray]
  vision_inputs: Dict[str, Tensor]
  vision_output: np.ndarray
  policy_inputs: Dict[str, Tensor]
  policy_output: np.ndarray
  parser: Parser
  vision_run: Any # Loaded from pickle
  policy_run: Any # Loaded from pickle


  def __init__(self, context: CLContext) -> None:
    params = CommonParams()
    selected_model_name: str | None = params.get("DrivingModel", encoding='utf-8')
    if selected_model_name is None:
      cloudlog.warning("DrivingModel param not set, using default model name 'default_tinygrad'.")
      selected_model_name = "default_tinygrad" # This key needs to exist in MODEL_FILE_SETS

    models_base_path: Path = Path(__file__).parent / 'models'

    MODEL_FILE_SETS: Dict[str, Dict[str, Path]] = {
      "default_tinygrad": { # Default model key
        "vision_pkl": models_base_path / "driving_vision_tinygrad.pkl",
        "policy_pkl": models_base_path / "driving_policy_tinygrad.pkl",
        "vision_metadata": models_base_path / "driving_vision_metadata.pkl",
        "policy_metadata": models_base_path / "driving_policy_metadata.pkl",
      },
      # Example for adding another model:
      # "experimental_v1": {
      #   "vision_pkl": models_base_path / "experimental_v1_vision.pkl",
      #   "policy_pkl": models_base_path / "experimental_v1_policy.pkl",
      #   "vision_metadata": models_base_path / "experimental_v1_vision_metadata.pkl",
      #   "policy_metadata": models_base_path / "experimental_v1_policy_metadata.pkl",
      # }
    }

    model_files: Optional[Dict[str, Path]] = MODEL_FILE_SETS.get(selected_model_name)
    if model_files is None:
      cloudlog.error(f"Model files for DrivingModel '{selected_model_name}' not found in MODEL_FILE_SETS. Falling back to 'default_tinygrad'.")
      model_files = MODEL_FILE_SETS["default_tinygrad"]

    cloudlog.info(f"Loading driving model: {selected_model_name}")
    cloudlog.info(f"  Vision PKL: {model_files['vision_pkl']}")
    cloudlog.info(f"  Policy PKL: {model_files['policy_pkl']}")

    with open(model_files["vision_metadata"], 'rb') as f:
      vision_metadata: Dict[str, Any] = pickle.load(f)
      self.vision_input_shapes = vision_metadata['input_shapes']
      self.vision_input_names = list(self.vision_input_shapes.keys())
      self.vision_output_slices = vision_metadata['output_slices']
      vision_output_size: int = vision_metadata['output_shapes']['outputs'][1]

    with open(model_files["policy_metadata"], 'rb') as f:
      policy_metadata: Dict[str, Any] = pickle.load(f)
      self.policy_input_shapes = policy_metadata['input_shapes']
      self.policy_output_slices = policy_metadata['output_slices']
      policy_output_size: int = policy_metadata['output_shapes']['outputs'][1]

    self.frames = {name: DrivingModelFrame(context, ModelConstants.TEMPORAL_SKIP) for name in self.vision_input_names}
    self.prev_desire = np.zeros(ModelConstants.DESIRE_LEN, dtype=np.float32)

    self.full_features_buffer = np.zeros((1, ModelConstants.FULL_HISTORY_BUFFER_LEN, ModelConstants.FEATURE_LEN), dtype=np.float32)
    self.full_desire = np.zeros((1, ModelConstants.FULL_HISTORY_BUFFER_LEN, ModelConstants.DESIRE_LEN), dtype=np.float32)
    self.full_prev_desired_curv = np.zeros((1, ModelConstants.FULL_HISTORY_BUFFER_LEN, ModelConstants.PREV_DESIRED_CURV_LEN), dtype=np.float32)
    self.temporal_idxs = slice(-1-(ModelConstants.TEMPORAL_SKIP*(ModelConstants.INPUT_HISTORY_BUFFER_LEN-1)), None, ModelConstants.TEMPORAL_SKIP)

    # policy inputs
    self.numpy_inputs = {
      'desire': np.zeros((1, ModelConstants.INPUT_HISTORY_BUFFER_LEN, ModelConstants.DESIRE_LEN), dtype=np.float32),
      'traffic_convention': np.zeros((1, ModelConstants.TRAFFIC_CONVENTION_LEN), dtype=np.float32),
      'lateral_control_params': np.zeros((1, ModelConstants.LATERAL_CONTROL_PARAMS_LEN), dtype=np.float32),
      'prev_desired_curv': np.zeros((1, ModelConstants.INPUT_HISTORY_BUFFER_LEN, ModelConstants.PREV_DESIRED_CURV_LEN), dtype=np.float32),
      'features_buffer': np.zeros((1, ModelConstants.INPUT_HISTORY_BUFFER_LEN, ModelConstants.FEATURE_LEN), dtype=np.float32),
    }

    # img buffers are managed in openCL transform code
    self.vision_inputs = {}
    self.vision_output = np.zeros(vision_output_size, dtype=np.float32)
    self.policy_inputs = {k: Tensor(v, device='NPY').realize() for k,v in self.numpy_inputs.items()}
    self.policy_output = np.zeros(policy_output_size, dtype=np.float32)
    self.parser = Parser()

    with open(model_files["vision_pkl"], "rb") as f:
      self.vision_run = pickle.load(f)

    with open(model_files["policy_pkl"], "rb") as f:
      self.policy_run = pickle.load(f)

  def slice_outputs(self, model_outputs: np.ndarray, output_slices: Dict[str, slice]) -> Dict[str, np.ndarray]:
    parsed_model_outputs: Dict[str, np.ndarray] = {k: model_outputs[np.newaxis, v] for k,v in output_slices.items()}
    return parsed_model_outputs

  def run(self, bufs: Dict[str, VisionBuf], transforms: Dict[str, np.ndarray],
                inputs: Dict[str, np.ndarray], prepare_only: bool) -> Optional[Dict[str, np.ndarray]]:
    # Model decides when action is completed, so desire input is just a pulse triggered on rising edge
    inputs['desire'][0] = 0
    new_desire: np.ndarray = np.where(inputs['desire'] - self.prev_desire > .99, inputs['desire'], 0)
    self.prev_desire[:] = inputs['desire']

    self.full_desire[0,:-1] = self.full_desire[0,1:]
    self.full_desire[0,-1] = new_desire
    self.numpy_inputs['desire'][:] = self.full_desire.reshape((1,ModelConstants.INPUT_HISTORY_BUFFER_LEN,ModelConstants.TEMPORAL_SKIP,-1)).max(axis=2)

    self.numpy_inputs['traffic_convention'][:] = inputs['traffic_convention']
    self.numpy_inputs['lateral_control_params'][:] = inputs['lateral_control_params']
    imgs_cl: Dict[str, Any] = {name: self.frames[name].prepare(bufs[name], transforms[name].flatten()) for name in self.vision_input_names}

    if TICI and not USBGPU:
      # The imgs tensors are backed by opencl memory, only need init once
      for key in imgs_cl:
        if key not in self.vision_inputs:
          self.vision_inputs[key] = qcom_tensor_from_opencl_address(imgs_cl[key].mem_address, self.vision_input_shapes[key], dtype=dtypes.uint8)
    else:
      for key in imgs_cl:
        frame_input: np.ndarray = self.frames[key].buffer_from_cl(imgs_cl[key]).reshape(self.vision_input_shapes[key])
        self.vision_inputs[key] = Tensor(frame_input, dtype=dtypes.uint8).realize()

    if prepare_only:
      return None

    self.vision_output = self.vision_run(**self.vision_inputs).numpy().flatten()
    vision_outputs_dict: Dict[str, np.ndarray] = self.parser.parse_vision_outputs(self.slice_outputs(self.vision_output, self.vision_output_slices))

    self.full_features_buffer[0,:-1] = self.full_features_buffer[0,1:]
    self.full_features_buffer[0,-1] = vision_outputs_dict['hidden_state'][0, :]
    self.numpy_inputs['features_buffer'][:] = self.full_features_buffer[0, self.temporal_idxs]

    self.policy_output = self.policy_run(**self.policy_inputs).numpy().flatten()
    policy_outputs_dict: Dict[str, np.ndarray] = self.parser.parse_policy_outputs(self.slice_outputs(self.policy_output, self.policy_output_slices))

    # TODO model only uses last value now
    self.full_prev_desired_curv[0,:-1] = self.full_prev_desired_curv[0,1:]
    self.full_prev_desired_curv[0,-1,:] = policy_outputs_dict['desired_curvature'][0, :]
    self.numpy_inputs['prev_desired_curv'][:] = self.full_prev_desired_curv[0, self.temporal_idxs]

    combined_outputs_dict: Dict[str, np.ndarray] = {**vision_outputs_dict, **policy_outputs_dict}
    if SEND_RAW_PRED:
      combined_outputs_dict['raw_pred'] = np.concatenate([self.vision_output.copy(), self.policy_output.copy()])

    return combined_outputs_dict


def main(demo: bool = False) -> None:
  cloudlog.warning("modeld init")

  sentry.set_tag("daemon", PROCESS_NAME)
  cloudlog.bind(daemon=PROCESS_NAME)
  setproctitle(PROCESS_NAME)
  if not USBGPU:
    # USB GPU currently saturates a core so can't do this yet,
    # also need to move the aux USB interrupts for good timings
    config_realtime_process(7, 54)

  st: float = time.monotonic()
  cloudlog.warning("setting up CL context")
  cl_context = CLContext()
  cloudlog.warning("CL context ready; loading model")
  model = ModelState(cl_context)
  cloudlog.warning(f"models loaded in {time.monotonic() - st:.1f}s, modeld starting")

  # visionipc clients
  vipc_client_main: VisionIpcClient
  vipc_client_extra: VisionIpcClient
  use_extra_client: bool
  main_wide_camera: bool
  while True:
    available_streams = VisionIpcClient.available_streams("camerad", block=False)
    if available_streams:
      use_extra_client = VisionStreamType.VISION_STREAM_WIDE_ROAD in available_streams and VisionStreamType.VISION_STREAM_ROAD in available_streams
      main_wide_camera = VisionStreamType.VISION_STREAM_ROAD not in available_streams
      break
    time.sleep(.1)

  vipc_client_main_stream: VisionStreamType = VisionStreamType.VISION_STREAM_WIDE_ROAD if main_wide_camera else VisionStreamType.VISION_STREAM_ROAD
  vipc_client_main = VisionIpcClient("camerad", vipc_client_main_stream, True, cl_context)
  if use_extra_client:
    vipc_client_extra = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_WIDE_ROAD, False, cl_context)
  cloudlog.warning(f"vision stream set up, main_wide_camera: {main_wide_camera}, use_extra_client: {use_extra_client}")

  while not vipc_client_main.connect(False):
    time.sleep(0.1)
  if use_extra_client:
    while not vipc_client_extra.connect(False):
      time.sleep(0.1)

  cloudlog.warning(f"connected main cam with buffer size: {vipc_client_main.buffer_len} ({vipc_client_main.width} x {vipc_client_main.height})")
  if use_extra_client:
    cloudlog.warning(f"connected extra cam with buffer size: {vipc_client_extra.buffer_len} ({vipc_client_extra.width} x {vipc_client_extra.height})")

  # messaging
  pm = PubMaster(["modelV2", "drivingModelData", "cameraOdometry"])
  sm = SubMaster(["deviceState", "carState", "roadCameraState", "liveCalibration", "driverMonitoringState", "carControl", "liveDelay"])

  publish_state = PublishState()
  params = CommonParams()

  # setup filter to track dropped frames
  frame_dropped_filter = FirstOrderFilter(0., 10., 1. / ModelConstants.MODEL_FREQ)
  frame_id: int = 0
  last_vipc_frame_id: int = 0
  run_count: int = 0

  model_transform_main: np.ndarray = np.zeros((3, 3), dtype=np.float32)
  model_transform_extra: np.ndarray = np.zeros((3, 3), dtype=np.float32)
  live_calib_seen: bool = False
  buf_main: Optional[VisionBuf] = None
  buf_extra: Optional[VisionBuf] = None
  meta_main = FrameMeta()
  meta_extra = FrameMeta()


  CP: car.CarParams.Reader
  if demo:
    CP = get_demo_car_params()
  else:
    CP = messaging.log_from_bytes(params.get("CarParams", block=True), car.CarParams)
  cloudlog.info("modeld got CarParams: %s", CP.brand)

  # TODO this needs more thought, use .2s extra for now to estimate other delays
  # TODO Move smooth seconds to action function
  long_delay: float = CP.longitudinalActuatorDelay + LONG_SMOOTH_SECONDS
  prev_action: log.ModelDataV2.Action.Reader = log.ModelDataV2.Action.new_message().as_reader()

  DH = DesireHelper()

  while True:
    # Keep receiving frames until we are at least 1 frame ahead of previous extra frame
    while meta_main.timestamp_sof < meta_extra.timestamp_sof + 25000000:  # 25ms
      buf_main = vipc_client_main.recv()
      meta_main = FrameMeta(vipc_client_main)
      if buf_main is None:
        break

    if buf_main is None:
      cloudlog.debug("vipc_client_main no frame")
      continue

    if use_extra_client:
      # Keep receiving extra frames until frame id matches main camera
      while True:
        buf_extra = vipc_client_extra.recv()
        meta_extra = FrameMeta(vipc_client_extra)
        if buf_extra is None or meta_main.timestamp_sof < meta_extra.timestamp_sof + 25000000:  # 25ms
          break

      if buf_extra is None:
        cloudlog.debug("vipc_client_extra no frame")
        continue

      if abs(meta_main.timestamp_sof - meta_extra.timestamp_sof) > 10000000:  # 10ms
        cloudlog.error(f"frames out of sync! main: {meta_main.frame_id} ({meta_main.timestamp_sof / 1e9:.5f}),\
                         extra: {meta_extra.frame_id} ({meta_extra.timestamp_sof / 1e9:.5f})")

    else:
      # Use single camera
      buf_extra = buf_main
      meta_extra = meta_main

    sm.update(0)
    desire: log.Desire = DH.desire
    is_rhd: bool = sm["driverMonitoringState"].isRHD
    frame_id = sm["roadCameraState"].frameId
    v_ego: float = max(sm["carState"].vEgo, 0.)
    lat_delay: float = sm["liveDelay"].lateralDelay + LAT_SMOOTH_SECONDS
    lateral_control_params: np.ndarray = np.array([v_ego, lat_delay], dtype=np.float32)
    if sm.updated["liveCalibration"] and sm.seen['roadCameraState'] and sm.seen['deviceState']:
      device_from_calib_euler: np.ndarray = np.array(sm["liveCalibration"].rpyCalib, dtype=np.float32)
      dc = DEVICE_CAMERAS[(str(sm['deviceState'].deviceType), str(sm['roadCameraState'].sensor))]
      model_transform_main = get_warp_matrix(device_from_calib_euler, dc.ecam.intrinsics if main_wide_camera else dc.fcam.intrinsics, False).astype(np.float32)
      model_transform_extra = get_warp_matrix(device_from_calib_euler, dc.ecam.intrinsics, True).astype(np.float32)
      live_calib_seen = True

    traffic_convention: np.ndarray = np.zeros(2)
    traffic_convention[int(is_rhd)] = 1

    vec_desire: np.ndarray = np.zeros(ModelConstants.DESIRE_LEN, dtype=np.float32)
    if desire >= 0 and desire < ModelConstants.DESIRE_LEN:
      vec_desire[desire] = 1

    # tracked dropped frames
    vipc_dropped_frames: int = max(0, meta_main.frame_id - last_vipc_frame_id - 1)
    frames_dropped: float = frame_dropped_filter.update(min(vipc_dropped_frames, 10))
    if run_count < 10: # let frame drops warm up
      frame_dropped_filter.x = 0.
      frames_dropped = 0.
    run_count = run_count + 1

    frame_drop_ratio: float = frames_dropped / (1 + frames_dropped)
    prepare_only: bool = vipc_dropped_frames > 0
    if prepare_only:
      cloudlog.error(f"skipping model eval. Dropped {vipc_dropped_frames} frames")

    # Ensure bufs and transforms are correctly typed for model.run
    # Assuming model.vision_input_names are all strings
    current_bufs: Dict[str, VisionBuf] = {name: buf_extra if 'big' in name else buf_main for name in model.vision_input_names}
    current_transforms: Dict[str, np.ndarray] = {name: model_transform_extra if 'big' in name else model_transform_main for name in model.vision_input_names}


    model_inputs:Dict[str, np.ndarray] = {
      'desire': vec_desire,
      'traffic_convention': traffic_convention,
      'lateral_control_params': lateral_control_params,
    }

    mt1: float = time.perf_counter()
    model_output: Optional[Dict[str, np.ndarray]] = model.run(current_bufs, current_transforms, model_inputs, prepare_only)
    mt2: float = time.perf_counter()
    model_execution_time: float = mt2 - mt1

    if model_output is not None:
      modelv2_send = messaging.new_message('modelV2')
      drivingdata_send = messaging.new_message('drivingModelData')
      posenet_send = messaging.new_message('cameraOdometry')


      updated_action: log.ModelDataV2.Action.Builder = get_action_from_model(model_output, prev_action, lat_delay + DT_MDL, long_delay + DT_MDL, v_ego)
      prev_action = updated_action.as_reader()
      fill_model_msg(drivingdata_send, modelv2_send, model_output, updated_action.as_reader(),
                     publish_state, meta_main.frame_id, meta_extra.frame_id, frame_id,
                     frame_drop_ratio, meta_main.timestamp_eof, model_execution_time, live_calib_seen)

      desire_state: List[float] = modelv2_send.modelV2.meta.desireState
      l_lane_change_prob: float = desire_state[log.Desire.laneChangeLeft]
      r_lane_change_prob: float = desire_state[log.Desire.laneChangeRight]
      lane_change_prob: float = l_lane_change_prob + r_lane_change_prob
      DH.update(sm['carState'], sm['carControl'].latActive, lane_change_prob)
      modelv2_send.modelV2.meta.laneChangeState = DH.lane_change_state
      modelv2_send.modelV2.meta.laneChangeDirection = DH.lane_change_direction
      drivingdata_send.drivingModelData.meta.laneChangeState = DH.lane_change_state
      drivingdata_send.drivingModelData.meta.laneChangeDirection = DH.lane_change_direction

      fill_pose_msg(posenet_send, model_output, meta_main.frame_id, vipc_dropped_frames, meta_main.timestamp_eof, live_calib_seen)
      pm.send('modelV2', modelv2_send)
      pm.send('drivingModelData', drivingdata_send)
      pm.send('cameraOdometry', posenet_send)
    last_vipc_frame_id = meta_main.frame_id


if __name__ == "__main__":
  try:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='A boolean for demo mode.')
    args = parser.parse_args()
    main(demo=args.demo)
  except KeyboardInterrupt:
    cloudlog.warning(f"child {PROCESS_NAME} got SIGINT")
  except Exception:
    sentry.capture_exception()
    raise
