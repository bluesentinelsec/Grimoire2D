"""Models layer (data models).

Pure value objects and data containers (configs, world states, etc.).
No behavior, no side effects. See proposal 0001.
"""

from .config import EngineConfig

__all__ = ["EngineConfig"]