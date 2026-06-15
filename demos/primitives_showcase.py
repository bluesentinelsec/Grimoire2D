"""Showcase of all Grimoire2D drawing primitives across 7 animated scenes.

Cycles through scenes automatically every 5 seconds (300 frames at 60 fps).
Press LEFT/RIGHT to navigate manually.  Press ESC or close the window to quit.

Run with:  python -m demos.primitives_showcase
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# HiDPI hint must be applied BEFORE pygame.init().
from grimoire2d.presentation.highdpi import enable_highdpi, get_drawable_size
enable_highdpi()

import pygame
import moderngl

from grimoire2d.presentation.renderer import Renderer
from grimoire2d.models import VirtualResolution

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCENE_COUNT = 7
SCENE_DURATION = 300          # frames before auto-advance
SCENE_NAMES = [
    "1 — Filled Shapes",
    "2 — Arcs, Pies & Borders",
    "3 — Triangles & Polygons",
    "4 — Gradients",
    "5 — Lines & Curves",
    "6 — Shadows & Glows",
    "7 — Sprites & Nine-Slice",
]

# Palette
C_BG      = (0.08, 0.08, 0.10, 1.0)
C_WHITE   = (1.0,  1.0,  1.0,  1.0)
C_YELLOW  = (1.0,  0.95, 0.2,  1.0)
C_DIM     = (0.55, 0.55, 0.55, 1.0)


# ---------------------------------------------------------------------------
# Procedural texture helpers
# ---------------------------------------------------------------------------

def _make_sprite_texture(ctx: moderngl.Context) -> moderngl.Texture:
    """Create a 128x128 four-quadrant colour sprite texture."""
    size = 128
    half = size // 2
    data = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            idx = (y * size + x) * 4
            if x < half and y < half:
                data[idx:idx + 4] = (220, 50,  50,  255)   # red TL
            elif x >= half and y < half:
                data[idx:idx + 4] = (50,  200, 80,  255)   # green TR
            elif x < half and y >= half:
                data[idx:idx + 4] = (50,  100, 220, 255)   # blue BL
            else:
                data[idx:idx + 4] = (220, 200, 50,  255)   # yellow BR
    tex = ctx.texture((size, size), 4, bytes(data))
    tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    return tex


def _make_nineslice_texture(ctx: moderngl.Context) -> moderngl.Texture:
    """Create a 64x64 nine-slice UI panel texture (border + fill)."""
    size = 64
    border = 8
    data = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            idx = (y * size + x) * 4
            on_border = (x < border or x >= size - border or
                         y < border or y >= size - border)
            if on_border:
                data[idx:idx + 4] = (200, 200, 210, 255)   # light border
            else:
                data[idx:idx + 4] = (40,  40,  50,  255)   # dark interior
    tex = ctx.texture((size, size), 4, bytes(data))
    tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    return tex


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def _label(r: Renderer, text: str, x: float, y: float, s: float) -> None:
    """Draw a small label."""
    r.draw_text(text, x, y, color=C_DIM, font_size=max(12, int(18 * s)))


def _heading(r: Renderer, text: str, x: float, y: float, s: float) -> None:
    """Draw a medium section heading."""
    r.draw_text(text, x, y, color=C_WHITE, font_size=max(14, int(22 * s)))


# ---------------------------------------------------------------------------
# Scene 1 — Filled Shapes
# ---------------------------------------------------------------------------

def _scene_filled_shapes(r: Renderer, frame: int, s: float, lw: float, lh: float) -> None:
    """A 2×3 grid of filled primitive types with labels."""
    cols = [lw * 0.17, lw * 0.50, lw * 0.83]
    rows = [lh * 0.30, lh * 0.68]
    cell_w = lw * 0.22
    cell_h = lh * 0.22

    # Row 0
    cx, cy = cols[0], rows[0]
    r.draw_rect(cx - cell_w * 0.5, cy - cell_h * 0.5, cell_w, cell_h, (0.2, 0.5, 1.0, 1.0))
    _label(r, "draw_rect", cx - cell_w * 0.5, cy + cell_h * 0.5 + 4 * s, s)

    cx, cy = cols[1], rows[0]
    r.draw_rect_rounded(cx - cell_w * 0.5, cy - cell_h * 0.5, cell_w, cell_h, 20 * s, (0.65, 0.2, 0.85, 1.0))
    _label(r, "draw_rect_rounded", cx - cell_w * 0.5, cy + cell_h * 0.5 + 4 * s, s)

    cx, cy = cols[2], rows[0]
    r.draw_circle(cx, cy, min(cell_w, cell_h) * 0.48, (1.0, 0.55, 0.1, 1.0))
    _label(r, "draw_circle", cx - cell_w * 0.5, cy + cell_h * 0.5 + 4 * s, s)

    # Row 1
    cx, cy = cols[0], rows[1]
    r.draw_ellipse(cx, cy, cell_w * 0.48, cell_h * 0.30, (0.2, 0.85, 0.4, 1.0))
    _label(r, "draw_ellipse", cx - cell_w * 0.5, cy + cell_h * 0.35 + 4 * s, s)

    cx, cy = cols[1], rows[1]
    r.draw_capsule(cx - cell_w * 0.48, cy - cell_h * 0.22, cell_w * 0.96, cell_h * 0.44, (0.1, 0.75, 0.75, 1.0))
    _label(r, "draw_capsule", cx - cell_w * 0.5, cy + cell_h * 0.25 + 4 * s, s)

    cx, cy = cols[2], rows[1]
    outer = min(cell_w, cell_h) * 0.48
    r.draw_ring(cx, cy, outer, outer * 0.55, (1.0, 0.9, 0.1, 1.0))
    _label(r, "draw_ring", cx - cell_w * 0.5, cy + cell_h * 0.5 + 4 * s, s)


# ---------------------------------------------------------------------------
# Scene 2 — Arcs, Pies & Borders
# ---------------------------------------------------------------------------

def _scene_arcs_pies(r: Renderer, frame: int, s: float, lw: float, lh: float) -> None:
    """Animated arc progress ring, pie chart slices, and border examples."""
    progress = frame / SCENE_DURATION

    # --- Arc progress ring ---
    cx1, cy1 = lw * 0.20, lh * 0.42
    rad = 90 * s
    # Background ring
    r.draw_ring(cx1, cy1, rad, rad * 0.70, (0.25, 0.25, 0.30, 1.0))
    # Progress arc (clockwise from top = -π/2)
    a_start = -math.pi * 0.5
    a_end = a_start + progress * 2.0 * math.pi
    if progress > 0.001:
        r.draw_arc(cx1, cy1, rad * 0.85, a_start, a_end, rad * 0.28, (0.2, 0.7, 1.0, 1.0))
    _label(r, f"draw_arc  ({int(progress*100)}%)", cx1 - rad, cy1 + rad + 8 * s, s)

    # --- Pie chart ---
    cx2, cy2 = lw * 0.52, lh * 0.42
    pie_r = 85 * s
    slices = [
        (0.0,             0.35 * 2 * math.pi, (0.9, 0.3, 0.3, 1.0)),
        (0.35 * 2 * math.pi, 0.60 * 2 * math.pi, (0.3, 0.8, 0.4, 1.0)),
        (0.60 * 2 * math.pi, 1.00 * 2 * math.pi, (0.3, 0.5, 0.9, 1.0)),
    ]
    for a0, a1, col in slices:
        r.draw_pie(cx2, cy2, pie_r, a0, a1, col)
    _label(r, "draw_pie", cx2 - pie_r, cy2 + pie_r + 8 * s, s)

    # --- Rect border / rounded border ---
    bx, by = lw * 0.78, lh * 0.30
    bw, bh = 160 * s, 80 * s
    r.draw_rect_border(bx - bw * 0.5, by - bh * 0.5, bw, bh, 3 * s, (0.8, 0.8, 0.8, 1.0))
    _label(r, "draw_rect_border", bx - bw * 0.5, by + bh * 0.5 + 4 * s, s)

    by2 = lh * 0.62
    r.draw_rect_rounded_border(bx - bw * 0.5, by2 - bh * 0.5, bw, bh, 16 * s, 3 * s, (0.65, 0.85, 1.0, 1.0))
    _label(r, "draw_rect_rounded_border", bx - bw * 0.5, by2 + bh * 0.5 + 4 * s, s)


# ---------------------------------------------------------------------------
# Scene 3 — Triangles & Polygons
# ---------------------------------------------------------------------------

def _make_regular_polygon(cx: float, cy: float, r: float, n: int, offset: float = 0.0) -> list[tuple[float, float]]:
    """Return vertices of a regular n-gon centred at (cx, cy)."""
    return [
        (cx + math.cos(2 * math.pi * i / n + offset) * r,
         cy + math.sin(2 * math.pi * i / n + offset) * r)
        for i in range(n)
    ]


def _make_star(cx: float, cy: float, r_outer: float, r_inner: float, points: int) -> list[tuple[float, float]]:
    """Return vertices for a star polygon alternating outer/inner radius."""
    verts = []
    for i in range(points * 2):
        angle = math.pi * i / points - math.pi * 0.5
        r = r_outer if i % 2 == 0 else r_inner
        verts.append((cx + math.cos(angle) * r, cy + math.sin(angle) * r))
    return verts


def _scene_triangles_polygons(r: Renderer, frame: int, s: float, lw: float, lh: float) -> None:
    """Triangles, hexagon, pentagon, octagon and a 10-point star."""
    row1_y = lh * 0.35
    row2_y = lh * 0.68

    # Triangle
    tx, ty = lw * 0.12, row1_y
    ts = 75 * s
    r.draw_triangle(tx, ty - ts, tx + ts, ty + ts * 0.6, tx - ts, ty + ts * 0.6,
                    (0.9, 0.4, 0.2, 1.0))
    _label(r, "draw_triangle", tx - ts, ty + ts * 0.7 + 4 * s, s)

    # Hexagon
    hx, hy = lw * 0.32, row1_y
    hex_pts = _make_regular_polygon(hx, hy, 70 * s, 6, math.pi / 6)
    r.draw_polygon(hex_pts, (0.4, 0.7, 0.3, 1.0))
    _label(r, "hexagon (6)", hx - 50 * s, hy + 75 * s, s)

    # Pentagon
    px, py = lw * 0.55, row1_y
    pent_pts = _make_regular_polygon(px, py, 68 * s, 5, -math.pi * 0.5)
    r.draw_polygon(pent_pts, (0.3, 0.55, 0.9, 1.0))
    _label(r, "pentagon (5)", px - 50 * s, py + 72 * s, s)

    # Octagon
    ox, oy = lw * 0.77, row1_y
    oct_pts = _make_regular_polygon(ox, oy, 68 * s, 8, math.pi / 8)
    r.draw_polygon(oct_pts, (0.75, 0.3, 0.7, 1.0))
    _label(r, "octagon (8)", ox - 50 * s, oy + 72 * s, s)

    # 10-point star (row 2, centred)
    sx, sy = lw * 0.50, row2_y
    star_r = 80 * s
    star_pts = _make_star(sx, sy, star_r, star_r * 0.4, 10)
    r.draw_polygon(star_pts, (1.0, 0.85, 0.1, 1.0))
    _label(r, "10-point star", sx - 55 * s, sy + star_r + 4 * s, s)


# ---------------------------------------------------------------------------
# Scene 4 — Gradients
# ---------------------------------------------------------------------------

def _scene_gradients(r: Renderer, frame: int, s: float, lw: float, lh: float) -> None:
    """Four gradient methods arranged in a 2×2 grid."""
    gw, gh = 220 * s, 110 * s
    col = [lw * 0.27, lw * 0.73]
    row = [lh * 0.32, lh * 0.66]

    # Vertical gradient (existing)
    x, y = col[0] - gw * 0.5, row[0] - gh * 0.5
    r.draw_rect_gradient(x, y, gw, gh, (0.2, 0.4, 0.9, 1.0), (0.8, 0.2, 0.5, 1.0))
    _label(r, "draw_rect_gradient (vertical)", x, y + gh + 4 * s, s)

    # Horizontal gradient
    x, y = col[1] - gw * 0.5, row[0] - gh * 0.5
    r.draw_rect_gradient_h(x, y, gw, gh, (0.1, 0.8, 0.4, 1.0), (0.9, 0.7, 0.1, 1.0))
    _label(r, "draw_rect_gradient_h (horizontal)", x, y + gh + 4 * s, s)

    # Four-corner gradient
    x, y = col[0] - gw * 0.5, row[1] - gh * 0.5
    r.draw_rect_gradient_corner(x, y, gw, gh,
                                (1.0, 0.2, 0.2, 1.0),
                                (0.2, 1.0, 0.2, 1.0),
                                (0.2, 0.2, 1.0, 1.0),
                                (1.0, 1.0, 0.2, 1.0))
    _label(r, "draw_rect_gradient_corner", x, y + gh + 4 * s, s)

    # Radial circle gradient
    cx2, cy2 = col[1], row[1]
    r.draw_circle_gradient(cx2, cy2, gh * 0.52, (1.0, 1.0, 1.0, 1.0), (0.2, 0.1, 0.5, 1.0))
    _label(r, "draw_circle_gradient (radial)", cx2 - gw * 0.5, cy2 + gh * 0.52 + 4 * s, s)


# ---------------------------------------------------------------------------
# Scene 5 — Lines & Curves
# ---------------------------------------------------------------------------

def _scene_lines(r: Renderer, frame: int, s: float, lw: float, lh: float) -> None:
    """Solid line, dashed line, polyline, quadratic and cubic Bezier curves."""
    margin_x = lw * 0.22
    right_x = lw * 0.92
    y_positions = [lh * 0.20, lh * 0.35, lh * 0.50, lh * 0.65, lh * 0.80]
    label_x = lw * 0.04

    # Solid line
    y = y_positions[0]
    r.draw_line(margin_x, y, right_x, y, 3 * s, (0.9, 0.9, 0.9, 1.0))
    _label(r, "draw_line", label_x, y - 10 * s, s)

    # Dashed line
    y = y_positions[1]
    r.draw_dashed_line(margin_x, y, right_x, y, 3 * s, (0.6, 0.9, 0.4, 1.0), dash=12 * s, gap=6 * s)
    _label(r, "draw_dashed_line", label_x, y - 10 * s, s)

    # Polyline (zigzag)
    y = y_positions[2]
    span = right_x - margin_x
    zpts = [(margin_x + span * i / 7, y + (30 * s if i % 2 == 0 else -30 * s)) for i in range(8)]
    r.draw_polyline(zpts, 3 * s, (1.0, 0.6, 0.2, 1.0))
    _label(r, "draw_polyline", label_x, y - 10 * s, s)

    # Quadratic Bezier
    y = y_positions[3]
    r.draw_bezier_quadratic(margin_x, y + 30 * s, lw * 0.57, y - 60 * s, right_x, y + 30 * s,
                            3 * s, (0.4, 0.7, 1.0, 1.0))
    _label(r, "draw_bezier_quadratic", label_x, y - 10 * s, s)

    # Cubic Bezier
    y = y_positions[4]
    r.draw_bezier_cubic(margin_x, y, lw * 0.38, y - 70 * s, lw * 0.62, y + 70 * s, right_x, y,
                        3 * s, (0.9, 0.3, 0.7, 1.0))
    _label(r, "draw_bezier_cubic", label_x, y - 10 * s, s)


# ---------------------------------------------------------------------------
# Scene 6 — Shadows & Glows
# ---------------------------------------------------------------------------

def _scene_shadows(r: Renderer, frame: int, s: float, lw: float, lh: float) -> None:
    """Shapes preceded by drop shadows / glow effects."""
    # --- Rounded rect with drop shadow ---
    rx, ry = lw * 0.20, lh * 0.38
    rw, rh = 200 * s, 100 * s
    r.draw_drop_shadow(rx - rw * 0.5, ry - rh * 0.5, rw, rh, ox=6 * s, oy=8 * s, blur=18 * s,
                       radius=16 * s, color=(0.0, 0.0, 0.0, 0.6))
    r.draw_rect_rounded(rx - rw * 0.5, ry - rh * 0.5, rw, rh, 16 * s, (0.3, 0.55, 0.9, 1.0))
    _label(r, "Rounded rect + drop shadow", rx - rw * 0.5, ry + rh * 0.5 + 6 * s, s)

    # --- Circle with glow (ox/oy=0, large blur) ---
    gx, gy = lw * 0.55, lh * 0.40
    gr = 65 * s
    r.draw_drop_shadow(gx - gr, gy - gr, gr * 2, gr * 2,
                       ox=0, oy=0, blur=30 * s, radius=gr,
                       color=(0.2, 0.7, 1.0, 0.7))
    r.draw_circle(gx, gy, gr, (0.2, 0.65, 1.0, 1.0))
    _label(r, "Circle + glow (ox=oy=0, large blur)", gx - gr, gy + gr + 6 * s, s)

    # --- Capsule with shadow ---
    kx, ky = lw * 0.80, lh * 0.40
    kw, kh = 160 * s, 60 * s
    r.draw_drop_shadow(kx - kw * 0.5, ky - kh * 0.5, kw, kh, ox=4 * s, oy=6 * s,
                       blur=14 * s, color=(0.0, 0.0, 0.0, 0.55))
    r.draw_capsule(kx - kw * 0.5, ky - kh * 0.5, kw, kh, (0.8, 0.5, 0.2, 1.0))
    _label(r, "Capsule + drop shadow", kx - kw * 0.5, ky + kh * 0.5 + 6 * s, s)

    # Info text
    r.draw_text("draw_drop_shadow drawn before the shape, then shape on top",
                lw * 0.05, lh * 0.80, color=C_DIM, font_size=max(14, int(20 * s)))


# ---------------------------------------------------------------------------
# Scene 7 — Sprites & Nine-Slice
# ---------------------------------------------------------------------------

def _scene_sprites(
    r: Renderer,
    frame: int,
    s: float,
    lw: float,
    lh: float,
    sprite_tex,
    nineslice_tex,
) -> None:
    """Sprite and nine-slice rendering examples."""
    # Full-size sprite
    sp = 128 * s
    sx1, sy1 = lw * 0.12 - sp * 0.5, lh * 0.35 - sp * 0.5
    r.draw_sprite(sprite_tex, sx1, sy1, sp, sp)
    _label(r, "draw_sprite (full size)", sx1, sy1 + sp + 4 * s, s)

    # Scaled + tinted sprite
    sp2 = 80 * s
    sx2, sy2 = lw * 0.38 - sp2 * 0.5, lh * 0.38 - sp2 * 0.5
    r.draw_sprite(sprite_tex, sx2, sy2, sp2, sp2, tint=(1.0, 0.6, 0.6, 0.85))
    _label(r, "draw_sprite (scaled + tinted)", sx2, sy2 + sp2 + 4 * s, s)

    # Nine-slice small
    ns_brd = 8
    ns_w1, ns_h1 = 160 * s, 90 * s
    nsx1, nsy1 = lw * 0.63 - ns_w1 * 0.5, lh * 0.35 - ns_h1 * 0.5
    r.draw_nine_slice(nineslice_tex, nsx1, nsy1, ns_w1, ns_h1, ns_brd * s)
    _label(r, "draw_nine_slice (small)", nsx1, nsy1 + ns_h1 + 4 * s, s)

    # Nine-slice wide (shows center stretching)
    ns_w2, ns_h2 = 340 * s, 90 * s
    nsx2, nsy2 = lw * 0.85 - ns_w2 * 0.5, lh * 0.35 - ns_h2 * 0.5
    r.draw_nine_slice(nineslice_tex, nsx2, nsy2, ns_w2, ns_h2, ns_brd * s)
    _label(r, "draw_nine_slice (wide — centre stretches, corners stay fixed)",
           nsx2, nsy2 + ns_h2 + 4 * s, s)

    # Explanatory note
    r.draw_text(
        "Nine-slice: border texels stay pixel-perfect; centre stretches to fill target size.",
        lw * 0.05, lh * 0.78, color=C_DIM, font_size=max(14, int(20 * s)),
    )


# ---------------------------------------------------------------------------
# Master scene dispatch
# ---------------------------------------------------------------------------

def _draw_scene(
    r: Renderer,
    scene: int,
    frame: int,
    s: float,
    lw: float,
    lh: float,
    sprite_tex,
    nineslice_tex,
) -> None:
    """Dispatch to the appropriate scene drawing function."""
    if scene == 0:
        _scene_filled_shapes(r, frame, s, lw, lh)
    elif scene == 1:
        _scene_arcs_pies(r, frame, s, lw, lh)
    elif scene == 2:
        _scene_triangles_polygons(r, frame, s, lw, lh)
    elif scene == 3:
        _scene_gradients(r, frame, s, lw, lh)
    elif scene == 4:
        _scene_lines(r, frame, s, lw, lh)
    elif scene == 5:
        _scene_shadows(r, frame, s, lw, lh)
    elif scene == 6:
        _scene_sprites(r, frame, s, lw, lh, sprite_tex, nineslice_tex)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point: open window, run scene loop."""
    pygame.init()
    pygame.font.init()

    flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE
    pygame.display.set_mode((1280, 720), flags)
    draw_w, draw_h = get_drawable_size()
    pygame.display.set_mode((draw_w, draw_h), flags)
    pygame.display.set_caption("Grimoire2D — Primitives Showcase")

    ctx = moderngl.create_context()
    renderer = Renderer(ctx, VirtualResolution(width=draw_w, height=draw_h, integer_scaling=False))
    renderer.handle_physical_resize(draw_w, draw_h)

    sprite_tex = _make_sprite_texture(ctx)
    nineslice_tex = _make_nineslice_texture(ctx)

    # Layout scale factor relative to a 1280×720 design canvas
    s = draw_h / 720.0
    lw = float(draw_w)
    lh = float(draw_h)

    current_scene = 0
    scene_frame = 0
    clock = pygame.time.Clock()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_RIGHT:
                    current_scene = (current_scene + 1) % SCENE_COUNT
                    scene_frame = 0
                elif event.key == pygame.K_LEFT:
                    current_scene = (current_scene - 1) % SCENE_COUNT
                    scene_frame = 0
            elif event.type == pygame.VIDEORESIZE:
                draw_w2, draw_h2 = get_drawable_size()
                renderer.handle_physical_resize(draw_w2, draw_h2)

        renderer.prepare_frame()

        # Dark background
        renderer.draw_rect(0, 0, lw, lh, C_BG)

        # Scene content
        _draw_scene(renderer, current_scene, scene_frame, s, lw, lh, sprite_tex, nineslice_tex)

        # HUD — scene name
        renderer.draw_text(
            SCENE_NAMES[current_scene],
            12 * s, 8 * s,
            color=C_WHITE,
            font_size=max(18, int(30 * s)),
        )

        # HUD — FPS (top-right)
        fps_str = f"FPS: {clock.get_fps():.0f}"
        fps_w, _ = renderer.measure_text(fps_str, font_size=max(14, int(22 * s)))
        renderer.draw_text(fps_str, lw - fps_w - 12 * s, 8 * s,
                           color=C_YELLOW, font_size=max(14, int(22 * s)))

        # HUD — navigation hint (bottom centre)
        hint = f"Scene {current_scene + 1}/{SCENE_COUNT}   ←→ to navigate   ESC to quit"
        hint_w, _ = renderer.measure_text(hint, font_size=max(12, int(18 * s)))
        renderer.draw_text(hint, (lw - hint_w) * 0.5, lh - 28 * s,
                           color=C_DIM, font_size=max(12, int(18 * s)))

        renderer.present()
        pygame.display.flip()

        scene_frame += 1
        if scene_frame >= SCENE_DURATION:
            scene_frame = 0
            current_scene = (current_scene + 1) % SCENE_COUNT

        clock.tick(60)

    sprite_tex.release()
    nineslice_tex.release()
    pygame.quit()


if __name__ == "__main__":
    main()
