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
from grimoire2d.presentation.shaders import (
    get_default_fragment_shader,
    get_default_vertex_shader,
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
        self.ctx = ctx
        self._virt = initial_virtual or VirtualResolution()
        self._phys: tuple[int, int] = (self._virt.width, self._virt.height)
        self._viewport: Viewport = compute_viewport(self._virt, self._phys[0], self._phys[1])

        # Compile the vendored shaders (strings live in the Python module)
        vert_src = get_default_vertex_shader()
        frag_src = get_default_fragment_shader()
        self.program = self.ctx.program(
            vertex_shader=vert_src,
            fragment_shader=frag_src,
        )

        # Unit quad (two triangles) in 0..1 space. We scale/offset per draw.
        # Using stdlib array (no numpy) so the only added dep is moderngl.
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
        self._quad_vao = self.ctx.simple_vertex_array(self.program, self._quad_vbo, "in_pos")

        # Textured quad for text (and future 2D sprites).
        textured_quad_data = array.array(
            "f",
            [
                0.0, 0.0, 0.0, 0.0,  # pos (0,0 top-left of unit) -> tex (0,0 top of image)
                1.0, 0.0, 1.0, 0.0,
                1.0, 1.0, 1.0, 1.0,
                0.0, 0.0, 0.0, 0.0,
                1.0, 1.0, 1.0, 1.0,
                0.0, 1.0, 0.0, 1.0,
            ],
        )
        self._textured_quad_vbo = self.ctx.buffer(textured_quad_data.tobytes())

        # Compile textured program (for text)
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

        # Reasonable defaults for demo visuals
        self._bar_color = (20, 20, 30, 255)  # dark bars outside letterbox
        self._game_clear = (0, 0, 0, 255)    # will be overridden from VideoSettings

        self._frame_textures: list[moderngl.Texture] = []

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

        # Enable blending so text (which uses alpha from the font texture for
        # glyph shape + antialiasing) composites correctly over the background.
        # Solid rects/border use alpha=1 so they are unaffected.
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
        """Draw a solid rectangle in *virtual* coordinates.

        (x,y) is the top-left corner in the current virtual resolution space.
        This is the proof that everything is resolution-independent.
        """
        self.program["u_offset"].value = (float(x), float(y))
        self.program["u_scale"].value = (float(w), float(h))
        self.program["u_color"].value = color
        self._quad_vao.render()

    def draw_virtual_border(self, thickness: float = 4.0) -> None:
        """Draw a thin border exactly at the virtual resolution edges.

        Extremely useful visual proof for letterboxing and scaling.
        """
        v_w = float(self._virt.width)
        v_h = float(self._virt.height)
        t = float(thickness)
        c = (0.9, 0.9, 0.2, 1.0)  # yellowish border

        # Top
        self.draw_rect(0, 0, v_w, t, c)
        # Bottom
        self.draw_rect(0, v_h - t, v_w, t, c)
        # Left
        self.draw_rect(0, 0, t, v_h, c)
        # Right
        self.draw_rect(v_w - t, 0, t, v_h, c)

    def draw_test_pattern(self) -> None:
        """A few fixed-size colored rects at fixed virtual positions.

        These keep their size and placement relative to the virtual
        resolution no matter how the user resizes the OS window or
        changes the virtual resolution at runtime.
        """
        # Near top-left
        self.draw_rect(40, 40, 180, 120, (0.2, 0.6, 1.0, 1.0))
        # Center-ish
        cx = (self._virt.width - 220) / 2
        cy = (self._virt.height - 160) / 2
        self.draw_rect(cx, cy, 220, 160, (1.0, 0.3, 0.3, 1.0))
        # Near bottom-right
        self.draw_rect(
            self._virt.width - 260, self._virt.height - 140, 200, 100, (0.3, 0.9, 0.4, 1.0)
        )

        # Text primitive demo (proves runtime string, color, alpha, scale + logical coords)
        # Positioned to the right of the top-left blue test rect so it doesn't overlap.
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
            color=(0.7, 0.9, 1.0, 0.9),  # slight transparency
            scale=0.75,
            font_size=18,
        )

    # --- Text primitive support ---

    def _get_font(self, size: int):
        """Lazy cache for pygame fonts (default system font for the primitive).

        Font size is the base render size; the `scale` parameter in draw_text
        then multiplies the resulting quad size in virtual coordinates.
        """
        if not hasattr(self, "_fonts"):
            self._fonts = {}
        if size not in self._fonts:
            # Font(None, size) gives a reasonable platform default.
            # Later we can support explicit font paths (via VFS for games).
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
        - `scale` multiplies the rendered size (in virtual units).
        - `font_size` is the base pygame font size used for rasterization.
        - Color tints the (white) rendered text and applies alpha.

        All drawing happens through the current logical viewport/projection,
        so text automatically respects the same scaling + letterboxing as
        everything else.

        This primitive is intended as a building block for higher-level GUI
        (TK-like) and console systems.
        """
        if not text:
            return

        font = self._get_font(font_size)
        # Render white; shader does the runtime tint (color + alpha)
        surf = font.render(text, True, (255, 255, 255)).convert_alpha()
        tw, th = surf.get_size()
        if tw <= 0 or th <= 0:
            return

        data = pygame.image.tostring(surf, 'RGBA', False)
        texture = self.ctx.texture((tw, th), 4, data)
        texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        texture.use(0)

        # Use the same offset/scale pattern as draw_rect, but on the textured program.
        # The quad size in virtual space = (font pixels * scale)
        self.text_program["u_offset"].value = (float(x), float(y))
        self.text_program["u_scale"].value = (float(tw) * scale, float(th) * scale)
        self.text_program["u_color"].value = color
        self.text_program["u_texture"].value = 0

        self._text_vao.render()

        # Keep the texture alive until the end of the frame.
        # Releasing immediately after render() can cause the GPU to sample
        # a deleted texture on some drivers/configs (result: invisible text).
        self._frame_textures.append(texture)

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
        """Swap / finish the frame.

        With pygame + moderngl the pygame.display.flip() after this
        (or ctx.finish()) is usually sufficient.
        """
        # Release any textures used for text (or sprites) this frame.
        # We kept them alive so the draw commands could actually sample them.
        for tex in self._frame_textures:
            tex.release()
        self._frame_textures.clear()

        # moderngl does not do the swap; the caller (window) does flip.
        pass
