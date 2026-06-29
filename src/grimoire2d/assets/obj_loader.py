"""OBJ + MTL mesh loader.

Parses Wavefront .obj files (and their companion .mtl material libraries) into
plain-Python data structures with no GL dependency.  The renderer consumes
these structures via ``Renderer3D.load_mesh()``.

Supported OBJ directives:
  v  vt  vn  f  o  g  s  mtllib  usemtl  #

Face handling:
  - Triangulates quads and n-gons (fan from vertex 0).
  - Indices may be 1-based positive or negative (relative).
  - All three f-token forms are accepted: ``p/t/n``, ``p//n``, ``p``.
  - If a face omits normal indices, a per-face normal is computed from the
    cross product of the first two edges.

MTL directives parsed:
  newmtl  Ka  Kd  Ks  Ns  d  Tr  map_Kd
"""

from __future__ import annotations

import array
import math
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data models (no GL)
# ---------------------------------------------------------------------------

@dataclass
class MtlMaterial:
    """Material parsed from a .mtl file."""
    name: str = "default"
    ambient:   tuple[float, float, float] = (0.1, 0.1, 0.1)
    diffuse:   tuple[float, float, float] = (0.8, 0.8, 0.8)
    specular:  tuple[float, float, float] = (0.3, 0.3, 0.3)
    shininess: float = 32.0
    alpha:     float = 1.0
    diffuse_map: Path | None = None   # resolved absolute path, or None


_DEFAULT_MATERIAL = MtlMaterial()


@dataclass
class SubMeshData:
    """One draw-call's worth of geometry sharing a single material."""
    material: MtlMaterial
    # Interleaved float32: x y z  nx ny nz  u v  (8 floats per vertex)
    vertices: array.array = field(default_factory=lambda: array.array("f"))
    # uint32 indices into vertices
    indices:  array.array = field(default_factory=lambda: array.array("I"))

    @property
    def vertex_count(self) -> int:
        return len(self.vertices) // 8

    @property
    def triangle_count(self) -> int:
        return len(self.indices) // 3


@dataclass
class ObjMesh:
    """Parsed OBJ file ready for GPU upload."""
    name:      str
    submeshes: list[SubMeshData]
    base_dir:  Path   # directory of the source .obj, for texture path resolution


# ---------------------------------------------------------------------------
# MTL parser
# ---------------------------------------------------------------------------

def _parse_mtl(path: Path) -> dict[str, MtlMaterial]:
    if not path.exists():
        return {}
    materials: dict[str, MtlMaterial] = {}
    cur: MtlMaterial | None = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        kw = parts[0].lower()
        if kw == "newmtl":
            cur = MtlMaterial(name=parts[1] if len(parts) > 1 else "default")
            materials[cur.name] = cur
        elif cur is None:
            continue
        elif kw == "ka" and len(parts) >= 4:
            cur.ambient = (float(parts[1]), float(parts[2]), float(parts[3]))
        elif kw == "kd" and len(parts) >= 4:
            cur.diffuse = (float(parts[1]), float(parts[2]), float(parts[3]))
        elif kw == "ks" and len(parts) >= 4:
            cur.specular = (float(parts[1]), float(parts[2]), float(parts[3]))
        elif kw == "ns" and len(parts) >= 2:
            cur.shininess = float(parts[1])
        elif kw == "d" and len(parts) >= 2:
            cur.alpha = float(parts[1])
        elif kw == "tr" and len(parts) >= 2:
            cur.alpha = 1.0 - float(parts[1])
        elif kw == "map_kd" and len(parts) >= 2:
            # Preserve spaces in path: everything after the keyword
            rel = line.split(None, 1)[1].strip()
            cur.diffuse_map = (path.parent / rel).resolve()
    return materials


# ---------------------------------------------------------------------------
# Face token parser
# ---------------------------------------------------------------------------

def _parse_face_token(token: str) -> tuple[int, int | None, int | None]:
    """Parse ``p/t/n``, ``p//n``, ``p/t``, or ``p``.  Indices are raw OBJ values."""
    parts = token.split("/")
    p = int(parts[0])
    t = int(parts[1]) if len(parts) > 1 and parts[1] else None
    n = int(parts[2]) if len(parts) > 2 and parts[2] else None
    return p, t, n


def _resolve(i: int, count: int) -> int:
    """Convert a 1-based positive or negative OBJ index to 0-based."""
    return i - 1 if i > 0 else count + i


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------

def load_obj(path: str | Path) -> ObjMesh:
    """Parse an OBJ file and return an ``ObjMesh`` ready for GPU upload.

    The returned mesh is pure Python — no GL objects are created here.
    Call ``Renderer3D.load_mesh(path)`` to get a GPU-resident mesh instead.
    """
    path     = Path(path).resolve()
    base_dir = path.parent
    text     = path.read_text(encoding="utf-8", errors="replace")

    positions:  list[tuple[float, float, float]] = []
    tex_coords: list[tuple[float, float]]        = []
    normals:    list[tuple[float, float, float]] = []
    materials:  dict[str, MtlMaterial]           = {}

    # Per-submesh: mat_name -> (MtlMaterial, [(p0,t0,n0), (p1,t1,n1), (p2,t2,n2), face_nrm])
    submesh_faces: dict[str, tuple[MtlMaterial, list]] = {}
    # Preserve insertion order so submeshes appear in the same order as the file
    submesh_order: list[str] = []

    cur_mat  = _DEFAULT_MATERIAL
    obj_name = path.stem

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        kw    = parts[0]

        if kw == "v" and len(parts) >= 4:
            positions.append((float(parts[1]), float(parts[2]), float(parts[3])))

        elif kw == "vt" and len(parts) >= 2:
            u = float(parts[1])
            v = float(parts[2]) if len(parts) >= 3 else 0.0
            tex_coords.append((u, v))

        elif kw == "vn" and len(parts) >= 4:
            normals.append((float(parts[1]), float(parts[2]), float(parts[3])))

        elif kw == "o" and len(parts) >= 2:
            obj_name = parts[1]

        elif kw == "mtllib" and len(parts) >= 2:
            mtl_path = base_dir / parts[1]
            materials.update(_parse_mtl(mtl_path))

        elif kw == "usemtl" and len(parts) >= 2:
            mat_name = parts[1]
            cur_mat  = materials.get(mat_name, MtlMaterial(name=mat_name))

        elif kw == "f" and len(parts) >= 4:
            tokens = [_parse_face_token(p) for p in parts[1:]]

            # Compute a face normal for vertices that don't supply one
            pi0 = _resolve(tokens[0][0], len(positions))
            pi1 = _resolve(tokens[1][0], len(positions))
            pi2 = _resolve(tokens[2][0], len(positions))
            ax, ay, az = positions[pi0]
            bx, by, bz = positions[pi1]
            cx, cy, cz = positions[pi2]
            ex, ey, ez = bx-ax, by-ay, bz-az
            fx, fy, fz = cx-ax, cy-ay, cz-az
            nx = ey*fz - ez*fy
            ny = ez*fx - ex*fz
            nz = ex*fy - ey*fx
            length = math.sqrt(nx*nx + ny*ny + nz*nz)
            face_nrm: tuple[float, float, float] = (
                (nx/length, ny/length, nz/length) if length > 1e-9 else (0.0, 1.0, 0.0)
            )

            key = cur_mat.name
            if key not in submesh_faces:
                submesh_faces[key] = (cur_mat, [])
                submesh_order.append(key)

            face_data = submesh_faces[key][1]
            # Fan triangulation: (0,1,2), (0,2,3), (0,3,4), ...
            for ti in range(1, len(tokens) - 1):
                face_data.append((tokens[0], tokens[ti], tokens[ti + 1], face_nrm))

    # ---------------------------------------------------------------------------
    # Build de-duplicated vertex buffers
    # ---------------------------------------------------------------------------

    submeshes: list[SubMeshData] = []

    for key in submesh_order:
        mat, face_list = submesh_faces[key]
        sub      = SubMeshData(material=mat)
        vert_map: dict[tuple, int] = {}

        for tok0, tok1, tok2, face_nrm in face_list:
            for pi_raw, ti_raw, ni_raw in (tok0, tok1, tok2):
                pi = _resolve(pi_raw, len(positions))
                ti = _resolve(ti_raw, len(tex_coords)) if ti_raw is not None else None
                ni = _resolve(ni_raw, len(normals))    if ni_raw is not None else None

                vkey = (pi, ti, ni)
                if vkey not in vert_map:
                    vert_map[vkey] = len(sub.vertices) // 8
                    x, y, z   = positions[pi]
                    nx, ny, nz = normals[ni] if ni is not None else face_nrm
                    u, v       = tex_coords[ti] if ti is not None else (0.0, 0.0)
                    sub.vertices.extend([x, y, z, nx, ny, nz, u, v])

                sub.indices.append(vert_map[vkey])

        submeshes.append(sub)

    if not submeshes:
        submeshes.append(SubMeshData(material=_DEFAULT_MATERIAL))

    return ObjMesh(name=obj_name, submeshes=submeshes, base_dir=base_dir)
