"""Assets and Virtual File System.

All asset loading in Grimoire2D **must** go through the VFS.

The `archive` submodule provides helpers to create and extract
(possibly obfuscated) zip-based archives.

Example::

    from grimoire2d.assets import archive
    from grimoire2d.assets.vfs import VFS, ZipProvider
    # or
    import grimoire2d.assets.vfs as vfs
"""

from __future__ import annotations

from . import archive, vfs
from .archive import create_archive, extract_archive
from .vfs import (
    DirProvider,
    MemoryProvider,
    VFS,
    VirtualFileSystem,
    ZipProvider,
)

__all__ = [
    "archive",
    "create_archive",
    "extract_archive",
    "vfs",
    "VFS",
    "VirtualFileSystem",
    "DirProvider",
    "ZipProvider",
    "MemoryProvider",
]
