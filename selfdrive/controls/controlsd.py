#!/usr/bin/env python3
import math
from typing import SupportsFloat, Any, Tuple, List, Optional

from cereal import car, log
import cereal.messaging as messaging
from cereal.messaging import SubMaster, PubMaster # pylint: disable=no-name-in-module
from openpilot.common.conversions import Conversions as CV
from openpilot.common.params import Params
from openpilot.common.realtime import config_realtime_process, Priority, Ratekeeper
from openpilot.common.swaglog import cloudlog

from opendbc.car.car_helpers import interfaces
from opendbc.car.interfaces import CarInterfaceBase
from opendbc.car.vehicle_model import VehicleModel
from openpilot.selfdrive.controls.lib.drive_helpers import clip_curvature
from openpilot.selfdrive.controls.lib.latcontrol import LatControl
from openpilot.selfdrive.controls.lib.latcontrol_pid import LatControlPID
from openpilot.selfdrive.controls.lib.latcontrol_angle import LatControlAngle, STEER_ANGLE_SATURATION_THRESHOLD
from openpilot.selfdrive.controls.lib.latcontrol_torque import LatControlTorque
from openpilot.selfdrive.controls.lib.longcontrol import LongControl
from openpilot.selfdrive.locationd.helpers import PoseCalibrator, Pose

State = log.SelfdriveState.OpenpilotState
LaneChangeState = log.LaneChangeState
LaneChangeDirection = log.LaneChangeDirection

ACTUATOR_FIELDS: Tuple[str, ...] = tuple(car.CarControl.Actuators.schema.fields.keys())


class Controls:
  params: Params
  CP: car.CarParams
  CI: CarInterfaceBase
  sm: SubMaster
  pm: PubMaster
  steer_limited_by_controls: bool
  curvature: float
  desired_curvature: float
  pose_calibrator: PoseCalibrator
  calibrated_pose: Pose | None
  LoC: LongControl
  VM: VehicleModel
  LaC: LatControl


  def __init__(self) -> None:
    self.params = Params()
    cloudlog.info("controlsd is waiting for CarParams")
    # TODO: change type of self.CP after this issue is resolved: https://github.com/commaai/cereal/issues/1433
    self.CP = messaging.log_from_bytes(self.params.get("CarParams", block=True), car.CarParams)
    cloudlog.info("controlsd got CarParams")

    self.CI = interfaces[self.CP.carFingerprint](self.CP)

    self.sm = messaging.SubMaster(['liveParameters', 'liveTorqueParameters', 'modelV2', 'selfdriveState',
                                   'liveCalibration', 'livePose', 'longitudinalPlan', 'carState', 'carOutput',
                                   'driverMonitoringState', 'onroadEvents', 'driverAssistance'], poll='selfdriveState')
    self.pm = messaging.PubMaster(['carControl', 'controlsState'])

    self.steer_limited_by_controls = False
    self.curvature = 0.0
    self.desired_curvature = 0.0

    self.pose_calibrator = PoseCalibrator()
    self.calibrated_pose = None

    self.LoC = LongControl(self.CP)
    self.VM = VehicleModel(self.CP)
    if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
      self.LaC = LatControlAngle(self.CP, self.CI)
    elif self.CP.lateralTuning.which() == 'pid':
      self.LaC = LatControlPID(self.CP, self.CI)
    elif self.CP.lateralTuning.which() == 'torque':
      self.LaC = LatControlTorque(self.CP, self.CI)
    else:
      raise ValueError(f"Unsupported steerControlType: {self.CP.steerControlType}")

  def update(self) -> None:
    self.sm.update(15)
    if self.sm.updated["liveCalibration"]:
      self.pose_calibrator.feed_live_calib(self.sm['liveCalibration'])
    if self.sm.updated["livePose"]:
      device_pose = Pose.from_live_pose(self.sm['livePose'])
      self.calibrated_pose = self.pose_calibrator.build_calibrated_pose(device_pose)

  def state_control(self) -> Tuple[car.CarControl.Builder, log.ControlsState.LateralControlState.Builder]:
    CS: car.CarState = self.sm['carState']

    # Update VehicleModel
    lp: log.LiveParametersData = self.sm['liveParameters']
    x: float = max(lp.stiffnessFactor, 0.1)
    sr: float = max(lp.steerRatio, 0.1)
    self.VM.update_params(x, sr)

    steer_angle_without_offset: float = math.radians(CS.steeringAngleDeg - lp.angleOffsetDeg)
    self.curvature = -self.VM.calc_curvature(steer_angle_without_offset, CS.vEgo, lp.roll)

    # Update Torque Params
    if self.CP.lateralTuning.which() == 'torque':
      torque_params: log.LiveTorqueParametersData = self.sm['liveTorqueParameters']
      if self.sm.all_checks(['liveTorqueParameters']) and torque_params.useParams:
        # Ensure LaC is LatControlTorque before calling update_live_torque_params
        if isinstance(self.LaC, LatControlTorque):
          self.LaC.update_live_torque_params(torque_params.latAccelFactorFiltered, torque_params.latAccelOffsetFiltered,
                                             torque_params.frictionCoefficientFiltered)

    long_plan: log.LongitudinalPlanData = self.sm['longitudinalPlan']
    model_v2: log.ModelDataV2 = self.sm['modelV2']

    CC: car.CarControl.Builder = car.CarControl.new_message()
    CC.enabled = self.sm['selfdriveState'].enabled

    # Check which actuators can be enabled
    standstill: bool = abs(CS.vEgo) <= max(self.CP.minSteerSpeed, 0.3) or CS.standstill
    CC.latActive = self.sm['selfdriveState'].active and not CS.steerFaultTemporary and not CS.steerFaultPermanent and \
                   (not standstill or self.CP.steerAtStandstill)
    CC.longActive = CC.enabled and not any(e.overrideLongitudinal for e in self.sm['onroadEvents']) and self.CP.openpilotLongitudinalControl

    actuators: car.CarControl.Actuators.Builder = CC.actuators
    actuators.longControlState = self.LoC.long_control_state

    # Enable blinkers while lane changing
    if model_v2.meta.laneChangeState != LaneChangeState.off:
      CC.leftBlinker = model_v2.meta.laneChangeDirection == LaneChangeDirection.left
      CC.rightBlinker = model_v2.meta.laneChangeDirection == LaneChangeDirection.right

    if not CC.latActive:
      self.LaC.reset()
    if not CC.longActive:
      self.LoC.reset()

    # accel PID loop
    pid_accel_limits: List[float] = self.CI.get_pid_accel_limits(self.CP, CS.vEgo, CS.vCruise * CV.KPH_TO_MS)
    actuators.accel = float(self.LoC.update(CC.longActive, CS, long_plan.aTarget, long_plan.shouldStop, pid_accel_limits))

    # Steering PID loop and lateral MPC
    # Reset desired curvature to current to avoid violating the limits on engage
    new_desired_curvature: float = model_v2.action.desiredCurvature if CC.latActive else self.curvature
    self.desired_curvature, curvature_limited = clip_curvature(CS.vEgo, self.desired_curvature, new_desired_curvature, lp.roll)

    actuators.curvature = self.desired_curvature
    steer: float
    steeringAngleDeg: float
    lac_log: log.ControlsState.LateralControlState.Builder
    steer, steeringAngleDeg, lac_log = self.LaC.update(CC.latActive, CS, self.VM, lp,
                                                       self.steer_limited_by_controls, self.desired_curvature,
                                                       self.calibrated_pose, curvature_limited)  # TODO what if not available
    actuators.torque = float(steer)
    actuators.steeringAngleDeg = float(steeringAngleDeg)
    # Ensure no NaNs/Infs
    p: str
    for p in ACTUATOR_FIELDS:
      attr: Any = getattr(actuators, p)
      if not isinstance(attr, SupportsFloat):
        continue

      if not math.isfinite(attr):
        cloudlog.error(f"actuators.{p} not finite {actuators.to_dict()}")
        setattr(actuators, p, 0.0)

    return CC, lac_log

  def publish(self, CC: car.CarControl.Builder, lac_log: log.ControlsState.LateralControlState.Builder) -> None:
    CS: car.CarState = self.sm['carState']

    # Orientation and angle rates can be useful for carcontroller
    # Only calibrated (car) frame is relevant for the carcontroller
    CC.currentCurvature = self.curvature
    if self.calibrated_pose is not None:
      CC.orientationNED = self.calibrated_pose.orientation.xyz.tolist()
      CC.angularVelocity = self.calibrated_pose.angular_velocity.xyz.tolist()

    CC.cruiseControl.override = CC.enabled and not CC.longActive and self.CP.openpilotLongitudinalControl
    CC.cruiseControl.cancel = CS.cruiseState.enabled and (not CC.enabled or not self.CP.pcmCruise)

    speeds: List[float] = self.sm['longitudinalPlan'].speeds
    if len(speeds):
      CC.cruiseControl.resume = CC.enabled and CS.cruiseState.standstill and speeds[-1] > 0.1

    hudControl: car.CarControl.HUDControl.Builder = CC.hudControl
    hudControl.setSpeed = float(CS.vCruiseCluster * CV.KPH_TO_MS)
    hudControl.speedVisible = CC.enabled
    hudControl.lanesVisible = CC.enabled
    hudControl.leadVisible = self.sm['longitudinalPlan'].hasLead
    hudControl.leadDistanceBars = self.sm['selfdriveState'].personality.raw + 1
    hudControl.visualAlert = self.sm['selfdriveState'].alertHudVisual

    hudControl.rightLaneVisible = True
    hudControl.leftLaneVisible = True
    if self.sm.valid['driverAssistance']:
      hudControl.leftLaneDepart = self.sm['driverAssistance'].leftLaneDeparture
      hudControl.rightLaneDepart = self.sm['driverAssistance'].rightLaneDeparture

    if self.sm['selfdriveState'].active:
      CO: car.CarOutput = self.sm['carOutput']
      if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
        self.steer_limited_by_controls = abs(CC.actuators.steeringAngleDeg - CO.actuatorsOutput.steeringAngleDeg) > \
                                              STEER_ANGLE_SATURATION_THRESHOLD
      else:
        self.steer_limited_by_controls = abs(CC.actuators.torque - CO.actuatorsOutput.torque) > 1e-2

    # TODO: both controlsState and carControl valids should be set by
    #       sm.all_checks(), but this creates a circular dependency

    # controlsState
    dat: log.ControlsState.Builder = messaging.new_message('controlsState')
    dat.valid = CS.canValid
    cs: log.ControlsState.Builder = dat.controlsState

    cs.curvature = self.curvature
    cs.longitudinalPlanMonoTime = self.sm.logMonoTime['longitudinalPlan']
    cs.lateralPlanMonoTime = self.sm.logMonoTime['modelV2']
    cs.desiredCurvature = self.desired_curvature
    cs.longControlState = self.LoC.long_control_state
    cs.upAccelCmd = float(self.LoC.pid.p)
    cs.uiAccelCmd = float(self.LoC.pid.i)
    cs.ufAccelCmd = float(self.LoC.pid.f)
    cs.forceDecel = bool((self.sm['driverMonitoringState'].awarenessStatus < 0.) or
                         (self.sm['selfdriveState'].state == State.softDisabling))

    lat_tuning: str = self.CP.lateralTuning.which()
    if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
      cs.lateralControlState.angleState = lac_log
    elif lat_tuning == 'pid':
      cs.lateralControlState.pidState = lac_log
    elif lat_tuning == 'torque':
      cs.lateralControlState.torqueState = lac_log

    self.pm.send('controlsState', dat)

    # carControl
    cc_send: car.CarControl.Builder = messaging.new_message('carControl')
    cc_send.valid = CS.canValid
    cc_send.carControl = CC
    self.pm.send('carControl', cc_send)

  def run(self) -> None:
    rk: Ratekeeper = Ratekeeper(100, print_delay_threshold=None)
    while True:
      self.update()
      CC, lac_log = self.state_control()
      self.publish(CC, lac_log)
      rk.monitor_time()


def main() -> None:
  config_realtime_process(4, Priority.CTRL_HIGH)
  controls: Controls = Controls()
  controls.run()


if __name__ == "__main__":
  main()
