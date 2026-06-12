"""Minimal demo to achieve the short-term goal: display a game window
that runs until the user presses ESC.

This demonstrates the current data model + logic + minimal presentation
layers working together.

Usage:
    python -m demos.minimal_window

The window will open according to the build mode in the data model
(dev = windowed maximized, release = fullscreen exclusive), using
the system's current resolution.

Press ESC or close the window to exit.
"""

import sys
from pathlib import Path

# Allow running without install
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.models import AppState, EngineConfig, BuildConfig, WindowSettings
from grimoire2d.logic.window import get_effective_window_settings
from grimoire2d.presentation.window import open_and_run


def main() -> None:
    # Build the data model for a minimal app.
    # For demo purposes we explicitly set build mode here.
    # In a real game this would come from command line, env, or config file.
    build = BuildConfig(mode="dev")  # Change to "release" to test fullscreen exclusive

    # Initial window settings (resolution 0 = system current)
    window = WindowSettings(mode="windowed", width=0, height=0, maximized=True)

    engine = EngineConfig.default()
    # Inject our demo settings into the extensions (this is how runtime
    # configuration would work too).
    engine = engine.with_updates(
        extensions={
            "build": build,
            "window": window,
        }
    )

    app_state = AppState(engine=engine)

    # The logic layer computes the *effective* settings (applies dev/release policy).
    effective = get_effective_window_settings(app_state.engine)
    print(f"Effective window mode for this run: {effective.mode}")
    print(f"Resolution (0 = system current): {effective.width}x{effective.height}")
    print("Press ESC or close the window to exit.")

    # Presentation layer opens the window and runs the loop.
    # It consumes the data models.
    open_and_run(app_state)


if __name__ == "__main__":
    main()
