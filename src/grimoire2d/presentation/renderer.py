"""OpenGL renderer (presentation layer).

Owns the moderngl context, all shader programs, VAOs, and the current
viewport + projection state. No raw GL or moderngl calls are allowed
outside this module (and the thin window bootstrap that creates the
pygame display + context).

For this increment the renderer provides just enough to prove:
- Virtual resolution is data driven (1280x720 default) and changeable at runtime.
- Integer scaling + letterboxing with proper glViewport.
- Resizable window updates the letterbox live.
- All drawing happens in virtual coordinate space.

A full sprite batcher, texture support, and multiple programs will be
added in later increments on top of this foundation.
"""

from __future__ import annotations

import array

import moderngl
import pygame

from grimoire2d.logic.scaling import Viewport, compute_viewport
from grimoire2d.models import VirtualResolution
from grimoire2d.presentation.batch import (
    PolygonBatch,
    ShapeBatch,
    ShapeType,
    SpriteBatch,
)
from grimoire2d.presentation.pixel_buffer import PixelBuffer
from grimoire2d.presentation.shaders import (
    get_default_fragment_shader,
    get_default_vertex_shader,
    get_pixel_buffer_fragment_shader,
    get_pixel_buffer_vertex_shader,
    get_polygon_fragment_shader,
    get_polygon_vertex_shader,
    get_shape_fragment_shader,
    get_shape_vertex_shader,
    get_sprite_fragment_shader,
    get_sprite_vertex_shader,
    get_textured_fragment_shader,
    get_textured_vertex_shader,
)


def _ortho(
    left: float,
    right: float,
    top: float,
    bottom: float,
    near: float = -1.0,
    far: float = 1.0,
) -> tuple[float, ...]:
    """Return a column-major 4x4 ortho matrix as 16 floats.

    Configured for top-left origin, y increasing downward (virtual 2D
    coordinates like classic 2D engines). (0,0) is top-left of virtual.
    """
    rml = right - left
    tmb = top - bottom
    fmn = far - near

    a = 2.0 / rml
    b = 2.0 / tmb
    c = -2.0 / fmn

    tx = -(right + left) / rml
    ty = -(top + bottom) / tmb
    tz = -(far + near) / fmn

    # Column major order for GL
    return (
        a,
        0.0,
        0.0,
        0.0,
        0.0,
        b,
        0.0,
        0.0,
        0.0,
        0.0,
        c,
        0.0,
        tx,
        ty,
        tz,
        1.0,
    )


class Renderer:
    """Encapsulates the OpenGL 3.30 core rendering pipeline.

    The window/presentation bootstrap code creates the pygame display
    with the proper GL attributes and passes the resulting moderngl
    context here. All subsequent GL work (programs, draws, viewport,
    clears for letterboxing) happens through this object.
    """

    def __init__(
        self, ctx: moderngl.Context, initial_virtual: VirtualResolution | None = None
    ) -> None:
        """Initialise the renderer with a live moderngl context.

        Args:
            ctx: The moderngl context created by the window bootstrap.
            initial_virtual: Starting virtual resolution; defaults to 1280x720.
        """
        self.ctx = ctx
        self._virt = initial_virtual or VirtualResolution()
        self._phys: tuple[int, int] = (self._virt.width, self._virt.height)
        self._viewport: Viewport = compute_viewport(
            self._virt, self._phys[0], self._phys[1]
        )

        # Legacy solid-colour program (kept for backward compatibility)
        vert_src = get_default_vertex_shader()
        frag_src = get_default_fragment_shader()
        self.program = self.ctx.program(
            vertex_shader=vert_src,
            fragment_shader=frag_src,
        )

        quad_data = array.array(
            "f",
            [
                0.0,
                0.0,
                1.0,
                0.0,
                1.0,
                1.0,
                0.0,
                0.0,
                1.0,
                1.0,
                0.0,
                1.0,
            ],
        )
        self._quad_vbo = self.ctx.buffer(quad_data.tobytes())
        self._quad_vao = self.ctx.simple_vertex_array(
            self.program, self._quad_vbo, "in_pos"
        )

        # Textured quad for text (and future 2D sprites).
        textured_quad_data = array.array(
            "f",
            [
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
                1.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                0.0,
                1.0,
                0.0,
                1.0,
            ],
        )
        self._textured_quad_vbo = self.ctx.buffer(textured_quad_data.tobytes())

        tvert = get_textured_vertex_shader()
        tfrag = get_textured_fragment_shader()
        self.text_program = self.ctx.program(
            vertex_shader=tvert,
            fragment_shader=tfrag,
        )
        self._text_vao = self.ctx.vertex_array(
            self.text_program,
            [(self._textured_quad_vbo, "2f 2f", "in_pos", "in_texcoord")],
        )

        self._projection: tuple[float, ...] = _ortho(
            0.0, float(self._virt.width), 0.0, float(self._virt.height)
        )
        self.program["u_projection"].value = self._projection
        self.text_program["u_projection"].value = self._projection

        # SDF shape batch
        self._shape_program = self.ctx.program(
            vertex_shader=get_shape_vertex_shader(),
            fragment_shader=get_shape_fragment_shader(),
        )
        self._shape_program["u_projection"].value = self._projection
        self._shape_batch = ShapeBatch(self.ctx, self._shape_program)

        # Sprite batch
        self._sprite_program = self.ctx.program(
            vertex_shader=get_sprite_vertex_shader(),
            fragment_shader=get_sprite_fragment_shader(),
        )
        self._sprite_program["u_projection"].value = self._projection
        self._sprite_batch = SpriteBatch(self.ctx, self._sprite_program)

        # Polygon batch (triangles, convex polygons, corner gradients, radial gradients)
        self._polygon_program = self.ctx.program(
            vertex_shader=get_polygon_vertex_shader(),
            fragment_shader=get_polygon_fragment_shader(),
        )
        self._polygon_program["u_projection"].value = self._projection
        self._polygon_batch = PolygonBatch(self.ctx, self._polygon_program)

        # Pixel buffer program + static unit-quad
        self._pixel_buffer_program = self.ctx.program(
            vertex_shader=get_pixel_buffer_vertex_shader(),
            fragment_shader=get_pixel_buffer_fragment_shader(),
        )
        self._pixel_buffer_program["u_projection"].value = self._projection

        _pb_quad = array.array(
            "f",
            [
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
                1.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                0.0,
                1.0,
                0.0,
                1.0,
            ],
        )
        self._pb_vbo = self.ctx.buffer(_pb_quad.tobytes())
        self._pb_vao = self.ctx.vertex_array(
            self._pixel_buffer_program,
            [(self._pb_vbo, "2f 2f", "in_pos", "in_texcoord")],
        )

        # Clip stack: list of (x, y, w, h) tuples in virtual coordinates
        self._clip_stack: list[tuple[float, float, float, float]] = []

        self._bar_color = (20, 20, 30, 255)
        self._game_clear = (0, 0, 0, 255)
        self._frame_textures: list[moderngl.Texture] = []

        # Persistent text cache: (text, font_size) → texture.
        # Avoids re-rasterising and re-uploading static labels every frame.
        self._text_cache: dict[tuple[str, int], moderngl.Texture] = {}

    def set_virtual_resolution(self, virtual: VirtualResolution) -> None:
        """Update the game virtual resolution at runtime (data driven).

        Recomputes the current viewport (using last known physical size)
        and the orthographic projection. The next frame will render
        using the new virtual coordinate space.
        """
        if virtual.width == self._virt.width and virtual.height == self._virt.height:
            self._virt = virtual
            return
        self._virt = virtual
        self._viewport = compute_viewport(self._virt, self._phys[0], self._phys[1])
        self._projection = _ortho(
            0.0, float(self._virt.width), 0.0, float(self._virt.height)
        )
        self.program["u_projection"].value = self._projection
        self.text_program["u_projection"].value = self._projection
        self._shape_program["u_projection"].value = self._projection
        self._sprite_program["u_projection"].value = self._projection
        self._polygon_program["u_projection"].value = self._projection
        self._pixel_buffer_program["u_projection"].value = self._projection
        # Font sizes are derived from the virtual height, so cached textures
        # rendered at the old scale are no longer valid.
        for tex in self._text_cache.values():
            tex.release()
        self._text_cache.clear()

    def handle_physical_resize(self, physical_width: int, physical_height: int) -> None:
        """React to a window resize (or initial size, or fullscreen change).

        Recomputes letterbox/scale and updates GL viewport on next prepare.
        """
        if physical_width == self._phys[0] and physical_height == self._phys[1]:
            return
        self._phys = (physical_width, physical_height)
        self._viewport = compute_viewport(self._virt, physical_width, physical_height)

    def set_clear_color(self, color: tuple[int, int, int, int]) -> None:
        """Update the game area clear color (from VideoSettings etc.)."""
        self._game_clear = color

    def prepare_frame(self) -> None:
        """Prepare letterbox bars + game viewport for the current frame.

        Must be called every frame (or on any virt/resize change before draws).
        Clears the full physical window to the bar color, then sets the
        letterboxed viewport and clears the game area to the configured color.
        All subsequent draw_* calls will land inside the game rect.
        """
        vp = self._viewport
        phys_w, phys_h = self._phys

        # Disable any scissor left over from the previous frame
        self.ctx.scissor = None
        self._clip_stack.clear()

        # Full window clear for the bars/pillarbox
        self.ctx.viewport = (0, 0, phys_w, phys_h)
        r, g, b, a = (c / 255.0 for c in self._bar_color)
        self.ctx.clear(r, g, b, a)

        # Game content viewport (letterboxed)
        self.ctx.viewport = (
            vp.viewport_x,
            vp.viewport_y,
            vp.viewport_width,
            vp.viewport_height,
        )
        r, g, b, a = (c / 255.0 for c in self._game_clear)
        self.ctx.clear(r, g, b, a)

        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)

    def draw_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        color: tuple[float, float, float, float],
    ) -> None:
        """Draw a solid rectangle in *virtual* coordinates via the SDF batch.

        (x, y) is the top-left corner in the current virtual resolution space.
        This is resolution-independent: the same call renders correctly at any
        physical window size or virtual resolution.
        """
        self._shape_batch.add_quad(x, y, w, h, color, shape_type=ShapeType.RECT)

    def draw_rect_rounded(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        radius: float,
        color: tuple[float, float, float, float],
    ) -> None:
        """Draw a filled rectangle with rounded corners.

        Args:
            x: Left edge in virtual coordinates.
            y: Top edge in virtual coordinates.
            w: Width in virtual pixels.
            h: Height in virtual pixels.
            radius: Corner radius in virtual pixels.
            color: RGBA (0..1) fill colour.
        """
        self._shape_batch.add_quad(
            x,
            y,
            w,
            h,
            color,
            shape_type=ShapeType.ROUNDED_RECT,
            corner_r=radius,
        )

    def draw_rect_gradient(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        color_top: tuple[float, float, float, float],
        color_bottom: tuple[float, float, float, float],
    ) -> None:
        """Draw a filled rectangle with a vertical linear gradient.

        Args:
            x: Left edge in virtual coordinates.
            y: Top edge in virtual coordinates.
            w: Width in virtual pixels.
            h: Height in virtual pixels.
            color_top: RGBA (0..1) colour at the top edge.
            color_bottom: RGBA (0..1) colour at the bottom edge.
        """
        self._shape_batch.add_quad(
            x,
            y,
            w,
            h,
            color_top,
            shape_type=ShapeType.RECT,
            color_b=color_bottom,
        )

    def draw_rect_border(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        thickness: float,
        color: tuple[float, float, float, float],
    ) -> None:
        """Draw an axis-aligned rectangle outline (stroke only).

        Args:
            x: Left edge in virtual coordinates.
            y: Top edge in virtual coordinates.
            w: Width in virtual pixels.
            h: Height in virtual pixels.
            thickness: Stroke width in virtual pixels.
            color: RGBA (0..1) stroke colour.
        """
        self._shape_batch.add_quad(
            x,
            y,
            w,
            h,
            color,
            shape_type=ShapeType.RECT_BORDER,
            border_t=thickness,
        )

    def draw_rect_rounded_border(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        radius: float,
        thickness: float,
        color: tuple[float, float, float, float],
    ) -> None:
        """Draw a rounded rectangle outline (stroke only).

        Args:
            x: Left edge in virtual coordinates.
            y: Top edge in virtual coordinates.
            w: Width in virtual pixels.
            h: Height in virtual pixels.
            radius: Corner radius in virtual pixels.
            thickness: Stroke width in virtual pixels.
            color: RGBA (0..1) stroke colour.
        """
        self._shape_batch.add_quad(
            x,
            y,
            w,
            h,
            color,
            shape_type=ShapeType.ROUNDED_RECT_BORDER,
            corner_r=radius,
            border_t=thickness,
        )

    def draw_circle(
        self,
        cx: float,
        cy: float,
        r: float,
        color: tuple[float, float, float, float],
    ) -> None:
        """Draw a filled circle.

        Args:
            cx: Centre x in virtual coordinates.
            cy: Centre y in virtual coordinates.
            r: Radius in virtual pixels.
            color: RGBA (0..1) fill colour.
        """
        self._shape_batch.add_quad(
            cx - r,
            cy - r,
            r * 2.0,
            r * 2.0,
            color,
            shape_type=ShapeType.CIRCLE,
        )

    def draw_ring(
        self,
        cx: float,
        cy: float,
        outer_r: float,
        inner_r: float,
        color: tuple[float, float, float, float],
    ) -> None:
        """Draw a ring / annulus.

        Args:
            cx: Centre x in virtual coordinates.
            cy: Centre y in virtual coordinates.
            outer_r: Outer radius in virtual pixels.
            inner_r: Inner radius (hole) in virtual pixels.
            color: RGBA (0..1) fill colour.
        """
        self._shape_batch.add_quad(
            cx - outer_r,
            cy - outer_r,
            outer_r * 2.0,
            outer_r * 2.0,
            color,
            shape_type=ShapeType.RING,
            inner_r=inner_r,
        )

    def draw_line(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        thickness: float,
        color: tuple[float, float, float, float],
    ) -> None:
        """Draw an arbitrarily-angled line segment.

        Args:
            x0: Start x in virtual coordinates.
            y0: Start y in virtual coordinates.
            x1: End x in virtual coordinates.
            y1: End y in virtual coordinates.
            thickness: Line width in virtual pixels.
            color: RGBA (0..1) colour.
        """
        self._shape_batch.add_line(x0, y0, x1, y1, thickness, color)

    def push_clip(self, x: float, y: float, w: float, h: float) -> None:
        """Enable a scissor rectangle, clipping all subsequent draws.

        Flushes both batches before changing GL scissor state.  Virtual
        coordinates are converted to physical pixels using the current
        viewport transform.

        Args:
            x: Left edge of clip rect in virtual coordinates.
            y: Top edge of clip rect in virtual coordinates.
            w: Width of clip rect in virtual pixels.
            h: Height of clip rect in virtual pixels.
        """
        self._shape_batch.flush()
        self._polygon_batch.flush()
        self._sprite_batch.flush()
        self._clip_stack.append((x, y, w, h))
        self._apply_scissor(x, y, w, h)

    def pop_clip(self) -> None:
        """Restore the previous scissor rectangle (or disable scissor).

        Flushes all batches before changing GL scissor state.
        """
        self._shape_batch.flush()
        self._polygon_batch.flush()
        self._sprite_batch.flush()
        if self._clip_stack:
            self._clip_stack.pop()
        if not self._clip_stack:
            self.ctx.scissor = None
        else:
            x, y, w, h = self._clip_stack[-1]
            self._apply_scissor(x, y, w, h)

    def _apply_scissor(self, x: float, y: float, w: float, h: float) -> None:
        """Convert virtual-space clip rect to physical pixels and set GL scissor.

        Args:
            x: Left edge in virtual coordinates.
            y: Top edge in virtual coordinates.
            w: Clip width in virtual pixels.
            h: Clip height in virtual pixels.
        """
        vp = self._viewport
        scale = vp.viewport_width / self._virt.width
        sx = int(vp.viewport_x + x * scale)
        sy = int(vp.viewport_y + (self._virt.height - y - h) * scale)
        sw = int(w * scale)
        sh = int(h * scale)
        self.ctx.scissor = (sx, sy, sw, sh)

    def draw_pixel_buffer(
        self,
        pixel_buffer: PixelBuffer,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> None:
        """Render a PixelBuffer texture as a nearest-neighbour scaled quad.

        Call ``pixel_buffer.upload()`` before this method each frame.

        Args:
            pixel_buffer: The PixelBuffer whose texture to render.
            x: Left edge destination in virtual coordinates.
            y: Top edge destination in virtual coordinates.
            w: Destination width in virtual pixels.
            h: Destination height in virtual pixels.
        """
        self._shape_batch.flush()
        self._sprite_batch.flush()
        pixel_buffer.texture.use(0)
        self._pixel_buffer_program["u_offset"].value = (float(x), float(y))
        self._pixel_buffer_program["u_scale"].value = (float(w), float(h))
        self._pixel_buffer_program["u_texture"].value = 0
        self._pb_vao.render()

    def draw_virtual_border(self, thickness: float = 4.0) -> None:
        """Draw a thin border exactly at the virtual resolution edges.

        Extremely useful visual proof for letterboxing and scaling.
        """
        v_w = float(self._virt.width)
        v_h = float(self._virt.height)
        t = float(thickness)
        c = (0.9, 0.9, 0.2, 1.0)

        self.draw_rect(0, 0, v_w, t, c)
        self.draw_rect(0, v_h - t, v_w, t, c)
        self.draw_rect(0, 0, t, v_h, c)
        self.draw_rect(v_w - t, 0, t, v_h, c)

    def draw_test_pattern(self) -> None:
        """A few fixed-size colored rects at fixed virtual positions.

        These keep their size and placement relative to the virtual
        resolution no matter how the user resizes the OS window or
        changes the virtual resolution at runtime.
        """
        self.draw_rect(40, 40, 180, 120, (0.2, 0.6, 1.0, 1.0))
        cx = (self._virt.width - 220) / 2
        cy = (self._virt.height - 160) / 2
        self.draw_rect(cx, cy, 220, 160, (1.0, 0.3, 0.3, 1.0))
        self.draw_rect(
            self._virt.width - 260,
            self._virt.height - 140,
            200,
            100,
            (0.3, 0.9, 0.4, 1.0),
        )

        self.draw_text(
            f"Virtual: {self._virt.width}x{self._virt.height}  (press 1-4 to change)",
            240,
            20,
            color=(1.0, 1.0, 0.2, 1.0),
            scale=1.0,
            font_size=26,
        )
        self.draw_text(
            "Text is a primitive. Full logical surface scales + letterboxes correctly.",
            240,
            55,
            color=(0.7, 0.9, 1.0, 0.9),
            scale=0.75,
            font_size=18,
        )

    # --- Text primitive support ---

    def _get_font(self, size: int):
        """Lazy cache for pygame fonts (default system font for the primitive).

        Font size is the base render size; the ``scale`` parameter in draw_text
        then multiplies the resulting quad size in virtual coordinates.
        """
        if not hasattr(self, "_fonts"):
            self._fonts = {}
        if size not in self._fonts:
            self._fonts[size] = pygame.font.Font(None, size)
        return self._fonts[size]

    def draw_text(
        self,
        text: str,
        x: float,
        y: float,
        *,
        color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        scale: float = 1.0,
        font_size: int = 32,
    ) -> None:
        """Draw text as a primitive in *virtual* (logical) coordinates.

        This is the foundational text drawing capability. The string, color
        (with alpha for transparency), and scale can all be changed every frame.

        - (x, y) is the top-left of the text in the current virtual resolution.
        - ``scale`` multiplies the rendered size (in virtual units).
        - ``font_size`` is the base pygame font size used for rasterization.
        - Color tints the (white) rendered text and applies alpha.

        All drawing happens through the current logical viewport/projection,
        so text automatically respects the same scaling + letterboxing as
        everything else.

        This primitive is intended for debug overlays, simple HUD elements,
        and custom immediate drawing inside games. Professional tooling GUIs
        are built with an external library such as Dear PyGui (see demos/).
        """
        if not text:
            return

        self._shape_batch.flush()

        # Look up the cache first to skip rasterisation + upload for static labels.
        cache_key = (text, font_size)
        texture = self._text_cache.get(cache_key)
        if texture is None:
            font = self._get_font(font_size)
            surf = font.render(text, True, (255, 255, 255)).convert_alpha()
            tw, th = surf.get_size()
            if tw <= 0 or th <= 0:
                return
            data = pygame.image.tostring(surf, "RGBA", False)
            texture = self.ctx.texture((tw, th), 4, data)
            texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
            # FIFO eviction at 512 entries to bound cache memory.
            if len(self._text_cache) >= 512:
                evict_key = next(iter(self._text_cache))
                self._text_cache.pop(evict_key).release()
            self._text_cache[cache_key] = texture

        tw, th = texture.width, texture.height
        texture.use(0)

        self.text_program["u_offset"].value = (float(x), float(y))
        self.text_program["u_scale"].value = (float(tw) * scale, float(th) * scale)
        self.text_program["u_color"].value = color
        self.text_program["u_texture"].value = 0

        self._text_vao.render()

    def measure_text(
        self, text: str, *, font_size: int = 32, scale: float = 1.0
    ) -> tuple[float, float]:
        """Return the (width, height) in virtual units the text would occupy.

        Useful for layout helpers, debug labels, and simple HUD text.
        """
        if not text:
            return 0.0, 0.0
        font = self._get_font(font_size)
        tw, th = font.size(text)
        return tw * scale, th * scale

    def draw_text_centered(
        self,
        text: str,
        cx: float,
        cy: float,
        *,
        color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        scale: float = 1.0,
        font_size: int = 32,
    ) -> None:
        """Centered variant of the text primitive (common for UI/console titles etc)."""
        w, h = self.measure_text(text, font_size=font_size, scale=scale)
        x = cx - w / 2.0
        y = cy - h / 2.0
        self.draw_text(text, x, y, color=color, scale=scale, font_size=font_size)

    # --- SDF shapes (new types) ---

    def draw_ellipse(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        color: tuple[float, float, float, float],
    ) -> None:
        """Draw a filled ellipse.

        Args:
            cx: Centre x in virtual coordinates.
            cy: Centre y in virtual coordinates.
            rx: Horizontal radius in virtual pixels.
            ry: Vertical radius in virtual pixels.
            color: RGBA (0..1) fill colour.
        """
        self._shape_batch.add_quad(
            cx - rx, cy - ry, rx * 2.0, ry * 2.0, color, shape_type=ShapeType.ELLIPSE
        )

    def draw_arc(
        self,
        cx: float,
        cy: float,
        r: float,
        angle_start: float,
        angle_end: float,
        thickness: float,
        color: tuple[float, float, float, float],
    ) -> None:
        """Draw a circular arc (ring sector).

        Args:
            cx: Centre x in virtual coordinates.
            cy: Centre y in virtual coordinates.
            r: Radius in virtual pixels.
            angle_start: Start angle in radians.
            angle_end: End angle in radians.
            thickness: Ring thickness in virtual pixels.
            color: RGBA (0..1) colour.
        """
        import math

        span = (angle_end - angle_start) % (2.0 * math.pi)
        if span < 1e-6:
            span = 2.0 * math.pi
        self._shape_batch.add_quad(
            cx - r,
            cy - r,
            r * 2.0,
            r * 2.0,
            color,
            shape_type=ShapeType.ARC,
            corner_r=thickness,
            border_t=angle_start,
            inner_r=span,
        )

    def draw_pie(
        self,
        cx: float,
        cy: float,
        r: float,
        angle_start: float,
        angle_end: float,
        color: tuple[float, float, float, float],
    ) -> None:
        """Draw a filled circle sector (pie slice).

        Args:
            cx: Centre x in virtual coordinates.
            cy: Centre y in virtual coordinates.
            r: Radius in virtual pixels.
            angle_start: Start angle in radians.
            angle_end: End angle in radians.
            color: RGBA (0..1) fill colour.
        """
        import math

        span = (angle_end - angle_start) % (2.0 * math.pi)
        if span < 1e-6:
            span = 2.0 * math.pi
        self._shape_batch.add_quad(
            cx - r,
            cy - r,
            r * 2.0,
            r * 2.0,
            color,
            shape_type=ShapeType.PIE,
            corner_r=angle_start,
            border_t=span,
        )

    def draw_capsule(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        color: tuple[float, float, float, float],
    ) -> None:
        """Draw a filled capsule (rectangle with fully rounded ends).

        Args:
            x: Left edge in virtual coordinates.
            y: Top edge in virtual coordinates.
            w: Width in virtual pixels.
            h: Height in virtual pixels.
            color: RGBA (0..1) fill colour.
        """
        self._shape_batch.add_quad(x, y, w, h, color, shape_type=ShapeType.CAPSULE)

    # --- Drop shadow / glow ---

    def draw_drop_shadow(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        ox: float = 4.0,
        oy: float = 4.0,
        blur: float = 12.0,
        radius: float = 0.0,
        color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.5),
    ) -> None:
        """Draw a soft drop shadow behind a rectangular region.

        The shadow is rendered as a GLOW quad offset by (ox, oy) and expanded
        by ``blur`` on all sides.  Draw this before the shape it shadows.

        Args:
            x: Left edge of the shadowed shape in virtual coordinates.
            y: Top edge of the shadowed shape in virtual coordinates.
            w: Width of the shadowed shape in virtual pixels.
            h: Height of the shadowed shape in virtual pixels.
            ox: Horizontal shadow offset in virtual pixels.
            oy: Vertical shadow offset in virtual pixels.
            blur: Glow spread radius in virtual pixels.
            radius: Corner radius of the shadowed shape.
            color: RGBA (0..1) shadow colour (alpha controls opacity).
        """
        sx = x + ox - blur
        sy = y + oy - blur
        sw = w + blur * 2.0
        sh = h + blur * 2.0
        self._shape_batch.add_quad(
            sx,
            sy,
            sw,
            sh,
            color,
            shape_type=ShapeType.GLOW,
            corner_r=blur,
            border_t=radius,
        )

    # --- Gradients ---

    def draw_rect_gradient_h(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        color_left: tuple[float, float, float, float],
        color_right: tuple[float, float, float, float],
    ) -> None:
        """Draw a filled rectangle with a horizontal linear gradient.

        Args:
            x: Left edge in virtual coordinates.
            y: Top edge in virtual coordinates.
            w: Width in virtual pixels.
            h: Height in virtual pixels.
            color_left: RGBA (0..1) colour at the left edge.
            color_right: RGBA (0..1) colour at the right edge.
        """
        self._shape_batch.add_quad(
            x, y, w, h, color_left, color_b=color_right, gradient_mode=1
        )

    def draw_rect_gradient_corner(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        c_tl: tuple[float, float, float, float],
        c_tr: tuple[float, float, float, float],
        c_bl: tuple[float, float, float, float],
        c_br: tuple[float, float, float, float],
    ) -> None:
        """Draw a rectangle with independent colours at each corner.

        Uses the polygon batch (two triangles) for per-vertex colour support.

        Args:
            x: Left edge in virtual coordinates.
            y: Top edge in virtual coordinates.
            w: Width in virtual pixels.
            h: Height in virtual pixels.
            c_tl: RGBA (0..1) colour at the top-left corner.
            c_tr: RGBA (0..1) colour at the top-right corner.
            c_bl: RGBA (0..1) colour at the bottom-left corner.
            c_br: RGBA (0..1) colour at the bottom-right corner.
        """
        self._polygon_batch.add_triangle(x, y, x + w, y, x + w, y + h, c_tl, c_tr, c_br)
        self._polygon_batch.add_triangle(x, y, x + w, y + h, x, y + h, c_tl, c_br, c_bl)

    def draw_circle_gradient(
        self,
        cx: float,
        cy: float,
        r: float,
        color_center: tuple[float, float, float, float],
        color_edge: tuple[float, float, float, float],
        *,
        segments: int = 48,
    ) -> None:
        """Draw a filled circle with a radial gradient.

        The polygon batch fan-triangulates from the centre outward.

        Args:
            cx: Centre x in virtual coordinates.
            cy: Centre y in virtual coordinates.
            r: Radius in virtual pixels.
            color_center: RGBA (0..1) colour at the centre.
            color_edge: RGBA (0..1) colour at the edge.
            segments: Number of triangular segments (higher = smoother).
        """
        import math

        pts = [
            (
                cx + math.cos(2 * math.pi * i / segments) * r,
                cy + math.sin(2 * math.pi * i / segments) * r,
            )
            for i in range(segments)
        ]
        self._polygon_batch.add_fan(cx, cy, pts, color_center, color_edge)

    # --- Triangles and polygons ---

    def draw_triangle(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: tuple[float, float, float, float],
    ) -> None:
        """Draw a filled triangle with a uniform colour.

        Args:
            x0, y0: First vertex in virtual coordinates.
            x1, y1: Second vertex in virtual coordinates.
            x2, y2: Third vertex in virtual coordinates.
            color: RGBA (0..1) fill colour.
        """
        self._polygon_batch.add_triangle(x0, y0, x1, y1, x2, y2, color, color, color)

    def draw_polygon(
        self,
        points: list[tuple[float, float]],
        color: tuple[float, float, float, float],
    ) -> None:
        """Draw a filled convex polygon via fan triangulation from points[0].

        Args:
            points: Ordered list of (x, y) vertices in virtual coordinates.
                    Must be convex for correct rendering.
            color: RGBA (0..1) fill colour.
        """
        n = len(points)
        if n < 3:
            return
        for i in range(1, n - 1):
            x0, y0 = points[0]
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            self._polygon_batch.add_triangle(
                x0, y0, x1, y1, x2, y2, color, color, color
            )

    # --- Lines ---

    def draw_polyline(
        self,
        points: list[tuple[float, float]],
        thickness: float,
        color: tuple[float, float, float, float],
        *,
        closed: bool = False,
    ) -> None:
        """Draw a series of connected line segments.

        Args:
            points: Ordered list of (x, y) vertices in virtual coordinates.
            thickness: Line width in virtual pixels.
            color: RGBA (0..1) colour.
            closed: If True, connects the last point back to the first.
        """
        n = len(points)
        for i in range(n - 1):
            x0, y0 = points[i]
            x1, y1 = points[i + 1]
            self._shape_batch.add_line(x0, y0, x1, y1, thickness, color)
        if closed and n > 2:
            x0, y0 = points[-1]
            x1, y1 = points[0]
            self._shape_batch.add_line(x0, y0, x1, y1, thickness, color)

    def draw_dashed_line(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        thickness: float,
        color: tuple[float, float, float, float],
        *,
        dash: float = 8.0,
        gap: float = 4.0,
    ) -> None:
        """Draw a dashed line segment.

        Args:
            x0: Start x in virtual coordinates.
            y0: Start y in virtual coordinates.
            x1: End x in virtual coordinates.
            y1: End y in virtual coordinates.
            thickness: Line width in virtual pixels.
            color: RGBA (0..1) colour.
            dash: Length of each dash in virtual pixels.
            gap: Gap between dashes in virtual pixels.
        """
        import math

        dx, dy = x1 - x0, y1 - y0
        total = math.sqrt(dx * dx + dy * dy)
        if total < 1e-9:
            return
        ux, uy = dx / total, dy / total
        period = dash + gap
        t = 0.0
        while t < total:
            t1 = min(t + dash, total)
            self._shape_batch.add_line(
                x0 + ux * t, y0 + uy * t, x0 + ux * t1, y0 + uy * t1, thickness, color
            )
            t += period

    def draw_bezier_quadratic(
        self,
        x0: float,
        y0: float,
        cx: float,
        cy: float,
        x1: float,
        y1: float,
        thickness: float,
        color: tuple[float, float, float, float],
        *,
        segments: int = 16,
    ) -> None:
        """Draw a quadratic Bezier curve as a polyline.

        Args:
            x0, y0: Start point in virtual coordinates.
            cx, cy: Control point in virtual coordinates.
            x1, y1: End point in virtual coordinates.
            thickness: Line width in virtual pixels.
            color: RGBA (0..1) colour.
            segments: Number of line segments used to approximate the curve.
        """
        pts = []
        for i in range(segments + 1):
            t = i / segments
            mt = 1.0 - t
            pts.append(
                (
                    mt * mt * x0 + 2 * mt * t * cx + t * t * x1,
                    mt * mt * y0 + 2 * mt * t * cy + t * t * y1,
                )
            )
        self.draw_polyline(pts, thickness, color)

    def draw_bezier_cubic(
        self,
        x0: float,
        y0: float,
        cx0: float,
        cy0: float,
        cx1: float,
        cy1: float,
        x1: float,
        y1: float,
        thickness: float,
        color: tuple[float, float, float, float],
        *,
        segments: int = 24,
    ) -> None:
        """Draw a cubic Bezier curve as a polyline.

        Args:
            x0, y0: Start point in virtual coordinates.
            cx0, cy0: First control point in virtual coordinates.
            cx1, cy1: Second control point in virtual coordinates.
            x1, y1: End point in virtual coordinates.
            thickness: Line width in virtual pixels.
            color: RGBA (0..1) colour.
            segments: Number of line segments used to approximate the curve.
        """
        pts = []
        for i in range(segments + 1):
            t = i / segments
            mt = 1.0 - t
            pts.append(
                (
                    mt**3 * x0 + 3 * mt**2 * t * cx0 + 3 * mt * t**2 * cx1 + t**3 * x1,
                    mt**3 * y0 + 3 * mt**2 * t * cy0 + 3 * mt * t**2 * cy1 + t**3 * y1,
                )
            )
        self.draw_polyline(pts, thickness, color)

    # --- Sprites ---

    def draw_sprite(
        self,
        texture,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        tint: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        src: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    ) -> None:
        """Draw a textured sprite quad.

        Flushes the shape and polygon batches first to preserve draw order.

        Args:
            texture: moderngl Texture to sample.
            x: Left edge in virtual coordinates.
            y: Top edge in virtual coordinates.
            w: Width in virtual pixels.
            h: Height in virtual pixels.
            tint: RGBA (0..1) colour multiplier.
            src: (u0, v0, u1, v1) normalised texcoord sub-rectangle.
        """
        self._shape_batch.flush()
        self._polygon_batch.flush()
        self._sprite_batch.add_quad(x, y, w, h, texture, tint=tint, src=src)

    def draw_nine_slice(
        self,
        texture,
        x: float,
        y: float,
        w: float,
        h: float,
        border: float,
        *,
        tint: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
    ) -> None:
        """Draw a nine-slice scaled texture (UI panel / frame).

        The texture is divided into a 3×3 grid by ``border`` pixels on each
        side.  Corner cells are drawn at their natural size; edge and centre
        cells stretch to fill the target dimensions.

        Args:
            texture: moderngl Texture to sample.
            x: Left edge in virtual coordinates.
            y: Top edge in virtual coordinates.
            w: Width in virtual pixels (>= 2 * border).
            h: Height in virtual pixels (>= 2 * border).
            border: Corner/edge width in texels.
            tint: RGBA (0..1) colour multiplier.
        """
        self._shape_batch.flush()
        self._polygon_batch.flush()
        tw, th = texture.width, texture.height
        bx, by = border / tw, border / th
        b = border
        cols_d = [x, x + b, x + w - b]
        cols_w = [b, w - 2 * b, b]
        rows_d = [y, y + b, y + h - b]
        rows_h = [b, h - 2 * b, b]
        cols_u = [0.0, bx, 1.0 - bx]
        cols_uw = [bx, 1.0 - 2 * bx, bx]
        rows_v = [0.0, by, 1.0 - by]
        rows_vh = [by, 1.0 - 2 * by, by]
        for row in range(3):
            for col in range(3):
                src = (
                    cols_u[col],
                    rows_v[row],
                    cols_u[col] + cols_uw[col],
                    rows_v[row] + rows_vh[row],
                )
                self._sprite_batch.add_quad(
                    cols_d[col],
                    rows_d[row],
                    cols_w[col],
                    rows_h[row],
                    texture,
                    tint=tint,
                    src=src,
                )

    def present(self) -> None:
        """Flush pending batches and swap / finish the frame.

        With pygame + moderngl the pygame.display.flip() after this
        (or ctx.finish()) is usually sufficient.
        """
        self._shape_batch.flush()
        self._polygon_batch.flush()
        self._sprite_batch.flush()

        for tex in self._frame_textures:
            tex.release()
        self._frame_textures.clear()

    @property
    def viewport(self):
        """Current computed letterboxed viewport (physical drawable pixels).

        Contains scale, offsets, and the exact glViewport rect used for the
        game content area.  Most callers should not need this; use GameWindow
        for automatic handling and screen_to_virtual for input mapping.
        Exposed for advanced cases (custom passes, debug overlays, etc.).
        """
        return self._viewport
