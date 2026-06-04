# Proposal 0003: Chunk 0 - Project Scaffolding

**Status:** Proposed  
**Date:** 2026-06  
**Related:** 0001 (data models first), 0002 (incremental plan to minimal loop), design-goals.md (separation of data model / logic / presentation, src/ layout per AGENTS.md), AGENTS.md (structure must scale and remain intuitive).

## Goal
Create the minimal, correct foundation so we can `pip install -e .`, import the package cleanly, run stdlib tests, and have a scalable home for all future code (data models, loop logic, graphics, etc.).

## Proposed Structure (intuitive + scalable)

```
Grimoire2D/
├── LICENSE
├── README.md          # untouched (stays TBD)
├── .gitignore
├── pyproject.toml     # packaging only (PEP 621 + build)
├── docs/
│   └── proposals/
│       └── 0003-...
├── src/
│   └── grimoire2d/    # the importable library (never run from here directly)
│       ├── __init__.py
│       ├── models/    # data model layer (pure value objects, per 0001)
│       │   └── __init__.py
│       ├── logic/     # business logic layer (loop, timing, engine host)
│       │   └── __init__.py
│       └── presentation/  # presentation / front-end layer (window, renderer)
│           └── __init__.py
├── tests/             # stdlib unittest only (outside the package)
│   └── test_import.py
└── demos/             # user examples / integration (outside the package, will scale)
    └── (empty for now)
```

## Why this structure?

- **Intuitive**: Obvious mapping from high-level architecture (models/ for data models, logic/ for business logic, presentation/ for front-end/view). Library vs. "user stuff" is crystal clear (src/ vs. tests/demos at root). New developers immediately see where to add the next concern. The directory names make the data-model / logic / presentation separation explicit and obvious.

- **Standard library facilities only (no third-party tooling)**:
  - Packaging: `pyproject.toml` (standard PEP) + `setuptools` as build backend (the conventional, minimal way; no poetry, flit, hatch, pdm, etc.).
  - Version: `importlib.metadata` (stdlib since 3.8).
  - Testing: `unittest` module + `python -m unittest` (stdlib). No pytest, no coverage, no tox.
  - No dev dependencies, no linters, no type checkers, no pre-commit declared or required at this time. Tools can be used ad-hoc by the developer or added in a future chunk.
  - No runtime dependencies yet (pygame-ce will appear only when Chunk 4/5 needs a window).

- **Scales with time and additional work**:
  - `src/` layout is the recommended modern standard for Python packages. It prevents import side-effects, works cleanly with editable installs and PyInstaller, and grows without pain (add `assets/`, `input/`, `gui/`, `math/`, `net/`, `persistence/` etc. as natural siblings).
  - Subpackage split (models/logic/presentation) directly mirrors the data-model / logic / presentation separation we want. Each can grow independently into multiple modules without the top level becoming a mess.
  - `demos/` and `tests/` live outside the installed package forever — they can contain hundreds of files later without affecting `pip install grimoire2d` or namespace pollution.
  - `pyproject.toml` starts minimal and can later accept `[project.optional-dependencies]`, `scripts`, `readme`, classifiers, etc. with zero directory moves.
  - Ready for "the game is just data" (models/ package is the obvious home for all pure models, configs, world states) and for the full engine (logic/ will own the loop that coordinates models + views).

This is the smallest possible correct skeleton that lets us begin Chunk 1 (first data model) immediately while guaranteeing the structure will not have to be refactored in 6 months or 2 years.

## What "done" for this chunk looks like
- `pip install -e .` succeeds and `import grimoire2d as g2d; print(g2d.__version__)` works.
- `python -m unittest discover -s tests` runs and passes (using only stdlib; the test file uses a tiny stdlib pathlib+sys.path adjustment so it works before or after `pip install -e .`).
- The three starting subpackages (models/, logic/, presentation/) exist with small `__init__.py` files containing only docstrings (ready for 0001-style data models in models/; keeps them importable and documented from day one).
- No changes to README.md.
- No third-party dev tools or runtime deps introduced.

All subsequent chunks will live inside this skeleton.

## Implementation notes for this chunk
- pyproject.toml uses a static version and setuptools (standard, minimal).
- src/grimoire2d/__init__.py uses only `importlib.metadata` (stdlib) for version.
- tests/test_import.py uses only `unittest` + `pathlib` + `sys` (no third-party).
- Subpackage __init__.py files (models/, logic/, presentation/) contain only module docstrings (no code yet).
- No changes were made to README.md.
- Structure matches the "intuitive + scalable" goals and directly enables starting Chunk 1 (first data model in models/) immediately.