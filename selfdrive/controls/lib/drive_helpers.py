import numpy as np
from cereal import log
from opendbc.car.vehicle_model import ACCELERATION_DUE_TO_GRAVITY
from openpilot.common.realtime import DT_CTRL, DT_MDL
from typing import Tuple, List # Added for type hinting

MIN_SPEED: float = 1.0
CONTROL_N: int = 17
CAR_ROTATION_RADIUS: float = 0.0
# This is a turn radius smaller than most cars can achieve
MAX_CURVATURE: float = 0.2
MAX_VEL_ERR: float = 5.0  # m/s

# EU guidelines
MAX_LATERAL_JERK: float = 5.0  # m/s^3
MAX_LATERAL_ACCEL_NO_ROLL: float = 3.0  # m/s^2


def clamp(val: float, min_val: float, max_val: float) -> Tuple[float, bool]:
  clamped_val: float = float(np.clip(val, min_val, max_val))
  return clamped_val, clamped_val != val

def smooth_value(val: float, prev_val: float, tau: float, dt: float = DT_MDL) -> float:
  alpha: float = 1 - np.exp(-dt/tau) if tau > 0 else 1.0
  return float(alpha * val + (1 - alpha) * prev_val)

def clip_curvature(v_ego: float, prev_curvature: float, new_curvature: float, roll: float) -> Tuple[float, bool]:
  # This function respects ISO lateral jerk and acceleration limits + a max curvature
  v_ego = max(v_ego, MIN_SPEED)
  max_curvature_rate: float = MAX_LATERAL_JERK / (v_ego ** 2)  # inexact calculation, check https://github.com/commaai/openpilot/pull/24755
  new_curvature_clipped_rate: float = np.clip(new_curvature,
                                               prev_curvature - max_curvature_rate * DT_CTRL,
                                               prev_curvature + max_curvature_rate * DT_CTRL)

  roll_compensation: float = roll * ACCELERATION_DUE_TO_GRAVITY
  max_lat_accel: float = MAX_LATERAL_ACCEL_NO_ROLL + roll_compensation
  min_lat_accel: float = -MAX_LATERAL_ACCEL_NO_ROLL + roll_compensation

  new_curvature_clipped_accel: float
  limited_accel: bool
  new_curvature_clipped_accel, limited_accel = clamp(new_curvature_clipped_rate, min_lat_accel / v_ego ** 2, max_lat_accel / v_ego ** 2)

  new_curvature_final: float
  limited_max_curv: bool
  new_curvature_final, limited_max_curv = clamp(new_curvature_clipped_accel, -MAX_CURVATURE, MAX_CURVATURE)
  return float(new_curvature_final), limited_accel or limited_max_curv


def get_speed_error(modelV2: log.ModelDataV2.Reader, v_ego: float) -> float:
  # ToDo: Try relative error, and absolute speed
  if len(modelV2.temporalPose.trans):
    vel_err: float = np.clip(modelV2.temporalPose.trans[0] - v_ego, -MAX_VEL_ERR, MAX_VEL_ERR)
    return float(vel_err)
  return 0.0


def get_accel_from_plan(speeds: np.ndarray, accels: np.ndarray, t_idxs: np.ndarray, action_t: float = DT_MDL, vEgoStopping: float = 0.05) -> Tuple[float, bool]:
  v_target: float
  v_target_1sec: float
  a_target: float
  if len(speeds) == len(t_idxs):
    v_now: float = speeds[0]
    a_now: float = accels[0]
    v_target = float(np.interp(action_t, t_idxs, speeds))
    a_target = 2 * (v_target - v_now) / (action_t) - a_now
    v_target_1sec = float(np.interp(action_t + 1.0, t_idxs, speeds))
  else:
    v_target = 0.0
    v_target_1sec = 0.0
    a_target = 0.0
  should_stop: bool = (v_target < vEgoStopping and
                       v_target_1sec < vEgoStopping)
  return a_target, should_stop

def curv_from_psis(psi_target: float, psi_rate: float, vego: float, action_t: float) -> float:
  vego = np.clip(vego, MIN_SPEED, np.inf)
  curv_from_psi: float = psi_target / (vego * action_t)
  return 2*curv_from_psi - psi_rate / vego

def get_curvature_from_plan(yaws: np.ndarray, yaw_rates: np.ndarray, t_idxs: np.ndarray, vego: float, action_t: float) -> float:
  psi_target: float = float(np.interp(action_t, t_idxs, yaws))
  psi_rate: float = yaw_rates[0]
  return curv_from_psis(psi_target, psi_rate, vego, action_t)
