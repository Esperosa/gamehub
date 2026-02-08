from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Sequence


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    r: float
    alpha: float


class ParticleSimulation:
    """Fast particle field simulation for GPU sprite-style rendering."""

    def __init__(self, count: int = 112, seed: int = 2024):
        self._rng = random.Random(seed)
        self._particles: List[Particle] = []
        self._target_count = max(72, min(150, int(count)))
        self._width = 1
        self._height = 1

    def resize(self, width: int, height: int) -> None:
        prev_w = self._width
        prev_h = self._height
        self._width = max(1, int(width))
        self._height = max(1, int(height))

        target = int((self._width * self._height) / 7000)
        target = max(88, min(112, target))
        self._target_count = target

        if not self._particles:
            self._spawn_initial()
            return

        sx = self._width / max(1.0, float(prev_w))
        sy = self._height / max(1.0, float(prev_h))
        for p in self._particles:
            p.x *= sx
            p.y *= sy
            p.r *= (sx + sy) * 0.5

        self._reconcile_count()

    def _spawn_initial(self) -> None:
        self._particles.clear()
        for _ in range(self._target_count):
            self._particles.append(
                Particle(
                    x=self._rng.uniform(0.0, float(self._width)),
                    y=self._rng.uniform(0.0, float(self._height)),
                    vx=self._rng.uniform(-6.4, 6.4),
                    vy=self._rng.uniform(-5.2, 5.2),
                    r=self._rng.uniform(1.8, 6.8),
                    alpha=self._rng.uniform(0.32, 0.88),
                )
            )

    def _reconcile_count(self) -> None:
        n = len(self._particles)
        if n < self._target_count:
            for _ in range(self._target_count - n):
                self._particles.append(
                    Particle(
                        x=self._rng.uniform(0.0, float(self._width)),
                        y=self._rng.uniform(0.0, float(self._height)),
                        vx=self._rng.uniform(-6.4, 6.4),
                        vy=self._rng.uniform(-5.2, 5.2),
                        r=self._rng.uniform(1.8, 6.8),
                        alpha=self._rng.uniform(0.32, 0.88),
                    )
                )
        elif n > self._target_count:
            self._particles = self._particles[: self._target_count]

    def step(self, dt: float) -> None:
        if not self._particles:
            return
        dt = max(0.0, min(1.0 / 30.0, float(dt)))
        if dt <= 0.0:
            return

        w = float(self._width)
        h = float(self._height)
        for p in self._particles:
            p.x += p.vx * dt
            p.y += p.vy * dt

            if p.x < -12.0:
                p.x = w + 12.0
            elif p.x > w + 12.0:
                p.x = -12.0
            if p.y < -12.0:
                p.y = h + 12.0
            elif p.y > h + 12.0:
                p.y = -12.0

    def shader_uniform_payload(self, max_count: int = 112) -> Sequence[float]:
        if self._width <= 0 or self._height <= 0:
            return []
        inv_w = 1.0 / float(self._width)
        inv_h = 1.0 / float(self._height)
        inv_min = 1.0 / float(max(1, min(self._width, self._height)))
        payload: List[float] = []
        for p in self._particles[:max_count]:
            payload.extend(
                (
                    float(p.x * inv_w),
                    float(p.y * inv_h),
                    float(p.r * inv_min),
                    float(p.alpha),
                )
            )
        return payload
