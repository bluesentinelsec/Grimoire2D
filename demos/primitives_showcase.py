"""Showcase of all Grimoire2D drawing primitives across 7 animated scenes.

Press SPACE to toggle auto-advance (default: off).
Press LEFT/RIGHT to navigate manually.
Press ESC or close the window to quit.

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
SCENE_DURATION = 300          # frames before auto-advance (when auto is on)
FADE_FRAMES = 24              # frames for fade-in / fade-out

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
C_GREEN   = (0.3,  0.9,  0.4,  1.0)


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
                data[idx:idx + 4] = (200, 200, 210, 255)
            else:
                data[idx:idx + 4] = (40,  40,  50,  255)
    tex = ctx.texture((size, size), 4, bytes(data))
    tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    return tex


# ---------------------------------------------------------------------------
# Animation helpers
# ---------------------------------------------------------------------------

def _rotate_points(
    points: list[tuple[float, float]],
    cx: float,
    cy: float,
    angle: float,
) -> list[tuple[float, float]]:
    """Rotate a list of (x, y) points around (cx, cy) by angle radians."""
    c, s = math.cos(angle), math.sin(angle)
    result = []
    for px, py in points:
        dx, dy = px - cx, py - cy
        result.append((cx + dx * c - dy * s, cy + dx * s + dy * c))
    return result


def _pulse(frame: int, period: float = 90.0, lo: float = 0.85, hi: float = 1.15) -> float:
    """Sinusoidal scale pulse between lo and hi over `period` frames."""
    t = (math.sin(frame * 2 * math.pi / period) + 1.0) * 0.5
    return lo + t * (hi - lo)


def _wave(frame: int, amplitude: float, period: float = 120.0) -> float:
    """Sinusoidal oscillation centred at zero."""
    return math.sin(frame * 2 * math.pi / period) * amplitude


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def _label(r: Renderer, text: str, x: float, y: float, s: float) -> None:
    r.draw_text(text, x, y, color=C_DIM, font_size=max(12, int(18 * s)))


def _heading(r: Renderer, text: str, x: float, y: float, s: float) -> None:
    r.draw_text(text, x, y, color=C_WHITE, font_size=max(14, int(22 * s)))


# ---------------------------------------------------------------------------
# Scene 1 — Filled Shapes  (pulse + translate)
# ---------------------------------------------------------------------------

def _scene_filled_shapes(r: Renderer, frame: int, s: float, lw: float, lh: float) -> None:
    cols = [lw * 0.17, lw * 0.50, lw * 0.83]
    rows = [lh * 0.30, lh * 0.68]
    cell_w = lw * 0.22
    cell_h = lh * 0.22

    # Rect pulses in size
    cx, cy = cols[0], rows[0] + _wave(frame, 12 * s, 100)
    pw = cell_w * _pulse(frame, 80)
    ph = cell_h * _pulse(frame, 80)
    r.draw_rect(cx - pw * 0.5, cy - ph * 0.5, pw, ph, (0.2, 0.5, 1.0, 1.0))
    _label(r, "draw_rect", cx - cell_w * 0.5, rows[0] + cell_h * 0.5 + 18 * s, s)

    # Rounded rect orbits slightly
    cx, cy = cols[1] + _wave(frame, 10 * s, 90), rows[0]
    r.draw_rect_rounded(cx - cell_w * 0.5, cy - cell_h * 0.5, cell_w, cell_h,
                        20 * s, (0.65, 0.2, 0.85, 1.0))
    _label(r, "draw_rect_rounded", cols[1] - cell_w * 0.5, rows[0] + cell_h * 0.5 + 4 * s, s)

    # Circle pulses radius
    cx, cy = cols[2], rows[0]
    cr = min(cell_w, cell_h) * 0.48 * _pulse(frame, 70)
    r.draw_circle(cx, cy, cr, (1.0, 0.55, 0.1, 1.0))
    _label(r, "draw_circle", cx - cell_w * 0.5, rows[0] + cell_h * 0.5 + 4 * s, s)

    # Ellipse rx/ry oscillate
    cx, cy = cols[0], rows[1]
    rx = cell_w * 0.48 * _pulse(frame, 110, 0.6, 1.0)
    ry = cell_h * 0.30 * _pulse(frame, 110, 0.7, 1.3)
    r.draw_ellipse(cx, cy, rx, ry, (0.2, 0.85, 0.4, 1.0))
    _label(r, "draw_ellipse", cx - cell_w * 0.5, rows[1] + cell_h * 0.35 + 4 * s, s)

    # Capsule translates left/right
    cx, cy = cols[1] + _wave(frame, 18 * s, 130), rows[1]
    r.draw_capsule(cx - cell_w * 0.48, cy - cell_h * 0.22, cell_w * 0.96, cell_h * 0.44,
                   (0.1, 0.75, 0.75, 1.0))
    _label(r, "draw_capsule", cols[1] - cell_w * 0.5, rows[1] + cell_h * 0.25 + 4 * s, s)

    # Ring inner_r oscillates
    cx, cy = cols[2], rows[1]
    outer = min(cell_w, cell_h) * 0.48
    inner = outer * (0.35 + 0.25 * (math.sin(frame * 2 * math.pi / 100) * 0.5 + 0.5))
    r.draw_ring(cx, cy, outer, inner, (1.0, 0.9, 0.1, 1.0))
    _label(r, "draw_ring", cx - cell_w * 0.5, rows[1] + cell_h * 0.5 + 4 * s, s)


# ---------------------------------------------------------------------------
# Scene 2 — Arcs, Pies & Borders
# ---------------------------------------------------------------------------

def _scene_arcs_pies(r: Renderer, frame: int, s: float, lw: float, lh: float) -> None:
    progress = frame / SCENE_DURATION

    # Arc progress ring
    cx1, cy1 = lw * 0.20, lh * 0.42
    rad = 90 * s
    r.draw_ring(cx1, cy1, rad, rad * 0.70, (0.25, 0.25, 0.30, 1.0))
    a_start = -math.pi * 0.5
    a_end = a_start + progress * 2.0 * math.pi
    if progress > 0.001:
        r.draw_arc(cx1, cy1, rad * 0.85, a_start, a_end, rad * 0.28, (0.2, 0.7, 1.0, 1.0))
    _label(r, f"draw_arc  ({int(progress*100)}%)", cx1 - rad, cy1 + rad + 8 * s, s)

    # Pie chart — whole chart rotates continuously
    cx2, cy2 = lw * 0.52, lh * 0.42
    pie_r = 85 * s
    rot = frame * 0.015
    slices = [
        (0.35, (0.9, 0.3, 0.3, 1.0)),
        (0.25, (0.3, 0.8, 0.4, 1.0)),
        (0.40, (0.3, 0.5, 0.9, 1.0)),
    ]
    a = rot
    for frac, col in slices:
        a1 = a + frac * 2 * math.pi
        r.draw_pie(cx2, cy2, pie_r, a, a1, col)
        a = a1
    _label(r, "draw_pie  (rotating)", cx2 - pie_r, cy2 + pie_r + 8 * s, s)

    # Rect border — thickness pulses
    bx, by = lw * 0.78, lh * 0.30
    bw, bh = 160 * s, 80 * s
    bt = (2.0 + 2.5 * (math.sin(frame * 2 * math.pi / 60) * 0.5 + 0.5)) * s
    r.draw_rect_border(bx - bw * 0.5, by - bh * 0.5, bw, bh, bt, (0.8, 0.8, 0.8, 1.0))
    _label(r, "draw_rect_border", bx - bw * 0.5, by + bh * 0.5 + 4 * s, s)

    by2 = lh * 0.62
    r.draw_rect_rounded_border(bx - bw * 0.5, by2 - bh * 0.5, bw, bh, 16 * s, bt,
                               (0.65, 0.85, 1.0, 1.0))
    _label(r, "draw_rect_rounded_border", bx - bw * 0.5, by2 + bh * 0.5 + 4 * s, s)


# ---------------------------------------------------------------------------
# Scene 3 — Triangles & Polygons  (all shapes rotate)
# ---------------------------------------------------------------------------

def _make_regular_polygon(cx: float, cy: float, r: float, n: int,
                          offset: float = 0.0) -> list[tuple[float, float]]:
    return [
        (cx + math.cos(2 * math.pi * i / n + offset) * r,
         cy + math.sin(2 * math.pi * i / n + offset) * r)
        for i in range(n)
    ]


def _make_star(cx: float, cy: float, r_outer: float, r_inner: float,
               points: int) -> list[tuple[float, float]]:
    verts = []
    for i in range(points * 2):
        angle = math.pi * i / points - math.pi * 0.5
        r = r_outer if i % 2 == 0 else r_inner
        verts.append((cx + math.cos(angle) * r, cy + math.sin(angle) * r))
    return verts


def _scene_triangles_polygons(r: Renderer, frame: int, s: float, lw: float, lh: float) -> None:
    row1_y = lh * 0.35
    row2_y = lh * 0.68
    spin = frame * 0.018

    # Triangle — rotates around its centroid
    tx, ty = lw * 0.12, row1_y
    ts = 75 * s
    raw_tri = [
        (tx, ty - ts),
        (tx + ts, ty + ts * 0.6),
        (tx - ts, ty + ts * 0.6),
    ]
    tri_pts = _rotate_points(raw_tri, tx, ty, spin * 0.9)
    r.draw_triangle(tri_pts[0][0], tri_pts[0][1],
                    tri_pts[1][0], tri_pts[1][1],
                    tri_pts[2][0], tri_pts[2][1],
                    (0.9, 0.4, 0.2, 1.0))
    _label(r, "draw_triangle", tx - ts, ty + ts * 0.75 + 4 * s, s)

    # Hexagon — rotates and pulses
    hx, hy = lw * 0.32, row1_y
    hr = 70 * s * _pulse(frame, 80, 0.88, 1.12)
    hex_pts = _make_regular_polygon(hx, hy, hr, 6, math.pi / 6 + spin * 0.7)
    r.draw_polygon(hex_pts, (0.4, 0.7, 0.3, 1.0))
    _label(r, "hexagon (6)", hx - 55 * s, hy + 75 * s, s)

    # Pentagon — counter-rotates
    px, py = lw * 0.55, row1_y
    pent_pts = _make_regular_polygon(px, py, 68 * s, 5, -math.pi * 0.5 - spin * 0.6)
    r.draw_polygon(pent_pts, (0.3, 0.55, 0.9, 1.0))
    _label(r, "pentagon (5)", px - 50 * s, py + 72 * s, s)

    # Octagon — rotates, translates up/down
    ox, oy = lw * 0.77, row1_y + _wave(frame, 14 * s, 110)
    oct_pts = _make_regular_polygon(ox, oy, 68 * s, 8, math.pi / 8 + spin * 0.5)
    r.draw_polygon(oct_pts, (0.75, 0.3, 0.7, 1.0))
    _label(r, "octagon (8)", ox - 50 * s, row1_y + 72 * s, s)

    # 10-point star — spins and pulses
    sx, sy = lw * 0.50, row2_y
    star_r = 80 * s * _pulse(frame, 90, 0.90, 1.10)
    star_pts = _make_star(sx, sy, star_r, star_r * 0.4, 10)
    star_pts = _rotate_points(star_pts, sx, sy, spin)
    r.draw_polygon(star_pts, (1.0, 0.85, 0.1, 1.0))
    _label(r, "10-point star", sx - 55 * s, sy + star_r + 4 * s, s)


# ---------------------------------------------------------------------------
# Scene 4 — Gradients  (size/position animation)
# ---------------------------------------------------------------------------

def _scene_gradients(r: Renderer, frame: int, s: float, lw: float, lh: float) -> None:
    gw_base, gh_base = 220 * s, 110 * s
    col = [lw * 0.27, lw * 0.73]
    row = [lh * 0.32, lh * 0.66]

    # Vertical gradient — sways horizontally
    gw, gh = gw_base, gh_base
    dx = _wave(frame, 12 * s, 100)
    x, y = col[0] - gw * 0.5 + dx, row[0] - gh * 0.5
    r.draw_rect_gradient(x, y, gw, gh, (0.2, 0.4, 0.9, 1.0), (0.8, 0.2, 0.5, 1.0))
    _label(r, "draw_rect_gradient (vertical)", col[0] - gw * 0.5, row[0] + gh * 0.5 + 4 * s, s)

    # Horizontal gradient — height pulses
    gh2 = gh_base * _pulse(frame, 80, 0.7, 1.3)
    x, y = col[1] - gw * 0.5, row[0] - gh2 * 0.5
    r.draw_rect_gradient_h(x, y, gw, gh2, (0.1, 0.8, 0.4, 1.0), (0.9, 0.7, 0.1, 1.0))
    _label(r, "draw_rect_gradient_h (horizontal)", x, row[0] + gh_base * 0.5 + 4 * s, s)

    # Four-corner gradient — translates diagonally
    off = _wave(frame, 10 * s, 130)
    x, y = col[0] - gw * 0.5 + off, row[1] - gh * 0.5 + off * 0.5
    r.draw_rect_gradient_corner(x, y, gw, gh,
                                (1.0, 0.2, 0.2, 1.0),
                                (0.2, 1.0, 0.2, 1.0),
                                (0.2, 0.2, 1.0, 1.0),
                                (1.0, 1.0, 0.2, 1.0))
    _label(r, "draw_rect_gradient_corner", col[0] - gw * 0.5, row[1] + gh * 0.5 + 4 * s, s)

    # Radial gradient — radius pulses
    cx2, cy2 = col[1], row[1]
    rr = gh * 0.52 * _pulse(frame, 90, 0.85, 1.15)
    r.draw_circle_gradient(cx2, cy2, rr, (1.0, 1.0, 1.0, 1.0), (0.2, 0.1, 0.5, 1.0))
    _label(r, "draw_circle_gradient (radial)", cx2 - gw * 0.5, row[1] + gh * 0.52 + 4 * s, s)


# ---------------------------------------------------------------------------
# Scene 5 — Lines & Curves  (animated control points)
# ---------------------------------------------------------------------------

def _scene_lines(r: Renderer, frame: int, s: float, lw: float, lh: float) -> None:
    margin_x = lw * 0.22
    right_x = lw * 0.92
    y_positions = [lh * 0.20, lh * 0.35, lh * 0.50, lh * 0.65, lh * 0.80]
    label_x = lw * 0.04

    # Solid line
    y = y_positions[0]
    r.draw_line(margin_x, y, right_x, y, 3 * s, (0.9, 0.9, 0.9, 1.0))
    _label(r, "draw_line", label_x, y - 10 * s, s)

    # Dashed line — dash/gap sizes oscillate
    y = y_positions[1]
    dash = (8 + 8 * (math.sin(frame * 2 * math.pi / 80) * 0.5 + 0.5)) * s
    gap  = (3 + 5 * (math.sin(frame * 2 * math.pi / 60) * 0.5 + 0.5)) * s
    r.draw_dashed_line(margin_x, y, right_x, y, 3 * s, (0.6, 0.9, 0.4, 1.0),
                       dash=dash, gap=gap)
    _label(r, "draw_dashed_line", label_x, y - 10 * s, s)

    # Polyline zigzag — amplitude oscillates
    y = y_positions[2]
    span = right_x - margin_x
    amp = 30 * s * _pulse(frame, 100, 0.3, 1.7)
    zpts = [(margin_x + span * i / 7, y + (amp if i % 2 == 0 else -amp)) for i in range(8)]
    r.draw_polyline(zpts, 3 * s, (1.0, 0.6, 0.2, 1.0))
    _label(r, "draw_polyline", label_x, y - 10 * s, s)

    # Quadratic Bezier — control point floats
    y = y_positions[3]
    cy_ctrl = y - 60 * s + _wave(frame, 40 * s, 110)
    r.draw_bezier_quadratic(margin_x, y + 30 * s, lw * 0.57, cy_ctrl, right_x, y + 30 * s,
                            3 * s, (0.4, 0.7, 1.0, 1.0))
    _label(r, "draw_bezier_quadratic", label_x, y - 10 * s, s)

    # Cubic Bezier — control points orbit
    y = y_positions[4]
    angle = frame * 0.04
    r0 = 60 * s
    cx0 = lw * 0.38 + math.cos(angle) * r0
    cy0 = y - r0 + math.sin(angle) * r0
    cx1 = lw * 0.62 + math.cos(angle + math.pi) * r0
    cy1 = y + r0 + math.sin(angle + math.pi) * r0
    r.draw_bezier_cubic(margin_x, y, cx0, cy0, cx1, cy1, right_x, y,
                        3 * s, (0.9, 0.3, 0.7, 1.0))
    _label(r, "draw_bezier_cubic", label_x, y - 10 * s, s)


# ---------------------------------------------------------------------------
# Scene 6 — Shadows & Glows  (float + pulsing glow)
# ---------------------------------------------------------------------------

def _scene_shadows(r: Renderer, frame: int, s: float, lw: float, lh: float) -> None:
    hover = _wave(frame, 8 * s, 120)

    # Rounded rect with drop shadow — floats
    rx, ry = lw * 0.20, lh * 0.38 + hover
    rw, rh = 200 * s, 100 * s
    r.draw_drop_shadow(rx - rw * 0.5, ry - rh * 0.5, rw, rh,
                       ox=6 * s, oy=8 * s, blur=18 * s,
                       radius=16 * s, color=(0.0, 0.0, 0.0, 0.6))
    r.draw_rect_rounded(rx - rw * 0.5, ry - rh * 0.5, rw, rh, 16 * s, (0.3, 0.55, 0.9, 1.0))
    _label(r, "Rounded rect + drop shadow", rx - rw * 0.5, lh * 0.38 + rh * 0.5 + 14 * s, s)

    # Circle with pulsing glow
    gx, gy = lw * 0.55, lh * 0.40 + hover * 0.7
    gr = 65 * s
    glow_blur = 30 * s * _pulse(frame, 80, 0.6, 1.6)
    r.draw_drop_shadow(gx - gr, gy - gr, gr * 2, gr * 2,
                       ox=0, oy=0, blur=glow_blur, radius=gr,
                       color=(0.2, 0.7, 1.0, 0.7))
    r.draw_circle(gx, gy, gr, (0.2, 0.65, 1.0, 1.0))
    _label(r, "Circle + glow (ox=oy=0, large blur)", gx - gr, lh * 0.40 + gr + 14 * s, s)

    # Capsule with shadow — translates sideways
    kx = lw * 0.80 + _wave(frame, 16 * s, 150)
    ky = lh * 0.40 + hover * 0.5
    kw, kh = 160 * s, 60 * s
    r.draw_drop_shadow(kx - kw * 0.5, ky - kh * 0.5, kw, kh,
                       ox=4 * s, oy=6 * s, blur=14 * s,
                       color=(0.0, 0.0, 0.0, 0.55))
    r.draw_capsule(kx - kw * 0.5, ky - kh * 0.5, kw, kh, (0.8, 0.5, 0.2, 1.0))
    _label(r, "Capsule + drop shadow", lw * 0.80 - kw * 0.5, lh * 0.40 + kh * 0.5 + 14 * s, s)

    r.draw_text("draw_drop_shadow drawn before the shape, then shape on top",
                lw * 0.05, lh * 0.80, color=C_DIM, font_size=max(14, int(20 * s)))


# ---------------------------------------------------------------------------
# Scene 7 — Sprites & Nine-Slice  (translate, scale, tint animation)
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
    # Full-size sprite — bobs vertically
    sp = 128 * s
    sx1 = lw * 0.12 - sp * 0.5
    sy1 = lh * 0.35 - sp * 0.5 + _wave(frame, 14 * s, 120)
    r.draw_sprite(sprite_tex, sx1, sy1, sp, sp)
    _label(r, "draw_sprite (full size)", lw * 0.12 - sp * 0.5, lh * 0.35 + sp * 0.5 + 4 * s, s)

    # Scaled + tinted sprite — scale pulses, tint shifts
    sp2_base = 80 * s
    sp2 = sp2_base * _pulse(frame, 90, 0.80, 1.20)
    tint_r = 0.5 + 0.5 * math.sin(frame * 2 * math.pi / 120)
    tint_g = 0.5 + 0.5 * math.sin(frame * 2 * math.pi / 120 + 2.094)
    sx2 = lw * 0.38 - sp2 * 0.5
    sy2 = lh * 0.38 - sp2 * 0.5
    r.draw_sprite(sprite_tex, sx2, sy2, sp2, sp2, tint=(tint_r, tint_g, 0.6, 0.85))
    _label(r, "draw_sprite (scaled + tinted)", lw * 0.38 - sp2_base * 0.5,
           lh * 0.38 + sp2_base * 0.5 + 4 * s, s)

    # Nine-slice small — translates
    ns_brd = 8
    ns_w1, ns_h1 = 160 * s, 90 * s
    nsx1 = lw * 0.63 - ns_w1 * 0.5 + _wave(frame, 20 * s, 110)
    nsy1 = lh * 0.35 - ns_h1 * 0.5
    r.draw_nine_slice(nineslice_tex, nsx1, nsy1, ns_w1, ns_h1, ns_brd * s)
    _label(r, "draw_nine_slice (small)", lw * 0.63 - ns_w1 * 0.5, nsy1 + ns_h1 + 4 * s, s)

    # Nine-slice wide — width pulses
    ns_w2 = (300 + 80 * (math.sin(frame * 2 * math.pi / 100) * 0.5 + 0.5)) * s
    ns_h2 = 90 * s
    nsx2 = lw * 0.85 - ns_w2 * 0.5
    nsy2 = lh * 0.35 - ns_h2 * 0.5
    r.draw_nine_slice(nineslice_tex, nsx2, nsy2, ns_w2, ns_h2, ns_brd * s)
    _label(r, "draw_nine_slice (wide — centre stretches, corners stay fixed)",
           lw * 0.85 - 180 * s, nsy2 + ns_h2 + 4 * s, s)

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
    pygame.init()
    pygame.font.init()

    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_FORWARD_COMPATIBLE_FLAG, True)

    desk_sizes = pygame.display.get_desktop_sizes()
    log_w, log_h = desk_sizes[0] if desk_sizes else (1280, 720)

    flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE
    pygame.display.set_mode((log_w, log_h), flags)
    pygame.display.set_caption("Grimoire2D — Primitives Showcase")

    draw_w, draw_h = get_drawable_size(log_w, log_h)
    pixel_ratio_x = draw_w / log_w
    pixel_ratio_y = draw_h / log_h

    ctx = moderngl.create_context()
    renderer = Renderer(ctx, VirtualResolution(width=draw_w, height=draw_h, integer_scaling=False))
    renderer.handle_physical_resize(draw_w, draw_h)

    sprite_tex = _make_sprite_texture(ctx)
    nineslice_tex = _make_nineslice_texture(ctx)

    s = draw_h / 720.0
    lw = float(draw_w)
    lh = float(draw_h)

    current_scene = 0
    scene_frame = 0       # animation clock; always increments
    auto_advance = False  # SPACE toggles

    clock = pygame.time.Clock()
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    auto_advance = not auto_advance
                elif event.key == pygame.K_RIGHT:
                    current_scene = (current_scene + 1) % SCENE_COUNT
                    scene_frame = 0
                elif event.key == pygame.K_LEFT:
                    current_scene = (current_scene - 1) % SCENE_COUNT
                    scene_frame = 0
            elif event.type == pygame.VIDEORESIZE:
                draw_w2 = round(event.w * pixel_ratio_x)
                draw_h2 = round(event.h * pixel_ratio_y)
                renderer.handle_physical_resize(draw_w2, draw_h2)

        renderer.prepare_frame()

        # Background
        renderer.draw_rect(0, 0, lw, lh, C_BG)

        # Scene content
        _draw_scene(renderer, current_scene, scene_frame, s, lw, lh, sprite_tex, nineslice_tex)

        # --- Fade overlay ---
        # Fade in: 1.0 → 0.0 over first FADE_FRAMES of each scene
        # Fade out: 0.0 → 1.0 over last FADE_FRAMES (only when auto_advance previews next switch)
        fade_alpha = 0.0
        if scene_frame < FADE_FRAMES:
            fade_alpha = 1.0 - scene_frame / FADE_FRAMES
        elif auto_advance and scene_frame > SCENE_DURATION - FADE_FRAMES:
            fade_alpha = (scene_frame - (SCENE_DURATION - FADE_FRAMES)) / FADE_FRAMES
        if fade_alpha > 0.001:
            renderer.draw_rect(0, 0, lw, lh, (0.0, 0.0, 0.0, min(1.0, fade_alpha)))

        # --- HUD ---
        renderer.draw_text(
            SCENE_NAMES[current_scene],
            12 * s, 8 * s,
            color=C_WHITE,
            font_size=max(18, int(30 * s)),
        )

        fps_str = f"FPS: {clock.get_fps():.0f}"
        fps_w, _ = renderer.measure_text(fps_str, font_size=max(14, int(22 * s)))
        renderer.draw_text(fps_str, lw - fps_w - 12 * s, 8 * s,
                           color=C_YELLOW, font_size=max(14, int(22 * s)))

        auto_label = "AUTO: ON" if auto_advance else "AUTO: OFF"
        auto_color = C_GREEN if auto_advance else C_DIM
        auto_w, _ = renderer.measure_text(auto_label, font_size=max(12, int(18 * s)))
        renderer.draw_text(auto_label, lw - auto_w - 12 * s, 40 * s,
                           color=auto_color, font_size=max(12, int(18 * s)))

        hint = f"Scene {current_scene + 1}/{SCENE_COUNT}   ←→ navigate   SPACE auto-advance   ESC quit"
        hint_w, _ = renderer.measure_text(hint, font_size=max(12, int(18 * s)))
        renderer.draw_text(hint, (lw - hint_w) * 0.5, lh - 28 * s,
                           color=C_DIM, font_size=max(12, int(18 * s)))

        renderer.present()
        pygame.display.flip()

        # scene_frame always increments for continuous animation
        scene_frame += 1

        # Auto-switch only when enabled
        if auto_advance and scene_frame >= SCENE_DURATION:
            scene_frame = 0
            current_scene = (current_scene + 1) % SCENE_COUNT

        clock.tick(60)

    sprite_tex.release()
    nineslice_tex.release()
    pygame.quit()


if __name__ == "__main__":
    main()
