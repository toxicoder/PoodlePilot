# `controlsd`: The Core Controls Process

`controlsd` is the heart of openpilot's vehicle control system. It is a critical process responsible for orchestrating both lateral (steering) and longitudinal (acceleration/braking) control of the vehicle. It runs at a high frequency (typically 100Hz) to ensure responsive and accurate vehicle maneuvering.

**Location:** `selfdrive/controls/controlsd.py`

## Purpose and Responsibilities

The primary responsibilities of `controlsd` include:

1.  **Data Aggregation:** Subscribing to and processing data from numerous `cereal` services, including:
    *   `modelV2`: For path predictions, lane lines, lead vehicle information from the perception models.
    *   `carState`: For real-time vehicle status (speed, steering angle, button presses, etc.).
    *   `carParams`: For vehicle-specific parameters needed for control tuning.
    *   `longitudinalPlan`: For desired speed and acceleration profiles from `plannerd`.
    *   `lateralPlan`: For desired path/curvature information from `plannerd`.
    *   `liveParameters`: For real-time adjustments to control parameters (e.g., steering ratio from `torqued`).
    *   `liveCalibration`: For camera calibration data.
    *   `radarState`: For lead vehicle information from `radard`.
    *   `controlsState`: For its own previous state and for enabling/disabling control.
    *   `selfdriveState`: For overall system engagement state and personality settings.

2.  **State Management:**
    *   Maintaining the current state of the control system (e.g., active, soft-disabling).
    *   Managing transitions between different control states.
    *   Tracking driver interaction (e.g., steering override, brake/gas pedal press) to determine control authority.

3.  **Lateral Control:**
    *   Instantiating and updating the appropriate lateral control algorithm (e.g., PID, LQR, Torque) based on `CarParams`.
    *   Providing the lateral controller with necessary inputs like desired curvature, current steering angle, and vehicle speed.
    *   Calculating the final steering command (torque or angle).

4.  **Longitudinal Control:**
    *   Instantiating and updating the longitudinal control algorithm (`LongControl`).
    *   Providing the longitudinal controller with target acceleration, current speed, and information about whether the car should be stopping.
    *   Calculating the final acceleration/braking command.

5.  **Actuator Command Generation:**
    *   Combining the outputs from the lateral and longitudinal controllers.
    *   Applying safety limits and checks.
    *   Populating the `CarControl` (`CC`) message with the final actuator commands (e.g., `actuators.accel`, `actuators.steeringAngleDeg` or `actuators.steerTorque`, `hudControl.leadVisible`).

6.  **Interface with Planners:**
    *   Utilizing the `longitudinalPlan` and `lateralPlan` to guide the vehicle.
    *   Adjusting behavior based on these plans (e.g., slowing down for turns indicated in the plan).

7.  **Alert Management:**
    *   Generating alerts for the UI based on control status, driver interaction, or system limitations (e.g., "Steer Override," "Gas Pressed").

8.  **Publishing Output:**
    *   Publishing the `CarControl` message, which is consumed by `pandad` to be sent to the vehicle's CAN bus.
    *   Publishing the `controlsState` message, which includes internal states of the controllers, status information, and alerts.

## Key Internal Components and Logic

While `controlsd.py` is the main orchestrator, it utilizes several helper classes and libraries:

*   **`LatControl` (and its variants like `LatControlPID`, `LatControlTorque`, `LatControlAngle`):** Found in `selfdrive/controls/lib/latcontrol*.py`. These classes implement the specific algorithms for steering control. `controlsd` selects and updates the appropriate one.
*   **`LongControl`:** Found in `selfdrive/controls/lib/longcontrol.py`. This class handles the acceleration and braking logic, typically using a PID controller.
*   **`Events`:** Manages the generation and status of alerts.
*   **`AlertManager`:** Part of `selfdrive/selfdrived/alertmanager.py` but events are created in `controlsd` to be passed to it.
*   **`CarParams` (CP):** Provides vehicle-specific tuning values that are critical for the performance of the lateral and longitudinal controllers.
*   **State Variables:** `controlsd` maintains numerous state variables to track things like whether openpilot is active, if the driver is overriding, saturation of controllers, etc.

## Simplified Control Loop within `controlsd.update()`

The core logic resides in the `Controls.update()` method, which is called iteratively. A simplified flow is:

1.  **Update Timers and States:** Increment timers, check for fresh data from SubMaster sockets.
2.  **Fetch Inputs:** Get the latest messages from `modelV2`, `carState`, `longitudinalPlan`, etc.
3.  **Handle Resets/Initialization:** If controls are just starting or re-engaging, reset internal states of controllers.
4.  **Driver Interaction:** Check for steering overrides, gas/brake pedal presses, and blinker status. Update `Events` accordingly.
5.  **Lateral Control Update:**
    *   If lateral control is active and appropriate, call the `latcontrol.update()` method with current data and desired path information. This returns the calculated steering command.
6.  **Longitudinal Control Update:**
    *   If longitudinal control is active, call `longcontrol.update()` with current data and target acceleration from the `longitudinalPlan`. This returns the calculated acceleration command.
7.  **Populate `CarControl` (CC) message:**
    *   Fill `CC.actuators` with the computed steer, gas, and brake values.
    *   Set HUD visuals (`CC.hudControl`).
    *   Set cruise button commands if needed (`CC.cruiseControl`).
8.  **Publish `CarControl` and `ControlsState` messages.**

---
`controlsd` is a central and complex part of openpilot. Understanding its interactions with other processes and its internal logic is key to understanding how openpilot drives a car. Developers working on control algorithms or vehicle integration will spend significant time with this module.
