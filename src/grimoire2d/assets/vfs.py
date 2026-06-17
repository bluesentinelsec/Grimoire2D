"""Virtual File System (VFS).

The single source of truth for all asset loading in Grimoire2D.

Mount providers under prefixes. Later mounts take priority (enables
dev directory overlay over a base archive).

All asset loads in the engine **must** go through an instance of VFS.

Supported sources:
- Real directories (dev + hot reload)
- Zip archives, optionally obfuscated with a simple password-based cipher (prod)
  Use :mod:`grimoire2d.assets.archive` to create such archives.
- In-memory byte arrays (embedded resources, tests, runtime data)

Typical usage::

    from grimoire2d.assets.vfs import VFS, DirProvider, ZipProvider, MemoryProvider

    vfs = VFS()
    vfs.mount("assets/", DirProvider("assets/"))           # dev overlay
    vfs.mount("", ZipProvider("game.dat"))                 # base content

    png = vfs.read_bytes("assets/sprites/player.png")
    with vfs.open("levels/1.json") as f:
        ...
"""

from __future__ import annotations

import zipfile
from abc import abstractmethod
from io import BytesIO
from os import PathLike
from pathlib import Path
from typing import BinaryIO, Protocol

from ..exceptions import AssetNotFound


# --------------------------------------------------------------------------- #
# Provider protocol
# --------------------------------------------------------------------------- #


class Provider(Protocol):
    """Protocol for a VFS backing store."""

    @abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """Return the full contents of the file at the given (normalized) path."""
        ...

    @abstractmethod
    def open(self, path: str) -> BinaryIO:
        """Return an open binary file handle for the given path.

        The returned object must be usable as a context manager
        (i.e. ``with provider.open(...) as f:``).
        """
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Return True if a file (not directory) exists at the path."""
        ...

    @abstractmethod
    def list_dir(self, path: str) -> list[str]:
        """Return immediate children (files and subdirectories) under the path.

        Names are relative (no leading path). Directory names do not end with '/'.
        """
        ...


# --------------------------------------------------------------------------- #
# Simple obfuscation (casual protection only)
# --------------------------------------------------------------------------- #


def _derive_key(password: str | None) -> bytes | None:
    """Derive an obfuscation key from a password.

    This is a simple, non-cryptographic derivation. The result is used
    with _apply_cipher for casual protection only (to discourage casual
    tampering or inspection of game data).
    """
    if not password:
        return None
    pw = password.encode("utf-8")
    # Repeat the password bytes to produce a reasonably long key.
    # XOR will cycle through it anyway.
    return (pw * 32)[:256]


def _apply_cipher(data: bytes, key: bytes | None) -> bytes:
    """Apply a simple reversible XOR cipher.

    This is **not** real cryptography. It provides only casual protection
    against casual inspection or accidental extraction. The transform is
    its own inverse.
    """
    if not key:
        return data
    klen = len(key)
    return bytes(b ^ key[i % klen] for i, b in enumerate(data))


# --------------------------------------------------------------------------- #
# Concrete providers
# --------------------------------------------------------------------------- #


class DirProvider:
    """Provider backed by a real directory on disk.

    Intended primarily for development. Supports hot-reload scenarios
    because the underlying files can change between reads.
    """

    def __init__(self, root: str | PathLike[str]) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"DirProvider root is not a directory: {root}")

    def _full_path(self, path: str) -> Path:
        # path is already normalized (no leading /)
        return self.root / path

    def read_bytes(self, path: str) -> bytes:
        fp = self._full_path(path)
        if not fp.is_file():
            raise FileNotFoundError(path)
        return fp.read_bytes()

    def open(self, path: str) -> BinaryIO:
        fp = self._full_path(path)
        if not fp.is_file():
            raise FileNotFoundError(path)
        return fp.open("rb")

    def exists(self, path: str) -> bool:
        return self._full_path(path).is_file()

    def list_dir(self, path: str) -> list[str]:
        fp = self._full_path(path)
        if not fp.is_dir():
            return []
        names: list[str] = []
        for child in fp.iterdir():
            if child.is_file() or child.is_dir():
                names.append(child.name)
        names.sort()
        return names


class ZipProvider:
    """Provider backed by a zip archive.

    The archive may be provided as a filesystem path or as raw bytes.

    Obfuscation:
      - Pass `password` (recommended) for simple symmetric obfuscation.
      - Or pass a raw `key` (advanced use).
      - The same password/key used to create the archive must be used here.

    See `_derive_key` and `_apply_cipher` for the (non-cryptographic)
    obfuscation details. This is only intended to discourage casual
    inspection or modification of a game's data files.

    The entire archive is loaded into memory on construction.
    """

    def __init__(
        self,
        source: str | PathLike[str] | bytes,
        *,
        password: str | None = None,
        key: bytes | None = None,
    ) -> None:
        if isinstance(source, (str, Path, PathLike)):
            raw = Path(source).read_bytes()
        elif isinstance(source, (bytes, bytearray)):
            raw = bytes(source)
        else:
            raise TypeError("ZipProvider source must be path or bytes")

        if password is not None:
            key = _derive_key(password)

        archive_bytes = _apply_cipher(raw, key)

        self._zip = zipfile.ZipFile(BytesIO(archive_bytes))
        # Precompute a set of files for fast exists / resolution.
        # We only care about actual files (not directory entries zip may contain).
        self._files: set[str] = {n for n in self._zip.namelist() if not n.endswith("/")}

    def read_bytes(self, path: str) -> bytes:
        if path not in self._files:
            raise FileNotFoundError(path)
        with self._zip.open(path) as f:
            return f.read()

    def open(self, path: str) -> BinaryIO:
        if path not in self._files:
            raise FileNotFoundError(path)
        # zipfile.open returns a file-like that is closeable.
        return self._zip.open(path)

    def exists(self, path: str) -> bool:
        return path in self._files

    def list_dir(self, path: str) -> list[str]:
        if path and not path.endswith("/"):
            path = path + "/"
        elif not path:
            path = ""

        children: set[str] = set()
        for name in self._files:
            if name.startswith(path):
                remainder = name[len(path) :]
                if not remainder:
                    continue
                # Take only the first segment
                first = remainder.split("/", 1)[0]
                children.add(first)
        return sorted(children)


class MemoryProvider:
    """Provider backed entirely by in-memory byte data.

    Useful for:
    - Embedded defaults
    - Test fixtures
    - Data received at runtime (e.g. downloaded patches)
    - Resources bundled inside PyInstaller or other single-file distributions
    """

    def __init__(self, files: dict[str, bytes]) -> None:
        # Normalize keys on construction
        self._files: dict[str, bytes] = {}
        for k, v in files.items():
            norm = _normalize_path(k)
            self._files[norm] = bytes(v)  # copy

    def read_bytes(self, path: str) -> bytes:
        norm = _normalize_path(path)
        if norm not in self._files:
            raise FileNotFoundError(path)
        return self._files[norm]

    def open(self, path: str) -> BinaryIO:
        data = self.read_bytes(path)
        return BytesIO(data)

    def exists(self, path: str) -> bool:
        return _normalize_path(path) in self._files

    def list_dir(self, path: str) -> list[str]:
        norm = _normalize_path(path)
        if norm:
            prefix = norm + "/"
        else:
            prefix = ""

        children: set[str] = set()
        for name in self._files:
            if name.startswith(prefix):
                remainder = name[len(prefix) :]
                if not remainder:
                    continue
                first = remainder.split("/", 1)[0]
                children.add(first)
        return sorted(children)


# --------------------------------------------------------------------------- #
# Path utilities
# --------------------------------------------------------------------------- #


def _normalize_path(path: str) -> str:
    """Normalize a user path to a canonical internal form.

    - Convert backslashes to forward slashes
    - Strip leading and trailing slashes
    - Collapse redundant slashes
    - Never return a path starting with '/'
    """
    if not path:
        return ""
    p = path.replace("\\", "/").strip("/")
    # Collapse multiple slashes
    while "//" in p:
        p = p.replace("//", "/")
    return p


def _strip_prefix(path: str, prefix: str) -> str | None:
    """If path starts with prefix, return the remainder (normalized)."""
    if not prefix:
        return path
    if path == prefix or path.startswith(prefix + "/"):
        remainder = path[len(prefix) :].lstrip("/")
        return remainder
    return None


# --------------------------------------------------------------------------- #
# VirtualFileSystem
# --------------------------------------------------------------------------- #


class VirtualFileSystem:
    """Mount-based virtual file system.

    Providers are tried in reverse mount order (last mounted wins).
    This makes it natural to mount a base archive first and a development
    directory last so that the directory overrides the archive.
    """

    def __init__(self) -> None:
        self._mounts: list[tuple[str, Provider]] = []

    def mount(self, prefix: str, provider: Provider) -> None:
        """Mount a provider under a path prefix.

        Example::
            vfs.mount("assets/", DirProvider("assets"))
            vfs.mount("", ZipProvider("game.dat"))
        """
        norm_prefix = _normalize_path(prefix)
        # Store with trailing slash for easy prefix math ("" is special)
        if norm_prefix and not norm_prefix.endswith("/"):
            norm_prefix = norm_prefix + "/"
        self._mounts.append((norm_prefix, provider))

    def _find_provider(self, path: str) -> tuple[Provider, str]:
        """Find a provider that can serve the path (prefix match + file exists).

        Tries mounts in reverse order (last mounted highest priority) so that
        overlays can provide a subset of files and fall back to earlier mounts.
        Raises AssetNotFound if no provider serves it.
        """
        norm = _normalize_path(path)
        for prefix, provider in reversed(self._mounts):
            if prefix == "":
                internal = norm
            else:
                remainder = _strip_prefix(norm, prefix.rstrip("/"))
                if remainder is None:
                    continue
                internal = remainder
            if provider.exists(internal):
                return provider, internal
        raise AssetNotFound(path)

    def read_bytes(self, path: str) -> bytes:
        """Read the entire contents of a file as bytes."""
        provider, internal = self._find_provider(path)
        return provider.read_bytes(internal)

    def open(self, path: str) -> BinaryIO:
        """Open a file for binary reading.

        The returned object is a context manager::

            with vfs.open("foo.txt") as f:
                data = f.read()
        """
        provider, internal = self._find_provider(path)
        return provider.open(internal)

    def exists(self, path: str) -> bool:
        """Return whether a file exists at the given path."""
        try:
            self._find_provider(path)
            return True
        except AssetNotFound:
            return False

    def list_dir(self, path: str = "") -> list[str]:
        """List immediate children under a directory path.

        Returns a sorted list of names (files and subdirectories).
        Subdirectory names do not carry a trailing slash.
        """
        norm = _normalize_path(path)
        results: set[str] = set()

        # Collect from all mounts that could contribute (in priority order)
        for prefix, provider in reversed(self._mounts):
            if prefix == "":
                candidate = norm
            else:
                remainder = _strip_prefix(norm, prefix.rstrip("/"))
                if remainder is None:
                    continue
                candidate = remainder

            try:
                children = provider.list_dir(candidate)
            except Exception:  # defensive; providers should not raise here
                continue

            for child in children:
                # Re-attach the original mount prefix for uniqueness? No:
                # we return logical names under the requested path.
                results.add(child)

        return sorted(results)

    def close(self) -> None:
        """Close any resources held by mounted providers (e.g. zip files).

        Safe to call multiple times. Most users do not need to call this
        explicitly; the process exit is usually sufficient.
        """
        for _, provider in self._mounts:
            if isinstance(provider, ZipProvider):
                provider._zip.close()  # type: ignore[attr-defined]
        self._mounts.clear()

    def __enter__(self) -> VirtualFileSystem:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# Public alias (shorter, matches "the game is just data" terminology and docs)
VFS = VirtualFileSystem
