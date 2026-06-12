"""Business logic / rules for window configuration.

This layer takes data models and produces effective window settings
for initial creation and runtime changes.

It encodes the professional-grade behavior:
- Release builds: fullscreen exclusive, system resolution.
- Dev builds: windowed and maximized, system resolution.

The actual window creation and mode application is the responsibility
of the presentation layer. This layer only decides "what" based on the data.
"""

from __future__ import annotations

from dataclasses import replace

from grimoire2d.models import EngineConfig, WindowSettings, BuildConfig


def get_effective_window_settings(engine_config: EngineConfig) -> WindowSettings:
    """Compute the effective window settings based on the current config.

    This rule applies the dev/release policy on top of the configured mode
    and resolution.

    If resolution is 0 in the settings, it means "use system's current"
    (the presentation layer is responsible for querying the actual value
    at open time).
    """
    window = engine_config.extensions.get("window")
    if window is None or not isinstance(window, WindowSettings):
        window = WindowSettings()

    build = engine_config.extensions.get("build")
    if build is None or not isinstance(build, BuildConfig):
        build = BuildConfig()

    if build.mode == "release":
        return replace(
            window,
            mode="fullscreen_exclusive",
            maximized=False,
            # width/height 0 means system current
        )
    else:
        # dev build
        return replace(
            window,
            mode="windowed",
            maximized=True,
            # width/height 0 means system current
        )


def apply_runtime_mode_change(
    current_config: EngineConfig, new_mode: str
) -> EngineConfig:
    """Produce an updated config with a runtime window mode change.

    This is the data transformation for runtime mode switches (e.g. from
    options screen or hotkey). The presentation layer can react to the
    updated config by re-applying the window mode.
    """
    window = current_config.extensions.get("window")
    if window is None or not isinstance(window, WindowSettings):
        window = WindowSettings()

    updated_window = replace(window, mode=new_mode)
    new_extensions = dict(current_config.extensions)
    new_extensions["window"] = updated_window

    return replace(current_config, extensions=new_extensions)
