"""SimulationClock: fixed-timestep tick accumulation.

The engine does not define what "advance the game one tick" means — that is
the game's responsibility. The engine provides SimulationClock to correctly
distribute variable-rate real time into discrete fixed-rate ticks.

Usage in a game loop:
    sim_clock = SimulationClock(tick_rate=60)
    while running:
        dt = wall_clock.tick(0) / 1000.0  # seconds since last frame
        n_ticks = sim_clock.update(dt)
        for _ in range(n_ticks):
            frames = route_inputs(sources, sim_clock.tick)
            game_state = my_advance_tick(game_state, frames)

The max_ticks_per_frame guard prevents the "spiral of death": if the
renderer stalls (e.g. loading a level), the simulation does not try to
catch up with an unbounded burst of ticks.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SimulationClock:
    """Fixed-timestep accumulator.

    Converts variable dt (seconds) into a discrete count of simulation ticks.

    tick_rate:           ticks per second (default 60).
    max_ticks_per_frame: burst cap per update() call (default 4).
    """

    tick_rate:            int   = 60
    max_ticks_per_frame:  int   = 4
    _accumulator:         float = field(default=0.0, init=False, repr=False)
    _tick:                int   = field(default=0,   init=False, repr=False)

    @property
    def tick(self) -> int:
        """The current authoritative tick count (monotonically increasing)."""
        return self._tick

    @property
    def tick_dt(self) -> float:
        """Duration of one simulation tick in seconds."""
        return 1.0 / self.tick_rate

    @property
    def alpha(self) -> float:
        """Interpolation factor in [0, 1) for render-between-ticks smoothing."""
        return self._accumulator / self.tick_dt

    def update(self, dt: float) -> int:
        """Advance the clock by dt real seconds.

        Returns the number of simulation ticks to run this frame.
        Increments the internal tick counter by that amount.
        Caps the return value at max_ticks_per_frame.
        """
        self._accumulator += dt
        step = self.tick_dt
        ticks = 0
        while self._accumulator >= step and ticks < self.max_ticks_per_frame:
            self._accumulator -= step
            self._tick += 1
            ticks += 1
        return ticks

    def reset(self) -> None:
        """Reset both the accumulator and the tick counter to zero."""
        self._accumulator = 0.0
        self._tick = 0
