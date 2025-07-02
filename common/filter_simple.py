class FirstOrderFilter:
  x: float  # Current filtered value
  dt: float # Time step
  alpha: float # Filter coefficient
  initialized: bool # Whether the filter has been initialized with a first value

  def __init__(self, x0: float, rc: float, dt: float, initialized: bool = True):
    self.x = x0
    self.dt = dt
    self.update_alpha(rc)
    self.initialized = initialized

  def update_alpha(self, rc: float) -> None:
    if rc + self.dt == 0: # Avoid division by zero if dt is 0 and rc is 0
        self.alpha = 1.0 # Effectively pass through the new value if time constant is zero
    else:
        self.alpha = self.dt / (rc + self.dt)

  def update(self, x: float) -> float:
    if self.initialized:
      self.x = (1. - self.alpha) * self.x + self.alpha * x
    else:
      self.initialized = True
      self.x = x
    return self.x
