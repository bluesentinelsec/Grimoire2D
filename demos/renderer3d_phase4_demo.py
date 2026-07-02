"""Phase 4 Demo — Generalized 3D Scene Foundation

Proves:
  4a  draw_quad / draw_rect3d — arbitrary planar geometry (walls, floor, ceiling)
  4b  SkyGradient — procedural zenith/horizon/ground sky, visible through the window
  4c  SpotLight — 2 ceiling fixtures + flashlight; 12 animated point lights that
      independently cycle hue and pulse radius over time
  4d  CollisionWorld + move_and_slide — player walks the room, can't pass through
      walls, stands on the floor, bumps the ceiling

Scene: a corridor + open side room.  One wall has a window gap; the sky
is visible through it.  Point lights are placed along the ceiling and floor.

Controls:
  Mouse               look (click to capture)
  WASD                strafe / walk
  Q / E               fly up / down (gravity off; use to explore full space)
  F                   toggle flashlight (spot light attached to camera)
  Shift+G             toggle gravity
  Shift+S             toggle specular
  Shift+H             toggle shadows
  Shift+F             toggle fog
  [ / ]               decrease / increase gamma (0.5 – 3.0)
  - / =               decrease / increase brightness (0.1 – 2.0)
  ESC                 release mouse / quit
"""

from __future__ import annotations

import math
import os
import sys

import pygame

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import glm

from grimoire2d.presentation.window import GameWindow
from grimoire2d.presentation.renderer3d import Renderer3D
from grimoire2d.models.render_settings_3d import RenderSettings3D
from grimoire2d.models.light3d import (
    AmbientLight, DirectionalLight, PointLight, SpotLight, SkyGradient,
)
from grimoire2d.logic.camera3d import FreelookCamera
from grimoire2d.logic.fixed_timestep import FixedTimestep
from grimoire2d.logic.collision import CollisionWorld

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VIRTUAL_W, VIRTUAL_H = 1920, 1080
PHYSICS_HZ  = 60
GRAVITY     = 18.0        # units per second squared
PLAYER_H    = 1.75        # capsule height
PLAYER_R    = 0.28        # capsule radius
EYE_HEIGHT  = PLAYER_H - 0.15  # camera above player foot

SKY = SkyGradient(
    zenith_color  = (0.08, 0.14, 0.38),
    horizon_color = (0.45, 0.58, 0.78),
    ground_color  = (0.16, 0.14, 0.11),
)

# Room geometry (main corridor: 20 wide, 28 long, 4 tall; side room +12 Z)
ROOM_W, ROOM_H, ROOM_L = 20.0, 4.0, 28.0
SIDE_W, SIDE_L         = 12.0, 14.0   # side room extends in +X

# Window gap in the far wall: Y=[1.0, 3.0], Z=[8, 16] centred
WIN_Y0, WIN_Y1 = 1.0, 3.0
WIN_Z0, WIN_Z1 = 8.0, 20.0

FLOOR_Y  = 0.0
CEIL_Y   = ROOM_H


# ---------------------------------------------------------------------------
# Build collision world
# ---------------------------------------------------------------------------

def build_collision_world() -> CollisionWorld:
    world = CollisionWorld()

    thickness = 0.5   # slab thickness for all geometry

    # Floor
    world.add_box((ROOM_W / 2, FLOOR_Y - thickness / 2, ROOM_L / 2),
                  (ROOM_W + SIDE_W + 2, thickness, ROOM_L + 2))
    # Ceiling
    world.add_box((ROOM_W / 2, CEIL_Y + thickness / 2, ROOM_L / 2),
                  (ROOM_W + 2, thickness, ROOM_L + 2))

    # Left wall (X = 0)
    world.add_box((-thickness / 2, ROOM_H / 2, ROOM_L / 2),
                  (thickness, ROOM_H + 2, ROOM_L + 2))

    # Right wall (X = ROOM_W) — only for the main corridor area; side room opens here
    # Use two segments: [0..10] and [SIDE_L..ROOM_L] in Z, full height
    seg_z1 = SIDE_L / 2.0
    world.add_box((ROOM_W + thickness / 2, ROOM_H / 2, seg_z1 / 2),
                  (thickness, ROOM_H + 2, seg_z1))
    world.add_box((ROOM_W + thickness / 2, ROOM_H / 2, (SIDE_L + ROOM_L) / 2),
                  (thickness, ROOM_H + 2, ROOM_L - SIDE_L))

    # Near wall (Z = 0)
    world.add_box((ROOM_W / 2, ROOM_H / 2, -thickness / 2),
                  (ROOM_W + 2, ROOM_H + 2, thickness))

    # Far wall (Z = ROOM_L) — split around window gap
    # Bottom section [Y=0..WIN_Y0]
    h0 = WIN_Y0; world.add_box((ROOM_W / 2, h0 / 2, ROOM_L + thickness / 2),
                                (ROOM_W + 2, h0, thickness))
    # Top section [Y=WIN_Y1..CEIL_Y]
    h1 = CEIL_Y - WIN_Y1; world.add_box((ROOM_W / 2, WIN_Y1 + h1 / 2, ROOM_L + thickness / 2),
                                         (ROOM_W + 2, h1, thickness))
    # Left of window [Z=WIN_Z0..WIN_Z1 is the gap; left side is Z<WIN_Z0]
    # Wait, the window is in the far wall (Z=ROOM_L), so it's the X extent of the gap
    # Window centred on X: covers [WIN_Z0, WIN_Z1] in X? No, let me rethink.
    # Far wall is at Z=ROOM_L, spanning X=[0..ROOM_W]. Window is a gap at X=[WIN_Z0, WIN_Z1]
    w_left = WIN_Z0
    world.add_box((w_left / 2, WIN_Y0 + (WIN_Y1 - WIN_Y0) / 2, ROOM_L + thickness / 2),
                  (w_left, WIN_Y1 - WIN_Y0, thickness))
    w_right = ROOM_W - WIN_Z1
    world.add_box((WIN_Z1 + w_right / 2, WIN_Y0 + (WIN_Y1 - WIN_Y0) / 2, ROOM_L + thickness / 2),
                  (w_right, WIN_Y1 - WIN_Y0, thickness))

    # Side room walls (extension in +X from X=ROOM_W)
    # Far wall of side room at Z = SIDE_L
    world.add_box((ROOM_W + SIDE_W / 2, ROOM_H / 2, SIDE_L + thickness / 2),
                  (SIDE_W + 2, ROOM_H + 2, thickness))
    # Outer wall of side room at X = ROOM_W + SIDE_W
    world.add_box((ROOM_W + SIDE_W + thickness / 2, ROOM_H / 2, SIDE_L / 2),
                  (thickness, ROOM_H + 2, SIDE_L + 2))
    # Side room ceiling
    world.add_box((ROOM_W + SIDE_W / 2, CEIL_Y + thickness / 2, SIDE_L / 2),
                  (SIDE_W + 2, thickness, SIDE_L + 2))

    return world


# ---------------------------------------------------------------------------
# Animated point lights
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dc

@_dc
class _LightAnim:
    """Static position + animation parameters for one modulating point light."""
    position:    tuple[float, float, float]
    intensity:   float
    radius:      float
    hue_offset:  float   # starting hue in radians
    hue_speed:   float   # hue drift speed, radians / second
    pulse_speed: float   # radius / intensity pulse speed, radians / second
    pulse_depth: float   # fraction of base radius that pulses (0 = static)


def _hue_rgb(h: float) -> tuple[float, float, float]:
    """Map a hue angle to a smooth RGB color wheel value."""
    TWO_PI_3 = 2.0943951
    r = 0.55 + 0.45 * math.cos(h)
    g = 0.55 + 0.45 * math.cos(h + TWO_PI_3)
    b = 0.55 + 0.45 * math.cos(h + 2 * TWO_PI_3)
    return (max(0.0, r), max(0.0, g), max(0.0, b))


def animate_point_lights(anims: list[_LightAnim], t: float) -> list[PointLight]:
    """Compute current PointLight state for all animated lights at time t."""
    lights = []
    for a in anims:
        color  = _hue_rgb(a.hue_offset + a.hue_speed * t)
        pulse  = 1.0 + a.pulse_depth * math.sin(a.pulse_speed * t + a.hue_offset)
        lights.append(PointLight(
            position  = a.position,
            color     = color,
            intensity = a.intensity * pulse,
            radius    = a.radius    * pulse,
        ))
    return lights


def build_light_anims() -> list[_LightAnim]:
    """Define 12 animated point lights: 8 corridor ceiling + 2 side room + 2 floor."""
    PI = math.pi
    anims: list[_LightAnim] = []

    # Corridor ceiling: two rails (x=5, x=15) × four positions along Z
    for rail_idx, x in enumerate([5.0, 15.0]):
        for row_idx, z in enumerate([4.0, 11.0, 18.0, 25.0]):
            anims.append(_LightAnim(
                position    = (x, CEIL_Y - 0.3, z),
                intensity   = 3.0,
                radius      = 11.0,
                hue_offset  = (rail_idx * PI) + (row_idx * PI / 2.5),
                hue_speed   = 0.18 + rail_idx * 0.07 + row_idx * 0.03,
                pulse_speed = 0.9  + row_idx  * 0.25,
                pulse_depth = 0.18,
            ))

    # Side room ceiling: two lights
    for idx, (x, z) in enumerate([(ROOM_W + 4, 4), (ROOM_W + 8, 10)]):
        anims.append(_LightAnim(
            position    = (x, CEIL_Y - 0.3, z),
            intensity   = 2.5,
            radius      = 9.0,
            hue_offset  = PI * 1.3 + idx * PI * 0.7,
            hue_speed   = 0.12 + idx * 0.09,
            pulse_speed = 1.1  + idx * 0.3,
            pulse_depth = 0.22,
        ))

    # Floor accent lights: two moody pools near the entrance
    for idx, (x, z) in enumerate([(2.5, 3.0), (17.5, 3.0)]):
        anims.append(_LightAnim(
            position    = (x, 0.15, z),
            intensity   = 2.0,
            radius      = 5.0,
            hue_offset  = PI * 0.5 + idx * PI,
            hue_speed   = 0.22 + idx * 0.11,
            pulse_speed = 1.6  + idx * 0.4,
            pulse_depth = 0.30,
        ))

    assert len(anims) == 12, f"Expected 12, got {len(anims)}"
    return anims


def build_spot_lights() -> list[SpotLight]:
    """Two static ceiling spot fixtures."""
    return [
        SpotLight(position=(5.0,  CEIL_Y - 0.05, 6.0),  direction=(0, -1, 0),
                  color=(1.0, 0.95, 0.80), intensity=6.0, radius=7.0,
                  inner_angle=12.0, outer_angle=25.0),
        SpotLight(position=(15.0, CEIL_Y - 0.05, 20.0), direction=(0, -1, 0),
                  color=(0.90, 0.95, 1.00), intensity=6.0, radius=7.0,
                  inner_angle=12.0, outer_angle=25.0),
    ]


# ---------------------------------------------------------------------------
# Draw room geometry
# ---------------------------------------------------------------------------

def draw_room(r3d: Renderer3D, flashlight_on: bool, flashlight: SpotLight) -> None:
    FLOOR_C  = (0.28, 0.26, 0.24, 1.0)
    CEIL_C   = (0.32, 0.32, 0.34, 1.0)
    WALL_C   = (0.38, 0.36, 0.34, 1.0)
    SIDE_C   = (0.30, 0.34, 0.40, 1.0)
    WIN_C    = (0.55, 0.70, 0.90, 0.35)   # translucent glass tint

    W, H, L = ROOM_W, ROOM_H, ROOM_L
    SW, SL  = SIDE_W, SIDE_L

    # draw_quad normal = cross(p1−p0, p3−p0).  All faces are wound so the
    # normal points INTO the room (toward the lights and the camera).
    # Rule of thumb: list vertices CCW as seen from inside the room.

    # --- Floors (normal = +Y) ---
    r3d.draw_quad((0, 0, 0), (0, 0, L), (W, 0, L), (W, 0, 0),           FLOOR_C)
    r3d.draw_quad((W, 0, 0), (W, 0, SL), (W+SW, 0, SL), (W+SW, 0, 0),  FLOOR_C)

    # --- Ceilings (normal = −Y) ---
    r3d.draw_quad((0, H, L), (0, H, 0), (W, H, 0), (W, H, L),           CEIL_C)
    r3d.draw_quad((W, H, SL), (W, H, 0), (W+SW, H, 0), (W+SW, H, SL),  CEIL_C)

    # --- Left wall  X=0  (normal = +X) ---
    r3d.draw_quad((0, 0, L), (0, 0, 0), (0, H, 0), (0, H, L),           WALL_C)

    # --- Right wall  X=W  (normal = −X, corridor section only) ---
    r3d.draw_quad((W, 0, L), (W, H, L), (W, H, SL), (W, 0, SL),         WALL_C)

    # --- Near walls  Z=0  (normal = +Z) ---
    r3d.draw_quad((0, 0, 0), (W, 0, 0), (W, H, 0), (0, H, 0),           WALL_C)
    r3d.draw_quad((W, 0, 0), (W+SW, 0, 0), (W+SW, H, 0), (W, H, 0),    SIDE_C)

    # --- Far wall  Z=L  (normal = −Z) — split around window ---
    WIN_X0, WIN_X1 = WIN_Z0, WIN_Z1
    # Bottom strip
    r3d.draw_quad((0, 0, L), (0, WIN_Y0, L), (W, WIN_Y0, L), (W, 0, L),           WALL_C)
    # Top strip
    r3d.draw_quad((0, WIN_Y1, L), (0, H, L), (W, H, L), (W, WIN_Y1, L),           WALL_C)
    # Left of window
    r3d.draw_quad((0, WIN_Y0, L), (0, WIN_Y1, L), (WIN_X0, WIN_Y1, L), (WIN_X0, WIN_Y0, L), WALL_C)
    # Right of window
    r3d.draw_quad((WIN_X1, WIN_Y0, L), (WIN_X1, WIN_Y1, L), (W, WIN_Y1, L), (W, WIN_Y0, L), WALL_C)
    # Window glass (drawn last so alpha blends over sky; same −Z normal)
    r3d.draw_quad((WIN_X0, WIN_Y0, L), (WIN_X0, WIN_Y1, L), (WIN_X1, WIN_Y1, L), (WIN_X1, WIN_Y0, L), WIN_C)

    # --- Side room walls ---
    # Far wall of side room  Z=SL  (normal = −Z)
    r3d.draw_quad((W, 0, SL), (W, H, SL), (W+SW, H, SL), (W+SW, 0, SL),  SIDE_C)
    # Outer wall  X=W+SW  (normal = −X)
    r3d.draw_quad((W+SW, 0, 0), (W+SW, 0, SL), (W+SW, H, SL), (W+SW, H, 0), SIDE_C)

    # A few pillars / props using existing primitives
    for px, pz in [(3, 7), (17, 7), (3, 21), (17, 21)]:
        r3d.draw_cylinder((px, H / 2, pz), radius=0.2, height=H, color=(0.45, 0.42, 0.40, 1.0))

    # A box crate in the side room
    r3d.draw_box((ROOM_W + 6, 0.5, 8), (1.0, 1.0, 1.0), (0.60, 0.50, 0.35, 1.0))
    r3d.draw_box((ROOM_W + 8, 0.5, 5), (1.2, 1.2, 1.2), (0.55, 0.45, 0.30, 1.0))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    win = GameWindow("Grimoire2D — 3D Phase 4", virtual_width=VIRTUAL_W,
                     virtual_height=VIRTUAL_H, target_fps=60, bar_color=(8, 10, 14, 255))

    settings = RenderSettings3D(specular=True, fog=True,
                                 fog_color=(0.01, 0.01, 0.02),
                                 fog_near=14.0, fog_far=28.0, shadows=True)
    r3d = Renderer3D(win.ctx, settings)
    ts  = FixedTimestep(physics_hz=PHYSICS_HZ, max_dt=settings.max_dt)

    col_world    = build_collision_world()
    light_anims  = build_light_anims()
    ceiling_spots = build_spot_lights()

    camera = FreelookCamera(position=(ROOM_W / 2, EYE_HEIGHT, 3.0),
                             yaw=90.0, pitch=-8.0, fov=85.0,
                             speed=6.0, sensitivity=0.15)

    ambient = AmbientLight(color=(0.008, 0.008, 0.012))
    sun = DirectionalLight(direction=(-0.3, -0.8, 0.5), color=(0.40, 0.45, 0.55),
                           intensity=0.04, enabled=True)

    foot_pos = list(camera.position)
    foot_pos[1] -= EYE_HEIGHT    # derive foot from eye
    foot_pos = tuple(foot_pos)

    vy: float = 0.0              # vertical velocity for gravity
    gravity_on = True
    flashlight_on = False
    mouse_captured = False
    keys_held: set[int] = set()
    pending_dx = pending_dy = 0.0
    anim_time: float = 0.0

    def make_flashlight() -> SpotLight:
        fwd = camera.get_forward()
        return SpotLight(
            position  = tuple(camera.position),
            direction = (fwd.x, fwd.y, fwd.z),
            color     = (1.0, 0.97, 0.88),
            intensity = 10.0,
            radius    = 18.0,
            inner_angle = 8.0,
            outer_angle = 18.0,
        )

    while win.is_open:
        pending_dx = pending_dy = 0.0
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
                elif event.key == pygame.K_f and not shift:
                    flashlight_on = not flashlight_on
                elif shift and event.key == pygame.K_g:
                    gravity_on = not gravity_on
                    if not gravity_on:
                        vy = 0.0
                elif shift and event.key == pygame.K_s:
                    settings.specular = not settings.specular
                elif shift and event.key == pygame.K_h:
                    settings.shadows = not settings.shadows
                elif shift and event.key == pygame.K_f:
                    settings.fog = not settings.fog
                # Gamma / brightness
                elif event.key == pygame.K_LEFTBRACKET:
                    settings.gamma = round(max(0.5, settings.gamma - 0.1), 2)
                elif event.key == pygame.K_RIGHTBRACKET:
                    settings.gamma = round(min(3.0, settings.gamma + 0.1), 2)
                elif event.key == pygame.K_MINUS:
                    settings.brightness = round(max(0.1, settings.brightness - 0.05), 2)
                elif event.key == pygame.K_EQUALS:
                    settings.brightness = round(min(2.0, settings.brightness + 0.05), 2)
            elif event.type == pygame.KEYUP:
                keys_held.discard(event.key)
            elif event.type == pygame.MOUSEMOTION and mouse_captured:
                pending_dx += event.rel[0]
                pending_dy += event.rel[1]

        dt = win.begin_frame()
        steps, alpha = ts.advance(dt)

        for _ in range(steps):
            step = ts.step
            if mouse_captured:
                camera.apply_mouse(pending_dx, pending_dy)
                pending_dx = pending_dy = 0.0

            # Compute horizontal velocity from WASD/QE (no gravity on noclip axes)
            fwd   = glm.normalize(glm.vec3(camera.get_forward().x, 0, camera.get_forward().z))
            right = camera.get_right()
            hvel  = glm.vec3(0.0)
            if pygame.K_w in keys_held: hvel += fwd
            if pygame.K_s in keys_held: hvel -= fwd
            if pygame.K_a in keys_held: hvel -= right
            if pygame.K_d in keys_held: hvel += right

            if glm.length(hvel) > 0.001:
                hvel = glm.normalize(hvel) * camera.speed

            if gravity_on:
                vy -= GRAVITY * step
                # Clamp fall speed to avoid tunneling on very thin slabs
                vy = max(vy, -20.0)
                vel = (hvel.x * step, vy * step, hvel.z * step)
            else:
                # Noclip vertical from Q/E
                vv = 0.0
                if pygame.K_q in keys_held: vv += camera.speed
                if pygame.K_e in keys_held: vv -= camera.speed
                vel = (hvel.x * step, vv * step, hvel.z * step)

            foot_pos, on_floor = col_world.move_and_slide(
                foot_pos, vel, radius=PLAYER_R, height=PLAYER_H)

            if on_floor and gravity_on:
                vy = 0.0

            anim_time += step
            camera.position = glm.vec3(foot_pos[0],
                                        foot_pos[1] + EYE_HEIGHT,
                                        foot_pos[2])

        # Animate point lights and build spot light list for this frame
        all_point_lights = animate_point_lights(light_anims, anim_time)
        spot_lights = list(ceiling_spots)
        if flashlight_on:
            spot_lights.append(make_flashlight())

        # Shadow pass
        if settings.shadows:
            r3d.begin_shadow_pass(sun, scene_center=(ROOM_W / 2, ROOM_H / 2, ROOM_L / 2),
                                  scene_radius=28.0)
            draw_room(r3d, flashlight_on, make_flashlight() if flashlight_on else spot_lights[0])
            r3d.end_shadow_pass()

        # Color pass
        r3d.begin_scene(
            camera, win.viewport,
            dt=dt,
            sky=SKY,
            ambient=ambient,
            dir_light=sun,
            point_lights=all_point_lights,
            spot_lights=spot_lights,
        )
        draw_room(r3d, flashlight_on, make_flashlight() if flashlight_on else spot_lights[0])
        r3d.end_scene()

        # HUD
        r  = win.renderer
        VW, VH = float(VIRTUAL_W), float(VIRTUAL_H)

        r.draw_rect(0, 0, VW, 62, (0, 0, 0, 160))

        fps  = win.fps
        sm   = r3d.shadow_map_size
        spec = "ON " if settings.specular else "OFF"
        fog  = "ON " if settings.fog      else "OFF"
        shad = "ON " if settings.shadows  else "OFF"
        grav = "ON " if gravity_on        else "OFF"
        fl   = "ON " if flashlight_on     else "OFF"

        total_pl   = r3d.last_point_light_count
        active_pl  = r3d.last_point_lights_active
        total_sl   = r3d.last_spot_light_count
        active_sl  = r3d.last_spot_lights_active

        r.draw_text(
            f"Grimoire2D  Phase 4  |  FPS: {fps:5.1f}  |  Shadow map: {sm}×{sm}",
            14, 8, font_size=26, color=(0.9, 0.95, 1.0, 1.0),
        )
        r.draw_text(
            f"[F] Flash: {fl}  [⇧G] Gravity: {grav}  [⇧S] Spec: {spec}  "
            f"[⇧H] Shadows: {shad}  [⇧F] Fog: {fog}  "
            f"[[ ]] Gamma: {settings.gamma:.1f}  [-  =] Bright: {settings.brightness:.2f}  "
            f"WASD+QE  Click=capture  ESC=quit",
            14, 38, font_size=18, color=(0.6, 0.70, 0.85, 1.0),
        )

        pos = camera.position
        r.draw_text(
            f"Cam ({pos.x:+.1f}, {pos.y:+.1f}, {pos.z:+.1f})  "
            f"vy={vy:+.1f}  |  "
            f"Point lights: {active_pl}/{total_pl} (animated)  "
            f"Spot lights: {active_sl}/{total_sl}",
            VW - 980, 8, font_size=18, color=(0.6, 0.70, 0.85, 1.0),
        )

        if not mouse_captured:
            r.draw_text("Click to capture mouse", VW / 2 - 160, VH / 2 - 14,
                        font_size=28, color=(1.0, 1.0, 0.5, 0.9))

        win.end_frame()

    win.quit()


if __name__ == "__main__":
    run()
