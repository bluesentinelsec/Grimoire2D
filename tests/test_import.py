"""Minimal test using only the standard library unittest module.

This verifies that the package installs and can be imported cleanly.

When running without an editable install, the test adds src/ to sys.path
using only stdlib facilities (pathlib + sys).
"""

import sys
import unittest
from pathlib import Path

# Support running tests directly or via discover before `pip install -e .`
_src = Path(__file__).parent.parent / "src"
if _src.exists():
    sys.path.insert(0, str(_src))

import grimoire2d as g2d


class TestGrimoire2DImport(unittest.TestCase):
    def test_version_is_string(self):
        self.assertIsInstance(g2d.__version__, str)
        self.assertGreater(len(g2d.__version__), 0)

    def test_subpackages_exist(self):
        # These will grow in later chunks; for now just confirm the packages are importable
        # (models for data, logic for business rules, presentation for front-end)
        import grimoire2d.logic  # noqa: F401
        import grimoire2d.models  # noqa: F401
        import grimoire2d.presentation  # noqa: F401


if __name__ == "__main__":
    unittest.main()