"""Utilities for reading real time clocks and keeping soft real time constraints."""
import gc
import os
import sys
import time
from typing import List, Union, Optional # Python 3.10+ allows list, int | X, but explicit for clarity/compatibility

from setproctitle import getproctitle

from openpilot.common.util import MovingAverage # Assuming MovingAverage methods are typed or need stubs
from openpilot.system.hardware import PC


# time step for each process
DT_CTRL: float = 0.01  # controlsd
DT_MDL: float = 0.05  # model
DT_HW: float = 0.5  # hardwared and manager
DT_DMON: float = 0.05  # driver monitoring


class Priority:
  # CORE 2
  # - modeld = 55
  # - camerad = 54
  CTRL_LOW: int = 51 # plannerd & radard

  # CORE 3
  # - pandad = 55
  CTRL_HIGH: int = 53


def set_core_affinity(cores: List[int]) -> None:
  if sys.platform == 'linux' and not PC:
    # os.sched_setaffinity is Linux-specific
    os.sched_setaffinity(0, cores) # type: ignore[attr-defined]


def config_realtime_process(cores: Union[int, List[int]], priority: int) -> None:
  gc.disable()
  if sys.platform == 'linux' and not PC:
    # os.sched_setscheduler and os.SCHED_FIFO are Linux-specific
    # os.sched_param is also Linux-specific
    sched_param = os.sched_param(priority) # type: ignore[attr-defined]
    os.sched_setscheduler(0, os.SCHED_FIFO, sched_param) # type: ignore[attr-defined, usado-before-def]

  c: List[int] = cores if isinstance(cores, list) else [cores]
  set_core_affinity(c)


class Ratekeeper:
  _interval: float
  _print_delay_threshold: Optional[float]
  _frame: int
  _remaining: float
  _process_name: str
  _last_monitor_time: float
  _next_frame_time: float
  avg_dt: MovingAverage # Type of MovingAverage itself. Instance attributes are typed via __init__

  def __init__(self, rate: float, print_delay_threshold: Optional[float] = 0.0) -> None:
    """Rate in Hz for ratekeeping. print_delay_threshold must be nonnegative."""
    self._interval = 1. / rate
    self._print_delay_threshold = print_delay_threshold
    self._frame = 0
    self._remaining = 0.0
    self._process_name = getproctitle()
    self._last_monitor_time = -1.0  # Ensure float
    self._next_frame_time = -1.0    # Ensure float

    # Assuming MovingAverage takes an int and its methods handle floats.
    # If MovingAverage is generic, like MovingAverage[float], that would be more precise.
    self.avg_dt = MovingAverage(100) # type: ignore[no-untyped-call]
    self.avg_dt.add_value(self._interval) # type: ignore[no-untyped-call]

  @property
  def frame(self) -> int:
    return self._frame

  @property
  def remaining(self) -> float:
    return self._remaining

  @property
  def lagging(self) -> bool:
    expected_dt: float = self._interval * (1 / 0.9)
    # Assuming get_average returns float
    return self.avg_dt.get_average() > expected_dt # type: ignore[no-untyped-call]

  # Maintain loop rate by calling this at the end of each loop
  def keep_time(self) -> bool:
    lagged: bool = self.monitor_time()
    if self._remaining > 0:
      time.sleep(self._remaining)
    return lagged

  # Monitors the cumulative lag, but does not enforce a rate
  def monitor_time(self) -> bool:
    if self._last_monitor_time < 0: # first frame
      self._next_frame_time = time.monotonic() + self._interval
      self._last_monitor_time = time.monotonic()

    prev: float = self._last_monitor_time
    self._last_monitor_time = time.monotonic()
    self.avg_dt.add_value(self._last_monitor_time - prev) # type: ignore[no-untyped-call]

    lagged: bool = False
    current_time: float = time.monotonic()
    remaining: float = self._next_frame_time - current_time
    self._next_frame_time += self._interval

    if self._print_delay_threshold is not None and remaining < -self._print_delay_threshold:
      # print_delay_threshold is explicitly checked for None, so remaining can be compared
      print(f"{self._process_name} lagging by {-remaining * 1000:.2f} ms")
      lagged = True

    self._frame += 1
    self._remaining = remaining
    return lagged
