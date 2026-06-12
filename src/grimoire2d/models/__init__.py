"""Models layer (data models).

Pure value objects and data containers (configs, world states, etc.).
No behavior, no side effects. See proposal 0001.

EngineConfig contains *only* an extensions dict (no hard-coded members).
All configuration, common or game-specific, is delivered via registered
DataModel extensions. This guarantees every addition is purely net-new code.

See models/base.py for the DataModel protocol.
Games define their own models and compose (see EngineConfig docstring).
"""

from . import title
from . import video
from . import timing
from . import lifecycle
from . import input
from . import app_state
from . import window_settings
from . import build_config

from .base import DataModel, register_extension
from .config import EngineConfig
from .app_state import AppState

# Re-export the individual models for convenience
from .title import TitleSetting
from .video import VideoSettings
from .timing import TimingSettings
from .lifecycle import LifecycleState
from .input import InputState
from .window_settings import WindowSettings
from .build_config import BuildConfig

__all__ = [
    "DataModel",
    "register_extension",
    "EngineConfig",
    "AppState",
    "TitleSetting",
    "VideoSettings",
    "TimingSettings",
    "LifecycleState",
    "InputState",
    "WindowSettings",
    "BuildConfig",
]