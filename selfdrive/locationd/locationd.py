#!/usr/bin/env python3
import os
import time
import capnp
import numpy as np
from enum import Enum
from collections import defaultdict
from typing import Dict, Any, Optional, Tuple, List, cast

from cereal import log, messaging
from cereal.messaging import PubMaster, SubMaster
from cereal.services import SERVICE_LIST
from openpilot.common.transformations.orientation import rot_from_euler
from openpilot.common.realtime import config_realtime_process
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.locationd.helpers import rotate_std
from openpilot.selfdrive.locationd.models.pose_kf import PoseKalman, States
from openpilot.selfdrive.locationd.models.constants import ObservationKind, GENERATED_DIR

ACCEL_SANITY_CHECK: float = 100.0  # m/s^2
ROTATION_SANITY_CHECK: float = 10.0  # rad/s
TRANS_SANITY_CHECK: float = 200.0  # m/s
CALIB_RPY_SANITY_CHECK: float = 0.5  # rad (+- 30 deg)
MIN_STD_SANITY_CHECK: float = 1e-5  # m or rad
MAX_FILTER_REWIND_TIME: float = 0.8  # s
MAX_SENSOR_TIME_DIFF: float = 0.1  # s
YAWRATE_CROSS_ERR_CHECK_FACTOR: int = 30
INPUT_INVALID_LIMIT: float = 2.0
INPUT_INVALID_RECOVERY: float = 10.0
POSENET_STD_INITIAL_VALUE: float = 10.0
POSENET_STD_HIST_HALF: int = 20


def calculate_invalid_input_decay(invalid_limit: float, recovery_time: float, frequency: float) -> float:
  return float((1 - 1 / (2 * invalid_limit)) ** (1 / (recovery_time * frequency)))


def init_xyz_measurement(measurement: capnp._DynamicStructBuilder, values: np.ndarray, stds: np.ndarray, valid: bool) -> None:
  assert len(values) == len(stds) == 3
  measurement.x = float(values[0])
  measurement.y = float(values[1])
  measurement.z = float(values[2])
  measurement.xStd = float(stds[0])
  measurement.yStd = float(stds[1])
  measurement.zStd = float(stds[2])
  measurement.valid = valid


class HandleLogResult(Enum):
  SUCCESS = 0
  TIMING_INVALID = 1
  INPUT_INVALID = 2
  SENSOR_SOURCE_INVALID = 3


class LocationEstimator:
  kf: PoseKalman
  debug: bool
  posenet_stds: np.ndarray
  car_speed: float
  camodo_yawrate_distribution: np.ndarray
  device_from_calib: np.ndarray
  observations: Dict[ObservationKind, np.ndarray]
  observation_errors: Dict[ObservationKind, np.ndarray]


  def __init__(self, debug: bool) -> None:
    self.kf = PoseKalman(GENERATED_DIR, MAX_FILTER_REWIND_TIME)
    self.debug = debug
    self.posenet_stds = np.array([POSENET_STD_INITIAL_VALUE] * (POSENET_STD_HIST_HALF * 2))
    self.car_speed = 0.0
    self.camodo_yawrate_distribution = np.array([0.0, 10.0])
    self.device_from_calib = np.eye(3)

    # Initialize with specific ObservationKind members
    self.observations = {
        ObservationKind.PHONE_ACCEL: np.zeros(3, dtype=np.float32),
        ObservationKind.PHONE_GYRO: np.zeros(3, dtype=np.float32),
        ObservationKind.CAMERA_ODO_ROTATION: np.zeros(3, dtype=np.float32),
        ObservationKind.CAMERA_ODO_TRANSLATION: np.zeros(3, dtype=np.float32),
    }
    self.observation_errors = {
        ObservationKind.PHONE_ACCEL: np.zeros(3, dtype=np.float32),
        ObservationKind.PHONE_GYRO: np.zeros(3, dtype=np.float32),
        ObservationKind.CAMERA_ODO_ROTATION: np.zeros(3, dtype=np.float32),
        ObservationKind.CAMERA_ODO_TRANSLATION: np.zeros(3, dtype=np.float32),
    }


  def reset(self, t: Optional[float], x_initial: np.ndarray = PoseKalman.initial_x, P_initial: np.ndarray = PoseKalman.initial_P) -> None:
    self.kf.init_state(x_initial, covs=P_initial, filter_time=t)

  def _validate_sensor_source(self, source: log.SensorEventData.SensorSource.Reader) -> bool:
    return source != log.SensorEventData.SensorSource.bmx055 # Direct comparison for Cap'n Proto enums

  def _validate_sensor_time(self, sensor_time: float, t: float) -> bool:
    if sensor_time == 0:
      return False
    sensor_time_invalid: bool = abs(sensor_time - t) > MAX_SENSOR_TIME_DIFF
    if sensor_time_invalid:
      cloudlog.warning("Sensor reading ignored, sensor timestamp more than 100ms off from log time")
    return not sensor_time_invalid

  def _validate_timestamp(self, t: float) -> bool:
    kf_t: float = self.kf.t
    invalid: bool = not np.isnan(kf_t) and (kf_t - t) > MAX_FILTER_REWIND_TIME
    if invalid:
      cloudlog.warning("Observation timestamp is older than the max rewind threshold of the filter")
    return not invalid

  def _finite_check(self, t: Optional[float], new_x: np.ndarray, new_P: np.ndarray) -> None:
    all_finite: bool = np.isfinite(new_x).all() and np.isfinite(new_P).all()
    if not all_finite:
      cloudlog.error("Non-finite values detected, kalman reset")
      self.reset(t)

  def handle_log(self, t: float, which: str, msg: capnp._DynamicStructReader) -> HandleLogResult:
    new_x: Optional[np.ndarray] = None
    new_P: Optional[np.ndarray] = None
    if which == "accelerometer" and msg.which() == "acceleration":
      sensor_data: log.SensorEventData.Reader = cast(log.SensorEventData.Reader, msg)
      sensor_time: float = sensor_data.timestamp * 1e-9
      if not self._validate_sensor_time(sensor_time, t) or not self._validate_timestamp(sensor_time):
        return HandleLogResult.TIMING_INVALID
      if not self._validate_sensor_source(sensor_data.source):
        return HandleLogResult.SENSOR_SOURCE_INVALID
      v: List[float] = sensor_data.acceleration.v
      meas: np.ndarray = np.array([-v[2], -v[1], -v[0]])
      if np.linalg.norm(meas) >= ACCEL_SANITY_CHECK:
        return HandleLogResult.INPUT_INVALID
      acc_res = self.kf.predict_and_observe(sensor_time, ObservationKind.PHONE_ACCEL, meas)
      if acc_res is not None:
        _, new_x, _, new_P, _, _, acc_err_tuple, _, _ = acc_res
        acc_err: List[float] = cast(List[float], acc_err_tuple[0])
        self.observation_errors[ObservationKind.PHONE_ACCEL] = np.array(acc_err)
        self.observations[ObservationKind.PHONE_ACCEL] = meas

    elif which == "gyroscope" and msg.which() == "gyroUncalibrated":
      sensor_data_gyro: log.SensorEventData.Reader = cast(log.SensorEventData.Reader, msg)
      sensor_time_gyro: float = sensor_data_gyro.timestamp * 1e-9
      if not self._validate_sensor_time(sensor_time_gyro, t) or not self._validate_timestamp(sensor_time_gyro):
        return HandleLogResult.TIMING_INVALID
      if not self._validate_sensor_source(sensor_data_gyro.source):
        return HandleLogResult.SENSOR_SOURCE_INVALID
      v_gyro: List[float] = sensor_data_gyro.gyroUncalibrated.v
      meas_gyro: np.ndarray = np.array([-v_gyro[2], -v_gyro[1], -v_gyro[0]])
      gyro_bias: np.ndarray = self.kf.x[States.GYRO_BIAS]
      gyro_camodo_yawrate_err: float = np.abs((meas_gyro[2] - gyro_bias[2]) - self.camodo_yawrate_distribution[0])
      gyro_camodo_yawrate_err_threshold: float = YAWRATE_CROSS_ERR_CHECK_FACTOR * self.camodo_yawrate_distribution[1]
      gyro_valid: bool = gyro_camodo_yawrate_err < gyro_camodo_yawrate_err_threshold
      if np.linalg.norm(meas_gyro) >= ROTATION_SANITY_CHECK or not gyro_valid:
        return HandleLogResult.INPUT_INVALID
      gyro_res = self.kf.predict_and_observe(sensor_time_gyro, ObservationKind.PHONE_GYRO, meas_gyro)
      if gyro_res is not None:
        _, new_x, _, new_P, _, _, gyro_err_tuple, _, _ = gyro_res
        gyro_err: List[float] = cast(List[float], gyro_err_tuple[0])
        self.observation_errors[ObservationKind.PHONE_GYRO] = np.array(gyro_err)
        self.observations[ObservationKind.PHONE_GYRO] = meas_gyro

    elif which == "carState":
      car_state_data: log.CarState.Reader = cast(log.CarState.Reader, msg)
      self.car_speed = abs(car_state_data.vEgo)

    elif which == "liveCalibration":
      calib_data: log.LiveCalibrationData.Reader = cast(log.LiveCalibrationData.Reader, msg)
      if len(calib_data.rpyCalib) > 0:
        calib_np: np.ndarray = np.array(calib_data.rpyCalib)
        if calib_np.min() < -CALIB_RPY_SANITY_CHECK or calib_np.max() > CALIB_RPY_SANITY_CHECK:
          return HandleLogResult.INPUT_INVALID
        self.device_from_calib = rot_from_euler(calib_np)

    elif which == "cameraOdometry":
      cam_odo_data: log.CameraOdometry.Reader = cast(log.CameraOdometry.Reader, msg)
      if not self._validate_timestamp(t):
        return HandleLogResult.TIMING_INVALID
      rot_device: np.ndarray = np.matmul(self.device_from_calib, np.array(cam_odo_data.rot))
      trans_device: np.ndarray = np.matmul(self.device_from_calib, np.array(cam_odo_data.trans))
      if np.linalg.norm(rot_device) > ROTATION_SANITY_CHECK or np.linalg.norm(trans_device) > TRANS_SANITY_CHECK:
        return HandleLogResult.INPUT_INVALID
      rot_calib_std: np.ndarray = np.array(cam_odo_data.rotStd)
      trans_calib_std: np.ndarray = np.array(cam_odo_data.transStd)
      if rot_calib_std.min() <= MIN_STD_SANITY_CHECK or trans_calib_std.min() <= MIN_STD_SANITY_CHECK:
        return HandleLogResult.INPUT_INVALID
      if np.linalg.norm(rot_calib_std) > 10 * ROTATION_SANITY_CHECK or np.linalg.norm(trans_calib_std) > 10 * TRANS_SANITY_CHECK:
        return HandleLogResult.INPUT_INVALID
      self.posenet_stds = np.roll(self.posenet_stds, -1)
      self.posenet_stds[-1] = trans_calib_std[0]
      rot_calib_std *= 10
      trans_calib_std *= 2
      rot_device_std: np.ndarray = rotate_std(self.device_from_calib, rot_calib_std)
      trans_device_std: np.ndarray = rotate_std(self.device_from_calib, trans_calib_std)
      rot_device_noise: np.ndarray = rot_device_std ** 2
      trans_device_noise: np.ndarray = trans_device_std ** 2
      cam_odo_rot_res = self.kf.predict_and_observe(t, ObservationKind.CAMERA_ODO_ROTATION, rot_device, np.array([np.diag(rot_device_noise)]))
      cam_odo_trans_res = self.kf.predict_and_observe(t, ObservationKind.CAMERA_ODO_TRANSLATION, trans_device, np.array([np.diag(trans_device_noise)]))
      self.camodo_yawrate_distribution = np.array([rot_device[2], rot_device_std[2]])
      if cam_odo_rot_res is not None:
        _, new_x, _, new_P, _, _, cam_odo_rot_err_tuple, _, _ = cam_odo_rot_res
        cam_odo_rot_err: List[float] = cast(List[float], cam_odo_rot_err_tuple[0])
        self.observation_errors[ObservationKind.CAMERA_ODO_ROTATION] = np.array(cam_odo_rot_err)
        self.observations[ObservationKind.CAMERA_ODO_ROTATION] = rot_device
      if cam_odo_trans_res is not None:
        _, new_x, _, new_P, _, _, cam_odo_trans_err_tuple, _, _ = cam_odo_trans_res
        cam_odo_trans_err: List[float] = cast(List[float], cam_odo_trans_err_tuple[0])
        self.observation_errors[ObservationKind.CAMERA_ODO_TRANSLATION] = np.array(cam_odo_trans_err)
        self.observations[ObservationKind.CAMERA_ODO_TRANSLATION] = trans_device

    if new_x is not None and new_P is not None:
      self._finite_check(t, new_x, new_P)
    return HandleLogResult.SUCCESS

  def get_msg(self, sensors_valid: bool, inputs_valid: bool, filter_valid: bool) -> capnp._DynamicStructBuilder:
    state: np.ndarray
    cov: np.ndarray
    state, cov = self.kf.x, self.kf.P
    std: np.ndarray = np.sqrt(np.diag(cov))

    orientation_ned: np.ndarray
    orientation_ned_std: np.ndarray
    velocity_device: np.ndarray
    velocity_device_std: np.ndarray
    angular_velocity_device: np.ndarray
    angular_velocity_device_std: np.ndarray
    acceleration_device: np.ndarray
    acceleration_device_std: np.ndarray

    orientation_ned, orientation_ned_std = state[States.NED_ORIENTATION], std[States.NED_ORIENTATION]
    velocity_device, velocity_device_std = state[States.DEVICE_VELOCITY], std[States.DEVICE_VELOCITY]
    angular_velocity_device, angular_velocity_device_std = state[States.ANGULAR_VELOCITY], std[States.ANGULAR_VELOCITY]
    acceleration_device, acceleration_device_std = state[States.ACCELERATION], std[States.ACCELERATION]

    msg = messaging.new_message("livePose")
    msg.valid = filter_valid

    livePose = msg.livePose
    init_xyz_measurement(livePose.orientationNED, orientation_ned, orientation_ned_std, filter_valid)
    init_xyz_measurement(livePose.velocityDevice, velocity_device, velocity_device_std, filter_valid)
    init_xyz_measurement(livePose.angularVelocityDevice, angular_velocity_device, angular_velocity_device_std, filter_valid)
    init_xyz_measurement(livePose.accelerationDevice, acceleration_device, acceleration_device_std, filter_valid)
    if self.debug:
      livePose.debugFilterState.value = state.tolist()
      livePose.debugFilterState.std = std.tolist()
      livePose.debugFilterState.valid = filter_valid
      # Use k.value for serialization as 'kind' in the schema is likely string or int
      livePose.debugFilterState.observations = [
        {'kind': k.value, 'value': self.observations[k].tolist(), 'error': self.observation_errors[k].tolist()}
        for k in self.observations.keys()
      ]

    old_mean: float = np.mean(self.posenet_stds[:POSENET_STD_HIST_HALF])
    new_mean: float = np.mean(self.posenet_stds[POSENET_STD_HIST_HALF:])
    std_spike: bool = (new_mean / old_mean) > 4.0 and new_mean > 7.0

    livePose.inputsOK = inputs_valid
    livePose.posenetOK = not std_spike or self.car_speed <= 5.0
    livePose.sensorsOK = sensors_valid

    return msg


def sensor_all_checks(acc_msgs: list[capnp._DynamicStructReader], gyro_msgs: list[capnp._DynamicStructReader], sensor_valid: Dict[str, bool],
                      sensor_recv_time: Dict[str, float], sensor_alive: Dict[str, bool], simulation: bool) -> bool:
  cur_time: float = time.monotonic()
  which: str
  msgs: list[capnp._DynamicStructReader]
  for which, msgs in [("accelerometer", acc_msgs), ("gyroscope", gyro_msgs)]:
    if len(msgs) > 0:
      sensor_valid[which] = msgs[-1].valid
      sensor_recv_time[which] = cur_time

    if not simulation:
      sensor_alive[which] = (cur_time - sensor_recv_time[which]) < 0.1
    else:
      sensor_alive[which] = len(msgs) > 0

  return all(sensor_alive.values()) and all(sensor_valid.values())


def main() -> None:
  config_realtime_process([0, 1, 2, 3], 5)

  DEBUG: bool = bool(int(os.getenv("DEBUG", "0")))
  SIMULATION: bool = bool(int(os.getenv("SIMULATION", "0")))

  pm = PubMaster(['livePose'])
  sm = SubMaster(['carState', 'liveCalibration', 'cameraOdometry'], poll='cameraOdometry')
  sensor_sockets: list[messaging.SubSocket] = [messaging.sub_sock(str(which), timeout=20) for which in ['accelerometer', 'gyroscope']]
  sensor_alive: Dict[str, bool] = defaultdict(bool)
  sensor_valid: Dict[str, bool] = defaultdict(bool)
  sensor_recv_time: Dict[str, float] = defaultdict(float)


  params = Params()

  estimator = LocationEstimator(DEBUG)

  filter_initialized: bool = False
  critcal_services: list[str] = ["accelerometer", "gyroscope", "cameraOdometry"]
  observation_input_invalid: Dict[str, float] = defaultdict(float)

  input_invalid_limit: Dict[str, float] = {s: round(INPUT_INVALID_LIMIT * (SERVICE_LIST[s].frequency / 20.)) for s in critcal_services}
  input_invalid_threshold: Dict[str, float] = {s: input_invalid_limit[s] - 0.5 for s in critcal_services}
  input_invalid_decay: Dict[str, float] = {s: calculate_invalid_input_decay(input_invalid_limit[s], INPUT_INVALID_RECOVERY, SERVICE_LIST[s].frequency) for s in critcal_services}

  initial_pose_data: Optional[bytes] = params.get("LocationFilterInitialState")
  if initial_pose_data is not None:
    with log.Event.from_bytes(initial_pose_data) as lp_msg:
      filter_state: log.LivePose.DebugFilterState.Reader = lp_msg.livePose.debugFilterState
      x_initial_list: List[float] = filter_state.value
      P_initial_diag_list: List[float] = filter_state.std
      x_initial_np: np.ndarray = np.array(x_initial_list, dtype=np.float64) if len(x_initial_list) != 0 else PoseKalman.initial_x
      P_initial_np: np.ndarray = np.diag(np.array(P_initial_diag_list, dtype=np.float64)) if len(P_initial_diag_list) != 0 else PoseKalman.initial_P
      estimator.reset(None, x_initial_np, P_initial_np)

  while True:
    sm.update()

    acc_msgs_raw: list[capnp._DynamicStructReader] = messaging.drain_sock(sensor_sockets[0])
    gyro_msgs_raw: list[capnp._DynamicStructReader] = messaging.drain_sock(sensor_sockets[1])


    if filter_initialized:
      msgs_to_process: list[Tuple[float, bool, str, capnp._DynamicStructReader]] = []
      msg_item: capnp._DynamicStructReader
      for msg_item in acc_msgs_raw + gyro_msgs_raw:
        t_val: float = msg_item.logMonoTime
        valid_val: bool = msg_item.valid
        which_val: str = msg_item.which()
        data_val: capnp._DynamicStructReader = getattr(msg_item, msg_item.which())
        msgs_to_process.append((t_val, valid_val, which_val, data_val))

      which_key: str
      for which_key in sm.updated:
        if not sm.updated[which_key]:
          continue
        t_val_sm: float = sm.logMonoTime[which_key]
        valid_val_sm: bool = sm.valid[which_key]
        data_val_sm: capnp._DynamicStructReader = sm[which_key]
        msgs_to_process.append((t_val_sm, valid_val_sm, which_key, data_val_sm))

      log_mono_time_val: float
      valid_processing_val: bool
      which_processing_val: str
      msg_processing_val: capnp._DynamicStructReader
      for log_mono_time_val, valid_processing_val, which_processing_val, msg_processing_val in sorted(msgs_to_process, key=lambda x: x[0]):
        if valid_processing_val:
          t_proc: float = log_mono_time_val * 1e-9
          res: HandleLogResult = estimator.handle_log(t_proc, which_processing_val, msg_processing_val)
          if which_processing_val not in critcal_services:
            continue

          if res == HandleLogResult.TIMING_INVALID:
            cloudlog.warning(f"Observation {which_processing_val} ignored due to failed timing check")
            observation_input_invalid[which_processing_val] += 1
          elif res == HandleLogResult.INPUT_INVALID:
            cloudlog.warning(f"Observation {which_processing_val} ignored due to failed sanity check")
            observation_input_invalid[which_processing_val] += 1
          elif res == HandleLogResult.SUCCESS:
            observation_input_invalid[which_processing_val] *= input_invalid_decay[which_processing_val]
    else:
      filter_initialized = sm.all_checks() and sensor_all_checks(acc_msgs_raw, gyro_msgs_raw, sensor_valid, sensor_recv_time, sensor_alive, SIMULATION)

    if sm.updated["cameraOdometry"]:
      critical_service_inputs_valid_val: bool = all(observation_input_invalid[s] < input_invalid_threshold[s] for s in critcal_services)
      inputs_valid_val: bool = sm.all_valid() and critical_service_inputs_valid_val
      sensors_valid_val: bool = sensor_all_checks(acc_msgs_raw, gyro_msgs_raw, sensor_valid, sensor_recv_time, sensor_alive, SIMULATION)

      final_msg: capnp._DynamicStructBuilder = estimator.get_msg(sensors_valid_val, inputs_valid_val, filter_initialized)
      pm.send("livePose", final_msg)


if __name__ == "__main__":
  main()
