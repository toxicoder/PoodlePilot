import numpy as np

class Conversions:
  # Speed
  MPH_TO_KPH: float = 1.609344
  KPH_TO_MPH: float = 1. / MPH_TO_KPH
  MS_TO_KPH: float = 3.6
  KPH_TO_MS: float = 1. / MS_TO_KPH
  MS_TO_MPH: float = MS_TO_KPH * KPH_TO_MPH
  MPH_TO_MS: float = MPH_TO_KPH * KPH_TO_MS
  MS_TO_KNOTS: float = 1.9438
  KNOTS_TO_MS: float = 1. / MS_TO_KNOTS

  # Angle
  DEG_TO_RAD: float = np.pi / 180.
  RAD_TO_DEG: float = 1. / DEG_TO_RAD

  # Mass
  LB_TO_KG: float = 0.453592
