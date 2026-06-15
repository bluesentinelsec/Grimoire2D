"""Tests for logic.viewport_layout — compute_viewports()."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.logic.viewport_layout import compute_viewports
from grimoire2d.models.multiplayer import (
    MultiplayerConfig,
    ViewportAssignment,
    TOPOLOGY_SHARED_SCREEN,
    TOPOLOGY_SPLIT_SCREEN,
    TOPOLOGY_NETWORK_HOST,
    TOPOLOGY_NETWORK_CLIENT,
)
from grimoire2d.models.player import PlayerIdentity, ROLE_LOCAL, ROLE_REMOTE

W, H = 1280.0, 720.0


def _make_split(n: int) -> MultiplayerConfig:
    slots = tuple(
        PlayerIdentity(player_id=f"P{i+1}", role=ROLE_LOCAL)
        for i in range(n)
    )
    return MultiplayerConfig(player_slots=slots, topology=TOPOLOGY_SPLIT_SCREEN)


class TestSharedScreenTopology(unittest.TestCase):

    def test_single_assignment_full_screen(self):
        cfg = MultiplayerConfig.single_player()
        vps = compute_viewports(cfg, W, H)
        self.assertEqual(len(vps), 1)
        self.assertEqual(vps[0].player_id, "*")
        self.assertEqual(vps[0].x, 0.0)
        self.assertEqual(vps[0].y, 0.0)
        self.assertEqual(vps[0].w, W)
        self.assertEqual(vps[0].h, H)

    def test_two_player_shared_still_one_viewport(self):
        cfg = MultiplayerConfig.local_two_player_shared()
        vps = compute_viewports(cfg, W, H)
        self.assertEqual(len(vps), 1)
        self.assertEqual(vps[0].player_id, "*")


class TestNetworkTopology(unittest.TestCase):

    def test_network_host_treated_as_shared(self):
        cfg = MultiplayerConfig.network_host()
        vps = compute_viewports(cfg, W, H)
        self.assertEqual(len(vps), 1)
        self.assertEqual(vps[0].player_id, "*")

    def test_network_client_treated_as_shared(self):
        cfg = MultiplayerConfig.network_client("127.0.0.1")
        vps = compute_viewports(cfg, W, H)
        self.assertEqual(len(vps), 1)
        self.assertEqual(vps[0].player_id, "*")


class TestSplitScreenTwoPlayer(unittest.TestCase):

    def setUp(self):
        self.cfg = _make_split(2)
        self.vps = compute_viewports(self.cfg, W, H)

    def test_returns_two_viewports(self):
        self.assertEqual(len(self.vps), 2)

    def test_player_ids_assigned(self):
        pids = {vp.player_id for vp in self.vps}
        self.assertEqual(pids, {"P1", "P2"})

    def test_left_right_split(self):
        left  = next(vp for vp in self.vps if vp.player_id == "P1")
        right = next(vp for vp in self.vps if vp.player_id == "P2")
        self.assertEqual(left.x, 0.0)
        self.assertAlmostEqual(left.w, W / 2)
        self.assertAlmostEqual(right.x, W / 2)
        self.assertAlmostEqual(right.w, W / 2)

    def test_full_height(self):
        for vp in self.vps:
            self.assertEqual(vp.h, H)

    def test_no_overlap_no_gap(self):
        left  = next(vp for vp in self.vps if vp.player_id == "P1")
        right = next(vp for vp in self.vps if vp.player_id == "P2")
        self.assertAlmostEqual(left.x + left.w, right.x)
        self.assertAlmostEqual(right.x + right.w, W)


class TestSplitScreenFourPlayer(unittest.TestCase):

    def setUp(self):
        self.cfg = _make_split(4)
        self.vps = compute_viewports(self.cfg, W, H)

    def test_returns_four_viewports(self):
        self.assertEqual(len(self.vps), 4)

    def test_player_ids_all_present(self):
        pids = {vp.player_id for vp in self.vps}
        self.assertEqual(pids, {"P1", "P2", "P3", "P4"})

    def test_each_viewport_is_quarter_screen(self):
        for vp in self.vps:
            self.assertAlmostEqual(vp.w, W / 2)
            self.assertAlmostEqual(vp.h, H / 2)

    def test_covers_full_screen(self):
        total_area = sum(vp.w * vp.h for vp in self.vps)
        self.assertAlmostEqual(total_area, W * H)


class TestSplitScreenFallback(unittest.TestCase):
    """3, 5, 6 … players fall back to horizontal strips."""

    def test_three_players_horizontal_strips(self):
        cfg = _make_split(3)
        vps = compute_viewports(cfg, W, H)
        self.assertEqual(len(vps), 3)
        for vp in vps:
            self.assertEqual(vp.w, W)
            self.assertAlmostEqual(vp.h, H / 3)

    def test_strips_are_contiguous(self):
        cfg = _make_split(3)
        vps = compute_viewports(cfg, W, H)
        sorted_vps = sorted(vps, key=lambda v: v.y)
        for i in range(len(sorted_vps) - 1):
            self.assertAlmostEqual(
                sorted_vps[i].y + sorted_vps[i].h,
                sorted_vps[i + 1].y,
            )

    def test_single_split_screen_player_fills_screen(self):
        cfg = _make_split(1)
        vps = compute_viewports(cfg, W, H)
        self.assertEqual(len(vps), 1)
        self.assertEqual(vps[0].w, W)
        self.assertEqual(vps[0].h, H)

    def test_zero_slots_returns_empty(self):
        cfg = MultiplayerConfig(player_slots=(), topology=TOPOLOGY_SPLIT_SCREEN)
        vps = compute_viewports(cfg, W, H)
        self.assertEqual(vps, [])


class TestViewportCoverage(unittest.TestCase):
    """General invariant: viewports must tile the screen without gaps or overlaps."""

    def _total_area(self, vps: list[ViewportAssignment]) -> float:
        return sum(vp.w * vp.h for vp in vps)

    def test_all_topologies_cover_full_screen(self):
        cases = [
            MultiplayerConfig.single_player(),
            MultiplayerConfig.local_two_player_shared(),
            MultiplayerConfig.local_two_player_split(),
            _make_split(4),
            MultiplayerConfig.network_host(),
        ]
        for cfg in cases:
            with self.subTest(topology=cfg.topology, n=cfg.player_count):
                vps = compute_viewports(cfg, W, H)
                self.assertAlmostEqual(self._total_area(vps), W * H)


if __name__ == "__main__":
    unittest.main()
