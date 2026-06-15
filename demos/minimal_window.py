"""Minimal demo showing the turnkey GameWindow path (recommended for games).

A single call to GameWindow gives you a resizable OpenGL 3.3 window with
a fixed virtual resolution. The engine handles HiDPI, letterboxing,
pillarboxing, centering, and scaling so that all drawing happens in the
virtual coordinate space while the backbuffer is always correctly placed
on the user's display.

For apps/tools that need the full data-model configuration (EngineConfig +
extensions for virtual resolution, window policy, video settings, etc.)
see the (now secondary) open_and_run / AppState path in the source.

Usage:
    python -m demos.minimal_window

Keys (window must have focus):
    ESC - quit

Drag any window edge. The engine recomputes the letterbox so the entire
1280x720 virtual surface stays visible and centered.
"""

import sys
from pathlib import Path

# Allow running without install
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pygame

from grimoire2d.presentation.window import GameWindow


def main() -> None:
    # The simple baked-in contract: pick a virtual size, draw in it forever.
    # GameWindow + Renderer + compute_viewport do the rest (HiDPI, letterbox,
    # centering, resize handling).  No per-demo math for drawable vs logical.
    print("GameWindow demo — fixed virtual 1280x720.")
    print("Drag to resize the OS window; the engine letterboxes/centers automatically.")
    print("ESC to quit.")

    win = GameWindow(
        "Grimoire2D — Minimal Window (GameWindow)",
        virtual_width=1280,
        virtual_height=720,
    )
    r = win.renderer

    # Simple content in virtual space (yellow border proves the full virtual
    # surface is always mapped, never cropped).
    while win.is_open:
        for event in win.poll():
            if event.type == pygame.QUIT:
                win.close()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                win.close()

        win.begin_frame()
        r.draw_rect(0, 0, 1280, 720, (0.08, 0.08, 0.10, 1.0))
        r.draw_virtual_border(4.0)
        r.draw_text(
            "Virtual 1280×720 — engine handles scaling + letterboxing",
            80,
            80,
            color=(0.9, 0.9, 0.2, 1.0),
            font_size=28,
        )
        r.draw_text(
            "Resize the window; content stays crisp in aspect and fully visible.",
            80,
            120,
            color=(0.7, 0.7, 0.75, 1.0),
            font_size=20,
        )
        r.draw_text(
            f"FPS: {win.fps:.0f}", 80, 160, color=(1.0, 0.85, 0.2, 1.0), font_size=18
        )
        win.end_frame()

    win.quit()


if __name__ == "__main__":
    main()
