"""3D light source data models.

Pure data — no GL objects. The Renderer3D reads these each frame and uploads
the values as uniforms.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AmbientLight:
    color: tuple[float, float, float] = (0.08, 0.08, 0.12)


@dataclass
class DirectionalLight:
    """Infinite-distance directional light (sun/moon).

    ``direction`` is the *direction the light travels* (pointing away from the
    source), so (0, -1, -0.5) means light coming from above and slightly in
    front of the camera. The shader negates this to get the surface-to-light
    vector.
    """

    direction: tuple[float, float, float] = (0.3, -1.0, -0.5)
    color: tuple[float, float, float] = (1.0, 0.95, 0.85)
    intensity: float = 1.0
    enabled: bool = True


@dataclass
class PointLight:
    position: tuple[float, float, float] = (0.0, 2.0, 0.0)
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    intensity: float = 1.0
    radius: float = 12.0
