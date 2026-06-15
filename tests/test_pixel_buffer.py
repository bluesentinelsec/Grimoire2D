"""Unit tests for grimoire2d.presentation.pixel_buffer.

Tests exercise the pure CPU-side logic (bytearray state) through a
lightweight mock GL context — no real OpenGL window is required.
"""
from __future__ import annotations

import unittest

from grimoire2d.presentation.pixel_buffer import PixelBuffer


class _FakeTexture:
    """Minimal stand-in for moderngl.Texture."""

    filter = (None, None)

    def write(self, data: bytes) -> None:
        """Accept texture data without uploading anywhere."""

    def release(self) -> None:
        """No-op release."""


class _FakeCtx:
    """Minimal stand-in for moderngl.Context."""

    def texture(self, size: tuple[int, int], components: int) -> _FakeTexture:
        """Return a fake texture of the given dimensions."""
        return _FakeTexture()


def _make_buf(w: int = 4, h: int = 4) -> PixelBuffer:
    return PixelBuffer(_FakeCtx(), w, h)  # type: ignore[arg-type]


class TestClear(unittest.TestCase):
    """Tests for PixelBuffer.clear."""

    def test_clears_all_pixels(self) -> None:
        buf = _make_buf(2, 2)
        buf.clear((10, 20, 30, 40))
        for i in range(2 * 2):
            base = i * 4
            self.assertEqual(buf._data[base], 10)
            self.assertEqual(buf._data[base + 1], 20)
            self.assertEqual(buf._data[base + 2], 30)
            self.assertEqual(buf._data[base + 3], 40)

    def test_dirty_after_clear(self) -> None:
        buf = _make_buf()
        buf._dirty = False
        buf.clear()
        self.assertTrue(buf._dirty)


class TestPlot(unittest.TestCase):
    """Tests for PixelBuffer.plot."""

    def test_correct_byte_offset(self) -> None:
        buf = _make_buf(4, 4)
        buf.plot(2, 1, (11, 22, 33, 44))
        i = (1 * 4 + 2) * 4
        self.assertEqual(buf._data[i], 11)
        self.assertEqual(buf._data[i + 1], 22)
        self.assertEqual(buf._data[i + 2], 33)
        self.assertEqual(buf._data[i + 3], 44)

    def test_out_of_bounds_does_nothing(self) -> None:
        buf = _make_buf(4, 4)
        buf._dirty = False
        before = bytes(buf._data)
        buf.plot(-1, 0, (255, 0, 0, 255))
        buf.plot(4, 0, (255, 0, 0, 255))
        buf.plot(0, -1, (255, 0, 0, 255))
        buf.plot(0, 4, (255, 0, 0, 255))
        self.assertEqual(bytes(buf._data), before)
        self.assertFalse(buf._dirty)

    def test_dirty_after_plot(self) -> None:
        buf = _make_buf()
        buf._dirty = False
        buf.plot(0, 0, (1, 2, 3, 4))
        self.assertTrue(buf._dirty)


class TestPlotHline(unittest.TestCase):
    """Tests for PixelBuffer.plot_hline."""

    def test_sets_correct_range(self) -> None:
        buf = _make_buf(8, 4)
        buf.plot_hline(2, 1, 3, (5, 6, 7, 8))
        for col in range(2, 5):
            i = (1 * 8 + col) * 4
            self.assertEqual(buf._data[i], 5)
        i_before = (1 * 8 + 1) * 4
        self.assertEqual(buf._data[i_before], 0)
        i_after = (1 * 8 + 5) * 4
        self.assertEqual(buf._data[i_after], 0)

    def test_out_of_bounds_row_noop(self) -> None:
        buf = _make_buf(4, 4)
        buf._dirty = False
        before = bytes(buf._data)
        buf.plot_hline(0, -1, 4, (1, 2, 3, 4))
        buf.plot_hline(0, 4, 4, (1, 2, 3, 4))
        self.assertEqual(bytes(buf._data), before)
        self.assertFalse(buf._dirty)

    def test_clips_to_buffer_width(self) -> None:
        buf = _make_buf(4, 4)
        buf.plot_hline(2, 0, 10, (9, 8, 7, 6))
        for col in range(2, 4):
            i = col * 4
            self.assertEqual(buf._data[i], 9)

    def test_dirty_after_hline(self) -> None:
        buf = _make_buf()
        buf._dirty = False
        buf.plot_hline(0, 0, 2, (1, 2, 3, 4))
        self.assertTrue(buf._dirty)


class TestPlotVline(unittest.TestCase):
    """Tests for PixelBuffer.plot_vline."""

    def test_sets_correct_range(self) -> None:
        buf = _make_buf(4, 8)
        buf.plot_vline(1, 2, 3, (10, 11, 12, 13))
        for row in range(2, 5):
            i = (row * 4 + 1) * 4
            self.assertEqual(buf._data[i], 10)
        i_before = (1 * 4 + 1) * 4
        self.assertEqual(buf._data[i_before], 0)
        i_after = (5 * 4 + 1) * 4
        self.assertEqual(buf._data[i_after], 0)

    def test_out_of_bounds_col_noop(self) -> None:
        buf = _make_buf(4, 4)
        buf._dirty = False
        before = bytes(buf._data)
        buf.plot_vline(-1, 0, 4, (1, 2, 3, 4))
        buf.plot_vline(4, 0, 4, (1, 2, 3, 4))
        self.assertEqual(bytes(buf._data), before)
        self.assertFalse(buf._dirty)

    def test_dirty_after_vline(self) -> None:
        buf = _make_buf()
        buf._dirty = False
        buf.plot_vline(0, 0, 2, (1, 2, 3, 4))
        self.assertTrue(buf._dirty)


class TestUploadDirtyFlag(unittest.TestCase):
    """Tests for PixelBuffer._dirty and upload()."""

    def test_dirty_reset_after_upload(self) -> None:
        buf = _make_buf()
        buf.plot(0, 0, (1, 2, 3, 4))
        self.assertTrue(buf._dirty)
        buf.upload()
        self.assertFalse(buf._dirty)

    def test_upload_noop_when_clean(self) -> None:
        buf = _make_buf()
        buf.upload()
        self.assertFalse(buf._dirty)
        buf.upload()
        self.assertFalse(buf._dirty)


if __name__ == "__main__":
    unittest.main()
