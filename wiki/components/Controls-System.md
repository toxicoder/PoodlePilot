# Controls System in openpilot

The Controls System is a critical part of openpilot, responsible for translating the desired path and speed from the planning modules into actual commands for the vehicle's actuators (steering, throttle, brakes). It operates in real-time, constantly making adjustments to keep the vehicle on the planned trajectory.

## Overview

The primary goals of the Controls System are:

*   **Lateral Control:** Keeping the vehicle centered in its lane by controlling steering.
*   **Longitudinal Control:** Maintaining the set speed or a safe following distance to a lead vehicle by controlling acceleration and braking.
*   **Smoothness and Comfort:** Ensuring that control actions are smooth and comfortable for the occupants.
*   **Safety:** Operating within safe limits and reacting appropriately to changing conditions.

The Controls System receives inputs from various sources, including:

*   **`plannerd` (via `longitudinalPlan` and `lateralPlan` messages):** Provides the target path, speed, and acceleration profiles.
*   **`modeld` (via `modelV2` messages):** Provides information about the current driving environment, including lane lines, path predictions, and lead vehicle data.
*   **`carState` messages:** Provides real-time information from the vehicle, such as current speed, steering angle, and brake/gas pedal status.
*   **`liveParameters` and `liveCalibration` messages:** Provide updated vehicle parameters and calibration data.

The main output of the Controls System is the `carControl` message, which contains the desired steering torque/angle, acceleration/braking commands, and other actuator commands sent to the Panda and then to the car's CAN bus.

## Key Processes and Components

The Controls System comprises several key processes and libraries, primarily located in `selfdrive/controls/`:

*   **[`controlsd`](controlsd.md):** The central process that orchestrates lateral and longitudinal control. It houses the main control loops and interfaces with various control algorithms.
*   **[`plannerd`](wiki/TODO-plannerd.md):** (To be created) While primarily a planning module, it works very closely with `controlsd`, providing the targets that `controlsd` aims to achieve.
*   **[`radard`](wiki/TODO-radard.md):** (To be created) Processes data from the car's radar (if available) to detect and track lead vehicles, providing crucial input for longitudinal control.
*   **Lateral Control Libraries (`latcontrol_*.py`):**
    *   Implement different lateral control strategies (e.g., PID, Torque, Angle-based).
    *   Selected based on car capabilities and tuning.
*   **Longitudinal Control Libraries (`longcontrol.py`, `longitudinal_mpc_lib/`):**
    *   Implement longitudinal control, including PID controllers and Model Predictive Control (MPC) for speed and following distance.
*   **State Machines and Helpers:**
    *   `drive_helpers.py`: Contains utility functions for speed control, curvature calculations, etc.
    *   `desire_helper.py`: Manages user intent for actions like lane changes.

## General Control Flow

1.  **Data Ingestion:** `controlsd` subscribes to relevant `cereal` messages (`modelV2`, `carState`, `longitudinalPlan`, `lateralPlan`, etc.).
2.  **State Estimation:** It uses current vehicle state (`carState`) and model outputs to understand the current driving situation.
3.  **Target Calculation:** Based on the plans from `plannerd` and current state, `controlsd` determines the immediate targets for lateral and longitudinal movement.
4.  **Control Algorithm Execution:**
    *   The appropriate lateral controller (e.g., `LatControlPID`, `LatControlTorque`) calculates the required steering command.
    *   The longitudinal controller (`LongControl`) calculates the required acceleration or braking command.
5.  **Command Generation:** The calculated steering, throttle, and brake values are packaged into a `CarControl` message.
6.  **Output:** The `CarControl` message is published, eventually reaching the car's CAN bus via `pandad` and the Panda hardware.

This loop runs continuously at a high frequency (typically 100Hz, synchronized with `DT_CTRL`) to ensure responsive vehicle control.

---
*Explore the linked pages for more detailed information on specific control processes and algorithms.*
