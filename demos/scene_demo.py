"""Scene and Actor system demo.

Cycles through four scenes that demonstrate the SceneGraph API live.
Actor positions update every frame via update_component(); the query
panel reflects the current graph state in real time.

Controls
--------
  ← →       navigate between scenes
  D         (gameplay only) destroy one enemy — watch the query counter drop
  R         (gameplay only) respawn all enemies
  ↑ ↓       (options only) select option row
  ESC       quit

Scenes
------
  SPLASH    logo animates in; auto-advances after ~4 s
  TITLE     three decoration actors orbit the title text
  GAMEPLAY  player / enemy / pickup actors with live query HUD
  OPTIONS   mock menu with three selectable option actors
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.presentation.highdpi import enable_highdpi, get_drawable_size
enable_highdpi()

import pygame
import moderngl

from grimoire2d.presentation.renderer import Renderer
from grimoire2d.models import VirtualResolution
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
# Geometry helpers
# ---------------------------------------------------------------------------

def _rotate(pts, cx, cy, angle):
    c, s = math.cos(angle), math.sin(angle)
    return [(cx + (x - cx) * c - (y - cy) * s,
             cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


def _ngon(cx, cy, r, n, angle_offset=0.0):
    step = 2 * math.pi / n
    return [(cx + r * math.cos(i * step + angle_offset),
             cy + r * math.sin(i * step + angle_offset)) for i in range(n)]


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
# Scene population
# ---------------------------------------------------------------------------

def _build_graph(lw: float, lh: float) -> tuple[SceneGraph, dict[str, str]]:
    """Build and return the initial SceneGraph plus a {name: scene_id} map."""
    g = SceneGraph()
    ids: dict[str, str] = {}
    s = lh / 720.0
    cx, cy = lw * 0.5, lh * 0.5

    # -- Splash (no actors needed) --
    g, sid = create_scene(g, "Splash", scene_id="splash")
    ids["splash"] = sid

    # -- Title: 3 decoration actors --
    g, sid = create_scene(g, "Title", scene_id="title")
    ids["title"] = sid
    for i in range(3):
        g, _ = spawn_actor(
            g, sid,
            tags=frozenset({"decoration", "background"}),
            components={"transform": TransformComponent(
                x=cx, y=cy, angle=i * (2 * math.pi / 3),
            )},
            actor_id=f"deco_{i}",
        )

    # -- Gameplay: player + 3 enemies + 2 pickups --
    g, sid = create_scene(g, "Gameplay", scene_id="gameplay")
    ids["gameplay"] = sid
    g, _ = spawn_actor(
        g, sid,
        tags=frozenset({"player", "dynamic"}),
        components={"transform": TransformComponent(x=cx, y=cy)},
        actor_id="player_0",
    )
    for i in range(3):
        r = (110 + i * 65) * s
        a0 = i * (2 * math.pi / 3)
        g, _ = spawn_actor(
            g, sid,
            tags=frozenset({"enemy", "dynamic"}),
            components={"transform": TransformComponent(
                x=cx + math.cos(a0) * r, y=cy + math.sin(a0) * r,
            )},
            actor_id=f"enemy_{i}",
        )
    for i in range(2):
        px = lw * (0.28 + i * 0.44)
        py = lh * 0.72
        g, _ = spawn_actor(
            g, sid,
            tags=frozenset({"pickup", "static"}),
            components={"transform": TransformComponent(x=px, y=py)},
            actor_id=f"pickup_{i}",
        )

    # -- Options: 3 menu-item actors --
    g, sid = create_scene(g, "Options", scene_id="options")
    ids["options"] = sid
    for i in range(3):
        g, _ = spawn_actor(
            g, sid,
            tags=frozenset({"menu_item"}),
            components={"transform": TransformComponent(
                x=cx, y=lh * (0.38 + i * 0.14),
            )},
            actor_id=f"opt_{i}",
        )

    g = set_active_scene(g, ids["splash"])
    return g, ids


# ---------------------------------------------------------------------------
# Per-frame transform updates
# ---------------------------------------------------------------------------

def _update_title_actors(graph: SceneGraph, frame: int,
                          lw: float, lh: float) -> SceneGraph:
    cx, cy = lw * 0.5, lh * 0.5
    for i in range(3):
        aid = f"deco_{i}"
        if get_actor(graph, aid) is None:
            continue
        r = (160 + i * 45) * (lh / 720)
        angle = frame * (0.008 + i * 0.004) + i * (2 * math.pi / 3)
        x = cx + math.cos(angle) * r
        y = cy + math.sin(angle) * r
        graph = update_component(
            graph, aid, "transform",
            TransformComponent(x=x, y=y, angle=angle * 2.5),
        )
    return graph


def _update_gameplay_actors(graph: SceneGraph, frame: int,
                             lw: float, lh: float) -> SceneGraph:
    s = lh / 720
    cx, cy = lw * 0.5, lh * 0.5

    # Player: figure-8 (lemniscate)
    t = frame * 0.022
    denom = 1 + math.sin(t) ** 2 + 1e-6
    px = cx + (200 * s * math.cos(t)) / denom
    py = cy + (180 * s * math.sin(t) * math.cos(t)) / denom
    pangle = t + math.pi * 0.5
    graph = update_component(
        graph, "player_0", "transform",
        TransformComponent(x=px, y=py, angle=pangle),
    )

    # Enemies
    for i in range(3):
        if get_actor(graph, f"enemy_{i}") is None:
            continue
        r = (110 + i * 65) * s
        angle = frame * (0.016 + i * 0.009) + i * (2 * math.pi / 3)
        ex = cx + math.cos(angle) * r
        ey = cy + math.sin(angle) * r
        graph = update_component(
            graph, f"enemy_{i}", "transform",
            TransformComponent(x=ex, y=ey, angle=angle * 2),
        )

    # Pickups: gentle bob + spin
    for i in range(2):
        if get_actor(graph, f"pickup_{i}") is None:
            continue
        base_x = lw * (0.28 + i * 0.44)
        base_y = lh * 0.72
        bx = base_x + math.sin(frame * 0.03 + i * math.pi) * 18 * s
        by = base_y + math.cos(frame * 0.02 + i * math.pi) * 10 * s
        graph = update_component(
            graph, f"pickup_{i}", "transform",
            TransformComponent(x=bx, y=by, angle=frame * 0.04 + i * math.pi),
        )

    return graph


# ---------------------------------------------------------------------------
# Per-scene drawing
# ---------------------------------------------------------------------------

def _draw_splash(r: Renderer, scene_frame: int, lw: float, lh: float,
                 s: float) -> None:
    cx, cy = lw * 0.5, lh * 0.5

    # Background glow
    for i in range(5):
        ri = (300 - i * 45) * s
        r.draw_circle(cx, cy, ri, (0.18, 0.08, 0.38, 0.03 + i * 0.01))

    # Animated logo
    t = min(scene_frame / 48.0, 1.0)
    ease = 1 - (1 - t) ** 3
    alpha = ease

    font_size = max(int(66 * s), 12)
    r.draw_text("GRIMOIRE 2D",
                cx, cy - 24 * s,
                color=(0.82, 0.55, 1.0, alpha),
                size=font_size, align="center")

    sub_alpha = max(0.0, ease - 0.4) / 0.6
    r.draw_text("Scene & Actor System Demo",
                cx, cy + 30 * s,
                color=(0.7, 0.7, 0.92, sub_alpha),
                size=int(22 * s), align="center")

    # Progress bar
    progress = min(scene_frame / 240.0, 1.0)
    bar_w, bar_h = 260 * s, 4 * s
    bx = cx - bar_w * 0.5
    by = lh - 42 * s
    r.draw_rect(bx, by, bar_w, bar_h, (0.25, 0.25, 0.38, 0.55))
    if progress > 0:
        r.draw_rect(bx, by, bar_w * progress, bar_h, (0.7, 0.45, 1.0, 0.9))

    r.draw_text("Auto-advancing…   → to skip",
                cx, by - 16 * s,
                color=(0.5, 0.5, 0.65, 0.75), size=int(15 * s), align="center")


def _draw_title(r: Renderer, graph: SceneGraph, frame: int,
                lw: float, lh: float, s: float) -> None:
    cx, cy = lw * 0.5, lh * 0.5
    actors = sorted(query_actors(graph, scene_id="title", tags={"decoration"}),
                    key=lambda a: a.actor_id)
    shapes = [5, 6, 3]
    colors = [(0.6, 0.2, 0.9, 0.4), (0.2, 0.5, 0.9, 0.32), (0.9, 0.35, 0.2, 0.32)]
    for i, actor in enumerate(actors):
        tf = get_component(graph, actor.actor_id, "transform")
        if tf is None:
            continue
        size = (52 + i * 20) * s
        pts = _ngon(tf.x, tf.y, size, shapes[i], tf.angle)
        r.draw_polygon(pts, colors[i % len(colors)])

    blink = 0.45 + 0.55 * abs(math.sin(frame * 0.05))
    r.draw_text("DUNGEON QUEST",
                cx, cy - 16 * s,
                color=(1.0, 0.86, 0.3, 1.0), size=int(58 * s), align="center")
    r.draw_text("A Grimoire 2D Demo",
                cx, cy + 34 * s,
                color=(0.72, 0.65, 0.85, 0.82), size=int(20 * s), align="center")
    r.draw_text("Press  →  to begin",
                cx, cy + 76 * s,
                color=(0.82, 0.82, 1.0, blink), size=int(18 * s), align="center")

    _draw_scene_badge(r, "title", len(actors), lw, lh, s)


def _draw_gameplay(r: Renderer, graph: SceneGraph, frame: int,
                   lw: float, lh: float, s: float) -> None:
    cx, cy = lw * 0.5, lh * 0.5

    # Orbit-path rings
    for i in range(3):
        ri = (110 + i * 65) * s
        r.draw_ring(cx, cy, ri + 1.5 * s, ri - 1.5 * s, (0.3, 0.3, 0.5, 0.16))

    # Pickups (gold diamonds)
    for actor in query_actors(graph, scene_id="gameplay", tags={"pickup"}):
        tf = get_component(graph, actor.actor_id, "transform")
        if tf:
            pts = _diamond(tf.x, tf.y, 14 * s, tf.angle)
            r.draw_polygon(pts, (1.0, 0.85, 0.15, 0.92))
            r.draw_ring(tf.x, tf.y, 18 * s, 14 * s, (1.0, 0.85, 0.15, 0.3))

    # Enemies (red circles with inner triangle)
    enemies = query_actors(graph, scene_id="gameplay", tags={"enemy"})
    for actor in enemies:
        tf = get_component(graph, actor.actor_id, "transform")
        if tf:
            r.draw_circle(tf.x, tf.y, 20 * s, (0.92, 0.18, 0.18, 1.0))
            tri = _ngon(tf.x, tf.y, 12 * s, 3, tf.angle)
            r.draw_polygon(tri, (0.55, 0.06, 0.06, 0.6))

    # Player (blue arrow)
    for actor in query_actors(graph, scene_id="gameplay", tags={"player"}):
        tf = get_component(graph, actor.actor_id, "transform")
        if tf:
            pts = _arrow(tf.x, tf.y, 26 * s, tf.angle)
            r.draw_polygon(pts, (0.22, 0.62, 1.0, 1.0))
            r.draw_circle(tf.x, tf.y, 8 * s, (0.45, 0.82, 1.0, 0.45))

    # Player transform readout
    players = query_actors(graph, scene_id="gameplay", tags={"player"})
    if players:
        tf = get_component(graph, players[0].actor_id, "transform")
        if tf:
            info = (f"transform  x={tf.x:+.1f}  y={tf.y:+.1f}"
                    f"  angle={tf.angle:.2f}")
            r.draw_text(info, 14 * s, lh - 30 * s,
                        color=(0.45, 0.75, 1.0, 0.7), size=int(14 * s))

    # Query HUD panel
    n_players = len(query_actors(graph, scene_id="gameplay", tags={"player"}))
    n_enemies = len(enemies)
    n_pickups = len(query_actors(graph, scene_id="gameplay", tags={"pickup"}))
    total = len(query_actors(graph, scene_id="gameplay"))

    pw, ph = 272 * s, 198 * s
    px, py = lw - pw - 12 * s, 12 * s
    r.draw_rect(px, py, pw, ph, (0.06, 0.06, 0.13, 0.90))

    lh_row = 23 * s
    tx, ty = px + 12 * s, py + 12 * s
    r.draw_text("SCENE GRAPH", tx, ty, color=(0.75, 0.55, 1.0, 1.0), size=int(15 * s))
    ty += lh_row * 0.8
    r.draw_rect(px + 8 * s, ty, pw - 16 * s, 1.5 * s, (0.38, 0.38, 0.58, 0.6))
    ty += 8 * s

    def _row(label, value, col, highlight=False):
        nonlocal ty
        if highlight:
            r.draw_rect(px + 4 * s, ty - 2 * s, pw - 8 * s, lh_row,
                        (0.18, 0.10, 0.30, 0.55))
        r.draw_text(label, tx, ty, color=(0.65, 0.65, 0.82, 0.9), size=int(13 * s))
        r.draw_text(str(value), px + pw - 14 * s, ty, color=col,
                    size=int(14 * s), align="right")
        ty += lh_row

    _row("Active scene:", "gameplay", (0.9, 0.9, 1.0, 1.0))
    _row("Total actors:", total, (0.82, 0.82, 0.94, 1.0))
    ty += 4 * s
    _row('query({"player"})', f"→ {n_players}", (0.3, 0.72, 1.0, 1.0))
    _row('query({"enemy"})',  f"→ {n_enemies}", (1.0, 0.32, 0.35, 1.0), highlight=True)
    _row('query({"pickup"})', f"→ {n_pickups}", (1.0, 0.85, 0.2, 1.0))
    ty += 4 * s
    r.draw_rect(px + 8 * s, ty, pw - 16 * s, 1.5 * s, (0.38, 0.38, 0.58, 0.4))
    ty += 8 * s
    r.draw_text("[D] destroy enemy   [R] respawn",
                tx, ty, color=(0.5, 0.5, 0.68, 0.75), size=int(12 * s))

    _draw_scene_badge(r, "gameplay", total, lw, lh, s)


def _draw_options(r: Renderer, graph: SceneGraph, frame: int,
                  lw: float, lh: float, s: float, selected_opt: int) -> None:
    cx, cy = lw * 0.5, lh * 0.5

    r.draw_text("OPTIONS",
                cx, cy - 130 * s,
                color=(0.9, 0.9, 1.0, 1.0), size=int(44 * s), align="center")

    mock_labels = ["Volume", "Resolution", "Fullscreen"]
    mock_values = ["80%", "1920 × 1080", "ON"]
    actors = sorted(query_actors(graph, scene_id="options", tags={"menu_item"}),
                    key=lambda a: a.actor_id)

    for i, actor in enumerate(actors):
        tf = get_component(graph, actor.actor_id, "transform")
        if tf is None:
            continue
        is_sel = (i == selected_opt)
        glow = 0.45 + 0.55 * abs(math.sin(frame * 0.07)) if is_sel else 0.0
        row_h = 44 * s
        bx = cx - 200 * s
        by = tf.y - row_h * 0.5
        if is_sel:
            r.draw_rect(bx - 10 * s, by, 420 * s, row_h,
                        (0.28, 0.13, 0.5, 0.32 + glow * 0.12))
            r.draw_rect(bx - 10 * s, by, 4 * s, row_h, (0.75, 0.4, 1.0, 0.88))

        lc = (1.0, 0.9, 1.0, 1.0) if is_sel else (0.65, 0.65, 0.82, 0.88)
        vc = (0.85, 0.65, 1.0, 1.0) if is_sel else (0.5, 0.5, 0.72, 0.75)
        r.draw_text(mock_labels[i], bx + 14 * s, tf.y - 9 * s,
                    color=lc, size=int(20 * s))
        r.draw_text(mock_values[i], cx + 200 * s, tf.y - 9 * s,
                    color=vc, size=int(20 * s), align="right")

    total = len(query_actors(graph, scene_id="options"))
    _draw_scene_badge(r, "options", total, lw, lh, s)
    r.draw_text("↑ ↓  select   ←  back",
                cx, lh - 38 * s,
                color=(0.5, 0.5, 0.65, 0.72), size=int(16 * s), align="center")


# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------

def _draw_scene_badge(r: Renderer, scene_name: str, actor_count: int,
                      lw: float, lh: float, s: float) -> None:
    r.draw_rect(8 * s, 8 * s, 222 * s, 28 * s, (0.06, 0.06, 0.13, 0.88))
    r.draw_text(f"scene: {scene_name}  |  actors: {actor_count}",
                16 * s, 14 * s,
                color=(0.6, 0.6, 0.82, 0.88), size=int(14 * s))


def _draw_nav_dots(r: Renderer, current_idx: int, total: int,
                   lw: float, lh: float, s: float) -> None:
    dot_r = 5 * s
    spacing = 22 * s
    start_x = lw * 0.5 - (total - 1) * spacing * 0.5
    by = lh - 18 * s
    for i in range(total):
        x = start_x + i * spacing
        if i == current_idx:
            r.draw_circle(x, by, dot_r, (0.75, 0.55, 1.0, 1.0))
        else:
            r.draw_ring(x, by, dot_r, dot_r - 2 * s, (0.42, 0.42, 0.6, 0.6))


def _draw_nav_hints(r: Renderer, lw: float, lh: float, s: float) -> None:
    r.draw_text("← →  change scene     ESC  quit",
                lw * 0.5, lh - 34 * s,
                color=(0.4, 0.4, 0.55, 0.65), size=int(14 * s), align="center")


# ---------------------------------------------------------------------------
# Enemy respawn helper
# ---------------------------------------------------------------------------

def _respawn_enemies(graph: SceneGraph, lw: float, lh: float) -> SceneGraph:
    s = lh / 720
    cx, cy = lw * 0.5, lh * 0.5
    for i in range(3):
        graph = destroy_actor(graph, f"enemy_{i}")
    for i in range(3):
        r = (110 + i * 65) * s
        a0 = i * (2 * math.pi / 3)
        graph, _ = spawn_actor(
            graph, "gameplay",
            tags=frozenset({"enemy", "dynamic"}),
            components={"transform": TransformComponent(
                x=cx + math.cos(a0) * r, y=cy + math.sin(a0) * r,
            )},
            actor_id=f"enemy_{i}",
        )
    return graph


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

SCENE_ORDER = ["splash", "title", "gameplay", "options"]
AUTO_ADVANCE_FRAMES = 240


def main() -> None:
    pygame.init()
    info = pygame.display.Info()
    flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE
    pygame.display.set_mode((min(info.current_w, 1280), min(info.current_h, 720)), flags)
    pygame.display.set_caption("Scene & Actor Demo — Grimoire 2D")

    ctx = moderngl.create_context()
    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    lw, lh = get_drawable_size(1280, 720)
    s = lh / 720.0
    renderer = Renderer(ctx, lw, lh)

    graph, ids = _build_graph(lw, lh)
    scene_idx = 0
    scene_frame = 0
    frame = 0
    selected_opt = 0
    clock = pygame.time.Clock()
    running = True

    while running:
        clock.tick(60)
        current = SCENE_ORDER[scene_idx]

        # ------------------------------------------------------------------ #
        # Events
        # ------------------------------------------------------------------ #
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

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
                    # Destroy one live enemy (lowest-index found)
                    for i in range(3):
                        if get_actor(graph, f"enemy_{i}") is not None:
                            graph = destroy_actor(graph, f"enemy_{i}")
                            break

                elif event.key == pygame.K_r and current == "gameplay":
                    graph = _respawn_enemies(graph, lw, lh)

                elif event.key == pygame.K_UP and current == "options":
                    selected_opt = (selected_opt - 1) % 3

                elif event.key == pygame.K_DOWN and current == "options":
                    selected_opt = (selected_opt + 1) % 3

            elif event.type == pygame.VIDEORESIZE:
                lw, lh = get_drawable_size(event.w, event.h)
                s = lh / 720.0
                renderer = Renderer(ctx, lw, lh)
                graph, ids = _build_graph(lw, lh)
                scene_frame = 0

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
            graph = _update_title_actors(graph, frame, lw, lh)
        elif current == "gameplay":
            graph = _update_gameplay_actors(graph, frame, lw, lh)

        # ------------------------------------------------------------------ #
        # Render
        # ------------------------------------------------------------------ #
        ctx.clear(0.055, 0.055, 0.09, 1.0)
        renderer.begin_frame()

        if current == "splash":
            _draw_splash(renderer, scene_frame, lw, lh, s)
        elif current == "title":
            _draw_title(renderer, graph, frame, lw, lh, s)
        elif current == "gameplay":
            _draw_gameplay(renderer, graph, frame, lw, lh, s)
        elif current == "options":
            _draw_options(renderer, graph, frame, lw, lh, s, selected_opt)

        _draw_nav_dots(renderer, scene_idx, len(SCENE_ORDER), lw, lh, s)
        _draw_nav_hints(renderer, lw, lh, s)
        renderer.end_frame()
        pygame.display.flip()

        frame += 1
        scene_frame += 1

    pygame.quit()


if __name__ == "__main__":
    main()
