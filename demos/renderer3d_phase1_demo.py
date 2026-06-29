"""Phase 1 Demo — 3D Renderer: Primitives + Phong Lighting

Proves:
  - Solid and wireframe primitives (box, sphere, plane)
  - Phong lighting: ambient + directional sun + 3 orbiting point lights
  - Runtime effect toggles (specular, fog) via RenderSettings3D
  - Fixed-timestep accumulator with dt clamping (frame-rate-independent animation)
  - 2D HUD rendered on top of the 3D scene using virtual coordinates

Controls:
  S       toggle specular highlights
  F       toggle distance fog
  W       toggle wireframe on selected objects
  ESC     quit
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
from grimoire2d.logic.camera3d import PerspectiveCamera
from grimoire2d.logic.fixed_timestep import FixedTimestep

# ---------------------------------------------------------------------------
# Scene constants
# ---------------------------------------------------------------------------

VIRTUAL_W = 1920
VIRTUAL_H = 1080

# Fixed physics rate — animation runs at this speed regardless of display Hz
PHYSICS_HZ = 60

# Point light orbit
LIGHT_ORBIT_RADIUS = 5.0
LIGHT_HEIGHT = 2.5

# Colors (RGBA, linear)
RED    = (0.9, 0.15, 0.15, 1.0)
GREEN  = (0.15, 0.85, 0.25, 1.0)
BLUE   = (0.15, 0.4,  0.95, 1.0)
GOLD   = (0.95, 0.8,  0.1,  1.0)
WHITE  = (1.0,  1.0,  1.0,  1.0)
SILVER = (0.7,  0.75, 0.8,  1.0)
WIRE_C = (0.9,  0.9,  0.2,  1.0)   # wireframe yellow

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    win = GameWindow(
        "Grimoire2D — 3D Phase 1",
        virtual_width=VIRTUAL_W,
        virtual_height=VIRTUAL_H,
        target_fps=60,
        bar_color=(5, 5, 10, 255),
    )
    win.renderer.set_clear_color((10, 12, 18, 255))  # dark night-sky background

    # 3D renderer shares the same GL context as the 2D renderer
    settings = RenderSettings3D(
        specular=True,
        fog=False,
        fog_color=(0.08, 0.1, 0.14),
        fog_near=14.0,
        fog_far=40.0,
    )
    r3d = Renderer3D(win.ctx, settings)

    # Fixed-timestep accumulator: physics at 60 Hz, render as fast as possible.
    # MAX_DT=0.1 means a 30-second debugger pause advances the simulation by
    # at most 100 ms — no spiral of death.
    ts = FixedTimestep(physics_hz=PHYSICS_HZ, max_dt=settings.max_dt)

    # Camera — fixed overhead angle for Phase 1 (free-look in Phase 2)
    camera = PerspectiveCamera(
        position=(0.0, 6.0, 14.0),
        yaw=-90.0,
        pitch=-22.0,
        fov=70.0,
    )

    # Lights
    ambient  = AmbientLight(color=(0.05, 0.05, 0.08))
    sun      = DirectionalLight(
        direction=(0.4, -1.0, -0.6),
        color=(0.9, 0.85, 0.75),
        intensity=0.6,
    )
    # Three coloured point lights that orbit the scene
    pl_colors = [
        (1.0, 0.25, 0.1),   # red-orange
        (0.1, 0.5,  1.0),   # cool blue
        (0.2, 1.0,  0.35),  # green
    ]
    pl_offsets = [0.0, 2.0 * math.pi / 3.0, 4.0 * math.pi / 3.0]

    # Animation state (driven by fixed steps, displayed with interpolation)
    anim_time: float = 0.0
    wireframe: bool  = False

    clock_ref = [0.0]   # raw elapsed for HUD readout only

    while win.is_open:
        # --- Input ---
        for event in win.poll():
            if event.type == pygame.QUIT:
                win.close()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    win.close()
                elif event.key == pygame.K_s:
                    settings.specular = not settings.specular
                elif event.key == pygame.K_f:
                    settings.fog = not settings.fog
                elif event.key == pygame.K_w:
                    wireframe = not wireframe

        # --- Fixed-timestep physics / animation update ---
        dt = win.begin_frame()
        steps, alpha = ts.advance(dt)
        for _ in range(steps):
            anim_time += ts.step  # accumulates exactly at 1/60 s each step

        # Interpolated animation time for smooth rendering at any frame rate
        t = anim_time + alpha * ts.step

        # --- Compute animated transforms ---
        # Three boxes rotating at different speeds and axes
        box_transforms = [
            # (position,      size,       color,  rot_axis,        rot_speed, phase)
            ((-3.5, 0.7, 0.0), (1.4,1.4,1.4), RED,   (0,1,0), 0.8,  0.0),
            (( 3.5, 0.7, 0.0), (1.2,1.6,1.2), GREEN, (1,0,0), 1.1,  1.0),
            (( 0.0, 0.7,-3.5), (1.3,1.3,1.3), BLUE,  (0.6,0.8,0), 0.6, 2.1),
        ]

        # Orbiting point lights
        point_lights = []
        for color, offset in zip(pl_colors, pl_offsets):
            angle = t * 0.9 + offset
            px = math.cos(angle) * LIGHT_ORBIT_RADIUS
            pz = math.sin(angle) * LIGHT_ORBIT_RADIUS
            point_lights.append(PointLight(
                position=(px, LIGHT_HEIGHT, pz),
                color=color,
                intensity=2.0,
                radius=11.0,
            ))

        # Pulsing center sphere scale
        sphere_r = 0.9 + 0.15 * math.sin(t * 2.3)

        # --- 3D render pass ---
        r3d.begin_scene(
            camera,
            win.viewport,
            ambient=ambient,
            dir_light=sun,
            point_lights=point_lights,
        )

        # Ground plane
        r3d.draw_plane((0.0, 0.0, 0.0), size=22.0, color=(0.18, 0.19, 0.22, 1.0))

        # Rotating boxes (solid)
        for (pos, sz, col, axis, speed, phase) in box_transforms:
            angle_rad = (t * speed + phase) % (2 * math.pi)
            rot = glm.rotate(glm.mat4(1.0), angle_rad, glm.vec3(*axis))
            r3d.draw_box(pos, sz, col, rotation=rot)

        # Wire outlines over the same boxes
        if wireframe:
            for (pos, sz, col, axis, speed, phase) in box_transforms:
                angle_rad = (t * speed + phase) % (2 * math.pi)
                rot = glm.rotate(glm.mat4(1.0), angle_rad, glm.vec3(*axis))
                slightly_larger = (sz[0]*1.02, sz[1]*1.02, sz[2]*1.02)
                r3d.draw_box(pos, slightly_larger, WIRE_C, rotation=rot, wireframe=True)

        # Center pulsing sphere
        r3d.draw_sphere((0.0, sphere_r, 0.0), radius=sphere_r, color=SILVER)
        r3d.draw_sphere((0.0, sphere_r, 0.0), radius=sphere_r * 1.02, color=WIRE_C, wireframe=wireframe)

        # Small spheres marking each point light position
        for pl in point_lights:
            r3d.draw_sphere(pl.position, radius=0.22,
                            color=(*pl.color, 1.0))

        r3d.end_scene()

        # --- 2D HUD (virtual coordinates, on top of 3D) ---
        r = win.renderer
        VW = float(VIRTUAL_W)

        # Semi-transparent dark strip at top
        r.draw_rect(0, 0, VW, 56, (0, 0, 0, 140))

        fps  = win.fps
        spec = "ON " if settings.specular else "OFF"
        fog  = "ON " if settings.fog      else "OFF"
        wire = "ON " if wireframe         else "OFF"

        r.draw_text(f"Grimoire2D  |  3D Phase 1  |  FPS: {fps:5.1f}",
                    14, 10, font_size=26, color=(0.85, 0.9, 1.0, 1.0))
        r.draw_text(
            f"[S] Specular: {spec}   [F] Fog: {fog}   [W] Wireframe: {wire}   [ESC] Quit",
            14, 36, font_size=20, color=(0.55, 0.65, 0.8, 1.0),
        )

        # Light indicators — small coloured dots + label
        labels = [("Red light", (1.0,0.4,0.2,1.0)),
                  ("Blue light",(0.3,0.6,1.0,1.0)),
                  ("Green light",(0.3,1.0,0.5,1.0))]
        for i, (name, col) in enumerate(labels):
            x = VW - 210
            y = 10 + i * 24
            r.draw_circle(x, y + 8, 7, col)
            r.draw_text(name, x + 15, y, font_size=18, color=(0.8, 0.85, 0.9, 1.0))

        win.end_frame()

    win.quit()


if __name__ == "__main__":
    run()
