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
)


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


if __name__ == "__main__":
    unittest.main()