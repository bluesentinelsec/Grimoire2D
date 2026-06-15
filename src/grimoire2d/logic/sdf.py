"""Signed-distance-field primitives for 2D shapes (pure Python reference).

All shapes are defined relative to their center (origin).  Callers
translate (px, py) relative to the shape center before calling.

Return convention:
  < 0  — point is inside the shape
    0  — point is exactly on the boundary
  > 0  — point is outside the shape

No GL, no third-party imports.  Every function is independently testable
in a headless Python process.
"""
from __future__ import annotations

import math


def sdf_rect(px: float, py: float, half_w: float, half_h: float) -> float:
    """Signed distance from (px, py) to a centered axis-aligned rectangle.

    Args:
        px: x coordinate relative to the rect center.
        py: y coordinate relative to the rect center.
        half_w: half the rectangle width.
        half_h: half the rectangle height.

    Returns:
        Signed distance; negative inside, zero on edge, positive outside.
    """
    qx = abs(px) - half_w
    qy = abs(py) - half_h
    return math.sqrt(max(qx, 0.0) ** 2 + max(qy, 0.0) ** 2) + min(max(qx, qy), 0.0)


def sdf_rounded_rect(px: float, py: float, half_w: float, half_h: float, r: float) -> float:
    """Signed distance from (px, py) to a centered rounded rectangle.

    The corner radius is clamped to ``min(half_w, half_h)`` so it
    never exceeds the geometry's shortest semi-axis.

    Args:
        px: x coordinate relative to the rect center.
        py: y coordinate relative to the rect center.
        half_w: half the rectangle width.
        half_h: half the rectangle height.
        r: corner radius (clamped internally).

    Returns:
        Signed distance; negative inside, zero on edge, positive outside.
    """
    r = min(r, min(half_w, half_h))
    qx = abs(px) - half_w + r
    qy = abs(py) - half_h + r
    return math.sqrt(max(qx, 0.0) ** 2 + max(qy, 0.0) ** 2) + min(max(qx, qy), 0.0) - r


def sdf_circle(px: float, py: float, r: float) -> float:
    """Signed distance from (px, py) to a circle of radius r centered at origin.

    Args:
        px: x coordinate relative to the circle center.
        py: y coordinate relative to the circle center.
        r: circle radius.

    Returns:
        Signed distance; negative inside, zero on boundary, positive outside.
    """
    return math.sqrt(px * px + py * py) - r


def sdf_ring(px: float, py: float, outer_r: float, inner_r: float) -> float:
    """Signed distance from (px, py) to an annulus (ring/donut) centered at origin.

    The ring is defined by an outer radius and an inner radius.  Points
    between the two radii are inside (distance < 0); points inside the
    hole or outside the outer circle are outside (distance > 0).

    Args:
        px: x coordinate relative to the ring center.
        py: y coordinate relative to the ring center.
        outer_r: outer radius of the ring.
        inner_r: inner radius (hole) of the ring.

    Returns:
        Signed distance; negative between radii, positive in hole or outside.
    """
    d = math.sqrt(px * px + py * py)
    return abs(d - (outer_r + inner_r) * 0.5) - (outer_r - inner_r) * 0.5


def sdf_stroke(d: float, thickness: float) -> float:
    """Convert a filled SDF distance to a stroke / border distance.

    Given the distance ``d`` to a shape's surface (as returned by any
    filled sdf_* function), returns the distance to the outline of that
    shape rendered with the given ``thickness``.

    Args:
        d: signed distance from any filled SDF function.
        thickness: total stroke width in the same units as ``d``.

    Returns:
        Signed distance to the stroke boundary; negative inside stroke.
    """
    return abs(d) - thickness * 0.5
