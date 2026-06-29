"""3D renderer using OpenGL 3.30 core + moderngl.

Renderer3D works alongside the existing 2D Renderer on the same GL context.
Typical frame flow with shadows::

    dt = win.begin_frame()
    r3d.begin_shadow_pass(sun, scene_center=(0,0,0), scene_radius=20)
    draw_all_shadow_casters()          # same draw_* calls as color pass
    r3d.end_shadow_pass()
    r3d.begin_scene(camera, win.viewport, sky_color=..., ambient=...,
                    dir_light=sun, point_lights=[...])
    draw_all_objects()
    r3d.end_scene()
    win.renderer.draw_text(...)        # 2D HUD on top
    win.end_frame()

Without shadows, omit begin/end_shadow_pass.

Phase 1 features:
  - Phong lighting: ambient + 1 directional + up to 8 point lights
  - Runtime effect toggles via RenderSettings3D (specular, fog, shadows)
  - draw_box / draw_sphere / draw_plane — solid and wireframe

Phase 2 additions:
  - Shadow mapping (directional light, PCF 3×3)
  - draw_cylinder / draw_cone / draw_capsule — solid and wireframe
  - FreelookCamera wiring (camera is in camera3d.py; this file renders it)

Phase 3 additions:
  - load_mesh(path) -> GpuMesh3D  — OBJ + MTL loader, texture upload
  - draw_mesh(mesh, ...)          — render a loaded mesh with full Phong + shadows
  - Texture cache: the same image file is only uploaded to the GPU once
"""

from __future__ import annotations

import array
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import glm
import moderngl

from grimoire2d.assets.obj_loader import ObjMesh, SubMeshData, MtlMaterial, load_obj
from grimoire2d.models.light3d import AmbientLight, DirectionalLight, PointLight
from grimoire2d.models.render_settings_3d import RenderSettings3D
from grimoire2d.presentation.shaders3d import (
    PHONG_VERT, PHONG_FRAG,
    WIRE_VERT, WIRE_FRAG,
    SHADOW_VERT, SHADOW_FRAG,
)

if TYPE_CHECKING:
    from grimoire2d.logic.camera3d import PerspectiveCamera
    from grimoire2d.logic.scaling import Viewport


# ---------------------------------------------------------------------------
# GPU mesh types (OBJ-loaded meshes)
# ---------------------------------------------------------------------------

@dataclass
class _GpuSubMesh:
    """One GPU draw call — geometry + material for a single OBJ submesh."""
    vao_solid:  moderngl.VertexArray
    vao_shadow: moderngl.VertexArray
    texture:    moderngl.Texture | None   # None = use material color
    color:      tuple[float, float, float, float]
    shininess:  float


class GpuMesh3D:
    """GPU-resident OBJ mesh returned by ``Renderer3D.load_mesh()``.

    Pass to ``Renderer3D.draw_mesh()`` each frame.  Do not construct directly.
    """
    def __init__(self, submeshes: list[_GpuSubMesh], name: str = "") -> None:
        self.submeshes = submeshes
        self.name      = name


# ---------------------------------------------------------------------------
# Internal primitive mesh container
# ---------------------------------------------------------------------------

class _GpuMesh:
    """Compiled vertex/index buffers for one primitive, bound to all programs."""

    def __init__(
        self,
        ctx: moderngl.Context,
        phong_prog: moderngl.Program,
        wire_prog: moderngl.Program,
        shadow_prog: moderngl.Program,
        solid_verts: list[float],
        solid_indices: list[int],
        wire_verts: list[float] | None = None,
        wire_indices: list[int] | None = None,
    ) -> None:
        # Solid / phong VAO  (layout: 3f pos | 3f normal | 2f uv = 32 bytes)
        vbo_s = ctx.buffer(array.array("f", solid_verts).tobytes())
        ibo_s = ctx.buffer(array.array("I", solid_indices).tobytes())
        self.vao_solid = ctx.vertex_array(
            phong_prog,
            [(vbo_s, "3f 3f 2f", "in_pos", "in_normal", "in_uv")],
            index_buffer=ibo_s,
        )

        # Shadow VAO — position-only from solid VBO.
        # "3f 20x" reads 3 floats (pos, 12 bytes) then skips 20 bytes
        # (normal 12 + uv 8), matching the 32-byte interleaved stride.
        self.vao_shadow = ctx.vertex_array(
            shadow_prog,
            [(vbo_s, "3f 20x", "in_pos")],
            index_buffer=ibo_s,
        )

        # Wireframe VAO — positions only (wire shader declares only in_pos)
        if wire_verts is not None and wire_indices is not None:
            vbo_w = ctx.buffer(array.array("f", wire_verts).tobytes())
            ibo_w = ctx.buffer(array.array("I", wire_indices).tobytes())
            self.vao_wire: moderngl.VertexArray | None = ctx.vertex_array(
                wire_prog,
                [(vbo_w, "3f", "in_pos")],
                index_buffer=ibo_w,
            )
        else:
            self.vao_wire = None


# ---------------------------------------------------------------------------
# Primitive geometry builders  (pure Python, no GL)
# ---------------------------------------------------------------------------

def _build_box_solid() -> tuple[list[float], list[int]]:
    """Unit box [-0.5, 0.5] on all axes. Per-face normals, 24 vertices."""
    h = 0.5
    face_data = [
        ((1, 0, 0),  [(h, h,-h,0,1),(h,-h,-h,0,0),(h,-h, h,1,0),(h, h, h,1,1)]),
        ((-1,0, 0),  [(-h, h, h,0,1),(-h,-h, h,0,0),(-h,-h,-h,1,0),(-h, h,-h,1,1)]),
        ((0, 1, 0),  [(-h,h,-h,0,0),(-h,h, h,0,1),(h,h, h,1,1),(h,h,-h,1,0)]),
        ((0,-1, 0),  [(-h,-h, h,0,0),(-h,-h,-h,0,1),(h,-h,-h,1,1),(h,-h, h,1,0)]),
        ((0, 0, 1),  [(-h, h, h,0,1),(-h,-h, h,0,0),(h,-h, h,1,0),(h, h, h,1,1)]),
        ((0, 0,-1),  [(h, h,-h,0,1),(h,-h,-h,0,0),(-h,-h,-h,1,0),(-h, h,-h,1,1)]),
    ]
    verts: list[float] = []
    indices: list[int] = []
    vi = 0
    for (nx, ny, nz), corners in face_data:
        for (x, y, z, u, v) in corners:
            verts += [x, y, z, nx, ny, nz, u, v]
        indices += [vi, vi+1, vi+2, vi, vi+2, vi+3]
        vi += 4
    return verts, indices


def _build_box_wire() -> tuple[list[float], list[int]]:
    """8-corner wireframe box. Positions only."""
    h = 0.5
    corners = [
        [-h,-h,-h], [ h,-h,-h], [ h, h,-h], [-h, h,-h],
        [-h,-h, h], [ h,-h, h], [ h, h, h], [-h, h, h],
    ]
    verts = [v for c in corners for v in c]
    lines = [
        0,1, 1,2, 2,3, 3,0,
        4,5, 5,6, 6,7, 7,4,
        0,4, 1,5, 2,6, 3,7,
    ]
    return verts, lines


def _build_sphere_solid(stacks: int = 24, slices: int = 24) -> tuple[list[float], list[int]]:
    """UV sphere, radius 1. Normals == position (unit sphere)."""
    verts: list[float] = []
    indices: list[int] = []
    for st in range(stacks + 1):
        phi = math.pi * st / stacks
        sin_phi = math.sin(phi)
        cos_phi = math.cos(phi)
        for sl in range(slices + 1):
            theta = 2.0 * math.pi * sl / slices
            x = sin_phi * math.cos(theta)
            y = cos_phi
            z = sin_phi * math.sin(theta)
            verts += [x, y, z, x, y, z, sl / slices, st / stacks]
    for st in range(stacks):
        for sl in range(slices):
            i0 = st * (slices + 1) + sl
            i1 = i0 + 1
            i2 = i0 + slices + 1
            i3 = i2 + 1
            indices += [i0, i2, i1, i1, i2, i3]
    return verts, indices


def _build_sphere_wire(segments: int = 64) -> tuple[list[float], list[int]]:
    """Three great circles (equator + two meridians). Positions only."""
    verts: list[float] = []
    lines: list[int] = []
    for ax1, ax2 in [(0, 2), (0, 1), (1, 2)]:
        base = len(verts) // 3
        for i in range(segments):
            theta = 2.0 * math.pi * i / segments
            p = [0.0, 0.0, 0.0]
            p[ax1] = math.cos(theta)
            p[ax2] = math.sin(theta)
            verts += p
        for i in range(segments):
            lines += [base + i, base + (i + 1) % segments]
    return verts, lines


def _build_plane_solid() -> tuple[list[float], list[int]]:
    """Unit XZ plane (Y=0). Normal points +Y."""
    n = [0.0, 1.0, 0.0]
    verts = [
        -0.5, 0.0, -0.5,  *n, 0.0, 0.0,
         0.5, 0.0, -0.5,  *n, 1.0, 0.0,
         0.5, 0.0,  0.5,  *n, 1.0, 1.0,
        -0.5, 0.0,  0.5,  *n, 0.0, 1.0,
    ]
    return verts, [0, 1, 2, 0, 2, 3]


def _build_cylinder_solid(slices: int = 24) -> tuple[list[float], list[int]]:
    """Unit cylinder: radius=0.5, height=1.0, center at origin."""
    verts: list[float] = []
    indices: list[int] = []
    vi = 0
    R, H = 0.5, 0.5

    # Side quads — smooth radial normals
    for sl in range(slices):
        a0 = 2 * math.pi * sl / slices
        a1 = 2 * math.pi * (sl + 1) / slices
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)
        u0, u1 = sl / slices, (sl + 1) / slices
        verts += [R*c0, -H, R*s0,  c0, 0, s0,  u0, 0]
        verts += [R*c1, -H, R*s1,  c1, 0, s1,  u1, 0]
        verts += [R*c1,  H, R*s1,  c1, 0, s1,  u1, 1]
        verts += [R*c0,  H, R*s0,  c0, 0, s0,  u0, 1]
        indices += [vi, vi+1, vi+2, vi, vi+2, vi+3]
        vi += 4

    # Top cap (y=H)
    tc = vi
    verts += [0, H, 0,  0, 1, 0,  0.5, 0.5]; vi += 1
    tb = vi
    for sl in range(slices):
        a = 2 * math.pi * sl / slices
        c, s = math.cos(a), math.sin(a)
        verts += [R*c, H, R*s,  0, 1, 0,  0.5+0.5*c, 0.5+0.5*s]; vi += 1
    for sl in range(slices):
        indices += [tc, tb + sl, tb + (sl + 1) % slices]

    # Bottom cap (y=-H), reversed winding
    bc = vi
    verts += [0, -H, 0,  0, -1, 0,  0.5, 0.5]; vi += 1
    bb = vi
    for sl in range(slices):
        a = 2 * math.pi * sl / slices
        c, s = math.cos(a), math.sin(a)
        verts += [R*c, -H, R*s,  0, -1, 0,  0.5+0.5*c, 0.5+0.5*s]; vi += 1
    for sl in range(slices):
        indices += [bc, bb + (sl + 1) % slices, bb + sl]

    return verts, indices


def _build_cylinder_wire(slices: int = 24) -> tuple[list[float], list[int]]:
    """Top ring + bottom ring + vertical lines. Positions only."""
    verts: list[float] = []
    lines: list[int] = []
    R, H = 0.5, 0.5

    # Top ring
    tb = 0
    for sl in range(slices):
        a = 2 * math.pi * sl / slices
        verts += [R * math.cos(a), H, R * math.sin(a)]
    for sl in range(slices):
        lines += [tb + sl, tb + (sl + 1) % slices]

    # Bottom ring
    bb = slices
    for sl in range(slices):
        a = 2 * math.pi * sl / slices
        verts += [R * math.cos(a), -H, R * math.sin(a)]
    for sl in range(slices):
        lines += [bb + sl, bb + (sl + 1) % slices]

    # Vertical connectors (every other slice to avoid clutter)
    for sl in range(0, slices, 2):
        lines += [tb + sl, bb + sl]

    return verts, lines


def _build_cone_solid(slices: int = 24) -> tuple[list[float], list[int]]:
    """Unit cone: base radius=0.5 at y=-0.5, tip at y=+0.5."""
    verts: list[float] = []
    indices: list[int] = []
    vi = 0
    R = 0.5
    # Slant normal: horizontal component = h/slant, y = r/slant
    slant = math.sqrt(R * R + 1.0)
    ny_s  = R / slant
    nr_s  = 1.0 / slant

    # Side triangles: tip + two base vertices per slice
    for sl in range(slices):
        a0 = 2 * math.pi * sl / slices
        a1 = 2 * math.pi * (sl + 1) / slices
        am = (a0 + a1) / 2
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)
        cm, sm = math.cos(am), math.sin(am)
        u0, u1 = sl / slices, (sl + 1) / slices
        # Tip (averaged normal for the slice)
        verts += [0, 0.5, 0,  nr_s*cm, ny_s, nr_s*sm,  (u0+u1)/2, 1.0]
        verts += [R*c0, -0.5, R*s0,  nr_s*c0, ny_s, nr_s*s0,  u0, 0.0]
        verts += [R*c1, -0.5, R*s1,  nr_s*c1, ny_s, nr_s*s1,  u1, 0.0]
        indices += [vi, vi+1, vi+2]
        vi += 3

    # Base cap (y=-0.5)
    bc = vi
    verts += [0, -0.5, 0,  0, -1, 0,  0.5, 0.5]; vi += 1
    bb = vi
    for sl in range(slices):
        a = 2 * math.pi * sl / slices
        c, s = math.cos(a), math.sin(a)
        verts += [R*c, -0.5, R*s,  0, -1, 0,  0.5+0.5*c, 0.5+0.5*s]; vi += 1
    for sl in range(slices):
        indices += [bc, bb + (sl + 1) % slices, bb + sl]

    return verts, indices


def _build_cone_wire(slices: int = 24) -> tuple[list[float], list[int]]:
    """Base ring + lines to tip. Positions only."""
    verts: list[float] = []
    lines: list[int] = []
    R = 0.5

    # Base ring
    for sl in range(slices):
        a = 2 * math.pi * sl / slices
        verts += [R * math.cos(a), -0.5, R * math.sin(a)]
    for sl in range(slices):
        lines += [sl, (sl + 1) % slices]

    # Lines to tip (every other)
    tip = slices
    verts += [0.0, 0.5, 0.0]
    for sl in range(0, slices, 3):
        lines += [sl, tip]

    return verts, lines


def _build_capsule_solid(hemi_stacks: int = 8, slices: int = 24) -> tuple[list[float], list[int]]:
    """Capsule: cylinder radius=0.5, cylinder height=1.0, hemispherical caps radius=0.5.
    Total height=2.0, center at origin."""
    verts: list[float] = []
    indices: list[int] = []
    vi = 0
    R  = 0.5
    CY = 0.5  # half cylinder height; caps attach at y=±CY

    def add_hemi_band(phi0: float, phi1: float, cy: float, flip: bool) -> None:
        """One latitude band of a hemisphere. cy = center Y of that hemisphere."""
        nonlocal vi
        rows: list[list[int]] = []
        for phi in (phi0, phi1):
            row_start = vi
            for sl in range(slices + 1):
                theta = 2 * math.pi * sl / slices
                nx = math.sin(phi) * math.cos(theta)
                ny = math.cos(phi)
                nz = math.sin(phi) * math.sin(theta)
                if flip:
                    ny = -ny
                verts.extend([R*nx, cy + R*(math.cos(phi) if not flip else -math.cos(phi)),
                               R*nz, nx, ny, nz, sl/slices, phi/math.pi])
                vi += 1
            rows.append(list(range(row_start, vi)))
        top_row, bot_row = rows[0], rows[1]
        for sl in range(slices):
            i0, i1 = top_row[sl],   top_row[sl+1]
            i2, i3 = bot_row[sl],   bot_row[sl+1]
            indices.extend([i0, i2, i1, i1, i2, i3])

    n_hemi = hemi_stacks

    # Top hemisphere: phi 0→π/2, center at y=+CY
    for st in range(n_hemi):
        phi0 = math.pi * 0.5 * st / n_hemi
        phi1 = math.pi * 0.5 * (st + 1) / n_hemi
        add_hemi_band(phi0, phi1, CY, flip=False)

    # Cylinder sides
    for sl in range(slices):
        a0 = 2 * math.pi * sl / slices
        a1 = 2 * math.pi * (sl + 1) / slices
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)
        u0, u1 = sl / slices, (sl + 1) / slices
        verts += [R*c0, -CY, R*s0,  c0, 0, s0,  u0, 0]
        verts += [R*c1, -CY, R*s1,  c1, 0, s1,  u1, 0]
        verts += [R*c1,  CY, R*s1,  c1, 0, s1,  u1, 1]
        verts += [R*c0,  CY, R*s0,  c0, 0, s0,  u0, 1]
        indices += [vi, vi+1, vi+2, vi, vi+2, vi+3]
        vi += 4

    # Bottom hemisphere: phi 0→π/2, center at y=-CY, flipped
    for st in range(n_hemi):
        phi0 = math.pi * 0.5 * st / n_hemi
        phi1 = math.pi * 0.5 * (st + 1) / n_hemi
        add_hemi_band(phi0, phi1, -CY, flip=True)

    return verts, indices


def _build_capsule_wire(slices: int = 24) -> tuple[list[float], list[int]]:
    """Top/bottom hemi arcs + equator rings + vertical connectors. Positions only."""
    verts: list[float] = []
    lines: list[int] = []
    R  = 0.5
    CY = 0.5
    SEG = slices

    # Vertical arcs in XY and ZY planes for both hemispheres
    for cx, cz in [(1, 0), (0, 1)]:
        for y_sign, cy in [(1, CY), (-1, -CY)]:
            base = len(verts) // 3
            for i in range(SEG + 1):
                phi = math.pi * 0.5 * i / SEG
                r = R * math.sin(phi)
                verts.extend([cx * r, cy + y_sign * R * math.cos(phi), cz * r])
            for i in range(SEG):
                lines.extend([base + i, base + i + 1])

    # Top and bottom equator rings; record start indices for vertical connectors
    ring: dict[str, int] = {}
    for label, cy in [("top", CY), ("bot", -CY)]:
        ring[label] = len(verts) // 3
        for sl in range(slices):
            a = 2 * math.pi * sl / slices
            verts.extend([R * math.cos(a), cy, R * math.sin(a)])
        for sl in range(slices):
            lines.extend([ring[label] + sl, ring[label] + (sl + 1) % slices])

    # Vertical connectors between equator rings (every other vertex, same VBO slots)
    for sl in range(0, slices, 2):
        lines.extend([ring["top"] + sl, ring["bot"] + sl])

    return verts, lines


# ---------------------------------------------------------------------------
# Uniform helpers
# ---------------------------------------------------------------------------

def _mat4(m: glm.mat4) -> tuple:
    """Flat 16-float tuple in column-major order for a moderngl mat4 uniform.

    PyGLM's bytes() outputs row-major data; moderngl uploads with GL_FALSE
    (column-major). Extracting via m[col][row] gives the correct layout.
    """
    return tuple(m[col][row] for col in range(4) for row in range(4))


def _mat4_inv_t(m: glm.mat4) -> tuple:
    return _mat4(glm.transpose(glm.inverse(m)))


def _set(prog: moderngl.Program, key: str, value) -> None:
    """Set a uniform, silently skipping any slot the driver pruned at link time."""
    try:
        prog[key].value = value
    except KeyError:
        pass


# ---------------------------------------------------------------------------
# Renderer3D
# ---------------------------------------------------------------------------

class Renderer3D:
    """Hardware-accelerated 3D renderer (forward Phong, OpenGL 3.30 core).

    Constructed with the moderngl context from GameWindow.ctx.  All GL
    objects (programs, buffers, VAOs) are owned here.
    """

    def __init__(
        self,
        ctx: moderngl.Context,
        settings: RenderSettings3D | None = None,
    ) -> None:
        self.ctx = ctx
        self.settings = settings or RenderSettings3D()

        # Scale shadow map to the physical display — next power-of-2 of the
        # larger screen dimension, clamped to [1024, 8192].
        #   4K (3840×2160) → 4096   1080p (1920×1080) → 2048   720p → 1024
        phys_w, phys_h = ctx.screen.size
        sz = 1024
        while sz < max(phys_w, phys_h) and sz < 8192:
            sz *= 2
        self._shadow_map_size = sz

        self._phong  = ctx.program(vertex_shader=PHONG_VERT,  fragment_shader=PHONG_FRAG)
        self._wire   = ctx.program(vertex_shader=WIRE_VERT,   fragment_shader=WIRE_FRAG)
        self._shadow = ctx.program(vertex_shader=SHADOW_VERT, fragment_shader=SHADOW_FRAG)

        self._meshes: dict[str, _GpuMesh] = {}

        # 1×1 white fallback for unit 0 (silences macOS sampler warning when
        # no texture is bound and u_use_texture=False).
        self._white_tex = ctx.texture((1, 1), 4, b"\xff\xff\xff\xff")
        self._white_tex.use(0)
        self._phong["u_use_texture"].value = False
        self._phong["u_albedo"].value = 0
        self._phong["u_color"].value = (1.0, 1.0, 1.0, 1.0)

        # Shadow map resources
        sz = self._shadow_map_size
        self._shadow_depth = ctx.depth_texture((sz, sz))
        self._shadow_fbo   = ctx.framebuffer(depth_attachment=self._shadow_depth)
        self._shadow_depth.use(1)
        self._phong["u_shadow_map"].value = 1
        self._phong["u_shadows_on"].value = False
        self._light_space: glm.mat4 | None = None
        self._in_shadow_pass = False
        self._last_viewport: "Viewport | None" = None

        # Texture cache: resolved absolute path → moderngl.Texture
        self._texture_cache: dict[Path, moderngl.Texture] = {}

    @property
    def shadow_map_size(self) -> int:
        """Physical pixel size of the shadow map (square). Derived from display at init."""
        return self._shadow_map_size

    # ------------------------------------------------------------------
    # Shadow pass
    # ------------------------------------------------------------------

    def begin_shadow_pass(
        self,
        dir_light: DirectionalLight,
        *,
        scene_center: tuple[float, float, float] = (0.0, 0.0, 0.0),
        scene_radius: float = 20.0,
    ) -> None:
        """Bind the shadow FBO and set up the light-space matrices.

        After this call, all draw_* calls write depth to the shadow map.
        Call end_shadow_pass() before begin_scene().
        """
        d = glm.normalize(glm.vec3(*dir_light.direction))
        center = glm.vec3(*scene_center)
        light_pos   = center - d * scene_radius * 2.0
        # Stable up vector — avoid degenerate lookAt when light points straight up
        world_up = glm.vec3(0, 1, 0) if abs(glm.dot(d, glm.vec3(0, 1, 0))) < 0.99 else glm.vec3(1, 0, 0)
        light_view  = glm.lookAt(light_pos, center, world_up)
        r = scene_radius
        light_proj  = glm.ortho(-r, r, -r, r, 0.1, scene_radius * 4.0)
        self._light_space = light_proj * light_view

        self._shadow["u_light_view"].value = _mat4(light_view)
        self._shadow["u_light_proj"].value = _mat4(light_proj)

        self._shadow_fbo.use()
        self._shadow_fbo.clear(depth=1.0)
        self.ctx.viewport = (0, 0, self._shadow_map_size, self._shadow_map_size)
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.depth_func = "<"
        self._in_shadow_pass = True

    def end_shadow_pass(self) -> None:
        """Unbind shadow FBO and make the depth texture available for sampling."""
        self.ctx.screen.use()
        self.ctx.disable(moderngl.DEPTH_TEST)
        self._in_shadow_pass = False
        # Re-bind depth texture to unit 1 so the phong shader can sample it
        self._shadow_depth.use(1)

    # ------------------------------------------------------------------
    # Scene begin / end
    # ------------------------------------------------------------------

    def begin_scene(
        self,
        camera: "PerspectiveCamera",
        viewport: "Viewport",
        *,
        sky_color: tuple[float, float, float, float] = (0.05, 0.07, 0.15, 1.0),
        ambient: AmbientLight | None = None,
        dir_light: DirectionalLight | None = None,
        point_lights: list[PointLight] | None = None,
    ) -> None:
        """Set GL state, clear the viewport, and upload per-frame uniforms."""
        vp = viewport
        self._last_viewport = vp
        self.ctx.viewport = (vp.viewport_x, vp.viewport_y, vp.viewport_width, vp.viewport_height)
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.depth_func = "<"
        r, g, b, a = sky_color
        self.ctx.clear(r, g, b, a, depth=1.0,
                       viewport=(vp.viewport_x, vp.viewport_y,
                                 vp.viewport_width, vp.viewport_height))

        aspect = vp.viewport_width / vp.viewport_height if vp.viewport_height else 1.0
        view = camera.get_view_matrix()
        proj = camera.get_projection_matrix(aspect)

        p = self._phong
        p["u_view"].value = _mat4(view)
        p["u_proj"].value = _mat4(proj)
        p["u_cam_pos"].value = tuple(camera.position)

        amb = ambient or AmbientLight()
        p["u_ambient_color"].value = amb.color

        dl = dir_light or DirectionalLight()
        if dl.enabled:
            p["u_dir_light_on"].value = True
            p["u_dir_light_dir"].value = dl.direction
            p["u_dir_light_color"].value = tuple(c * dl.intensity for c in dl.color)
        else:
            p["u_dir_light_on"].value = False

        # Shadow uniforms
        s = self.settings
        if self._light_space is not None and s.shadows:
            p["u_shadows_on"].value = True
            p["u_light_space"].value = _mat4(self._light_space)
            self._shadow_depth.use(1)
        else:
            p["u_shadows_on"].value = False

        # Point lights — whole-array upload (macOS Metal reports array uniforms
        # under base name only; per-element indexed writes always KeyError)
        MAX_PL = s.max_point_lights
        lights  = (point_lights or [])[:MAX_PL]
        p["u_num_point_lights"].value = len(lights)
        pos_rows: list[tuple] = []
        col_rows: list[tuple] = []
        rad_flat: list[float] = []
        int_flat: list[float] = []
        for i in range(MAX_PL):
            if i < len(lights):
                pl = lights[i]
                pos_rows.append(tuple(pl.position))
                col_rows.append(tuple(pl.color))
                rad_flat.append(float(pl.radius))
                int_flat.append(float(pl.intensity))
            else:
                pos_rows.append((0.0, 0.0, 0.0))
                col_rows.append((0.0, 0.0, 0.0))
                rad_flat.append(1.0)
                int_flat.append(0.0)
        _set(p, "u_pl_pos",       tuple(pos_rows))
        _set(p, "u_pl_color",     tuple(col_rows))
        _set(p, "u_pl_radius",    tuple(rad_flat))
        _set(p, "u_pl_intensity", tuple(int_flat))

        p["u_specular_on"].value = s.specular
        p["u_fog_on"].value = s.fog
        if s.fog:
            p["u_fog_color"].value = s.fog_color
            p["u_fog_near"].value  = s.fog_near
            p["u_fog_far"].value   = s.fog_far

        # Wire program shares view/proj
        w = self._wire
        w["u_view"].value = _mat4(view)
        w["u_proj"].value = _mat4(proj)

    def end_scene(self) -> None:
        """Disable depth test so subsequent 2D drawing works correctly."""
        self.ctx.disable(moderngl.DEPTH_TEST)
        if self._last_viewport:
            vp = self._last_viewport
            self.ctx.viewport = (vp.viewport_x, vp.viewport_y,
                                  vp.viewport_width, vp.viewport_height)

    # ------------------------------------------------------------------
    # Primitive draw calls
    # ------------------------------------------------------------------

    def draw_box(
        self,
        center: tuple[float, float, float],
        size: tuple[float, float, float] = (1.0, 1.0, 1.0),
        color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        rotation: glm.mat4 | None = None,
        wireframe: bool = False,
    ) -> None:
        model = glm.translate(glm.mat4(1.0), glm.vec3(*center))
        if rotation is not None:
            model = model * rotation
        model = glm.scale(model, glm.vec3(*size))
        self._draw("box", model, color, wireframe)

    def draw_sphere(
        self,
        center: tuple[float, float, float],
        radius: float = 1.0,
        color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        wireframe: bool = False,
    ) -> None:
        model = glm.translate(glm.mat4(1.0), glm.vec3(*center))
        model = glm.scale(model, glm.vec3(radius))
        self._draw("sphere", model, color, wireframe)

    def draw_plane(
        self,
        center: tuple[float, float, float] = (0.0, 0.0, 0.0),
        size: float = 10.0,
        color: tuple[float, float, float, float] = (0.25, 0.25, 0.28, 1.0),
    ) -> None:
        model = glm.translate(glm.mat4(1.0), glm.vec3(*center))
        model = glm.scale(model, glm.vec3(size, 1.0, size))
        self._draw("plane", model, color, False)

    def draw_cylinder(
        self,
        center: tuple[float, float, float],
        radius: float = 0.5,
        height: float = 1.0,
        color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        rotation: glm.mat4 | None = None,
        wireframe: bool = False,
    ) -> None:
        model = glm.translate(glm.mat4(1.0), glm.vec3(*center))
        if rotation is not None:
            model = model * rotation
        model = glm.scale(model, glm.vec3(radius * 2, height, radius * 2))
        self._draw("cylinder", model, color, wireframe)

    def draw_cone(
        self,
        center: tuple[float, float, float],
        radius: float = 0.5,
        height: float = 1.0,
        color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        rotation: glm.mat4 | None = None,
        wireframe: bool = False,
    ) -> None:
        model = glm.translate(glm.mat4(1.0), glm.vec3(*center))
        if rotation is not None:
            model = model * rotation
        model = glm.scale(model, glm.vec3(radius * 2, height, radius * 2))
        self._draw("cone", model, color, wireframe)

    def draw_capsule(
        self,
        center: tuple[float, float, float],
        radius: float = 0.5,
        height: float = 2.0,
        color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        rotation: glm.mat4 | None = None,
        wireframe: bool = False,
    ) -> None:
        """Draw a capsule. height is total (cylinder body + two hemispherical caps)."""
        # The unit capsule has total height=2, radius=0.5.
        # Scale: radius axis = radius/0.5, height axis = height/2.
        sx = radius / 0.5
        sy = height / 2.0
        model = glm.translate(glm.mat4(1.0), glm.vec3(*center))
        if rotation is not None:
            model = model * rotation
        model = glm.scale(model, glm.vec3(sx, sy, sx))
        self._draw("capsule", model, color, wireframe)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _draw(
        self,
        key: str,
        model: glm.mat4,
        color: tuple,
        wireframe: bool,
    ) -> None:
        mesh = self._get_mesh(key)

        if self._in_shadow_pass:
            self._shadow["u_model"].value = _mat4(model)
            mesh.vao_shadow.render(moderngl.TRIANGLES)
            return

        if wireframe:
            if mesh.vao_wire is None:
                return
            self._wire["u_model"].value = _mat4(model)
            self._wire["u_color"].value = color
            mesh.vao_wire.render(moderngl.LINES)
        else:
            self._phong["u_model"].value      = _mat4(model)
            self._phong["u_model_inv_t"].value = _mat4_inv_t(model)
            self._phong["u_color"].value       = color
            self._phong["u_use_texture"].value = False
            mesh.vao_solid.render(moderngl.TRIANGLES)

    # ------------------------------------------------------------------
    # OBJ mesh loading (Phase 3)
    # ------------------------------------------------------------------

    def _load_texture(self, path: Path) -> moderngl.Texture:
        """Upload an image file to the GPU, returning a cached texture."""
        if path in self._texture_cache:
            return self._texture_cache[path]
        import pygame
        surf = pygame.image.load(str(path))
        # Flip vertically: OBJ/PNG origin is top-left, OpenGL is bottom-left
        surf = pygame.transform.flip(surf, False, True)
        surf = surf.convert_alpha()
        w, h = surf.get_size()
        raw  = pygame.image.tobytes(surf, "RGBA")
        tex  = self.ctx.texture((w, h), 4, raw)
        tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        tex.build_mipmaps()
        self._texture_cache[path] = tex
        return tex

    def load_mesh(self, path: str | Path) -> GpuMesh3D:
        """Parse an OBJ file and upload its geometry + textures to the GPU.

        Returns a ``GpuMesh3D`` that can be passed to ``draw_mesh()`` each frame.
        The texture cache ensures each image is uploaded only once.
        """
        obj  = load_obj(path)
        subs: list[_GpuSubMesh] = []

        for sub in obj.submeshes:
            vbo_bytes = sub.vertices.tobytes()
            ibo_bytes = sub.indices.tobytes()
            vbo = self.ctx.buffer(vbo_bytes)
            ibo = self.ctx.buffer(ibo_bytes)

            vao_solid = self.ctx.vertex_array(
                self._phong,
                [(vbo, "3f 3f 2f", "in_pos", "in_normal", "in_uv")],
                index_buffer=ibo,
            )
            vao_shadow = self.ctx.vertex_array(
                self._shadow,
                [(vbo, "3f 20x", "in_pos")],
                index_buffer=ibo,
            )

            tex: moderngl.Texture | None = None
            if sub.material.diffuse_map and sub.material.diffuse_map.exists():
                tex = self._load_texture(sub.material.diffuse_map)

            mat = sub.material
            color = (*mat.diffuse, mat.alpha)
            subs.append(_GpuSubMesh(
                vao_solid  = vao_solid,
                vao_shadow = vao_shadow,
                texture    = tex,
                color      = color,
                shininess  = mat.shininess,
            ))

        return GpuMesh3D(subs, name=obj.name)

    def draw_mesh(
        self,
        mesh: GpuMesh3D,
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
        rotation: glm.mat4 | None = None,
        scale: float | tuple[float, float, float] = 1.0,
    ) -> None:
        """Render a loaded OBJ mesh with full Phong shading and shadow support."""
        model = glm.translate(glm.mat4(1.0), glm.vec3(*position))
        if rotation is not None:
            model = model * rotation
        if isinstance(scale, (int, float)):
            model = glm.scale(model, glm.vec3(float(scale)))
        else:
            model = glm.scale(model, glm.vec3(*scale))

        for sub in mesh.submeshes:
            if self._in_shadow_pass:
                self._shadow["u_model"].value = _mat4(model)
                sub.vao_shadow.render(moderngl.TRIANGLES)
            else:
                self._phong["u_model"].value       = _mat4(model)
                self._phong["u_model_inv_t"].value  = _mat4_inv_t(model)
                if sub.texture is not None:
                    sub.texture.use(0)
                    self._phong["u_use_texture"].value = True
                    self._phong["u_color"].value       = (1.0, 1.0, 1.0, sub.color[3])
                else:
                    self._white_tex.use(0)
                    self._phong["u_use_texture"].value = False
                    self._phong["u_color"].value       = sub.color
                sub.vao_solid.render(moderngl.TRIANGLES)
        # Restore white fallback so subsequent non-mesh draw_* calls work correctly
        if not self._in_shadow_pass:
            self._white_tex.use(0)
            self._phong["u_use_texture"].value = False

    def _get_mesh(self, key: str) -> _GpuMesh:
        if key not in self._meshes:
            self._meshes[key] = self._build_mesh(key)
        return self._meshes[key]

    def _build_mesh(self, key: str) -> _GpuMesh:
        builders: dict[str, tuple] = {
            "box":      (_build_box_solid,      _build_box_wire),
            "sphere":   (_build_sphere_solid,   _build_sphere_wire),
            "cylinder": (_build_cylinder_solid, _build_cylinder_wire),
            "cone":     (_build_cone_solid,     _build_cone_wire),
            "capsule":  (_build_capsule_solid,  _build_capsule_wire),
            "plane":    (_build_plane_solid,    None),
        }
        if key not in builders:
            raise ValueError(f"Unknown primitive: {key!r}")
        solid_fn, wire_fn = builders[key]
        sv, si = solid_fn()
        wv, wi = wire_fn() if wire_fn else (None, None)
        return _GpuMesh(self.ctx, self._phong, self._wire, self._shadow,
                        sv, si, wv, wi)
