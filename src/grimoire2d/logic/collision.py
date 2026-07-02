"""Axis-aligned bounding-box (AABB) collision world.

Provides a simple spatial database of static obstacles and a
``move_and_slide()`` method that resolves a capsule-shaped player
against those obstacles with wall-sliding behaviour.

Design notes
------------
- The capsule is approximated as an AABB ``(2r, h, 2r)`` for all
  collision tests.  This is exact for axis-aligned surfaces (the
  common case in a brush-based interior).
- Resolution uses per-axis swept AABB: for each axis (X → Y → Z) we
  compute the furthest safe displacement before hitting any obstacle,
  then move exactly that far.  This is the Quake/Doom approach and
  gives sliding naturally — X blocked by a wall leaves Y and Z intact.
- The sweep-path check uses strict overlap (touching = not in path)
  so that after resolving contact on one axis, the contacted surface
  does not incorrectly block movement along itself on the next axis.
- Large steps are handled correctly: they are not subdivided.  The
  swept test computes the exact entry distance regardless of step size,
  so tunneling cannot occur.
- ``on_floor`` is set whenever a downward Y move is stopped by a
  surface beneath the capsule — the standard FPS floor signal.

Usage::

    world = CollisionWorld()
    world.add_box(center=(0, -0.5, 0), size=(20, 1, 20))  # floor slab
    world.add_box(center=(5,  2,   0), size=(1,  4, 10))  # wall

    # Each physics tick (displacement = velocity * dt):
    displacement = (vx * dt, vy * dt - 0.5 * GRAVITY * dt * dt, vz * dt)
    pos, on_floor = world.move_and_slide(pos, displacement, radius=0.3, height=1.8)
    if on_floor:
        vy = 0.0
"""

from __future__ import annotations

from dataclasses import dataclass


# How much penetration on an "other" axis makes an obstacle count as being in
# the sweep path.  Using strict overlap (gap < 0) with a tiny tolerance so
# that surfaces in exact contact (gap == 0) are treated as "touching, not in
# path", which prevents a wall from blocking slide movement along itself.
_PATH_EPS = 1e-4


@dataclass(frozen=True)
class AABB:
    """Axis-aligned bounding box stored as centre + half-extents."""
    cx: float; cy: float; cz: float
    hx: float; hy: float; hz: float


class CollisionWorld:
    """Holds registered AABB obstacles and resolves capsule movement."""

    def __init__(self) -> None:
        self._boxes: list[AABB] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_box(
        self,
        center: tuple[float, float, float],
        size:   tuple[float, float, float],
    ) -> None:
        """Register a static AABB obstacle.

        ``center`` is the world-space centre; ``size`` is (width, height, depth).
        """
        self._boxes.append(AABB(
            cx=float(center[0]), cy=float(center[1]), cz=float(center[2]),
            hx=float(size[0]) * 0.5,
            hy=float(size[1]) * 0.5,
            hz=float(size[2]) * 0.5,
        ))

    def clear(self) -> None:
        """Remove all registered obstacles."""
        self._boxes.clear()

    @property
    def box_count(self) -> int:
        return len(self._boxes)

    # ------------------------------------------------------------------
    # Movement + collision resolution
    # ------------------------------------------------------------------

    def move_and_slide(
        self,
        position: tuple[float, float, float],
        velocity: tuple[float, float, float],
        *,
        radius: float = 0.3,
        height: float = 1.8,
    ) -> tuple[tuple[float, float, float], bool]:
        """Move ``position`` by ``velocity`` with swept AABB collision.

        ``velocity`` should be the desired displacement in world units for this
        tick (i.e. velocity × dt, not raw velocity).

        Returns ``(new_position, on_floor)`` where ``on_floor`` is True when a
        downward Y move was stopped by a surface beneath the capsule.
        """
        px, py, pz = float(position[0]), float(position[1]), float(position[2])
        vx, vy, vz = float(velocity[0]),  float(velocity[1]),  float(velocity[2])

        hr = float(radius)
        hh = float(height) * 0.5   # capsule half-height
        on_floor = False

        for axis_idx, delta_v in enumerate((vx, vy, vz)):
            if abs(delta_v) < 1e-9:
                continue

            # Capsule AABB centre at current position
            cx = px
            cy = py + hh
            cz = pz
            cap_c = (cx, cy, cz)
            cap_h = (hr, hh, hr)

            safe = delta_v   # start with the full desired displacement

            for box in self._boxes:
                bc = (box.cx, box.cy, box.cz)
                bh = (box.hx, box.hy, box.hz)

                # --- Sweep-path filter ---
                # The obstacle must overlap the capsule on the two axes we are
                # NOT moving on.  We use a strict inequality (gap < -_PATH_EPS)
                # so surfaces in contact (gap == 0) are excluded from the path
                # check — this prevents a wall from blocking sliding along itself.
                in_path = True
                for j in range(3):
                    if j == axis_idx:
                        continue
                    gap = abs(cap_c[j] - bc[j]) - (cap_h[j] + bh[j])
                    if gap > -_PATH_EPS:     # clear or just touching → not in path
                        in_path = False
                        break
                if not in_path:
                    continue

                # --- Swept entry distance along the movement axis ---
                p_lo = cap_c[axis_idx] - cap_h[axis_idx]
                p_hi = cap_c[axis_idx] + cap_h[axis_idx]
                b_lo = bc[axis_idx] - bh[axis_idx]
                b_hi = bc[axis_idx] + bh[axis_idx]

                if delta_v > 0:
                    # Moving in + direction: our high face approaches box low face.
                    if p_lo < b_hi and p_hi > b_lo:
                        # Already overlapping on this axis → stop completely.
                        safe = 0.0
                    else:
                        entry = b_lo - p_hi   # positive gap before collision
                        if 0.0 <= entry < safe:
                            safe = entry

                else:   # delta_v < 0
                    # Moving in - direction: our low face approaches box high face.
                    if p_lo < b_hi and p_hi > b_lo:
                        safe = 0.0
                    else:
                        entry = b_hi - p_lo   # negative gap before collision
                        if safe < entry <= 0.0:
                            safe = entry

            # --- Apply displacement ---
            if axis_idx == 0:
                px += safe
            elif axis_idx == 1:
                py += safe
                # on_floor: wanted to move down, got blocked from below
                if delta_v < 0 and safe > delta_v:
                    on_floor = True
            else:
                pz += safe

        return (px, py, pz), on_floor

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def overlaps(
        self,
        center: tuple[float, float, float],
        half_extents: tuple[float, float, float],
    ) -> bool:
        """Return True if the given AABB overlaps any registered obstacle."""
        cx, cy, cz = center
        hx, hy, hz = half_extents
        for box in self._boxes:
            if (abs(cx - box.cx) < hx + box.hx and
                abs(cy - box.cy) < hy + box.hy and
                abs(cz - box.cz) < hz + box.hz):
                return True
        return False
