"""Multi-viewport rendering: draw one scene per player viewport.

render_scene() is the single entry point. It accepts the list of
ViewportAssignment objects returned by logic.viewport_layout.compute_viewports
and a caller-supplied scene function, then clips the renderer to each
viewport's rectangle before calling the scene function.

SceneFn signature:
    scene_fn(renderer: Renderer, player_id: str | None) -> None

player_id is None when the assignment carries the shared-screen sentinel "*".
The game uses player_id to anchor the camera to the correct player's position
(split-screen) or passes None to render a single global view (shared-screen).

Example — shared screen (Pong):
    def draw_pong(r, player_id):
        draw_ball(r)
        draw_paddles(r)

    render_scene(renderer, compute_viewports(cfg, w, h), draw_pong)
    # → push_clip(0,0,w,h), draw_pong(renderer, None), pop_clip

Example — split screen:
    def draw_racer(r, player_id):
        cam = cameras[player_id]
        draw_world(r, cam)

    render_scene(renderer, compute_viewports(cfg, w, h), draw_racer)
    # → push_clip(0,0,half_w,h), draw_racer(renderer,"P1"), pop_clip
    # → push_clip(half_w,0,half_w,h), draw_racer(renderer,"P2"), pop_clip
"""

from __future__ import annotations

from typing import Callable

from grimoire2d.presentation.renderer import Renderer
from grimoire2d.models.multiplayer import ViewportAssignment

SceneFn = Callable[[Renderer, "str | None"], None]


def render_scene(
    renderer: Renderer,
    viewports: list[ViewportAssignment],
    scene_fn: SceneFn,
) -> None:
    """Render the scene once per viewport, each clipped to its pixel rectangle.

    For each ViewportAssignment:
      1. renderer.push_clip(x, y, w, h)
      2. scene_fn(renderer, player_id)  — player_id is None for "*" sentinel
      3. renderer.pop_clip()

    Viewports are rendered in list order. Overlapping viewports (shared-screen
    with a single entry) naturally only call the scene function once.
    """
    for vp in viewports:
        pid = None if vp.player_id == "*" else vp.player_id
        renderer.push_clip(vp.x, vp.y, vp.w, vp.h)
        scene_fn(renderer, pid)
        renderer.pop_clip()
