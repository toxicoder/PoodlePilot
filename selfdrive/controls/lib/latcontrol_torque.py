import math
import numpy as np
from typing import Any, Callable, Tuple # Added for type hinting

from cereal import car, log
from opendbc.car.interfaces import LatControlInputs
from opendbc.car.vehicle_model import ACCELERATION_DUE_TO_GRAVITY, VehicleModel
from openpilot.selfdrive.controls.lib.latcontrol import LatControl
from openpilot.common.pid import PIDController

# At higher speeds (25+mph) we can assume:
# Lateral acceleration achieved by a specific car correlates to
# torque applied to the steering rack. It does not correlate to
# wheel slip, or to speed.

# This controller applies torque to achieve desired lateral
# accelerations. To compensate for the low speed effects we
# use a LOW_SPEED_FACTOR in the error. Additionally, there is
# friction in the steering wheel that needs to be overcome to
# move it at all, this is compensated for too.

LOW_SPEED_X: list[int] = [0, 10, 20, 30]
LOW_SPEED_Y: list[int] = [15, 13, 10, 5]


class LatControlTorque(LatControl):
  torque_params: car.CarParams.LateralTorqueTuning.Builder
  pid: PIDController
  torque_from_lateral_accel: Callable[[LatControlInputs, car.CarParams.LateralTorqueTuning.Reader, float, float, bool, bool], float]
  use_steering_angle: bool
  steering_angle_deadzone_deg: float

  def __init__(self, CP: car.CarParams.Reader, CI: Any) -> None: # CI type is CarInterfaceBase
    super().__init__(CP, CI)
    self.torque_params = CP.lateralTuning.torque.as_builder()
    self.pid = PIDController(self.torque_params.kp, self.torque_params.ki,
                             k_f=self.torque_params.kf, pos_limit=self.steer_max, neg_limit=-self.steer_max)
    self.torque_from_lateral_accel = CI.torque_from_lateral_accel()
    self.use_steering_angle = self.torque_params.useSteeringAngle
    self.steering_angle_deadzone_deg = self.torque_params.steeringAngleDeadzoneDeg

  def update_live_torque_params(self, latAccelFactor: float, latAccelOffset: float, friction: float) -> None:
    self.torque_params.latAccelFactor = latAccelFactor
    self.torque_params.latAccelOffset = latAccelOffset
    self.torque_params.friction = friction

  def update(self, active: bool, CS: car.CarState.Reader, VM: VehicleModel, params: log.LiveParametersData.Reader,
             steer_limited_by_controls: bool, desired_curvature: float, calibrated_pose: Any, # calibrated_pose is locationd.helpers.Pose
             curvature_limited: bool) -> Tuple[float, float, log.ControlsState.LateralTorqueState.Builder]:
    pid_log: log.ControlsState.LateralTorqueState.Builder = log.ControlsState.LateralTorqueState.new_message()
    output_torque: float
    if not active:
      output_torque = 0.0
      pid_log.active = False
    else:
      actual_curvature_vm: float = -VM.calc_curvature(math.radians(CS.steeringAngleDeg - params.angleOffsetDeg), CS.vEgo, params.roll)
      roll_compensation: float = params.roll * ACCELERATION_DUE_TO_GRAVITY
      actual_curvature: float
      curvature_deadzone: float
      if self.use_steering_angle:
        actual_curvature = actual_curvature_vm
        curvature_deadzone = abs(VM.calc_curvature(math.radians(self.steering_angle_deadzone_deg), CS.vEgo, 0.0))
      else:
        assert calibrated_pose is not None, "calibrated_pose must be available when use_steering_angle is False"
        actual_curvature_pose: float = calibrated_pose.angular_velocity.yaw / CS.vEgo
        actual_curvature = np.interp(CS.vEgo, [2.0, 5.0], [actual_curvature_vm, actual_curvature_pose])
        curvature_deadzone = 0.0
      desired_lateral_accel: float = desired_curvature * CS.vEgo ** 2

      # desired rate is the desired rate of change in the setpoint, not the absolute desired curvature
      # desired_lateral_jerk = desired_curvature_rate * CS.vEgo ** 2
      actual_lateral_accel: float = actual_curvature * CS.vEgo ** 2
      lateral_accel_deadzone: float = curvature_deadzone * CS.vEgo ** 2

      low_speed_factor: float = np.interp(CS.vEgo, LOW_SPEED_X, LOW_SPEED_Y)**2
      setpoint: float = desired_lateral_accel + low_speed_factor * desired_curvature
      measurement: float = actual_lateral_accel + low_speed_factor * actual_curvature
      gravity_adjusted_lateral_accel: float = desired_lateral_accel - roll_compensation
      torque_from_setpoint: float = self.torque_from_lateral_accel(LatControlInputs(setpoint, roll_compensation, CS.vEgo, CS.aEgo), self.torque_params.as_reader(),
                                                            setpoint, lateral_accel_deadzone, friction_compensation=False, gravity_adjusted=False)
      torque_from_measurement: float = self.torque_from_lateral_accel(LatControlInputs(measurement, roll_compensation, CS.vEgo, CS.aEgo), self.torque_params.as_reader(),
                                                               measurement, lateral_accel_deadzone, friction_compensation=False, gravity_adjusted=False)
      pid_log.error = float(torque_from_setpoint - torque_from_measurement)
      ff: float = self.torque_from_lateral_accel(LatControlInputs(gravity_adjusted_lateral_accel, roll_compensation, CS.vEgo, CS.aEgo), self.torque_params.as_reader(),
                                          desired_lateral_accel - actual_lateral_accel, lateral_accel_deadzone, friction_compensation=True,
                                          gravity_adjusted=True)

      freeze_integrator: bool = steer_limited_by_controls or CS.steeringPressed or CS.vEgo < 5
      output_torque = self.pid.update(pid_log.error,
                                      feedforward=ff,
                                      speed=CS.vEgo,
                                      freeze_integrator=freeze_integrator)

      pid_log.active = True
      pid_log.p = float(self.pid.p)
      pid_log.i = float(self.pid.i)
      pid_log.d = float(self.pid.d)
      pid_log.f = float(self.pid.f)
      pid_log.output = float(-output_torque)
      pid_log.actualLateralAccel = float(actual_lateral_accel)
      pid_log.desiredLateralAccel = float(desired_lateral_accel)
      pid_log.saturated = bool(self._check_saturation(self.steer_max - abs(output_torque) < 1e-3, CS, steer_limited_by_controls, curvature_limited))

    # TODO left is positive in this convention
    return -output_torque, 0.0, pid_log
