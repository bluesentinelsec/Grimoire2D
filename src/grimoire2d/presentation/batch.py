"""GPU-side batch renderers for SDF shapes and textured sprites.

Both batchers follow the same pattern:
  - pre-allocated ``array.array`` CPU buffer (no numpy)
  - single dynamic VBO that is written once per flush
  - VAO wired to the matching shader program

Callers feed geometry every frame with ``add_quad`` / ``add_line``;
``flush()`` uploads and draws, then resets the counter.  The Renderer
calls ``flush()`` automatically before any state-changing operation and
at the end of each frame in ``present()``.
"""
from __future__ import annotations

import array
import math

import moderngl


class ShapeType:
    """Integer constants identifying the SDF shape dispatched in the fragment shader.

    The value is written into ``in_params.w`` (as a float) for each vertex.
    """

    RECT = 0
    ROUNDED_RECT = 1
    CIRCLE = 2
    RING = 3
    RECT_BORDER = 4
    ROUNDED_RECT_BORDER = 5
    ELLIPSE = 6
    ARC = 7
    PIE = 8
    CAPSULE = 9
    GLOW = 10


class ShapeBatch:
    """Pre-allocated vertex buffer for SDF shape quads.

    Geometry is accumulated into a CPU-side ``array.array`` buffer and
    uploaded to the GPU in one call on ``flush()``.  Six vertices (two
    triangles) are emitted per shape.  The vertex format is:

        '2f 2f 2f 4f 4f'
        in_pos (vec2), in_local_p (vec2), in_half_size (vec2),
        in_color (vec4), in_params (vec4)

    14 floats × 6 vertices × 4 bytes = 336 bytes per quad.
    """

    _FLOATS_PER_VERTEX: int = 14
    _VERTS_PER_QUAD: int = 6

    def __init__(
        self,
        ctx: moderngl.Context,
        program: moderngl.Program,
        capacity: int = 2048,
    ) -> None:
        """Initialise with a pre-allocated buffer for *capacity* quads.

        Args:
            ctx: Active moderngl context.
            program: Compiled SHAPE_VERTEX / SHAPE_FRAGMENT program.
            capacity: Maximum number of quads before an automatic flush.
        """
        self._capacity = capacity
        self._quad_count = 0
        self._stride = self._FLOATS_PER_VERTEX * self._VERTS_PER_QUAD
        self._data: array.array = array.array(
            "f", [0.0] * (capacity * self._stride)
        )
        reserve = capacity * self._stride * 4
        self._vbo: moderngl.Buffer = ctx.buffer(reserve=reserve, dynamic=True)
        self._vao: moderngl.VertexArray = ctx.vertex_array(
            program,
            [
                (
                    self._vbo,
                    "2f 2f 2f 4f 4f",
                    "in_pos",
                    "in_local_p",
                    "in_half_size",
                    "in_color",
                    "in_params",
                )
            ],
        )

    def _write_vertex(
        self,
        base: int,
        px: float,
        py: float,
        lx: float,
        ly: float,
        hw: float,
        hh: float,
        color: tuple[float, float, float, float],
        params: tuple[float, float, float, float],
    ) -> None:
        """Write one vertex (14 floats) starting at *base* in ``_data``."""
        r, g, b, a = color
        p0, p1, p2, p3 = params
        self._data[base:base + 14] = array.array(
            "f", [px, py, lx, ly, hw, hh, r, g, b, a, p0, p1, p2, p3]
        )

    def add_quad(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        color: tuple[float, float, float, float],
        *,
        shape_type: int = ShapeType.RECT,
        corner_r: float = 0.0,
        border_t: float = 0.0,
        inner_r: float = 0.0,
        color_b: tuple[float, float, float, float] | None = None,
        gradient_mode: int = 0,
    ) -> None:
        """Enqueue an axis-aligned quad into the batch.

        (x, y) is the top-left corner; (w, h) is the size.  Colour assignment
        depends on ``gradient_mode``:

        - ``0`` (vertical, default): TL=color, TR=color, BL=color_b, BR=color_b
        - ``1`` (horizontal): TL=color, TR=color_b, BL=color, BR=color_b

        An automatic ``flush()`` is issued when the buffer is full.

        Args:
            x: Left edge in virtual coordinates.
            y: Top edge in virtual coordinates.
            w: Width in virtual pixels.
            h: Height in virtual pixels.
            color: RGBA (0..1) primary colour (top or left depending on mode).
            shape_type: One of the ``ShapeType`` constants.
            corner_r: Corner radius for rounded shapes.
            border_t: Stroke thickness for border shapes.
            inner_r: Inner radius for ring shapes.
            color_b: Secondary colour for gradients; defaults to *color*.
            gradient_mode: 0=vertical gradient, 1=horizontal gradient.
        """
        if self._quad_count >= self._capacity:
            self.flush()

        cb = color_b if color_b is not None else color
        hw = w * 0.5
        hh = h * 0.5
        cx = x + hw
        cy = y + hh

        params: tuple[float, float, float, float] = (
            corner_r,
            border_t,
            inner_r,
            float(shape_type),
        )

        tl_x, tl_y = x, y
        tr_x, tr_y = x + w, y
        br_x, br_y = x + w, y + h
        bl_x, bl_y = x, y + h

        tl_lx, tl_ly = tl_x - cx, tl_y - cy
        tr_lx, tr_ly = tr_x - cx, tr_y - cy
        br_lx, br_ly = br_x - cx, br_y - cy
        bl_lx, bl_ly = bl_x - cx, bl_y - cy

        # Assign per-vertex colours based on gradient_mode
        if gradient_mode == 1:
            # Horizontal: left=color, right=cb
            c_tl, c_tr, c_br, c_bl = color, cb, cb, color
        else:
            # Vertical (default): top=color, bottom=cb
            c_tl, c_tr, c_br, c_bl = color, color, cb, cb

        base = self._quad_count * self._stride
        self._write_vertex(base + 0 * 14,  tl_x, tl_y, tl_lx, tl_ly, hw, hh, c_tl, params)
        self._write_vertex(base + 1 * 14,  tr_x, tr_y, tr_lx, tr_ly, hw, hh, c_tr, params)
        self._write_vertex(base + 2 * 14,  br_x, br_y, br_lx, br_ly, hw, hh, c_br, params)
        self._write_vertex(base + 3 * 14,  tl_x, tl_y, tl_lx, tl_ly, hw, hh, c_tl, params)
        self._write_vertex(base + 4 * 14,  br_x, br_y, br_lx, br_ly, hw, hh, c_br, params)
        self._write_vertex(base + 5 * 14,  bl_x, bl_y, bl_lx, bl_ly, hw, hh, c_bl, params)

        self._quad_count += 1

    def add_line(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        thickness: float,
        color: tuple[float, float, float, float],
    ) -> None:
        """Enqueue an arbitrarily-angled line segment as an expanded quad.

        The segment from (x0, y0) to (x1, y1) is expanded by *thickness*
        in the perpendicular direction.  The resulting four corners are
        submitted directly as two triangles (bypassing ``add_quad``).

        The SDF used is RECT (type 0) so the fragment shader fills the
        oriented quad without rounding.

        Args:
            x0: Start x in virtual coordinates.
            y0: Start y in virtual coordinates.
            x1: End x in virtual coordinates.
            y1: End y in virtual coordinates.
            thickness: Line width in virtual pixels.
            color: RGBA (0..1) colour.
        """
        if self._quad_count >= self._capacity:
            self.flush()

        dx = x1 - x0
        dy = y1 - y0
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-9:
            return

        inv_len = 1.0 / length
        dir_x = dx * inv_len
        dir_y = dy * inv_len
        perp_x = -dir_y * (thickness * 0.5)
        perp_y = dir_x * (thickness * 0.5)

        half_len = length * 0.5
        half_t = thickness * 0.5
        cx = (x0 + x1) * 0.5
        cy = (y0 + y1) * 0.5

        hw = half_len
        hh = half_t

        params: tuple[float, float, float, float] = (0.0, 0.0, 0.0, float(ShapeType.RECT))

        tl_x = x0 - perp_x
        tl_y = y0 - perp_y
        tr_x = x1 - perp_x
        tr_y = y1 - perp_y
        br_x = x1 + perp_x
        br_y = y1 + perp_y
        bl_x = x0 + perp_x
        bl_y = y0 + perp_y

        def local(px: float, py: float) -> tuple[float, float]:
            rx = px - cx
            ry = py - cy
            lx = rx * dir_x + ry * dir_y
            ly = rx * (-dir_y) + ry * dir_x
            return lx, ly

        tl_lx, tl_ly = local(tl_x, tl_y)
        tr_lx, tr_ly = local(tr_x, tr_y)
        br_lx, br_ly = local(br_x, br_y)
        bl_lx, bl_ly = local(bl_x, bl_y)

        base = self._quad_count * self._stride
        self._write_vertex(base + 0 * 14, tl_x, tl_y, tl_lx, tl_ly, hw, hh, color, params)
        self._write_vertex(base + 1 * 14, tr_x, tr_y, tr_lx, tr_ly, hw, hh, color, params)
        self._write_vertex(base + 2 * 14, br_x, br_y, br_lx, br_ly, hw, hh, color, params)
        self._write_vertex(base + 3 * 14, tl_x, tl_y, tl_lx, tl_ly, hw, hh, color, params)
        self._write_vertex(base + 4 * 14, br_x, br_y, br_lx, br_ly, hw, hh, color, params)
        self._write_vertex(base + 5 * 14, bl_x, bl_y, bl_lx, bl_ly, hw, hh, color, params)

        self._quad_count += 1

    def flush(self) -> None:
        """Upload accumulated geometry to the GPU and render.

        Resets the quad counter after drawing.  Safe to call when empty.
        """
        if self._quad_count == 0:
            return
        n_verts = self._quad_count * self._VERTS_PER_QUAD
        n_bytes = n_verts * self._FLOATS_PER_VERTEX * 4
        self._vbo.write(self._data.tobytes()[:n_bytes])
        self._vao.render(vertices=n_verts)
        self._quad_count = 0

    def release(self) -> None:
        """Release GPU resources (VAO then VBO)."""
        self._vao.release()
        self._vbo.release()


class PolygonBatch:
    """Pre-allocated vertex buffer for flat-coloured and gradient triangles.

    Used for convex polygon fan-triangulation, four-corner gradient quads,
    radial circle gradients, and arbitrary triangle meshes.  Vertex format:

        '2f 4f'
        in_pos (vec2), in_color (vec4)

    6 floats × 3 verts × 4 bytes = 72 bytes per triangle.
    """

    _FLOATS_PER_VERTEX: int = 6
    _VERTS_PER_TRI: int = 3

    def __init__(self, ctx: moderngl.Context, program: moderngl.Program, capacity: int = 4096) -> None:
        """Initialise with a pre-allocated buffer for *capacity* triangles.

        Args:
            ctx: Active moderngl context.
            program: Compiled POLYGON_VERTEX / POLYGON_FRAGMENT program.
            capacity: Maximum number of triangles before an automatic flush.
        """
        self._capacity = capacity
        self._tri_count = 0
        self._stride = self._FLOATS_PER_VERTEX * self._VERTS_PER_TRI
        self._data: array.array = array.array("f", [0.0] * (capacity * self._stride))
        reserve = capacity * self._stride * 4
        self._vbo = ctx.buffer(reserve=reserve, dynamic=True)
        self._vao = ctx.vertex_array(program, [(self._vbo, "2f 4f", "in_pos", "in_color")])

    def _write_vertex(self, base: int, px: float, py: float, r: float, g: float, b: float, a: float) -> None:
        """Write one vertex (6 floats) starting at *base* in ``_data``."""
        self._data[base:base + 6] = array.array("f", [px, py, r, g, b, a])

    def add_triangle(
        self,
        x0: float, y0: float,
        x1: float, y1: float,
        x2: float, y2: float,
        c0: tuple[float, float, float, float],
        c1: tuple[float, float, float, float],
        c2: tuple[float, float, float, float],
    ) -> None:
        """Enqueue a single triangle with per-vertex colours.

        Args:
            x0, y0: First vertex position in virtual coordinates.
            x1, y1: Second vertex position in virtual coordinates.
            x2, y2: Third vertex position in virtual coordinates.
            c0: RGBA (0..1) colour for the first vertex.
            c1: RGBA (0..1) colour for the second vertex.
            c2: RGBA (0..1) colour for the third vertex.
        """
        if self._tri_count >= self._capacity:
            self.flush()
        base = self._tri_count * self._stride
        self._write_vertex(base + 0,  x0, y0, *c0)
        self._write_vertex(base + 6,  x1, y1, *c1)
        self._write_vertex(base + 12, x2, y2, *c2)
        self._tri_count += 1

    def add_fan(
        self,
        cx: float,
        cy: float,
        points: list[tuple[float, float]],
        center_color: tuple[float, float, float, float],
        edge_color: tuple[float, float, float, float],
    ) -> None:
        """Fan of triangles from (cx, cy) to adjacent edge point pairs.

        Args:
            cx: Fan centre x in virtual coordinates.
            cy: Fan centre y in virtual coordinates.
            points: Ordered list of edge points (x, y).
            center_color: RGBA (0..1) colour at the fan centre.
            edge_color: RGBA (0..1) colour at the edge points.
        """
        n = len(points)
        for i in range(n):
            p0 = points[i]
            p1 = points[(i + 1) % n]
            self.add_triangle(cx, cy, p0[0], p0[1], p1[0], p1[1],
                              center_color, edge_color, edge_color)

    def flush(self) -> None:
        """Upload accumulated geometry to the GPU and render.

        Resets the triangle counter after drawing.  Safe to call when empty.
        """
        if self._tri_count == 0:
            return
        n_verts = self._tri_count * self._VERTS_PER_TRI
        n_bytes = n_verts * self._FLOATS_PER_VERTEX * 4
        self._vbo.write(self._data.tobytes()[:n_bytes])
        self._vao.render(vertices=n_verts)
        self._tri_count = 0

    def release(self) -> None:
        """Release GPU resources (VAO then VBO)."""
        self._vao.release()
        self._vbo.release()


class SpriteBatch:
    """Pre-allocated vertex buffer for textured sprite quads.

    Automatically flushes when the active texture changes so callers
    never need to manage texture binding order.  Vertex format:

        '2f 2f 4f'
        in_pos (vec2), in_texcoord (vec2), in_tint (vec4)

    8 floats × 6 vertices × 4 bytes = 192 bytes per quad.
    """

    _FLOATS_PER_VERTEX: int = 8
    _VERTS_PER_QUAD: int = 6

    def __init__(
        self,
        ctx: moderngl.Context,
        program: moderngl.Program,
        capacity: int = 1024,
    ) -> None:
        """Initialise with a pre-allocated buffer for *capacity* quads.

        Args:
            ctx: Active moderngl context.
            program: Compiled SPRITE_VERTEX / SPRITE_FRAGMENT program.
            capacity: Maximum number of quads before an automatic flush.
        """
        self._capacity = capacity
        self._quad_count = 0
        self._stride = self._FLOATS_PER_VERTEX * self._VERTS_PER_QUAD
        self._data: array.array = array.array(
            "f", [0.0] * (capacity * self._stride)
        )
        reserve = capacity * self._stride * 4
        self._vbo: moderngl.Buffer = ctx.buffer(reserve=reserve, dynamic=True)
        self._vao: moderngl.VertexArray = ctx.vertex_array(
            program,
            [
                (
                    self._vbo,
                    "2f 2f 4f",
                    "in_pos",
                    "in_texcoord",
                    "in_tint",
                )
            ],
        )
        self._current_texture: moderngl.Texture | None = None

    def _write_vertex(
        self,
        base: int,
        px: float,
        py: float,
        u: float,
        v: float,
        tint: tuple[float, float, float, float],
    ) -> None:
        """Write one vertex (8 floats) starting at *base* in ``_data``."""
        r, g, b, a = tint
        self._data[base:base + 8] = array.array("f", [px, py, u, v, r, g, b, a])

    def add_quad(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        texture: moderngl.Texture,
        *,
        tint: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        src: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    ) -> None:
        """Enqueue a textured quad.

        Automatically flushes if the texture changes or the buffer is full.

        Args:
            x: Left edge in virtual coordinates.
            y: Top edge in virtual coordinates.
            w: Width in virtual pixels.
            h: Height in virtual pixels.
            texture: moderngl Texture to sample.
            tint: RGBA multiplier applied in the fragment shader.
            src: (u0, v0, u1, v1) normalised texcoord sub-rect.
        """
        if texture is not self._current_texture:
            self.flush()
            texture.use(0)
            self._current_texture = texture

        if self._quad_count >= self._capacity:
            self.flush()

        u0, v0, u1, v1 = src
        base = self._quad_count * self._stride

        self._write_vertex(base + 0 * 8, x,     y,     u0, v0, tint)
        self._write_vertex(base + 1 * 8, x + w, y,     u1, v0, tint)
        self._write_vertex(base + 2 * 8, x + w, y + h, u1, v1, tint)
        self._write_vertex(base + 3 * 8, x,     y,     u0, v0, tint)
        self._write_vertex(base + 4 * 8, x + w, y + h, u1, v1, tint)
        self._write_vertex(base + 5 * 8, x,     y + h, u0, v1, tint)

        self._quad_count += 1

    def flush(self) -> None:
        """Upload accumulated geometry to the GPU and render.

        Resets the quad counter after drawing.  Safe to call when empty.
        """
        if self._quad_count == 0:
            return
        n_verts = self._quad_count * self._VERTS_PER_QUAD
        n_bytes = n_verts * self._FLOATS_PER_VERTEX * 4
        self._vbo.write(self._data.tobytes()[:n_bytes])
        self._vao.render(vertices=n_verts)
        self._quad_count = 0

    def release(self) -> None:
        """Release GPU resources (VAO then VBO)."""
        self._vao.release()
        self._vbo.release()
