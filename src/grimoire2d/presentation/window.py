"""Presentation layer for window management + OpenGL rendering.

This module owns window creation (via pygame-ce) and the top-level
event loop for the current milestone. All OpenGL 3.30 core work is
delegated to the Renderer (which must never leak GL objects or calls
to the outside world).

Key behaviors implemented here:
- Resizable window (windowed mode) with live VIDEORESIZE handling.
- Virtual resolution (default 1280x720) is data-driven via EngineConfig
  extension and can be changed at runtime (demo keys, future options).
- Integer scaling + letterboxing (see logic.scaling.compute_viewport).
- Proper GL viewport + orthographic projection so all drawing uses
  virtual coordinates.
- Support for the existing dev/release + window mode policy (from PR3).
- Vendored shaders as Python string literals (see presentation/shaders.py).
"""

from __future__ import annotations

import pygame
import moderngl

from grimoire2d.models import (
    AppState,
    EngineConfig,
    VirtualResolution,
    WindowSettings,
    VideoSettings,
)
from grimoire2d.logic.window import get_effective_window_settings
from grimoire2d.logic.scaling import get_virtual_resolution
from grimoire2d.presentation.renderer import Renderer


def _get_system_resolution() -> tuple[int, int]:
    """Query the current display resolution."""
    info = pygame.display.Info()
    return info.current_w, info.current_h


def _compute_flags(mode: str, resizable: bool = True) -> int:
    """Map our mode string to pygame display flags."""
    if mode == "fullscreen_exclusive":
        return pygame.FULLSCREEN
    elif mode == "fullscreen_borderless":
        return pygame.FULLSCREEN | pygame.SCALED
    else:
        # windowed - resizable is the key for this milestone
        flags = pygame.RESIZABLE if resizable else 0
        return flags


def _set_gl_context_attributes() -> None:
    """Request a core 3.3 profile before set_mode.

    This must be called before the first pygame.display.set_mode that
    asks for OPENGL. Enforces the "OpenGL 3.30 core only" rule.
    """
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(
        pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE
    )
    # Double buffer is implied by DOUBLEBUF flag but we can be explicit
    pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)


def open_and_run(app_state: AppState | None = None) -> None:
    """Open a resizable (or fullscreen) window driven by the data models
    and run until quit.

    The window is always created with an OpenGL 3.30 core context.
    Virtual resolution (from the "virtual_resolution" extension) is the
    authoritative game coordinate space. The renderer + logic.scaling
    compute the letterboxed viewport on every resize and on virtual
    resolution changes.

    Demo keys (while the window has focus):
      ESC - quit
      1   - 640x360 virtual
      2   - 1280x720 virtual (default)
      3   - 1920x1080 virtual
      4   - 256x224 virtual (retro)

    Drag the window borders in windowed mode to see live integer-scaled
    letterboxing. The test pattern boxes keep their virtual size.
    """
    if app_state is None:
        app_state = AppState.default()

    effective = get_effective_window_settings(app_state.engine)
    virt = get_virtual_resolution(app_state.engine)

    pygame.init()
    _set_gl_context_attributes()

    width, height = effective.width, effective.height
    if width == 0 or height == 0:
        width, height = _get_system_resolution()

    flags = _compute_flags(effective.mode, resizable=(effective.mode == "windowed"))
    flags |= pygame.OPENGL | pygame.DOUBLEBUF

    pygame.display.set_mode((width, height), flags)
    title = app_state.engine.extensions.get("title")
    caption = title.value if title is not None else "Grimoire2D"
    pygame.display.set_caption(caption)

    # Video settings for vsync / clear color (best effort)
    video = app_state.engine.extensions.get("video")
    if video is None or not isinstance(video, VideoSettings):
        video = VideoSettings()
    try:
        pygame.display.set_vsync(1 if video.vsync else 0)
    except Exception:
        pass  # older pygame-ce or platform may not support

    ctx = moderngl.create_context()
    renderer = Renderer(ctx, initial_virtual=virt)
    renderer.set_clear_color(video.clear_color)

    # Track current physical size for the data-driven path
    current_phys = (width, height)
    renderer.handle_physical_resize(*current_phys)

    running = True
    clock = pygame.time.Clock()

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                else:
                    # Runtime virtual resolution changes (data driven)
                    new_virt = None
                    if event.key == pygame.K_1:
                        new_virt = VirtualResolution(width=640, height=360)
                    elif event.key == pygame.K_2:
                        new_virt = VirtualResolution(width=1280, height=720)
                    elif event.key == pygame.K_3:
                        new_virt = VirtualResolution(width=1920, height=1080)
                    elif event.key == pygame.K_4:
                        new_virt = VirtualResolution(width=256, height=224)

                    if new_virt is not None:
                        # Mutate the engine config (extensions bag) - pure data
                        new_engine = app_state.engine.with_updates(
                            extensions={"virtual_resolution": new_virt}
                        )
                        app_state = app_state.with_updates(engine=new_engine)
                        renderer.set_virtual_resolution(new_virt)

            elif event.type == pygame.VIDEORESIZE:
                # Live resize with proper scaling + letterboxing
                new_w, new_h = event.size
                current_phys = (new_w, new_h)
                renderer.handle_physical_resize(new_w, new_h)

        # Re-read authoritative virtual every frame (supports external
        # changes to the data model, hot reload, options, etc.)
        current_virt = get_virtual_resolution(app_state.engine)
        renderer.set_virtual_resolution(current_virt)

        # Also refresh clear color if it changed in the model
        video = app_state.engine.extensions.get("video")
        if isinstance(video, VideoSettings):
            renderer.set_clear_color(video.clear_color)

        renderer.prepare_frame()
        renderer.draw_virtual_border()
        renderer.draw_test_pattern()
        renderer.present()

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


def open_window_with_config(engine_config: EngineConfig) -> None:
    """Convenience for using just the engine config (for early testing)."""
    app_state = AppState(engine=engine_config)
    open_and_run(app_state)
