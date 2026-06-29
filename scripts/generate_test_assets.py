"""Generate synthetic test assets for Phase 3 OBJ loader testing.

Outputs (all written to demos/assets/):
  checker.png        — 512×512 UV checker with 8 colored quadrants + grid lines
  uv_cube.obj        — unit cube, quads, each face UV-mapped to a distinct quadrant
  uv_cube.mtl        — material referencing checker.png
  low_poly_sphere.obj — icosphere (~80 tris), UV-mapped, no external material

Run from the repo root:
  python scripts/generate_test_assets.py
"""

from __future__ import annotations

import math
import os
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).parent.parent / "demos" / "assets"
OUT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# PNG writer (stdlib only — no Pillow dependency)
# ---------------------------------------------------------------------------

def _png_chunk(tag: bytes, data: bytes) -> bytes:
    c = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", c)


def write_png(path: Path, width: int, height: int, pixels: list[tuple[int,int,int]]) -> None:
    """Write an 8-bit RGB PNG using only stdlib."""
    raw = b""
    for y in range(height):
        raw += b"\x00"  # filter type: None
        for x in range(width):
            r, g, b = pixels[y * width + x]
            raw += bytes([r, g, b])
    compressed = zlib.compress(raw, 9)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(data)
    print(f"  wrote {path}  ({width}×{height} px)")


# ---------------------------------------------------------------------------
# checker.png
# ---------------------------------------------------------------------------

# 8 quadrant colors (2×4 grid of colored regions) matching cube face order:
# right=red, left=cyan, top=yellow, bottom=blue, front=green, back=magenta
QUAD_COLORS = [
    (220,  50,  50),   # Q0  red
    ( 50, 200, 200),   # Q1  cyan
    (220, 200,  40),   # Q2  yellow
    ( 50,  80, 220),   # Q3  blue
    ( 50, 200,  80),   # Q4  green
    (200,  50, 200),   # Q5  magenta
    (180, 120,  40),   # Q6  orange (spare)
    (160, 160, 160),   # Q7  gray   (spare)
]
GRID_COLOR   = (20, 20, 20)
GRID_DIVS    = 4       # grid lines per quadrant cell
PNG_SIZE     = 512
QUAD_COLS    = 4       # 4 columns of quadrants
QUAD_ROWS    = 2       # 2 rows of quadrants


def make_checker(size: int = PNG_SIZE) -> list[tuple[int,int,int]]:
    pixels: list[tuple[int,int,int]] = []
    qw = size // QUAD_COLS
    qh = size // QUAD_ROWS
    cell_w = qw // GRID_DIVS
    cell_h = qh // GRID_DIVS
    for y in range(size):
        for x in range(size):
            qx = x // qw
            qy = y // qh
            qi = qy * QUAD_COLS + qx
            base = QUAD_COLORS[qi % len(QUAD_COLORS)]
            # Grid lines at cell boundaries
            lx = x % cell_w
            ly = y % cell_h
            if lx == 0 or ly == 0:
                pixels.append(GRID_COLOR)
            else:
                # Subtle checkerboard within each cell
                cx = (x // cell_w) % 2
                cy = (y // cell_h) % 2
                if cx == cy:
                    pixels.append(base)
                else:
                    r, g, b = base
                    pixels.append((min(r + 30, 255), min(g + 30, 255), min(b + 30, 255)))
    return pixels


# ---------------------------------------------------------------------------
# uv_cube.obj  +  uv_cube.mtl
# ---------------------------------------------------------------------------
#
# UV layout on checker.png — each face maps to one quadrant in a 4×2 grid:
#
#   +-------+-------+-------+-------+
#   |  +X   |  -X   |  +Y   |  -Y   |   row 0  (v=0.5..1.0)
#   | right  | left  |  top  | bottom|
#   +-------+-------+-------+-------+
#   |  +Z   |  -Z   | (spare| spare)|   row 1  (v=0.0..0.5)
#   | front  | back  |       |       |
#   +-------+-------+-------+-------+
#
# Each quadrant occupies 0.25 in U and 0.5 in V.

def _quad_uv(col: int, row: int) -> tuple[tuple,...]:
    """Bottom-left, bottom-right, top-right, top-left UV coords for a quadrant."""
    u0 = col * 0.25
    u1 = u0 + 0.25
    # row 0 = top half of texture (V 0.5..1.0), row 1 = bottom half (0.0..0.5)
    v0 = (1 - row) * 0.5
    v1 = v0 - 0.5
    # Return UVs in CCW order matching quad winding: BL BR TR TL
    return (u0, v1), (u1, v1), (u1, v0), (u0, v0)


def build_cube_obj() -> str:
    """Unit cube centred at origin with per-face UVs. Outputs quads (face = 4 verts)."""
    h = 0.5
    # Vertex positions (shared)
    positions = [
        (-h, -h, -h), ( h, -h, -h), ( h,  h, -h), (-h,  h, -h),  # -Z face
        (-h, -h,  h), ( h, -h,  h), ( h,  h,  h), (-h,  h,  h),  # +Z face
    ]

    # Each face: (normal, [pos_indices CCW], quadrant col, quadrant row)
    faces = [
        # +X right
        (( 1, 0, 0), [1, 5, 6, 2], 0, 0),
        # -X left
        ((-1, 0, 0), [4, 0, 3, 7], 1, 0),
        # +Y top
        (( 0, 1, 0), [3, 2, 6, 7], 2, 0),
        # -Y bottom
        (( 0,-1, 0), [4, 5, 1, 0], 3, 0),
        # +Z front
        (( 0, 0, 1), [5, 4, 7, 6], 0, 1),
        # -Z back
        (( 0, 0,-1), [0, 1, 2, 3], 1, 1),
    ]

    lines: list[str] = [
        "# uv_cube.obj — synthetic test asset for Grimoire2D Phase 3",
        "# Unit cube, 6 faces (quads), each face UV-mapped to a distinct checker quadrant.",
        "mtllib uv_cube.mtl",
        "o uv_cube",
        "",
    ]

    # Write all positions
    for x, y, z in positions:
        lines.append(f"v {x:.4f} {y:.4f} {z:.4f}")
    lines.append("")

    # Write all UVs — 4 per face × 6 faces = 24
    uv_list: list[tuple[float,float]] = []
    for _, _, col, row in faces:
        for uv in _quad_uv(col, row):
            uv_list.append(uv)
            lines.append(f"vt {uv[0]:.6f} {uv[1]:.6f}")
    lines.append("")

    # Per-face normals
    for nx, ny, nz in [f[0] for f in faces]:
        lines.append(f"vn {float(nx):.4f} {float(ny):.4f} {float(nz):.4f}")
    lines.append("")

    lines.append("usemtl checker")
    lines.append("s off")
    lines.append("")

    # Faces — pos/uv/normal (1-indexed)
    uv_idx = 1
    for fi, (_, pos_ids, _, _) in enumerate(faces):
        ni = fi + 1
        # Quad as two triangles: 0-1-2-3 → (0,1,2) (0,2,3)
        p = [i + 1 for i in pos_ids]   # 1-indexed positions
        u = [uv_idx, uv_idx+1, uv_idx+2, uv_idx+3]
        lines.append(f"f {p[0]}/{u[0]}/{ni} {p[1]}/{u[1]}/{ni} {p[2]}/{u[2]}/{ni} {p[3]}/{u[3]}/{ni}")
        uv_idx += 4

    return "\n".join(lines) + "\n"


def build_cube_mtl() -> str:
    return "\n".join([
        "# uv_cube.mtl — material for uv_cube.obj",
        "newmtl checker",
        "Ka 0.1 0.1 0.1",
        "Kd 1.0 1.0 1.0",
        "Ks 0.3 0.3 0.3",
        "Ns 32.0",
        "d 1.0",
        "map_Kd checker.png",
        "",
    ])


# ---------------------------------------------------------------------------
# low_poly_sphere.obj  (icosphere, 2 subdivisions → 80 triangles)
# ---------------------------------------------------------------------------

def _normalize(v: tuple) -> tuple:
    l = math.sqrt(sum(x*x for x in v))
    return tuple(x / l for x in v)


def _midpoint(a: tuple, b: tuple) -> tuple:
    return _normalize(((a[0]+b[0])/2, (a[1]+b[1])/2, (a[2]+b[2])/2))


def _sphere_uv(x: float, y: float, z: float) -> tuple[float, float]:
    u = 0.5 + math.atan2(z, x) / (2 * math.pi)
    v = 0.5 - math.asin(max(-1.0, min(1.0, y))) / math.pi
    return u, v


def build_icosphere(subdivisions: int = 2) -> str:
    """Icosphere subdivided N times. Returns OBJ text (no external material)."""
    # Seed icosahedron
    t = (1.0 + math.sqrt(5.0)) / 2.0
    seed_verts = [
        _normalize((-1,  t, 0)), _normalize(( 1,  t, 0)),
        _normalize((-1, -t, 0)), _normalize(( 1, -t, 0)),
        _normalize(( 0, -1,  t)), _normalize(( 0,  1,  t)),
        _normalize(( 0, -1, -t)), _normalize(( 0,  1, -t)),
        _normalize(( t,  0, -1)), _normalize(( t,  0,  1)),
        _normalize((-t,  0, -1)), _normalize((-t,  0,  1)),
    ]
    faces = [
        (0,11,5),(0,5,1),(0,1,7),(0,7,10),(0,10,11),
        (1,5,9),(5,11,4),(11,10,2),(10,7,6),(7,1,8),
        (3,9,4),(3,4,2),(3,2,6),(3,6,8),(3,8,9),
        (4,9,5),(2,4,11),(6,2,10),(8,6,7),(9,8,1),
    ]
    verts = list(seed_verts)

    for _ in range(subdivisions):
        new_faces = []
        mid_cache: dict[tuple, int] = {}
        def mid(a: int, b: int) -> int:
            key = (min(a,b), max(a,b))
            if key not in mid_cache:
                mid_cache[key] = len(verts)
                verts.append(_midpoint(verts[a], verts[b]))
            return mid_cache[key]
        for a, b, c in faces:
            ab, bc, ca = mid(a,b), mid(b,c), mid(c,a)
            new_faces += [(a,ab,ca),(b,bc,ab),(c,ca,bc),(ab,bc,ca)]
        faces = new_faces

    lines: list[str] = [
        "# low_poly_sphere.obj — synthetic icosphere for Grimoire2D Phase 3",
        f"# {subdivisions} subdivisions → {len(faces)} triangles, {len(verts)} vertices.",
        "# No external material — uses vertex normals only.",
        "o low_poly_sphere",
        "",
    ]
    for x, y, z in verts:
        lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
    lines.append("")

    # UVs per face-vertex (no shared UVs to avoid seam artifacts in a simple loader)
    uv_entries: list[tuple[float,float]] = []
    for a, b, c in faces:
        for vi in (a, b, c):
            uv_entries.append(_sphere_uv(*verts[vi]))
    for u, v in uv_entries:
        lines.append(f"vt {u:.6f} {v:.6f}")
    lines.append("")

    # Normals == positions on unit sphere
    for x, y, z in verts:
        lines.append(f"vn {x:.6f} {y:.6f} {z:.6f}")
    lines.append("")

    lines.append("s 1")
    lines.append("")

    uv_base = 1
    for a, b, c in faces:
        lines.append(
            f"f {a+1}/{uv_base}/{a+1}"
            f" {b+1}/{uv_base+1}/{b+1}"
            f" {c+1}/{uv_base+2}/{c+1}"
        )
        uv_base += 3

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Generating test assets → {OUT}/")

    # checker.png
    pixels = make_checker(PNG_SIZE)
    write_png(OUT / "checker.png", PNG_SIZE, PNG_SIZE, pixels)

    # uv_cube
    (OUT / "uv_cube.obj").write_text(build_cube_obj())
    print(f"  wrote {OUT / 'uv_cube.obj'}")
    (OUT / "uv_cube.mtl").write_text(build_cube_mtl())
    print(f"  wrote {OUT / 'uv_cube.mtl'}")

    # low_poly_sphere
    obj = build_icosphere(subdivisions=2)
    (OUT / "low_poly_sphere.obj").write_text(obj)
    n_tris = obj.count("\nf ")
    print(f"  wrote {OUT / 'low_poly_sphere.obj'}  ({n_tris} triangles)")

    print("Done.")


if __name__ == "__main__":
    main()
