"""Presentation layer (front-end / rendering).

Window management and all OpenGL 3.30 core code lives here (or below).
No raw GL calls should escape this package.
"""

from .window import open_and_run, open_window_with_config

__all__ = ["open_and_run", "open_window_with_config"]