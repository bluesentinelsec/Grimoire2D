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


@dataclass
class SpotLight:
    """Cone-shaped spot light — flashlight, ceiling fixture, lamp.

    ``direction`` is the direction the cone points (away from the source).
    ``inner_angle`` is the full-intensity cone (degrees); ``outer_angle`` is
    where the light fades to zero.  Intensity falls off smoothly between them.
    """
    position:    tuple[float, float, float] = (0.0, 3.0, 0.0)
    direction:   tuple[float, float, float] = (0.0, -1.0, 0.0)
    color:       tuple[float, float, float] = (1.0, 1.0, 1.0)
    intensity:   float = 3.0
    radius:      float = 15.0
    inner_angle: float = 15.0   # degrees — full brightness inside
    outer_angle: float = 30.0   # degrees — fade to zero at edge


@dataclass
class SkyGradient:
    """Procedural gradient sky rendered before scene geometry.

    Reconstructs world-space ray directions from NDC — no textures required.
    Colours are blended from ground → horizon → zenith based on the ray's
    world-space Y component.
    """
    zenith_color:  tuple[float, float, float] = (0.10, 0.18, 0.42)
    horizon_color: tuple[float, float, float] = (0.52, 0.65, 0.80)
    ground_color:  tuple[float, float, float] = (0.18, 0.16, 0.14)
