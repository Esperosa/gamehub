from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import List

from PySide6.QtCore import QTimer, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QRadialGradient, QLinearGradient, QBrush
from PySide6.QtWidgets import QWidget


@dataclass
class Particle:
    x: float
    y: float
    r: float
    vx: float
    vy: float
    alpha: float


class AnimatedBackground(QWidget):
    """Subtle neon nebula + drifting particles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._t0 = time.time()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

        self._particles: List[Particle] = []
        self._seed_particles(70)

    def _seed_particles(self, n: int) -> None:
        w = max(1, self.width())
        h = max(1, self.height())
        for _ in range(n):
            r = random.uniform(0.8, 2.3)
            self._particles.append(
                Particle(
                    x=random.uniform(0, w),
                    y=random.uniform(0, h),
                    r=r,
                    vx=random.uniform(-0.22, 0.22),
                    vy=random.uniform(-0.18, 0.18),
                    alpha=random.uniform(0.05, 0.18),
                )
            )

    def _tick(self) -> None:
        w = max(1, self.width())
        h = max(1, self.height())
        for p in self._particles:
            p.x += p.vx
            p.y += p.vy
            if p.x < -10: p.x = w + 10
            if p.x > w + 10: p.x = -10
            if p.y < -10: p.y = h + 10
            if p.y > h + 10: p.y = -10
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        target = int((self.width() * self.height()) / 22000)
        target = max(50, min(130, target))
        if len(self._particles) < target:
            self._seed_particles(target - len(self._particles))
        elif len(self._particles) > target:
            self._particles = self._particles[:target]

    def paintEvent(self, event) -> None:
        t = time.time() - self._t0
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Base background
        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0.0, QColor(8, 10, 16))
        base.setColorAt(1.0, QColor(4, 6, 10))
        painter.fillRect(self.rect(), base)

        # Nebula blobs
        def blob(cx, cy, radius, c1: QColor):
            grad = QRadialGradient(QPointF(cx, cy), radius)
            grad.setColorAt(0.0, c1)
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(grad))
            painter.setPen(QColor(0, 0, 0, 0))
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

        cx1 = w * (0.25 + 0.05 * math.sin(t * 0.22))
        cy1 = h * (0.30 + 0.05 * math.cos(t * 0.18))
        cx2 = w * (0.80 + 0.04 * math.cos(t * 0.17))
        cy2 = h * (0.65 + 0.06 * math.sin(t * 0.14))
        cx3 = w * (0.55 + 0.05 * math.sin(t * 0.11))
        cy3 = h * (0.15 + 0.05 * math.cos(t * 0.13))

        blob(cx1, cy1, max(w, h) * 0.55, QColor(110, 231, 255, 45))
        blob(cx2, cy2, max(w, h) * 0.65, QColor(167, 139, 250, 38))
        blob(cx3, cy3, max(w, h) * 0.50, QColor(34, 211, 238, 26))

        # Particles
        for p in self._particles:
            painter.setBrush(QColor(255, 255, 255, int(255 * p.alpha)))
            painter.setPen(QColor(0, 0, 0, 0))
            painter.drawEllipse(QPointF(p.x, p.y), p.r, p.r)

        # Vignette
        v = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.72)
        v.setColorAt(0.0, QColor(0, 0, 0, 0))
        v.setColorAt(1.0, QColor(0, 0, 0, 150))
        painter.fillRect(self.rect(), v)
