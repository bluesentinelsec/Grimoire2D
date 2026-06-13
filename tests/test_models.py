"""Unit tests for the data model layer supporting the minimal window + ESC milestone.

All tests use only the standard library (unittest + dataclasses).
Models are tested in isolation (pure data, no logic or presentation).
"""

import sys
import unittest
from dataclasses import dataclass, field, replace
from pathlib import Path

# Support running tests directly or via discover before `pip install -e .`
_src = Path(__file__).parent.parent / "src"
if _src.exists():
    sys.path.insert(0, str(_src))

from grimoire2d.models import (
    EngineConfig,
    DataModel,
    LifecycleState,
    InputState,
    AppState,
    VirtualResolution,
)
from grimoire2d.logic.scaling import Viewport, compute_viewport, get_virtual_resolution


class TestLifecycleState(unittest.TestCase):
    def test_defaults(self):
        state = LifecycleState()
        self.assertTrue(state.is_running)
        self.assertFalse(state.should_quit)
        self.assertIsNone(state.quit_reason)

    def test_with_updates_and_serialization(self):
        state = LifecycleState()
        updated = state.with_updates(should_quit=True, quit_reason="escape_pressed")
        self.assertTrue(updated.should_quit)
        self.assertEqual(updated.quit_reason, "escape_pressed")
        d = updated.to_dict()
        restored = LifecycleState.from_dict(d)
        self.assertEqual(restored, updated)


class TestInputState(unittest.TestCase):
    def test_defaults(self):
        state = InputState()
        self.assertEqual(len(state.pressed_keys), 0)

    def test_is_key_pressed_and_serialization(self):
        state = InputState(pressed_keys=frozenset(["escape", "a"]))
        self.assertTrue(state.is_key_pressed("escape"))
        self.assertFalse(state.is_key_pressed("b"))
        d = state.to_dict()
        restored = InputState.from_dict(d)
        self.assertEqual(restored, state)

    def test_with_updates(self):
        state = InputState()
        updated = state.with_updates(pressed_keys=frozenset(["escape"]))
        self.assertIn("escape", updated.pressed_keys)


class TestAppState(unittest.TestCase):
    def test_default(self):
        state = AppState.default()
        self.assertIsInstance(state.engine, EngineConfig)
        self.assertIsInstance(state.lifecycle, LifecycleState)
        self.assertIsInstance(state.input, InputState)
        self.assertTrue(state.lifecycle.is_running)

    def test_composition_for_milestone(self):
        """Demonstrates data for the high-level goal: window + terminate on escape."""
        state = AppState.default()
        # Simulate "ESC pressed" in input data (will be set by future input layer)
        state = state.with_updates(
            input={"pressed_keys": ["escape"]},
            lifecycle={"should_quit": True, "quit_reason": "escape_pressed", "is_running": False},
        )
        self.assertIn("escape", state.input.pressed_keys)
        self.assertTrue(state.lifecycle.should_quit)
        self.assertEqual(state.lifecycle.quit_reason, "escape_pressed")
        self.assertFalse(state.lifecycle.is_running)

    def test_game_specific_composition(self):
        """Shows how game-specific data models are added via composition (not inheritance)."""
        @dataclass(frozen=True, slots=True)
        class PlayerState(DataModel):
            health: int = 100
            version: int = 1

            def to_dict(self):
                return {"health": self.health, "version": self.version}

            @classmethod
            def from_dict(cls, data):
                return cls(health=data.get("health", 100), version=data.get("version", 1))

            def with_updates(self, **changes):
                return replace(self, **changes)

        @dataclass(frozen=True, slots=True)
        class MyGameState(DataModel):
            """Example of a game composing AppState components + own data."""
            app: AppState = field(default_factory=AppState.default)
            player: PlayerState = field(default_factory=PlayerState)
            version: int = 1

            def to_dict(self):
                return {
                    "app": self.app.to_dict(),
                    "player": self.player.to_dict(),
                    "version": self.version,
                }

            @classmethod
            def from_dict(cls, data):
                return cls(
                    app=AppState.from_dict(data.get("app", {})),
                    player=PlayerState.from_dict(data.get("player", {})),
                    version=data.get("version", 1),
                )

            def with_updates(self, **changes):
                if "app" in changes:
                    changes["app"] = self.app.with_updates(**changes["app"])
                if "player" in changes:
                    changes["player"] = self.player.with_updates(**changes["player"])
                return replace(self, **changes)

        game_state = MyGameState()
        game_state = game_state.with_updates(
            app={"lifecycle": {"should_quit": True, "quit_reason": "escape_pressed", "is_running": False}},
            player={"health": 75},
        )
        self.assertEqual(game_state.player.health, 75)
        self.assertTrue(game_state.app.lifecycle.should_quit)

    def test_roundtrip_serialization(self):
        state = AppState.default()
        d = state.to_dict()
        restored = AppState.from_dict(d)
        self.assertEqual(restored, state)


class TestVirtualResolution(unittest.TestCase):
    def test_default_is_1280x720(self):
        vr = VirtualResolution()
        self.assertEqual(vr.width, 1280)
        self.assertEqual(vr.height, 720)
        self.assertTrue(vr.integer_scaling)

    def test_custom_and_validation(self):
        vr = VirtualResolution(width=640, height=360, integer_scaling=False)
        self.assertEqual(vr.width, 640)
        self.assertFalse(vr.integer_scaling)

        with self.assertRaises(ValueError):
            VirtualResolution(width=0, height=720)

        with self.assertRaises(ValueError):
            VirtualResolution(width=1280, height=-10)

    def test_roundtrip_and_with_updates(self):
        vr = VirtualResolution(width=1920, height=1080)
        d = vr.to_dict()
        restored = VirtualResolution.from_dict(d)
        self.assertEqual(restored, vr)

        updated = vr.with_updates(width=1280, height=720)
        self.assertEqual(updated.width, 1280)
        self.assertEqual(updated.height, 720)
        self.assertEqual(vr.width, 1920)  # original unchanged


class TestScalingLogic(unittest.TestCase):
    """Pure tests for the scaling / letterboxing math (no GL, no window)."""

    def test_exact_match(self):
        vr = VirtualResolution(width=1280, height=720)
        vp = compute_viewport(vr, 1280, 720)
        self.assertIsInstance(vp, Viewport)
        self.assertEqual(vp.scale, 1.0)
        self.assertEqual(vp.offset_x, 0)
        self.assertEqual(vp.offset_y, 0)
        self.assertEqual(vp.viewport_width, 1280)
        self.assertEqual(vp.viewport_height, 720)

    def test_wider_physical_pillarbox_integer(self):
        vr = VirtualResolution(width=1280, height=720, integer_scaling=True)
        vp = compute_viewport(vr, 1920, 720)
        self.assertEqual(vp.scale, 1.0)
        self.assertEqual(vp.offset_x, 320)
        self.assertEqual(vp.offset_y, 0)
        self.assertEqual(vp.viewport_width, 1280)

    def test_taller_physical_letterbox(self):
        vr = VirtualResolution(width=1280, height=720)
        vp = compute_viewport(vr, 1280, 1080)
        self.assertEqual(vp.scale, 1.0)
        self.assertEqual(vp.offset_y, 180)
        self.assertEqual(vp.viewport_height, 720)

    def test_integer_double_scale(self):
        vr = VirtualResolution(width=1280, height=720)
        vp = compute_viewport(vr, 2560, 1440)
        self.assertEqual(vp.scale, 2.0)
        self.assertEqual(vp.offset_x, 0)
        self.assertEqual(vp.offset_y, 0)
        self.assertEqual(vp.viewport_width, 2560)

    def test_fractional_when_integer_disabled(self):
        vr = VirtualResolution(width=1280, height=720, integer_scaling=False)
        # 1500x780 gives fractional scale limited by the height dimension
        vp = compute_viewport(vr, 1500, 780)
        self.assertAlmostEqual(vp.scale, 780 / 720, places=4)
        self.assertGreater(vp.offset_x, 0)

    def test_small_physical_downscales_to_show_full_logical_surface(self):
        """When the physical window is smaller than the virtual resolution,
        we must still show the *entire* logical scene, just scaled down.
        This was the reported issue: content must not disappear or collapse.
        """
        vr = VirtualResolution(width=1280, height=720)
        vp = compute_viewport(vr, 640, 360)
        self.assertAlmostEqual(vp.scale, 0.5, places=5)
        self.assertEqual(vp.viewport_width, 640)
        self.assertEqual(vp.viewport_height, 360)
        # The scaled logical surface exactly fits the physical window in this case
        self.assertLessEqual(vp.viewport_width, 640)
        self.assertLessEqual(vp.viewport_height, 360)

    def test_zero_physical_falls_back(self):
        vr = VirtualResolution(width=1280, height=720)
        vp = compute_viewport(vr, 0, 0)
        self.assertEqual(vp.physical_width, 1280)
        self.assertEqual(vp.physical_height, 720)

    def test_full_logical_surface_always_fits(self):
        """Core correctness property requested by the user.

        No matter what physical window size (as long as positive),
        the computed viewport must never be larger than the physical
        window in either dimension. This guarantees the entire logical
        (virtual) scene is always visible, just scaled + letterboxed.
        """
        vr = VirtualResolution(width=1280, height=720, integer_scaling=True)

        # A range of realistic shrinking, matching, and expanding cases
        physical_sizes = [
            (100, 100), (320, 200), (640, 360), (800, 450), (1000, 600),
            (1280, 720), (1280, 600), (1366, 768), (1440, 900),
            (1600, 900), (1920, 1080), (2560, 1440), (3000, 2000),
            (500, 2000), (2000, 500),  # extreme aspect ratios
        ]

        for pw, ph in physical_sizes:
            with self.subTest(physical=f"{pw}x{ph}"):
                vp = compute_viewport(vr, pw, ph)
                self.assertLessEqual(
                    vp.viewport_width, pw,
                    f"viewport wider than physical for {pw}x{ph}"
                )
                self.assertLessEqual(
                    vp.viewport_height, ph,
                    f"viewport taller than physical for {pw}x{ph}"
                )
                self.assertGreater(vp.scale, 0)
                self.assertGreaterEqual(vp.offset_x, 0)
                self.assertGreaterEqual(vp.offset_y, 0)

    def test_get_virtual_resolution_with_compute(self):
        """Integration between data model and scaling logic.

        This is how the presentation layer will actually use it at runtime.
        """
        from grimoire2d.models import EngineConfig

        engine = EngineConfig.default()
        # Replace the default with a non-standard virtual res
        engine = engine.with_updates(
            extensions={"virtual_resolution": VirtualResolution(640, 360)}
        )

        vr = get_virtual_resolution(engine)
        self.assertEqual(vr.width, 640)
        self.assertEqual(vr.height, 360)

        vp = compute_viewport(vr, 1280, 720)
        self.assertEqual(vp.scale, 2.0)  # integer upscaling from 640x360
        self.assertEqual(vp.viewport_width, 1280)
        self.assertEqual(vp.viewport_height, 720)


if __name__ == "__main__":
    unittest.main()