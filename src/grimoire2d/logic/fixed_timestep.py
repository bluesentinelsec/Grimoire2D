"""Fixed-timestep accumulator for frame-rate-independent game logic.

Pattern: "Fix Your Timestep" (Glenn Fiedler, 2004).

Usage::

    ts = FixedTimestep(physics_hz=60, max_dt=0.1)

    # In the game loop:
    steps, alpha = ts.advance(raw_dt)
    for _ in range(steps):
        physics_update(ts.step)   # always exactly 1/60 s
    render(interpolate(prev_state, curr_state, alpha))

Key properties:

* ``max_dt`` clamps the raw frame time so a debugger pause (or a stutter)
  cannot push many seconds of simulation into a single frame. The game
  runs slow but never spirals.
* ``alpha`` is the sub-step interpolation factor in [0, 1) for smooth
  rendering at any refresh rate.
* The physics tick rate is fixed regardless of render rate — 144 Hz
  monitor, 30 Hz render, same physics.
"""

from __future__ import annotations


class FixedTimestep:
    def __init__(self, physics_hz: int = 60, max_dt: float = 0.1) -> None:
        if physics_hz <= 0:
            raise ValueError("physics_hz must be positive")
        self.step: float = 1.0 / physics_hz
        self.max_dt: float = max_dt
        self._accumulator: float = 0.0

    def advance(self, raw_dt: float) -> tuple[int, float]:
        """Consume raw frame time and return (num_fixed_steps, blend_alpha).

        ``blend_alpha`` in [0, 1) represents how far into the *next* fixed
        step the renderer is — use it to interpolate between previous and
        current physics state for sub-step-smooth rendering.
        """
        dt = min(raw_dt, self.max_dt)
        self._accumulator += dt
        steps = 0
        while self._accumulator >= self.step:
            self._accumulator -= self.step
            steps += 1
        alpha = self._accumulator / self.step
        return steps, alpha

    def reset(self) -> None:
        self._accumulator = 0.0
