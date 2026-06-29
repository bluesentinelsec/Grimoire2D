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

GameWindow
----------
For game code that should not care about the underlying display hardware,
use ``GameWindow``.  The caller specifies a virtual resolution and draws in
that coordinate space; the engine handles HiDPI, letterboxing, centering,
and resize events transparently::

    win = GameWindow("My Game", virtual_width=1280, virtual_height=720)
    while win.is_open:
        for event in win.poll():
            if event.type == pygame.QUIT:
                win.close()
        dt = win.begin_frame()
        win.renderer.draw_circle(640, 360, 80, (1.0, 0.4, 0.1, 1.0))
        win.end_frame()
    win.quit()
"""

from __future__ import annotations


import pygame
import moderngl

from grimoire2d.models import (
    AppState,
    EngineConfig,
    VirtualResolution,
    VideoSettings,
)
from grimoire2d.logic.window import get_effective_window_settings
from grimoire2d.logic.scaling import Viewport, get_virtual_resolution
from grimoire2d.presentation.highdpi import enable_highdpi, get_drawable_size
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
    The forward-compatible flag is required on macOS to get a 3.3 core
    context (without it the driver silently falls back to 2.1).
    """
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(
        pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE
    )
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_FORWARD_COMPATIBLE_FLAG, True)
    # Double buffer is implied by DOUBLEBUF flag but we can be explicit
    pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)


class GameWindow:
    """Turn-key pygame + OpenGL 3.3 window with automatic virtual-resolution scaling.

    The engine handles everything the caller should not have to think about:

    * HiDPI detection and correct drawable-pixel calculation
    * OpenGL 3.3 core profile initialization (including the macOS forward-compat flag)
    * Resizable window: on every ``VIDEORESIZE`` event the letterbox/pillarbox is
      recomputed so the virtual content stays centered in the window
    * Blend state and per-frame GL setup

    Game code works entirely in the fixed virtual coordinate space
    ``(0 .. virtual_width, 0 .. virtual_height)``.  The engine scales that
    space to fill as much of the physical window as possible while preserving
    the aspect ratio, with letterbox/pillarbox bars filling the remainder.

    For crisp text in the in-house GUI (or text primitives), supply a high
    quality TTF via ``font_path`` or (preferred for embedding/VFS) ``font_bytes``
    loaded e.g. via ``vfs.read_bytes("fonts/serif.ttf")``.

    Typical usage::

        win = GameWindow("My Game", virtual_width=1280, virtual_height=720)
        while win.is_open:
            for event in win.poll():
                if event.type == pygame.QUIT:
                    win.close()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    win.close()
            dt = win.begin_frame()
            win.renderer.draw_circle(640, 360, 80, (1.0, 0.4, 0.1, 1.0))
            win.end_frame()
        win.quit()
    """

    def __init__(
        self,
        title: str = "Grimoire 2D",
        virtual_width: int = 1280,
        virtual_height: int = 720,
        target_fps: int = 60,
        bar_color: tuple[int, int, int, int] = (0, 0, 0, 255),
        *,
        font_path: str | None = None,
        font_bytes: bytes | None = None,
        render_scale: float = 1.0,
    ) -> None:
        # HiDPI hints must be set before pygame.init().
        enable_highdpi()
        pygame.init()
        pygame.font.init()
        _set_gl_context_attributes()

        # Choose a reasonable initial logical window size (around 1.5x virtual).
        # Avoid full desktop to prevent decoration/titlebar mismatches on macOS etc.
        # The user can immediately resize; VIDEORESIZE will handle it.
        log_w = int(virtual_width * 1.5)
        log_h = int(virtual_height * 1.5)

        flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE
        pygame.display.set_mode((log_w, log_h), flags)
        pygame.display.set_caption(title)

        # Enable key repeat so holding Backspace/Delete/etc in Entry/Text widgets
        # feels responsive (delay, interval in ms). Games that don't want repeat
        # can call pygame.key.set_repeat(0, 0) after.
        pygame.key.set_repeat(300, 50)

        # After set_mode, query the actual sizes (OS may adjust for decorations).
        actual_log = pygame.display.get_window_size()
        log_w, log_h = actual_log

        # Drawable pixels may differ from logical pixels on HiDPI displays.
        draw_w, draw_h = get_drawable_size(log_w, log_h)
        self._px_ratio_x: float = draw_w / log_w if log_w else 1.0
        self._px_ratio_y: float = draw_h / log_h if log_h else 1.0

        # Font scale for crisp text on HiDPI. On Retina this is typically 2.0.
        # We supersample font rasterization by this factor so glyphs have native
        # device pixel detail while still occupying the correct virtual size.
        font_scale = (self._px_ratio_x + self._px_ratio_y) / 2.0 or 1.0

        ctx = moderngl.create_context()
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self._ctx = ctx

        self._virt_w = virtual_width
        self._virt_h = virtual_height
        self._target_fps = target_fps
        self._is_open = True

        vr = VirtualResolution(
            width=virtual_width, height=virtual_height, integer_scaling=False
        )
        self._renderer = Renderer(
            ctx, vr, font_path=font_path, font_bytes=font_bytes, font_scale=font_scale
        )
        self._renderer.set_render_scale(render_scale)
        self._renderer.set_clear_color(bar_color)
        self._renderer.handle_physical_resize(draw_w, draw_h)

        self._clock = pygame.time.Clock()
        self._dt: float = 0.0

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #

    @property
    def renderer(self) -> Renderer:
        """The Renderer for this window. Draw with it between begin_frame / end_frame."""
        return self._renderer

    @property
    def ctx(self) -> "moderngl.Context":
        """Raw moderngl GL context — escape hatch for 3D renderer and custom GL work."""
        return self._ctx

    @property
    def viewport(self):
        """Letterboxed viewport rect (Viewport namedtuple from logic.scaling).

        Use this to set up a 3D renderer's glViewport so 3D and 2D HUD share
        the same on-screen region and maintain the same aspect ratio.
        """
        return self._renderer.viewport

    @property
    def physical_size(self) -> tuple[int, int]:
        """Physical (drawable) window size in pixels, accounting for HiDPI."""
        return self._renderer._phys  # type: ignore[attr-defined]

    @property
    def is_open(self) -> bool:
        """True until close() is called."""
        return self._is_open

    @property
    def virtual_width(self) -> int:
        """Width of the virtual coordinate space in logical pixels."""
        return self._virt_w

    @property
    def virtual_height(self) -> int:
        """Height of the virtual coordinate space in logical pixels."""
        return self._virt_h

    @property
    def dt(self) -> float:
        """Delta-time in seconds from the most recent begin_frame() call."""
        return self._dt

    @property
    def fps(self) -> float:
        """Measured frames per second (moving average)."""
        return self._clock.get_fps()

    @property
    def viewport(self) -> Viewport:
        """Current letterbox viewport in physical (drawable) pixels.

        Advanced use only.  Most code draws in virtual coordinates and uses
        poll/begin_frame/end_frame; this is exposed for custom input math or
        overlays when you must know the exact placement of the game rect.
        """
        return self._renderer.viewport

    def screen_to_virtual(self, x: float, y: float) -> tuple[float, float]:
        """Map a point from logical window client coordinates into virtual space.

        Use this for mouse input (pygame.mouse.get_pos()) so that your game/UI
        logic receives coordinates in the same 0..virtual_width, 0..virtual_height
        space that all drawing functions expect.

        Points landing in the letterbox/pillarbox return values outside the
        virtual rect (negative or > virtual size).  Clamping is the caller's
        responsibility if desired.
        """
        vp = self._renderer.viewport
        if vp.viewport_width <= 0 or vp.viewport_height <= 0:
            return 0.0, 0.0

        # Convert the logical mouse position (from pygame) into physical pixels
        # using the HiDPI ratio. This ensures the mapping uses the exact same
        # physical numbers that the renderer used for glViewport and drawing
        # placement, avoiding mismatches on retina/HiDPI (especially macOS).
        phys_x = x * self._px_ratio_x
        phys_y = y * self._px_ratio_y

        # Use the top-left-based offsets (from physical window edge to content area).
        # These match the letterboxed region where virtual (0,0) is drawn.
        vx = (phys_x - vp.offset_x) / vp.viewport_width * self._virt_w
        vy = (phys_y - vp.offset_y) / vp.viewport_height * self._virt_h
        return vx, vy

    # ------------------------------------------------------------------ #
    # Frame lifecycle
    # ------------------------------------------------------------------ #

    def poll(self) -> list[pygame.event.Event]:
        """Consume all pending pygame events; handle VIDEORESIZE internally.

        Window resize events are processed transparently — the physical
        drawable size is updated and the letterbox layout is recomputed so
        the virtual content stays centered.  All other events are returned
        to the caller unchanged.
        """
        result: list[pygame.event.Event] = []
        for event in pygame.event.get():
            if event.type == pygame.VIDEORESIZE:
                draw_w = round(event.w * self._px_ratio_x)
                draw_h = round(event.h * self._px_ratio_y)
                # Virtual resolution is fixed; only physical size changes.
                # compute_viewport() will re-centre and re-letterbox automatically.
                self._renderer.handle_physical_resize(draw_w, draw_h)
            else:
                result.append(event)
        return result

    def begin_frame(self) -> float:
        """Tick the clock and prepare the GL frame.  Returns delta-time in seconds.

        Always renders at the native physical resolution (render_scale=1.0 by
        default).  Dynamic resolution scaling, if desired, must be enabled
        explicitly by the caller via renderer.set_render_scale() — the engine
        never silently reduces quality on its own, mirroring the default
        behaviour of Godot, Unity, and Unreal Engine.
        """
        self._dt = self._clock.tick(self._target_fps) / 1000.0
        self._renderer.prepare_frame()
        return self._dt

    def end_frame(self) -> None:
        """Flush renderer batches and flip the back buffer to the screen.

        If a reduced-res world FBO was used, it is upscaled here.
        """
        self._renderer.end_world_render()
        self._renderer.present()
        pygame.display.flip()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Signal the window to stop (sets is_open to False)."""
        self._is_open = False

    def quit(self) -> None:
        """Shut down pygame.  Call once after the main loop exits."""
        pygame.quit()


def open_and_run(
    app_state: AppState | None = None,
    *,
    font_path: str | None = None,
    font_bytes: bytes | None = None,
    render_scale: float = 1.0,
) -> None:
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
    pygame.font.init()  # for the text primitive
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

    # Compute HiDPI scale for crisp text (mirrors GameWindow logic).
    draw_w, draw_h = get_drawable_size(width, height)
    px_ratio = (
        (draw_w / width if width else 1.0) + (draw_h / height if height else 1.0)
    ) / 2.0 or 1.0
    font_scale = px_ratio

    # Video settings for vsync / clear color (best effort)
    video = app_state.engine.extensions.get("video")
    if video is None or not isinstance(video, VideoSettings):
        video = VideoSettings()
    try:
        pygame.display.set_vsync(1 if video.vsync else 0)
    except Exception:
        pass  # older pygame-ce or platform may not support

    ctx = moderngl.create_context()
    renderer = Renderer(
        ctx,
        initial_virtual=virt,
        font_path=font_path,
        font_bytes=font_bytes,
        font_scale=font_scale,
    )
    renderer.set_render_scale(render_scale)
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


def open_window_with_config(
    engine_config: EngineConfig,
    *,
    font_path: str | None = None,
    font_bytes: bytes | None = None,
    render_scale: float = 1.0,
) -> None:
    """Convenience for using just the engine config (for early testing)."""
    app_state = AppState(engine=engine_config)
    open_and_run(
        app_state, font_path=font_path, font_bytes=font_bytes, render_scale=render_scale
    )
