"""Phase 2 Demo — FPS Camera + Shadow Mapping + New Primitives

Proves:
  - FreelookCamera: WASD movement + mouse-look, FPS-style
  - Real-time shadow mapping from directional sun (PCF 3×3 soft shadows)
  - Shadow toggle at runtime
  - Three new solid primitives: cylinder, cone, capsule
  - All Phase 1 features still work (specular, fog, point lights, wireframe)

Controls:
  Mouse         look around (captured on click)
  WASD          move (XZ plane)
  Q             fly up
  E             fly down
  Shift+S       toggle specular
  Shift+F       toggle fog
  Shift+H       toggle shadows
  Shift+W       toggle wireframe
  ESC           release mouse / quit
"""

from __future__ import annotations

import math
import sys
import os

import pygame

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import glm

from grimoire2d.presentation.window import GameWindow
from grimoire2d.presentation.renderer3d import Renderer3D
from grimoire2d.models.render_settings_3d import RenderSettings3D
from grimoire2d.models.light3d import AmbientLight, DirectionalLight, PointLight
from grimoire2d.logic.camera3d import FreelookCamera
from grimoire2d.logic.fixed_timestep import FixedTimestep

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VIRTUAL_W = 1920
VIRTUAL_H = 1080
PHYSICS_HZ = 60
SKY_COLOR  = (0.45, 0.55, 0.70, 1.0)   # daytime sky blue

WHITE  = (1.0, 1.0, 1.0, 1.0)
GRAY   = (0.55, 0.55, 0.58, 1.0)
RED    = (0.85, 0.18, 0.12, 1.0)
GREEN  = (0.18, 0.75, 0.25, 1.0)
BLUE   = (0.18, 0.35, 0.90, 1.0)
GOLD   = (0.90, 0.75, 0.10, 1.0)
COPPER = (0.80, 0.45, 0.20, 1.0)
TEAL   = (0.15, 0.75, 0.70, 1.0)
WIRE_C = (0.9,  0.9,  0.2,  1.0)

# Scene objects laid out on a grid so shadows are clearly visible
# (type, center_xyz, extra_kwargs, color)
SCENE = [
    # Ground plane drawn separately
    ("box",      ( 0.0, 0.5,  0.0), dict(size=(1.2,1.2,1.2)),                WHITE),
    ("sphere",   (-3.5, 1.0,  0.0), dict(radius=1.0),                        RED),
    ("cylinder", ( 3.5, 1.0,  0.0), dict(radius=0.55, height=2.0),           GREEN),
    ("cone",     ( 0.0, 0.75, 3.5), dict(radius=0.65, height=1.5),           GOLD),
    ("capsule",  (-3.5, 1.5, -3.5), dict(radius=0.5,  height=3.0),           BLUE),
    ("cylinder", ( 3.5, 0.75,-3.5), dict(radius=0.4,  height=1.5),           COPPER),
    ("cone",     (-3.5, 0.75, 3.5), dict(radius=0.5,  height=1.5),           TEAL),
    ("capsule",  ( 3.5, 1.0,  3.5), dict(radius=0.45, height=2.0),           GRAY),
    ("box",      ( 0.0, 0.5, -4.0), dict(size=(2.0,1.0,0.5)),                COPPER),
    ("sphere",   ( 0.0, 0.35,-7.0), dict(radius=0.35),                       TEAL),
]

SCENE_CENTER = (0.0, 0.0, 0.0)
SCENE_RADIUS = 22.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def draw_scene(r3d: Renderer3D, wireframe: bool, t: float) -> None:
    """Submit all scene geometry. Called for both shadow pass and color pass."""
    # Ground plane
    r3d.draw_plane((0.0, 0.0, 0.0), size=32.0, color=(0.30, 0.32, 0.28, 1.0))

    for prim, center, kwargs, color in SCENE:
        getattr(r3d, f"draw_{prim}")(center, **kwargs, color=color)
        if wireframe:
            wkwargs = dict(kwargs)
            if "size" in wkwargs:
                s = wkwargs["size"]
                wkwargs["size"] = (s[0] * 1.02, s[1] * 1.02, s[2] * 1.02)
            elif "radius" in wkwargs:
                wkwargs["radius"] = wkwargs["radius"] * 1.02
            getattr(r3d, f"draw_{prim}")(center, **wkwargs, color=WIRE_C, wireframe=True)

    # A few slowly-rotating boxes to make shadows dynamic
    for i, (ox, oz, spd) in enumerate([(-6, 0, 0.4), (6, 0, -0.35), (0, -6, 0.5)]):
        angle = t * spd + i * 2.1
        rot = glm.rotate(glm.mat4(1.0), angle, glm.vec3(0, 1, 0))
        r3d.draw_box((ox, 0.6, oz), (1.2, 1.2, 1.2), GRAY, rotation=rot)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    win = GameWindow(
        "Grimoire2D — 3D Phase 2",
        virtual_width=VIRTUAL_W,
        virtual_height=VIRTUAL_H,
        target_fps=60,
        bar_color=(10, 12, 18, 255),
    )

    settings = RenderSettings3D(
        specular=True,
        fog=True,
        fog_color=(0.45, 0.55, 0.70),   # matches sky color
        fog_near=10.0,                   # starts fading at 10 units
        fog_far=28.0,                    # fully opaque at 28 units
        shadows=True,
    )
    r3d = Renderer3D(win.ctx, settings)
    ts  = FixedTimestep(physics_hz=PHYSICS_HZ, max_dt=settings.max_dt)

    camera = FreelookCamera(
        position=(0.0, 3.5, 12.0),
        yaw=-90.0,
        pitch=-12.0,
        fov=80.0,
        speed=8.0,
        sensitivity=0.15,
    )

    # Daytime sun — high and to one side so shadow angle is interesting
    ambient = AmbientLight(color=(0.20, 0.22, 0.28))
    sun = DirectionalLight(
        direction=(-0.4, -0.9, -0.3),
        color=(1.0, 0.95, 0.85),
        intensity=1.1,
    )
    # Two subtle fill lights so the shadow side isn't pitch black
    fill_lights = [
        PointLight(position=(-8.0, 4.0,  8.0), color=(0.3, 0.4, 0.8), intensity=3.0, radius=25.0),
        PointLight(position=( 8.0, 4.0, -8.0), color=(0.8, 0.5, 0.2), intensity=2.0, radius=25.0),
    ]

    mouse_captured = False
    wireframe = False
    anim_time: float = 0.0
    keys_held: set[int] = set()
    pending_dx: float = 0.0
    pending_dy: float = 0.0

    while win.is_open:
        # --- Input ---
        pending_dx = 0.0
        pending_dy = 0.0
        for event in win.poll():
            if event.type == pygame.QUIT:
                win.close()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not mouse_captured:
                    pygame.event.set_grab(True)
                    pygame.mouse.set_visible(False)
                    mouse_captured = True
            elif event.type == pygame.KEYDOWN:
                keys_held.add(event.key)
                shift = bool(event.mod & pygame.KMOD_SHIFT)
                if event.key == pygame.K_ESCAPE:
                    if mouse_captured:
                        pygame.event.set_grab(False)
                        pygame.mouse.set_visible(True)
                        mouse_captured = False
                    else:
                        win.close()
                elif shift and event.key == pygame.K_s:
                    settings.specular = not settings.specular
                elif shift and event.key == pygame.K_f:
                    settings.fog = not settings.fog
                elif shift and event.key == pygame.K_h:
                    settings.shadows = not settings.shadows
                elif shift and event.key == pygame.K_w:
                    wireframe = not wireframe
            elif event.type == pygame.KEYUP:
                keys_held.discard(event.key)
            elif event.type == pygame.MOUSEMOTION and mouse_captured:
                pending_dx += event.rel[0]
                pending_dy += event.rel[1]

        # --- Fixed-timestep update ---
        dt = win.begin_frame()
        steps, alpha = ts.advance(dt)
        for _ in range(steps):
            if mouse_captured:
                camera.apply_mouse(pending_dx, pending_dy)
                pending_dx = 0.0
                pending_dy = 0.0
            camera.move(keys_held, ts.step)
            anim_time += ts.step

        t = anim_time + alpha * ts.step

        # --- Shadow pass (draw all shadow casters into depth map) ---
        if settings.shadows:
            r3d.begin_shadow_pass(
                sun,
                scene_center=SCENE_CENTER,
                scene_radius=SCENE_RADIUS,
            )
            draw_scene(r3d, False, t)   # wire=False for shadow; solid only
            r3d.end_shadow_pass()

        # --- 3D color pass ---
        r3d.begin_scene(
            camera,
            win.viewport,
            sky_color=SKY_COLOR,
            ambient=ambient,
            dir_light=sun,
            point_lights=fill_lights,
        )
        draw_scene(r3d, wireframe, t)
        r3d.end_scene()

        # --- 2D HUD ---
        r  = win.renderer
        VW = float(VIRTUAL_W)

        r.draw_rect(0, 0, VW, 58, (0, 0, 0, 150))

        fps  = win.fps
        spec = "ON " if settings.specular else "OFF"
        fog  = "ON " if settings.fog      else "OFF"
        shad = "ON " if settings.shadows  else "OFF"
        wire = "ON " if wireframe         else "OFF"

        sm = r3d.shadow_map_size
        r.draw_text(f"Grimoire2D  |  3D Phase 2  |  FPS: {fps:5.1f}  |  Shadow map: {sm}×{sm}",
                    14, 8, font_size=26, color=(0.9, 0.95, 1.0, 1.0))
        r.draw_text(
            f"[⇧S] Specular: {spec}   [⇧F] Fog: {fog}   [⇧H] Shadows: {shad}   "
            f"[⇧W] Wireframe: {wire}   WASD+QE=move  Click=capture  ESC=release/quit",
            14, 36, font_size=19, color=(0.6, 0.7, 0.85, 1.0),
        )

        pos = camera.position
        r.draw_text(
            f"Cam  ({pos.x:+.1f}, {pos.y:+.1f}, {pos.z:+.1f})  "
            f"Yaw {camera.yaw:.0f}°  Pitch {camera.pitch:.0f}°",
            VW - 480, 8, font_size=19, color=(0.6, 0.7, 0.85, 1.0),
        )

        if not mouse_captured:
            r.draw_text("Click to capture mouse", VW/2 - 160, VIRTUAL_H/2 - 14,
                        font_size=28, color=(1.0, 1.0, 0.5, 0.9))

        win.end_frame()

    win.quit()


if __name__ == "__main__":
    run()
