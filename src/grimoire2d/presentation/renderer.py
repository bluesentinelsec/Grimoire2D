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
import struct
from dataclasses import replace

import moderngl
import pygame

from grimoire2d.logic.scaling import Viewport, compute_viewport
from grimoire2d.models import VirtualResolution
from grimoire2d.presentation.batch import ShapeBatch, ShapeType, SpriteBatch
from grimoire2d.presentation.pixel_buffer import PixelBuffer
from grimoire2d.presentation.shaders import (
    get_default_fragment_shader,
    get_default_vertex_shader,
    get_pixel_buffer_fragment_shader,
    get_pixel_buffer_vertex_shader,
    get_shape_fragment_shader,
    get_shape_vertex_shader,
    get_sprite_fragment_shader,
    get_sprite_vertex_shader,
    get_textured_fragment_shader,
    get_textured_vertex_shader,
)


def _ortho(left: float, right: float, top: float, bottom: float, near: float = -1.0, far: float = 1.0) -> tuple[float, ...]:
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
        a, 0.0, 0.0, 0.0,
        0.0, b, 0.0, 0.0,
        0.0, 0.0, c, 0.0,
        tx, ty, tz, 1.0,
    )


class Renderer:
    """Encapsulates the OpenGL 3.30 core rendering pipeline.

    The window/presentation bootstrap code creates the pygame display
    with the proper GL attributes and passes the resulting moderngl
    context here. All subsequent GL work (programs, draws, viewport,
    clears for letterboxing) happens through this object.
    """

    def __init__(self, ctx: moderngl.Context, initial_virtual: VirtualResolution | None = None) -> None:
        """Initialise the renderer with a live moderngl context.

        Args:
            ctx: The moderngl context created by the window bootstrap.
            initial_virtual: Starting virtual resolution; defaults to 1280x720.
        """
        self.ctx = ctx
        self._virt = initial_virtual or VirtualResolution()
        self._phys: tuple[int, int] = (self._virt.width, self._virt.height)
        self._viewport: Viewport = compute_viewport(self._virt, self._phys[0], self._phys[1])

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
                0.0, 0.0,
                1.0, 0.0,
                1.0, 1.0,
                0.0, 0.0,
                1.0, 1.0,
                0.0, 1.0,
            ],
        )
        self._quad_vbo = self.ctx.buffer(quad_data.tobytes())
        self._quad_vao = self.ctx.simple_vertex_array(self.program, self._quad_vbo, "in_pos")

        # Textured quad for text (and future 2D sprites).
        textured_quad_data = array.array(
            "f",
            [
                0.0, 0.0, 0.0, 0.0,
                1.0, 0.0, 1.0, 0.0,
                1.0, 1.0, 1.0, 1.0,
                0.0, 0.0, 0.0, 0.0,
                1.0, 1.0, 1.0, 1.0,
                0.0, 1.0, 0.0, 1.0,
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

        # Pixel buffer program + static unit-quad
        self._pixel_buffer_program = self.ctx.program(
            vertex_shader=get_pixel_buffer_vertex_shader(),
            fragment_shader=get_pixel_buffer_fragment_shader(),
        )
        self._pixel_buffer_program["u_projection"].value = self._projection

        _pb_quad = array.array("f", [
            0.0, 0.0, 0.0, 0.0,
            1.0, 0.0, 1.0, 0.0,
            1.0, 1.0, 1.0, 1.0,
            0.0, 0.0, 0.0, 0.0,
            1.0, 1.0, 1.0, 1.0,
            0.0, 1.0, 0.0, 1.0,
        ])
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
            x, y, w, h, color,
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
            x, y, w, h, color_top,
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
            x, y, w, h, color,
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
            x, y, w, h, color,
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
            cx - r, cy - r, r * 2.0, r * 2.0, color,
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
            cx - outer_r, cy - outer_r, outer_r * 2.0, outer_r * 2.0, color,
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
        self._sprite_batch.flush()
        self._clip_stack.append((x, y, w, h))
        self._apply_scissor(x, y, w, h)

    def pop_clip(self) -> None:
        """Restore the previous scissor rectangle (or disable scissor).

        Flushes both batches before changing GL scissor state.
        """
        self._shape_batch.flush()
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
            self._virt.width - 260, self._virt.height - 140, 200, 100, (0.3, 0.9, 0.4, 1.0)
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

        This primitive is intended as a building block for higher-level GUI
        (TK-like) and console systems.
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

    def measure_text(self, text: str, *, font_size: int = 32, scale: float = 1.0) -> tuple[float, float]:
        """Return the (width, height) in virtual units the text would occupy.

        Useful for layout helpers when building GUI or console systems on top
        of this primitive.
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

    def present(self) -> None:
        """Flush pending batches and swap / finish the frame.

        With pygame + moderngl the pygame.display.flip() after this
        (or ctx.finish()) is usually sufficient.
        """
        self._shape_batch.flush()
        self._sprite_batch.flush()

        for tex in self._frame_textures:
            tex.release()
        self._frame_textures.clear()
