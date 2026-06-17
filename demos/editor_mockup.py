"""Tiled-like map editor mockup using Dear PyGui.

This demo has been reworked to delegate all GUI/widget functionality to
Dear PyGui (a mature, high-quality immediate-mode GUI library). Grimoire2D
no longer attempts to provide or maintain its own widget toolkit.

The core engine (GameWindow, Renderer, etc.) focuses exclusively on game
runtime concerns: batched OpenGL rendering of sprites/lights/particles for
actual gameplay content, virtual resolution + letterboxing, input, physics,
etc.

For professional video game programming tools (level editors, sprite tools,
animation editors, etc.) the recommended approach is Dear PyGui in the tool
process. A real tool can host a live Grimoire2D game preview by rendering
to an offscreen texture (via moderngl) and displaying the result in a
dpg texture widget.

Run with:
    python -m demos.editor_mockup

Requires: dearpygui (pip install dearpygui  or  pip install -e '.[tools]')
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


import dearpygui.dearpygui as dpg


# ---------------------------------------------------------------------------
# Theme colors (approximating the prior dark editor palette)
# ---------------------------------------------------------------------------

C_BG = (45, 45, 45, 255)
C_PANEL = (55, 55, 55, 255)
C_PANEL_HDR = (40, 40, 40, 255)
C_BORDER = (35, 35, 35, 255)
C_BTN = (70, 70, 70, 255)
C_BTN_HOV = (90, 90, 90, 255)
C_BTN_ACT = (50, 50, 50, 255)
C_ACCENT = (60, 120, 190, 255)
C_TEXT = (220, 220, 220, 255)
C_TEXT_DIM = (140, 140, 140, 255)
C_CANVAS = (100, 100, 100, 255)
C_GRID = (80, 80, 80, 255)
C_SEL = (60, 120, 190, 90)

_MENU_ITEMS = ["File", "Edit", "View", "Map", "Layer", "Tileset", "Help"]
_TOOL_NAMES = ["Pen", "Erase", "Fill", "Select", "Rect", "Pick", "Stamp", "Line"]


@dataclass
class EditorState:
    """Simple mutable state for the mock editor (immediate-mode friendly)."""

    active_tool: int = 0
    active_layer: int = 3
    selected_tiles: set[int] = field(default_factory=lambda: {3, 7, 14})
    # Demo "placed" tiles on the canvas: list of (tile_index, grid_x, grid_y)
    placed: list[tuple[int, int, int]] = field(default_factory=list)
    frame: int = 0
    status_text: str = "Ready"
    last_mouse: tuple[int, int] = (0, 0)
    tile_size: int = 16
    grid_offset: tuple[int, int] = (280, 116)


def _tile_color(idx: int) -> tuple[int, int, int, int]:
    """Stable pseudo-random colour for a tileset swatch (0-255)."""
    hue = (idx * 37) % 360
    h = hue / 60.0
    i = int(h)
    f = h - i
    p = int(0.55 * (1.0 - 0.55) * 255)
    q = int(0.55 * (1.0 - 0.55 * f) * 255)
    t = int(0.55 * (1.0 - 0.55 * (1.0 - f)) * 255)
    v = int(0.55 * 255)
    segs = [
        (v, t, p),
        (q, v, p),
        (p, v, t),
        (p, q, v),
        (t, p, v),
        (v, p, q),
    ]
    r, g, b = segs[i % 6]
    return (r, g, b, 255)


def _update_preview_texture(
    tag: str, frame: int, width: int = 86, height: int = 50
) -> None:
    """Animate a simple wave pattern into a raw texture for the Preview pane.
    Values are float [0..1] for mvFormat_Float_rgba.
    """
    pixels: list[float] = []
    t = frame * 0.04
    for y in range(height):
        wave = math.sin(t + y * 0.18) * 0.5 + 0.5
        wave2 = math.sin(t * 1.3 + y * 0.09 + 1.0) * 0.5 + 0.5
        r = (wave * 200 + 30) / 255.0
        g = (wave2 * 160 + 30) / 255.0
        b = ((1.0 - wave) * 180 + 40) / 255.0
        for _ in range(width):
            pixels.extend([r, g, b, 1.0])
    dpg.set_value(tag, pixels)


def _build_theme() -> None:
    """Create and apply a dark, compact editor theme."""
    with dpg.theme() as editor_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, C_BG)
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, C_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, C_PANEL_HDR)
            dpg.add_theme_color(dpg.mvThemeCol_Header, C_ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (*C_ACCENT[:3], 200))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, C_ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_Button, C_BTN)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, C_BTN_HOV)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, C_BTN_ACT)
            dpg.add_theme_color(dpg.mvThemeCol_Text, C_TEXT)
            dpg.add_theme_color(dpg.mvThemeCol_Border, C_BORDER)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 0)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 2)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 2)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 4, 4)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 4, 4)
    dpg.bind_theme(editor_theme)


def _menu_bar(state: EditorState) -> None:
    with dpg.menu_bar():
        for label in _MENU_ITEMS:
            with dpg.menu(label=label):
                if label == "File":
                    dpg.add_menu_item(
                        label="New Map", callback=lambda: _log_action(state, "New Map")
                    )
                    dpg.add_menu_item(
                        label="Open...", callback=lambda: _log_action(state, "Open")
                    )
                    dpg.add_menu_item(
                        label="Save", callback=lambda: _log_action(state, "Save")
                    )
                    dpg.add_separator()
                    dpg.add_menu_item(
                        label="Exit", callback=lambda: dpg.stop_dearpygui()
                    )
                elif label == "Edit":
                    dpg.add_menu_item(
                        label="Undo", callback=lambda: _log_action(state, "Undo")
                    )
                    dpg.add_menu_item(
                        label="Redo", callback=lambda: _log_action(state, "Redo")
                    )
                    dpg.add_separator()
                    dpg.add_menu_item(
                        label="Cut", callback=lambda: _log_action(state, "Cut")
                    )
                    dpg.add_menu_item(
                        label="Copy", callback=lambda: _log_action(state, "Copy")
                    )
                    dpg.add_menu_item(
                        label="Paste", callback=lambda: _log_action(state, "Paste")
                    )
                else:
                    dpg.add_menu_item(
                        label=f"{label} (stub)",
                        callback=lambda s=label: _log_action(state, s),
                    )


def _log_action(state: EditorState, action: str) -> None:
    state.status_text = f"{action} (demo)"
    # Will be visible on next frame in status bar


def _toolbar(state: EditorState) -> None:
    with dpg.group(horizontal=True):
        for idx, name in enumerate(_TOOL_NAMES):
            is_active = idx == state.active_tool
            # Use small selectable buttons with short labels / symbols
            label = name[:1]  # single letter icon substitute
            btn = dpg.add_button(
                label=label,
                width=26,
                height=22,
                callback=lambda s, a, u, i=idx: _select_tool(state, i),
            )
            if is_active:
                dpg.bind_item_theme(btn, _active_tool_theme())
        dpg.add_spacer(width=8)
        dpg.add_separator()
        dpg.add_spacer(width=8)
        dpg.add_text("Grimoire2D + Dear PyGui Editor Mockup", color=C_TEXT_DIM)


_active_tool_theme_cache: int | None = None


def _active_tool_theme() -> int:
    global _active_tool_theme_cache
    if _active_tool_theme_cache is not None:
        return _active_tool_theme_cache
    with dpg.theme() as th:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, C_ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (*C_ACCENT[:3], 220))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, C_ACCENT)
    _active_tool_theme_cache = th
    return th


def _select_tool(state: EditorState, idx: int) -> None:
    state.active_tool = idx
    state.status_text = f"Tool: {_TOOL_NAMES[idx]}"


def _left_sidebar(state: EditorState, preview_tex: str) -> None:
    with dpg.child_window(width=180, height=-1, border=True):
        dpg.add_text("Tools", color=C_TEXT)
        dpg.add_separator()

        # Tool grid (2 columns)
        with dpg.group(horizontal=True):
            for col in range(2):
                with dpg.group():
                    for row in range(4):
                        idx = row * 2 + col
                        if idx >= len(_TOOL_NAMES):
                            break
                        name = _TOOL_NAMES[idx]
                        is_active = idx == state.active_tool
                        btn = dpg.add_button(
                            label=name,
                            width=76,
                            height=36,
                            callback=lambda s, a, u, i=idx: _select_tool(state, i),
                        )
                        if is_active:
                            dpg.bind_item_theme(btn, _active_tool_theme())

        dpg.add_spacer(height=12)
        dpg.add_text("Preview", color=C_TEXT)
        dpg.add_separator()

        # Preview area using the animated texture
        with dpg.child_window(width=172, height=100, border=True, no_scrollbar=True):
            dpg.add_image(preview_tex, width=170, height=98)


def _canvas_drawlist(state: EditorState, tag: str, width: int, height: int) -> None:
    """Draw the tile grid + placed tiles + selection into a drawlist."""
    dpg.delete_item(tag, children_only=True)

    grid_ox, grid_oy = state.grid_offset
    ts = state.tile_size
    cols, rows = 24, 20

    # Background
    dpg.draw_rectangle(
        (0, 0), (width, height), color=C_CANVAS, fill=C_CANVAS, parent=tag
    )

    # Tiles + grid
    for row in range(rows):
        for col in range(cols):
            tx = grid_ox + col * ts
            ty = grid_oy + row * ts
            fill = (60, 60, 60, 255) if (col + row) % 2 == 0 else (65, 65, 65, 255)
            dpg.draw_rectangle(
                (tx, ty), (tx + ts, ty + ts), color=fill, fill=fill, parent=tag
            )

    # Grid lines
    for col in range(cols + 1):
        x = grid_ox + col * ts
        dpg.draw_line(
            (x, grid_oy),
            (x, grid_oy + rows * ts),
            color=C_GRID,
            thickness=1,
            parent=tag,
        )
    for row in range(rows + 1):
        y = grid_oy + row * ts
        dpg.draw_line(
            (grid_ox, y),
            (grid_ox + cols * ts, y),
            color=C_GRID,
            thickness=1,
            parent=tag,
        )

    # Placed demo tiles (simple filled rects)
    for tidx, gx, gy in state.placed:
        tx = grid_ox + gx * ts
        ty = grid_oy + gy * ts
        col = _tile_color(tidx)
        dpg.draw_rectangle(
            (tx + 1, ty + 1),
            (tx + ts - 1, ty + ts - 1),
            color=col,
            fill=col,
            parent=tag,
        )

    # Selection rectangle (demo)
    sel_x = grid_ox + 2 * ts
    sel_y = grid_oy + 2 * ts
    sel_size = 3 * ts
    dpg.draw_rectangle(
        (sel_x, sel_y),
        (sel_x + sel_size, sel_y + sel_size),
        color=C_SEL,
        fill=C_SEL,
        parent=tag,
    )
    dpg.draw_rectangle(
        (sel_x, sel_y),
        (sel_x + sel_size, sel_y + sel_size),
        color=C_ACCENT,
        thickness=2,
        parent=tag,
    )


def _on_canvas_click(state: EditorState, canvas_tag: str) -> None:
    """Handle clicks inside the canvas to demonstrate painting / picking."""
    if not dpg.is_item_hovered(canvas_tag):
        return
    mx, my = dpg.get_mouse_pos(local=False)
    # Approximate mapping from window coords into the drawn grid area.
    # (Good enough for a visual mock; a real tool would use its own layout math.)
    gx = int((mx - 280) // state.tile_size)
    gy = int((my - 160) // state.tile_size)  # accounts for menu+toolbar roughly
    gx = max(0, min(23, gx))
    gy = max(0, min(19, gy))

    if state.active_tool in (0, 6):  # Pen / Stamp
        tid = next(iter(state.selected_tiles)) if state.selected_tiles else 0
        existing = [p for p in state.placed if p[1:] == (gx, gy)]
        if existing:
            state.placed = [p for p in state.placed if p[1:] != (gx, gy)]
        else:
            state.placed.append((tid, gx, gy))
        state.status_text = f"Placed tile {tid} @ ({gx},{gy})"
    elif state.active_tool == 1:  # Erase
        state.placed = [p for p in state.placed if p[1:] != (gx, gy)]
        state.status_text = f"Erased @ ({gx},{gy})"
    elif state.active_tool == 5:  # Pick
        for tid, px, py in state.placed:
            if px == gx and py == gy:
                state.selected_tiles = {tid}
                state.status_text = f"Picked tile {tid}"
                return
        tid = (gy * 10 + gx) % 80
        state.selected_tiles = {tid}
        state.status_text = f"Picked tile {tid}"
    else:
        state.status_text = (
            f"Tool action: {_TOOL_NAMES[state.active_tool]} @ ({gx},{gy})"
        )


def _build_canvas(state: EditorState) -> tuple[str, str]:
    """Create the canvas child + drawlist. Returns (canvas_tag, drawlist_tag)."""
    canvas_tag = dpg.generate_uuid()
    draw_tag = dpg.generate_uuid()

    with dpg.child_window(
        tag=canvas_tag,
        width=-1,
        height=-1,
        border=True,
        no_scrollbar=True,
    ):
        dpg.add_drawlist(width=720, height=520, tag=draw_tag)

    # Initial draw
    _canvas_drawlist(state, draw_tag, 720, 520)

    return canvas_tag, draw_tag


def _update_status_from_mouse(state: EditorState) -> None:
    if dpg.is_dearpygui_running():
        mx, my = dpg.get_mouse_pos(local=False)
        state.last_mouse = (int(mx), int(my))


def _layers_panel(state: EditorState) -> None:
    with dpg.child_window(width=360, height=348, border=True):
        with dpg.group(horizontal=True):
            dpg.add_text("Layers", color=C_TEXT)
            dpg.add_spacer(width=180)
            if dpg.add_button(
                label="+",
                width=14,
                height=14,
                callback=lambda: _log_action(state, "Add layer"),
            ):
                pass
            if dpg.add_button(
                label="-",
                width=14,
                height=14,
                callback=lambda: _log_action(state, "Remove layer"),
            ):
                pass

        dpg.add_separator()

        layer_names = ["Collision", "Objects", "Foreground", "Tiles", "Background"]
        swatch_colors = [
            (230, 77, 77, 255),
            (77, 204, 128, 255),
            (128, 128, 230, 255),
            (230, 179, 77, 255),
            (128, 77, 179, 255),
        ]

        for i, name in enumerate(layer_names):
            is_active = i == state.active_layer
            with dpg.group(horizontal=True):
                # Color swatch as small colored quad
                sw = dpg.add_drawlist(width=16, height=16)
                dpg.draw_rectangle(
                    (0, 0),
                    (16, 16),
                    color=swatch_colors[i],
                    fill=swatch_colors[i],
                    parent=sw,
                )
                # Selectable row
                sel = dpg.add_selectable(
                    label=name,
                    default_value=is_active,
                    width=-1,
                    callback=lambda s, a, u, idx=i: _select_layer(state, idx),
                )
                if is_active:
                    dpg.bind_item_theme(sel, _accent_selectable_theme())


_accent_sel_theme: int | None = None


def _accent_selectable_theme() -> int:
    global _accent_sel_theme
    if _accent_sel_theme is not None:
        return _accent_sel_theme
    with dpg.theme() as th:
        with dpg.theme_component(dpg.mvSelectable):
            dpg.add_theme_color(dpg.mvThemeCol_Header, (*C_ACCENT[:3], 64))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (*C_ACCENT[:3], 120))
    _accent_sel_theme = th
    return th


def _select_layer(state: EditorState, idx: int) -> None:
    state.active_layer = idx
    state.status_text = (
        f"Layer: {['Collision', 'Objects', 'Foreground', 'Tiles', 'Background'][idx]}"
    )


def _tileset_panel(state: EditorState) -> None:
    """Tileset grid implemented with a drawlist + click handler for robust layout."""
    with dpg.child_window(width=360, height=-1, border=True):
        dpg.add_text("Tileset", color=C_TEXT)
        dpg.add_separator()

        ts_w = 28
        ts_h = 24
        gap = 4
        cols = 10
        rows = 8
        margin = 6

        tileset_tag = dpg.generate_uuid()
        dlw = margin * 2 + cols * (ts_w + gap) - gap
        dlh = margin * 2 + rows * (ts_h + gap) - gap

        dpg.add_drawlist(width=dlw, height=dlh, tag=tileset_tag)

        def _redraw_tileset() -> None:
            dpg.delete_item(tileset_tag, children_only=True)
            for idx in range(cols * rows):
                col = idx % cols
                row = idx // cols
                sx = margin + col * (ts_w + gap)
                sy = margin + row * (ts_h + gap)
                col4 = _tile_color(idx)
                # filled rect
                dpg.draw_rectangle(
                    (sx, sy),
                    (sx + ts_w, sy + ts_h),
                    color=col4,
                    fill=col4,
                    parent=tileset_tag,
                )
                if idx in state.selected_tiles:
                    dpg.draw_rectangle(
                        (sx - 1, sy - 1),
                        (sx + ts_w + 1, sy + ts_h + 1),
                        color=C_ACCENT,
                        thickness=2,
                        parent=tileset_tag,
                    )

        # Stash redraw + geometry so render loop can handle clicks + refresh highlights
        state._tileset_redraw = _redraw_tileset  # type: ignore[attr-defined]
        state._tileset_geom = (tileset_tag, margin, ts_w, ts_h, gap, cols, rows)  # type: ignore[attr-defined]


def _select_tile(state: EditorState, idx: int) -> None:
    if dpg.is_key_down(dpg.mvKey_Control):
        if idx in state.selected_tiles:
            state.selected_tiles.remove(idx)
        else:
            state.selected_tiles.add(idx)
    else:
        state.selected_tiles = {idx}
    state.status_text = f"Selected tile(s): {sorted(state.selected_tiles)}"


def _status_bar(state: EditorState) -> None:
    with dpg.group(horizontal=True):
        dpg.add_text("Virtual: 1280×720  |  ", color=C_TEXT_DIM)
        dpg.add_text("Pos: 0, 0  |  ", tag="status_pos", color=C_TEXT_DIM)
        dpg.add_text("Tile: 0, 0  |  ", tag="status_tile", color=C_TEXT_DIM)
        dpg.add_text("Scale: 1.00×  |  ", color=C_TEXT_DIM)
        dpg.add_text(tag="status_msg", color=C_TEXT_DIM)


def _update_status_labels(state: EditorState) -> None:
    x, y = state.last_mouse
    dpg.set_value("status_pos", f"Pos: {x}, {y}  |  ")
    # Rough tile calc from last known grid
    gx = int((x - state.grid_offset[0]) // state.tile_size)
    gy = int((y - state.grid_offset[1]) // state.tile_size)
    dpg.set_value("status_tile", f"Tile: {max(0, gx)}, {max(0, gy)}  |  ")
    dpg.set_value("status_msg", state.status_text)


def _on_render(
    state: EditorState, draw_tag: str, preview_tex: str, canvas_tag: str
) -> None:
    """Called every frame to keep draw content and animation fresh."""
    state.frame += 1
    _canvas_drawlist(state, draw_tag, 720, 520)

    # Tileset click + refresh (poll to avoid handler quirks on drawlists)
    geom = getattr(state, "_tileset_geom", None)
    redraw = getattr(state, "_tileset_redraw", None)
    if geom and redraw and dpg.is_mouse_button_clicked(dpg.mvMouseButton_Left):
        tag, margin, tw, th, gap, tcols, trows = geom
        if dpg.is_item_hovered(tag):
            mx, my = dpg.get_mouse_pos(local=True)
            rel_x = mx - margin
            rel_y = my - margin
            if rel_x >= 0 and rel_y >= 0:
                c = int(rel_x // (tw + gap))
                r = int(rel_y // (th + gap))
                if 0 <= c < tcols and 0 <= r < trows:
                    idx = r * tcols + c
                    _select_tile(state, idx)
                    redraw()
    if redraw:
        redraw()

    if state.frame % 2 == 0:
        _update_preview_texture(preview_tex, state.frame)
    _update_status_labels(state)

    # Drive canvas painting on drag/click too (left button held or just clicked)
    if dpg.is_mouse_button_down(dpg.mvMouseButton_Left) or dpg.is_mouse_button_clicked(
        dpg.mvMouseButton_Left
    ):
        _on_canvas_click(state, canvas_tag)


def main() -> None:
    """Launch the Dear PyGui editor mockup."""
    dpg.create_context()
    dpg.create_viewport(
        title="Grimoire2D — Editor Mockup (Dear PyGui)",
        width=1280,
        height=760,
        resizable=True,
    )
    dpg.setup_dearpygui()
    _build_theme()

    state = EditorState()

    # Animated preview texture (raw RGBA floats [0..1])
    preview_tag = dpg.generate_uuid()
    preview_w, preview_h = 86, 50
    initial_pixels = [0.7, 0.7, 0.7, 1.0] * (preview_w * preview_h)
    with dpg.texture_registry(show=False):
        dpg.add_raw_texture(
            width=preview_w,
            height=preview_h,
            default_value=initial_pixels,
            format=dpg.mvFormat_Float_rgba,
            tag=preview_tag,
        )
    _update_preview_texture(preview_tag, 0, preview_w, preview_h)

    # Main editor window that fills most of the viewport
    with dpg.window(
        tag="main_editor",
        label="",
        no_title_bar=True,
        no_move=True,
        no_resize=True,
        no_collapse=True,
        no_close=True,
        pos=(0, 0),
        width=1280,
        height=720,
    ):
        _menu_bar(state)
        _toolbar(state)

        # Content area: 3-column split using a table (left / canvas / right)
        with dpg.table(
            header_row=False, resizable=True, policy=dpg.mvTable_SizingStretchProp
        ):
            dpg.add_table_column(init_width_or_weight=0.14)
            dpg.add_table_column(init_width_or_weight=0.58)
            dpg.add_table_column(init_width_or_weight=0.28)

            with dpg.table_row():
                with dpg.table_cell():
                    _left_sidebar(state, preview_tag)

                with dpg.table_cell():
                    canvas_tag, draw_tag = _build_canvas(state)

                with dpg.table_cell():
                    _layers_panel(state)
                    dpg.add_spacer(height=4)
                    _tileset_panel(state)

        # Status bar area
        dpg.add_separator()
        _status_bar(state)

    # Optional: keep main content roughly sized to viewport (best effort for demo)
    def _resize_main() -> None:
        w = dpg.get_viewport_client_width()
        h = dpg.get_viewport_client_height()
        dpg.set_item_width("main_editor", max(800, w))
        dpg.set_item_height("main_editor", max(600, h - 20))

    dpg.set_viewport_resize_callback(_resize_main)

    dpg.show_viewport()

    # Manual render loop so we can drive per-frame updates for drawlist + status + interactions
    while dpg.is_dearpygui_running():
        _on_render(state, draw_tag, preview_tag, canvas_tag)
        dpg.render_dearpygui_frame()

    dpg.destroy_context()


if __name__ == "__main__":
    main()
