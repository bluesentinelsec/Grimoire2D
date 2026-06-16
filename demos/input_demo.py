"""Input system demo.

Exercises the full input stack: keyboard, mouse, up to 4 gamepads, action
mapping, axis-as-button helpers, and gamepad rumble.

Controls
--------
  ESC             quit
  Any gamepad     connect and see live state; hold START to rumble

Default action map (shown in the Active Actions panel)
------------------------------------------------------
  accept    → Enter  /  Gamepad A
  cancel    → Escape /  Gamepad B
  move_up   → W / Up arrow  /  Left-stick up  /  DPad-up
  move_down → S / Down arrow / Left-stick down / DPad-down
  move_left → A / Left arrow / Left-stick left / DPad-left
  move_right→ D / Right arrow/ Left-stick right/ DPad-right
  fire      → Space  /  Gamepad X  /  Left mouse button
  aim       → Left-trigger (axis-as-button, threshold 0.2)
  rumble    → R key  /  Gamepad START  — triggers rumble on all pads

Layout (1280×720 virtual)
-------------------------
  Top strip   — title
  Row 1       — Active Actions | Mouse state | Keyboard
  Row 2       — Pad 0 | Pad 1 | Pad 2 | Pad 3
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.presentation.highdpi import enable_highdpi, get_drawable_size

enable_highdpi()

import pygame
import moderngl

from grimoire2d.logic.scaling import compute_viewport
from grimoire2d.models import VirtualResolution
from grimoire2d.models.gamepad_state import GamepadAxis, GamepadButton
from grimoire2d.models.input_binding import (
    GamepadAxisBinding,
    GamepadButtonBinding,
    KeyBinding,
    MouseButtonBinding,
)
from grimoire2d.models.input_map import InputMap
from grimoire2d.models.raw_input_frame import RawInputFrame
from grimoire2d.presentation.input_manager import InputManager
from grimoire2d.presentation.mapped_input_source import MappedInputSource
from grimoire2d.presentation.renderer import Renderer

# ---------------------------------------------------------------------------
# Layout constants (all in virtual pixels, 1280×720)
# ---------------------------------------------------------------------------

VW, VH = 1280, 720

PANEL_BG = (0.09, 0.09, 0.12, 1.0)
HEADER_BG = (0.15, 0.15, 0.22, 1.0)
ACCENT = (0.25, 0.55, 1.0, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)
DIM = (0.55, 0.55, 0.65, 1.0)
GREEN = (0.20, 0.85, 0.40, 1.0)
RED = (0.90, 0.25, 0.25, 1.0)
YELLOW = (1.0, 0.85, 0.15, 1.0)
ORANGE = (1.0, 0.55, 0.10, 1.0)

# ---------------------------------------------------------------------------
# Default action map
# ---------------------------------------------------------------------------


def _build_input_map() -> InputMap:
    m = InputMap.empty()

    for action, bindings in [
        ("accept", [KeyBinding("return"), GamepadButtonBinding(GamepadButton.A)]),
        ("cancel", [KeyBinding("escape"), GamepadButtonBinding(GamepadButton.B)]),
        (
            "move_up",
            [
                KeyBinding("w"),
                KeyBinding("up"),
                GamepadButtonBinding(GamepadButton.DPAD_UP),
                GamepadAxisBinding(GamepadAxis.LEFT_Y, direction=-1, threshold=0.4),
            ],
        ),
        (
            "move_down",
            [
                KeyBinding("s"),
                KeyBinding("down"),
                GamepadButtonBinding(GamepadButton.DPAD_DOWN),
                GamepadAxisBinding(GamepadAxis.LEFT_Y, direction=1, threshold=0.4),
            ],
        ),
        (
            "move_left",
            [
                KeyBinding("a"),
                KeyBinding("left"),
                GamepadButtonBinding(GamepadButton.DPAD_LEFT),
                GamepadAxisBinding(GamepadAxis.LEFT_X, direction=-1, threshold=0.4),
            ],
        ),
        (
            "move_right",
            [
                KeyBinding("d"),
                KeyBinding("right"),
                GamepadButtonBinding(GamepadButton.DPAD_RIGHT),
                GamepadAxisBinding(GamepadAxis.LEFT_X, direction=1, threshold=0.4),
            ],
        ),
        (
            "fire",
            [
                KeyBinding("space"),
                GamepadButtonBinding(GamepadButton.X),
                MouseButtonBinding(1),
            ],
        ),
        (
            "aim",
            [GamepadAxisBinding(GamepadAxis.LEFT_TRIGGER, direction=1, threshold=0.2)],
        ),
        ("rumble", [KeyBinding("r"), GamepadButtonBinding(GamepadButton.START)]),
    ]:
        for b in bindings:
            m = m.with_binding(action, b)
    return m


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------


def _label(
    r: Renderer, text: str, x: float, y: float, color=WHITE, fs: int = 18
) -> float:
    """Draw text and return the y position after it."""
    r.draw_text(text, x, y, color=color, font_size=fs)
    _, h = r.measure_text(text, font_size=fs)
    return y + h + 2


def _panel(r: Renderer, x: float, y: float, w: float, h: float, title: str) -> float:
    """Draw a labelled panel background. Returns the y for content start."""
    r.draw_rect(x, y, w, h, PANEL_BG)
    r.draw_rect(x, y, w, 22, HEADER_BG)
    r.draw_text(title, x + 6, y + 3, color=ACCENT, font_size=16)
    r.draw_rect_border(x, y, w, h, 1.0, (0.25, 0.30, 0.45, 1.0))
    return y + 24


# ---------------------------------------------------------------------------
# Active-actions panel
# ---------------------------------------------------------------------------


def _draw_actions(
    r: Renderer,
    raw: RawInputFrame,
    imap: InputMap,
    actions: frozenset[str],
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    cy = _panel(r, x, y, w, h, "ACTIVE ACTIONS")
    for action in sorted(imap.action_names()):
        active = action in actions
        color = GREEN if active else DIM
        prefix = "▶ " if active else "  "
        cy = _label(r, f"{prefix}{action}", x + 8, cy, color=color, fs=16)
        if cy > y + h - 18:
            break


# ---------------------------------------------------------------------------
# Mouse panel
# ---------------------------------------------------------------------------


def _draw_mouse(
    r: Renderer, raw: RawInputFrame, x: float, y: float, w: float, h: float
) -> None:
    cy = _panel(r, x, y, w, h, "MOUSE")
    m = raw.mouse
    mx, my = m.position
    vx, vy = m.virtual_position
    sdx, sdy = m.scroll_delta

    cy = _label(r, f"Screen:  {mx:7.1f}, {my:7.1f}", x + 8, cy, fs=16)
    cy = _label(r, f"Virtual: {vx:7.1f}, {vy:7.1f}", x + 8, cy, fs=16)
    cy = _label(r, f"Scroll:  {sdx:+.1f}, {sdy:+.1f}", x + 8, cy, fs=16)
    cy += 4

    btn_labels = ["L", "M", "R", "BK", "FW"]
    from grimoire2d.models.mouse_state import MouseButton

    btn_enums = [
        MouseButton.LEFT,
        MouseButton.MIDDLE,
        MouseButton.RIGHT,
        MouseButton.BACK,
        MouseButton.FORWARD,
    ]
    bx = x + 8
    for label, btn in zip(btn_labels, btn_enums):
        held = btn in m.buttons
        color = GREEN if held else (0.25, 0.25, 0.35, 1.0)
        r.draw_rect(bx, cy, 36, 22, color)
        r.draw_text_centered(label, bx + 18, cy + 11, color=WHITE, font_size=15)
        bx += 42


# ---------------------------------------------------------------------------
# Keyboard panel
# ---------------------------------------------------------------------------


def _draw_keyboard(
    r: Renderer, raw: RawInputFrame, x: float, y: float, w: float, h: float
) -> None:
    cy = _panel(r, x, y, w, h, "KEYBOARD")
    keys = sorted(raw.keys_held)
    if not keys:
        _label(r, "(no keys held)", x + 8, cy, color=DIM, fs=16)
        return
    line = ""
    for key in keys:
        candidate = (line + "  " + key).strip() if line else key
        tw, _ = r.measure_text(candidate, font_size=16)
        if tw > w - 16 and line:
            cy = _label(r, line, x + 8, cy, fs=16)
            line = key
        else:
            line = candidate
    if line:
        _label(r, line, x + 8, cy, fs=16)


# ---------------------------------------------------------------------------
# Gamepad panel
# ---------------------------------------------------------------------------

_ALL_BUTTONS = [
    (GamepadButton.A, "A", GREEN),
    (GamepadButton.B, "B", RED),
    (GamepadButton.X, "X", (0.30, 0.50, 1.0, 1.0)),
    (GamepadButton.Y, "Y", YELLOW),
    (GamepadButton.LB, "LB", WHITE),
    (GamepadButton.RB, "RB", WHITE),
    (GamepadButton.BACK, "BK", DIM),
    (GamepadButton.START, "ST", DIM),
    (GamepadButton.GUIDE, "G", ORANGE),
    (GamepadButton.LEFT_STICK, "LS", DIM),
    (GamepadButton.RIGHT_STICK, "RS", DIM),
    (GamepadButton.DPAD_UP, "↑", WHITE),
    (GamepadButton.DPAD_DOWN, "↓", WHITE),
    (GamepadButton.DPAD_LEFT, "←", WHITE),
    (GamepadButton.DPAD_RIGHT, "→", WHITE),
]

def _draw_axis_bar(
    r: Renderer, label: str, value: float, x: float, y: float, w: float
) -> float:
    """Draw a labelled horizontal axis bar. Returns y after the bar."""
    bw = w - 60
    r.draw_text(label, x, y, color=DIM, font_size=14)
    bx = x + 40
    r.draw_rect(bx, y + 2, bw, 12, (0.15, 0.15, 0.22, 1.0))
    # Centre mark
    r.draw_rect(bx + bw // 2 - 1, y + 2, 2, 12, (0.35, 0.35, 0.45, 1.0))
    if abs(value) > 0.01:
        fill_w = max(1, abs(value) * bw / 2)
        fill_x = bx + bw // 2 if value > 0 else bx + bw // 2 - fill_w
        r.draw_rect(fill_x, y + 2, fill_w, 12, ACCENT)
    r.draw_text(f"{value:+.2f}", bx + bw + 4, y, color=WHITE, font_size=14)
    return y + 18


def _draw_stick_crosshair(
    r: Renderer, ax: float, ay: float, cx: float, cy: float, radius: float
) -> None:
    """Draw a stick crosshair at (cx, cy) with the given radius."""
    r.draw_ring(cx, cy, radius, 1.5, (0.25, 0.30, 0.45, 1.0))
    # Cross lines
    r.draw_line(cx - radius, cy, cx + radius, cy, (0.20, 0.25, 0.38, 1.0), 1.0)
    r.draw_line(cx, cy - radius, cx, cy + radius, (0.20, 0.25, 0.38, 1.0), 1.0)
    # Dot at axis position
    dot_x = cx + ax * (radius - 4)
    dot_y = cy + (-ay) * (radius - 4)  # flip y: pygame Y is down
    r.draw_circle(dot_x, dot_y, 5, ACCENT)


def _draw_gamepad(
    r: Renderer, pad_state, x: float, y: float, w: float, h: float, pad_id: int
) -> None:
    from grimoire2d.logic.gamepad_ops import trigger_value

    r.draw_rect(x, y, w, h, PANEL_BG)
    r.draw_rect_border(x, y, w, h, 1.0, (0.25, 0.30, 0.45, 1.0))

    if not pad_state.connected:
        r.draw_rect(x, y, w, 22, (0.18, 0.12, 0.12, 1.0))
        r.draw_text(
            f"PAD {pad_id}  —  NOT CONNECTED",
            x + 6,
            y + 3,
            color=(0.5, 0.3, 0.3, 1.0),
            font_size=16,
        )
        r.draw_text_centered(
            "plug in a gamepad", x + w / 2, y + h / 2, color=DIM, font_size=16
        )
        return

    r.draw_rect(x, y, w, 22, HEADER_BG)
    r.draw_text(f"PAD {pad_id}  •  CONNECTED", x + 6, y + 3, color=GREEN, font_size=16)

    # --- Buttons (row of small squares) ---
    bx, by = x + 6, y + 28
    btn_size = 26
    btn_gap = 4
    for btn, label, c_on in _ALL_BUTTONS:
        held = pad_state.is_button_pressed(btn)
        color = c_on if held else (0.20, 0.20, 0.28, 1.0)
        r.draw_rect(bx, by, btn_size, btn_size, color)
        r.draw_text_centered(
            label,
            bx + btn_size / 2,
            by + btn_size / 2,
            color=WHITE if held else DIM,
            font_size=13,
        )
        bx += btn_size + btn_gap
        if bx + btn_size > x + w - 4:
            bx = x + 6
            by += btn_size + btn_gap

    cy = by + btn_size + 8

    # --- Triggers ---
    lt = trigger_value(pad_state, GamepadAxis.LEFT_TRIGGER)
    rt = trigger_value(pad_state, GamepadAxis.RIGHT_TRIGGER)
    tw = (w - 24) / 2 - 4
    # LT bar
    r.draw_text("LT", x + 6, cy, color=DIM, font_size=14)
    r.draw_rect(x + 6 + 22, cy + 2, tw - 22, 12, (0.15, 0.15, 0.22, 1.0))
    if lt > 0.01:
        r.draw_rect(x + 6 + 22, cy + 2, (tw - 22) * lt, 12, ORANGE)
    # RT bar
    rx2 = x + w / 2 + 4
    r.draw_text("RT", rx2, cy, color=DIM, font_size=14)
    r.draw_rect(rx2 + 22, cy + 2, tw - 22, 12, (0.15, 0.15, 0.22, 1.0))
    if rt > 0.01:
        r.draw_rect(rx2 + 22, cy + 2, (tw - 22) * rt, 12, ORANGE)
    cy += 20

    # --- Stick crosshairs ---
    stick_r = min(35, (h - (cy - y) - 8) / 2 - 4)
    if stick_r > 8:
        mid_y = cy + stick_r + 4
        lx_raw = pad_state.get_axis(GamepadAxis.LEFT_X)
        ly_raw = pad_state.get_axis(GamepadAxis.LEFT_Y)
        rx_raw = pad_state.get_axis(GamepadAxis.RIGHT_X)
        ry_raw = pad_state.get_axis(GamepadAxis.RIGHT_Y)
        _draw_stick_crosshair(r, lx_raw, ly_raw, x + stick_r + 12, mid_y, stick_r)
        _draw_stick_crosshair(r, rx_raw, ry_raw, x + w / 2, mid_y, stick_r)
        r.draw_text("L", x + 6, cy + stick_r * 2 + 6, color=DIM, font_size=13)
        r.draw_text(
            "R", x + w / 2 - stick_r - 10, cy + stick_r * 2 + 6, color=DIM, font_size=13
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    pygame.init()
    pygame.font.init()

    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(
        pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE
    )
    pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)

    info = pygame.display.Info()
    log_w, log_h = info.current_w, info.current_h
    flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE
    pygame.display.set_mode((log_w, log_h), flags)
    pygame.display.set_caption("Grimoire2D — Input System Demo")

    ctx = moderngl.create_context()
    virt = VirtualResolution(width=VW, height=VH, integer_scaling=False)
    renderer = Renderer(ctx, initial_virtual=virt)
    phys_w, phys_h = get_drawable_size(log_w, log_h)
    renderer.handle_physical_resize(phys_w, phys_h)
    renderer.set_clear_color((0.06, 0.06, 0.09, 1.0))

    # --- Input setup ---
    input_manager = InputManager()
    input_manager.initialize()
    imap = _build_input_map()
    source = MappedInputSource("P1", imap, pad_id=None)

    clock = pygame.time.Clock()
    running = True
    tick = 0

    print("Input Demo running — connect gamepads, press keys, move mouse.")
    print("Hold START or press R to test rumble. ESC to quit.")

    while running:
        events = pygame.event.get()
        input_manager.process_events(events)

        for event in events:
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                log_w, log_h = event.size
                phys_w, phys_h = get_drawable_size(log_w, log_h)
                renderer.handle_physical_resize(phys_w, phys_h)

        # Build viewport for mouse coordinate mapping
        phys_w, phys_h = get_drawable_size(log_w, log_h)
        vp = compute_viewport(virt, phys_w, phys_h)
        raw = input_manager.poll(
            tick,
            viewport=(vp.scale, vp.offset_x, vp.offset_y),
        )

        source.update_raw(raw)
        frame = source.poll(tick)
        actions = frame.actions if frame else frozenset()

        # Rumble all connected pads when rumble action fires
        if "rumble" in actions:
            for pad_id in input_manager.connected_pad_ids:
                input_manager.rumble(pad_id, 0.6, 0.3, 120)

        # --- Draw ---
        renderer.prepare_frame()

        # Title strip
        renderer.draw_rect(0, 0, VW, 38, (0.10, 0.10, 0.16, 1.0))
        renderer.draw_text_centered(
            "GRIMOIRE2D  —  INPUT SYSTEM DEMO",
            VW / 2,
            19,
            color=ACCENT,
            font_size=20,
        )
        renderer.draw_text(
            f"tick {tick:06d}  |  pads: {len(input_manager.connected_pad_ids)}",
            VW - 240,
            10,
            color=DIM,
            font_size=15,
        )

        # Row 1: three info panels
        margin = 8
        row1_y = 44
        row1_h = 178
        col_w = (VW - margin * 4) // 3
        col1_x = margin
        col2_x = col1_x + col_w + margin
        col3_x = col2_x + col_w + margin

        _draw_actions(renderer, raw, imap, actions, col1_x, row1_y, col_w, row1_h)
        _draw_mouse(renderer, raw, col2_x, row1_y, col_w, row1_h)
        _draw_keyboard(renderer, raw, col3_x, row1_y, col_w, row1_h)

        # Row 2: gamepad panels (4 across)
        row2_y = row1_y + row1_h + margin
        row2_h = VH - row2_y - margin
        pad_w = (VW - margin * 5) // 4

        for pad_id in range(4):
            px = margin + pad_id * (pad_w + margin)
            state = raw.get_pad(pad_id)
            _draw_gamepad(renderer, state, px, row2_y, pad_w, row2_h, pad_id)

        renderer.present()
        pygame.display.flip()
        clock.tick(60)
        tick += 1

    input_manager.quit()
    pygame.quit()


if __name__ == "__main__":
    main()
