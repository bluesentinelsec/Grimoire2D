"""3D perspective camera — view and projection matrices.

PerspectiveCamera stores position + yaw/pitch orientation and produces
GL-ready view and projection matrices via PyGLM.

FreelookCamera adds FPS-style mouse-look and WASD movement on top; it is
intended to be driven once per frame with raw input deltas.
"""

from __future__ import annotations

import math
import glm


class PerspectiveCamera:
    """Minimal perspective camera.

    Coordinate convention: Y-up, right-handed (same as OpenGL default).
    Yaw=0 / Pitch=0 looks down the -Z axis.
    """

    def __init__(
        self,
        position: tuple[float, float, float] = (0.0, 3.0, 8.0),
        yaw: float = -90.0,
        pitch: float = -15.0,
        fov: float = 75.0,
        near: float = 0.1,
        far: float = 1000.0,
    ) -> None:
        self.position = glm.vec3(*position)
        self.yaw = yaw      # degrees; -90 faces -Z
        self.pitch = pitch  # degrees; negative tilts down
        self.fov = fov      # vertical field of view in degrees
        self.near = near
        self.far = far

    # ------------------------------------------------------------------
    # Derived vectors
    # ------------------------------------------------------------------

    def get_forward(self) -> glm.vec3:
        yr = math.radians(self.yaw)
        pr = math.radians(self.pitch)
        return glm.normalize(glm.vec3(
            math.cos(pr) * math.cos(yr),
            math.sin(pr),
            math.cos(pr) * math.sin(yr),
        ))

    def get_right(self) -> glm.vec3:
        return glm.normalize(glm.cross(self.get_forward(), glm.vec3(0, 1, 0)))

    def get_up(self) -> glm.vec3:
        return glm.normalize(glm.cross(self.get_right(), self.get_forward()))

    # ------------------------------------------------------------------
    # GL matrices (column-major; PyGLM bytes() gives column-major floats)
    # ------------------------------------------------------------------

    def get_view_matrix(self) -> glm.mat4:
        fwd = self.get_forward()
        return glm.lookAt(self.position, self.position + fwd, glm.vec3(0, 1, 0))

    def get_projection_matrix(self, aspect: float) -> glm.mat4:
        return glm.perspective(glm.radians(self.fov), aspect, self.near, self.far)


class FreelookCamera(PerspectiveCamera):
    """FPS-style free-look camera driven by mouse deltas and key state.

    Typical per-frame usage::

        steps, alpha = timestep.advance(dt)
        for _ in range(steps):
            cam.apply_mouse(mouse_dx, mouse_dy)
            cam.move(keys, FIXED_STEP)
        # render with cam.get_view_matrix() / cam.get_projection_matrix()
    """

    PITCH_LIMIT = 89.0  # degrees — prevents gimbal flip at poles

    def __init__(
        self,
        *args,
        sensitivity: float = 0.15,
        speed: float = 8.0,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.sensitivity = sensitivity  # degrees per pixel
        self.speed = speed              # world units per second

    def apply_mouse(self, dx: float, dy: float) -> None:
        """Accumulate mouse delta into yaw/pitch. Call once per physics step."""
        self.yaw += dx * self.sensitivity
        self.pitch -= dy * self.sensitivity  # invert Y: mouse down → look down
        self.pitch = max(-self.PITCH_LIMIT, min(self.PITCH_LIMIT, self.pitch))

    def move(self, keys_held: set[int], dt: float) -> None:
        """Translate camera based on held key set. Call once per physics step.

        ``keys_held`` is a set of pygame key constants.
        WASD moves on the XZ plane (no vertical drift from pitch);
        Q rises and E descends along world-Y.
        """
        import pygame

        fwd = glm.normalize(glm.vec3(self.get_forward().x, 0.0, self.get_forward().z))
        right = self.get_right()
        up = glm.vec3(0, 1, 0)

        vel = glm.vec3(0.0)
        if pygame.K_w in keys_held:
            vel += fwd
        if pygame.K_s in keys_held:
            vel -= fwd
        if pygame.K_a in keys_held:
            vel -= right
        if pygame.K_d in keys_held:
            vel += right
        if pygame.K_q in keys_held:
            vel += up
        if pygame.K_e in keys_held:
            vel -= up

        if glm.length(vel) > 0.001:
            self.position += glm.normalize(vel) * self.speed * dt
