"""Pause system demo.

Demonstrates selective pause via PauseState update groups.

  ENTER / RETURN  toggle pause
  ESC             quit

Four actors are on screen:

  Blue circle      orbits the centre (rotation + translation)  [gameplay group]
  Purple rect      bounces left/right and spins                 [gameplay group]
  Orange triangle  rotates in place and pulses in size          [gameplay group]
  Yellow ring      spins in the corner — NEVER pauses           [always group]

When paused:
  • The three gameplay actors freeze exactly where they are.
  • The yellow ring keeps spinning (different update group).
  • A "PAUSED" banner flashes at the centre (UI counter always advances).
  • The scene dims slightly to emphasise the frozen state.

The topology is single_player (local), so pause is permitted.
Swap MultiplayerConfig.single_player() for MultiplayerConfig.network_host()
and ENTER will have no effect — the pause request is silently rejected.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pygame

from grimoire2d.presentation.window import GameWindow
from grimoire2d.models.pause import PauseState, GROUP_GAMEPLAY
from grimoire2d.models.multiplayer import MultiplayerConfig
from grimoire2d.logic.pause_logic import toggle_pause, is_paused

if TYPE_CHECKING:
    from grimoire2d.presentation.renderer import Renderer

# ---------------------------------------------------------------------------
# Actor helpers
# ---------------------------------------------------------------------------


def _rotate_pts(
    pts: list[tuple[float, float]], cx: float, cy: float, angle: float
) -> list[tuple[float, float]]:
    c, s = math.cos(angle), math.sin(angle)
    return [
        (cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c)
        for x, y in pts
    ]


def _tri(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    return [
        (cx, cy - r),
        (cx + r * math.cos(math.pi / 6), cy + r * math.sin(math.pi / 6)),
        (cx - r * math.cos(math.pi / 6), cy + r * math.sin(math.pi / 6)),
    ]


# ---------------------------------------------------------------------------
# Scene-drawing functions (read gameplay_frame / ui_frame, never mutate)
# ---------------------------------------------------------------------------


def _draw_orbiting_circle(r: Renderer, gf: int, s: float, cx: float, cy: float) -> None:
    """Blue circle that orbits the screen centre (gameplay group)."""
    orbit_r = 160 * s
    angle = gf * 0.025
    x = cx + math.cos(angle) * orbit_r
    y = cy + math.sin(angle) * orbit_r
    radius = (28 + 10 * math.sin(gf * 0.07)) * s
    r.draw_circle(x, y, radius, (0.15, 0.55, 1.0, 1.0))
    # trail ghost
    for i in range(1, 4):
        a2 = angle - i * 0.12
        gx = cx + math.cos(a2) * orbit_r
        gy = cy + math.sin(a2) * orbit_r
        alpha = 0.25 - i * 0.07
        r.draw_circle(gx, gy, radius * (1.0 - i * 0.2), (0.15, 0.55, 1.0, alpha))


def _draw_bouncing_rect(
    r: Renderer, gf: int, s: float, cx: float, cy: float, lw: float
) -> None:
    """Purple rect that bounces left/right and spins (gameplay group)."""
    span = lw * 0.30
    bx = cx + math.sin(gf * 0.032) * span
    by = cy + lw * 0.18
    angle = gf * 0.045
    w, h = 110 * s, 55 * s
    # draw_rect doesn't rotate, so we submit a rotated polygon
    corners = [
        (bx - w * 0.5, by - h * 0.5),
        (bx + w * 0.5, by - h * 0.5),
        (bx + w * 0.5, by + h * 0.5),
        (bx - w * 0.5, by + h * 0.5),
    ]
    rotated = _rotate_pts(corners, bx, by, angle)
    r.draw_polygon(rotated, (0.65, 0.2, 0.85, 1.0))


def _draw_spinning_triangle(
    r: Renderer, gf: int, s: float, cx: float, cy: float, lw: float
) -> None:
    """Orange triangle that rotates and pulses in size (gameplay group)."""
    tx = cx - lw * 0.24
    ty = cy - lw * 0.05
    scale = 1.0 + 0.35 * math.sin(gf * 0.055)
    radius = 70 * s * scale
    angle = gf * 0.038
    pts = _tri(tx, ty, radius)
    pts = _rotate_pts(pts, tx, ty, angle)
    r.draw_polygon(pts, (1.0, 0.5, 0.1, 1.0))


def _draw_always_on_ring(r: Renderer, uf: int, s: float, lw: float, lh: float) -> None:
    """Yellow ring in the corner — uses ui_frame, never checks pause."""
    margin = 90 * s
    cx, cy = lw - margin, lh - margin
    outer = 50 * s
    inner = outer * 0.55
    # Spinning indicator: draw arc from 0 to growing angle
    angle = uf * 0.06
    r.draw_ring(cx, cy, outer, inner, (0.25, 0.25, 0.20, 1.0))
    r.draw_arc(
        cx,
        cy,
        (outer + inner) * 0.5,
        0.0,
        angle,
        (outer - inner) * 0.9,
        (1.0, 0.9, 0.1, 1.0),
    )
    # Label
    label_x = cx - 62 * s
    label_y = cy + outer + 6 * s
    r.draw_text(
        "always on",
        label_x,
        label_y,
        color=(0.7, 0.7, 0.2, 1.0),
        font_size=max(12, int(16 * s)),
    )


def _draw_pause_overlay(r: Renderer, uf: int, s: float, lw: float, lh: float) -> None:
    """Dim overlay + flashing PAUSED banner (UI group, always animates)."""
    # Dim the scene
    r.draw_rect(0, 0, lw, lh, (0.0, 0.0, 0.0, 0.45))

    # Flashing text (visible 30 frames on, 20 frames off)
    cycle = uf % 50
    if cycle < 30:
        alpha = 1.0
    else:
        # smooth fade-out in last 20 frames of cycle
        alpha = 1.0 - (cycle - 30) / 20.0

    if alpha > 0.01:
        text = "PAUSED"
        fs = max(36, int(72 * s))
        tw, th = r.measure_text(text, font_size=fs)
        r.draw_text(
            text,
            (lw - tw) * 0.5,
            (lh - th) * 0.5 - 20 * s,
            color=(1.0, 0.95, 0.3, alpha),
            font_size=fs,
        )

    # Static hint below
    hint = "Press ENTER to unpause"
    hfs = max(14, int(22 * s))
    hw, _ = r.measure_text(hint, font_size=hfs)
    r.draw_text(
        hint,
        (lw - hw) * 0.5,
        lh * 0.5 + 30 * s,
        color=(0.8, 0.8, 0.8, 0.9),
        font_size=hfs,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # Virtual coordinate space: 1280×720. The engine scales to the user's
    # display and letterboxes to preserve aspect ratio automatically.
    win = GameWindow("Grimoire2D — Pause Demo", virtual_width=1280, virtual_height=720)
    r = win.renderer

    # Fixed virtual layout constants
    lw, lh, s = 1280.0, 720.0, 1.0
    cx, cy = lw * 0.5, lh * 0.5

    mp_config = MultiplayerConfig.single_player()
    pause_state = PauseState.running()

    gameplay_frame: int = 0
    ui_frame: int = 0

    while win.is_open:
        for event in win.poll():
            if event.type == pygame.QUIT:
                win.close()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    win.close()
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    pause_state = toggle_pause(pause_state, mp_config)

        gameplay_paused = is_paused(pause_state, GROUP_GAMEPLAY)
        if not gameplay_paused:
            gameplay_frame += 1
        ui_frame += 1

        win.begin_frame()
        r.draw_rect(0, 0, lw, lh, (0.06, 0.06, 0.09, 1.0))

        orbit_r = 160 * s
        r.draw_ring(cx, cy, orbit_r + 1 * s, orbit_r - 1 * s, (0.2, 0.2, 0.2, 0.5))

        _draw_orbiting_circle(r, gameplay_frame, s, cx, cy)
        _draw_bouncing_rect(r, gameplay_frame, s, cx, cy, lw)
        _draw_spinning_triangle(r, gameplay_frame, s, cx, cy, lw)
        _draw_always_on_ring(r, ui_frame, s, lw, lh)

        if gameplay_paused:
            _draw_pause_overlay(r, ui_frame, s, lw, lh)

        topo_text = f"Topology: {mp_config.topology}"
        r.draw_text(
            topo_text, 12 * s, 8 * s, color=(0.45, 0.45, 0.45, 1.0), font_size=18
        )

        state_text = "GAMEPLAY: PAUSED" if gameplay_paused else "GAMEPLAY: RUNNING"
        state_color = (1.0, 0.7, 0.2, 1.0) if gameplay_paused else (0.3, 0.9, 0.4, 1.0)
        r.draw_text(state_text, 12 * s, 32 * s, color=state_color, font_size=18)

        hint = "ENTER  toggle pause   |   ESC  quit"
        hw, _ = r.measure_text(hint, font_size=16)
        r.draw_text(
            hint, (lw - hw) * 0.5, lh - 26 * s, color=(0.4, 0.4, 0.4, 1.0), font_size=16
        )

        fps_str = f"FPS: {win.fps:.0f}"
        fw, _ = r.measure_text(fps_str, font_size=18)
        r.draw_text(
            fps_str, lw - fw - 12 * s, 8 * s, color=(1.0, 0.9, 0.2, 1.0), font_size=18
        )

        legend = [
            ((0.15, 0.55, 1.0, 1.0), "Orbiting circle    [gameplay — pauses]"),
            ((0.65, 0.20, 0.85, 1.0), "Bouncing rect      [gameplay — pauses]"),
            ((1.0, 0.50, 0.10, 1.0), "Spinning triangle  [gameplay — pauses]"),
            ((1.0, 0.90, 0.10, 1.0), "Spinning ring      [always on — never pauses]"),
        ]
        for i, (color, label) in enumerate(legend):
            lx = 12 * s
            ly = lh - (26 + (len(legend) - i) * 20) * s
            r.draw_circle(lx + 6 * s, ly + 6 * s, 5 * s, color)
            r.draw_text(
                label, lx + 15 * s, ly, color=(0.65, 0.65, 0.65, 1.0), font_size=15
            )

        win.end_frame()

    win.quit()


if __name__ == "__main__":
    main()
