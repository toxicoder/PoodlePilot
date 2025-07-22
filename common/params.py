from typing import Optional, List, Union # Added Union
# ParamKeyType and UnknownKeyName are not used in the script logic itself,
# but asserted. Their specific types from Cython are unknown without stubs.
from openpilot.common.params_pyx import Params as CythonParams, ParamKeyType, UnknownKeyName

# For type checking, we'd ideally have a stub file for openpilot.common.params_pyx.
# For now, we'll use type: ignore for calls to CythonParams methods.
# Assumed signatures:
# class CythonParams:
#     def __init__(self) -> None: ...
#     def check_key(self, key: str) -> bool: ...
#     def put(self, key: str, val: Union[str, bytes]) -> None: ...
#     def get(self, key: str, encoding: Optional[str] = 'utf-8') -> Optional[Union[str, bytes]]: ...
#     # Or more simply:
#     # def get(self, key: str) -> Optional[bytes]: ... (and caller decodes)

assert CythonParams
assert ParamKeyType
assert UnknownKeyName

if __name__ == "__main__":
  import sys

  args: List[str] = sys.argv

  # The script uses Params directly from params_pyx
  params_instance: CythonParams = CythonParams()  # type: ignore[no-untyped-call]

  key: str = args[1]

  # Assuming check_key(key: str) -> bool
  assert params_instance.check_key(key), f"unknown param: {key}"  # type: ignore[no-untyped-call]

  if len(args) == 3:
    val_arg: str = args[2]
    print(f"SET: {key} = {val_arg}")
    # Assuming put(key: str, val: str | bytes) -> None
    # The example uses a string value directly.
    params_instance.put(key, val_arg)  # type: ignore[no-untyped-call]
  elif len(args) == 2:
    # Assuming get(key: str) -> Optional[bytes]
    # This is a common pattern; the caller handles decoding.
    ret_val_bytes: Optional[bytes] = params_instance.get(key)  # type: ignore[no-untyped-call]

    value_to_print: Optional[str] = None
    if ret_val_bytes is not None:
      try:
        value_to_print = ret_val_bytes.decode()
      except UnicodeDecodeError:
        # Fallback for non-UTF-8 decodable bytes, or if they are not meant to be strings
        print(f"Warning: Value for key '{key}' is not valid UTF-8 bytes.", file=sys.stderr)
        value_to_print = f"{ret_val_bytes!r}" # Show repr of bytes

    print(f"GET: {key} = {value_to_print}")
