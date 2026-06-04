"""Unit tests for the pure data model layer (Chunk 1).

Uses only the standard library (unittest + dataclasses).
No caller logic, no VFS, no presentation or logic layers involved.
Tests are isolated to models/ only.
"""

import sys
import unittest
from pathlib import Path

# Support running tests directly or via discover before `pip install -e .`
_src = Path(__file__).parent.parent / "src"
if _src.exists():
    sys.path.insert(0, str(_src))

from grimoire2d.models import EngineConfig


class TestEngineConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = EngineConfig()
        self.assertEqual(cfg.title, "Grimoire2D")
        self.assertEqual(cfg.width, 800)
        self.assertEqual(cfg.height, 600)
        self.assertEqual(cfg.target_fps, 60)
        self.assertTrue(cfg.vsync)
        self.assertEqual(cfg.clear_color, (0, 0, 0, 255))
        self.assertEqual(cfg.version, 1)

    def test_custom_construction(self):
        cfg = EngineConfig(title="Test", width=640, height=480, target_fps=30)
        self.assertEqual(cfg.title, "Test")
        self.assertEqual(cfg.width, 640)
        self.assertEqual(cfg.height, 480)
        self.assertEqual(cfg.target_fps, 30)

    def test_post_init_validation(self):
        with self.assertRaises(ValueError):
            EngineConfig(width=0)
        with self.assertRaises(ValueError):
            EngineConfig(height=-100)
        with self.assertRaises(ValueError):
            EngineConfig(target_fps=0)
        with self.assertRaises(ValueError):
            EngineConfig(clear_color=(300, 0, 0, 255))

    def test_equality(self):
        cfg1 = EngineConfig(title="Foo")
        cfg2 = EngineConfig(title="Foo")
        cfg3 = EngineConfig(title="Bar")
        self.assertEqual(cfg1, cfg2)
        self.assertNotEqual(cfg1, cfg3)

    def test_to_dict_and_from_dict_roundtrip(self):
        original = EngineConfig(title="MyGame", width=1024, height=768, clear_color=(255, 128, 0, 255))
        d = original.to_dict()
        restored = EngineConfig.from_dict(d)
        self.assertEqual(original, restored)
        self.assertEqual(d["version"], 1)

    def test_from_dict_ignores_unknown_keys(self):
        data = {"title": "Foo", "width": 100, "height": 100, "extra": "ignored", "version": 2}
        cfg = EngineConfig.from_dict(data)
        self.assertEqual(cfg.title, "Foo")
        self.assertEqual(cfg.version, 2)

    def test_with_updates_returns_new_instance(self):
        original = EngineConfig(title="Original", target_fps=60)
        updated = original.with_updates(title="Updated", target_fps=120)
        self.assertIsNot(original, updated)
        self.assertEqual(original.title, "Original")
        self.assertEqual(original.target_fps, 60)
        self.assertEqual(updated.title, "Updated")
        self.assertEqual(updated.target_fps, 120)
        # Original unchanged
        self.assertEqual(original.title, "Original")

    def test_serialization_after_update(self):
        cfg = EngineConfig().with_updates(title="Updated", vsync=False)
        d = cfg.to_dict()
        self.assertEqual(d["title"], "Updated")
        self.assertFalse(d["vsync"])


if __name__ == "__main__":
    unittest.main()