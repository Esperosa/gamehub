from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Sequence


@dataclass
class Metaball:
    x: float
    y: float
    z: float
    px: float
    py: float
    pz: float
    r: float
    home_x: float
    home_y: float
    home_z: float
    phase: float
    orbit_x: float
    orbit_y: float
    orbit_z: float
    orbit_speed_x: float
    orbit_speed_y: float
    orbit_speed_z: float


class MetaballSimulation:
    """3D metaball dynamics tuned for raymarched bubble rendering."""

    def __init__(self, count: int = 24, seed: int = 1337):
        self._rng = random.Random(seed)
        self._balls: List[Metaball] = []
        self._base_count = max(4, min(36, int(count)))
        self._target_count = self._base_count
        self._width = 1
        self._height = 1
        self._time = 0.0

        self._damping = 0.994
        self._flow = 0.20
        self._anchor = 0.62
        self._render_scale = 1.64

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    def _spawn_ball(self, x: float, y: float, z: float, base_r: float) -> Metaball:
        radius = self._rng.uniform(base_r * 0.72, base_r * 1.72)
        render_margin = radius * self._render_scale
        x = self._clamp(x, -1.0 + render_margin, 1.0 - render_margin)
        y = self._clamp(y, -1.0 + render_margin, 1.0 - render_margin)
        z = self._clamp(z, -1.0 + render_margin, 1.0 - render_margin)
        speed = self._rng.uniform(0.18, 0.52)
        heading_a = self._rng.uniform(0.0, math.tau)
        heading_b = self._rng.uniform(-0.8, 0.8)
        vx = math.cos(heading_a) * math.cos(heading_b) * speed
        vy = math.sin(heading_b) * speed
        vz = math.sin(heading_a) * math.cos(heading_b) * speed
        dt = 1.0 / 60.0
        return Metaball(
            x=x,
            y=y,
            z=z,
            px=x - vx * dt,
            py=y - vy * dt,
            pz=z - vz * dt,
            r=radius,
            home_x=x,
            home_y=y,
            home_z=z,
            phase=self._rng.uniform(0.0, math.tau),
            orbit_x=self._rng.uniform(0.05, 0.20),
            orbit_y=self._rng.uniform(0.05, 0.20),
            orbit_z=self._rng.uniform(0.04, 0.18),
            orbit_speed_x=self._rng.uniform(0.28, 0.76),
            orbit_speed_y=self._rng.uniform(0.26, 0.72),
            orbit_speed_z=self._rng.uniform(0.22, 0.66),
        )

    def _spawn_initial(self) -> None:
        self._balls.clear()
        n = self._target_count
        cells = max(3, math.ceil(n ** (1.0 / 3.0)))
        step = 1.34 / cells
        base_r = 0.122
        slots = [(ix, iy, iz) for iz in range(cells) for iy in range(cells) for ix in range(cells)]
        self._rng.shuffle(slots)
        for i in range(n):
            ix, iy, iz = slots[i]
            x = -0.67 + (ix + 0.5) * step + self._rng.uniform(-0.25, 0.25) * step
            y = -0.67 + (iy + 0.5) * step + self._rng.uniform(-0.25, 0.25) * step
            z = -0.67 + (iz + 0.5) * step + self._rng.uniform(-0.25, 0.25) * step
            self._balls.append(self._spawn_ball(x, y, z, base_r))

    def _reconcile_count(self) -> None:
        n = len(self._balls)
        if n < self._target_count:
            missing = self._target_count - n
            for _ in range(missing):
                x = self._rng.uniform(-0.66, 0.66)
                y = self._rng.uniform(-0.66, 0.66)
                z = self._rng.uniform(-0.66, 0.66)
                self._balls.append(self._spawn_ball(x, y, z, 0.125))
        elif n > self._target_count:
            self._balls = self._balls[: self._target_count]

    def resize(self, width: int, height: int) -> None:
        self._width = max(1, int(width))
        self._height = max(1, int(height))
        # Keep deterministic count for visual debugging.
        self._target_count = self._base_count

        if not self._balls:
            self._spawn_initial()
        else:
            self._reconcile_count()

    def step(self, dt: float) -> None:
        if not self._balls:
            return

        dt = max(0.0, min(1.0 / 30.0, float(dt)))
        if dt <= 0.0:
            return

        self._time += dt
        n = len(self._balls)
        near_count = [0] * n
        near_cx = [0.0] * n
        near_cy = [0.0] * n
        near_cz = [0.0] * n

        for b in self._balls:
            vx = (b.x - b.px) * self._damping
            vy = (b.y - b.py) * self._damping
            vz = (b.z - b.pz) * self._damping

            flow_x = math.sin(1.8 * b.y + 1.3 * b.z + 0.72 * self._time + b.phase)
            flow_y = math.cos(1.7 * b.x - 1.4 * b.z + 0.63 * self._time - b.phase * 0.7)
            flow_z = math.sin(1.6 * b.x + 1.5 * b.y - 0.58 * self._time + b.phase * 1.2)

            target_x = b.home_x + math.cos(self._time * b.orbit_speed_x + b.phase) * b.orbit_x
            target_y = b.home_y + math.sin(self._time * b.orbit_speed_y + b.phase * 0.91) * b.orbit_y
            target_z = b.home_z + math.cos(self._time * b.orbit_speed_z + b.phase * 1.07) * b.orbit_z

            ax = (target_x - b.x) * self._anchor
            ay = (target_y - b.y) * self._anchor
            az = (target_z - b.z) * self._anchor

            nx = b.x + vx + flow_x * (self._flow * dt) + ax * dt
            ny = b.y + vy + flow_y * (self._flow * dt) + ay * dt
            nz = b.z + vz + flow_z * (self._flow * dt) + az * dt

            b.px, b.py, b.pz = b.x, b.y, b.z
            b.x, b.y, b.z = nx, ny, nz

        for _ in range(6):
            for i in range(n):
                a = self._balls[i]
                for j in range(i + 1, n):
                    b = self._balls[j]
                    dx = a.x - b.x
                    dy = a.y - b.y
                    dz = a.z - b.z
                    dist2 = dx * dx + dy * dy + dz * dz + 1e-8
                    dist = math.sqrt(dist2)
                    sum_r = a.r + b.r
                    min_dist = sum_r * 0.96
                    if dist < min_dist:
                        corr = (min_dist - dist) / dist
                        push_x = dx * corr * 0.5
                        push_y = dy * corr * 0.5
                        push_z = dz * corr * 0.5
                        a.x += push_x
                        a.y += push_y
                        a.z += push_z
                        b.x -= push_x
                        b.y -= push_y
                        b.z -= push_z

                    if dist < sum_r * 1.25:
                        near_count[i] += 1
                        near_count[j] += 1
                        near_cx[i] += b.x
                        near_cy[i] += b.y
                        near_cz[i] += b.z
                        near_cx[j] += a.x
                        near_cy[j] += a.y
                        near_cz[j] += a.z

            for b in self._balls:
                margin = b.r * self._render_scale
                b.x = self._clamp(b.x, -1.0 + margin, 1.0 - margin)
                b.y = self._clamp(b.y, -1.0 + margin, 1.0 - margin)
                b.z = self._clamp(b.z, -1.0 + margin, 1.0 - margin)

        for i, b in enumerate(self._balls):
            if near_count[i] >= 3:
                cx = near_cx[i] / near_count[i]
                cy = near_cy[i] / near_count[i]
                cz = near_cz[i] / near_count[i]
                dx = b.x - cx
                dy = b.y - cy
                dz = b.z - cz
                mag = math.sqrt(dx * dx + dy * dy + dz * dz)
                if mag > 1e-6:
                    spread = min(0.07, (near_count[i] - 2) * 0.011)
                    b.x += (dx / mag) * spread
                    b.y += (dy / mag) * spread
                    b.z += (dz / mag) * spread

            # Keep rendered isosurface inside tracing box after anti-clump push.
            margin = b.r * self._render_scale
            b.x = self._clamp(b.x, -1.0 + margin, 1.0 - margin)
            b.y = self._clamp(b.y, -1.0 + margin, 1.0 - margin)
            b.z = self._clamp(b.z, -1.0 + margin, 1.0 - margin)

    def shader_uniform_payload(self, max_count: int = 32) -> Sequence[float]:
        payload: List[float] = []
        for ball in self._balls[:max_count]:
            payload.extend(
                (
                    float(ball.x),
                    float(ball.y),
                    float(ball.z),
                    float(ball.r * self._render_scale),
                )
            )
        return payload

    @property
    def count(self) -> int:
        return len(self._balls)
