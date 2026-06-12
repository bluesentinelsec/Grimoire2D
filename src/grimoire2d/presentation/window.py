"""Presentation layer for window management.

This is a minimal implementation to achieve the short-term goal of
displaying a game window that runs until ESC is pressed.

It consumes the data models (via AppState or EngineConfig) and the
effective settings computed by the logic layer.

The actual window creation uses pygame (the base for the engine;
OpenGL integration comes later).

Runtime mode changes are supported by re-computing effective settings
and re-applying (re-creating the display surface).

Note: "maximized" for windowed mode is approximated by opening at
system resolution; true OS-level maximize is platform-specific and
can be added later without changing the data model.
"""

from __future__ import annotations

import pygame

from grimoire2d.models import AppState, EngineConfig, WindowSettings
from grimoire2d.logic.window import get_effective_window_settings


def _get_system_resolution() -> tuple[int, int]:
    """Query the current display resolution."""
    info = pygame.display.Info()
    return info.current_w, info.current_h


def _compute_flags(mode: str) -> int:
    """Map our mode string to pygame display flags."""
    if mode == "fullscreen_exclusive":
        return pygame.FULLSCREEN
    elif mode == "fullscreen_borderless":
        # Common way to get borderless fullscreen window
        return pygame.FULLSCREEN | pygame.SCALED
    else:
        # windowed
        return pygame.RESIZABLE


def open_and_run(app_state: AppState | None = None) -> None:
    """Open a window based on the provided (or default) app state and run
    until the user requests quit (ESC or window close).

    This is the minimal implementation for the short-term goal.
    It demonstrates consuming the data model layer.
    """
    if app_state is None:
        app_state = AppState.default()

    # Get effective settings from logic (this encodes dev/release policy)
    effective = get_effective_window_settings(app_state.engine)

    pygame.init()

    width, height = effective.width, effective.height
    if width == 0 or height == 0:
        width, height = _get_system_resolution()

    flags = _compute_flags(effective.mode)

    screen = pygame.display.set_mode((width, height), flags)
    pygame.display.set_caption(app_state.engine.extensions.get("title", type("obj", (object,), {"value": "Grimoire2D"})()).value)

    running = True
    clock = pygame.time.Clock()

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        # Minimal "render" - clear the screen
        screen.fill((0, 0, 0))
        pygame.display.flip()

        clock.tick(60)  # basic rate

    pygame.quit()


def open_window_with_config(engine_config: EngineConfig) -> None:
    """Convenience for using just the engine config (for early testing)."""
    app_state = AppState(engine=engine_config)
    open_and_run(app_state)
