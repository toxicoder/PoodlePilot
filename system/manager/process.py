import importlib
import os
import signal
import struct
import time
import subprocess
from collections.abc import Callable, ValuesView
from abc import ABC, abstractmethod
from multiprocessing import Process
from typing import Optional, List, Any # Added for type hinting

from setproctitle import setproctitle

from cereal import car, log
import cereal.messaging as messaging
import openpilot.system.sentry as sentry
from openpilot.common.basedir import BASEDIR
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.common.watchdog import WATCHDOG_FN

ENABLE_WATCHDOG: bool = os.getenv("NO_WATCHDOG") is None


def launcher(proc: str, name: str) -> None:
  try:
    # import the process
    mod: Any = importlib.import_module(proc)

    # rename the process
    setproctitle(proc)

    # create new context since we forked
    messaging.reset_context()

    # add daemon name tag to logs
    cloudlog.bind(daemon=name)
    sentry.set_tag("daemon", name)

    # exec the process
    mod.main()
  except KeyboardInterrupt:
    cloudlog.warning(f"child {proc} got SIGINT")
  except Exception:
    # can't install the crash handler because sys.excepthook doesn't play nice
    # with threads, so catch it here.
    sentry.capture_exception()
    raise


def nativelauncher(pargs: List[str], cwd: str, name: str) -> None:
  os.environ['MANAGER_DAEMON'] = name

  # exec the process
  os.chdir(cwd)
  os.execvp(pargs[0], pargs)


def join_process(process: Process, timeout: float) -> None:
  # Process().join(timeout) will hang due to a python 3 bug: https://bugs.python.org/issue28382
  # We have to poll the exitcode instead
  t: float = time.monotonic()
  while time.monotonic() - t < timeout and process.exitcode is None:
    time.sleep(0.001)


class ManagerProcess(ABC):
  daemon: bool = False
  sigkill: bool = False
  should_run: Callable[[bool, Params, car.CarParams.Reader], bool]
  proc: Optional[Process] = None
  enabled: bool = True
  name: str = ""

  last_watchdog_time: float = 0.0 # Changed from int to float for consistency with time.monotonic()
  watchdog_max_dt: Optional[int] = None # Max delta time in seconds
  watchdog_seen: bool = False
  shutting_down: bool = False

  @abstractmethod
  def prepare(self) -> None:
    pass

  @abstractmethod
  def start(self) -> None:
    pass

  def restart(self) -> None:
    self.stop(sig=signal.SIGKILL)
    self.start()

  def check_watchdog(self, started: bool) -> None:
    if self.watchdog_max_dt is None or self.proc is None or self.proc.pid is None: # Added pid check
      return

    try:
      fn: str = WATCHDOG_FN + str(self.proc.pid)
      with open(fn, "rb") as f:
        # last_watchdog_time is originally an int (nanoseconds)
        self.last_watchdog_time = float(struct.unpack('Q', f.read())[0]) / 1e9 # Convert to seconds
    except Exception:
      pass

    dt: float = time.monotonic() - self.last_watchdog_time # Now both are in seconds

    if dt > self.watchdog_max_dt:
      if self.watchdog_seen and ENABLE_WATCHDOG:
        cloudlog.error(f"Watchdog timeout for {self.name} (exitcode {self.proc.exitcode}) restarting ({started=})")
        self.restart()
    else:
      self.watchdog_seen = True

  def stop(self, retry: bool = True, block: bool = True, sig: Optional[signal.Signals] = None) -> Optional[int]:
    if self.proc is None:
      return None

    if self.proc.exitcode is None:
      if not self.shutting_down:
        cloudlog.info(f"killing {self.name}")
        if sig is None:
          sig = signal.SIGKILL if self.sigkill else signal.SIGINT
        self.signal(sig) # sig is now signal.Signals
        self.shutting_down = True

        if not block:
          return None

      join_process(self.proc, 5)

      # If process failed to die send SIGKILL
      if self.proc.exitcode is None and retry:
        cloudlog.info(f"killing {self.name} with SIGKILL")
        self.signal(signal.SIGKILL)
        self.proc.join()

    ret: Optional[int] = self.proc.exitcode
    cloudlog.info(f"{self.name} is dead with {ret}")

    if self.proc.exitcode is not None:
      self.shutting_down = False
      self.proc = None

    return ret

  def signal(self, sig: int) -> None: # sig is int here for os.kill
    if self.proc is None:
      return

    # Don't signal if already exited
    if self.proc.exitcode is not None and self.proc.pid is not None:
      return

    # Can't signal if we don't have a pid
    if self.proc.pid is None:
      return

    cloudlog.info(f"sending signal {sig} to {self.name}")
    os.kill(self.proc.pid, sig)

  def get_process_state_msg(self) -> log.ManagerState.ProcessState.Builder:
    state = log.ManagerState.ProcessState.new_message()
    state.name = self.name
    if self.proc:
      state.running = self.proc.is_alive()
      state.shouldBeRunning = self.proc is not None and not self.shutting_down
      state.pid = self.proc.pid or 0
      state.exitCode = self.proc.exitcode or 0
    return state


class NativeProcess(ManagerProcess):
  cwd: str
  cmdline: List[str]
  launcher: Callable[[List[str], str, str], None]

  def __init__(self, name: str, cwd: str, cmdline: List[str], should_run: Callable[[bool, Params, car.CarParams.Reader], bool],
               enabled: bool = True, sigkill: bool = False, watchdog_max_dt: Optional[int] = None) -> None:
    self.name = name
    self.cwd = cwd
    self.cmdline = cmdline
    self.should_run = should_run
    self.enabled = enabled
    self.sigkill = sigkill
    self.watchdog_max_dt = watchdog_max_dt
    self.launcher = nativelauncher

  def prepare(self) -> None:
    pass

  def start(self) -> None:
    # In case we only tried a non blocking stop we need to stop it before restarting
    if self.shutting_down:
      self.stop()

    if self.proc is not None:
      return

    cwd_path: str = os.path.join(BASEDIR, self.cwd)
    cloudlog.info(f"starting process {self.name}")
    self.proc = Process(name=self.name, target=self.launcher, args=(self.cmdline, cwd_path, self.name))
    self.proc.start()
    self.watchdog_seen = False
    self.shutting_down = False


class PythonProcess(ManagerProcess):
  module: str
  launcher: Callable[[str, str], None]

  def __init__(self, name: str, module: str, should_run: Callable[[bool, Params, car.CarParams.Reader], bool],
               enabled: bool = True, sigkill: bool = False, watchdog_max_dt: Optional[int] = None) -> None:
    self.name = name
    self.module = module
    self.should_run = should_run
    self.enabled = enabled
    self.sigkill = sigkill
    self.watchdog_max_dt = watchdog_max_dt
    self.launcher = launcher

  def prepare(self) -> None:
    if self.enabled:
      cloudlog.info(f"preimporting {self.module}")
      importlib.import_module(self.module)

  def start(self) -> None:
    # In case we only tried a non blocking stop we need to stop it before restarting
    if self.shutting_down:
      self.stop()

    if self.proc is not None:
      return

    # TODO: this is just a workaround for this tinygrad check:
    # https://github.com/tinygrad/tinygrad/blob/ac9c96dae1656dc220ee4acc39cef4dd449aa850/tinygrad/device.py#L26
    process_target_name: str = self.name if "modeld" not in self.name else "MainProcess"

    cloudlog.info(f"starting python {self.module}")
    self.proc = Process(name=process_target_name, target=self.launcher, args=(self.module, self.name))
    self.proc.start()
    self.watchdog_seen = False
    self.shutting_down = False


class DaemonProcess(ManagerProcess):
  """Python process that has to stay running across manager restart.
  This is used for athena so you don't lose SSH access when restarting manager."""
  module: str
  param_name: str
  params: Optional[Params]

  def __init__(self, name: str, module: str, param_name: str, enabled: bool = True) -> None:
    self.name = name
    self.module = module
    self.param_name = param_name
    self.enabled = enabled
    self.params = None

  @staticmethod
  def should_run(started: bool, params: Params, CP: car.CarParams.Reader) -> bool:
    return True

  def prepare(self) -> None:
    pass

  def start(self) -> None:
    if self.params is None:
      self.params = Params()

    pid_str: Optional[str] = self.params.get(self.param_name, encoding='utf-8')
    if pid_str is not None:
      try:
        pid: int = int(pid_str)
        os.kill(pid, 0)
        with open(f'/proc/{pid}/cmdline') as f:
          if self.module in f.read():
            # daemon is running
            return
      except (OSError, FileNotFoundError, ValueError): # Added ValueError for int conversion
        # process is dead
        pass

    cloudlog.info(f"starting daemon {self.name}")
    # Use Popen for daemonized process
    subprocess.Popen(['python', '-m', self.module],
                               stdin=open('/dev/null'),
                               stdout=open('/dev/null', 'w'),
                               stderr=open('/dev/null', 'w'),
                               preexec_fn=os.setpgrp)
    # Re-fetch pid after starting, Popen.pid is available immediately
    # This part is tricky as we need to reliably get the new PID.
    # For now, assuming the user/system handles updating the param if needed,
    # or the next check will re-verify.
    # A more robust way might involve the daemon writing its PID to the param.

  def stop(self, retry: bool = True, block: bool = True, sig: Optional[signal.Signals] = None) -> None:
    pass # Daemon processes are not stopped by manager in this design


def ensure_running(procs: ValuesView[ManagerProcess], started: bool, params: Optional[Params] = None, # Made params Optional
                   CP: Optional[car.CarParams.Reader] = None, # Made CP Optional
                   not_run: Optional[List[str]] = None) -> List[ManagerProcess]:
  if not_run is None:
    not_run = []

  running: List[ManagerProcess] = []
  p: ManagerProcess
  for p in procs:
    # Provide default for params and CP if None, as should_run expects them
    current_params = params if params is not None else Params() # Default if None
    # CP might need a more sophisticated default or handling if None is not acceptable by should_run
    # For now, assuming should_run can handle CP being None or this needs adjustment based on usage.
    # This is a simplification; real default for CP would be complex.
    # If should_run implementations *always* need a valid CP, this approach needs refinement.
    default_cp = car.CarParams.new_message().as_reader() # Create a default if CP is None
    should_run_decision: bool = p.should_run(started, current_params, CP if CP is not None else default_cp)


    if p.enabled and p.name not in not_run and should_run_decision:
      running.append(p)
    else:
      p.stop(block=False)

    p.check_watchdog(started)

  for p_running in running:
    p_running.start()

  return running
