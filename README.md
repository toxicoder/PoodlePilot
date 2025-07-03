# PoodlePilot

![Poodle Pilot Logo](https://via.placeholder.com/300x100.jpg?text=Poodle+Pilot+Logo+V1)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
<!-- Add other relevant badges here if available, e.g., for specific sub-components or documentation status -->
<!-- Note: Badges for tests, codecov, and version currently point to the original openpilot repository. These should be updated if PoodlePilot establishes its own CI and release cycle. -->

**PoodlePilot is an open source driver assistance system, forked from [comma.ai's openpilot](https://github.com/commaai/openpilot).** PoodlePilot enhances compatible vehicles with features like Automated Lane Centering (ALC) and Adaptive Cruise Control (ACC). Originally developed by [comma.ai](https://comma.ai/) and the community, PoodlePilot aims to provide a safe and reliable driving experience.

This document provides information for developers and contributors looking to understand, build, and extend PoodlePilot. For user-facing documentation, please visit [docs.comma.ai](https://docs.comma.ai) (official OpenPilot documentation).

## Table of Contents

- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Development Environment Setup](#development-environment-setup)
- [Running the Application](#running-the-application)
  - [On a comma device](#on-a-comma-device)
  - [In Simulation](#in-simulation)
- [Running Tests](#running-tests)
- [Building PoodlePilot](#building-poodlepilot)
- [Deployment](#deployment)
- [High-Level Architecture](#high-level-architecture)
- [Contributing](#contributing)
- [License](#license)

## Getting Started

This section guides you through setting up your development environment for PoodlePilot.

### Prerequisites

Before you begin, ensure you have the following:

*   **Supported Operating System:**
    *   Ubuntu 20.04 or later (22.04/24.04 LTS recommended).
    *   macOS.
*   **Git:** For version control (LFS is also used).
*   **Python:** Version >=3.11, <3.13 (defined in `pyproject.toml`).
*   **C++ Compiler:** A modern C++ compiler (e.g., Clang, GCC). Clang is specified in `SConstruct`.
*   **SCons:** The build system used by openpilot.
*   **uv:** Python packaging tool, used for dependency management (`uv sync --frozen --all-extras`).
*   **OS-Specific Dependencies:** Various libraries for UI (Qt5), multimedia (ffmpeg), system tools, etc. See `tools/install_ubuntu_dependencies.sh` for Ubuntu and `tools/mac_setup.sh` for macOS.

### Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/commaai/openpilot.git
    cd openpilot
    ```
    <!-- TODO: Update this URL if/when PoodlePilot has its own repository -->

2.  **Initialize Submodules & LFS:**
    PoodlePilot uses Git submodules and LFS.
    ```bash
    git submodule update --init --recursive
    git lfs pull
    ```

3.  **Install Dependencies:**

    *   **For Ubuntu:**
        ```bash
        ./tools/install_ubuntu_dependencies.sh
        ./tools/install_python_dependencies.sh
        ```
        *The first script installs system-level packages. The second script sets up `uv` (if not present) and installs Python packages into a virtual environment (`.venv`) using `uv sync --frozen --all-extras` based on `pyproject.toml` and `uv.lock`.*

    *   **For macOS:**
        ```bash
        ./tools/mac_setup.sh
        ```
        *This script uses Homebrew to install system-level packages and then calls `tools/install_python_dependencies.sh` for Python packages.*

    *   **Activate Virtual Environment:**
        After running the Python dependency installation, activate the virtual environment:
        ```bash
        source .venv/bin/activate
        ```

### Development Environment Setup

*   **Using a PC/Laptop:**
    *   Follow the installation steps above.
    *   Ensure your system is set up for C++ and Python development.
    *   [VS Code](https://code.visualstudio.com/) is a popular choice, and the repository includes a `.vscode/` configuration.
*   **Developing for a comma device:**
    *   While much development can be done on a PC (especially with simulation), testing on actual hardware is crucial for many features.
    *   Refer to the official openpilot documentation and community resources for device-specific setup if you intend to deploy directly to a comma 3/3X.

## Running the Application

### On a comma device

For running PoodlePilot on a comma 3/3X:
1.  Follow the [official OpenPilot installation instructions from comma.ai](https://comma.ai/setup).
2.  To use a custom PoodlePilot build (e.g., from your development branch), you typically need to build and transfer it to the device. The `release/` directory scripts, particularly `release/build_release.sh` (which calls `release/pack.py`), are used for creating deployable builds.
    *Further details on deploying custom builds to devices will be added here or in specific Wiki sections once the process is fully documented.*

### In Simulation

PoodlePilot can be run in a simulator, which is highly beneficial for development and testing without needing a car or comma hardware.
*   **Setup and Run Simulation:**
    The `tools/sim/launch_openpilot.sh` script configures and starts PoodlePilot in simulation mode.
    Make sure your virtual environment is active (`source .venv/bin/activate`).
    ```bash
    # From the root of the openpilot directory
    ./tools/sim/launch_openpilot.sh
    ```
    This script sets necessary environment variables (e.g., `SIMULATION=1`, `NOBOARD=1`) and then runs `system/manager/manager.py`.
    *Refer to `tools/sim/README.md` if available, or the script itself for more details on simulation capabilities and requirements.*

## Running Tests

PoodlePilot has an extensive suite of tests, combining Python and C++ tests, primarily run using `pytest`.
Ensure your Python virtual environment is active (`source .venv/bin/activate`).

*   **General Testing:**
    From the root directory:
    ```bash
    # Run all tests (Python and C++ discovered by pytest-cpp)
    pytest

    # Run with parallel execution (similar to CI)
    pytest -n logical # "logical" will use a sensible number of workers

    # Run specific tests by path or name
    pytest selfdrive/controls/tests/test_longcontrol.py
    pytest selfdrive/locationd/test/test_locationd_scenarios.py::test_scenario_a
    ```
    *The `pyproject.toml` file (under `tool.pytest.ini_options`) configures `pytest` to discover C++ tests (`test_*` files) using `pytest-cpp` and `selfdrive/test/cpp_harness.py`.*

*   **Specific Test Suites (examples):**
    *   **Process Replay:** `pytest selfdrive/test/process_replay/test_processes.py`
    *   **Car Models:** `pytest selfdrive/car/tests/test_models.py`
    *   **UI Tests:** See `selfdrive/ui/tests/`. For example, `pytest selfdrive/ui/tests/test_translations.py`.

*   **Coverage:**
    To generate a coverage report (as done in CI):
    ```bash
    pytest --cov --cov-report=xml --cov-append
    # View HTML report: coverage html
    ```

## Building PoodlePilot

PoodlePilot is primarily built using SCons. Ensure your Python virtual environment is active (`source .venv/bin/activate`).

1.  **Standard Development Build:**
    To build all targets. SCons will typically use about half your CPU cores by default.
    ```bash
    # From the root directory
    scons
    # Or specify job count, e.g., using all available cores:
    scons -j$(nproc)
    ```

2.  **Specific Targets:**
    You can build specific parts of the project:
    ```bash
    scons selfdrive/modeld/modeld
    scons system/camerad/camerad # Example, actual target might differ or be part of a larger one
    ```

3.  **Clean Build:**
    To clean build artifacts:
    ```bash
    scons -c
    ```

4.  **Release Builds:**
    For creating packages suitable for deployment on a device, use scripts in the `release/` directory:
    ```bash
    ./release/build_devel.sh  # For a development/testing build
    ./release/build_release.sh # For a full release build
    ```
    These scripts often involve SCons and additional steps like packaging.

## Deployment

Deployment typically refers to installing PoodlePilot on a comma device.
*   **Official Releases:** Users install official OpenPilot releases via URLs like `openpilot.comma.ai` during the device setup. For PoodlePilot, release mechanisms will be defined by its maintainers.
*   **Custom Builds / Development Builds:**
    1.  Build PoodlePilot using the appropriate release scripts (e.g., `./release/build_devel.sh`). This usually creates an update package.
    2.  Transfer the package to the comma device. This might involve SSH, USB, or a custom update mechanism. Consult the OpenPilot documentation and community discussions for methods, adapting as necessary for PoodlePilot.
    3.  Install the update on the device.
    *This section will be significantly expanded in the Wiki documentation with detailed procedures.*

## High-Level Architecture

PoodlePilot's architecture (derived from OpenPilot) is modular, consisting of several key systems and processes that communicate with each other, primarily using the `cereal` messaging library.

*   **Core Components (inherited from OpenPilot):**
    *   **`selfdrive`**: The primary software for autonomous driving capabilities.
        *   **`controls`**: Manages vehicle control (steering, acceleration, braking) through `controlsd`, `plannerd`, and `radard`.
        *   **`modeld`**: Runs machine learning models for perception (e.g., path planning, object detection).
        *   **`locationd`**: Handles localization and sensor fusion (GPS, IMU).
        *   **`camerad`**: Manages camera inputs (on device).
        *   **`ui`**: Provides the user interface on the device.
    *   **`panda`**: Firmware for the Panda hardware interface, which connects to the car's CAN bus. It enforces safety rules. (Submodule: `panda/`)
    *   **`opendbc`**: A repository of DBC files (CAN database files) for various car models, used to decode and encode CAN messages. (Submodule: `opendbc/`)
    *   **`cereal`**: The messaging framework (using Cap'n Proto) used for inter-process communication.
    *   **`system`**: Low-level services for logging (`loggerd`, `logcatd`), hardware management (`hardwared`), process management (`manager`), etc.
    *   **`common`**: Shared utility code, libraries, and data structures.
    *   **`tools`**: Various utilities for development, simulation, data analysis, etc.

*   **Data Flow (Simplified):**
    1.  Sensors (cameras, GPS, IMU, CAN via Panda) provide data.
    2.  Processes like `camerad` (on device), `sensord`, `locationd`, and `pandad` (interfacing with Panda hardware/firmware) acquire and publish this data using `cereal`.
    3.  `modeld` processes vision data and other inputs to make driving predictions (e.g., path, lead vehicles).
    4.  `plannerd` uses model outputs, vehicle state, and other inputs (like desired cruise speed) to plan trajectories.
    5.  `controlsd` translates planned trajectories into vehicle commands (steering angle/torque, acceleration/braking) and sends them to the car's actuators via the Panda interface.
    6.  The `ui` process displays relevant information and status to the driver on the comma device.
    7.  `loggerd` logs data from various processes for debugging, replay, and training.

*(This is a very high-level overview. Detailed architecture diagrams and component descriptions will be part of the Wiki documentation.)*

## Contributing

We welcome contributions to PoodlePilot! Please see our detailed [Contribution Guidelines](docs/CONTRIBUTING.md) (Note: this currently points to the original OpenPilot guidelines and may need to be adapted for PoodlePilot) and the project's Code of Conduct (link to be added or file created).

Key points:
*   Priorities: Safety, stability, quality, features (in that order).
*   Check existing issues and discussions before starting work (refer to PoodlePilot's issue tracker if separate from OpenPilot's).
*   Follow coding style and submit well-tested pull requests to the PoodlePilot repository.
*   Join the [OpenPilot community Discord](https://discord.comma.ai) for discussions with other developers and users. (PoodlePilot specific channels may be established here or elsewhere in the future).

## License

PoodlePilot is a fork of OpenPilot and is also released under the MIT License. See the [LICENSE](LICENSE) file for more details.
The original OpenPilot software is copyrighted by comma.ai and its contributors.
Some components inherited from OpenPilot may be under different licenses as specified within their respective directories.
