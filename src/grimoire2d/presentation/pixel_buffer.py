"""CPU-side RGBA pixel buffer with single-upload-per-frame GL texture backing."""

from __future__ import annotations

import moderngl


class PixelBuffer:
    """Wraps a bytearray of RGBA pixels and a GL texture for retro pixel-art effects.

    Typical use per frame:
        buf.clear((0, 0, 0, 255))
        buf.plot(x, y, (255, 0, 0, 255))
        buf.upload()
        renderer.draw_pixel_buffer(buf, dst_x, dst_y, dst_w, dst_h)

    The internal ``_data`` bytearray is always ``width * height * 4`` bytes
    in row-major order (row 0 = top), RGBA channel order.

    ``upload()`` is a no-op when nothing has changed since the last call,
    so it is safe to call unconditionally every frame.
    """

    def __init__(self, ctx: moderngl.Context, width: int, height: int) -> None:
        """Create a zeroed pixel buffer and its backing GL texture.

        Args:
            ctx: Active moderngl context.
            width: Buffer width in pixels.
            height: Buffer height in pixels.
        """
        self._ctx = ctx
        self.width = width
        self.height = height
        self._data: bytearray = bytearray(width * height * 4)
        self._dirty: bool = True
        self._texture: moderngl.Texture = ctx.texture((width, height), 4)
        self._texture.filter = (moderngl.NEAREST, moderngl.NEAREST)

    def plot(self, x: int, y: int, color: tuple[int, int, int, int]) -> None:
        """Set a single pixel.  No-op if (x, y) is out of bounds.

        Args:
            x: Column index (0 = left).
            y: Row index (0 = top).
            color: RGBA bytes, each 0..255.
        """
        if 0 <= x < self.width and 0 <= y < self.height:
            i = (y * self.width + x) * 4
            self._data[i] = color[0]
            self._data[i + 1] = color[1]
            self._data[i + 2] = color[2]
            self._data[i + 3] = color[3]
            self._dirty = True

    def plot_hline(
        self,
        x: int,
        y: int,
        length: int,
        color: tuple[int, int, int, int],
    ) -> None:
        """Draw a horizontal run of pixels, clipped to the buffer bounds.

        Args:
            x: Start column index.
            y: Row index.
            length: Number of pixels to write.
            color: RGBA bytes, each 0..255.
        """
        if y < 0 or y >= self.height:
            return
        x_start = max(x, 0)
        x_end = min(x + length, self.width)
        if x_start >= x_end:
            return
        pixel = bytes(color)
        base = (y * self.width + x_start) * 4
        for i in range(x_end - x_start):
            self._data[base + i * 4 : base + i * 4 + 4] = pixel
        self._dirty = True

    def plot_vline(
        self,
        x: int,
        y: int,
        length: int,
        color: tuple[int, int, int, int],
    ) -> None:
        """Draw a vertical run of pixels, clipped to the buffer bounds.

        Args:
            x: Column index.
            y: Start row index.
            length: Number of pixels to write.
            color: RGBA bytes, each 0..255.
        """
        if x < 0 or x >= self.width:
            return
        y_start = max(y, 0)
        y_end = min(y + length, self.height)
        if y_start >= y_end:
            return
        pixel = bytes(color)
        for row in range(y_start, y_end):
            i = (row * self.width + x) * 4
            self._data[i : i + 4] = pixel
        self._dirty = True

    def clear(self, color: tuple[int, int, int, int] = (0, 0, 0, 255)) -> None:
        """Fill the entire buffer with a single colour.

        Args:
            color: RGBA bytes, each 0..255.  Defaults to opaque black.
        """
        pixel = bytes(color)
        n = self.width * self.height
        for i in range(n):
            self._data[i * 4 : i * 4 + 4] = pixel
        self._dirty = True

    def upload(self) -> None:
        """Push the CPU buffer to the GL texture.

        A no-op when the buffer has not been modified since the last call.
        Typical usage: call once per frame, immediately before
        ``renderer.draw_pixel_buffer()``.
        """
        if not self._dirty:
            return
        self._texture.write(bytes(self._data))
        self._dirty = False

    @property
    def texture(self) -> moderngl.Texture:
        """The backing GL texture (use ``upload()`` first each frame)."""
        return self._texture

    def release(self) -> None:
        """Release the backing GL texture."""
        self._texture.release()
