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
import dataclasses
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import glm
import moderngl

from grimoire2d.assets.obj_loader import ObjMesh, SubMeshData, MtlMaterial, load_obj
from grimoire2d.models.light3d import (
    AmbientLight, DirectionalLight, PointLight, SpotLight, SkyGradient,
)
from grimoire2d.models.render_settings_3d import RenderSettings3D
from grimoire2d.presentation.shaders3d import (
    PHONG_VERT, PHONG_FRAG,
    WIRE_VERT, WIRE_FRAG,
    SHADOW_VERT, SHADOW_FRAG,
    SKY_VERT, SKY_FRAG,
    BLIT_VERT, BLIT_FRAG,
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


class LightCuller:
    """Stateful per-light fade weights to eliminate pop-in/out during culling.

    Each frame, lights are scored by their influence at the camera.  The top
    *max_n* form the desired active set.  A light entering the set ramps its
    effective intensity from 0 to full over ~0.12 s; a light leaving ramps to
    0 over ~0.33 s.  Both fading-in and fading-out lights occupy GPU slots,
    so no hard pop is ever visible.

    Lights are identified by their ``position`` tuple, which is stable for
    static fixtures.  Dynamic lights (e.g. a per-frame flashlight) simply
    start at weight 0 and ramp up — any stale entry for the previous position
    fades out normally.

    When the total number of lights is within the GPU cap, all lights are
    returned at full intensity without any state tracking.
    """

    FADE_IN_RATE  = 8.0   # weight gained per second (0 → 1 in ~0.12 s)
    FADE_OUT_RATE = 3.0   # weight lost  per second  (1 → 0 in ~0.33 s)

    def __init__(self, max_n: int) -> None:
        self._max_n = max_n
        # position tuple → current fade weight in [0, 1]
        self._weights: dict[tuple, float] = {}

    @staticmethod
    def _score(light, cam_pos: glm.vec3) -> float:
        px, py, pz = light.position
        d = math.sqrt((px - cam_pos.x)**2 + (py - cam_pos.y)**2 + (pz - cam_pos.z)**2)
        if d >= light.radius:
            return 0.0
        return light.intensity * (1.0 - d / light.radius) ** 2

    def update(self, lights: list, cam_pos: glm.vec3, dt: float) -> list:
        """Return up to max_n lights with intensity scaled by their fade weight."""
        if not lights:
            self._weights.clear()
            return []

        if len(lights) <= self._max_n:
            return lights

        # Score and rank all lights
        scored_pairs = [(l, self._score(l, cam_pos)) for l in lights]
        scored_pairs.sort(key=lambda x: x[1], reverse=True)
        desired_keys = {tuple(l.position) for l, s in scored_pairs[:self._max_n] if s > 0.0}
        light_by_key = {tuple(l.position): l for l in lights}

        # Advance fade weights for already-tracked lights
        for key in list(self._weights):
            if key not in light_by_key:
                del self._weights[key]
                continue
            if key in desired_keys:
                self._weights[key] = min(1.0, self._weights[key] + self.FADE_IN_RATE * dt)
            else:
                self._weights[key] = max(0.0, self._weights[key] - self.FADE_OUT_RATE * dt)

        # Admit newly desired lights not yet tracked
        for key in desired_keys:
            if key not in self._weights:
                self._weights[key] = min(1.0, self.FADE_IN_RATE * dt)

        # Purge fully-faded lights
        self._weights = {k: w for k, w in self._weights.items() if w > 1e-4}

        # Slot allocation: desired lights first, then fading-out sorted by weight
        desired_slots = [(k, self._weights[k], light_by_key[k])
                         for k in desired_keys if k in self._weights]
        fading_slots  = [(k, self._weights[k], light_by_key[k])
                         for k in self._weights
                         if k not in desired_keys and k in light_by_key]
        fading_slots.sort(key=lambda x: x[1], reverse=True)

        result = []
        for _key, w, light in (desired_slots + fading_slots)[:self._max_n]:
            result.append(dataclasses.replace(light, intensity=light.intensity * w))
        return result


# ---------------------------------------------------------------------------
# Post-processing pipeline
# ---------------------------------------------------------------------------

class _PostProcessPipeline:
    """Intermediate scene FBO + ordered post-processing pass chain.

    The 3D scene renders into ``scene_fbo`` (an off-screen color + depth
    buffer).  Calling ``run()`` executes every enabled pass in order and
    blits the final result to the default (screen) framebuffer.

    The terminal pass always applies gamma correction and brightness
    adjustment so no separate blit is needed when other passes are off.

    Adding a new pass
    -----------------
    1. Add a GLSL program to shaders3d.py.
    2. Add an enable flag (and any tuning floats) to RenderSettings3D.
    3. Compile the program in ``__init__`` and call it inside ``run()``
       using ping-pong between ``_ping_fbo`` / ``_pong_fbo``.
    """

    def __init__(
        self,
        ctx: moderngl.Context,
        settings: RenderSettings3D,
        width: int,
        height: int,
    ) -> None:
        self._ctx      = ctx
        self._settings = settings
        self._w = self._h = 0
        self._scene_color: moderngl.Texture | None       = None
        self._scene_depth: moderngl.Texture | None       = None
        self._scene_fbo:   moderngl.Framebuffer | None   = None

        # Gamma + brightness blit — always the terminal pass
        self._blit_prog = ctx.program(
            vertex_shader=BLIT_VERT, fragment_shader=BLIT_FRAG,
        )
        self._blit_prog["u_scene"].value = 0
        self._blit_vao = ctx.vertex_array(self._blit_prog, [])   # no VBO needed

        self._resize(width, height)

    # ------------------------------------------------------------------
    # FBO lifecycle
    # ------------------------------------------------------------------

    def _resize(self, width: int, height: int) -> None:
        if self._scene_fbo is not None:
            self._scene_fbo.release()
            self._scene_color.release()
            self._scene_depth.release()

        self._w = width
        self._h = height
        self._scene_color = self._ctx.texture((width, height), 4)
        self._scene_color.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._scene_depth = self._ctx.depth_texture((width, height))
        self._scene_fbo   = self._ctx.framebuffer(
            color_attachments=[self._scene_color],
            depth_attachment=self._scene_depth,
        )

    def ensure_size(self, width: int, height: int) -> None:
        """Recreate the scene FBO if the render dimensions changed."""
        if width != self._w or height != self._h:
            self._resize(width, height)

    # ------------------------------------------------------------------
    # Properties used by Renderer3D
    # ------------------------------------------------------------------

    @property
    def scene_fbo(self) -> moderngl.Framebuffer:
        """Bind this before drawing the 3D scene."""
        return self._scene_fbo

    @property
    def scene_depth(self) -> moderngl.Texture:
        """Depth texture of the scene FBO (used only for depth testing)."""
        return self._scene_depth

    # ------------------------------------------------------------------
    # Execute pass chain
    # ------------------------------------------------------------------

    def run(self, screen_viewport: tuple[int, int, int, int]) -> None:
        """Run all enabled post-processing passes then blit to the screen.

        ``screen_viewport`` is the letterboxed destination on the default
        framebuffer: ``(x, y, width, height)`` in physical pixels.

        Future passes (bloom, FXAA, etc.) ping-pong between additional
        FBOs and write their output into ``_scene_color`` before this
        terminal blit runs.
        """
        s = self._settings
        self._ctx.screen.use()
        self._ctx.disable(moderngl.DEPTH_TEST)
        self._ctx.viewport = screen_viewport

        # Terminal pass: gamma correction + brightness → screen
        self._scene_color.use(0)
        self._blit_prog["u_brightness"].value = float(s.brightness)
        self._blit_prog["u_gamma"].value      = float(max(s.gamma, 0.01))
        self._blit_vao.render(moderngl.TRIANGLES, vertices=3)


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
        self._sky    = ctx.program(vertex_shader=SKY_VERT,    fragment_shader=SKY_FRAG)

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

        # Sky: empty VAO — vertex shader uses gl_VertexID to emit a covering triangle
        self._sky_vao = ctx.vertex_array(self._sky, [])

        # Dynamic quad: single reusable VBO written each draw_quad() call.
        # Layout: 3f pos | 3f normal | 2f uv — same interleaved stride as all
        # solid meshes (32 bytes / vertex), so the shadow VAO can reuse "3f 20x".
        _QUAD_IBO_S = array.array("I", [0, 1, 2, 0, 2, 3]).tobytes()   # solid: 2 tris
        _QUAD_IBO_W = array.array("I", [0, 1, 1, 2, 2, 3, 3, 0]).tobytes()  # wire: 4 edges
        self._dyn_quad_vbo = ctx.buffer(reserve=4 * 32)
        _dq_ibo_s = ctx.buffer(_QUAD_IBO_S)
        _dq_ibo_w = ctx.buffer(_QUAD_IBO_W)
        self._dyn_quad_vao_solid = ctx.vertex_array(
            self._phong,
            [(self._dyn_quad_vbo, "3f 3f 2f", "in_pos", "in_normal", "in_uv")],
            index_buffer=_dq_ibo_s,
        )
        self._dyn_quad_vao_shadow = ctx.vertex_array(
            self._shadow,
            [(self._dyn_quad_vbo, "3f 20x", "in_pos")],
            index_buffer=_dq_ibo_s,
        )
        self._dyn_quad_vao_wire = ctx.vertex_array(
            self._wire,
            [(self._dyn_quad_vbo, "3f 20x", "in_pos")],
            index_buffer=_dq_ibo_w,
        )

        # Spot light zero-init so all slots are always populated
        self._phong["u_num_spot_lights"].value = 0

        # Stateful light cullers — maintain per-light fade weights across frames
        self._pl_culler = LightCuller(settings.max_point_lights if settings else 8)
        self._sl_culler = LightCuller(4)  # spot light GPU cap is always 4

        # Texture cache: resolved absolute path → moderngl.Texture
        self._texture_cache: dict[Path, moderngl.Texture] = {}

        # Post-processing pipeline — scene renders into an intermediate FBO;
        # end_scene() runs the pass chain and blits to the screen viewport.
        # Initialised to 1×1; resized automatically on the first begin_scene().
        self._pp = _PostProcessPipeline(ctx, self.settings, 1, 1)

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
        dt: float = 0.016,
        sky_color: tuple[float, float, float, float] = (0.05, 0.07, 0.15, 1.0),
        sky: SkyGradient | None = None,
        ambient: AmbientLight | None = None,
        dir_light: DirectionalLight | None = None,
        point_lights: list[PointLight] | None = None,
        spot_lights: list[SpotLight] | None = None,
    ) -> None:
        """Set GL state, clear the viewport, and upload per-frame uniforms.

        ``dt`` — frame delta time in seconds, used to advance per-light fade
        weights in the stateful light culler.  Pass ``win.begin_frame()`` here.

        ``sky`` — if a SkyGradient is provided it is rendered as a procedural
        background before scene geometry (depth writes off during sky pass).
        ``sky_color`` is used as the plain clear colour when ``sky`` is None.

        Lights beyond the GPU cap (8 point / 4 spot) are CPU-culled.  Lights
        entering or leaving the active set fade in/out over ~0.1–0.3 s to
        prevent visible pop-in/out.  Counts before culling are available via
        ``last_point_light_count`` / ``last_spot_light_count``.
        """
        vp = viewport
        self._last_viewport = vp

        # Compute scene render resolution (render_scale applied here)
        rs = max(0.1, self.settings.render_scale)
        scene_w = max(1, round(vp.viewport_width  * rs))
        scene_h = max(1, round(vp.viewport_height * rs))
        self._pp.ensure_size(scene_w, scene_h)

        # Redirect rendering into the intermediate scene FBO
        self._pp.scene_fbo.use()
        self.ctx.viewport = (0, 0, scene_w, scene_h)

        # Clear the scene FBO (full buffer — no letterbox sub-rect needed)
        if sky is None:
            r, g, b, a = sky_color
            self.ctx.clear(r, g, b, a, depth=1.0)
        else:
            self.ctx.clear(0.0, 0.0, 0.0, 1.0, depth=1.0)

        aspect = scene_w / scene_h if scene_h else 1.0
        view = camera.get_view_matrix()
        proj = camera.get_projection_matrix(aspect)

        # --- Procedural gradient sky (depth test + write off) ---
        if sky is not None:
            self.ctx.disable(moderngl.DEPTH_TEST)
            inv_proj = glm.inverse(proj)
            inv_view = glm.inverse(view)
            self._sky["u_inv_proj"].value  = _mat4(inv_proj)
            self._sky["u_inv_view"].value  = _mat4(inv_view)
            self._sky["u_sky_zenith"].value  = sky.zenith_color
            self._sky["u_sky_horizon"].value = sky.horizon_color
            self._sky["u_sky_ground"].value  = sky.ground_color
            self._sky_vao.render(moderngl.TRIANGLES, vertices=3)

        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.depth_func = "<"

        p = self._phong
        p["u_view"].value    = _mat4(view)
        p["u_proj"].value    = _mat4(proj)
        p["u_cam_pos"].value = tuple(camera.position)

        amb = ambient or AmbientLight()
        p["u_ambient_color"].value = amb.color

        dl = dir_light or DirectionalLight()
        if dl.enabled:
            p["u_dir_light_on"].value    = True
            p["u_dir_light_dir"].value   = dl.direction
            p["u_dir_light_color"].value = tuple(c * dl.intensity for c in dl.color)
        else:
            p["u_dir_light_on"].value = False

        # Shadow uniforms
        s = self.settings
        if self._light_space is not None and s.shadows:
            p["u_shadows_on"].value  = True
            p["u_light_space"].value = _mat4(self._light_space)
            self._shadow_depth.use(1)
        else:
            p["u_shadows_on"].value = False

        # --- Point lights: cull to GPU cap, then upload whole-array ---
        # macOS/Metal registers array uniforms under the base name only.
        # All MAX_PL slots are always written so the driver never prunes any.
        MAX_PL = s.max_point_lights   # GPU cap (default 8)
        all_pl = point_lights or []
        self.last_point_light_count = len(all_pl)       # total before cull
        active_pl = self._pl_culler.update(all_pl, camera.position, dt)
        self.last_point_lights_active = len(active_pl)  # uploaded to GPU

        p["u_num_point_lights"].value = len(active_pl)
        pl_pos: list[tuple] = []
        pl_col: list[tuple] = []
        pl_rad: list[float] = []
        pl_int: list[float] = []
        for i in range(MAX_PL):
            if i < len(active_pl):
                pl = active_pl[i]
                pl_pos.append(tuple(pl.position))
                pl_col.append(tuple(pl.color))
                pl_rad.append(float(pl.radius))
                pl_int.append(float(pl.intensity))
            else:
                pl_pos.append((0.0, 0.0, 0.0))
                pl_col.append((0.0, 0.0, 0.0))
                pl_rad.append(1.0)
                pl_int.append(0.0)
        _set(p, "u_pl_pos",       tuple(pl_pos))
        _set(p, "u_pl_color",     tuple(pl_col))
        _set(p, "u_pl_radius",    tuple(pl_rad))
        _set(p, "u_pl_intensity", tuple(pl_int))

        # --- Spot lights: cull to 4, then upload whole-array ---
        MAX_SL = 4
        all_sl = spot_lights or []
        self.last_spot_light_count  = len(all_sl)
        active_sl = self._sl_culler.update(all_sl, camera.position, dt)
        self.last_spot_lights_active = len(active_sl)

        p["u_num_spot_lights"].value = len(active_sl)
        sl_pos: list[tuple] = []
        sl_dir: list[tuple] = []
        sl_col: list[tuple] = []
        sl_int: list[float] = []
        sl_rad: list[float] = []
        sl_ic:  list[float] = []
        sl_oc:  list[float] = []
        for i in range(MAX_SL):
            if i < len(active_sl):
                sl = active_sl[i]
                sl_pos.append(tuple(sl.position))
                sl_dir.append(tuple(sl.direction))
                sl_col.append(tuple(sl.color))
                sl_int.append(float(sl.intensity))
                sl_rad.append(float(sl.radius))
                sl_ic.append(math.cos(math.radians(sl.inner_angle)))
                sl_oc.append(math.cos(math.radians(sl.outer_angle)))
            else:
                sl_pos.append((0.0, 0.0, 0.0))
                sl_dir.append((0.0, -1.0, 0.0))
                sl_col.append((0.0, 0.0, 0.0))
                sl_int.append(0.0)
                sl_rad.append(1.0)
                sl_ic.append(1.0)
                sl_oc.append(0.9)
        _set(p, "u_sl_pos",       tuple(sl_pos))
        _set(p, "u_sl_dir",       tuple(sl_dir))
        _set(p, "u_sl_color",     tuple(sl_col))
        _set(p, "u_sl_intensity", tuple(sl_int))
        _set(p, "u_sl_radius",    tuple(sl_rad))
        _set(p, "u_sl_inner_cos", tuple(sl_ic))
        _set(p, "u_sl_outer_cos", tuple(sl_oc))

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
        """Run the post-processing chain, blit to screen, restore HUD viewport."""
        if self._last_viewport:
            vp = self._last_viewport
            screen_vp = (vp.viewport_x, vp.viewport_y,
                         vp.viewport_width, vp.viewport_height)
            self._pp.run(screen_vp)
            # Restore viewport and depth state for subsequent 2D HUD drawing
            self.ctx.viewport = screen_vp
        self.ctx.disable(moderngl.DEPTH_TEST)

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

    def draw_quad(
        self,
        p0: tuple[float, float, float],
        p1: tuple[float, float, float],
        p2: tuple[float, float, float],
        p3: tuple[float, float, float],
        color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        *,
        wireframe: bool = False,
    ) -> None:
        """Draw an arbitrary planar quad defined by four world-space corners.

        Winding (CCW from outside):  p0 → p1 → p2 → p3.
        Normal is computed from cross(p1−p0, p3−p0).
        UVs: p0=(0,0) p1=(1,0) p2=(1,1) p3=(0,1).

        The quad writes to the shadow map when called inside a shadow pass.
        """
        v0 = glm.vec3(*p0); v1 = glm.vec3(*p1)
        v2 = glm.vec3(*p2); v3 = glm.vec3(*p3)
        e1 = v1 - v0; e2 = v3 - v0
        raw_n = glm.cross(e1, e2)
        n = glm.normalize(raw_n) if glm.length(raw_n) > 1e-9 else glm.vec3(0, 1, 0)
        nx, ny, nz = n.x, n.y, n.z

        verts = array.array("f", [
            p0[0], p0[1], p0[2],  nx, ny, nz,  0.0, 0.0,
            p1[0], p1[1], p1[2],  nx, ny, nz,  1.0, 0.0,
            p2[0], p2[1], p2[2],  nx, ny, nz,  1.0, 1.0,
            p3[0], p3[1], p3[2],  nx, ny, nz,  0.0, 1.0,
        ])
        self._dyn_quad_vbo.write(verts.tobytes())
        identity = _mat4(glm.mat4(1.0))

        if self._in_shadow_pass:
            self._shadow["u_model"].value = identity
            self._dyn_quad_vao_shadow.render(moderngl.TRIANGLES)
            return

        if wireframe:
            self._wire["u_model"].value = identity
            self._wire["u_color"].value = color
            self._dyn_quad_vao_wire.render(moderngl.LINES)
        else:
            self._phong["u_model"].value       = identity
            self._phong["u_model_inv_t"].value  = identity
            self._phong["u_color"].value        = color
            self._phong["u_use_texture"].value  = False
            self._dyn_quad_vao_solid.render(moderngl.TRIANGLES)

    def draw_rect3d(
        self,
        center: tuple[float, float, float],
        normal: tuple[float, float, float],
        up: tuple[float, float, float] = (0.0, 1.0, 0.0),
        width: float = 1.0,
        height: float = 1.0,
        color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        *,
        wireframe: bool = False,
    ) -> None:
        """Convenience wrapper: draw a rectangle from center + normal + size.

        ``up`` guides the local Y axis (height direction).  If ``normal`` and
        ``up`` are parallel a fallback is used automatically.
        """
        n = glm.normalize(glm.vec3(*normal))
        u = glm.vec3(*up)
        if abs(glm.dot(n, glm.normalize(u))) > 0.99:
            u = glm.vec3(1, 0, 0) if abs(n.x) < 0.9 else glm.vec3(0, 0, 1)
        right  = glm.normalize(glm.cross(u, n)) * (width  * 0.5)
        up_vec = glm.normalize(glm.cross(n, right)) * (height * 0.5)
        c = glm.vec3(*center)
        self.draw_quad(
            tuple(c - right - up_vec),
            tuple(c + right - up_vec),
            tuple(c + right + up_vec),
            tuple(c - right + up_vec),
            color, wireframe=wireframe,
        )

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
