# Inter-Process Communication (IPC) with `cereal`

`cereal` is openpilot's messaging library, crucial for enabling communication between its many independent processes. It is built on top of [Cap'n Proto](https://capnproto.org/), a fast data interchange format, and uses ZeroMQ (ZMQ) for the underlying message transport.

## Overview

Effective IPC is vital in a complex system like openpilot where different tasks (e.g., reading sensor data, running machine learning models, controlling the vehicle, updating the UI) are handled by separate processes. `cereal` provides a standardized and efficient way for these processes to exchange data.

Key characteristics:

*   **Schema-Defined Messages:** Message structures are defined using Cap'n Proto schema files (`.capnp`). This ensures type safety and well-defined data formats.
*   **Publish-Subscribe Model:** Most communication follows a publish-subscribe pattern. Processes ("publishers") send out messages on named "services" (topics), and other processes ("subscribers") can listen to the services they are interested in.
*   **Efficiency:** Cap'n Proto is designed for high performance, avoiding parsing/copying steps where possible, which is critical for real-time applications.
*   **Language Support:** While `cereal` itself is primarily used with C++ and Python in openpilot, Cap'n Proto supports multiple languages.

## Core Concepts

### 1. Message Definitions (`.capnp` files)

*   Message types and their fields are defined in `.capnp` files located in the `cereal/` directory (e.g., `cereal/log.capnp`, `cereal/car.capnp`).
*   These schema files are compiled by the Cap'n Proto compiler (`capnp compile`) to generate C++ and Python code that can be used to create, send, receive, and access these messages.
*   **Example:** A `CarState` message might define fields like `vEgo` (vehicle speed), `steeringAngleDeg`, `leftBlinker`, etc.

    ```capnp
    # In a .capnp file (simplified example)
    struct CarState {
      vEgo @0 :Float32;
      steeringAngleDeg @1 :Float32;
      leftBlinker @2 :Bool;
      # ... other fields
    }
    ```

### 2. Services

*   Processes publish messages to, and subscribe to messages from, "services." A service is essentially a named channel or topic for a specific type of data.
*   The list of available services and their associated message types and port numbers are defined in `cereal/services.py`.
*   **Example Services:**
    *   `carState`: Publishes `CarState` messages.
    *   `modelV2`: Publishes outputs from the driving model.
    *   `controlsState`: Publishes the current state of the control system.
    *   `liveCalibration`: Publishes calibration data.

### 3. Publishers (`PubMaster`)

*   A process that wants to send messages creates a `PubMaster` instance for the services it will publish to.
*   **Python Example (Simplified):**
    ```python
    # import cereal.messaging as messaging
    # pm = messaging.PubMaster(['carState'])
    #
    # msg = messaging.new_message('carState')
    # msg.carState.vEgo = 10.0
    # msg.carState.steeringAngleDeg = 5.0
    # pm.send('carState', msg)
    ```
*   The `PubMaster` handles the serialization of the message (using Cap'n Proto) and sends it via ZMQ.

### 4. Subscribers (`SubMaster`, `Poller`)

*   Processes that need to receive messages use `SubMaster` to subscribe to specific services.
*   A `Poller` can be used with `SubMaster` to efficiently wait for new messages on multiple services.
*   **Python Example (Simplified):**
    ```python
    # import cereal.messaging as messaging
    # sm = messaging.SubMaster(['modelV2', 'carState'], poll='modelV2')
    #
    # while True:
    #   sm.update()
    #   if sm.updated['modelV2']:
    #     model_output = sm['modelV2']
    #     # Process model_output
    #   if sm.updated['carState']:
    #     car_state = sm['carState']
    #     # Process car_state
    ```
*   `sm.update()` checks for new messages. `sm.updated[service_name]` indicates if a new message arrived on that service, and `sm[service_name]` provides access to the deserialized message content.
*   The `poll` argument in `SubMaster` specifies a service that dictates the update frequency; `sm.update()` will block until a message arrives on the polled service (or a timeout occurs if configured).

### 5. Logging and Replay

*   A significant advantage of this architecture is that all IPC messages can be easily logged. The `loggerd` process subscribes to many services and writes the messages to log files.
*   These logs can then be used for:
    *   Debugging issues.
    *   Replaying scenarios (`tools/replay/`).
    *   Training machine learning models.

## Location in Codebase

*   **`cereal/`**: Contains message definitions (`.capnp` files), service definitions (`services.py`), and the core C++/Python messaging library code (`messaging.cc`, `messaging.py`).
*   **`selfdrive/` and `system/`**: Most processes in these directories use `cereal.messaging` to communicate.

## Key Considerations for Developers

*   **Message Evolution:** When modifying `.capnp` files (e.g., adding or changing fields), be mindful of backward and forward compatibility, especially for logged data and communication between components that might be version-skewed. Cap'n Proto has mechanisms to help manage this.
*   **Frequency and Latency:** Understand the publication frequency of services you subscribe to and the potential latency involved in message passing.
*   **Blocking vs. Non-Blocking:** Be aware of how `SubMaster` and `Poller` are used, especially regarding blocking calls (`sm.update()` can block).
*   **Data Integrity:** While Cap'n Proto provides schema enforcement, the logical correctness of data is the responsibility of the publishing process.

---
This page provides a foundational understanding of `cereal`. For specific message field details, refer directly to the `.capnp` schema files in the `cereal/` directory and the `services.py` file. More detailed examples of publisher/subscriber patterns can be found throughout the openpilot codebase.
