"""Scene and Actor system demo.

Cycles through four scenes demonstrating the SceneGraph API live.
Uses GameWindow for display — all drawing is in the fixed 1280×720
virtual coordinate space; the engine handles scaling, centering, and
letterboxing for the user's actual display automatically.

Controls
--------
  ← →    navigate between scenes
  D       (gameplay) destroy one enemy — watch the query counter drop
  R       (gameplay) respawn all enemies
  ↑ ↓    (options) select option row
  ESC     quit

Scenes
------
  SPLASH     logo animates in; auto-advances after ~4 s
  TITLE      three decoration actors orbit the title text
  GAMEPLAY   player / enemy / pickup actors with live query HUD
  OPTIONS    mock menu with three selectable option actors
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pygame

from grimoire2d.presentation.window import GameWindow
from grimoire2d.models.components import TransformComponent
from grimoire2d.models.scene_graph import SceneGraph
from grimoire2d.logic.scene_ops import (
    create_scene,
    set_active_scene,
    spawn_actor,
    destroy_actor,
    query_actors,
    get_actor,
    get_component,
    update_component,
)

# ---------------------------------------------------------------------------
# Virtual coordinate space constants  (engine scales these to any display)
# ---------------------------------------------------------------------------

VW = 1280.0  # virtual width
VH = 720.0  # virtual height
VCX = 640.0  # virtual centre x
VCY = 360.0  # virtual centre y

# ---------------------------------------------------------------------------
# Text helpers  (Renderer.draw_text has no align= param)
# ---------------------------------------------------------------------------


def _text(r, text, x, y, *, color=(1.0, 1.0, 1.0, 1.0), fs=22):
    r.draw_text(text, x, y, color=color, font_size=fs)


def _text_c(r, text, cx, y, *, color=(1.0, 1.0, 1.0, 1.0), fs=22):
    w, _ = r.measure_text(text, font_size=fs)
    r.draw_text(text, cx - w * 0.5, y, color=color, font_size=fs)


def _text_r(r, text, rx, y, *, color=(1.0, 1.0, 1.0, 1.0), fs=22):
    w, _ = r.measure_text(text, font_size=fs)
    r.draw_text(text, rx - w, y, color=color, font_size=fs)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _rotate(pts, cx, cy, angle):
    c, s = math.cos(angle), math.sin(angle)
    return [
        (cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c)
        for x, y in pts
    ]


def _ngon(cx, cy, r, n, angle_offset=0.0):
    step = 2 * math.pi / n
    return [
        (
            cx + r * math.cos(i * step + angle_offset),
            cy + r * math.sin(i * step + angle_offset),
        )
        for i in range(n)
    ]


def _arrow(cx, cy, r, angle):
    pts = [
        (cx, cy - r),
        (cx + r * 0.55, cy + r * 0.7),
        (cx, cy + r * 0.25),
        (cx - r * 0.55, cy + r * 0.7),
    ]
    return _rotate(pts, cx, cy, angle)


def _diamond(cx, cy, r, angle):
    pts = [(cx, cy - r), (cx + r * 0.55, cy), (cx, cy + r), (cx - r * 0.55, cy)]
    return _rotate(pts, cx, cy, angle)


# ---------------------------------------------------------------------------
# Scene population  (all coordinates in the 1280×720 virtual space)
# ---------------------------------------------------------------------------


def _build_graph() -> tuple[SceneGraph, dict[str, str]]:
    g = SceneGraph()
    ids: dict[str, str] = {}

    g, sid = create_scene(g, "Splash", scene_id="splash")
    ids["splash"] = sid

    g, sid = create_scene(g, "Title", scene_id="title")
    ids["title"] = sid
    for i in range(3):
        g, _ = spawn_actor(
            g,
            sid,
            tags=frozenset({"decoration", "background"}),
            components={"transform": TransformComponent(x=VCX, y=VCY)},
            actor_id=f"deco_{i}",
        )

    g, sid = create_scene(g, "Gameplay", scene_id="gameplay")
    ids["gameplay"] = sid
    g, _ = spawn_actor(
        g,
        sid,
        tags=frozenset({"player", "dynamic"}),
        components={"transform": TransformComponent(x=VCX, y=VCY)},
        actor_id="player_0",
    )
    for i in range(3):
        r = 110 + i * 65
        a0 = i * (2 * math.pi / 3)
        g, _ = spawn_actor(
            g,
            sid,
            tags=frozenset({"enemy", "dynamic"}),
            components={
                "transform": TransformComponent(
                    x=VCX + math.cos(a0) * r, y=VCY + math.sin(a0) * r
                )
            },
            actor_id=f"enemy_{i}",
        )
    for i in range(2):
        g, _ = spawn_actor(
            g,
            sid,
            tags=frozenset({"pickup", "static"}),
            components={
                "transform": TransformComponent(x=VW * (0.28 + i * 0.44), y=VH * 0.72)
            },
            actor_id=f"pickup_{i}",
        )

    g, sid = create_scene(g, "Options", scene_id="options")
    ids["options"] = sid
    for i in range(3):
        g, _ = spawn_actor(
            g,
            sid,
            tags=frozenset({"menu_item"}),
            components={
                "transform": TransformComponent(x=VCX, y=VH * (0.38 + i * 0.14))
            },
            actor_id=f"opt_{i}",
        )

    g = set_active_scene(g, ids["splash"])
    return g, ids


# ---------------------------------------------------------------------------
# Per-frame transform updates
# ---------------------------------------------------------------------------


def _update_title_actors(graph, frame):
    for i in range(3):
        aid = f"deco_{i}"
        if get_actor(graph, aid) is None:
            continue
        r = 160 + i * 45
        angle = frame * (0.008 + i * 0.004) + i * (2 * math.pi / 3)
        graph = update_component(
            graph,
            aid,
            "transform",
            TransformComponent(
                x=VCX + math.cos(angle) * r,
                y=VCY + math.sin(angle) * r,
                angle=angle * 2.5,
            ),
        )
    return graph


def _update_gameplay_actors(graph, frame):
    # Player: figure-8 (lemniscate)
    t = frame * 0.022
    denom = 1 + math.sin(t) ** 2 + 1e-6
    px = VCX + (200 * math.cos(t)) / denom
    py = VCY + (180 * math.sin(t) * math.cos(t)) / denom
    graph = update_component(
        graph,
        "player_0",
        "transform",
        TransformComponent(x=px, y=py, angle=t + math.pi * 0.5),
    )

    for i in range(3):
        if get_actor(graph, f"enemy_{i}") is None:
            continue
        r = 110 + i * 65
        angle = frame * (0.016 + i * 0.009) + i * (2 * math.pi / 3)
        graph = update_component(
            graph,
            f"enemy_{i}",
            "transform",
            TransformComponent(
                x=VCX + math.cos(angle) * r,
                y=VCY + math.sin(angle) * r,
                angle=angle * 2,
            ),
        )

    for i in range(2):
        if get_actor(graph, f"pickup_{i}") is None:
            continue
        bx = VW * (0.28 + i * 0.44) + math.sin(frame * 0.03 + i * math.pi) * 18
        by = VH * 0.72 + math.cos(frame * 0.02 + i * math.pi) * 10
        graph = update_component(
            graph,
            f"pickup_{i}",
            "transform",
            TransformComponent(x=bx, y=by, angle=frame * 0.04 + i * math.pi),
        )

    return graph


# ---------------------------------------------------------------------------
# Per-scene drawing  (all coordinates are virtual pixels)
# ---------------------------------------------------------------------------


def _draw_splash(r, scene_frame):
    for i in range(4):
        r.draw_circle(VCX, VCY, 280 - i * 50, (0.18, 0.08, 0.38, 0.03 + i * 0.01))

    ease = 1 - (1 - min(scene_frame / 48.0, 1.0)) ** 3
    _text_c(r, "GRIMOIRE 2D", VCX, VCY - 24, color=(0.82, 0.55, 1.0, ease), fs=66)
    _text_c(
        r,
        "Scene & Actor System Demo",
        VCX,
        VCY + 30,
        color=(0.7, 0.7, 0.92, max(0.0, ease - 0.4) / 0.6),
        fs=22,
    )

    progress = min(scene_frame / 240.0, 1.0)
    r.draw_rect(VCX - 130, VH - 42, 260, 4, (0.25, 0.25, 0.38, 0.55))
    if progress > 0:
        r.draw_rect(VCX - 130, VH - 42, 260 * progress, 4, (0.7, 0.45, 1.0, 0.9))
    _text_c(
        r,
        "Auto-advancing...   right arrow to skip",
        VCX,
        VH - 58,
        color=(0.5, 0.5, 0.65, 0.75),
        fs=15,
    )


def _draw_title(r, graph, frame):
    actors = sorted(
        query_actors(graph, scene_id="title", tags={"decoration"}),
        key=lambda a: a.actor_id,
    )
    shapes = [5, 6, 3]
    colors = [(0.6, 0.2, 0.9, 0.4), (0.2, 0.5, 0.9, 0.32), (0.9, 0.35, 0.2, 0.32)]
    for i, actor in enumerate(actors):
        tf = get_component(graph, actor.actor_id, "transform")
        if tf is None:
            continue
        pts = _ngon(tf.x, tf.y, 52 + i * 20, shapes[i], tf.angle)
        r.draw_polygon(pts, colors[i % len(colors)])

    blink = 0.45 + 0.55 * abs(math.sin(frame * 0.05))
    _text_c(r, "DUNGEON QUEST", VCX, VCY - 16, color=(1.0, 0.86, 0.3, 1.0), fs=58)
    _text_c(
        r, "A Grimoire 2D Demo", VCX, VCY + 34, color=(0.72, 0.65, 0.85, 0.82), fs=20
    )
    _text_c(
        r,
        "Press  right arrow  to begin",
        VCX,
        VCY + 76,
        color=(0.82, 0.82, 1.0, blink),
        fs=18,
    )
    _draw_scene_badge(r, "title", len(actors))


def _draw_gameplay(r, graph, frame):
    # Orbit-path rings
    for i in range(3):
        ri = 110 + i * 65
        r.draw_ring(VCX, VCY, ri + 1.5, ri - 1.5, (0.3, 0.3, 0.5, 0.16))

    # Pickups (gold diamonds)
    for actor in query_actors(graph, scene_id="gameplay", tags={"pickup"}):
        tf = get_component(graph, actor.actor_id, "transform")
        if tf:
            r.draw_polygon(_diamond(tf.x, tf.y, 14, tf.angle), (1.0, 0.85, 0.15, 0.92))
            r.draw_ring(tf.x, tf.y, 18, 14, (1.0, 0.85, 0.15, 0.3))

    # Enemies (red circles with inner triangle)
    enemies = query_actors(graph, scene_id="gameplay", tags={"enemy"})
    for actor in enemies:
        tf = get_component(graph, actor.actor_id, "transform")
        if tf:
            r.draw_circle(tf.x, tf.y, 20, (0.92, 0.18, 0.18, 1.0))
            r.draw_polygon(_ngon(tf.x, tf.y, 12, 3, tf.angle), (0.55, 0.06, 0.06, 0.6))

    # Player (blue arrow)
    for actor in query_actors(graph, scene_id="gameplay", tags={"player"}):
        tf = get_component(graph, actor.actor_id, "transform")
        if tf:
            r.draw_polygon(_arrow(tf.x, tf.y, 26, tf.angle), (0.22, 0.62, 1.0, 1.0))
            r.draw_circle(tf.x, tf.y, 8, (0.45, 0.82, 1.0, 0.45))

    # Player transform readout
    players = query_actors(graph, scene_id="gameplay", tags={"player"})
    if players:
        tf = get_component(graph, players[0].actor_id, "transform")
        if tf:
            _text(
                r,
                f"transform   x={tf.x:+.1f}   y={tf.y:+.1f}   angle={tf.angle:.2f}",
                14,
                VH - 30,
                color=(0.45, 0.75, 1.0, 0.7),
                fs=14,
            )

    # Query HUD panel
    n_players = len(query_actors(graph, scene_id="gameplay", tags={"player"}))
    n_enemies = len(enemies)
    n_pickups = len(query_actors(graph, scene_id="gameplay", tags={"pickup"}))
    total = len(query_actors(graph, scene_id="gameplay"))

    px, py, pw, ph = VW - 282, 12, 270, 198
    r.draw_rect(px, py, pw, ph, (0.06, 0.06, 0.13, 0.90))

    row_h = 23.0
    tx, ty = px + 12, py + 12
    _text(r, "SCENE GRAPH", tx, ty, color=(0.75, 0.55, 1.0, 1.0), fs=15)
    ty += row_h * 0.8
    r.draw_rect(px + 8, ty, pw - 16, 1.5, (0.38, 0.38, 0.58, 0.6))
    ty += 8

    def _row(label, value, col, highlight=False):
        nonlocal ty
        if highlight:
            r.draw_rect(px + 4, ty - 2, pw - 8, row_h, (0.18, 0.10, 0.30, 0.55))
        _text(r, label, tx, ty, color=(0.65, 0.65, 0.82, 0.9), fs=13)
        _text_r(r, str(value), px + pw - 14, ty, color=col, fs=14)
        ty += row_h

    _row("Active scene:", "gameplay", (0.9, 0.9, 1.0, 1.0))
    _row("Total actors:", total, (0.82, 0.82, 0.94, 1.0))
    ty += 4
    _row('query({"player"})', f"-> {n_players}", (0.3, 0.72, 1.0, 1.0))
    _row('query({"enemy"})', f"-> {n_enemies}", (1.0, 0.32, 0.35, 1.0), highlight=True)
    _row('query({"pickup"})', f"-> {n_pickups}", (1.0, 0.85, 0.2, 1.0))
    ty += 4
    r.draw_rect(px + 8, ty, pw - 16, 1.5, (0.38, 0.38, 0.58, 0.4))
    ty += 8
    _text(
        r,
        "[D] destroy enemy   [R] respawn",
        tx,
        ty,
        color=(0.5, 0.5, 0.68, 0.75),
        fs=12,
    )

    _draw_scene_badge(r, "gameplay", total)


def _draw_options(r, graph, frame, selected_opt):
    _text_c(r, "OPTIONS", VCX, VCY - 130, color=(0.9, 0.9, 1.0, 1.0), fs=44)

    mock_labels = ["Volume", "Resolution", "Fullscreen"]
    mock_values = ["80%", "1920 x 1080", "ON"]
    actors = sorted(
        query_actors(graph, scene_id="options", tags={"menu_item"}),
        key=lambda a: a.actor_id,
    )

    for i, actor in enumerate(actors):
        iy = VH * (0.38 + i * 0.14)
        is_sel = i == selected_opt
        glow = 0.45 + 0.55 * abs(math.sin(frame * 0.07)) if is_sel else 0.0
        row_h, bx = 44.0, VCX - 200
        by = iy - row_h * 0.5
        if is_sel:
            r.draw_rect(bx - 10, by, 420, row_h, (0.28, 0.13, 0.5, 0.32 + glow * 0.12))
            r.draw_rect(bx - 10, by, 4, row_h, (0.75, 0.4, 1.0, 0.88))

        lc = (1.0, 0.9, 1.0, 1.0) if is_sel else (0.65, 0.65, 0.82, 0.88)
        vc = (0.85, 0.65, 1.0, 1.0) if is_sel else (0.5, 0.5, 0.72, 0.75)
        _text(r, mock_labels[i], bx + 14, iy - 9, color=lc, fs=20)
        _text_r(r, mock_values[i], VCX + 200, iy - 9, color=vc, fs=20)

    _draw_scene_badge(r, "options", len(query_actors(graph, scene_id="options")))
    _text_c(
        r,
        "up/down  select     left arrow  back",
        VCX,
        VH - 38,
        color=(0.5, 0.5, 0.65, 0.72),
        fs=16,
    )


# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------


def _draw_scene_badge(r, scene_name, actor_count):
    r.draw_rect(8, 8, 230, 28, (0.06, 0.06, 0.13, 0.88))
    _text(
        r,
        f"scene: {scene_name}  |  actors: {actor_count}",
        16,
        14,
        color=(0.6, 0.6, 0.82, 0.88),
        fs=14,
    )


def _draw_nav_dots(r, current_idx, total):
    dot_r, spacing = 5, 22
    start_x = VCX - (total - 1) * spacing * 0.5
    by = VH - 14
    for i in range(total):
        x = start_x + i * spacing
        if i == current_idx:
            r.draw_circle(x, by, dot_r, (0.75, 0.55, 1.0, 1.0))
        else:
            r.draw_ring(x, by, dot_r, dot_r - 2, (0.42, 0.42, 0.6, 0.6))


def _draw_nav_hints(r):
    _text_c(
        r,
        "left/right arrow  change scene     ESC  quit",
        VCX,
        VH - 34,
        color=(0.4, 0.4, 0.55, 0.65),
        fs=14,
    )


# ---------------------------------------------------------------------------
# Enemy respawn helper
# ---------------------------------------------------------------------------


def _respawn_enemies(graph):
    for i in range(3):
        graph = destroy_actor(graph, f"enemy_{i}")
    for i in range(3):
        r = 110 + i * 65
        a0 = i * (2 * math.pi / 3)
        graph, _ = spawn_actor(
            graph,
            "gameplay",
            tags=frozenset({"enemy", "dynamic"}),
            components={
                "transform": TransformComponent(
                    x=VCX + math.cos(a0) * r, y=VCY + math.sin(a0) * r
                )
            },
            actor_id=f"enemy_{i}",
        )
    return graph


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

SCENE_ORDER = ["splash", "title", "gameplay", "options"]
AUTO_ADVANCE_FRAMES = 240


def main() -> None:
    win = GameWindow(
        title="Scene & Actor Demo — Grimoire 2D",
        virtual_width=1280,
        virtual_height=720,
        target_fps=60,
    )

    graph, ids = _build_graph()
    scene_idx = 0
    scene_frame = 0
    frame = 0
    selected_opt = 0

    while win.is_open:
        current = SCENE_ORDER[scene_idx]

        # ------------------------------------------------------------------ #
        # Events
        # ------------------------------------------------------------------ #
        for event in win.poll():
            if event.type == pygame.QUIT:
                win.close()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    win.close()
                elif event.key == pygame.K_RIGHT:
                    scene_idx = (scene_idx + 1) % len(SCENE_ORDER)
                    scene_frame = 0
                    current = SCENE_ORDER[scene_idx]
                    graph = set_active_scene(graph, ids[current])
                elif event.key == pygame.K_LEFT:
                    scene_idx = (scene_idx - 1) % len(SCENE_ORDER)
                    scene_frame = 0
                    current = SCENE_ORDER[scene_idx]
                    graph = set_active_scene(graph, ids[current])
                elif event.key == pygame.K_d and current == "gameplay":
                    for i in range(3):
                        if get_actor(graph, f"enemy_{i}") is not None:
                            graph = destroy_actor(graph, f"enemy_{i}")
                            break
                elif event.key == pygame.K_r and current == "gameplay":
                    graph = _respawn_enemies(graph)
                elif event.key == pygame.K_UP and current == "options":
                    selected_opt = (selected_opt - 1) % 3
                elif event.key == pygame.K_DOWN and current == "options":
                    selected_opt = (selected_opt + 1) % 3

        # ------------------------------------------------------------------ #
        # Splash auto-advance
        # ------------------------------------------------------------------ #
        if current == "splash" and scene_frame >= AUTO_ADVANCE_FRAMES:
            scene_idx = 1
            scene_frame = 0
            current = SCENE_ORDER[scene_idx]
            graph = set_active_scene(graph, ids[current])

        # ------------------------------------------------------------------ #
        # Update transforms
        # ------------------------------------------------------------------ #
        if current == "title":
            graph = _update_title_actors(graph, frame)
        elif current == "gameplay":
            graph = _update_gameplay_actors(graph, frame)

        # ------------------------------------------------------------------ #
        # Render  (all draw calls use the 1280×720 virtual coordinate space)
        # ------------------------------------------------------------------ #
        win.begin_frame()
        win.renderer.draw_rect(0, 0, VW, VH, (0.055, 0.055, 0.09, 1.0))

        if current == "splash":
            _draw_splash(win.renderer, scene_frame)
        elif current == "title":
            _draw_title(win.renderer, graph, frame)
        elif current == "gameplay":
            _draw_gameplay(win.renderer, graph, frame)
        elif current == "options":
            _draw_options(win.renderer, graph, frame, selected_opt)

        _draw_nav_dots(win.renderer, scene_idx, len(SCENE_ORDER))
        _draw_nav_hints(win.renderer)
        win.end_frame()

        frame += 1
        scene_frame += 1

    win.quit()


if __name__ == "__main__":
    main()
