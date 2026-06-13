"""Minimal demo: resizable window + data-driven virtual resolution
with integer scaling and letterboxing.

This is the first visible demonstration of the professional windowing
contract:
- Default virtual (game) resolution is 1280x720 (changeable at runtime).
- The OS window can be any size (drag to resize).
- The renderer uses integer scaling + letterboxing so game content
  stays the correct aspect and crisp (when integer_scaling=True).
- All drawing happens in virtual coordinates; the viewport + projection
  do the mapping.

Usage:
    python -m demos.minimal_window

Keys (window must have focus):
    ESC - quit
    1   - switch to 640x360 virtual
    2   - 1280x720 (the default)
    3   - 1920x1080
    4   - 256x224 (classic 8:7-ish retro)

Drag any window edge in windowed mode. Watch the yellow border and
colored test rects stay the same size in *game units* while letterbox
bars appear/disappear.

Change the BuildConfig to "release" to start in fullscreen_exclusive
(virtual resolution + letterboxing still apply inside the display res).
"""

import sys
from pathlib import Path

# Allow running without install
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.models import (
    AppState,
    EngineConfig,
    BuildConfig,
    WindowSettings,
    VirtualResolution,
)
from grimoire2d.logic.window import get_effective_window_settings
from grimoire2d.presentation.window import open_and_run


def main() -> None:
    # Build the data model for a minimal app.
    # Virtual resolution is the key new piece for this milestone.
    build = BuildConfig(mode="dev")

    # Initial window settings (0 = let the system / dev policy decide)
    window = WindowSettings(mode="windowed", width=0, height=0, maximized=True)

    # Explicit virtual resolution (the default is already 1280x720, but
    # we show it here so it is obvious this is data and can be changed).
    virt = VirtualResolution(width=1280, height=720, integer_scaling=True)

    engine = EngineConfig.default()
    engine = engine.with_updates(
        extensions={
            "build": build,
            "window": window,
            "virtual_resolution": virt,
        }
    )

    app_state = AppState(engine=engine)

    effective = get_effective_window_settings(app_state.engine)
    print(f"Effective window mode for this run: {effective.mode}")
    print(f"Physical request (0 = system): {effective.width}x{effective.height}")
    print(f"Virtual resolution (data driven): {virt.width}x{virt.height}")
    print("Drag window borders to resize. Letterboxing + integer scaling update live.")
    print("Press 1/2/3/4 to change virtual resolution at runtime (ESC to quit).")

    open_and_run(app_state)


if __name__ == "__main__":
    main()
