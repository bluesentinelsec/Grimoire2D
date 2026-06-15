"""Logic layer (business logic: game loop, timing, engine coordination).

This package will contain the business logic that operates on models.
"""

from .window import get_effective_window_settings, apply_runtime_mode_change
from .scaling import Viewport, compute_viewport, get_virtual_resolution
from .sdf import sdf_rect, sdf_rounded_rect, sdf_circle, sdf_ring, sdf_stroke

__all__ = [
    "get_effective_window_settings",
    "apply_runtime_mode_change",
    "Viewport",
    "compute_viewport",
    "get_virtual_resolution",
    "sdf_rect",
    "sdf_rounded_rect",
    "sdf_circle",
    "sdf_ring",
    "sdf_stroke",
]