# Welcome to the openpilot Developer Wiki

This Wiki is a comprehensive technical resource for engineers and developers working on or contributing to the openpilot codebase. It aims to provide in-depth explanations of the system architecture, components, development practices, and other essential technical information.

## Purpose

While the main [openpilot documentation](https://docs.comma.ai) (and the root [README.md](../README.md)) offers user-facing information and a general overview, this Wiki delves into the "how" and "why" of openpilot's internals. It's designed to help you:

*   Understand the software architecture and how different modules interact.
*   Learn about key algorithms and control strategies.
*   Get familiar with the development environment, tools, and processes.
*   Find detailed information on specific components and subsystems.
*   Effectively contribute to the project.

## Navigating This Wiki

This Wiki is organized into several main sections:

*   **[Architecture Deep Dive](Architecture-Deep-Dive.md):** A detailed look at the overall system architecture, core philosophies, process breakdowns, inter-process communication, hardware abstraction, and more.
*   **[API Reference / Messaging (cereal)](Inter-Process-Communication-with-Cereal.md):** Focuses on the `cereal` messaging library, message definitions, and how services communicate.
*   **[Parameter Management](Parameter-Management.md):** Explains how on-device parameters are stored and managed.
*   **[Key Components/Modules](components/):** In-depth articles on specific critical components like the controls system, perception system, CAN communication, etc. (This will be a directory of pages).
*   **[Development Practices and Tools](Development-Practices-and-Tools.md):** Information on debugging, testing, profiling, working with submodules, and coding standards.
*   **[Car Porting Guide](Car-Porting-Guide.md):** (Future Section) Detailed instructions and best practices for porting openpilot to new vehicle models.
*   **[Glossary](Glossary.md):** Definitions of common terms, acronyms, and concepts used within the openpilot project.

Use the links above or the sidebar (if your Wiki viewer supports it) to navigate through the sections. Pages will cross-link to related topics for easier exploration.

## Other Important Resources

*   **Developer [README.md](../README.md):** For developer-focused setup, build, and run instructions.
*   **[Contribution Guidelines](../docs/CONTRIBUTING.md):** Essential reading before making contributions. (Note: Link might need adjustment based on final location of `CONTRIBUTING.md` if it's moved or renamed).
*   **[Official openpilot Documentation](https://docs.comma.ai):** User manuals, supported cars, and general information.
*   **[openpilot community Discord](https://discord.comma.ai):** Engage with the community for discussions with other developers and users.

We hope this Wiki serves as a valuable tool for your openpilot development journey!

---
*This Wiki is a living document and will be continuously updated and expanded.*
