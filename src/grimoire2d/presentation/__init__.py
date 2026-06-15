"""Presentation layer (front-end / rendering).

Window management and all OpenGL 3.30 core code lives here (or below).
No raw GL calls should escape this package.

The Renderer (and the vendored shaders) are the implementation of the
real GL pipeline. Most callers only need the high-level open_and_run.
"""

from .window import open_and_run, open_window_with_config, GameWindow
from .renderer import Renderer
from .batch import ShapeBatch, SpriteBatch, ShapeType
from .pixel_buffer import PixelBuffer
from .highdpi import enable_highdpi, get_drawable_size
from .multi_viewport_renderer import render_scene, SceneFn
from .tcp_transport import TcpTransport, InMemoryTransport

__all__ = [
    "open_and_run",
    "open_window_with_config",
    "GameWindow",
    "Renderer",
    "ShapeBatch",
    "SpriteBatch",
    "ShapeType",
    "PixelBuffer",
    "enable_highdpi",
    "get_drawable_size",
    "render_scene",
    "SceneFn",
    "TcpTransport",
    "InMemoryTransport",
]
