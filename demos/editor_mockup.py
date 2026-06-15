"""Mock-up of a Tiled-like map editor demonstrating all Grimoire2D drawing primitives.

Uses GameWindow with a fixed 1280×720 virtual design space. The engine
handles HiDPI, window resize, letterboxing, and centering automatically.
All layout and drawing is expressed in the virtual coordinate space;
callers do not perform manual scaling or letterboxing.

Run with:  python -m demos.editor_mockup
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pygame

from grimoire2d.presentation.window import GameWindow
from grimoire2d.presentation.pixel_buffer import PixelBuffer

if TYPE_CHECKING:
    from grimoire2d.presentation.renderer import Renderer

# ---------------------------------------------------------------------------
# Colour palette (RGBA floats 0..1)
# ---------------------------------------------------------------------------

C_BG = (0.176, 0.176, 0.176, 1.0)
C_PANEL = (0.216, 0.216, 0.216, 1.0)
C_PANEL_HDR = (0.157, 0.157, 0.157, 1.0)
C_BORDER = (0.137, 0.137, 0.137, 1.0)
C_BTN = (0.275, 0.275, 0.275, 1.0)
C_BTN_HOV = (0.353, 0.353, 0.353, 1.0)
C_BTN_ACT = (0.196, 0.196, 0.196, 1.0)
C_ACCENT = (0.235, 0.471, 0.745, 1.0)
C_TEXT = (0.863, 0.863, 0.863, 1.0)
C_TEXT_DIM = (0.549, 0.549, 0.549, 1.0)
C_CANVAS = (0.392, 0.392, 0.392, 1.0)
C_GRID = (0.314, 0.314, 0.314, 1.0)
C_TILE_A = (0.235, 0.235, 0.235, 1.0)
C_TILE_B = (0.255, 0.255, 0.255, 1.0)
C_SEL = (0.235, 0.471, 0.745, 0.35)

_MENU_ITEMS = ["File", "Edit", "View", "Map", "Layer", "Tileset", "Help"]
_TOOL_NAMES = ["Pen", "Erase", "Fill", "Select", "Rect", "Pick", "Stamp", "Line"]


# ---------------------------------------------------------------------------
# Layout: all panel coordinates scaled from the 1280×720 design
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Layout:
    """Pre-computed coordinates in the fixed virtual design space.

    The editor always uses a 1280×720 virtual design. ``s = vh / 720`` is the
    uniform scale factor from the 720p design (s == 1.0 here).  Vertical
    coordinates work as ``s * N`` because panel seams are at fixed base y values.
    The right panel x is derived from vw so it stays correct on any aspect.
    The GameWindow / Renderer handle mapping this design space to the
    physical display with letterboxing.
    """

    vw: float
    vh: float
    s: float

    @classmethod
    def from_virtual(cls, vw: float, vh: float) -> "Layout":
        """Build a Layout scaled to the given virtual resolution."""
        return cls(vw=vw, vh=vh, s=vh / 720.0)

    def px(self, base: float) -> float:
        """Scale a 720p-design value to the current resolution."""
        return base * self.s

    def font(self, base: int) -> int:
        """Scale a design-space font size; minimum 8 px."""
        return max(8, round(base * self.s))

    # --- Horizontal panel boundaries ---

    @property
    def sidebar_w(self) -> float:
        return self.px(180)

    @property
    def right_w(self) -> float:
        return self.px(360)

    @property
    def right_x(self) -> float:
        """Left edge of the right panel — derived from vw so it's aspect-safe."""
        return self.vw - self.right_w

    @property
    def canvas_x(self) -> float:
        return self.sidebar_w

    @property
    def canvas_w(self) -> float:
        return self.right_x - self.canvas_x

    # --- Vertical panel boundaries ---

    @property
    def menu_h(self) -> float:
        return self.px(24)

    @property
    def toolbar_h(self) -> float:
        return self.px(28)

    @property
    def work_y(self) -> float:
        return self.menu_h + self.toolbar_h

    @property
    def status_h(self) -> float:
        return self.px(20)

    @property
    def status_y(self) -> float:
        return self.vh - self.status_h

    @property
    def work_h(self) -> float:
        return self.status_y - self.work_y

    @property
    def layers_h(self) -> float:
        return self.px(348)

    @property
    def tileset_y(self) -> float:
        return self.work_y + self.layers_h

    @property
    def tileset_h(self) -> float:
        return self.status_y - self.tileset_y


# ---------------------------------------------------------------------------
# Tileset palette
# ---------------------------------------------------------------------------


def _tile_color(idx: int) -> tuple[float, float, float, float]:
    """Return a stable pseudo-random colour for a tileset swatch."""
    hue = (idx * 37) % 360
    h = hue / 60.0
    i = int(h)
    f = h - i
    p = 0.55 * (1.0 - 0.55)
    q = 0.55 * (1.0 - 0.55 * f)
    t = 0.55 * (1.0 - 0.55 * (1.0 - f))
    v = 0.55
    segs = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]
    r, g, b = segs[i % 6]
    return (r, g, b, 1.0)


# ---------------------------------------------------------------------------
# Shared draw helpers
# ---------------------------------------------------------------------------


def _panel_header(
    r: Renderer,
    lyt: Layout,
    x: float,
    y: float,
    w: float,
    h: float,
    label: str,
) -> None:
    """Gradient panel header with a vertically centred label."""
    r.draw_rect_gradient(x, y, w, h, C_PANEL_HDR, C_PANEL)
    approx_cap_h = lyt.px(14)
    r.draw_text(
        label,
        x + lyt.px(6),
        y + (h - approx_cap_h) * 0.5,
        color=C_TEXT,
        font_size=lyt.font(16),
    )


def _btn_color(
    bx: float,
    by: float,
    bw: float,
    bh: float,
    mx: float,
    my: float,
    active: bool = False,
) -> tuple[float, float, float, float]:
    """Return the button fill colour given hover / active state."""
    if active:
        return C_BTN_ACT
    if bx <= mx < bx + bw and by <= my < by + bh:
        return C_BTN_HOV
    return C_BTN


# ---------------------------------------------------------------------------
# Section draw functions
# ---------------------------------------------------------------------------


def _draw_menu_bar(renderer: Renderer, lyt: Layout, mx: float, my: float) -> None:
    """Top menu bar with hover highlighting."""
    s = lyt.s
    renderer.draw_rect_gradient(0, 0, lyt.vw, lyt.menu_h, C_PANEL_HDR, C_PANEL)
    renderer.draw_rect(0, lyt.menu_h - s, lyt.vw, s, C_BORDER)

    x = s * 8
    font_sz = lyt.font(18)
    for item in _MENU_ITEMS:
        tw, _ = renderer.measure_text(item, font_size=font_sz)
        item_w = tw + s * 12
        if mx >= x - s * 4 and mx < x + item_w and my < lyt.menu_h:
            renderer.draw_rect_rounded(
                x - s * 4, s * 2, item_w, s * 20, s * 3, C_BTN_HOV
            )
        renderer.draw_text(item, x, s * 4, color=C_TEXT, font_size=font_sz)
        x += item_w + s * 4


def _draw_toolbar(
    renderer: Renderer, lyt: Layout, mx: float, my: float, active_tool: int
) -> None:
    """Icon toolbar below the menu bar."""
    s = lyt.s
    renderer.draw_rect(0, lyt.menu_h, lyt.vw, lyt.toolbar_h, C_PANEL)
    renderer.draw_rect(0, lyt.work_y - s, lyt.vw, s, C_BORDER)

    bx = s * 4
    bw, bh = s * 26, s * 22
    by = lyt.menu_h + s * 3

    for idx, _name in enumerate(_TOOL_NAMES):
        color = _btn_color(bx, by, bw, bh, mx, my, active=idx == active_tool)
        renderer.draw_rect_rounded(bx, by, bw, bh, s * 3, color)
        _draw_tool_icon_small(renderer, lyt, bx + bw * 0.5, by + bh * 0.5, idx)
        bx += s * 30

    renderer.draw_rect(bx + s * 4, lyt.menu_h + s * 4, s, s * 20, C_BORDER)


def _draw_tool_icon_small(
    renderer: Renderer, lyt: Layout, cx: float, cy: float, tool_idx: int
) -> None:
    """Minimal icon inside a small toolbar button."""
    s = lyt.s
    if tool_idx == 0:
        renderer.draw_line(
            cx - s * 4, cy - s * 4, cx + s * 3, cy + s * 3, s * 1.5, C_TEXT
        )
    elif tool_idx == 1:
        renderer.draw_rect(cx - s * 4, cy - s * 3, s * 8, s * 6, C_TEXT_DIM)
    elif tool_idx == 2:
        renderer.draw_circle(cx, cy, s * 4, C_TEXT)
    elif tool_idx == 3:
        renderer.draw_rect_border(cx - s * 4, cy - s * 3, s * 8, s * 6, s, C_TEXT)
    elif tool_idx == 4:
        renderer.draw_rect_rounded_border(
            cx - s * 4, cy - s * 3, s * 8, s * 6, s * 1.5, s, C_ACCENT
        )
    elif tool_idx == 5:
        renderer.draw_circle(cx, cy, s * 3, C_ACCENT)
    elif tool_idx == 6:
        renderer.draw_rect_rounded(
            cx - s * 3, cy - s * 3, s * 7, s * 7, s * 1.5, C_TEXT_DIM
        )
    else:
        renderer.draw_line(cx - s * 4, cy, cx + s * 4, cy, s * 1.5, C_TEXT)


def _draw_tool_icon(
    renderer: Renderer, lyt: Layout, cx: float, cy: float, tool_idx: int
) -> None:
    """Larger icon centred inside a sidebar tool button."""
    s = lyt.s
    if tool_idx == 0:
        renderer.draw_line(
            cx - s * 8, cy - s * 8, cx + s * 6, cy + s * 6, s * 2, C_TEXT
        )
    elif tool_idx == 1:
        renderer.draw_rect(cx - s * 6, cy - s * 5, s * 12, s * 10, C_TEXT_DIM)
    elif tool_idx == 2:
        renderer.draw_circle(cx, cy, s * 7, C_TEXT)
    elif tool_idx == 3:
        renderer.draw_rect_border(
            cx - s * 7, cy - s * 6, s * 14, s * 12, s * 1.5, C_TEXT
        )
    elif tool_idx == 4:
        renderer.draw_rect_rounded_border(
            cx - s * 7, cy - s * 6, s * 14, s * 12, s * 2.5, s * 1.5, C_ACCENT
        )
    elif tool_idx == 5:
        renderer.draw_circle(cx, cy, s * 5, C_ACCENT)
    elif tool_idx == 6:
        renderer.draw_rect_rounded(
            cx - s * 6, cy - s * 5, s * 12, s * 10, s * 2, C_TEXT_DIM
        )
    else:
        renderer.draw_line(cx - s * 8, cy, cx + s * 8, cy, s * 2, C_TEXT)


def _animate_pixel_buffer(buf: PixelBuffer, frame: int) -> None:
    """Fill the pixel buffer with animated colour bands each frame."""
    t = frame * 0.04
    for y in range(buf.height):
        wave = math.sin(t + y * 0.18) * 0.5 + 0.5
        wave2 = math.sin(t * 1.3 + y * 0.09 + 1.0) * 0.5 + 0.5
        r = int(wave * 200 + 30)
        g = int(wave2 * 160 + 30)
        b = int((1.0 - wave) * 180 + 40)
        buf.plot_hline(0, y, buf.width, (r, g, b, 255))


def _draw_left_sidebar(
    renderer: Renderer,
    lyt: Layout,
    mx: float,
    my: float,
    active_tool: int,
    pixel_buffer: PixelBuffer,
    frame: int,
) -> None:
    """Left sidebar: tool grid and pixel buffer preview."""
    s = lyt.s
    renderer.draw_rect(0, lyt.work_y, lyt.sidebar_w, lyt.work_h, C_PANEL)
    renderer.draw_rect(lyt.sidebar_w - s, lyt.work_y, s, lyt.work_h, C_BORDER)

    _panel_header(renderer, lyt, 0, lyt.work_y, lyt.sidebar_w, lyt.px(22), "Tools")

    cols = 2
    bw, bh, gap = lyt.px(38), lyt.px(38), lyt.px(6)
    start_x, start_y = lyt.px(8), lyt.px(78)

    for idx, _name in enumerate(_TOOL_NAMES):
        col = idx % cols
        row = idx // cols
        bx = start_x + col * (bw + gap)
        by = start_y + row * (bh + gap)
        is_active = idx == active_tool
        color = C_ACCENT if is_active else _btn_color(bx, by, bw, bh, mx, my)
        renderer.draw_rect_rounded(bx, by, bw, bh, lyt.px(4), color)
        _draw_tool_icon(renderer, lyt, bx + bw * 0.5, by + bh * 0.5, idx)

    _panel_header(renderer, lyt, 0, lyt.px(578), lyt.sidebar_w, lyt.px(18), "Preview")
    renderer.draw_rect(
        lyt.px(4), lyt.px(596), lyt.px(172), lyt.px(100), (0.0, 0.0, 0.0, 1.0)
    )
    _animate_pixel_buffer(pixel_buffer, frame)
    pixel_buffer.upload()
    renderer.draw_pixel_buffer(
        pixel_buffer, lyt.px(5), lyt.px(597), lyt.px(170), lyt.px(98)
    )


def _draw_canvas(renderer: Renderer, lyt: Layout, mx: float, my: float) -> None:
    """Tiled canvas area with grid lines and a selection rectangle."""
    s = lyt.s
    renderer.draw_rect(lyt.canvas_x, lyt.work_y, lyt.canvas_w, lyt.work_h, C_CANVAS)

    renderer.push_clip(lyt.canvas_x, lyt.work_y, lyt.canvas_w, lyt.work_h)

    grid_ox = lyt.px(280)
    grid_oy = lyt.px(116)
    tile_size = lyt.px(16)
    cols, rows = 24, 20

    for row in range(rows):
        for col in range(cols):
            tx = grid_ox + col * tile_size
            ty = grid_oy + row * tile_size
            fill = C_TILE_A if (col + row) % 2 == 0 else C_TILE_B
            renderer.draw_rect(tx, ty, tile_size, tile_size, fill)

    for col in range(cols + 1):
        renderer.draw_rect(
            grid_ox + col * tile_size, grid_oy, s, rows * tile_size, C_GRID
        )
    for row in range(rows + 1):
        renderer.draw_rect(
            grid_ox, grid_oy + row * tile_size, cols * tile_size, s, C_GRID
        )

    sel_x = grid_ox + lyt.px(32)
    sel_y = grid_oy + lyt.px(32)
    sel_size = lyt.px(48)
    renderer.draw_rect(sel_x, sel_y, sel_size, sel_size, C_SEL)
    renderer.draw_rect_border(sel_x, sel_y, sel_size, sel_size, s * 1.5, C_ACCENT)

    renderer.pop_clip()


def _draw_layers_panel(
    renderer: Renderer,
    lyt: Layout,
    mx: float,
    my: float,
    active_layer: int,
) -> None:
    """Layers panel on the right side."""
    s = lyt.s
    rx = lyt.right_x  # left edge of right panel

    renderer.draw_rect(rx, lyt.work_y, lyt.right_w, lyt.layers_h, C_PANEL)
    _panel_header(renderer, lyt, rx, lyt.work_y, lyt.right_w, lyt.px(22), "Layers")
    renderer.draw_rect(rx, lyt.work_y + lyt.px(21), lyt.right_w, s, C_BORDER)

    # +/- buttons in the header
    plus_x = rx + lyt.right_w - lyt.px(34)
    minus_x = rx + lyt.right_w - lyt.px(16)
    btn_y = lyt.work_y + lyt.px(3)
    btn_sz = lyt.px(14)
    renderer.draw_rect_rounded(plus_x, btn_y, btn_sz, btn_sz, lyt.px(3), C_BTN)
    renderer.draw_text(
        "+", plus_x + lyt.px(4), btn_y + lyt.px(1), color=C_TEXT, font_size=lyt.font(14)
    )
    renderer.draw_rect_rounded(minus_x, btn_y, btn_sz, btn_sz, lyt.px(3), C_BTN)
    renderer.draw_text(
        "-",
        minus_x + lyt.px(4),
        btn_y + lyt.px(1),
        color=C_TEXT,
        font_size=lyt.font(14),
    )

    layer_names = ["Collision", "Objects", "Foreground", "Tiles", "Background"]
    swatch_colors = [
        (0.9, 0.3, 0.3, 1.0),
        (0.3, 0.8, 0.5, 1.0),
        (0.5, 0.5, 0.9, 1.0),
        (0.9, 0.7, 0.3, 1.0),
        (0.5, 0.3, 0.7, 1.0),
    ]
    row_h = lyt.px(28)
    first_row_y = lyt.work_y + lyt.px(24)

    for i, name in enumerate(layer_names):
        ly = first_row_y + i * row_h
        bg = (*C_ACCENT[:3], 0.25) if i == active_layer else C_PANEL
        renderer.draw_rect(rx + s, ly, lyt.right_w - s * 2, row_h, bg)
        renderer.draw_rect(rx + s, ly + row_h - s, lyt.right_w - s * 2, s, C_BORDER)
        renderer.draw_rect_rounded(
            rx + lyt.px(7),
            ly + lyt.px(6),
            lyt.px(16),
            lyt.px(16),
            lyt.px(2),
            swatch_colors[i],
        )
        renderer.draw_circle(
            rx + lyt.right_w - lyt.px(22), ly + row_h * 0.5, lyt.px(5), C_TEXT_DIM
        )
        renderer.draw_text(
            name, rx + lyt.px(30), ly + lyt.px(7), color=C_TEXT, font_size=lyt.font(16)
        )

    renderer.draw_rect(lyt.vw - s, lyt.work_y, s, lyt.layers_h, C_BORDER)


def _draw_tileset_panel(renderer: Renderer, lyt: Layout, mx: float, my: float) -> None:
    """Tileset swatch panel on the right side."""
    s = lyt.s
    rx = lyt.right_x

    renderer.draw_rect(rx, lyt.tileset_y, lyt.right_w, lyt.tileset_h, C_PANEL)
    _panel_header(renderer, lyt, rx, lyt.tileset_y, lyt.right_w, lyt.px(22), "Tileset")
    renderer.draw_rect(rx, lyt.tileset_y + lyt.px(21), lyt.right_w, s, C_BORDER)

    swatch_w = lyt.px(28)
    swatch_h = lyt.px(24)
    gap = lyt.px(4)
    start_x = rx + lyt.px(6)
    start_y = lyt.tileset_y + lyt.px(26)
    selected = {3, 7, 14}

    for idx in range(80):
        col = idx % 10
        row = idx // 10
        sx = start_x + col * (swatch_w + gap)
        sy = start_y + row * (swatch_h + gap)
        renderer.draw_rect_rounded(
            sx, sy, swatch_w, swatch_h, lyt.px(2), _tile_color(idx)
        )
        if idx in selected:
            renderer.draw_rect_rounded_border(
                sx, sy, swatch_w, swatch_h, lyt.px(2), s * 1.5, C_ACCENT
            )

    renderer.draw_rect(lyt.vw - s, lyt.tileset_y, s, lyt.tileset_h, C_BORDER)


def _draw_status_bar(renderer: Renderer, lyt: Layout, mx: float, my: float) -> None:
    """Bottom status bar showing position, tile coordinates, and resolution."""
    s = lyt.s
    renderer.draw_rect(0, lyt.status_y, lyt.vw, s, C_BORDER)
    renderer.draw_rect(0, lyt.status_y + s, lyt.vw, lyt.status_h - s, C_PANEL_HDR)

    grid_ox = lyt.px(280)
    grid_oy = lyt.px(116)
    tile_size = lyt.px(16)
    tile_x = int((mx - grid_ox) / tile_size) if mx >= grid_ox else 0
    tile_y = int((my - grid_oy) / tile_size) if my >= grid_oy else 0

    status = (
        f"Virtual: {int(lyt.vw)}×{int(lyt.vh)}"
        f"  |  Pos: {int(mx)}, {int(my)}"
        f"  |  Tile: {tile_x}, {tile_y}"
        f"  |  Scale: {lyt.s:.2f}×"
        f"  |  Ready"
    )
    renderer.draw_text(
        status,
        lyt.px(8),
        lyt.status_y + lyt.px(4),
        color=C_TEXT_DIM,
        font_size=lyt.font(14),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the editor mockup in a fixed 1280×720 virtual design space.

    GameWindow + the engine take care of creating the GL context,
    HiDPI handling, resizes, letterboxing, and presenting.  The demo
    simply draws and receives input in the stable virtual coordinate space.
    """
    win = GameWindow(
        "Grimoire2D — Editor Mockup (HiDPI)", virtual_width=1280, virtual_height=720
    )
    r = win.renderer
    ctx = r.ctx

    # Fixed design-space layout (engine scales + letterboxes to the display).
    lyt = Layout.from_virtual(1280, 720)

    pixel_buffer = PixelBuffer(ctx, 86, 50)

    active_tool = 0
    active_layer = 3
    frame = 0

    while win.is_open:
        for event in win.poll():
            if event.type == pygame.QUIT:
                win.close()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                win.close()

        # Map logical mouse (window client coords) into the virtual design space.
        mx, my = pygame.mouse.get_pos()
        vx, vy = win.screen_to_virtual(mx, my)

        win.begin_frame()
        r.draw_rect(0, 0, lyt.vw, lyt.vh, C_BG)

        _draw_canvas(r, lyt, vx, vy)
        _draw_left_sidebar(r, lyt, vx, vy, active_tool, pixel_buffer, frame)
        _draw_layers_panel(r, lyt, vx, vy, active_layer)
        _draw_tileset_panel(r, lyt, vx, vy)
        _draw_menu_bar(r, lyt, vx, vy)
        _draw_toolbar(r, lyt, vx, vy, active_tool)
        _draw_status_bar(r, lyt, vx, vy)

        win.end_frame()

        frame += 1

    pixel_buffer.release()
    win.quit()


if __name__ == "__main__":
    main()
