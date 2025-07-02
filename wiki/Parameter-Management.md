# Parameter Management in openpilot

openpilot utilizes a persistent key-value store for managing configuration parameters, calibration data, toggles, and other settings that need to survive reboots. This system is primarily managed by helpers in `common/params.py`.

## Overview

Instead of a traditional database, openpilot parameters are stored as files on the device's filesystem, typically in `/data/params/` (or a similar path depending on the environment). Each parameter is a file, where the filename is the parameter key (name) and the file content is its value.

This approach offers simplicity and robustness for the embedded environment openpilot runs in.

## Core Functionality (`common/params.py`)

The `common/params.py` module provides the primary interface for interacting with parameters. Key classes and methods include:

*   **`Params()` class:** The main class for reading and writing parameters.
    *   `put(key: str, value: bytes)`: Writes a value (as bytes) to the specified parameter key.
    *   `get(key: str, block: bool = False, encoding: Optional[str] = 'utf-8') -> Optional[Union[bytes, str]]`: Reads the value of the specified parameter key.
        *   `block`: If `True`, this call can block until the parameter exists (useful for waiting for parameters set by other processes).
        *   `encoding`: If specified (e.g., 'utf-8'), the byte value is decoded into a string. Otherwise, raw bytes are returned.
    *   `delete(key: str)`: Removes a parameter.
    *   `get_bool(key: str, block: bool = False) -> bool`: A convenience method to read a parameter and interpret its value ("0" or "1") as a boolean.

*   **Parameter Types:**
    *   Parameters are fundamentally stored as byte strings.
    *   Helper methods like `get_bool` or manual type conversions (e.g., `int()`, `float()`) are used in application code to interpret these byte strings as specific data types.
    *   Common convention is to store boolean values as "0" (False) or "1" (True).

*   **Storage Path:**
    *   The base path for parameters is typically `/data/params/d/`.
    *   There's also a path for "non-persistent" parameters (`/data/params/m/`) that might be cleared on certain conditions, though most critical parameters use the persistent path.

*   **Event-Driven Updates:**
    *   The system uses file system events (like `inotify` on Linux) to allow processes to react to parameter changes without constant polling. `Params().get()` with `block=True` leverages this.

## Key Parameter Groups and Examples

Numerous parameters are used throughout openpilot. Here are some illustrative examples of common parameter types and their roles:

*   **Calibration Parameters:**
    *   `CalibrationParams` (Protobuf message often stored as a string): Contains intrinsic and extrinsic camera calibration data. Critical for accurate perception.
    *   `LiveTorqueParameters`: Parameters related to torque control, potentially learned or adjusted live.
    *   `AngleOffset`: Steering angle sensor offset.

*   **Feature Toggles (User Settings):**
    *   `IsMetric`: Boolean, whether to display units in metric (km/h) or imperial (mph).
    *   `RecordFront`: Boolean, whether to record the front-facing driver camera.
    *   `LaneChangeEnabled`: Boolean, to enable or disable automated lane changes.
    *   Many toggles correspond to settings available in the on-device UI.

*   **Vehicle Specific Parameters (`CarParams` related):**
    *   While `CarParams` are largely determined by the car's fingerprint and code, some persistent adjustments or learned values related to a specific vehicle might be stored.
    *   `CompletedTrainingVersion`: Tracks the version of the initial training/setup guide the user has completed.

*   **System & Operational Parameters:**
    *   `DongleId`: The unique identifier for the comma device.
    *   `GitCommit`, `GitBranch`, `GitRemote`: Information about the currently running software version.
    *   `HasAcceptedTerms`: Tracks acceptance of terms and conditions.
    *   `AccessToken`: For accessing comma.ai services.

## Working with Parameters

### Reading a Parameter

```python
# from openpilot.common.params import Params
# params = Params()
#
# # Read a string parameter
# git_branch = params.get("GitBranch")
# if git_branch is not None:
#   print(f"Current branch: {git_branch}")
#
# # Read a boolean parameter
# is_metric = params.get_bool("IsMetric")
# print(f"Using metric units: {is_metric}")
#
# # Read a parameter that might not exist yet, or wait for it
# try:
#   # Non-blocking read, returns None if not found
#   calibration_params_bytes = params.get("CalibrationParams")
#   if calibration_params_bytes:
#     # Process calibration_params_bytes (e.g., parse protobuf)
#     pass
#
#   # Blocking read (waits for parameter to appear if it doesn't exist)
#   # Useful for one-time initialization after another process sets the param.
#   # Use with caution to avoid deadlocks if the param is never set.
#   # dongle_id = params.get("DongleId", block=True)
#
# except Exception as e:
#   print(f"Error reading params: {e}")

```

### Writing a Parameter

```python
# from openpilot.common.params import Params
# params = Params()
#
# # Write a string parameter
# params.put("MyCustomParam", "my_value")
#
# # Write a boolean parameter (conventionally "0" or "1")
# params.put("MyToggleFeature", "1") # Enable
# params.put("MyToggleFeature", "0") # Disable
#
# # Clear a parameter
# # params.delete("MyCustomParam")
```

## Considerations for Developers

*   **Parameter Naming:** Use clear and descriptive names for new parameters.
*   **Default Values:** Ensure your code handles cases where a parameter might not be set and has a sensible default behavior. `Params().get()` returns `None` if a parameter doesn't exist (and `block=False`).
*   **Data Types:** Be consistent with how you store and interpret parameter values (e.g., always store booleans as "0" or "1").
*   **Performance:** While reading/writing parameters is relatively fast, avoid doing it excessively in tight, performance-critical loops. Cache values if a parameter is read frequently and changes rarely.
*   **Atomicity:** File system operations for single parameter reads/writes are generally atomic.
*   **Parameter Discovery:** There isn't a central registry of all possible parameters within the code itself (beyond `common.params_keys.h` which lists many common ones for C++ access). Developers often discover them by examining the codebase or existing parameter files on a device.

---
This system provides a flexible way to manage persistent settings across openpilot. For a list of many common parameters, developers can also refer to `common/params_keys.h` (used for C++ access) and by exploring the `/data/params/d/` directory on a running openpilot system.
