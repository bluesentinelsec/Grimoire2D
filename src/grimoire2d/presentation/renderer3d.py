"""3D renderer using OpenGL 3.30 core + moderngl.

Renderer3D works alongside the existing 2D Renderer on the same GL context.
Typical frame flow::

    dt = win.begin_frame()               # clears color, sets 2D viewport
    r3d.begin_scene(camera, win.viewport, lights=...)  # clears depth, sets 3D viewport
    r3d.draw_box(...)
    r3d.draw_sphere(...)
    r3d.end_scene()                      # disables depth test, restores viewport
    win.renderer.draw_text(...)          # 2D HUD on top
    win.end_frame()

Primitives are built once on first use and cached as GPU meshes.

Phase 1 features:
  - Phong lighting: ambient + 1 directional + up to 8 point lights
  - Runtime effect toggles via RenderSettings3D (specular, fog)
  - draw_box / draw_sphere / draw_plane — solid and wireframe
"""

from __future__ import annotations

import array
import math
import struct
from typing import TYPE_CHECKING

import glm
import moderngl

from grimoire2d.models.light3d import AmbientLight, DirectionalLight, PointLight
from grimoire2d.models.render_settings_3d import RenderSettings3D
from grimoire2d.presentation.shaders3d import PHONG_VERT, PHONG_FRAG, WIRE_VERT, WIRE_FRAG

if TYPE_CHECKING:
    from grimoire2d.logic.camera3d import PerspectiveCamera
    from grimoire2d.logic.scaling import Viewport


# ---------------------------------------------------------------------------
# Internal mesh container
# ---------------------------------------------------------------------------

class _GpuMesh:
    """Compiled vertex/index buffers for one primitive, bound to both programs."""

    def __init__(
        self,
        ctx: moderngl.Context,
        phong_prog: moderngl.Program,
        wire_prog: moderngl.Program,
        solid_verts: list[float],
        solid_indices: list[int],
        wire_verts: list[float] | None = None,
        wire_indices: list[int] | None = None,
    ) -> None:
        # Solid / phong VAO
        vbo_s = ctx.buffer(array.array("f", solid_verts).tobytes())
        ibo_s = ctx.buffer(array.array("I", solid_indices).tobytes())
        self.vao_solid = ctx.vertex_array(
            phong_prog,
            [(vbo_s, "3f 3f 2f", "in_pos", "in_normal", "in_uv")],
            index_buffer=ibo_s,
        )

        # Wireframe VAO (separate vertex buffer with only corner positions)
        if wire_verts is not None and wire_indices is not None:
            vbo_w = ctx.buffer(array.array("f", wire_verts).tobytes())
            ibo_w = ctx.buffer(array.array("I", wire_indices).tobytes())
            self.vao_wire: moderngl.VertexArray | None = ctx.vertex_array(
                wire_prog,
                [(vbo_w, "3f 3f 2f", "in_pos", "in_normal", "in_uv")],
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
    # (normal_xyz, [(x,y,z, u,v), ...]) for each of the 6 faces
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
    """8-corner wireframe box. Dummy normals/UVs so vertex layout matches."""
    h = 0.5
    n, u = [0, 1, 0], [0, 0]  # dummy
    corners = [
        [-h,-h,-h]+n+u, [ h,-h,-h]+n+u, [ h, h,-h]+n+u, [-h, h,-h]+n+u,
        [-h,-h, h]+n+u, [ h,-h, h]+n+u, [ h, h, h]+n+u, [-h, h, h]+n+u,
    ]
    verts = [v for c in corners for v in c]
    lines = [
        0,1, 1,2, 2,3, 3,0,   # -z face
        4,5, 5,6, 6,7, 7,4,   # +z face
        0,4, 1,5, 2,6, 3,7,   # connecting edges
    ]
    return verts, lines


def _build_sphere_solid(stacks: int = 24, slices: int = 24) -> tuple[list[float], list[int]]:
    """UV sphere, radius 1. Normals == position (unit sphere)."""
    verts: list[float] = []
    indices: list[int] = []

    for st in range(stacks + 1):
        phi = math.pi * st / stacks           # 0 (north pole) → π (south pole)
        sin_phi = math.sin(phi)
        cos_phi = math.cos(phi)
        for sl in range(slices + 1):
            theta = 2.0 * math.pi * sl / slices
            x = sin_phi * math.cos(theta)
            y = cos_phi
            z = sin_phi * math.sin(theta)
            u = sl / slices
            v = st / stacks
            verts += [x, y, z, x, y, z, u, v]

    for st in range(stacks):
        for sl in range(slices):
            i0 = st * (slices + 1) + sl
            i1 = i0 + 1
            i2 = i0 + slices + 1
            i3 = i2 + 1
            indices += [i0, i2, i1, i1, i2, i3]

    return verts, indices


def _build_sphere_wire(rings: int = 3, segments: int = 64) -> tuple[list[float], list[int]]:
    """Three great circles (equator + two meridians)."""
    n_dummy = [0.0, 1.0, 0.0]
    uv_dummy = [0.0, 0.0]
    verts: list[float] = []
    lines: list[int] = []

    axes = [(0, 2), (0, 1), (1, 2)]  # XZ, XY, YZ planes
    for ax1, ax2 in axes:
        base = len(verts) // 8
        for i in range(segments):
            theta = 2.0 * math.pi * i / segments
            p = [0.0, 0.0, 0.0]
            p[ax1] = math.cos(theta)
            p[ax2] = math.sin(theta)
            verts += p + n_dummy + uv_dummy
        for i in range(segments):
            lines += [base + i, base + (i + 1) % segments]

    return verts, lines


def _build_plane_solid() -> tuple[list[float], list[int]]:
    """Unit XZ plane (Y=0). Normal points +Y. Scale via model matrix."""
    n = [0.0, 1.0, 0.0]
    verts = [
        -0.5, 0.0, -0.5,  *n, 0.0, 0.0,
         0.5, 0.0, -0.5,  *n, 1.0, 0.0,
         0.5, 0.0,  0.5,  *n, 1.0, 1.0,
        -0.5, 0.0,  0.5,  *n, 0.0, 1.0,
    ]
    indices = [0, 1, 2, 0, 2, 3]
    return verts, indices


# ---------------------------------------------------------------------------
# Uniform helpers
# ---------------------------------------------------------------------------

def _mat4(m: glm.mat4) -> tuple:
    """Flat 16-float tuple (column-major) for moderngl mat4 uniform."""
    return struct.unpack("16f", bytes(m))


def _mat4_inv_t(m: glm.mat4) -> tuple:
    return _mat4(glm.transpose(glm.inverse(m)))


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

        self._phong = ctx.program(vertex_shader=PHONG_VERT, fragment_shader=PHONG_FRAG)
        self._wire  = ctx.program(vertex_shader=WIRE_VERT,  fragment_shader=WIRE_FRAG)

        self._meshes: dict[str, _GpuMesh] = {}

        # Defaults written to phong uniforms in begin_scene
        self._phong["u_use_texture"].value = False
        self._phong["u_color"].value = (1.0, 1.0, 1.0, 1.0)

    # ------------------------------------------------------------------
    # Scene begin / end
    # ------------------------------------------------------------------

    def begin_scene(
        self,
        camera: "PerspectiveCamera",
        viewport: "Viewport",
        *,
        ambient: AmbientLight | None = None,
        dir_light: DirectionalLight | None = None,
        point_lights: list[PointLight] | None = None,
    ) -> None:
        """Set GL state and upload per-frame uniforms.

        Call once per frame before any draw_* calls.  The viewport is the
        letterboxed region returned by GameWindow.viewport — 3D and 2D
        share the same on-screen rect so aspect ratios match.
        """
        vp = viewport
        self.ctx.viewport = (vp.viewport_x, vp.viewport_y, vp.viewport_width, vp.viewport_height)
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.depth_func = "<"
        # Clear only depth — color was already cleared by 2D renderer's prepare_frame.
        self.ctx.clear(depth=True)

        aspect = vp.viewport_width / vp.viewport_height if vp.viewport_height else 1.0
        view = camera.get_view_matrix()
        proj = camera.get_projection_matrix(aspect)

        p = self._phong
        p["u_view"].value = _mat4(view)
        p["u_proj"].value = _mat4(proj)
        p["u_cam_pos"].value = tuple(camera.position)

        # Ambient
        amb = ambient or AmbientLight()
        p["u_ambient_color"].value = amb.color

        # Directional light
        dl = dir_light or DirectionalLight()
        if dl.enabled:
            p["u_dir_light_on"].value = True
            p["u_dir_light_dir"].value = dl.direction
            scaled = tuple(c * dl.intensity for c in dl.color)
            p["u_dir_light_color"].value = scaled
        else:
            p["u_dir_light_on"].value = False

        # Point lights
        lights = (point_lights or [])[: self.settings.max_point_lights]
        p["u_num_point_lights"].value = len(lights)
        for i, pl in enumerate(lights):
            p[f"u_pl_pos[{i}]"].value = pl.position
            p[f"u_pl_color[{i}]"].value = pl.color
            p[f"u_pl_radius[{i}]"].value = pl.radius
            p[f"u_pl_intensity[{i}]"].value = pl.intensity

        # Effect flags
        s = self.settings
        p["u_specular_on"].value = s.specular
        p["u_fog_on"].value = s.fog
        if s.fog:
            p["u_fog_color"].value = s.fog_color
            p["u_fog_near"].value = s.fog_near
            p["u_fog_far"].value = s.fog_far

        # Wireframe program gets the same view/proj
        w = self._wire
        w["u_view"].value = _mat4(view)
        w["u_proj"].value = _mat4(proj)

        # Store for end_scene restore
        self._last_viewport = vp

    def end_scene(self) -> None:
        """Disable depth test so subsequent 2D drawing works correctly."""
        self.ctx.disable(moderngl.DEPTH_TEST)
        # Restore viewport to the letterboxed region (2D renderer's home)
        vp = self._last_viewport
        self.ctx.viewport = (vp.viewport_x, vp.viewport_y, vp.viewport_width, vp.viewport_height)

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
        if wireframe:
            if mesh.vao_wire is None:
                return
            self._wire["u_model"].value = _mat4(model)
            self._wire["u_color"].value = color
            mesh.vao_wire.render(moderngl.LINES)
        else:
            self._phong["u_model"].value = _mat4(model)
            self._phong["u_model_inv_t"].value = _mat4_inv_t(model)
            self._phong["u_color"].value = color
            self._phong["u_use_texture"].value = False
            mesh.vao_solid.render(moderngl.TRIANGLES)

    def _get_mesh(self, key: str) -> _GpuMesh:
        if key not in self._meshes:
            self._meshes[key] = self._build_mesh(key)
        return self._meshes[key]

    def _build_mesh(self, key: str) -> _GpuMesh:
        if key == "box":
            sv, si = _build_box_solid()
            wv, wi = _build_box_wire()
        elif key == "sphere":
            sv, si = _build_sphere_solid()
            wv, wi = _build_sphere_wire()
        elif key == "plane":
            sv, si = _build_plane_solid()
            wv, wi = None, None  # type: ignore[assignment]
        else:
            raise ValueError(f"Unknown primitive: {key!r}")

        return _GpuMesh(
            self.ctx,
            self._phong,
            self._wire,
            sv, si,
            wv if key != "plane" else None,
            wi if key != "plane" else None,
        )
