# AGENTS.md — Grimoire2D Architectural and Coding Rules

**This file is the primary source of truth for how to write, structure, and evolve code in this repository.** It takes precedence over all other instructions when working in the Grimoire2D codebase.

All AI agents, contributors, and future work **must** follow these rules strictly. Violations (hacks, shortcuts, architectural debt) are not acceptable.

## 1. Core Mandate (from design-goals.md)

Grimoire2D is a **professional-grade**, opinionated 2D game framework. The philosophy is **"the game is just data"**:

- The engine correctly and performantly abstracts everything 99% of 2D games need.
- User code + media assets (via VFS) provide only what is unique.
- It must support shipping commercial games on Steam (Windows AMD64, Linux AMD64, macOS ARM) via clean `pip install grimoire2d` + PyInstaller.

**Non-negotiable qualities**:
- Architecturally correct at every layer. No quick fixes, no deferred bugs, no hacks, no half-measures, no "we'll clean it up later".
- Explicit, transparent, traceable. Maximize namespace clarity. Only one obvious way to do things.
- Follow single responsibility principle, and open and closed principle rigorously. Partition data model / rules / rendering/views for testability and evolution.
- Functions, methods, and source files should be short in length. Smaller is better.
- Self-documenting code. Small, well-named functions. Long-lived comments only.
- Layered architecture with clear, documented escape hatches.
- Data-driven: assets/config live in the VFS (zip + optional simple obfuscation), not hardcoded in Python.
- Follow **known successful patterns from video game engines** (Love2D callback/resource model, Godot hot-reload ergonomics, proper batching/shader pipelines from modern 2D renderers, etc.). Do not reinvent poorly.

If a design decision would require a hack to make progress, **stop and redesign the abstraction properly** before writing the code.

If bugs are encountered, fix them, do not defer them.


## 3. Architectural Rules (Strict — No Exceptions)

### Layering (Visible and Enforced)
1. **High-level**: The "Love2D-like" surface most users (and tool authors) touch (`g2d.run()`, `g2d.graphics.draw_sprite(...)`, simple config, scene manager). Immediate-mode *feel*.
2. **Mid-level**: Subsystem managers (Camera, Batch, VFS, LightingSystem, PhysicsWorld, SceneStack, HotReloadCoordinator, etc.). Tooling UI is provided by Dear PyGui (external, see demos/).
3. **Low-level / Escape Hatches**: Raw pygame-ce surfaces/events (rare), GL objects (VAO/VBO/program via explicit path), pymunk bodies, etc. These must be obvious and not require fighting the framework.

Internals **must** keep data model, business rules/logic, and rendering/views separated so tests can target the first two without a window/GL.

The Engine (core) owns/co-ordinates subsystems. Subsystems do **not** import the Engine circularly; use dependency injection (pass what they need at construction or via protocols) or a narrow, well-defined context object.

### "The Game Is Just Data" + VFS
- **Every** asset load (textures, shaders, sounds, fonts, level data, config JSON, even internal defaults if any) **must** go through `grimoire2d.assets.vfs`.
- Dev mode: VFS can overlay real filesystem for instant hot-reload without repacking.
- Prod: Load exclusively from a single (optionally obfuscated) zip archive. Obfuscation = simple symmetric cipher only (casual protection).
- User games point at their archive or folder; engine abstracts the rest.
- Hot reload is a first-class, always-on (in dev) service. Resources are handles or versioned objects that can be invalidated/replaced without breaking user references (use indirection, callbacks, or weak observers — design it properly).

### Rendering (Non-Negotiable)
- **Day one and forever**: OpenGL 3.30 core profile only. No legacy paths, no `pygame.Surface.blit` in the hot path, no software fallbacks for primary content.
- Batching is **mandatory** for performance. The public API must never expose the caller to "you must batch yourself".
- All GL state changes, VAO/VBO/UBO/Texture binding, shader use, etc. are encapsulated inside `presentation/renderer.py` + `presentation/gl/` or equivalent. Other modules (particles, lighting, debug overlays, in-game HUD drawing) **must** go through the batcher/renderer API. Professional editor UIs live in separate processes using Dear PyGui and only cross into engine rendering for viewport previews via textures.
- Shaders: First-class. Support both embedded strings (Raylib-style) and files. Compilation errors must be excellent. Hot reload must recompile and swap atomically where possible.
- Lighting/fog/post: Designed as part of the pipeline from the beginning (not bolted on). Support arbitrary lights via culling + batching/GPU upload (no hard-coded light counts in shaders). GPU particles required.
- Resolution independence: integer scaling + letterboxing is the model. Camera + viewport handled centrally.
- The renderer owns the main framebuffer(s) and post chain.

If you ever feel the need to call `gl*` or `moderngl` directly from outside presentation/, you are violating the architecture. Create the proper abstraction instead.

### Explicitness & No Magic
- No hidden globals that magically affect behavior (except the single active Engine instance during a `run()`, and even that must be explicit).
- No decorators that hide control flow or registration (unless the decorator is the *only* public API and its effect is trivial and documented in one place).
- No monkey-patching. No `if TYPE_CHECKING` hacks to break import cycles — fix the cycle by proper layering.
- Configuration is explicit and runtime-mutable. Systems that care register interest or poll the current config snapshot.
- Namespaces: `from grimoire2d.presentation import Camera` or `import grimoire2d.presentation as pres`. Avoid dumping everything into the top `grimoire2d` namespace except the absolute minimum (run, App, version, etc.).
- Prefer composition and protocols (PEP 544) over deep inheritance for extension points.
- For data models specifically: EngineConfig contains *literally nothing* except `version` and an `extensions: dict[str, DataModel]`. All configuration (common or game-specific) is delivered exclusively through registered extensions.
  - Goal: PRs should be *exclusively* net-new code (maximum OCP).
  - Adding anything = create new *Setting model + one register_extension() call (never touches EngineConfig.py again).
  - Games compose via their own models (e.g. MyGameConfig(engine=..., custom=...)).
  - See models/config.py docstring for the exact process.

### SOLID + Testability
- Every class/module has a single, clear responsibility.
- Open for extension, closed for modification: new features (new light type, new widget, new post effect) are added by new code, not by editing core switch statements.
- Data classes / simple value objects for the model.
- Business rules (collision response, input mapping, scene transitions, lighting culling) are testable in isolation.
- Rendering code is the hardest to test — isolate the pure logic (culling, batch sorting, shader param calculation) and test that. Use integration tests + the classic game demos for the GL parts.

### Performance & Correctness
- Hot paths (per-frame update/draw of thousands of sprites + lights + particles) must be designed for performance from the start. Measure, don't guess. (GUI for tools is not on the game hot path.)
- Delegate to C where it matters (pygame-ce, OpenGL, pymunk).
- No allocations in hot paths after init (where practical). Use object pools or pre-allocated buffers for particles, batches, etc. when it makes a difference.
- Steam Deck (original) capability via opt-in performance modes/profiles. These are first-class, not afterthoughts.
- Input: favor buffered/real-time polling for responsiveness.

### Error Handling & Invariants
- Fail fast, openly, and transparently
- Errors should present to both console and GUI
- Define and use specific exceptions in `grimoire2d.exceptions`.
- Fail fast and loud on programmer errors / bad data in dev. Good error messages with hints.
- In production paths, still validate critical invariants but don't crash the player's game on recoverable asset issues (graceful fallback + log).
- Asserts / debug checks for architectural invariants (e.g. "batch is flushed before state change").
- Never swallow exceptions with bare `except:` or `except Exception:`.

### Hot Reload, Dev Ergonomics
- Emulate Godot: edit Python, shader, texture, data → see change with minimal friction while the game is running.
- The hot-reload coordinator must be a proper service that subsystems (graphics, assets, scene, etc.) register with. Tool processes using Dear PyGui can opt into asset hot-reload via the same VFS mechanisms.
- Code reload: module re-import with care for state (document the supported patterns; avoid complex global state that can't be reloaded).
- Resource reload: transparent replacement of handles.

## 4. Coding Standards (Enforced)

- **Python version**: Target the stable version that works best with PyInstaller on the three platforms. Use modern syntax where safe.
- **Formatting/Linting**: ruff (format + lint) is the law. Run it. Pre-commit or editor integration expected. No style debates in PRs.
- **Type hints**: Use them. `from __future__ import annotations`. mypy is encouraged for new code (strictness level decided in pyproject).
- **Docstrings**: Every public (and most internal) function, class, and module gets a docstring describing purpose, parameters, returns, important side-effects, invariants, and when it is safe to call. NumPy or Google style — be consistent.
- **Function size**: Small. If a function does two things, split it. SRP applies to functions too.
- **Comments**: Only for *why* (architectural decisions, non-obvious tradeoffs, engine patterns being followed). Never for "what" if the code + name already say it. No tactical "fix for issue #123" comments that rot.
- **Imports**: Absolute within the package. Group stdlib, third-party, local. Use `import grimoire2d.presentation as presentation` style inside the lib for clarity.
- **No print, no pdb in library code**. Use `logging.getLogger(__name__)` with proper levels.
- **Mutable vs immutable**: Document the contract. Positions/velocities in games are typically mutated in place for perf — provide clear `copy()` / immutable views when needed.
- **Third-party deps**: Only mature, stable, performant, minimal-transitive-dep libraries. Pin versions in pyproject.toml. Never GPL/AGPL that would infect user games. pygame-ce is blessed. pymunk (or evaluated alternative) for physics. Minimal else.
- **Packaging**: The library **must** remain PyInstaller-friendly. Clean separation between runtime code and build-time. No heavy compile steps for end users of the lib.

## 5. Subsystem-Specific Guidelines

- **Core / Loop**: Fixed/variable timestep options. Delta time everywhere for logic. Configurable max FPS. Proper pause. Runtime config changes (resolution, fullscreen, audio) must propagate correctly without leaks or lost state.
- **Presentation/Renderer**: One canonical way to draw. Everything funnels through batch + current camera + current shader state managed by the renderer. Lighting and post are not "add-ons". (The top-level package for this is `presentation/`.)
- **Assets/VFS**: The single source of truth. Loaders are thin adapters on top of VFS + format-specific parsing. Hot reload protocol is part of the contract for any reloadable resource.
- **GUI for tools**: Delegated to Dear PyGui (or equivalent mature external library). The engine does not implement or maintain widgets, focus systems, or layout engines for editors. In-game HUDs use the low-level Renderer drawing primitives. Tools that need live game previews integrate via texture export from the Renderer.
- **Physics**: Thin wrapper. Do not re-implement broad/narrow phase. Provide debug draw that uses the graphics system. Bodies/queries exposed cleanly.
- **Math**: Keep it small and fast. No numpy in the default path. Vec ops must be ergonomic (`v += other`, `v * 2`, etc.).
- **Scene Management**: Stack-based with transitions. Common screens (options, loading) have easy patterns but are not forced on the user.
- **Net**: Direct sockets, client/server model. Keep it out of the main hot path as much as possible. Message serialization must be explicit and versioned.

When a new concern appears (e.g. achievements, Steam integration), treat it as a new mid-level subsystem with the same layering rules.

## 6. Testing (Non-Negotiable)

- Every module that contains logic or rules gets unit tests (pure Python, no window required).
- Example games in `demos/` (and `tools/`) are integration tests. They must run cleanly and are used in CI.
- CI **must** execute the full test suite on Windows, macOS, and Linux (as per design-goals).
- Graphics-heavy code: test the pure parts (math, culling logic, batch construction, shader param prep, VFS path resolution). Use headless or mocked contexts where possible for CI. Full GL tests run on dev machines + via the demo games.
- Property-based testing (hypothesis) is encouraged for math, collision queries, config round-tripping, etc.
- When you change behavior, update or add tests **first** (or at the same time). Never leave tests broken.
- If a test is hard to write because of the design, the design has a problem. Fix the design.

## 7. What You Must NEVER Do (Zero Tolerance)

- Quick fixes / workarounds that paper over a deeper architectural issue.
- "TODO: fix later" or "HACK:" comments that stay in the tree.
- Deferring correctness (e.g. "we'll add proper resource lifetime management after we ship the first demo").
- Global mutable state that is not the single documented Engine instance (and even then, keep its surface tiny).
- Leaking GL state, pygame state, or physics state between unrelated systems.
- Bypassing the VFS for any asset.
- Raw GL calls outside the presentation subsystem.
- Magic that makes "only one way" impossible to discover by reading the module structure.
- Adding a feature by editing a giant `if` or `match` in core code instead of extending via new classes / registration / composition.
- Writing code without considering hot-reload, PyInstaller, the three platforms, and testability.
- Using heavy deps (numpy, etc.) for core paths when the charter calls for lightweight.
- Implementing custom physics, 3D, visual scripting, or hosted multiplayer services.
- Treating the supplemental editor/tools as "inside" the core library package.

If you are about to do any of the above, **you must stop**, document the tension in a design note or by updating design-goals.md + this file, and choose the correct path.

## 8. Process When Working on Code

1. Read (or re-read) `docs/design-goals.md` and this `AGENTS.md` before touching any source.
2. Understand the layering and which subsystem owns the concern.
3. Design the abstraction first (on paper or in comments). Make sure it is SRP, testable, explicit, and follows engine patterns.
4. Implement the minimal correct slice that satisfies the invariants.
5. Add / update tests that would have caught a regression.
6. Run the full relevant test suite (unit + any affected demos).
7. Run ruff format + lint.
8. Verify the change does not introduce circular imports, hidden state, or bypasses of VFS/renderer/etc.
9. If the change affects public API, hot-reload contract, packaging, or performance bar, update design-goals.md and this file.
10. Only then consider the work done. Half-measures are not "done".

For spikes/prototypes: they may live in a `spikes/` or `demos/` temporarily, but anything that graduates into `src/grimoire2d/` must be brought up to the standards in this file with no debt left behind.

## 9. Packaging, Distribution & CI Notes

- `pyproject.toml` is the single source for dependencies, entry points, package data (include shader defaults? default skins?).
- The package must be importable and functional after `pip install grimoire2d` and after PyInstaller bundling on all three platforms.
- CI runs tests on all three OSes. GL context creation must be robust (or tests that require a real window are marked appropriately and still exercised in demos).
- Versioning follows semantic versioning. `__version__` in `grimoire2d/__init__.py`.

## 10. When in Doubt (from design-goals.md + this file)

Prefer:
- Explicitness and architectural cleanliness (SOLID, no magic).
- "The game is just data" + professional shipping capability.
- High-quality 2D lighting/fog/particles as a visual differentiator (GPU where specified).
- A pip-installable, PyInstaller-friendly core library.
- Full CI coverage on Windows + macOS + Linux.
- Follow known successful patterns in video game engines.
- Small functions, clear namespaces, proper layering.
- Fix the root cause / redesign rather than hack.

This is not a suggestion list. It is the filter through which every line of code must pass.

---

**End of AGENTS.md**

The existence of this file means "we tried to be careful" is no longer an excuse. The code either meets these standards or it does not belong in the tree.

When the design-goals.md is updated, re-read it and consider whether this AGENTS.md also needs tightening.
