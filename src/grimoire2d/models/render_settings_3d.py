"""Runtime toggles for 3D rendering effects.

Every field maps directly to a GLSL uniform. Flipping a flag takes effect
on the next frame — no pipeline rebuild or shader recompilation.

This is the data model only. The renderer reads it; nothing here holds GL
objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RenderSettings3D:
    # Per-fragment lighting components
    specular: bool = True
    normal_mapping: bool = True  # requires tangent-space normal maps (Phase 3+)

    # Atmospheric
    fog: bool = False
    fog_color: tuple[float, float, float] = (0.4, 0.45, 0.5)
    fog_near: float = 20.0
    fog_far: float = 120.0

    # Shadow map (Phase 2)
    shadows: bool = False  # not yet implemented; flag reserved

    # Post-process (Phase 6)
    fxaa: bool = False
    bloom: bool = False

    # Light budget — lower on constrained hardware
    max_point_lights: int = 8

    # Delta-time cap: prevents simulation spiral-of-death when the process is
    # paused (e.g. under a debugger). No more than this many seconds of
    # simulation time will advance in a single frame.
    max_dt: float = 0.1
