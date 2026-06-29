"""Unit tests for the OBJ + MTL loader.

All tests are pure Python — no OpenGL context required.
"""

from __future__ import annotations

import array
import math
import textwrap
import tempfile
from pathlib import Path

import pytest

from grimoire2d.assets.obj_loader import (
    ObjMesh,
    SubMeshData,
    MtlMaterial,
    load_obj,
    _parse_mtl,
    _parse_face_token,
    _resolve,
)


# ---------------------------------------------------------------------------
# _parse_face_token
# ---------------------------------------------------------------------------

class TestParseFaceToken:
    def test_pos_only(self):
        assert _parse_face_token("3") == (3, None, None)

    def test_pos_tex(self):
        assert _parse_face_token("1/2") == (1, 2, None)

    def test_pos_tex_nrm(self):
        assert _parse_face_token("4/2/1") == (4, 2, 1)

    def test_pos_skip_tex(self):
        assert _parse_face_token("5//3") == (5, None, 3)

    def test_negative_index(self):
        pi, ti, ni = _parse_face_token("-1/-2/-3")
        assert pi == -1 and ti == -2 and ni == -3


# ---------------------------------------------------------------------------
# _resolve
# ---------------------------------------------------------------------------

class TestResolve:
    def test_positive(self):
        assert _resolve(1, 5) == 0
        assert _resolve(5, 5) == 4

    def test_negative(self):
        assert _resolve(-1, 5) == 4
        assert _resolve(-2, 5) == 3


# ---------------------------------------------------------------------------
# _parse_mtl
# ---------------------------------------------------------------------------

class TestParseMtl:
    def _write_mtl(self, tmp_path: Path, text: str) -> Path:
        p = tmp_path / "test.mtl"
        p.write_text(textwrap.dedent(text))
        return p

    def test_basic_material(self, tmp_path):
        p = self._write_mtl(tmp_path, """
            newmtl mymat
            Ka 0.2 0.3 0.4
            Kd 0.5 0.6 0.7
            Ks 0.1 0.2 0.3
            Ns 64.0
            d 0.9
        """)
        mats = _parse_mtl(p)
        assert "mymat" in mats
        m = mats["mymat"]
        assert m.ambient == pytest.approx((0.2, 0.3, 0.4))
        assert m.diffuse == pytest.approx((0.5, 0.6, 0.7))
        assert m.specular == pytest.approx((0.1, 0.2, 0.3))
        assert m.shininess == pytest.approx(64.0)
        assert m.alpha == pytest.approx(0.9)

    def test_tr_inverts_alpha(self, tmp_path):
        p = self._write_mtl(tmp_path, """
            newmtl glass
            Tr 0.3
        """)
        m = _parse_mtl(p)["glass"]
        assert m.alpha == pytest.approx(0.7)

    def test_map_kd_resolved(self, tmp_path):
        (tmp_path / "color.png").touch()
        p = self._write_mtl(tmp_path, """
            newmtl textured
            map_Kd color.png
        """)
        m = _parse_mtl(p)["textured"]
        assert m.diffuse_map is not None
        assert m.diffuse_map.name == "color.png"

    def test_missing_file_returns_empty(self, tmp_path):
        mats = _parse_mtl(tmp_path / "nope.mtl")
        assert mats == {}

    def test_multiple_materials(self, tmp_path):
        p = self._write_mtl(tmp_path, """
            newmtl red
            Kd 1.0 0.0 0.0
            newmtl blue
            Kd 0.0 0.0 1.0
        """)
        mats = _parse_mtl(p)
        assert set(mats) == {"red", "blue"}
        assert mats["red"].diffuse[0] == pytest.approx(1.0)
        assert mats["blue"].diffuse[2] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# load_obj — triangle
# ---------------------------------------------------------------------------

def _write_obj(tmp_path: Path, text: str, name: str = "test.obj") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(text))
    return p


class TestLoadObjTriangle:
    def test_single_triangle_pos_only(self, tmp_path):
        p = _write_obj(tmp_path, """
            v 0 0 0
            v 1 0 0
            v 0 1 0
            f 1 2 3
        """)
        mesh = load_obj(p)
        assert isinstance(mesh, ObjMesh)
        assert len(mesh.submeshes) == 1
        sub = mesh.submeshes[0]
        assert sub.triangle_count == 1
        assert sub.vertex_count == 3

    def test_face_normal_computed(self, tmp_path):
        p = _write_obj(tmp_path, """
            v 0 0 0
            v 1 0 0
            v 0 0 -1
            f 1 2 3
        """)
        mesh = load_obj(p)
        sub = mesh.submeshes[0]
        # Normal at each vertex (floats 3,4,5 in each 8-float block)
        verts = list(sub.vertices)
        nx, ny, nz = verts[3], verts[4], verts[5]
        length = math.sqrt(nx*nx + ny*ny + nz*nz)
        assert length == pytest.approx(1.0, abs=1e-5)
        # Floor-lying CCW triangle should point upward (positive Y)
        assert ny == pytest.approx(1.0, abs=1e-5)

    def test_explicit_normals_used(self, tmp_path):
        p = _write_obj(tmp_path, """
            v 0 0 0
            v 1 0 0
            v 0 1 0
            vn 0 0 1
            f 1//1 2//1 3//1
        """)
        sub = load_obj(p).submeshes[0]
        verts = list(sub.vertices)
        assert verts[5] == pytest.approx(1.0, abs=1e-5)   # nz of first vertex

    def test_uv_coords_stored(self, tmp_path):
        p = _write_obj(tmp_path, """
            v 0 0 0
            v 1 0 0
            v 0 1 0
            vt 0.0 0.0
            vt 1.0 0.0
            vt 0.0 1.0
            vn 0 0 1
            f 1/1/1 2/2/1 3/3/1
        """)
        sub = load_obj(p).submeshes[0]
        verts = list(sub.vertices)
        # UV at vertex 0: indices 6,7
        assert verts[6] == pytest.approx(0.0)
        assert verts[7] == pytest.approx(0.0)
        # UV at vertex 1: indices 14,15
        assert verts[14] == pytest.approx(1.0)
        assert verts[15] == pytest.approx(0.0)


class TestLoadObjQuad:
    def test_quad_triangulated(self, tmp_path):
        p = _write_obj(tmp_path, """
            v -1 0 -1
            v  1 0 -1
            v  1 0  1
            v -1 0  1
            f 1 2 3 4
        """)
        sub = load_obj(p).submeshes[0]
        # Fan triangulation: 2 triangles
        assert sub.triangle_count == 2

    def test_ngon_triangulated(self, tmp_path):
        # Pentagon: fan gives 3 triangles
        p = _write_obj(tmp_path, """
            v 0 0 0
            v 1 0 0
            v 2 1 0
            v 1 2 0
            v 0 2 0
            f 1 2 3 4 5
        """)
        sub = load_obj(p).submeshes[0]
        assert sub.triangle_count == 3


class TestLoadObjDedup:
    def test_shared_vertices_deduped(self, tmp_path):
        # Two faces sharing an edge: 4 unique positions but 6 face vertices
        p = _write_obj(tmp_path, """
            v 0 0 0
            v 1 0 0
            v 1 1 0
            v 0 1 0
            vn 0 0 1
            f 1//1 2//1 3//1
            f 1//1 3//1 4//1
        """)
        sub = load_obj(p).submeshes[0]
        # 4 unique (pos, None, normal) combos — deduplication should give 4 verts
        assert sub.vertex_count == 4
        assert sub.triangle_count == 2

    def test_same_pos_diff_uv_not_deduped(self, tmp_path):
        # Vertex at pos 1 appears in two faces with different UVs → 2 GPU vertices
        p = _write_obj(tmp_path, """
            v 0 0 0
            v 1 0 0
            v 0 1 0
            v 1 1 0
            vt 0.0 0.0
            vt 1.0 0.0
            vt 0.0 1.0
            vt 0.5 0.5
            vn 0 0 1
            f 1/1/1 2/2/1 3/3/1
            f 1/4/1 3/3/1 4/2/1
        """)
        sub = load_obj(p).submeshes[0]
        # Vertex 1 used with uv_idx=0 and uv_idx=3 → must NOT be merged
        assert sub.vertex_count >= 5


class TestLoadObjMultipleMaterials:
    def test_two_submeshes(self, tmp_path):
        mtl = tmp_path / "multi.mtl"
        mtl.write_text(textwrap.dedent("""
            newmtl red
            Kd 1 0 0
            newmtl blue
            Kd 0 0 1
        """))
        p = _write_obj(tmp_path, """
            mtllib multi.mtl
            v 0 0 0
            v 1 0 0
            v 0 1 0
            v 1 1 0
            vn 0 0 1
            usemtl red
            f 1//1 2//1 3//1
            usemtl blue
            f 2//1 4//1 3//1
        """)
        mesh = load_obj(p)
        assert len(mesh.submeshes) == 2
        assert mesh.submeshes[0].material.name == "red"
        assert mesh.submeshes[1].material.name == "blue"

    def test_submesh_order_preserved(self, tmp_path):
        p = _write_obj(tmp_path, """
            v 0 0 0
            v 1 0 0
            v 0 1 0
            v 1 1 0
            vn 0 0 1
            usemtl aaa
            f 1//1 2//1 3//1
            usemtl bbb
            f 2//1 4//1 3//1
            usemtl ccc
            f 1//1 4//1 2//1
        """)
        mesh = load_obj(p)
        names = [s.material.name for s in mesh.submeshes]
        assert names == ["aaa", "bbb", "ccc"]


class TestLoadObjNegativeIndices:
    def test_negative_face_indices(self, tmp_path):
        p = _write_obj(tmp_path, """
            v 0 0 0
            v 1 0 0
            v 0 1 0
            f -3 -2 -1
        """)
        sub = load_obj(p).submeshes[0]
        assert sub.triangle_count == 1
        assert sub.vertex_count == 3


class TestLoadObjMeshName:
    def test_object_name_parsed(self, tmp_path):
        p = _write_obj(tmp_path, """
            o my_model
            v 0 0 0
            v 1 0 0
            v 0 1 0
            f 1 2 3
        """)
        mesh = load_obj(p)
        assert mesh.name == "my_model"

    def test_default_name_is_stem(self, tmp_path):
        p = _write_obj(tmp_path, """
            v 0 0 0
            v 1 0 0
            v 0 1 0
            f 1 2 3
        """, name="cool_thing.obj")
        assert load_obj(p).name == "cool_thing"


class TestLoadObjEmptyFallback:
    def test_empty_obj_returns_one_empty_submesh(self, tmp_path):
        p = _write_obj(tmp_path, "# empty\n")
        mesh = load_obj(p)
        assert len(mesh.submeshes) == 1
        assert mesh.submeshes[0].vertex_count == 0

    def test_base_dir_set(self, tmp_path):
        p = _write_obj(tmp_path, """
            v 0 0 0
            v 1 0 0
            v 0 1 0
            f 1 2 3
        """)
        mesh = load_obj(p)
        assert mesh.base_dir == tmp_path


class TestLoadSyntheticAssets:
    """Smoke tests against the generated demo assets (if present)."""

    ASSETS = Path(__file__).parent.parent / "demos" / "assets"

    def test_uv_cube_loads(self):
        p = self.ASSETS / "uv_cube.obj"
        if not p.exists():
            pytest.skip("Demo assets not generated — run scripts/generate_test_assets.py")
        mesh = load_obj(p)
        assert len(mesh.submeshes) >= 1
        total_tris = sum(s.triangle_count for s in mesh.submeshes)
        assert total_tris == 12, f"Unit cube should have 12 triangles, got {total_tris}"

    def test_sphere_loads(self):
        p = self.ASSETS / "low_poly_sphere.obj"
        if not p.exists():
            pytest.skip("Demo assets not generated — run scripts/generate_test_assets.py")
        mesh = load_obj(p)
        assert len(mesh.submeshes) >= 1
        total_tris = sum(s.triangle_count for s in mesh.submeshes)
        assert total_tris > 0

    def test_cube_material_references_texture(self):
        p = self.ASSETS / "uv_cube.obj"
        if not p.exists():
            pytest.skip("Demo assets not generated — run scripts/generate_test_assets.py")
        mesh = load_obj(p)
        sub = mesh.submeshes[0]
        assert sub.material.diffuse_map is not None
        assert sub.material.diffuse_map.name == "checker.png"
