import os
import fcntl
import ctypes
from functools import cache
from typing import List, Optional, Union # bool | None is Python 3.10+

# For ctypes Structures, type hints on fields are for documentation / mypy understanding
# The actual C types are defined by ctypes.c_*
# Python attributes of these structures will have corresponding Python types.

def gpio_init(pin: int, output: bool) -> None:
  try:
    with open(f"/sys/class/gpio/gpio{pin}/direction", 'wb') as f:
      f.write(b"out" if output else b"in")
  except Exception as e:
    # Consider logging instead of printing, or raising a specific exception type
    print(f"Failed to set gpio {pin} direction: {e}")

def gpio_set(pin: int, high: bool) -> None:
  try:
    with open(f"/sys/class/gpio/gpio{pin}/value", 'wb') as f:
      f.write(b"1" if high else b"0")
  except Exception as e:
    print(f"Failed to set gpio {pin} value: {e}")

def gpio_read(pin: int) -> Optional[bool]: # Equivalent to bool | None
  val: Optional[bool] = None
  try:
    with open(f"/sys/class/gpio/gpio{pin}/value", 'rb') as f:
      val = bool(int(f.read().strip()))
  except Exception as e:
    # Consider specific exceptions like FileNotFoundError, ValueError
    print(f"Failed to read gpio {pin} value: {e}")
  return val

def gpio_export(pin: int) -> None:
  if os.path.isdir(f"/sys/class/gpio/gpio{pin}"):
    return

  try:
    with open("/sys/class/gpio/export", 'w') as f:
      f.write(str(pin))
  except Exception as e: # Catching generic Exception might hide specific issues
    print(f"Failed to export gpio {pin}: {e}")

@cache
def get_irq_action(irq: int) -> List[str]:
  try:
    with open(f"/sys/kernel/irq/{irq}/actions") as f:
      actions: List[str] = f.read().strip().split(',')
      return actions
  except FileNotFoundError:
    return []

def get_irqs_for_action(action: str) -> List[str]:
  ret: List[str] = []
  try:
    with open("/proc/interrupts") as f:
      for line in f.readlines():
        parts: List[str] = line.split(':')
        irq_num_str: str = parts[0].strip()
        if irq_num_str.isdigit():
          # Convert irq_num_str to int for get_irq_action
          if action in get_irq_action(int(irq_num_str)):
            ret.append(irq_num_str)
  except FileNotFoundError:
    # Handle the case where /proc/interrupts might not exist (though unlikely on target systems)
    print("Warning: /proc/interrupts not found.")
  return ret

# *** gpiochip ***

class gpioevent_data(ctypes.Structure):
  _fields_: List[tuple[str, type]] = [ # type: ignore # ctypes _fields_ type
    ("timestamp", ctypes.c_uint64),
    ("id", ctypes.c_uint32),
  ]
  timestamp: int # Python representation
  id: int        # Python representation

class gpioevent_request(ctypes.Structure):
  _fields_: List[tuple[str, type]] = [ # type: ignore # ctypes _fields_ type
    ("lineoffset", ctypes.c_uint32),
    ("handleflags", ctypes.c_uint32),
    ("eventflags", ctypes.c_uint32),
    ("label", ctypes.c_char * 32), # This will be bytes on Python side
    ("fd", ctypes.c_int)
  ]
  lineoffset: int
  handleflags: int
  eventflags: int
  label: bytes # When accessed from Python, c_char* is bytes
  fd: int


GPIOEVENT_REQUEST_BOTH_EDGES: int = 0x3
GPIOHANDLE_REQUEST_INPUT: int = 0x1
# This IOCTL number can be platform-dependent, ensure it's correct for target.
# For typing, it's an int.
GPIO_GET_LINEEVENT_IOCTL: int = 0xc030b404 # Value specific to architecture/kernel

def gpiochip_get_ro_value_fd(label: str, gpiochip_id: int, pin: int) -> int:
  rq = gpioevent_request()
  rq.lineoffset = pin
  rq.handleflags = GPIOHANDLE_REQUEST_INPUT
  rq.eventflags = GPIOEVENT_REQUEST_BOTH_EDGES

  # Ensure label is correctly formatted bytes, null-terminated, and fits
  encoded_label: bytes = label.encode('utf-8')
  # Max length for label is 31 actual characters + null terminator
  if len(encoded_label) > 31:
    encoded_label = encoded_label[:31]
  rq.label = encoded_label # ctypes handles null termination if space allows, or manual needed

  fd_dev: int = -1
  return_fd: int = -1
  try:
    # os.O_RDONLY | os.O_CLOEXEC is often a good idea for file descriptors
    fd_dev = os.open(f"/dev/gpiochip{gpiochip_id}", os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0))
    # fcntl.ioctl third argument can be a mutable buffer (like rq) or an int/bytes for some ioctls.
    # Here, it's a mutable buffer (ctypes.Structure).
    fcntl.ioctl(fd_dev, GPIO_GET_LINEEVENT_IOCTL, rq) # type: ignore[call-overload]
    return_fd = int(rq.fd) # rq.fd is populated by the ioctl
  except Exception as e:
    print(f"Failed in gpiochip_get_ro_value_fd for {label} ({gpiochip_id}:{pin}): {e}")
    # Ensure a defined error path, perhaps raise or return -1
    if return_fd != -1: # If fd was populated before another error
        try:
            os.close(return_fd)
        except OSError:
            pass
    raise # Re-raise the caught exception to signal failure
  finally:
    if fd_dev != -1:
      os.close(fd_dev)

  # This path should ideally not be reached if an exception occurs and is re-raised.
  # If an error occurs before rq.fd is set, it could be problematic.
  # The current structure returns int(rq.fd) which might be uninitialized if ioctl fails early.
  # The fix is to ensure return_fd is used and exceptions are handled robustly.
  # However, original code did os.close(fd) then return int(rq.fd). fd here was fd_dev.
  # The rq.fd is the one to be returned. The original fd (fd_dev) should be closed.

  # Corrected logic based on original structure:
  # fd_dev = os.open(...)
  # fcntl.ioctl(fd_dev, ..., rq)
  # os.close(fd_dev) # This was the original fd being closed
  # return int(rq.fd) # This is the new fd from the ioctl

  # The fd returned by the ioctl (rq.fd) is the one the caller should use and close.
  # The fd_dev for /dev/gpiochipX is only used for the ioctl call itself.
  return return_fd
