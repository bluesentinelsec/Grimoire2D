"""Unit tests for grimoire2d.logic.sdf — pure Python SDF reference implementations.

All tests run headlessly with no GL context required.
"""
from __future__ import annotations

import math
import unittest

from grimoire2d.logic.sdf import (
    sdf_circle,
    sdf_rect,
    sdf_ring,
    sdf_rounded_rect,
    sdf_stroke,
)


class TestSdfRect(unittest.TestCase):
    """Tests for sdf_rect."""

    def test_center_is_inside(self) -> None:
        d = sdf_rect(0.0, 0.0, 10.0, 5.0)
        self.assertLess(d, 0.0)

    def test_on_right_edge(self) -> None:
        d = sdf_rect(10.0, 0.0, 10.0, 5.0)
        self.assertAlmostEqual(d, 0.0)

    def test_on_top_edge(self) -> None:
        d = sdf_rect(0.0, 5.0, 10.0, 5.0)
        self.assertAlmostEqual(d, 0.0)

    def test_outside_right(self) -> None:
        d = sdf_rect(15.0, 0.0, 10.0, 5.0)
        self.assertAlmostEqual(d, 5.0)

    def test_outside_corner(self) -> None:
        d = sdf_rect(13.0, 14.0, 10.0, 10.0)
        expected = math.sqrt(3.0 ** 2 + 4.0 ** 2)
        self.assertAlmostEqual(d, expected, places=6)

    def test_inside_center_negative(self) -> None:
        d = sdf_rect(0.0, 0.0, 100.0, 50.0)
        self.assertAlmostEqual(d, -50.0)


class TestSdfRoundedRect(unittest.TestCase):
    """Tests for sdf_rounded_rect."""

    def test_center_is_inside(self) -> None:
        d = sdf_rounded_rect(0.0, 0.0, 10.0, 5.0, 2.0)
        self.assertLess(d, 0.0)

    def test_on_flat_edge(self) -> None:
        d = sdf_rounded_rect(0.0, 5.0, 10.0, 5.0, 2.0)
        self.assertAlmostEqual(d, 0.0, places=6)

    def test_outside_flat_edge(self) -> None:
        d = sdf_rounded_rect(0.0, 7.0, 10.0, 5.0, 2.0)
        self.assertAlmostEqual(d, 2.0, places=6)

    def test_on_corner_arc_boundary(self) -> None:
        r = 2.0
        half_w, half_h = 10.0, 5.0
        arc_cx = half_w - r
        arc_cy = half_h - r
        inv_sqrt2 = math.sqrt(2.0) / 2.0
        px = arc_cx + r * inv_sqrt2
        py = arc_cy + r * inv_sqrt2
        d = sdf_rounded_rect(px, py, half_w, half_h, r)
        self.assertAlmostEqual(d, 0.0, places=6)

    def test_outside_via_corner(self) -> None:
        d = sdf_rounded_rect(12.0, 7.0, 10.0, 5.0, 2.0)
        self.assertGreater(d, 0.0)

    def test_radius_clamped_to_circle(self) -> None:
        r = 100.0
        hw = hh = 5.0
        d_rr = sdf_rounded_rect(3.0, 4.0, hw, hh, r)
        d_c = sdf_circle(3.0, 4.0, hw)
        self.assertAlmostEqual(d_rr, d_c, places=6)


class TestSdfCircle(unittest.TestCase):
    """Tests for sdf_circle."""

    def test_center_is_inside(self) -> None:
        d = sdf_circle(0.0, 0.0, 10.0)
        self.assertAlmostEqual(d, -10.0)

    def test_on_boundary(self) -> None:
        d = sdf_circle(10.0, 0.0, 10.0)
        self.assertAlmostEqual(d, 0.0)

    def test_outside(self) -> None:
        d = sdf_circle(13.0, 0.0, 10.0)
        self.assertAlmostEqual(d, 3.0)

    def test_diagonal_boundary(self) -> None:
        r = 5.0
        d = sdf_circle(3.0, 4.0, r)
        self.assertAlmostEqual(d, 0.0, places=6)


class TestSdfRing(unittest.TestCase):
    """Tests for sdf_ring."""

    def test_center_inside_hole_is_positive(self) -> None:
        d = sdf_ring(0.0, 0.0, 10.0, 4.0)
        self.assertGreater(d, 0.0)

    def test_on_inner_edge(self) -> None:
        d = sdf_ring(4.0, 0.0, 10.0, 4.0)
        self.assertAlmostEqual(d, 0.0, places=6)

    def test_between_radii_is_negative(self) -> None:
        d = sdf_ring(7.0, 0.0, 10.0, 4.0)
        self.assertLess(d, 0.0)

    def test_on_outer_edge(self) -> None:
        d = sdf_ring(10.0, 0.0, 10.0, 4.0)
        self.assertAlmostEqual(d, 0.0, places=6)

    def test_outside_ring(self) -> None:
        d = sdf_ring(15.0, 0.0, 10.0, 4.0)
        self.assertGreater(d, 0.0)


class TestSdfStroke(unittest.TestCase):
    """Tests for sdf_stroke."""

    def test_positive_d_inside_stroke(self) -> None:
        d = sdf_stroke(1.0, 4.0)
        self.assertAlmostEqual(d, -1.0)

    def test_zero_d_is_boundary(self) -> None:
        d = sdf_stroke(0.0, 4.0)
        self.assertAlmostEqual(d, -2.0)

    def test_large_d_outside_stroke(self) -> None:
        d = sdf_stroke(10.0, 4.0)
        self.assertAlmostEqual(d, 8.0)

    def test_negative_d_same_as_positive(self) -> None:
        d_neg = sdf_stroke(-3.0, 6.0)
        d_pos = sdf_stroke(3.0, 6.0)
        self.assertAlmostEqual(d_neg, d_pos)


if __name__ == "__main__":
    unittest.main()
