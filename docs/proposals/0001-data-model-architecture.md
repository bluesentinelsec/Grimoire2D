# Proposal 0001: High-Level Data Model Architecture

**Status:** Proposed / Draft  
**Date:** 2026-06  
**Author:** Grok (based on user requirements)  
**Related Documents:**
- [docs/design-goals.md](../design-goals.md) — Architecture & Invariants section ("keeping data model, rules/logic, and views/rendering clearly separated"), "The game is just data", runtime configuration / options, professional persistence, VFS for configs and level data, hot reload for data, scene/gamestate management, SOLID/OCP for evolvability.
- [AGENTS.md](../../AGENTS.md) — Mandatory separation of data model / business rules / rendering/views for testability; "Data classes / simple value objects for the model"; "Configuration is explicit and runtime-mutable. Systems that care register interest or poll the current config snapshot."; "The Game Is Just Data" + VFS for all data; hot reload as first-class; composition and protocols; no magic; pure testable logic.

This proposal focuses **exclusively on high-level architecture**. No implementation details (no specific classes, no code, no library choices beyond what is already mandated, no file formats beyond "serializable via VFS").

---

## 1. Motivation and Problem Statement

Per the project charter and user direction, Grimoire2D must support a clean separation of concerns:

1. **Data Model** (pure state / "what is")
2. **Business Logic** / Rules (how state changes over time, "what happens")
3. **Presentation** / View (how state is observed and rendered, "what is shown")

This separation is explicitly called out as required for testability ("internals must support testing by keeping data model, rules/logic, and views/rendering clearly separated") and long-term evolution ("Partition the engine's data model, business logic/rules, and rendering/views so the system is easy to test, reason about, and evolve without heavy modification of old code").

Games inherently involve **multiple distinct data models**:

- **Engine / Cross-cutting Configuration** ("Game Options"): Video settings (resolution, fullscreen mode, vsync, scaling), Audio levels and devices, Input mappings and sensitivities, Gameplay toggles, etc. These must be **runtime mutable** (changeable from an in-game options screen without restart) and reachable in most contexts.
- **Simulation / World States**: The authoritative state(s) that drive game simulations. These govern positions, health, AI parameters, level progress, inventory, physics bodies (as data), etc. A single game may need **one or more** such states concurrently (e.g., active gameplay world, editor preview, client-side prediction in multiplayer, paused save state, replay buffer).

**The core challenge** (explicitly noted by the user): Data models are not fully known upfront. New features will reveal new data needs (new settings categories, new world concepts for a Diablo-like vs. a platformer, netcode sync requirements, tool-specific editor state, etc.). An architecture that hard-codes today's known models will become a maintenance burden and will violate OCP (Open/Closed Principle).

The architecture must therefore be **scalable** (handle many models, large state, high-frequency updates) and **adaptable** (evolve without rewriting core engine or breaking user saves / user-defined data / existing logic).

All of this must align with "the game is just data": normal content (including configs and level/world data) lives in the VFS. User code supplies only the unique logic.

## 2. Goals for the Data Model Architecture

The data model layer must deliver:

- **Purity and Separation**: Data models contain *only* data (values, structure, identity). Zero behavior that belongs in logic or presentation. This enables isolated unit testing of models, easy mocking, and clear boundaries.
- **Evolvability and Adaptability to the Unknown**: Mechanisms to introduce new data fields, entirely new model kinds, and new relationships over time. Support for schema evolution, user extensions, and graceful degradation/migration of old persisted data.
- **First-Class Serialization & Persistence**: Every data model must be serializable to a form that can be stored/loaded via the VFS (for built-in assets, levels, configs) and via professional persistence (user saves, high scores, cross-platform locations, JSON + binary-friendly formats).
- **Runtime Mutability with Control**: Especially for options/config — changes at runtime must be possible and observable by interested subsystems without tight coupling or global magic. World states are also mutable during simulation but under controlled rules.
- **Support for Multiplicity**: Easy creation, management, and isolation of multiple independent world/simulation states. Options are typically singleton-per-engine-instance but still versioned and swappable.
- **Hot-Reload Friendliness**: Data (especially config and level/world data files) must support live reload during development (Godot-like ergonomics) without corrupting live state or requiring full restarts. Reload must produce clean, versioned model instances.
- **Observability without Pollution**: Subsystems can react to data changes (e.g., video settings change → renderer must resize viewport) via explicit, narrow contracts (registration, polling snapshots, or events) rather than direct dependencies.
- **Testability in Isolation**: Pure data models + their serialization can be exercised in unit tests with no window, no OpenGL, no pygame, no physics library.
- **Performance Characteristics**: Lightweight in memory and CPU for hot paths (frequent simulation updates, frequent option queries). Support snapshots for history/rollback/networking without excessive copying. Aligns with "no allocations in hot paths after init (where practical)".
- **Explicitness and Traceability**: Data ownership is clear. There is one authoritative source for any given piece of state. Namespaces and module structure make it obvious where a model "lives."
- **Composition over Centralization**: Avoid a single "God Model" that accretes every feature. Favor composable, smaller models that can be assembled into larger world states.

Non-goals for *this proposal* (to be addressed in later architecture or implementation steps): exact on-disk formats, choice of serialization library, concrete shapes for any specific game feature (e.g., exact fields in a platformer WorldState), full ECS vs. other world representations.

## 3. High-Level Architecture

### 3.1 Foundational Principles

- **Data Models are Value-Oriented**: They are descriptions of state. Prefer value semantics (equality based on content, easy cloning/snapshotting) where practical. Use simple, transparent structures (the mandated "data classes / simple value objects").
- **Versioning is Mandatory**: Every model carries sufficient versioning information to support migration. Old saved data must be loadable (and upgradable) by newer engine versions.
- **Clear Ownership and Authority**: 
  - Engine-level options/config have a single owner (the core engine/config system).
  - Each simulation/world has its own authoritative state owner (a simulation manager, scene, or dedicated world object).
- **Snapshots vs. Authoritative Live State**: Distinguish read-only snapshots (for rendering, GUI, networking, saves, history) from the live mutable authoritative model (for simulation rules). This supports functional-style updates when desired and safe direct mutation when performance demands it.
- **Serialization is a Boundary, Not an Afterthought**: All models have a defined path to external representation. This boundary is what allows VFS, persistence, hot reload, and netcode to work uniformly.

### 3.2 Primary Categories of Data Models

The architecture recognizes (at minimum) these categories. New categories can be added later following the same patterns.

**Category A: Engine Configuration / Game Options Models**
- Purpose: Capture all runtime-configurable engine and cross-cutting settings.
- Examples of concerns (not exhaustive, and not a spec): video (mode, resolution, vsync, integer scaling, letterboxing), audio (master/ sfx / music volumes, spatial settings), input (key/mouse/gamepad bindings, deadzones, sensitivity), general gameplay (difficulty modifiers, etc.).
- Key properties:
  - Loaded early (with sensible defaults + user overrides from persisted storage).
  - Mutable at runtime from user-facing options screens (and programmatically).
  - Changes are observable by many mid-level subsystems (renderer, audio, input, etc.).
  - Persisted in user-writable, cross-platform locations (separate from VFS game archives).
  - Support for "apply" semantics (some changes may require confirmation or restart of subsystems).
- Relationship to other models: Options are usually independent of any specific world state but can influence how a world is simulated or presented (e.g., input map affects control logic).

**Category B: Simulation / World State Models**
- Purpose: Represent the complete (or partial) state of one running game simulation / world instance.
- Can be composed of many smaller domain models (see Category C).
- Key properties:
  - Multiple instances can exist simultaneously and independently (critical for editor tools, net play, replays, save previews, background simulations).
  - Governs the "simulation(s)" — updated by business logic each tick (using delta time, fixed timestep, etc.).
  - Must be serializable for saves, net sync, and potentially hot-reload of level data.
  - Contains both static-ish level data (references to loaded content) and highly dynamic per-frame state.
- The architecture does **not** prescribe a single representation (monolithic struct, entity list + component bags, scene graph, tilemap + actor list, etc.). Instead, it provides a container / composition model that different game genres and user code can specialize. This is the primary mechanism for adapting to unknown future requirements.

**Category C: Feature / Domain-Specific Data Models**
- Purpose: Reusable, composable pure data types for specific concerns (inventory contents, quest progress, dialogue state, particle emitter parameters as data, physics body descriptors (data side), etc.).
- These are the building blocks that get assembled into a WorldState or referenced by options.
- They are the most likely to grow in number and variety as features are added.
- Must be independently versionable and serializable.

**Category D: Persistence & Transport Wrappers**
- Higher-level envelopes: SaveGame (header + options snapshot + world snapshot(s) + metadata like timestamp, version, screenshot data if any), NetworkMessage payloads, Undo/Redo deltas, Replay frames.
- These wrap the core models and add cross-cutting concerns (versioning at the save level, checksums, compression hints).

### 3.3 Cross-Cutting Supporting Structures (Conceptual)

These are not "models" themselves but are required to make the data models usable at scale:

- **Model Versioning & Migration Layer**: A registry or strategy that knows how to take a serialized older representation of a model and produce a current-version instance (with defaults filled for new fields, or explicit migration transforms). This is the key to long-term adaptability and not breaking user saves.
- **Data Context / Model Host**: A container that holds the *live* authoritative instances of one or more data models. Responsibilities (high-level):
  - Owns the current options/config.
  - Owns (or coordinates) one or more active world/simulation states.
  - Provides uniform load/save entry points that go through VFS for asset data.
  - Exposes change observation for runtime-mutable models (especially options).
  - Coordinates with the hot-reload service so that when a data file on disk changes, the corresponding model instance(s) are refreshed cleanly.
- **Serialization Boundary**: A narrow, explicit interface for turning a pure data model into a portable form (dict-like for JSON, bytes for binary) and back. This boundary owns all knowledge of versions, field renaming, etc. Business logic and presentation never talk directly to the serialized form.
- **Observation / Notification Mechanism**: For models that are expected to change at runtime (options especially, and some world state in tools), interested parties can register interest or receive snapshots/events. Must be decoupled (no direct imports from data layer into every subsystem).
- **Snapshot & Cloning Facilities**: Ability to cheaply (or at least explicitly) produce immutable copies of (parts of) a model for rendering, GUI, networking, history, or rollback.

### 3.4 How the Pieces Relate (Conceptual Flow)

```
VFS (assets, level data, default configs)
  |
  v
Serialization Boundary  <--- HotReload service watches & triggers reloads
  |
  v
Data Context / Model Host
  +-- owns GameOptions (Category A)  --> observed by many subsystems
  +-- owns 0..N WorldStates (Category B)
        +-- composed of many Domain Models (Category C)
  |
  +-- provides snapshots / live views
  |
  +-- used by:
        - Business Logic / Rules (read current state, compute mutations or new states according to rules)
        - Presentation / Rendering / GUI (read-only queries for drawing, UI state)
        - Persistence (save/load user data via the same serialization path + platform save locations)
        - Netcode (serialization of world state deltas or full states)
```

- **Data models never contain** references to logic objects, renderers, physics simulators (as live objects), or GUI widgets.
- **Business logic** owns the *rules* that mutate or derive from data models. Logic can be pure functions (take data in, produce new data out) or stateful managers that operate on the models owned by the Data Context.
- **Presentation** reads data (often via snapshots or queries) and may maintain its own *derived / temporary* UI state, but never mutates the authoritative game data models except through well-defined channels (e.g., an options widget writes back to the options model via the host).
- The Engine / Core coordinates the Data Context with the game loop (update phase runs logic against current world state; render phase reads presentation data).

This structure directly supports the mandated three-way separation while allowing the data models themselves to evolve.

### 3.5 Adaptability Techniques (for Unknown Future Requirements)

To handle the reality that "you do not always know your data model early":

1. **Composition and Aggregation over Inheritance**: A WorldState is primarily an aggregator of other models rather than a giant class that subclasses or grows methods. New gameplay systems bring their own small data models and register them with the world.
2. **Extensible / Open Data**: Models can carry extension points (typed maps of additional named data, or a generic "user data" bag for game-specific extensions) so that user code and future engine features can attach data without modifying the core model definitions.
3. **Mandatory Versioning + Migration Registry**: Adding a field is a non-breaking change if a migration supplies a default. Removing/renaming is handled by migration code that runs on load. This is the primary defense against unknown future changes.
4. **Model Registry / Discovery**: A central (but extensible) place that maps type identifiers (or versioned names) to deserializers. User-defined models (for custom games or tools) can be registered.
5. **Snapshot / Delta Support**: For features like replays, netcode, editor undo, or save diffs, the architecture favors being able to produce and apply deltas on top of base models rather than assuming a fixed shape.
6. **Separation of Authoritative vs. Derived Data**: Only store what must be persisted or simulated. Derived values (e.g., "is the player visible to this enemy?") can be recomputed by logic or cached transiently in a way that doesn't pollute the core model.
7. **Protocol / Interface-based Extension**: Interested code depends on narrow protocols or views over the data rather than concrete shapes. This allows the concrete data to grow without breaking dependents (OCP).
8. **Data-Oriented Mindset**: Follow patterns proven in successful engines — keep data flat and accessible where possible; logic iterates over data collections rather than calling methods on rich objects.

These techniques together mean that when a new feature (e.g., a new "reputation" system for an RPG, or a new "photo mode" camera state for a tool) arrives, the data model layer can absorb it with localized additions and a migration, rather than a global refactor.

## 4. How This Fits the Broader Mandates

- **Layered Architecture (AGENTS + design-goals)**: Data models live at the "models" layer (in the `models/` package). They are owned by mid-level hosts (Data Context, owned by logic/engine). Business logic (another mid-level) and presentation consume them. Low-level escape hatches (raw GL, raw physics bodies) are *not* part of the pure data models.
- **VFS and "Game is Just Data"**: Config JSONs, level descriptions, and any other serializable world data are assets loaded exclusively through VFS. The data model layer provides the typed view over what VFS delivers.
- **Hot Reload**: The hot-reload coordinator (mandated) integrates directly with the Data Context / serialization boundary so data file changes result in updated model instances.
- **Runtime Configuration**: Explicitly modeled as first-class mutable data (Category A) with observation. Subsystems register interest rather than polling globals.
- **Professional Persistence**: The same serialization used for VFS assets is reused (with different storage backend) for user saves. Versioning + migration ensures long-term save compatibility.
- **Testability**: Because models are pure and have a serialization boundary, you can round-trip them, create test fixtures, assert on them, and test logic that operates on them with zero dependencies on graphics, audio, or windowing.
- **SOLID / OCP**: The versioning + registry + composition approach lets the engine be extended with new data without modifying existing model definitions or all the logic that consumes older versions.
- **Multiple Worlds / Simulations**: First-class support via multiplicity in the Data Context / host. This directly enables the "one or more world states that govern the game simulation(s)" requirement.
- **Performance & Shipping**: Snapshots, controlled mutability, and data-oriented design support the performance bar and PyInstaller / Steam Deck requirements.

## 5. Risks, Trade-offs, and Open Questions

(This section is intentionally part of the architecture proposal — these must be resolved before or during implementation of the data model layer.)

- **Granularity of Models**: How coarse vs. fine should individual data models be? (Too coarse → hard to hot-reload or migrate partially; too fine → explosion of types and ownership complexity.)
- **Mutation Model**: Pure functional updates (replace whole sub-models) vs. in-place mutation of live state vs. hybrid (immutable snapshots + mutable "dirty" views). Different answers may apply to options vs. high-frequency simulation state.
- **Notification Mechanism**: Callbacks, event objects, reactive streams, or simple "dirty flags + poll on next frame"? Must be lightweight and not introduce magic.
- **Multiplayer / Net Implications**: World state serialization must eventually support delta compression, partial updates, and client-side prediction data. The architecture should not make this impossible or require later invasive changes.
- **Editor / Tooling State**: Supplemental tools (e.g., level editors) will need their own data models (selection state, clipboard, undo stack). Should these live in the same data model system or a parallel one? (The dual-use GUI requirement suggests reuse where possible.)
- **Derived / Transient State**: Where does purely visual or temporary state live (e.g., current animation frame timers that are derived from a base "animation state" + time)? In the model (for simplicity of save/replay) or outside (for performance)?
- **Validation**: How much validation lives at the pure data model layer vs. in the business logic that mutates it?
- **Dependency on Other Mandated Systems**: The data model layer will depend on VFS for loading and on the hot-reload service. It must not create circular dependencies with the Engine core.

These are **not** to be solved by implementation hacks; they require deliberate architectural decisions (possibly in follow-on proposals or spikes).

## 6. Proposed Next Steps (After Acceptance)

1. Socialize / iterate on this proposal with feedback. Update design-goals.md and AGENTS.md with any new invariants that emerge.
2. Decide on the concrete placement in the source tree (likely something under `src/grimoire2d/` that makes namespaces clear, e.g., a `data` or `models` package that other subsystems can depend on without cycles). Follow the layout rules in AGENTS.md.
3. Implement the data model foundation in small, verifiable steps (as the user prefers modular progress):
   - First: the options / configuration data model category + serialization boundary + basic VFS round-trip + runtime mutation + observation.
   - Then: general model versioning + migration infrastructure.
   - Then: WorldState container + composition model (initially simple, to be specialized later).
   - Then: integration with hot reload and persistence.
4. Use the resulting data model layer as the foundation for the first real "hello world" loop, options screen scaffolding, and early simulation work.
5. Revisit and refine this proposal (or spawn child proposals) when concrete world simulation or netcode work begins.

---

**End of Proposal 0001**

This proposal provides a high-level, evolvable foundation for data models that directly supports the mandated separation of concerns, the "game is just data" philosophy, runtime configurability, hot reload, professional persistence, multiple simulations, and the reality of discovering data requirements incrementally. It deliberately stays at the architectural level so that subsequent small modular steps can implement against a stable vision rather than ad-hoc growth.