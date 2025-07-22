# Development Practices and Tools

Effective development in the openpilot ecosystem involves understanding its specific tools, workflows, and best practices. This section provides an overview of key areas to help developers contribute efficiently and maintain code quality.

## Overview

Developing for openpilot can range from tweaking car parameters and tuning control algorithms to working on core perception models or system services. Regardless of the area, a common set of practices and tools applies.

## Key Areas

The following pages delve into specific aspects of development:

*   **[Debugging Techniques](TODO-Debugging-Techniques.md):** (To be created)
    *   Strategies for debugging C++ and Python processes.
    *   Using tools like `gdb`, `pdb`, and IDE debuggers.
    *   Analyzing system logs and `cereal` message logs.
    *   On-device debugging tips and tricks.
    *   Leveraging simulation for debugging.

*   **[Testing in openpilot](TODO-Testing-in-openpilot.md):** (To be created)
    *   Overview of the testing philosophy.
    *   Running unit tests (`pytest` for Python and C++).
    *   Understanding and using process replay tests (`selfdrive/test/process_replay/`).
    *   The role of simulation in testing.
    *   Hardware-in-the-loop (HIL) testing concepts (if applicable).
    *   Continuous Integration (CI) checks and how they validate contributions.

*   **[Profiling and Performance Analysis](TODO-Profiling-Performance.md):** (To be created)
    *   Identifying performance bottlenecks in C++ and Python code.
    *   Using profiling tools available in the repository (e.g., from `tools/profiling/` like `py-spy`, `perf`, `FlameGraph` generation).
    *   Optimizing code for real-time performance on embedded hardware.

*   **[Working with Submodules](TODO-Working-with-Submodules.md):** (To be created)
    *   Understanding how openpilot uses Git submodules (e.g., for `panda`, `opendbc`, `tinygrad`).
    *   Common workflows for updating and contributing to submodules.

*   **[Code Style and Linting](TODO-Code-Style-Linting.md):** (To be created)
    *   Importance of adhering to coding standards for C++ and Python.
    *   Using linters and formatters (`ruff`, `codespell`, `clang-format`).
    *   Pre-commit hooks and CI checks for style enforcement.

*   **[Build System (SCons) - Developer Guide](TODO-Build-System-Developer-Guide.md):** (To be created)
    *   (This would be a more developer-focused companion to the architectural overview of SCons).
    *   Tips for efficient SCons usage.
    *   Understanding common build issues.
    *   Adding new files or modules to the build system.

*   **[Working with `cereal` and `.capnp` schema](TODO-Cereal-Schema-Development.md):** (To be created)
    *   Best practices for modifying or adding new `cereal` message types.
    *   Ensuring backward and forward compatibility.
    *   Recompiling schema and understanding generated code.

## General Best Practices

*   **Version Control (Git):** Follow best practices for Git usage, including meaningful commit messages, logical commit history, and effective branching strategies (see [Contribution Guidelines](../docs/CONTRIBUTING.md) - *adjust link as needed*).
*   **Incremental Development:** Break down complex tasks into smaller, manageable changes.
*   **Test-Driven Development (TDD):** Where appropriate, write tests before or alongside your code.
*   **Documentation:** Comment your code, especially complex or non-obvious sections. For significant changes, consider if Wiki documentation also needs updating.
*   **Community Engagement:** Utilize the [openpilot community Discord](https://discord.comma.ai) for questions, discussions, and collaboration with other developers and users.

---
*This page serves as a directory to more detailed articles on specific development practices and tools. Effective use of these resources will help ensure high-quality contributions to openpilot.*
