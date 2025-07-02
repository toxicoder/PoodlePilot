import numpy as np
from abc import abstractmethod, ABC
from typing import Any, Tuple

from openpilot.common.realtime import DT_CTRL
from cereal import car, log
from opendbc.car.vehicle_model import VehicleModel


class LatControl(ABC):
  sat_count_rate: float
  sat_limit: float
  sat_count: float
  sat_check_min_speed: float
  steer_max: float

  def __init__(self, CP: car.CarParams.Reader, CI: Any) -> None: # CI type is CarInterfaceBase, but causes circular import
    self.sat_count_rate = 1.0 * DT_CTRL
    self.sat_limit = CP.steerLimitTimer
    self.sat_count = 0.
    self.sat_check_min_speed = 10.

    # we define the steer torque scale as [-1.0...1.0]
    self.steer_max = 1.0

  @abstractmethod
  def update(self, active: bool, CS: car.CarState.Reader, VM: VehicleModel, params: log.LiveParametersData.Reader,
             steer_limited_by_controls: bool, desired_curvature: float, calibrated_pose: Any, # calibrated_pose is locationd.helpers.Pose
             curvature_limited: bool) -> Tuple[float, float, Any]: # Any is LatControlState variant
    pass

  def reset(self) -> None:
    self.sat_count = 0.

  def _check_saturation(self, saturated: bool, CS: car.CarState.Reader, steer_limited_by_controls: bool, curvature_limited: bool) -> bool:
    # Saturated only if control output is not being limited by car torque/angle rate limits
    if (saturated or curvature_limited) and CS.vEgo > self.sat_check_min_speed and not steer_limited_by_controls and not CS.steeringPressed:
      self.sat_count += self.sat_count_rate
    else:
      self.sat_count -= self.sat_count_rate
    self.sat_count = np.clip(self.sat_count, 0.0, self.sat_limit)
    return self.sat_count > (self.sat_limit - 1e-3)
