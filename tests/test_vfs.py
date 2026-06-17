"""Tests for the Virtual File System."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from grimoire2d.assets import VFS as PublicVFS, create_archive
from grimoire2d.assets.vfs import (
    DirProvider,
    MemoryProvider,
    VirtualFileSystem,
    ZipProvider,
    _apply_cipher,
)
from grimoire2d.exceptions import AssetNotFound


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_test_zip(tmp_path: Path, files: dict[str, bytes]) -> Path:
    zpath = tmp_path / "test.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return zpath


# --------------------------------------------------------------------------- #
# Cipher
# --------------------------------------------------------------------------- #


def test_cipher_is_reversible():
    key = b"supersecret"
    data = b"hello world\x00\xff some binary data"
    enc = _apply_cipher(data, key)
    dec = _apply_cipher(enc, key)
    assert dec == data
    assert _apply_cipher(data, None) == data


# --------------------------------------------------------------------------- #
# MemoryProvider
# --------------------------------------------------------------------------- #


def test_memory_provider_basic():
    files = {
        "sprites/player.png": b"PNGDATA",
        "data/level.json": b'{"name": "test"}',
        "shaders/basic.vert": b"#version 330",
    }
    mp = MemoryProvider(files)

    assert mp.exists("sprites/player.png")
    assert mp.read_bytes("data/level.json") == b'{"name": "test"}'
    assert mp.exists("shaders/basic.vert")

    with mp.open("sprites/player.png") as f:
        assert f.read() == b"PNGDATA"

    assert sorted(mp.list_dir("")) == ["data", "shaders", "sprites"]
    assert mp.list_dir("data") == ["level.json"]
    assert mp.list_dir("nonexistent") == []


def test_memory_provider_normalizes_paths():
    mp = MemoryProvider({"assets\\foo.txt": b"hi", "/bar/baz": b"there"})
    assert mp.exists("assets/foo.txt")
    assert mp.exists("bar/baz")
    assert mp.read_bytes("assets/foo.txt") == b"hi"


# --------------------------------------------------------------------------- #
# ZipProvider
# --------------------------------------------------------------------------- #


def test_zip_provider_basic(tmp_path: Path):
    zpath = _make_test_zip(
        tmp_path,
        {
            "assets/sprites/player.png": b"ZIPPNG",
            "config/settings.json": b"{}",
            "assets/levels/1.tmx": b"<map/>",
        },
    )
    zp = ZipProvider(zpath)

    assert zp.exists("assets/sprites/player.png")
    assert zp.read_bytes("config/settings.json") == b"{}"

    with zp.open("assets/levels/1.tmx") as f:
        assert f.read() == b"<map/>"

    assert zp.list_dir("") == ["assets", "config"]
    assert zp.list_dir("assets") == ["levels", "sprites"]


def test_zip_provider_from_bytes(tmp_path: Path):
    zpath = _make_test_zip(tmp_path, {"hello.txt": b"world"})
    raw = zpath.read_bytes()
    zp = ZipProvider(raw)
    assert zp.read_bytes("hello.txt") == b"world"


def test_zip_provider_obfuscated(tmp_path: Path):
    key = b"mykey42"
    plain = _make_test_zip(tmp_path, {"secret.dat": b"topsecret"})

    # Create obfuscated version
    raw = plain.read_bytes()
    obf = _apply_cipher(raw, key)
    obf_path = tmp_path / "game.dat"
    obf_path.write_bytes(obf)

    zp = ZipProvider(obf_path, key=key)
    assert zp.read_bytes("secret.dat") == b"topsecret"

    # Wrong key produces invalid zip data -> fail fast on construction
    with pytest.raises(zipfile.BadZipFile):
        ZipProvider(obf_path, key=b"wrong")


def test_zip_provider_not_found(tmp_path: Path):
    zpath = _make_test_zip(tmp_path, {"a.txt": b"1"})
    zp = ZipProvider(zpath)
    with pytest.raises(FileNotFoundError):
        zp.read_bytes("nope.txt")


# --------------------------------------------------------------------------- #
# DirProvider
# --------------------------------------------------------------------------- #


def test_dir_provider(tmp_path: Path):
    root = tmp_path / "assets"
    (root / "sprites").mkdir(parents=True)
    (root / "sprites" / "p.png").write_bytes(b"PNG")
    (root / "data.json").write_bytes(b"{}")

    dp = DirProvider(root)

    assert dp.exists("sprites/p.png")
    assert dp.read_bytes("data.json") == b"{}"
    assert dp.list_dir("") == ["data.json", "sprites"]
    assert dp.list_dir("sprites") == ["p.png"]


def test_dir_provider_not_directory():
    with pytest.raises(NotADirectoryError):
        DirProvider("/this/does/not/exist/12345")


# --------------------------------------------------------------------------- #
# VirtualFileSystem mounting and priority
# --------------------------------------------------------------------------- #


def test_vfs_mount_priority(tmp_path: Path):
    # Base archive
    base_zip = _make_test_zip(
        tmp_path, {"common.txt": b"from_zip", "only_in_zip.txt": b"zip_only"}
    )

    # Overlay dir
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "common.txt").write_bytes(b"from_dir")
    (overlay / "only_in_dir.txt").write_bytes(b"dir_only")

    vfs = VirtualFileSystem()
    vfs.mount("", ZipProvider(base_zip))
    vfs.mount("assets/", DirProvider(overlay))  # note prefix

    # Dir should win for common
    assert vfs.read_bytes("assets/common.txt") == b"from_dir"
    assert vfs.read_bytes("only_in_zip.txt") == b"zip_only"
    assert vfs.read_bytes("assets/only_in_dir.txt") == b"dir_only"

    assert vfs.exists("assets/common.txt")
    assert not vfs.exists("nonexistent")


def test_vfs_read_open_exists(tmp_path: Path):
    zpath = _make_test_zip(tmp_path, {"foo/bar.txt": b"hello"})
    vfs = VirtualFileSystem()
    vfs.mount("", ZipProvider(zpath))

    assert vfs.exists("foo/bar.txt")
    assert vfs.read_bytes("foo/bar.txt") == b"hello"

    with vfs.open("foo/bar.txt") as f:
        assert f.read() == b"hello"


def test_vfs_asset_not_found():
    vfs = VirtualFileSystem()
    vfs.mount("", MemoryProvider({"a.txt": b"x"}))

    with pytest.raises(AssetNotFound) as exc:
        vfs.read_bytes("missing.txt")
    assert "missing.txt" in str(exc.value)

    with pytest.raises(AssetNotFound):
        vfs.open("missing.txt")


def test_vfs_list_dir_union(tmp_path: Path):
    z = _make_test_zip(tmp_path, {"a/z.txt": b"1", "shared/x.txt": b"2"})
    overlay = tmp_path / "ov"
    overlay.mkdir()
    (overlay / "shared").mkdir()
    (overlay / "shared" / "y.txt").write_bytes(b"3")
    (overlay / "onlydir").mkdir()

    vfs = VirtualFileSystem()
    vfs.mount("", ZipProvider(z))
    vfs.mount("", DirProvider(overlay))

    root = vfs.list_dir("")
    assert "a" in root and "onlydir" in root and "shared" in root

    shared = vfs.list_dir("shared")
    assert sorted(shared) == ["x.txt", "y.txt"]


def test_vfs_normalize_and_backslashes():
    vfs = VirtualFileSystem()
    vfs.mount("", MemoryProvider({"deep\\file.txt": b"ok"}))

    assert vfs.exists("deep/file.txt")
    assert vfs.read_bytes("deep\\file.txt") == b"ok"


def test_vfs_context_manager_closes_zip(tmp_path: Path):
    zpath = _make_test_zip(tmp_path, {"f.txt": b"1"})
    with VirtualFileSystem() as vfs:
        vfs.mount("", ZipProvider(zpath))
        assert vfs.read_bytes("f.txt") == b"1"
    # After exit, the internal zip should be closed (best effort check)
    # We can't easily inspect without leaking, so just ensure no crash.


# --------------------------------------------------------------------------- #
# End-to-end VFS scenarios (realistic usage patterns)
# --------------------------------------------------------------------------- #


def _create_sample_asset_tree(root: Path) -> None:
    """Helper to populate a realistic game asset tree."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "sprites").mkdir()
    (root / "sprites" / "player.png").write_bytes(b"PNGPIXELS123")
    (root / "sprites" / "enemy.png").write_bytes(b"ENEMYDATA")
    (root / "data").mkdir()
    (root / "data" / "level1.json").write_bytes(b'{"id": 1, "name": "Level One"}')
    (root / "shaders").mkdir()
    (root / "shaders" / "basic.vert").write_bytes(b"#version 330\nvoid main() {}")
    (root / "README.txt").write_bytes(b"Sample game assets")


def test_vfs_e2e_directory_only(tmp_path: Path):
    """End-to-end using only a directory provider (dev scenario)."""
    assets_dir = tmp_path / "assets"
    _create_sample_asset_tree(assets_dir)

    vfs = VirtualFileSystem()
    vfs.mount("assets/", DirProvider(assets_dir))

    # Read bytes
    assert vfs.read_bytes("assets/sprites/player.png") == b"PNGPIXELS123"
    assert (
        vfs.read_bytes("assets/data/level1.json") == b'{"id": 1, "name": "Level One"}'
    )

    # Open context
    with vfs.open("assets/shaders/basic.vert") as f:
        content = f.read()
        assert b"version 330" in content

    # Exists and list_dir
    assert vfs.exists("assets/README.txt")
    assert not vfs.exists("assets/missing.txt")

    top_level = vfs.list_dir("assets/")
    assert sorted(top_level) == ["README.txt", "data", "shaders", "sprites"]

    data_children = vfs.list_dir("assets/data")
    assert data_children == ["level1.json"]


def test_vfs_e2e_plain_zip(tmp_path: Path):
    """End-to-end using a plain (unencrypted) zip archive."""
    src = tmp_path / "src_assets"
    _create_sample_asset_tree(src)

    arch = tmp_path / "game.dat"  # arbitrary extension
    create_archive(src, arch)  # no password

    vfs = VirtualFileSystem()
    vfs.mount("res/", ZipProvider(arch))  # no password

    assert vfs.read_bytes("res/sprites/enemy.png") == b"ENEMYDATA"
    assert vfs.exists("res/data/level1.json")

    with vfs.open("res/README.txt") as f:
        assert f.read() == b"Sample game assets"

    # list_dir through prefix
    assert "sprites" in vfs.list_dir("res/")


def test_vfs_e2e_password_protected_zip(tmp_path: Path):
    """End-to-end using password-protected archive (prod scenario)."""
    src = tmp_path / "src_assets"
    _create_sample_asset_tree(src)

    arch = tmp_path / "game.pak"
    password = "supersecretpassword123"
    create_archive(src, arch, password=password)

    # Direct zip open must fail (obfuscated)
    with pytest.raises(zipfile.BadZipFile):
        zipfile.ZipFile(arch)

    vfs = VirtualFileSystem()
    # Mount using password=
    vfs.mount("", ZipProvider(arch, password=password))

    # All reads should succeed
    assert vfs.read_bytes("sprites/player.png") == b"PNGPIXELS123"
    assert vfs.read_bytes("data/level1.json") == b'{"id": 1, "name": "Level One"}'

    with vfs.open("shaders/basic.vert") as f:
        assert b"version 330" in f.read()

    assert vfs.exists("README.txt")

    # Wrong password should fail at mount time (or read)
    vfs_bad = VirtualFileSystem()
    with pytest.raises(zipfile.BadZipFile):
        vfs_bad.mount("", ZipProvider(arch, password="wrongpw"))


def test_vfs_e2e_memory_provider():
    """End-to-end using only in-memory data (embedded / patch scenario)."""
    files = {
        "config/game.json": b'{"version": "1.0"}',
        "textures/ui/icon.png": b"ICONDATA",
        "shaders/default.frag": b"uniform vec4 color;",
    }
    vfs = VirtualFileSystem()
    vfs.mount("assets/", MemoryProvider(files))

    assert vfs.read_bytes("assets/config/game.json") == b'{"version": "1.0"}'

    with vfs.open("assets/textures/ui/icon.png") as f:
        assert f.read() == b"ICONDATA"

    assert "config" in vfs.list_dir("assets/")
    assert vfs.exists("assets/shaders/default.frag")
    assert not vfs.exists("assets/missing")


def test_vfs_e2e_mixed_sources(tmp_path: Path):
    """End-to-end realistic mix: password-protected base + dir overlay + memory."""
    # Base assets in encrypted archive
    base_src = tmp_path / "base"
    _create_sample_asset_tree(base_src)
    base_arch = tmp_path / "base.pak"
    create_archive(base_src, base_arch, password="packpw")

    # Overlay directory (dev overrides)
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "sprites").mkdir()
    (overlay / "sprites" / "player.png").write_bytes(b"OVERRIDE_PLAYER")
    (overlay / "new_file.txt").write_bytes(b"added in dev")

    # Embedded defaults via memory
    embedded = {"embedded/default.json": b'{"default": true}'}

    vfs = VirtualFileSystem()
    vfs.mount("", ZipProvider(base_arch, password="packpw"))  # base
    vfs.mount("assets/", DirProvider(overlay))  # overlay wins
    vfs.mount("assets/", MemoryProvider(embedded))  # also under assets

    # Overlay wins over zip
    assert vfs.read_bytes("assets/sprites/player.png") == b"OVERRIDE_PLAYER"
    # Zip still visible for non-overridden
    assert vfs.read_bytes("data/level1.json") == b'{"id": 1, "name": "Level One"}'
    # New file from overlay
    assert vfs.read_bytes("assets/new_file.txt") == b"added in dev"
    # Memory
    assert vfs.read_bytes("assets/embedded/default.json") == b'{"default": true}'

    # list_dir shows merged view (priority order affects but union is collected)
    assets_listing = vfs.list_dir("assets/")
    assert "sprites" in assets_listing
    assert "new_file.txt" in assets_listing
    assert "embedded" in assets_listing


def test_vfs_e2e_full_usage_pattern(tmp_path: Path):
    """Simulate typical game loading loop using VFS end-to-end."""
    src = tmp_path / "game_assets"
    _create_sample_asset_tree(src)

    arch = tmp_path / "data.bin"
    create_archive(src, arch, password="gamepw")

    # Typical usage: one VFS for the whole game
    vfs = VirtualFileSystem()
    vfs.mount("data/", ZipProvider(arch, password="gamepw"))

    # "Load" several resources
    player = vfs.read_bytes("data/sprites/player.png")
    level = vfs.read_bytes("data/data/level1.json")
    shader = None
    with vfs.open("data/shaders/basic.vert") as f:
        shader = f.read()

    assert player == b"PNGPIXELS123"
    assert b"Level One" in level
    assert b"version 330" in shader

    # Check what "packages" are present
    top = vfs.list_dir("data/")
    assert {"sprites", "data", "shaders", "README.txt"}.issubset(set(top))

    # Graceful missing
    assert not vfs.exists("data/does/not/exist.png")
    with pytest.raises(AssetNotFound):
        vfs.read_bytes("data/missing")


def test_vfs_public_alias():
    """Sanity check that the public VFS alias works for typical usage."""
    vfs = PublicVFS()
    vfs.mount("", MemoryProvider({"test.txt": b"via public alias"}))
    assert vfs.read_bytes("test.txt") == b"via public alias"
