"""Mock-up of a Tiled-like map editor demonstrating all Grimoire2D drawing primitives.

Layout (virtual 1280x720):
  y=0..24    Menu bar
  y=24..52   Toolbar
  y=52..700  Main work area (left sidebar / canvas / right panels)
  y=700..720 Status bar

Run with:  python -m demos.editor_mockup
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pygame
import moderngl

from grimoire2d.presentation.renderer import Renderer
from grimoire2d.presentation.pixel_buffer import PixelBuffer
from grimoire2d.models import VirtualResolution

# ---------------------------------------------------------------------------
# Colour palette (RGBA floats 0..1)
# ---------------------------------------------------------------------------

C_BG        = (0.176, 0.176, 0.176, 1.0)
C_PANEL     = (0.216, 0.216, 0.216, 1.0)
C_PANEL_HDR = (0.157, 0.157, 0.157, 1.0)
C_BORDER    = (0.137, 0.137, 0.137, 1.0)
C_BTN       = (0.275, 0.275, 0.275, 1.0)
C_BTN_HOV   = (0.353, 0.353, 0.353, 1.0)
C_BTN_ACT   = (0.196, 0.196, 0.196, 1.0)
C_ACCENT    = (0.235, 0.471, 0.745, 1.0)
C_TEXT      = (0.863, 0.863, 0.863, 1.0)
C_TEXT_DIM  = (0.549, 0.549, 0.549, 1.0)
C_CANVAS    = (0.392, 0.392, 0.392, 1.0)
C_GRID      = (0.314, 0.314, 0.314, 1.0)
C_TILE_A    = (0.235, 0.235, 0.235, 1.0)
C_TILE_B    = (0.255, 0.255, 0.255, 1.0)
C_SEL       = (0.235, 0.471, 0.745, 0.35)

# ---------------------------------------------------------------------------
# Menu bar constants
# ---------------------------------------------------------------------------

_MENU_ITEMS = ["File", "Edit", "View", "Map", "Layer", "Tileset", "Help"]
_MENU_FONT  = 18

# ---------------------------------------------------------------------------
# Toolbar constants
# ---------------------------------------------------------------------------

_TOOL_NAMES = ["Pen", "Erase", "Fill", "Select", "Rect", "Pick", "Stamp", "Line"]

# ---------------------------------------------------------------------------
# Tileset palette – deterministic colours derived from index
# ---------------------------------------------------------------------------

def _tile_color(idx: int) -> tuple[float, float, float, float]:
    """Return a stable pseudo-random colour for a tileset swatch."""
    hue = (idx * 37) % 360
    # Simple HSV → RGB for saturation=0.55, value=0.55
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
# Draw helpers
# ---------------------------------------------------------------------------

def _panel_header(r: Renderer, x: float, y: float, w: float, h: float, label: str) -> None:
    """Draw a gradient panel header with centred label text."""
    r.draw_rect_gradient(x, y, w, h, C_PANEL_HDR, C_PANEL)
    r.draw_text(label, x + 6, y + (h - 14) * 0.5, color=C_TEXT, font_size=16)


def _btn_color(
    bx: float, by: float, bw: float, bh: float,
    mx: float, my: float,
    active: bool = False,
) -> tuple[float, float, float, float]:
    """Return the appropriate button colour given hover / active state."""
    if active:
        return C_BTN_ACT
    if bx <= mx < bx + bw and by <= my < by + bh:
        return C_BTN_HOV
    return C_BTN


# ---------------------------------------------------------------------------
# Section draw functions
# ---------------------------------------------------------------------------

def _draw_menu_bar(renderer: Renderer, mx: float, my: float, frame: int) -> None:
    """Draw the top menu bar with hover highlighting."""
    renderer.draw_rect_gradient(0, 0, 1280, 24, C_PANEL_HDR, C_PANEL)
    renderer.draw_rect(0, 23, 1280, 1, C_BORDER)

    x = 8
    for item in _MENU_ITEMS:
        tw, _ = renderer.measure_text(item, font_size=_MENU_FONT)
        item_w = tw + 12
        if mx >= x - 4 and mx < x + item_w and my < 24:
            renderer.draw_rect_rounded(x - 4, 2, item_w, 20, 3.0, C_BTN_HOV)
        renderer.draw_text(item, x, 4, color=C_TEXT, font_size=_MENU_FONT)
        x += item_w + 4


def _draw_toolbar(renderer: Renderer, mx: float, my: float, active_tool: int) -> None:
    """Draw the icon toolbar below the menu bar."""
    renderer.draw_rect(0, 24, 1280, 28, C_PANEL)
    renderer.draw_rect(0, 51, 1280, 1, C_BORDER)

    bx = 4
    for idx, name in enumerate(_TOOL_NAMES):
        by = 27
        color = _btn_color(bx, by, 26, 22, mx, my, active=idx == active_tool)
        renderer.draw_rect_rounded(bx, by, 26, 22, 3.0, color)
        _draw_tool_icon_small(renderer, bx + 13, by + 11, idx)
        bx += 30

    renderer.draw_rect(bx + 4, 28, 1, 20, C_BORDER)


def _draw_tool_icon_small(renderer: Renderer, cx: float, cy: float, tool_idx: int) -> None:
    """Draw a minimal icon inside a small toolbar button."""
    if tool_idx == 0:
        renderer.draw_line(cx - 4, cy - 4, cx + 3, cy + 3, 1.5, C_TEXT)
    elif tool_idx == 1:
        renderer.draw_rect(cx - 4, cy - 3, 8, 6, C_TEXT_DIM)
    elif tool_idx == 2:
        renderer.draw_circle(cx, cy, 4.0, C_TEXT)
    elif tool_idx == 3:
        renderer.draw_rect_border(cx - 4, cy - 3, 8, 6, 1.0, C_TEXT)
    elif tool_idx == 4:
        renderer.draw_rect_rounded_border(cx - 4, cy - 3, 8, 6, 1.5, 1.0, C_ACCENT)
    elif tool_idx == 5:
        renderer.draw_circle(cx, cy, 3.0, C_ACCENT)
    elif tool_idx == 6:
        renderer.draw_rect_rounded(cx - 3, cy - 3, 7, 7, 1.5, C_TEXT_DIM)
    else:
        renderer.draw_line(cx - 4, cy, cx + 4, cy, 1.5, C_TEXT)


def _draw_left_sidebar(
    renderer: Renderer,
    mx: float,
    my: float,
    active_tool: int,
    pixel_buffer: PixelBuffer,
    frame: int,
) -> None:
    """Draw the left sidebar: tool selector grid and pixel preview."""
    renderer.draw_rect(0, 52, 180, 648, C_PANEL)
    renderer.draw_rect(179, 52, 1, 648, C_BORDER)

    _panel_header(renderer, 0, 52, 180, 22, "Tools")

    cols, bw, bh, gap = 2, 38, 38, 6
    start_x, start_y = 8, 78

    for idx, name in enumerate(_TOOL_NAMES):
        col = idx % cols
        row = idx // cols
        bx = start_x + col * (bw + gap)
        by = start_y + row * (bh + gap)
        is_active = idx == active_tool
        color = C_ACCENT if is_active else _btn_color(bx, by, bw, bh, mx, my)
        renderer.draw_rect_rounded(bx, by, bw, bh, 4.0, color)
        _draw_tool_icon(renderer, bx + bw // 2, by + bh // 2, idx)

    _panel_header(renderer, 0, 578, 180, 18, "Preview")
    renderer.draw_rect(4, 596, 172, 100, (0.0, 0.0, 0.0, 1.0))
    _animate_pixel_buffer(pixel_buffer, frame)
    pixel_buffer.upload()
    renderer.draw_pixel_buffer(pixel_buffer, 5, 597, 170, 98)


def _draw_tool_icon(renderer: Renderer, cx: float, cy: float, tool_idx: int) -> None:
    """Draw a larger icon centred inside a sidebar tool button."""
    if tool_idx == 0:
        renderer.draw_line(cx - 8, cy - 8, cx + 6, cy + 6, 2.0, C_TEXT)
    elif tool_idx == 1:
        renderer.draw_rect(cx - 6, cy - 5, 12, 10, C_TEXT_DIM)
    elif tool_idx == 2:
        renderer.draw_circle(cx, cy, 7.0, C_TEXT)
    elif tool_idx == 3:
        renderer.draw_rect_border(cx - 7, cy - 6, 14, 12, 1.5, C_TEXT)
    elif tool_idx == 4:
        renderer.draw_rect_rounded_border(cx - 7, cy - 6, 14, 12, 2.5, 1.5, C_ACCENT)
    elif tool_idx == 5:
        renderer.draw_circle(cx, cy, 5.0, C_ACCENT)
    elif tool_idx == 6:
        renderer.draw_rect_rounded(cx - 6, cy - 5, 12, 10, 2.0, C_TEXT_DIM)
    else:
        renderer.draw_line(cx - 8, cy, cx + 8, cy, 2.0, C_TEXT)


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


def _draw_canvas(renderer: Renderer, mx: float, my: float) -> None:
    """Draw the tiled canvas area with grid lines and a fake selection."""
    renderer.draw_rect(180, 52, 740, 648, C_CANVAS)

    grid_ox, grid_oy = 280, 116
    tile_size = 16
    cols, rows = 24, 20

    for row in range(rows):
        for col in range(cols):
            tx = grid_ox + col * tile_size
            ty = grid_oy + row * tile_size
            fill = C_TILE_A if (col + row) % 2 == 0 else C_TILE_B
            renderer.draw_rect(tx, ty, tile_size, tile_size, fill)

    for col in range(cols + 1):
        renderer.draw_rect(grid_ox + col * tile_size, grid_oy, 1, rows * tile_size, C_GRID)
    for row in range(rows + 1):
        renderer.draw_rect(grid_ox, grid_oy + row * tile_size, cols * tile_size, 1, C_GRID)

    sel_x = grid_ox + 32
    sel_y = grid_oy + 32
    renderer.draw_rect(sel_x, sel_y, 48, 48, C_SEL)
    renderer.draw_rect_border(sel_x, sel_y, 48, 48, 1.5, C_ACCENT)


def _draw_layers_panel(renderer: Renderer, mx: float, my: float, active_layer: int) -> None:
    """Draw the layers panel on the right side."""
    renderer.draw_rect(920, 52, 360, 348, C_PANEL)
    _panel_header(renderer, 920, 52, 360, 22, "Layers")
    renderer.draw_rect(920, 73, 360, 1, C_BORDER)

    renderer.draw_rect_rounded(1246, 55, 14, 14, 3.0, C_BTN)
    renderer.draw_text("+", 1250, 57, color=C_TEXT, font_size=14)
    renderer.draw_rect_rounded(1264, 55, 14, 14, 3.0, C_BTN)
    renderer.draw_text("-", 1267, 57, color=C_TEXT, font_size=14)

    layer_names = ["Collision", "Objects", "Foreground", "Tiles", "Background"]
    row_h = 28
    for i, name in enumerate(layer_names):
        ly = 76 + i * row_h
        bg = (*C_ACCENT[:3], 0.25) if i == active_layer else C_PANEL
        renderer.draw_rect(921, ly, 358, row_h, bg)
        renderer.draw_rect(921, ly + row_h - 1, 358, 1, C_BORDER)
        swatch_colors = [
            (0.9, 0.3, 0.3, 1.0),
            (0.3, 0.8, 0.5, 1.0),
            (0.5, 0.5, 0.9, 1.0),
            (0.9, 0.7, 0.3, 1.0),
            (0.5, 0.3, 0.7, 1.0),
        ]
        renderer.draw_rect_rounded(927, ly + 6, 16, 16, 2.0, swatch_colors[i])
        renderer.draw_circle(1258, ly + 14, 5.0, C_TEXT_DIM)
        renderer.draw_text(name, 950, ly + 7, color=C_TEXT, font_size=16)

    renderer.draw_rect(1279, 52, 1, 348, C_BORDER)


def _draw_tileset_panel(renderer: Renderer, mx: float, my: float) -> None:
    """Draw the tileset swatch panel on the right side."""
    renderer.draw_rect(920, 400, 360, 300, C_PANEL)
    _panel_header(renderer, 920, 400, 360, 22, "Tileset")
    renderer.draw_rect(920, 421, 360, 1, C_BORDER)

    swatch_w, swatch_h, gap = 28, 24, 4
    start_x, start_y = 926, 426
    selected = {3, 7, 14}

    for idx in range(80):
        col = idx % 10
        row = idx // 10
        sx = start_x + col * (swatch_w + gap)
        sy = start_y + row * (swatch_h + gap)
        renderer.draw_rect_rounded(sx, sy, swatch_w, swatch_h, 2.0, _tile_color(idx))
        if idx in selected:
            renderer.draw_rect_rounded_border(sx, sy, swatch_w, swatch_h, 2.0, 1.5, C_ACCENT)

    renderer.draw_rect(1279, 400, 1, 300, C_BORDER)


def _draw_status_bar(renderer: Renderer, mx: float, my: float) -> None:
    """Draw the bottom status bar showing position and zoom info."""
    renderer.draw_rect(0, 700, 1280, 1, C_BORDER)
    renderer.draw_rect(0, 701, 1280, 19, C_PANEL_HDR)

    grid_ox, grid_oy, tile_size = 280, 116, 16
    tile_x = int((mx - grid_ox) / tile_size) if mx >= grid_ox else 0
    tile_y = int((my - grid_oy) / tile_size) if my >= grid_oy else 0

    status = (
        f"Virtual: 1280×720  |  "
        f"Pos: {int(mx)}, {int(my)}  |  "
        f"Tile: {tile_x}, {tile_y}  |  "
        f"Zoom: 100%  |  Ready"
    )
    renderer.draw_text(status, 8, 704, color=C_TEXT_DIM, font_size=14)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Initialise pygame + moderngl and run the demo loop."""
    pygame.init()
    pygame.font.init()

    virt = VirtualResolution(width=1280, height=720)
    phys_w, phys_h = 1280, 720

    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_FORWARD_COMPATIBLE_FLAG, True)

    screen = pygame.display.set_mode(
        (phys_w, phys_h),
        pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE,
    )
    pygame.display.set_caption("Grimoire2D — Editor Mockup")

    ctx = moderngl.create_context()
    renderer = Renderer(ctx, virt)
    renderer.handle_physical_resize(phys_w, phys_h)

    pixel_buffer = PixelBuffer(ctx, 86, 50)

    active_tool = 0
    active_layer = 3
    frame = 0
    clock = pygame.time.Clock()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pixel_buffer.release()
                renderer.present()
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                pixel_buffer.release()
                pygame.quit()
                return
            if event.type == pygame.VIDEORESIZE:
                phys_w, phys_h = event.w, event.h
                renderer.handle_physical_resize(phys_w, phys_h)

        mx, my = pygame.mouse.get_pos()
        scale = renderer._viewport.viewport_width / virt.width
        vx = (mx - renderer._viewport.viewport_x) / scale
        vy = (my - renderer._viewport.viewport_y) / scale

        renderer.prepare_frame()

        renderer.draw_rect(0, 0, 1280, 720, C_BG)

        _draw_canvas(renderer, vx, vy)
        _draw_left_sidebar(renderer, vx, vy, active_tool, pixel_buffer, frame)
        _draw_layers_panel(renderer, vx, vy, active_layer)
        _draw_tileset_panel(renderer, vx, vy)
        _draw_menu_bar(renderer, vx, vy, frame)
        _draw_toolbar(renderer, vx, vy, active_tool)
        _draw_status_bar(renderer, vx, vy)

        renderer.present()
        pygame.display.flip()

        frame += 1
        clock.tick(60)


if __name__ == "__main__":
    main()
