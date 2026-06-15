"""Viewport layout: maps MultiplayerConfig to screen rectangles.

compute_viewports() is a pure function — no GL, no pygame, no side effects.
Given a MultiplayerConfig and the physical pixel dimensions of the window,
it returns a list of ViewportAssignment objects that tell the renderer
which rectangle to clip to when drawing each player's view.

Layouts:

  shared_screen (and network topologies):
      Single full-screen assignment with player_id="*".
      The renderer calls the scene function once.

  split_screen 2 players:
      Left half (P1) and right half (P2).

  split_screen 4 players:
      Four equal quadrants: TL, TR, BL, BR.

  split_screen other player counts:
      Horizontal equal strips (top → bottom).
"""

from __future__ import annotations

from grimoire2d.models.multiplayer import (
    MultiplayerConfig,
    ViewportAssignment,
    TOPOLOGY_SHARED_SCREEN,
    TOPOLOGY_SPLIT_SCREEN,
    TOPOLOGY_NETWORK_HOST,
    TOPOLOGY_NETWORK_CLIENT,
)


def compute_viewports(
    config: MultiplayerConfig,
    screen_w: float,
    screen_h: float,
) -> list[ViewportAssignment]:
    """Return viewport assignments for all player slots.

    shared_screen / network topologies → one full-screen assignment ("*").
    split_screen                       → one sub-rect per player slot.
    """
    topo = config.topology

    # Network and shared-screen: everyone sees the same full frame.
    if topo in (TOPOLOGY_SHARED_SCREEN, TOPOLOGY_NETWORK_HOST, TOPOLOGY_NETWORK_CLIENT):
        return [ViewportAssignment(player_id="*", x=0.0, y=0.0,
                                   w=screen_w, h=screen_h)]

    # split_screen
    slots = config.player_slots
    n = len(slots)

    if n == 0:
        return []

    if n == 1:
        return [ViewportAssignment(player_id=slots[0].player_id,
                                   x=0.0, y=0.0, w=screen_w, h=screen_h)]

    if n == 2:
        half_w = screen_w / 2.0
        return [
            ViewportAssignment(player_id=slots[0].player_id,
                               x=0.0,    y=0.0, w=half_w, h=screen_h),
            ViewportAssignment(player_id=slots[1].player_id,
                               x=half_w, y=0.0, w=half_w, h=screen_h),
        ]

    if n == 4:
        half_w = screen_w / 2.0
        half_h = screen_h / 2.0
        return [
            ViewportAssignment(player_id=slots[0].player_id,
                               x=0.0,    y=0.0,    w=half_w, h=half_h),
            ViewportAssignment(player_id=slots[1].player_id,
                               x=half_w, y=0.0,    w=half_w, h=half_h),
            ViewportAssignment(player_id=slots[2].player_id,
                               x=0.0,    y=half_h, w=half_w, h=half_h),
            ViewportAssignment(player_id=slots[3].player_id,
                               x=half_w, y=half_h, w=half_w, h=half_h),
        ]

    # Fallback: equal horizontal strips
    strip_h = screen_h / n
    return [
        ViewportAssignment(player_id=slots[i].player_id,
                           x=0.0, y=i * strip_h, w=screen_w, h=strip_h)
        for i in range(n)
    ]
