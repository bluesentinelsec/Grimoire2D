# Grimoire2D Design Goals and Project Charter

**Status:** Draft (synthesized from QUESTIONNAIRE.md)  
**Scope:** Personal indie project, but held to professional-grade standards.  
**Date:** 2026 (regenerated from updated questionnaire)

---

## Vision

Grimoire2D is a Python 2D game framework that provides a **Love2D-like** developer experience while delivering the **robust, production-ready subsystems** required to ship commercial-grade PC games (primarily via Steam, with potential support for Epic Games Store and GOG).

The guiding philosophy is **"the game is just data"**:

- The engine is a solid, architecturally correct, opinionated foundation that correctly and performantly handles the 99% of concerns shared by virtually all 2D games.
- Developers point the engine at media assets (via a virtual filesystem) and supply game-specific logic.
- Everything else — window management and scaling, screen/scene transitions, input mapping, audio, physics, rendering, persistence, UI scaffolding, multiplayer connectivity, loading from packed + obfuscated archives, cross-platform filesystem access, font rendering, dynamic library loading (e.g. Steam SDK), etc. — is abstracted, correct by default, and does not require the game author to reinvent it.

The framework must feel immediate and productive at the call site (library API style with `init`/`update`/`render`/`quit` hooks, immediate-mode *feel*) while the internals can be as sophisticated as necessary for performance and correctness. Callers should never need to care about the underlying OpenGL or platform details for normal use.

It must support both **code-first game development** and the creation of higher-level graphical tools (level editors, etc.). Tooling uses a first-class external GUI library (Dear PyGui is the recommended choice) while the engine renderer powers game viewports and content preview where embedded.

**North-star experiences:** High-fidelity, clean implementations of classic 2D action, platformer, and adventure games such as *Super Mario World*, *The Legend of Zelda: A Link to the Past*, *Contra 3*, plus Diablo-style ARPGs, and foundational titles (Pong, Asteroids, Pac-Man, Space Invaders, Pitfall, auto-scrollers, top-down adventures, etc.).

The desired end state is the ability to ship a complete Steam game using this framework.

---

## Guiding Principles

- **Explicit and transparent over magic or syntactic sugar.** Only one obvious way to do common things. Maximize namespace clarity so it is trivial to trace which module a name comes from and how execution flows. Easy to read and debug at a glance.
- **SOLID architecture.** Strong application of Single Responsibility Principle and Open/Closed Principle. Partition the engine's data model, business logic/rules, and rendering/views so the system is easy to test, reason about, and evolve without heavy modification of old code.
- **Professional-grade shipping is the bar.** The engine must eliminate the boilerplate and correctness traps that stop most Python 2D projects from reaching commercial quality: proper window modes (exclusive fullscreen, borderless, windowed) with runtime switching and correct scaling/resize behavior, virtual resolution + integer scaling + letterboxing, packed media archives with light obfuscation, screen transitions, professional persistence, clean PyInstaller distribution, etc.
- **Opinionated but enabling.** The "imposed way of working" is a deliberate feature. Game developers want to focus on logic and art; they should not have to fight the engine on window scaling, load screens, options menus, or basic screen flow.
- **Layered access.** High-level productive APIs for the 95% case. Obvious, documented escape hatches to lower-level primitives (pygame-ce surfaces/events, raw OpenGL context/objects, physics bodies, etc.) without requiring forks or monkey-patching.
- **Data-driven where practical.** Normal game content (assets, config, levels, etc.) lives outside Python code. First-class support for a virtual filesystem over compressed archives (zip-based, with optional simple symmetric cipher obfuscation for casual protection only — PyInstaller games are trivially decompilable anyway).
- **Performance via delegation + batching.** Hot paths delegate to mature C-level libraries (pygame-ce, OpenGL). Batching and hardware acceleration are mandatory under the hood but invisible to normal callers. Callers never need to know OpenGL is present.
- **Self-documenting, testable code.** Small, well-named functions that express intent. Long-lived comments only (architectural rationale, not tactical issue references). Thorough automated test coverage. Favor standard library for tests and docs.
- **CI/CD and cross-platform testing are non-negotiable.** The project must maintain a CI/CD pipeline that runs the full test suite on Windows, macOS, and Linux.

---

## Scope and Target Capabilities (Professional-Grade Release)

The questionnaire placed nearly every major subsystem into the "MVP" bucket. There is **no emphasis on the smallest possible slice**. Scope is managed through strong architecture (SRP, OCP, clear layering, testability) and smart prioritization rather than by declaring large parts of the engine "post-1.0."

The core library (`pip install grimoire2d`) delivers the framework. The source repository may additionally contain demos, example games, and supplemental tools (e.g. editors built on the framework). Supplemental tools and demos are not automatically in scope for the pip package distribution.

### Core Loop, Configuration & Flow
- Sane managed game loop with configurable target FPS (default 60; caller may set a maximum), fixed/variable timestep options, pause support.
- Game options such as window mode, effects, audio, input all need to be configurable at runtime, from an options screen reachable in most contexts.
- Frame-rate independent logic via delta time.
- Library-style API: caller supplies (or registers) `init`, `update(dt)`, `render`, `quit` functions/methods. Immediate-mode *feel* at the API surface.
- Rich runtime configuration for engine behavior: window size and mode (exclusive fullscreen, borderless, windowed), vsync on/off, audio levels, input maps, etc.
- Professional windowing + virtual resolution: resolution independence via integer scaling + letterboxing. Proper handling of runtime resize, mode switches, and scaling.
- Scene / gamestate / screen stack management with transitions (e.g. fade in/out). Scaffolding or easy patterns for the common commercial screens (splash, title, gameplay, options, pause, loading, etc.).

### Graphics, Assets & Camera
- Sprites with batching (batching is mandatory for performance), animations, texture atlases.
- Tilemaps (at minimum orthogonal; isometric and hexagonal desirable).
- Full 2D camera: position, zoom, rotation, screen shake, bounds, follow targets, etc.
- **Virtual filesystem (VFS)**: read arbitrary files from compressed and (optionally) obfuscated archives. Grimoire2D archives are zip-based; obfuscation uses a simple symmetric cipher (casual protection only).
- Asset hot-reloading (code, textures, shaders, data) during development, emulating patterns from engines such as Godot.
- Shaders are first-class and "embedded as code" (Raylib-inspired). Provide default shaders for common tasks; allow caller-provided shaders.
- Math primitives (Vec2/3/4, Rect, transforms, easing, intersections, etc.) that are fast, mature, and light on transitive dependencies (to keep final bundled game size small). 
- Prefer library dependencies that are mature, stable, performant, and contain minimal transitive dependencies. Exceptions can be made on a case-by-case basis.

### Input, Audio & Physics
- Input abstraction covering keyboard, mouse, gamepad. Support for rebinding and chords. Favor buffered / real-time input over pure event-based where it improves perceived responsiveness.
- Audio: streaming music, sound effects, volume groups/categories, and **2D spatial / positional audio**. pygame-ce mixer is the expected baseline (considered adequate).
- 2D rigid-body physics with collision detection, queries, and joints. Use a stable, mature, performant existing library (pymunk/Chipmunk is the leading community candidate in the pygame ecosystem; pybox2d is an alternative). Custom physics engine is a non-goal. Required features include static/dynamic/kinematic bodies, sensors, one-way platforms, raycasts, and practical continuous collision.

### Particles, Lighting, Fog, Post-Processing (Flagship Visual Features)
- Particle/emitter system (should be GPU/shader based for performance).
- **Dynamic lighting and fog are major selling points and differentiators.** High-quality, performant lights. Vision statement: "imagine if *Doom 3* was a 2D side-scroller" — impressive lighting paired with particles and fog for strong visual impact. Use of shaders should make it fast.
  - Light types: point, spot, directional, ambient (area as needed).
  - Sprite interaction: multiplicative/additive, normal-mapped (height-mapped desirable).
  - Shadow casting (hard/soft 2D techniques chosen for look and performance).
  - Light cookies/gobos/textured lights.
  - We should be able to have an arbitrary number of lights by making use of culling and batching 
  - Fog: atmospheric/distance/height fog (sidescrollers, pseudo-depth); fog-of-war via runtime-paintable visibility masks (top-down).
  - Full-screen post-processing pipeline (bloom, CRT, vignette, custom user passes). Order is significant; easy extension points for caller shaders.
- All lighting/fog/post effects must integrate cleanly with the batched renderer and camera and remain performant.

### In-Game HUDs and Professional Tooling
- In-game HUDs, menus, and overlays are the responsibility of the game author. The engine supplies only low-level drawing primitives (rects, text, lines, sprites, pixel buffers) via the Renderer for simple immediate-mode HUDs and debug overlays.
- Professional tooling (level editors, animation tools, inspectors, etc.) is built with a dedicated external GUI library. Dear PyGui is the recommended, supported choice for video game programming tools in this ecosystem. See `demos/editor_mockup.py` for the current reference implementation.
- When a tool needs a live game/content preview it can render a Grimoire2D scene to an offscreen texture (using the public Renderer + moderngl context) and present the result inside the tool GUI. The engine itself does not own or ship widget set code.

### Rendering Internals
- **Everything is OpenGL 3.30 core from day one.** No legacy software or immediate-mode fallback paths in the primary renderer.
- Batching is mandatory under the hood for performance; completely hidden from normal callers.
- Callers never need to know or care that OpenGL is running unless they explicitly use a low-level escape hatch.
- Default shaders for common tasks + first-class support for caller-supplied shaders.
- Hot reload for shaders.

### Debug, Persistence, Dev Ergonomics & Multiplayer
- Debug overlays and tools: FPS counter, physics debug draw, bounding boxes, light gizmos, profiler hooks, etc.
- Professional-grade persistence: save/load (JSON and binary-friendly formats), configuration, high scores, cross-platform friendly save locations.
- Hot reloading of code + assets + shaders is a hard requirement.
- **Multiplayer netcode is required** (not a non-goal). Client/server model using direct TCP/IP connections (LAN or Internet). Players are responsible for port forwarding and firewalls. No matchmaking or hosted relay services in the core. Must be performant enough that "every game can be multiplayer if desired."

### Distribution & Packaging
- Primary consumption model: `pip install grimoire2d` (with optional extras as needed). Callers are expected to install the library this way.
- The library must be **PyInstaller friendly**. Professional single-file or single-folder executables for Windows/macOS/Linux must be straightforward (framework provides helpers, documented patterns, or clean separation so vendoring works).
- Stable, mainstream Python 3 build (chosen for long-term PyInstaller compatibility and broad platform support).
- The Git repository may contain demos, example games, supplemental tools, CI configuration, etc. These are not automatically part of the pip-installable library distribution.

---

## Technology Stack

### Core Runtime
- **Language / Packaging:** Python 3 (sane stable version chosen for PyInstaller friendliness). Primary delivery is a pip-installable library.
- **Windowing, Input, Basic Media, Time:** pygame-ce. Build on top of its abstractions for surfaces, events, mixer, font, etc. in most cases.
- **Rendering:** OpenGL 3.30 core profile exclusively. Hardware acceleration and batching are mandatory. Modern context acquisition may use pygame-ce's GL support, moderngl, PyOpenGL, or similar as needed internally; the public API hides this.
- **Shaders:** Embedded as code (Raylib style) or loadable from files, with hot reload. Default shaders provided; caller shaders supported.

### Key Subsystems
- **Physics:** Stable, mature, performant 2D library (pymunk/Chipmunk strongly preferred due to ecosystem; evaluate pybox2d as alternative). No custom full physics engine.
- **Math / Geometry:** Lightweight, fast primitives (own `g2d.math` module or a slim, mature dependency with minimal transitive deps). Avoid heavy scientific stacks.
- **Audio:** pygame-ce mixer baseline + 2D spatial/positional support.
- **GUI for tools:** Dear PyGui (external). The engine renderer and input are available for embedding game viewports inside tools but the core library does not implement widgets. In-game HUDs are drawn with engine primitives or game-specific code.
- **Virtual Filesystem + Archives:** Custom VFS layer over zip, with optional simple obfuscation.
- **Hot Reloading:** File watching + reload patterns for code, resources, and shaders (Godot-inspired).
- **Packaging / Distribution:** PyInstaller (core requirement). The library must not make clean bundling difficult.

### Tooling & Quality (Mature & Ubiquitous Only)
- Linting, formatting, type checking: ruff (or equivalent proven tools); mypy where it adds value without excessive ceremony.
- Testing: pytest (property-based testing encouraged where useful). Example games (see Success Criteria) serve as integration tests.
- Documentation: Favor self-documenting code + standard library (doctests, etc.). Additional docs tools only if they provide clear long-term value with low maintenance cost.
- **CI/CD:** Mandatory pipeline that invokes/runs the full project test suite on Windows, macOS, and Linux.

### License & Dependency Constraints
- Current project license: LGPL-2.1.
- Runtime dependencies must never introduce copyleft terms (GPL, AGPL, or similar) that would "infect" or impose obligations on end-user games.
- Pin dependency versions. Use only mature, longstanding libraries.
- PyInstaller (and similar) must be able to vendor/freeze the entire thing into a distributable without internet access at runtime.

---

## Architecture & Invariants

### Layering (Must Be Visible and Useful)
- High-level productive API (the Love2D-like surface most developers and tool authors use).
- Mid-level subsystems (camera, VFS, scene/screen manager, lighting system, physics world, asset loaders, etc.). Tooling GUIs live outside the core.
- Low-level escape hatches (direct pygame-ce objects, GL context/buffers/shaders/programs, raw physics bodies, etc.).
- Internals must support testing by keeping data model, rules/logic, and views/rendering clearly separated.

### Hard Invariants (Must Always Hold)
- Primary rendering path is always OpenGL 3.30 core + batching. Normal callers are fully shielded from this.
- Resolution independence is achieved via integer scaling + letterboxing (the supported model).
- Input latency is minimized for game feel; buffered/real-time input is preferred over pure event handling where it matters.
- "The game is just data": normal content lives in the VFS (assets, JSON configs, level data, etc.). User code is the thin logic + rules layer.
- Common data models are provided exclusively as registered extensions inside EngineConfig (which itself has no hard-coded members — only version + extensions dict). Game-specific models follow the same DataModel contract and are composed by the game (see models/config.py docstring and proposal 0001). Every addition is purely net-new.
- Hot reload works for Python code, shaders, textures, and data (development time).
- Performance/memory: opt-in mechanisms for constrained targets (explicitly: games should run well on original Steam Deck specs).
- Only one primary, obvious way to accomplish common tasks (window configuration, scene transitions, asset loading, etc.).
- Escape hatches are documented and do not require fighting the framework.
- Automated tests cover the engine's core data model, business rules, and (to the extent practical) rendering separation.
- The library remains PyInstaller-friendly and pip-installable.

### Performance & Quality Bar
- 60 FPS is the common target; callers can configure a maximum FPS. Higher refresh rates (120/144) supported where the loop and vsync settings allow.
- Target hardware: modern Windows, Linux, and macOS PCs. Must run well on Steam Deck (original hardware).
- Example aspirational load (to be validated through implementation and profiling): hundreds to low thousands of lit, animated, normal-mapped sprites + multiple dynamic lights + particles + physics at 1080p with headroom on target hardware. (Tool GUIs run in separate processes or as light overlays.)
- Input must feel responsive.

---

## Platform Support

**Primary / Must Support (tailored for shipping Steam games):**
- Windows 10/11 (AMD64)
- Linux (AMD64; X11 and Wayland)
- macOS (ARM / Apple Silicon; universal binary strongly preferred)

**Explicitly Out of Scope (for the foreseeable future):**
- Web / browser (WASM, pygbag, etc.)
- Mobile (Android, iOS, buildozer, etc.)
- Consoles
- Raspberry Pi or other embedded devices as primary targets (Steam Deck is the relevant constrained device for performance considerations)

**CI / Test Matrix:** Full automated test suite must run on Windows, macOS, and Linux via CI/CD. Steam Deck verification is expected to be manual or via developer hardware.

---

## Non-Goals (Scope Control)

Deliberately **not** building into the core (at least for the first 1–2 years):

- Visual scripting or node graphs.
- 3D rendering or heavy 3D concepts (billboards, pseudo-3D perspective, etc.). Competent **2D dynamic lighting** is explicitly required and a priority.
- Console export, certification, or platform-specific console toolchains.
- Official asset store, marketplace, or content pipeline services.
- Heavy runtime asset pipeline work (texture compression at runtime, automatic atlasing/packing tools, etc.). Asset preparation is a development-time or build-time concern for the game author.
- Matchmaking, lobbies, relay servers, or any hosted multiplayer services. (Direct TCP/IP client/server netcode *is* required.)

**Clarification on editors:** The core library will *not* ship a full "built-in" level editor or tilemap editor as part of the pip package. The source repository contains demos (e.g. `demos/editor_mockup.py`) showing how to build professional editors using Dear PyGui + Grimoire2D content/viewport integration when desired. The framework itself remains a focused game runtime library.

---

## Documentation, Testing & Process Philosophy

- **Code is the primary documentation.** Small, well-named functions, strong separation of concerns, and thorough tests make the system understandable. Comments are reserved for long-term architectural rationale.
- Example games (the classic recreations listed under Vision and Success Criteria) are first-class citizens: they serve as integration tests, regression tests, and living tutorials.
- Use only proven, ubiquitous, mature tooling.
- CI/CD that runs the complete test suite on all three primary desktop platforms is mandatory.

---

## Success Criteria (Personal / Project Use)

The framework is "good enough" for its intended purpose when the author can implement and (near-)ship real games with it, including at minimum:

- Foundational arcade: Pong, Asteroids, Pac-Man, Space Invaders.
- Platform/action: Pitfall-style side-scrollers, auto-scrollers, *Super Mario World*-like, *Contra 3*-like.
- Adventure/ARPG: Top-down *Legend of Zelda: A Link to the Past*-style, *Diablo*-style.

Additional success signals:
- A full-featured level editor (or other non-trivial standalone tool) can be built using Dear PyGui for the interface and Grimoire2D (renderer + assets + input models) for game content preview and data.
- Clean, professional PyInstaller distribution of a non-trivial game works reliably on Windows, macOS, and Linux.
- Hot reload, dynamic lighting + fog + particles, physics, Dear PyGui-based tools, and multiplayer netcode can be used together in a project without heroic workarounds.
- The codebase remains clean, architecturally sound (SOLID), and easy to modify after the above milestones.
- The library installs via pip, games bundle via PyInstaller, and the full test suite passes under CI on all three platforms.

---

## Open Items / TBD (Resolved via Prototypes & Follow-on Work)

- Exact physics library selection and the precise collision feature matrix (after evaluation spikes).
- Concrete math implementation (own lightweight module vs. slim external dep).
- (removed) GUI is delegated to Dear PyGui for tools; engine drawing primitives are intentionally low-level.
- Shader embedding format details and the initial set of default shaders.
- Exact VFS obfuscation implementation (simple, reversible, well-documented cipher).
- Performance / Steam Deck opt-in API surface and any associated modes or profiles.
- How much "screen template" scaffolding (title screen, options, etc.) lives in the core library vs. being easy patterns in documentation/demos.
- Whether any supplemental tools (e.g. a basic editor) ship inside the pip package or live only in the repository.
- Data model shapes and ownership details (see `docs/proposals/0001-data-model-architecture.md` and the incremental implementation plan in `docs/proposals/0002-minimal-game-loop-incremental-plan.md`).

These will be closed through implementation spikes, profiling, and small design notes as work proceeds.

---

**End of Charter.** This document is the authoritative reference for project goals, vision, feature scope, technology choices, constraints, invariants, and platform decisions. All future architecture, implementation, refactoring, and feature work must be evaluated against it.

When in doubt, prefer:
- Explicitness and architectural cleanliness (SOLID, no magic)
- "The game is just data" + professional shipping capability
- High-quality 2D lighting/fog as a visual differentiator
- A pip-installable, PyInstaller-friendly core library
- Full CI coverage on Windows + macOS + Linux
- Follow known successful patterns in video game engines

**Immediate next steps (suggested):** Per the user's modular approach and Proposal 0002, execute the small chunks in `docs/proposals/0002-minimal-game-loop-incremental-plan.md` (starting with scaffolding + first data model slice) to reach the first user-facing milestone (open window + minimal managed game loop) while spanning model/logic/view in an architecturally correct way. All work must obey AGENTS.md (no quick fixes, hacks, or half-measures) and the data model / business logic / presentation separation. Check everything against the charter, AGENTS.md, 0001, and 0002.
