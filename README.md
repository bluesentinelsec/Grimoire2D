# Grimoire2D

A professional-grade, opinionated 2D game framework targeting a Love2D-like developer experience in Python, powered by pygame-ce + OpenGL 3.30 core.

**Key documentation:**
- [docs/design-goals.md](docs/design-goals.md) — Project charter, vision ("the game is just data"), features, tech stack, invariants, success criteria.
- [AGENTS.md](AGENTS.md) — Mandatory rules for architecturally correct code (SOLID, explicit, layered, data model / logic / presentation separation, no hacks/half-measures).
- [docs/proposals/](docs/proposals/) — Design proposals. 0001: data model architecture. 0002: incremental plan for the first user-facing milestone (minimal window + game loop).

The core library is delivered via `pip install grimoire2d`. The repository also contains demos and supplemental tools.

See design-goals.md for platform support (Windows AMD64, Linux AMD64, macOS ARM — Steam-focused), runtime options, professional persistence, VFS + hot reload for data, flagship dynamic lighting/fog/GPU particles, Dear PyGui for professional tooling, direct TCP multiplayer, and the requirement to keep data model, business logic, and presentation clearly separated.
