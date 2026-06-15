"""HiDPI / Retina detection for SDL2 + OpenGL windows.

On macOS the SDL2 logical "points" window size differs from the GL
framebuffer's physical pixel dimensions.  This module provides a
platform-safe way to:

  1. Enable HiDPI before pygame initialises (``enable_highdpi()``).
  2. Query the actual drawable pixels after ``set_mode()``
     (``get_drawable_size()``).

The drawable size is what the GL viewport and the virtual resolution must
be set to for native-resolution rendering; using the logical window size
instead gives an OS-upscaled (slightly blurry) framebuffer.

Usage::

    from grimoire2d.presentation.highdpi import enable_highdpi, get_drawable_size

    enable_highdpi()          # call BEFORE pygame.init()
    pygame.init()
    ...
    pygame.display.set_mode(logical_size, flags)
    draw_w, draw_h = get_drawable_size(*logical_size)
    # draw_w / draw_h are the native physical pixels to target.
"""
from __future__ import annotations

import ctypes
import os
import pathlib


def enable_highdpi() -> None:
    """Tell SDL2 to expose the native Retina framebuffer for OpenGL windows.

    Must be called **before** ``pygame.init()`` so that SDL reads the hint
    during subsystem initialisation.  Safe to call on non-HiDPI platforms
    (the hint is silently ignored).
    """
    os.environ["SDL_VIDEO_HIGHDPI_DISABLED"] = "0"


def _pygame_sdl2_path() -> str | None:
    """Return the absolute path of the SDL2 shared library bundled with pygame."""
    try:
        import pygame as _pg
        base = pathlib.Path(_pg.__file__).parent
    except ImportError:
        return None

    candidates = [
        base / ".dylibs" / "libSDL2-2.0.0.dylib",   # macOS (pygame-ce)
        base / ".dylibs" / "libSDL2-2.0.so.0",       # Linux bundled
        base / "libSDL2-2.0.so.0",
        base / "SDL2.dll",                            # Windows
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def get_drawable_size(fallback_w: int, fallback_h: int) -> tuple[int, int]:
    """Return the GL framebuffer dimensions in physical pixels.

    On HiDPI / Retina displays the framebuffer can be 2× (or more) larger
    than the SDL logical window size.  This function calls
    ``SDL_GL_GetDrawableSize`` via ctypes so the caller does not need to
    depend on a specific pygame version.

    Must be called **after** ``pygame.display.set_mode()`` has created the
    OpenGL window.

    Args:
        fallback_w: Logical window width to return if detection fails.
        fallback_h: Logical window height to return if detection fails.

    Returns:
        ``(width, height)`` in physical pixels, or the fallback values if
        SDL2 is not reachable or the query fails.
    """
    lib_path = _pygame_sdl2_path()
    if lib_path is None:
        return fallback_w, fallback_h

    try:
        sdl = ctypes.CDLL(lib_path)

        sdl.SDL_GL_GetCurrentWindow.restype = ctypes.c_void_p
        win = sdl.SDL_GL_GetCurrentWindow()
        if not win:
            return fallback_w, fallback_h

        dw, dh = ctypes.c_int(0), ctypes.c_int(0)
        sdl.SDL_GL_GetDrawableSize(
            ctypes.c_void_p(win), ctypes.byref(dw), ctypes.byref(dh)
        )
        if dw.value > 0 and dh.value > 0:
            return dw.value, dh.value
    except Exception:
        pass

    return fallback_w, fallback_h
