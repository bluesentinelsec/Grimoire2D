"""Grimoire2D exceptions.

All library-specific exceptions inherit from GrimoireError.
"""

from __future__ import annotations


class GrimoireError(Exception):
    """Base exception for all Grimoire2D errors."""


class AssetError(GrimoireError):
    """Error related to the VFS or asset loading."""


class AssetNotFound(AssetError, FileNotFoundError):
    """Requested asset was not found in any mounted provider."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Asset not found: {path}")
