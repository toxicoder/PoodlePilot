import math
from typing import Any, Tuple # Added for type hinting

from cereal import car, log
from openpilot.selfdrive.controls.lib.latcontrol import LatControl
from opendbc.car.vehicle_model import VehicleModel # Added for type hinting


STEER_ANGLE_SATURATION_THRESHOLD: float = 2.5  # Degrees


class LatControlAngle(LatControl):
  use_steer_limited_by_controls: bool

  def __init__(self, CP: car.CarParams.Reader, CI: Any) -> None: # CI type is CarInterfaceBase
    super().__init__(CP, CI)
    self.sat_check_min_speed = 5.
    self.use_steer_limited_by_controls = CP.brand == "tesla"

  def update(self, active: bool, CS: car.CarState.Reader, VM: VehicleModel, params: log.LiveParametersData.Reader,
             steer_limited_by_controls: bool, desired_curvature: float, calibrated_pose: Any, # calibrated_pose is locationd.helpers.Pose
             curvature_limited: bool) -> Tuple[float, float, log.ControlsState.LateralAngleState.Builder]:
    angle_log: log.ControlsState.LateralAngleState.Builder = log.ControlsState.LateralAngleState.new_message()
    angle_steers_des: float

    if not active:
      angle_log.active = False
      angle_steers_des = float(CS.steeringAngleDeg)
    else:
      angle_log.active = True
      angle_steers_des = math.degrees(VM.get_steer_from_curvature(-desired_curvature, CS.vEgo, params.roll))
      angle_steers_des += params.angleOffsetDeg

    angle_control_saturated: bool
    if self.use_steer_limited_by_controls:
      # these cars' carcontrollers calculate max lateral accel and jerk, so we can rely on carOutput for saturation
      angle_control_saturated = steer_limited_by_controls
    else:
      # for cars which use a method of limiting torque such as a torque signal (Nissan and Toyota)
      # or relying on EPS (Ford Q3), carOutput does not capture maxing out torque  # TODO: this can be improved
      angle_control_saturated = abs(angle_steers_des - CS.steeringAngleDeg) > STEER_ANGLE_SATURATION_THRESHOLD
    angle_log.saturated = bool(self._check_saturation(angle_control_saturated, CS, False, curvature_limited))
    angle_log.steeringAngleDeg = float(CS.steeringAngleDeg)
    angle_log.steeringAngleDesiredDeg = angle_steers_des
    return 0.0, float(angle_steers_des), angle_log
