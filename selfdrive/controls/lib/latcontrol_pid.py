import math
from typing import Any, Callable, Tuple # Added for type hinting

from cereal import car, log
from openpilot.selfdrive.controls.lib.latcontrol import LatControl
from openpilot.common.pid import PIDController
from opendbc.car.vehicle_model import VehicleModel # Added for type hinting


class LatControlPID(LatControl):
  pid: PIDController
  get_steer_feedforward: Callable[[float, float], float]

  def __init__(self, CP: car.CarParams.Reader, CI: Any) -> None: # CI type is CarInterfaceBase
    super().__init__(CP, CI)
    self.pid = PIDController((CP.lateralTuning.pid.kpBP, CP.lateralTuning.pid.kpV),
                             (CP.lateralTuning.pid.kiBP, CP.lateralTuning.pid.kiV),
                             k_f=CP.lateralTuning.pid.kf, pos_limit=self.steer_max, neg_limit=-self.steer_max)
    self.get_steer_feedforward = CI.get_steer_feedforward_function()

  def reset(self) -> None:
    super().reset()
    self.pid.reset()

  def update(self, active: bool, CS: car.CarState.Reader, VM: VehicleModel, params: log.LiveParametersData.Reader,
             steer_limited_by_controls: bool, desired_curvature: float, calibrated_pose: Any, # calibrated_pose is locationd.helpers.Pose
             curvature_limited: bool) -> Tuple[float, float, log.ControlsState.LateralPIDState.Builder]:
    pid_log: log.ControlsState.LateralPIDState.Builder = log.ControlsState.LateralPIDState.new_message()
    pid_log.steeringAngleDeg = float(CS.steeringAngleDeg)
    pid_log.steeringRateDeg = float(CS.steeringRateDeg)

    angle_steers_des_no_offset: float = math.degrees(VM.get_steer_from_curvature(-desired_curvature, CS.vEgo, params.roll))
    angle_steers_des: float = angle_steers_des_no_offset + params.angleOffsetDeg
    error: float = angle_steers_des - CS.steeringAngleDeg

    pid_log.steeringAngleDesiredDeg = angle_steers_des
    pid_log.angleError = error
    output_steer: float
    if not active:
      output_steer = 0.0
      pid_log.active = False
      self.pid.reset()
    else:
      # offset does not contribute to resistive torque
      steer_feedforward: float = self.get_steer_feedforward(angle_steers_des_no_offset, CS.vEgo)

      output_steer = self.pid.update(error, override=CS.steeringPressed,
                                     feedforward=steer_feedforward, speed=CS.vEgo)
      pid_log.active = True
      pid_log.p = float(self.pid.p)
      pid_log.i = float(self.pid.i)
      pid_log.f = float(self.pid.f)
      pid_log.output = float(output_steer)
      pid_log.saturated = bool(self._check_saturation(self.steer_max - abs(output_steer) < 1e-3, CS, steer_limited_by_controls, curvature_limited))

    return output_steer, angle_steers_des, pid_log
