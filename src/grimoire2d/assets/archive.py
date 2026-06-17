"""Archive creation and extraction helpers.

These utilities work with standard zip archives (the actual file extension
is up to the caller) and support optional simple password-based obfuscation.

The obfuscation is **not** cryptographically secure. It is intended only
to keep casual users from easily inspecting or modifying a game's internal
data files.

All functions are pure stdlib (no third-party dependencies).
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from .vfs import _apply_cipher, _derive_key


def create_archive(
    source_dir: str | Path,
    dest: str | Path,
    password: str | None = None,
) -> None:
    """Create a zip archive from the contents of `source_dir`.

    Args:
        source_dir: Directory whose contents will be archived (recursively).
        dest: Destination path for the archive. The extension can be
              anything the caller wants (".zip", ".dat", ".pak", etc.).
        password: If provided, the archive bytes will be obfuscated using
                  a simple symmetric transform derived from the password.
                  The same password will be required to read or extract it.

    The created archive contains relative paths from `source_dir`.
    """
    src = Path(source_dir).resolve()
    dst = Path(dest)

    if not src.is_dir():
        raise NotADirectoryError(f"source_dir is not a directory: {src}")

    # Build the zip in memory so we can optionally obfuscate the whole blob.
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Sort for deterministic output (nice for tests and reproducibility)
        for path in sorted(src.rglob("*")):
            if path.is_file():
                arcname = path.relative_to(src).as_posix()
                zf.write(path, arcname=arcname)

    data = buf.getvalue()

    if password:
        key = _derive_key(password)
        data = _apply_cipher(data, key)

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)


def extract_archive(
    source: str | Path,
    dest_dir: str | Path,
    password: str | None = None,
) -> None:
    """Extract a (possibly obfuscated) archive to `dest_dir`.

    Args:
        source: Path to the archive.
        dest_dir: Directory that will receive the extracted files.
        password: Must match the password used when the archive was created
                  (if any).

    Raises:
        zipfile.BadZipFile: If the archive (after optional de-obfuscation)
            is not a valid zip or the wrong password was supplied.
    """
    src = Path(source)
    dst = Path(dest_dir)

    data = src.read_bytes()

    if password:
        key = _derive_key(password)
        data = _apply_cipher(data, key)

    dst.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(BytesIO(data)) as zf:
        zf.extractall(dst)
