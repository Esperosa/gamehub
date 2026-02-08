from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Protocol

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QRadialGradient

try:
    import numpy as np
except Exception:  # pragma: no cover - fallback path for missing numpy
    np = None  # type: ignore[assignment]


class BackgroundEffect(Protocol):
    def resize(self, old_w: int, old_h: int, new_w: int, new_h: int) -> None: ...
    def tick(self, width: int, height: int, elapsed_s: float) -> None: ...
    def paint(self, painter: QPainter, width: int, height: int, elapsed_s: float) -> None: ...


@dataclass
class Particle:
    x: float
    y: float
    r: float
    vx: float
    vy: float
    alpha: float


class ParticleEffect:
    def __init__(self, initial_count: int = 120):
        self._particles: List[Particle] = []
        self._initial_count = max(1, int(initial_count))

    def _seed_particles(self, count: int, width: int, height: int) -> None:
        w = max(1, width)
        h = max(1, height)
        for _ in range(count):
            radius = random.uniform(1.1, 3.2)
            self._particles.append(
                Particle(
                    x=random.uniform(0, w),
                    y=random.uniform(0, h),
                    r=radius,
                    vx=random.uniform(-0.20, 0.20),
                    vy=random.uniform(-0.16, 0.16),
                    alpha=random.uniform(0.10, 0.34),
                )
            )

    def resize(self, old_w: int, old_h: int, new_w: int, new_h: int) -> None:
        old_w = max(1, old_w)
        old_h = max(1, old_h)
        new_w = max(1, new_w)
        new_h = max(1, new_h)

        target = int((new_w * new_h) / 6000)
        target = max(90, min(260, target))
        target = max(target, self._initial_count)

        if not self._particles:
            self._seed_particles(target, width=new_w, height=new_h)
            return

        sx = new_w / old_w
        sy = new_h / old_h
        for particle in self._particles:
            particle.x *= sx
            particle.y *= sy

        if len(self._particles) < target:
            self._seed_particles(target - len(self._particles), width=new_w, height=new_h)
        elif len(self._particles) > target:
            self._particles = self._particles[:target]

    def tick(self, width: int, height: int, elapsed_s: float) -> None:
        del elapsed_s
        w = max(1, width)
        h = max(1, height)
        for particle in self._particles:
            particle.x += particle.vx
            particle.y += particle.vy
            if particle.x < -10:
                particle.x = w + 10
            if particle.x > w + 10:
                particle.x = -10
            if particle.y < -10:
                particle.y = h + 10
            if particle.y > h + 10:
                particle.y = -10

    def paint(self, painter: QPainter, width: int, height: int, elapsed_s: float) -> None:
        del width, height, elapsed_s
        for particle in self._particles:
            halo_alpha = int(255 * min(1.0, particle.alpha * 0.65))
            core_alpha = int(255 * min(1.0, particle.alpha * 1.20))

            painter.setBrush(QColor(138, 230, 255, halo_alpha))
            painter.setPen(QColor(0, 0, 0, 0))
            painter.drawEllipse(QPointF(particle.x, particle.y), particle.r * 2.2, particle.r * 2.2)

            painter.setBrush(QColor(245, 253, 255, core_alpha))
            painter.setPen(QColor(0, 0, 0, 0))
            painter.drawEllipse(QPointF(particle.x, particle.y), particle.r, particle.r)


@dataclass
class Metaball:
    x: float
    y: float
    r: float
    vx: float
    vy: float
    phase: float
    strength: float


class MetaballEffect:
    def __init__(self, initial_count: int = 10):
        self._metaballs: List[Metaball] = []
        self._initial_count = max(2, int(initial_count))
        self._grid_size: Optional[tuple[int, int]] = None
        self._grid_x = None
        self._grid_y = None
        self._image_bytes: Optional[bytes] = None

    def _seed_metaballs(self, count: int, width: int, height: int) -> None:
        w = max(1, width)
        h = max(1, height)
        base_radius = max(24.0, min(88.0, min(w, h) * 0.072))
        for _ in range(count):
            # Keep most blobs in the central field so interactions are visible.
            if random.random() < 0.55:
                px = random.uniform(w * 0.16, w * 0.84)
                py = random.uniform(h * 0.16, h * 0.84)
            else:
                px = random.uniform(0, w)
                py = random.uniform(0, h)
            self._metaballs.append(
                Metaball(
                    x=px,
                    y=py,
                    r=random.uniform(base_radius * 0.72, base_radius * 1.62),
                    vx=random.uniform(-0.26, 0.26),
                    vy=random.uniform(-0.22, 0.22),
                    phase=random.uniform(0.0, math.tau),
                    strength=random.uniform(0.70, 1.00),
                )
            )

    def _ensure_grid(self, width: int, height: int) -> tuple[int, int]:
        assert np is not None
        pixels = width * height
        if pixels <= 1_000_000:
            downsample = 2
        elif pixels <= 2_200_000:
            downsample = 3
        else:
            downsample = 4
        gw = max(220, width // downsample)
        gh = max(140, height // downsample)
        if self._grid_size != (gw, gh):
            xs = np.linspace(0.0, float(width), gw, dtype=np.float32)
            ys = np.linspace(0.0, float(height), gh, dtype=np.float32)
            self._grid_x, self._grid_y = np.meshgrid(xs, ys)
            self._grid_size = (gw, gh)
        return gw, gh

    def resize(self, old_w: int, old_h: int, new_w: int, new_h: int) -> None:
        old_w = max(1, old_w)
        old_h = max(1, old_h)
        new_w = max(1, new_w)
        new_h = max(1, new_h)

        # Keep deterministic count for visual debugging.
        target = self._initial_count

        if not self._metaballs:
            self._seed_metaballs(target, width=new_w, height=new_h)
            self._grid_size = None
            self._grid_x = None
            self._grid_y = None
            return

        sx = new_w / old_w
        sy = new_h / old_h
        scale = math.sqrt((sx * sx + sy * sy) * 0.5)
        for metaball in self._metaballs:
            metaball.x *= sx
            metaball.y *= sy
            metaball.r *= scale

        if len(self._metaballs) < target:
            self._seed_metaballs(target - len(self._metaballs), width=new_w, height=new_h)
        elif len(self._metaballs) > target:
            self._metaballs = self._metaballs[:target]

        self._grid_size = None
        self._grid_x = None
        self._grid_y = None

    def tick(self, width: int, height: int, elapsed_s: float) -> None:
        w = max(1, width)
        h = max(1, height)
        n = len(self._metaballs)
        if n <= 0:
            return

        # Local-only interaction: influence only near other blobs and modulated over time
        # so connections form and then naturally split again.
        for i in range(n):
            a = self._metaballs[i]
            for j in range(i + 1, n):
                b = self._metaballs[j]
                dx = b.x - a.x
                dy = b.y - a.y
                dist2 = dx * dx + dy * dy
                if dist2 <= 1e-6:
                    continue
                dist = math.sqrt(dist2)
                nx = dx / dist
                ny = dy / dist

                sum_r = a.r + b.r
                interaction_range = sum_r * 1.55
                if dist > interaction_range:
                    continue

                closeness = 1.0 - (dist / interaction_range)
                window = 0.5 + 0.5 * math.sin(elapsed_s * 0.9 + a.phase - b.phase)

                # Attract only when reasonably close and only during active window.
                if dist > sum_r * 0.78:
                    pull_strength = (0.0065 + 0.010 * window) * closeness
                    ax = nx * pull_strength
                    ay = ny * pull_strength
                    a.vx += ax
                    a.vy += ay
                    b.vx -= ax
                    b.vy -= ay
                else:
                    # Short-range repulsion to allow separation after merge.
                    repel = (sum_r * 0.78 - dist) / max(sum_r * 0.78, 1e-6)
                    repel_strength = 0.028 * repel
                    ax = nx * repel_strength
                    ay = ny * repel_strength
                    a.vx -= ax
                    a.vy -= ay
                    b.vx += ax
                    b.vy += ay

                # Tangential swirl when close helps organic split/rejoin behavior.
                swirl = (0.0015 + 0.0030 * window) * closeness
                tx = -ny
                ty = nx
                a.vx += tx * swirl
                a.vy += ty * swirl
                b.vx -= tx * swirl
                b.vy -= ty * swirl

        for metaball in self._metaballs:
            # Mild phase-driven drift keeps long-term motion alive without global center collapse.
            metaball.vx += 0.0026 * math.cos(elapsed_s * 0.75 + metaball.phase)
            metaball.vy += 0.0026 * math.sin(elapsed_s * 0.82 + metaball.phase * 1.07)

            metaball.vx *= 0.986
            metaball.vy *= 0.986

            speed = math.hypot(metaball.vx, metaball.vy)
            max_speed = 0.40
            if speed > max_speed:
                scale = max_speed / speed
                metaball.vx *= scale
                metaball.vy *= scale

            metaball.x += metaball.vx
            metaball.y += metaball.vy

            margin = metaball.r * 0.55
            if metaball.x < margin:
                metaball.x = margin
                metaball.vx = abs(metaball.vx) * 0.92
            elif metaball.x > w - margin:
                metaball.x = w - margin
                metaball.vx = -abs(metaball.vx) * 0.92
            if metaball.y < margin:
                metaball.y = margin
                metaball.vy = abs(metaball.vy) * 0.92
            elif metaball.y > h - margin:
                metaball.y = h - margin
                metaball.vy = -abs(metaball.vy) * 0.92

        # Gentle anti-collapse only; allow overlaps so metaball effect is visible.
        n = len(self._metaballs)
        for i in range(n):
            a = self._metaballs[i]
            for j in range(i + 1, n):
                b = self._metaballs[j]
                dx = a.x - b.x
                dy = a.y - b.y
                dist2 = dx * dx + dy * dy
                if dist2 <= 1e-6:
                    dx = random.uniform(-1.0, 1.0)
                    dy = random.uniform(-1.0, 1.0)
                    dist2 = dx * dx + dy * dy
                dist = math.sqrt(dist2)
                min_dist = (a.r + b.r) * 0.30
                if dist < min_dist:
                    push = (min_dist - dist) / max(dist, 1e-6)
                    px = dx * push * 0.10
                    py = dy * push * 0.10
                    a.x += px
                    a.y += py
                    b.x -= px
                    b.y -= py

    def _paint_numpy(self, painter: QPainter, width: int, height: int, elapsed_s: float) -> None:
        assert np is not None
        gw, gh = self._ensure_grid(width, height)
        xx = self._grid_x
        yy = self._grid_y
        assert xx is not None and yy is not None

        field = np.zeros((gh, gw), dtype=np.float32)
        for metaball in self._metaballs:
            radius = metaball.r * (1.0 + 0.10 * math.sin(elapsed_s * 1.10 + metaball.phase))
            radius_sq = max(1.0, radius * radius)
            dx = xx - metaball.x
            dy = yy - metaball.y
            t = 1.0 - ((dx * dx + dy * dy) / radius_sq)
            np.clip(t, 0.0, None, out=t)
            t2 = t * t
            field += metaball.strength * (t2 * t)

        threshold = 0.62
        soft = 0.08
        mask = np.clip((field - (threshold - soft)) / (2.0 * soft), 0.0, 1.0)
        mask = mask * mask * (3.0 - 2.0 * mask)  # smoothstep
        if float(mask.max()) <= 0.001:
            return

        # Surface normals from field gradient -> more bubble-like shading.
        gy, gx = np.gradient(field)
        nx = -gx
        ny = -gy
        nz = np.full_like(field, 0.72, dtype=np.float32)
        norm = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-6
        nx /= norm
        ny /= norm
        nz /= norm

        lx, ly, lz = (-0.34, -0.22, 0.92)
        diff = np.clip(nx * lx + ny * ly + nz * lz, 0.0, 1.0)
        spec = np.power(np.clip(2.0 * diff - 1.0, 0.0, 1.0), 12.0)
        fres = np.power(1.0 - np.clip(nz, 0.0, 1.0), 2.8)
        interior = np.clip((field - threshold) / 0.55, 0.0, 1.0)

        alpha = mask * (170.0 + interior * 70.0)
        red = 36.0 + interior * 46.0 + diff * 34.0 + spec * 78.0 + fres * 20.0
        green = 114.0 + interior * 58.0 + diff * 44.0 + spec * 85.0 + fres * 24.0
        blue = 182.0 + interior * 52.0 + diff * 36.0 + spec * 92.0 + fres * 16.0

        rgba = np.empty((gh, gw, 4), dtype=np.uint8)
        rgba[..., 0] = np.clip(red, 0.0, 255.0).astype(np.uint8)
        rgba[..., 1] = np.clip(green, 0.0, 255.0).astype(np.uint8)
        rgba[..., 2] = np.clip(blue, 0.0, 255.0).astype(np.uint8)
        rgba[..., 3] = np.clip(alpha, 0.0, 255.0).astype(np.uint8)

        self._image_bytes = rgba.tobytes()
        image = QImage(self._image_bytes, gw, gh, gw * 4, QImage.Format_RGBA8888)
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawImage(
            QRectF(0.0, 0.0, float(width), float(height)),
            image,
            QRectF(0.0, 0.0, float(gw), float(gh)),
        )
        painter.restore()

    def _paint_fallback(self, painter: QPainter, elapsed_s: float) -> None:
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode_Plus)
        for metaball in self._metaballs:
            radius = metaball.r * (1.0 + 0.10 * math.sin(elapsed_s * 1.10 + metaball.phase))
            gradient = QRadialGradient(QPointF(metaball.x, metaball.y), radius)
            gradient.setColorAt(0.0, QColor(102, 216, 250, 64))
            gradient.setColorAt(0.45, QColor(68, 152, 216, 44))
            gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(gradient))
            painter.setPen(QColor(0, 0, 0, 0))
            painter.drawEllipse(QPointF(metaball.x, metaball.y), radius, radius)
        painter.restore()

    def paint(self, painter: QPainter, width: int, height: int, elapsed_s: float) -> None:
        if not self._metaballs:
            return
        if np is not None:
            self._paint_numpy(painter, width, height, elapsed_s)
        else:
            self._paint_fallback(painter, elapsed_s)
