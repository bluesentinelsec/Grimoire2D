# Proposal 0002: Incremental Path to First User-Facing Milestone (Minimal Window + Managed Game Loop)

**Status:** Proposed  
**Date:** 2026-06  
**Related:**
- [docs/design-goals.md](../design-goals.md) — First visible milestone should be "open a window and run a minimal game loop". Managed game loop with delta time, configurable FPS (default 60), library-style API (init/update/render/quit functions or methods). "The game is just data". Layered architecture with clear data model / business logic / presentation separation. Runtime configuration (window size/mode, vsync, etc.) from options. Professional-grade from the start. g2d import convention. PyInstaller-friendly. Follow known successful engine patterns (Love2D-like feel for the loop).
- [AGENTS.md](../../AGENTS.md) — **All work must obey this strictly**. src/grimoire2d/ layout. Explicit namespaces (maximize clarity of module origins). Data model / rules / views separation for testability (even in the minimal milestone). Small functions. Data classes / simple value objects for models. No hacks, no half-measures, no deferred bugs, no "we'll clean it up later". Start with data models per 0001. Use ruff, pytest from day 1. Composition, protocols, explicit over magic. Engine owns/co-ordinates; no circular imports.
- [docs/proposals/0001-data-model-architecture.md](0001-data-model-architecture.md) — User is in general agreement. Data models come first. Pure data (no logic or presentation). Options/config as a core data model category (runtime mutable, observable). World/simulation states. Serialization boundary, Data Context / Model Host, versioning for adaptability. VFS integration (even if stubbed initially for the loop). All data (including the minimal config that drives the window) must be treated as data.

This proposal describes a **sequence of small, focused chunks** (one core idea at a time) to reach the first user-facing milestone while properly scaffolding the project and honoring every constraint.

---

## 1. Milestone Definition (What "Success" Looks Like)

The first user-facing, demonstrable milestone is:

- `pip install -e .` (or equivalent editable install)
- Run a small demo (e.g. `python -m demos.minimal` or `python demos/minimal_loop.py`)
- A window opens (using pygame-ce + OpenGL 3.30 core attributes, per charter)
- A managed game loop runs (default 60 FPS target, configurable, delta time passed to update)
- User provides simple hooks (init / update(dt) / render / quit) — library API feel, immediate-mode *surface*
- Something visible happens (e.g. the screen clears to a color taken from a runtime config data model; title from config; perhaps a simple "ESC to quit" or auto-timeout)
- Loop respects pause, basic timing, and can be driven from user code
- The demo works on the three primary platforms
- All code is architecturally sound (no hacks), fully tested at the appropriate level, and follows the module structure

This milestone will necessarily touch **data model**, **business logic**, and **presentation** layers, but we will introduce them in controlled, separated increments.

**Non-goals for this milestone** (defer per small-chunk philosophy):
- Full VFS + archives + hot reload (stub or minimal in-memory for config)
- Real batching / sprites / shaders / lighting (a minimal renderer that just clears is acceptable if the *structure* is correct per AGENTS)
- Scene stack, GUI, physics, net, persistence, particles, etc.
- Polished error handling or options screen UI (just enough to prove the config data model is wired)
- Production PyInstaller bundle (but structure must not break it)

## 2. Guiding Constraints for Every Chunk

Every step **must**:
- Follow AGENTS.md 100% (layout, separation, explicitness, no half-measures, ruff + tests required before considering a chunk "done").
- Align with Proposal 0001 (data models as pure value objects first; config as observable runtime data; clear ownership; preparation for VFS/serialization).
- Respect design-goals (library API shape, delta time, "game is just data", GL 3.30 from day one, encapsulated).
- Be small: one core idea per chunk. Deliverable = working code + tests + (if relevant) demo + doc update.
- Produce something reviewable / runnable after each chunk.
- Codify module structure and imports early and consistently (e.g. `import grimoire2d as g2d`, `from grimoire2d.models.config import ...`, `from grimoire2d.logic.loop import ...`, explicit subpackage usage).
- Start automated tests immediately (unit for data models and pure logic; integration for the loop + window where feasible).

We will **not** write presentation code that bypasses the future graphics layer, nor logic that owns data, nor data that contains behavior.

## 3. Proposed Incremental Sequence (Small Chunks)

### Chunk 0 (Infra / Scaffolding — Core Idea: "Project can be installed and tested as a proper package")
- Create `pyproject.toml` (name="grimoire2d", dynamic version, dependencies=[pygame-ce], optional dev deps for ruff/pytest, [tool.ruff], [tool.pytest.ini_options]).
- Establish `src/grimoire2d/` layout (models/, logic/, presentation/ directories with `__init__.py` — making the data / logic / presentation separation obvious).
- Minimal `src/grimoire2d/__init__.py` (expose `__version__`, perhaps a placeholder for the future `run` entrypoint; no premature re-exports).
- Basic `tests/` structure (`tests/unit/`, `tests/integration/`, `conftest.py`).
- A single passing test: `import grimoire2d as g2d; assert g2d.__version__`.
- Run `ruff format/check` and `pytest` as part of the chunk.
- Update `.gitignore` if needed for new build artifacts.
- Update README.md to document "getting started for development" (editable install + running tests + running the future minimal demo).
- **Layers touched**: None (pure scaffolding). Sets up the module structure and import conventions that all future code will follow.
- **Verification**: `pip install -e ".[dev]"`, `pytest`, `ruff check .`, import works cleanly.
- **Why first**: You can't do anything architecturally correct without the skeleton. This codifies structure/imports/tests immediately.

### Chunk 1 (Data Model — Core Idea: "The first pure data model exists and is testable in isolation")
- Per 0001 and AGENTS: Introduce the data layer.
- Minimal `src/grimoire2d/models/` (the data model directory).
- First model: a small, pure `EngineConfig` / `GameOptions` (window title, size, target_fps, vsync, clear_color as a simple tuple or Vec, etc.). Use `dataclass` (frozen or with clear mutation story) + slots if appropriate. Pure value object — no methods with side effects.
- Basic serialization boundary (to_dict / from_dict classmethods or free functions). Version field.
- Defaults + simple construction.
- **No VFS yet** (in-memory or dict loading is fine; comment notes the future VFS path).
- Unit tests only: construction, equality, serialization roundtrips, validation of invariants, mutation semantics.
- **Layers touched**: Pure data model (Category A from 0001).
- **Verification**: All tests pass; can create a config, mutate a runtime value, serialize it.
- **Why here**: Honors "start with the data model first". Gives us something real for the loop to drive (e.g. clear color and title come from data).

### Chunk 2 (Data Model + Observation — Core Idea: "Config is runtime-mutable and observable as required")
- Extend the config model so it is explicitly mutable at runtime.
- Introduce a minimal observation mechanism (e.g. a simple `ConfigObserver` protocol or callback registry in a `ConfigHost` / thin Data Context). Systems "register interest" or poll a snapshot.
- Tests prove that changes are visible to observers without magic globals.
- Keep everything pure + isolated.
- **Layers touched**: Data + the beginning of the "host" concept from 0001.
- **Verification**: Test that changing a value notifies registered observers (or snapshot reflects change).
- **Why now**: Directly satisfies charter ("Game options ... configurable at runtime, from an options screen") and AGENTS ("Configuration is explicit and runtime-mutable").

### Chunk 3 (Core Logic / Loop — Core Idea: "The managed game loop exists as pure logic operating on data")
- Introduce `src/grimoire2d/logic/` (loop management, timing, the engine "host").
- Implement the skeleton of the managed loop:
  - Timing (delta time calculation, fixed/variable timestep options, FPS limiting, pause support).
  - The entry point API (e.g. `g2d.run(init=..., update=..., render=..., quit=...)` or a minimal `App`/`Engine` class with overridable methods — decide one primary shape per charter's "library API" preference for explicitness).
  - Loop owns/co-ordinates a Config (from previous chunk) and a minimal world/simulation state placeholder.
  - Calls user hooks at the right times. Passes dt to update.
- The loop itself is **logic** (rules for when to call what, timing math). It consumes/produces data models but does not own presentation.
- Headless tests: run N fixed steps, assert timing, hook call counts, config is visible inside the loop.
- **Layers touched**: Data (config) + business logic (loop rules). No presentation yet.
- **Verification**: A test that exercises the loop for 100 "frames" without opening a window.
- **Why here**: This is the "managed game loop" heart of the milestone. Keeps it separate from windowing.

### Chunk 4 (Minimal Presentation + Window — Core Idea: "We can open a GL window and draw something driven by data")
- Start `src/grimoire2d/presentation/` (per the structure: everything front-end / GL lives here or below; batching and encapsulation will grow here later).
- Minimal `Renderer` / `WindowContext` that:
  - Uses pygame-ce to set GL attributes for 3.30 core + double buffer.
  - Opens a window (size/title from the config data model).
  - Provides a `clear()` or `present()` that does the GL clear (color from config) + swap.
  - All raw GL (or moderngl/PyOpenGL) calls are inside this layer. No leakage.
- This is the first real **view/presentation** code.
- Integration-style test or a very small demo that can be run manually: create config, create renderer, open window, clear a few times, close.
- For CI friendliness: the test can be marked `integration` or `requires_display` and skipped in headless CI runs initially (we still exercise the structure).
- **Layers touched**: Data (config drives window) + Presentation (encapsulated GL window + clear).
- **Verification**: Manually run a script that opens a window with the title and clear color from a config instance. ESC or timeout to exit cleanly.
- **Why here (after logic)**: We now have something to render. The renderer is a proper (if tiny) citizen of the graphics package.

### Chunk 5 (Integration — Core Idea: "Everything wires together into the first user-facing minimal loop")
- Wire the pieces:
  - The loop (Chunk 3) now owns/uses the graphics renderer (Chunk 4).
  - Render phase calls the minimal clear using data from config.
  - User can pass (or the loop provides) a config that affects the running window (title, size, clear color).
  - Basic quit handling (user hook or default ESC).
  - Delta time flows from logic to user update.
- Create the first real demo under `demos/minimal_loop.py` (or `demos/000_minimal.py`) that demonstrates the library API.
- Full round-trip test (integration): start loop with a config, run a few frames (perhaps with a fake renderer for CI, or real if display available), assert state.
- Ensure the demo can be run after editable install and produces a visible window + running loop.
- **Layers touched**: All three (data model drives both logic and presentation; logic orchestrates; presentation produces the visible result). Separation is still honored because each layer only touches what it should.
- **Verification**: The milestone demo runs and looks correct. All prior unit tests still pass. ruff clean.
- **Why last**: This is the composition step. Previous chunks gave us independent, testable pieces.

### Optional Polish Chunk (if needed for "done")
- Basic error paths (e.g. bad GL context creation gives a clear exception).
- Ensure the loop can be paused/resumed and config changes (if we support live mutation) are reflected (e.g. clear color can be changed mid-run in a test).
- Update design docs / AGENTS if any new conventions emerged.
- Add a simple "frame counter" or FPS display in the demo (text via pygame font is acceptable for minimal; later this will move to proper text rendering in graphics).

## 4. Scaffolding & Codification That Happens Across Chunks

- **Module structure** (codified in Chunk 0 and enforced thereafter):
  - `src/grimoire2d/models/` — pure models + serialization boundary.
  - `src/grimoire2d/logic/` — loop, timing, engine host, config host.
  - `src/grimoire2d/presentation/` — window, renderer, GL encapsulation (start minimal).
  - `src/grimoire2d/__init__.py` — careful public surface only (version + the run() entrypoint once it exists).
  - Future: `assets/`, `input/`, etc. will follow the same pattern.
- **Imports**: Always explicit and namespace-clear. Users do `import grimoire2d as g2d`. Internal code uses `from grimoire2d.models.config import EngineConfig` or `import grimoire2d.logic.loop as loop`. No star imports. No dumping everything into the top namespace.
- **Tests**: 
  - Unit tests live next to the code they test or in `tests/unit/grimoire2d/...`.
  - Integration tests for anything involving pygame/GL/window.
  - Every chunk adds or updates tests. A chunk is not complete until tests pass and are green in CI (where applicable).
- **Other codification**: pyproject.toml becomes the single source for deps, scripts, tool config. Pre-commit or editor hooks encouraged but not mandatory for first milestone.

## 5. How This Honors Everything

- **Data model first** (0001): Chunks 1–2 deliver real data models before heavy logic or presentation.
- **Separation**: Each chunk is intentionally narrow (data only, then logic consuming data, then presentation reading data). The final integration proves the separation works end-to-end.
- **No half-measures**: The presentation code in Chunk 4 starts the correct encapsulation (AGENTS: "All GL state changes ... are encapsulated inside presentation/..."). The loop in Chunk 3 is the real managed loop, not a toy.
- **Scaffolding + tests + structure**: Done in Chunk 0 and reinforced in every subsequent chunk.
- **Small chunks**: One idea (packaging, first model, observation, loop logic, window, wiring).
- **User-facing early**: By Chunk 5 (or even late Chunk 4) there is a runnable demo that opens a window.
- **Future-proof**: The config data model and loop skeleton are the real ones (or direct ancestors) that will grow to support full runtime options, multiple world states, VFS-loaded level data, etc.
- **Engine patterns**: The loop API shape will feel Love2D-like. Timing and delta time are real.

## 6. Risks & Mitigations (Small-Chunk Philosophy Helps Here)

- GL context / window creation is platform finicky (especially macOS ARM, Wayland): Mitigate by making the window creation the *last* chunk before integration. Use a very thin wrapper and test the non-GL parts first.
- "Minimal renderer" might tempt shortcuts: AGENTS forbids this. The chunk will explicitly create the package structure even if the first implementation is only a clear + swap.
- Testability of window code: Some tests will be manual or marked integration. That's acceptable as long as the data + logic parts are unit-testable.
- Scope creep: The proposal explicitly lists what is out of scope for the milestone. Any feature that appears will be parked in a future chunk or new proposal.

## 7. Suggested Way to Proceed

1. Review / iterate on this proposal (and 0001) until we have consensus.
2. Update any cross-references (design-goals.md, README, AGENTS if new conventions appear).
3. Execute **one chunk at a time**. After each chunk:
   - Run full test suite + ruff.
   - Manually verify any demo.
   - Commit with clear message referencing the chunk.
4. After Chunk 5, we have the milestone. Then we can decide the *next* small milestone (e.g. "first sprite drawn from VFS data", "runtime options screen that actually changes the running config", "simple world state with a moving entity", "hot reload for config files", etc.).

This plan gives us a visible, working window + loop relatively quickly while building the foundation correctly instead of hacking a demo and refactoring later.

---

**End of Proposal 0002**

This is deliberately a *plan* document, not a big design. It respects the user's preference for small, focused chunks while ensuring we never violate the architectural rules we have already agreed upon. Once accepted, the first actionable step is usually Chunk 0 (scaffolding), because everything else depends on having the package structure and test harness in place.