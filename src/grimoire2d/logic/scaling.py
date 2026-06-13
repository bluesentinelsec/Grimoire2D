"""Business logic for virtual resolution, integer scaling, and letterboxing.

All functions here are pure and fully testable without a window or OpenGL.
They implement the professional "resolution independence via integer
scaling + letterboxing" behavior mandated by the design goals.

The computed Viewport tells the renderer exactly which physical pixel
rectangle to use for glViewport and how to configure the orthographic
projection so that game drawing code can work entirely in virtual
coordinates (default 1280x720).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from grimoire2d.models import EngineConfig, VirtualResolution


@dataclass(frozen=True, slots=True)
class Viewport:
    """Pure computed mapping from virtual game coordinates to a letterboxed
    region of the physical window.

    All values are in pixels. The viewport_* fields describe the sub-rectangle
    (in physical window pixels) that should receive the game's rendering.
    """

    virtual_width: int
    virtual_height: int
    physical_width: int
    physical_height: int
    scale: float
    offset_x: int  # letterbox/pillarbox from left (and right)
    offset_y: int  # letterbox from top (and bottom)
    viewport_x: int
    viewport_y: int  # GL origin is bottom-left; this is pre-adjusted
    viewport_width: int
    viewport_height: int


def compute_viewport(
    virtual: VirtualResolution, physical_width: int, physical_height: int
) -> Viewport:
    """Compute the letterboxed viewport and scale.

    The game is always drawn using the *full* virtual (logical) coordinate
    space (e.g. 0..1280, 0..720). This function computes how to map that
    logical surface into the actual OS window:

      - scale = the factor that makes the entire logical surface fit
        inside the physical window while preserving aspect ratio.
      - The content is centered with letterbox/pillarbox bars as needed.
      - glViewport is set to the resulting centered sub-rectangle.

    This means:
    - When the window is larger than the virtual resolution, the logical
      scene is scaled *up* (and letterboxed).
    - When the window is smaller, the logical scene is scaled *down* so
      the **full** content remains visible (just smaller on screen).
    - integer_scaling=True (default) prefers crisp integer scales when
      upscaling is possible. When the window is too small for 1:1, it
      falls back to fractional downscaling so you never lose part of the
      logical surface.

    The returned Viewport tells the renderer the exact physical pixel
    rectangle to use for the viewport + how the orthographic projection
    should be configured.
    """
    if physical_width <= 0 or physical_height <= 0:
        physical_width = max(virtual.width, 1)
        physical_height = max(virtual.height, 1)

    v_w = virtual.width
    v_h = virtual.height

    scale_x = physical_width / v_w
    scale_y = physical_height / v_h
    fit_scale = min(scale_x, scale_y)

    if virtual.integer_scaling and fit_scale >= 1.0:
        # Prefer largest integer scale that still fits (crisp pixels)
        scale = max(1.0, float(int(fit_scale)))
    else:
        # Either fractional mode, or window is smaller than virtual:
        # always use the fit scale so the *entire* logical surface is visible.
        scale = fit_scale

    scaled_w = int(v_w * scale)
    scaled_h = int(v_h * scale)

    offset_x = (physical_width - scaled_w) // 2
    offset_y = (physical_height - scaled_h) // 2

    # GL viewport y is measured from the *bottom* of the window.
    # Our offset_y is distance from the *top* of the window to the game area.
    gl_viewport_y = physical_height - (offset_y + scaled_h)
    gl_viewport_x = offset_x

    return Viewport(
        virtual_width=v_w,
        virtual_height=v_h,
        physical_width=physical_width,
        physical_height=physical_height,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        viewport_x=gl_viewport_x,
        viewport_y=gl_viewport_y,
        viewport_width=scaled_w,
        viewport_height=scaled_h,
    )


def get_virtual_resolution(engine_config: "EngineConfig") -> VirtualResolution:
    """Extract the current virtual resolution from an EngineConfig extension.

    Falls back to the 1280x720 default if missing or wrong type (defensive).
    This is the single obvious place presentation and other logic should
    ask for the authoritative virtual size.
    """
    from grimoire2d.models import VirtualResolution  # local to avoid cycles

    vr = engine_config.extensions.get("virtual_resolution")
    if vr is None or not isinstance(vr, VirtualResolution):
        return VirtualResolution()
    return vr
