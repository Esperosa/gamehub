from __future__ import annotations

import math
import time
from typing import Dict

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from hub.animations import BackgroundEffect, MetaballEffect, ParticleEffect


class FallbackAnimatedBackground(QWidget):
    """CPU fallback background used when GPU renderer is unavailable."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._t0 = time.time()
        self._last_size = self.size()
        self._effect_mode = "particles"

        self._effects: Dict[str, BackgroundEffect] = {
            "particles": ParticleEffect(initial_count=120),
            "metaballs": MetaballEffect(initial_count=10),
        }

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_effect_mode(self, mode: str) -> None:
        normalized = (mode or "").strip().lower()
        if normalized == "metaballs":
            # TODO(metaballs): Re-enable fallback metaballs mode once production-ready.
            normalized = "particles"
        if normalized not in self._effects:
            normalized = "particles"
        self._effect_mode = "particles"
        self.update()

    @property
    def effect_mode(self) -> str:
        return self._effect_mode

    def _tick(self) -> None:
        elapsed = time.time() - self._t0
        self._effects[self._effect_mode].tick(max(1, self.width()), max(1, self.height()), elapsed)
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        old = event.oldSize()
        old_w = old.width() if old.width() > 0 else self._last_size.width()
        old_h = old.height() if old.height() > 0 else self._last_size.height()
        new_w = max(1, self.width())
        new_h = max(1, self.height())
        for effect in self._effects.values():
            effect.resize(max(1, old_w), max(1, old_h), new_w, new_h)
        self._last_size = self.size()

    def paintEvent(self, event) -> None:
        del event
        elapsed = time.time() - self._t0
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0.0, QColor(8, 10, 16))
        base.setColorAt(1.0, QColor(4, 6, 10))
        painter.fillRect(self.rect(), base)

        def blob(cx: float, cy: float, radius: float, color: QColor) -> None:
            grad = QRadialGradient(QPointF(cx, cy), radius)
            grad.setColorAt(0.0, color)
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(grad))
            painter.setPen(QColor(0, 0, 0, 0))
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

        cx1 = w * (0.25 + 0.05 * math.sin(elapsed * 0.22))
        cy1 = h * (0.30 + 0.05 * math.cos(elapsed * 0.18))
        cx2 = w * (0.80 + 0.04 * math.cos(elapsed * 0.17))
        cy2 = h * (0.65 + 0.06 * math.sin(elapsed * 0.14))
        cx3 = w * (0.55 + 0.05 * math.sin(elapsed * 0.11))
        cy3 = h * (0.15 + 0.05 * math.cos(elapsed * 0.13))

        blob(cx1, cy1, max(w, h) * 0.55, QColor(110, 231, 255, 45))
        blob(cx2, cy2, max(w, h) * 0.65, QColor(167, 139, 250, 38))
        blob(cx3, cy3, max(w, h) * 0.50, QColor(34, 211, 238, 26))

        self._effects[self._effect_mode].paint(painter, w, h, elapsed)

        vignette = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.72)
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 150))
        painter.fillRect(self.rect(), vignette)
