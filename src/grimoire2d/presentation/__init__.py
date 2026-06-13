"""Presentation layer (front-end / rendering).

Window management and all OpenGL 3.30 core code lives here (or below).
No raw GL calls should escape this package.

The Renderer (and the vendored shaders) are the implementation of the
real GL pipeline. Most callers only need the high-level open_and_run.
"""

from .window import open_and_run, open_window_with_config
from .renderer import Renderer

__all__ = ["open_and_run", "open_window_with_config", "Renderer"]