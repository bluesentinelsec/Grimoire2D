"""Tests for archive creation, extraction, and obfuscation.

These tests prove that:
- Plain archives (no password) are standard zip files.
- Password-protected archives are not valid zips until de-obfuscated.
- Roundtrips (create -> extract) preserve file contents and directory structure.
- The same mechanism works when loading via ZipProvider.
- Wrong password fails appropriately.
- No third-party libraries are required.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from grimoire2d.assets import create_archive, extract_archive
from grimoire2d.assets.vfs import VFS, ZipProvider


def _write_tree(root: Path, tree: dict[str, bytes | dict]) -> None:
    """Helper to create a nested file tree for testing."""
    root.mkdir(parents=True, exist_ok=True)
    for name, content in tree.items():
        p = root / name
        if isinstance(content, dict):
            _write_tree(p, content)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)


def test_create_and_extract_plain(tmp_path: Path):
    src = tmp_path / "src"
    _write_tree(
        src,
        {
            "readme.txt": b"Hello world",
            "data": {
                "level1.json": b'{"name": "level1"}',
                "sprites": {"player.png": b"PNGDATA"},
            },
        },
    )

    arch = tmp_path / "game.dat"  # arbitrary extension
    create_archive(src, arch)

    # Should be a valid plain zip
    with zipfile.ZipFile(arch) as z:
        assert "readme.txt" in z.namelist()
        assert "data/level1.json" in z.namelist()

    dst = tmp_path / "extracted"
    extract_archive(arch, dst)

    assert (dst / "readme.txt").read_bytes() == b"Hello world"
    assert (dst / "data" / "level1.json").read_bytes() == b'{"name": "level1"}'
    assert (dst / "data" / "sprites" / "player.png").read_bytes() == b"PNGDATA"


def test_create_and_extract_with_password(tmp_path: Path):
    src = tmp_path / "src"
    _write_tree(src, {"secret.bin": b"top secret data", "nested": {"a.txt": b"aaa"}})

    arch = tmp_path / "protected.pak"
    password = "my casual password 123"
    create_archive(src, arch, password=password)

    # Direct open as zip should fail (obfuscated)
    with pytest.raises(zipfile.BadZipFile):
        zipfile.ZipFile(arch)

    # Extract with correct password
    dst = tmp_path / "out"
    extract_archive(arch, dst, password=password)

    assert (dst / "secret.bin").read_bytes() == b"top secret data"
    assert (dst / "nested" / "a.txt").read_bytes() == b"aaa"

    # Wrong password should fail
    with pytest.raises(zipfile.BadZipFile):
        extract_archive(arch, tmp_path / "wrong", password="wrong password")


def test_create_archive_idempotent_structure(tmp_path: Path):
    """Files and structure are preserved exactly."""
    src = tmp_path / "src"
    tree = {
        "top.txt": b"1",
        "dir1": {"f1.bin": b"11", "sub": {"f2.bin": b"22"}},
        "dir2": {"f3.bin": b"33"},
    }
    _write_tree(src, tree)

    arch = tmp_path / "out.zip"
    create_archive(src, arch)

    dst = tmp_path / "dst"
    extract_archive(arch, dst)

    for rel, expected in [
        ("top.txt", b"1"),
        ("dir1/f1.bin", b"11"),
        ("dir1/sub/f2.bin", b"22"),
        ("dir2/f3.bin", b"33"),
    ]:
        assert (dst / rel).read_bytes() == expected


def test_password_roundtrip_via_zip_provider(tmp_path: Path):
    """Prove that archives created with password are readable by ZipProvider."""
    src = tmp_path / "src"
    _write_tree(src, {"assets": {"image.png": b"IMAGE", "config.json": b"{}"}})

    arch = tmp_path / "data.dat"
    pw = "s3cr3t!"
    create_archive(src, arch, password=pw)

    # Load via VFS / ZipProvider using password
    vfs = VFS()
    vfs.mount("", ZipProvider(arch, password=pw))

    assert vfs.read_bytes("assets/image.png") == b"IMAGE"
    assert vfs.read_bytes("assets/config.json") == b"{}"

    # Using wrong password should not work
    vfs_bad = VFS()
    with pytest.raises(zipfile.BadZipFile):
        vfs_bad.mount("", ZipProvider(arch, password="bad"))


def test_no_password_is_plain_zip(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_bytes(b"plain")

    arch = tmp_path / "plain.dat"
    create_archive(src, arch)  # no password

    # Must be directly readable as zip
    with zipfile.ZipFile(arch) as z:
        assert z.read("f.txt") == b"plain"


def test_empty_password_treated_as_no_encryption(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_bytes(b"data")

    arch = tmp_path / "e.dat"
    create_archive(src, arch, password="")
    extract_archive(arch, tmp_path / "e", password="")  # should succeed

    assert (tmp_path / "e" / "f.txt").read_bytes() == b"data"

    # Also works with None
    arch2 = tmp_path / "e2.dat"
    create_archive(src, arch2, password=None)
    with zipfile.ZipFile(arch2) as z:
        assert z.read("f.txt") == b"data"


def test_create_from_nested_and_extract_preserves_names(tmp_path: Path):
    """Edge case with deeper nesting and special chars (safe for zip)."""
    src = tmp_path / "src"
    _write_tree(
        src,
        {
            "a b.txt": b"space",
            "dir-with-dash": {"file_1.txt": b"one"},
        },
    )

    arch = tmp_path / "weird.ext"
    create_archive(src, arch)
    dst = tmp_path / "out"
    extract_archive(arch, dst)

    assert (dst / "a b.txt").read_bytes() == b"space"
    assert (dst / "dir-with-dash" / "file_1.txt").read_bytes() == b"one"
