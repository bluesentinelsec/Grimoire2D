"""Unit tests for the CollisionWorld / move_and_slide system."""

from __future__ import annotations

import pytest
from grimoire2d.logic.collision import AABB, CollisionWorld

R = 0.3    # player capsule radius used throughout
H = 1.8    # player capsule height


def _world_with_floor(y: float = 0.0) -> CollisionWorld:
    """Infinite flat floor slab centred at (0, y-0.5, 0)."""
    w = CollisionWorld()
    w.add_box(center=(0.0, y - 0.5, 0.0), size=(1000.0, 1.0, 1000.0))
    return w


# ---------------------------------------------------------------------------
# Free movement (no obstacles)
# ---------------------------------------------------------------------------

class TestFreeMovement:
    def test_moves_on_x(self):
        w = CollisionWorld()
        pos, on_floor = w.move_and_slide((0, 0, 0), (2, 0, 0), radius=R, height=H)
        assert pos[0] == pytest.approx(2.0)
        assert pos[1] == pytest.approx(0.0)
        assert pos[2] == pytest.approx(0.0)

    def test_moves_on_y(self):
        w = CollisionWorld()
        pos, _ = w.move_and_slide((0, 0, 0), (0, 5, 0), radius=R, height=H)
        assert pos[1] == pytest.approx(5.0)

    def test_moves_on_z(self):
        w = CollisionWorld()
        pos, _ = w.move_and_slide((0, 0, 0), (0, 0, -3), radius=R, height=H)
        assert pos[2] == pytest.approx(-3.0)

    def test_on_floor_false_when_no_obstacles(self):
        w = CollisionWorld()
        _, on_floor = w.move_and_slide((0, 10, 0), (0, -1, 0), radius=R, height=H)
        assert not on_floor

    def test_diagonal_moves_freely(self):
        w = CollisionWorld()
        pos, _ = w.move_and_slide((0, 0, 0), (1, 0, 1), radius=R, height=H)
        assert pos[0] == pytest.approx(1.0)
        assert pos[2] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Floor collision
# ---------------------------------------------------------------------------

class TestFloorCollision:
    def test_player_lands_on_floor(self):
        w = _world_with_floor(y=0.0)
        # Player falling toward floor; capsule bottom is at py, top at py+H
        # Floor is a slab from y=-1 to y=0. Player needs py >= 0 to stand on it.
        pos, on_floor = w.move_and_slide((0, 2, 0), (0, -5, 0), radius=R, height=H)
        # Should be blocked at floor surface (py ≥ 0)
        assert pos[1] >= -0.001
        assert on_floor

    def test_on_floor_true_when_standing(self):
        w = _world_with_floor(y=0.0)
        # Player already at rest on floor with a tiny downward nudge
        pos, on_floor = w.move_and_slide((0, 0, 0), (0, -0.01, 0), radius=R, height=H)
        assert on_floor

    def test_on_floor_false_when_airborne(self):
        w = _world_with_floor(y=0.0)
        pos, on_floor = w.move_and_slide((0, 5, 0), (0, 1, 0), radius=R, height=H)
        assert not on_floor

    def test_ceiling_does_not_set_on_floor(self):
        w = CollisionWorld()
        # Ceiling slab at y=3..4
        w.add_box(center=(0, 3.5, 0), size=(100, 1.0, 100))
        # Player moving up and hitting ceiling
        pos, on_floor = w.move_and_slide((0, 0, 0), (0, 5, 0), radius=R, height=H)
        # Blocked, but NOT on_floor (was pushed down, not up)
        assert pos[1] < 5.0
        assert not on_floor


# ---------------------------------------------------------------------------
# Wall collision
# ---------------------------------------------------------------------------

class TestWallCollision:
    def _wall_at_x(self, x: float) -> CollisionWorld:
        w = CollisionWorld()
        w.add_box(center=(x + 0.5, 2.0, 0.0), size=(1.0, 10.0, 100.0))
        return w

    def test_blocked_by_wall_on_x(self):
        w = self._wall_at_x(x=3.0)
        pos, _ = w.move_and_slide((0, 0, 0), (10, 0, 0), radius=R, height=H)
        # Should be stopped before the wall face at x=3.0
        assert pos[0] <= 3.0 + 0.001

    def test_slide_along_wall(self):
        """Moving diagonally into a wall on X should preserve Z movement."""
        w = self._wall_at_x(x=2.0)
        pos, _ = w.move_and_slide((0, 0, 0), (10, 0, 3), radius=R, height=H)
        # X is blocked; Z should be largely preserved
        assert pos[0] <= 2.0 + 0.001
        assert pos[2] == pytest.approx(3.0, abs=0.05)

    def test_blocked_from_both_sides(self):
        w = CollisionWorld()
        # Two walls forming a channel; player is centred
        w.add_box(center=(-5, 2, 0), size=(1, 10, 100))
        w.add_box(center=( 5, 2, 0), size=(1, 10, 100))
        # Large move in X in both directions should be blocked
        pos, _ = w.move_and_slide((0, 0, 0), (20, 0, 0), radius=R, height=H)
        assert pos[0] <= 5.0 + 0.001
        pos2, _ = w.move_and_slide((0, 0, 0), (-20, 0, 0), radius=R, height=H)
        assert pos2[0] >= -5.0 - 0.001


# ---------------------------------------------------------------------------
# Corner resolution
# ---------------------------------------------------------------------------

class TestCornerResolution:
    def test_corner_doesnt_get_stuck(self):
        """Player moving into an inner corner should stop, not get stuck."""
        w = CollisionWorld()
        # Two walls forming an inner corner at (+5, +5) in XZ
        w.add_box(center=(5.5, 2, 0), size=(1, 10, 100))  # X wall
        w.add_box(center=(0, 2, 5.5), size=(100, 10, 1))  # Z wall
        # Move diagonally into corner
        pos, _ = w.move_and_slide((0, 0, 0), (10, 0, 10), radius=R, height=H)
        assert pos[0] <= 5.0 + 0.1
        assert pos[2] <= 5.0 + 0.1


# ---------------------------------------------------------------------------
# Overlaps query
# ---------------------------------------------------------------------------

class TestOverlapsQuery:
    def test_overlaps_with_contained_box(self):
        w = CollisionWorld()
        w.add_box(center=(0, 0, 0), size=(4, 4, 4))
        assert w.overlaps((0, 0, 0), (0.5, 0.5, 0.5))

    def test_no_overlap_when_clear(self):
        w = CollisionWorld()
        w.add_box(center=(10, 0, 0), size=(2, 2, 2))
        assert not w.overlaps((0, 0, 0), (1, 1, 1))

    def test_touching_but_not_overlapping(self):
        w = CollisionWorld()
        w.add_box(center=(3, 0, 0), size=(2, 2, 2))   # occupies x=[2,4]
        # Query box at x=[0,2] — touching but not overlapping
        assert not w.overlaps((1, 0, 0), (1, 1, 1))


# ---------------------------------------------------------------------------
# CollisionWorld management
# ---------------------------------------------------------------------------

class TestManagement:
    def test_box_count(self):
        w = CollisionWorld()
        assert w.box_count == 0
        w.add_box((0, 0, 0), (1, 1, 1))
        w.add_box((5, 0, 0), (1, 1, 1))
        assert w.box_count == 2

    def test_clear_removes_all(self):
        w = _world_with_floor()
        w.clear()
        assert w.box_count == 0
        # Player should now fall through
        pos, on_floor = w.move_and_slide((0, 0, 0), (0, -5, 0), radius=R, height=H)
        assert not on_floor

    def test_zero_velocity_no_movement(self):
        w = _world_with_floor()
        pos, _ = w.move_and_slide((0, 0, 0), (0, 0, 0), radius=R, height=H)
        assert pos == pytest.approx((0.0, 0.0, 0.0), abs=0.001)
