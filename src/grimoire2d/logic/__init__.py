"""Logic layer (business logic: game loop, timing, engine coordination).

This package will contain the business logic that operates on models.
"""

from .window import get_effective_window_settings, apply_runtime_mode_change
from .scaling import Viewport, compute_viewport, get_virtual_resolution
from .sdf import sdf_rect, sdf_rounded_rect, sdf_circle, sdf_ring, sdf_stroke
from .input_router import (
    InputSource,
    LocalInputSource,
    StaticInputSource,
    SequencedInputSource,
    route_inputs,
)
from .simulation import SimulationClock
from .viewport_layout import compute_viewports
from .network_protocol import (
    encode_frame,
    decode_frame,
    encode_state,
    decode_state,
    read_length,
    LENGTH_PREFIX_SIZE,
)
from .pause_logic import (
    can_pause,
    request_pause,
    request_unpause,
    toggle_pause,
    is_paused,
)
from .scene_ops import (
    create_scene,
    close_scene,
    set_active_scene,
    query_scenes,
    get_scene,
    spawn_actor,
    destroy_actor,
    set_actor_active,
    query_actors,
    get_actor,
    update_component,
    get_component,
    remove_component,
)

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
    "InputSource",
    "LocalInputSource",
    "StaticInputSource",
    "SequencedInputSource",
    "route_inputs",
    "SimulationClock",
    "compute_viewports",
    "encode_frame",
    "decode_frame",
    "encode_state",
    "decode_state",
    "read_length",
    "LENGTH_PREFIX_SIZE",
    "can_pause",
    "request_pause",
    "request_unpause",
    "toggle_pause",
    "is_paused",
    "create_scene",
    "close_scene",
    "set_active_scene",
    "query_scenes",
    "get_scene",
    "spawn_actor",
    "destroy_actor",
    "set_actor_active",
    "query_actors",
    "get_actor",
    "update_component",
    "get_component",
    "remove_component",
]