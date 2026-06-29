"""Phase 3 Demo — OBJ Mesh Loader + Texture Support

Proves:
  - load_mesh(): OBJ + MTL parsed and uploaded to GPU
  - Textured rendering: checker-mapped cube with per-face UV islands
  - Untextured sphere loaded from OBJ (vertex-normal shading, no material)
  - Shadow mapping works with loaded meshes (draw_mesh participates in shadow pass)
  - Texture cache: cube loaded twice but checker.png uploaded only once
  - All Phase 2 features still work (FPS camera, fog, point lights, wireframe)

Controls:
  Mouse         look around (click to capture)
  WASD          move (XZ plane)
  Q             fly up
  E             fly down
  Shift+S       toggle specular
  Shift+F       toggle fog
  Shift+H       toggle shadows
  Shift+T       toggle texture
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
SKY_COLOR = (0.45, 0.55, 0.70, 1.0)

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
CUBE_OBJ   = os.path.join(ASSETS, "uv_cube.obj")
SPHERE_OBJ = os.path.join(ASSETS, "low_poly_sphere.obj")

WHITE  = (1.0, 1.0, 1.0, 1.0)
GRAY   = (0.55, 0.55, 0.58, 1.0)
RED    = (0.85, 0.18, 0.12, 1.0)
GREEN  = (0.18, 0.75, 0.25, 1.0)
GOLD   = (0.90, 0.75, 0.10, 1.0)

SCENE_CENTER = (0.0, 0.0, 0.0)
SCENE_RADIUS = 22.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    win = GameWindow(
        "Grimoire2D — 3D Phase 3",
        virtual_width=VIRTUAL_W,
        virtual_height=VIRTUAL_H,
        target_fps=60,
        bar_color=(10, 12, 18, 255),
    )

    settings = RenderSettings3D(
        specular=True,
        fog=True,
        fog_color=(0.45, 0.55, 0.70),
        fog_near=10.0,
        fog_far=28.0,
        shadows=True,
    )
    r3d = Renderer3D(win.ctx, settings)
    ts  = FixedTimestep(physics_hz=PHYSICS_HZ, max_dt=settings.max_dt)

    # Load OBJ meshes — textures cached automatically
    cube_mesh   = r3d.load_mesh(CUBE_OBJ)
    sphere_mesh = r3d.load_mesh(SPHERE_OBJ)
    # Second load of cube — should not re-upload checker.png
    cube_mesh2  = r3d.load_mesh(CUBE_OBJ)

    camera = FreelookCamera(
        position=(0.0, 3.5, 12.0),
        yaw=-90.0,
        pitch=-12.0,
        fov=80.0,
        speed=8.0,
        sensitivity=0.15,
    )

    ambient = AmbientLight(color=(0.20, 0.22, 0.28))
    sun = DirectionalLight(
        direction=(-0.4, -0.9, -0.3),
        color=(1.0, 0.95, 0.85),
        intensity=1.1,
    )
    fill_lights = [
        PointLight(position=(-8.0, 4.0,  8.0), color=(0.3, 0.4, 0.8), intensity=3.0, radius=25.0),
        PointLight(position=( 8.0, 4.0, -8.0), color=(0.8, 0.5, 0.2), intensity=2.0, radius=25.0),
    ]

    mouse_captured = False
    show_texture   = True
    anim_time: float = 0.0
    keys_held: set[int] = set()
    pending_dx: float = 0.0
    pending_dy: float = 0.0

    while win.is_open:
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
                elif shift and event.key == pygame.K_t:
                    show_texture = not show_texture
            elif event.type == pygame.KEYUP:
                keys_held.discard(event.key)
            elif event.type == pygame.MOUSEMOTION and mouse_captured:
                pending_dx += event.rel[0]
                pending_dy += event.rel[1]

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

        # Build spinning rotation for cubes
        rot_y = glm.rotate(glm.mat4(1.0), t * 0.4, glm.vec3(0, 1, 0))
        rot_slow = glm.rotate(glm.mat4(1.0), t * 0.15, glm.vec3(0, 1, 0))

        def draw_all(shadow: bool = False) -> None:
            # Ground plane (primitive, no OBJ)
            r3d.draw_plane((0.0, 0.0, 0.0), size=32.0, color=(0.30, 0.32, 0.28, 1.0))

            # OBJ meshes — textured cubes
            active_cube = cube_mesh if show_texture else cube_mesh2
            r3d.draw_mesh(active_cube, position=(0.0, 1.0, 0.0),   rotation=rot_y,   scale=2.0)
            r3d.draw_mesh(active_cube, position=(-4.0, 1.0, -4.0), rotation=rot_slow, scale=1.5)
            r3d.draw_mesh(active_cube, position=( 4.0, 0.75, -4.0), scale=1.5)

            # OBJ sphere (no texture — vertex normal shading)
            r3d.draw_mesh(sphere_mesh, position=( 3.5, 1.5,  3.0), scale=1.5)
            r3d.draw_mesh(sphere_mesh, position=(-3.5, 1.0,  3.0), scale=1.0)

            # Mix in some primitives so interop is visible
            r3d.draw_sphere(( 0.0, 1.0,  5.0), radius=0.8, color=RED)
            r3d.draw_cylinder((-5.5, 1.0, 0.0), radius=0.45, height=2.0, color=GREEN)
            r3d.draw_cone(   ( 5.5, 0.75, 0.0), radius=0.55, height=1.5, color=GOLD)

            # Slowly rotating boxes to make shadows dynamic
            for i, (ox, oz, spd) in enumerate([(-7, 0, 0.3), (7, 0, -0.25)]):
                angle = t * spd + i * 1.5
                rot_box = glm.rotate(glm.mat4(1.0), angle, glm.vec3(0, 1, 0))
                r3d.draw_box((ox, 0.6, oz), (1.2, 1.2, 1.2), GRAY, rotation=rot_box)

        # Shadow pass
        if settings.shadows:
            r3d.begin_shadow_pass(sun, scene_center=SCENE_CENTER, scene_radius=SCENE_RADIUS)
            draw_all(shadow=True)
            r3d.end_shadow_pass()

        # Color pass
        r3d.begin_scene(
            camera, win.viewport,
            sky_color=SKY_COLOR,
            ambient=ambient,
            dir_light=sun,
            point_lights=fill_lights,
        )
        draw_all()
        r3d.end_scene()

        # HUD
        r  = win.renderer
        VW = float(VIRTUAL_W)

        r.draw_rect(0, 0, VW, 58, (0, 0, 0, 150))

        fps  = win.fps
        spec = "ON " if settings.specular else "OFF"
        fog  = "ON " if settings.fog      else "OFF"
        shad = "ON " if settings.shadows  else "OFF"
        tex  = "ON " if show_texture      else "OFF"

        sm = r3d.shadow_map_size
        r.draw_text(
            f"Grimoire2D  |  3D Phase 3  |  FPS: {fps:5.1f}  |  Shadow map: {sm}×{sm}",
            14, 8, font_size=26, color=(0.9, 0.95, 1.0, 1.0),
        )
        r.draw_text(
            f"[⇧S] Specular: {spec}   [⇧F] Fog: {fog}   [⇧H] Shadows: {shad}   "
            f"[⇧T] Texture: {tex}   WASD+QE=move  Click=capture  ESC=release/quit",
            14, 36, font_size=19, color=(0.6, 0.7, 0.85, 1.0),
        )

        pos = camera.position
        cached_tex = len(r3d._texture_cache)
        r.draw_text(
            f"Cam ({pos.x:+.1f}, {pos.y:+.1f}, {pos.z:+.1f})  "
            f"Yaw {camera.yaw:.0f}°  Pitch {camera.pitch:.0f}°  |  "
            f"Tex cache: {cached_tex} image(s)",
            VW - 660, 8, font_size=19, color=(0.6, 0.7, 0.85, 1.0),
        )

        if not mouse_captured:
            r.draw_text("Click to capture mouse", VW / 2 - 160, VIRTUAL_H / 2 - 14,
                        font_size=28, color=(1.0, 1.0, 0.5, 0.9))

        win.end_frame()

    win.quit()


if __name__ == "__main__":
    run()
