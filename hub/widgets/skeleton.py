from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QLinearGradient, QColor
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QSizePolicy


class ShimmerBar(QWidget):
    """Simple shimmer bar used for skeleton loading."""

    def __init__(self, height: int = 12, radius: int = 6, parent=None):
        super().__init__(parent)
        self._offset = 0.0
        self._radius = radius
        self.setFixedHeight(height)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)

    def _tick(self):
        self._offset = (self._offset + 0.025) % 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()
        r = min(self._radius, h // 2)

        grad = QLinearGradient(0, 0, w, 0)
        a = max(0, self._offset - 0.15)
        b = self._offset
        c = min(1, self._offset + 0.15)
        grad.setColorAt(0.0, QColor(110, 231, 255, 20))
        grad.setColorAt(a, QColor(110, 231, 255, 35))
        grad.setColorAt(b, QColor(110, 231, 255, 60))
        grad.setColorAt(c, QColor(110, 231, 255, 35))
        grad.setColorAt(1.0, QColor(110, 231, 255, 20))

        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), r, r)
        painter.end()


class SkeletonCard(QFrame):
    """Square placeholder card matching GameCard design."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SkeletonCard")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setMinimumSize(80, 80)
        
        self.setStyleSheet("""
            QFrame#SkeletonCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(30,35,50,0.9), stop:1 rgba(20,24,36,0.95));
                border: 1px solid rgba(110,231,255,0.2);
                border-radius: 16px;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        # Large graphic placeholder at top
        graphic_placeholder = ShimmerBar(height=40, radius=8)
        graphic_placeholder.setFixedWidth(100)
        lay.addWidget(graphic_placeholder, alignment=Qt.AlignCenter)

        lay.addStretch(1)

        # Title placeholder
        title_bar = ShimmerBar(height=14, radius=6)
        title_bar.setFixedWidth(100)
        lay.addWidget(title_bar, alignment=Qt.AlignCenter)

        # Play hint placeholder
        play_bar = ShimmerBar(height=12, radius=4)
        play_bar.setFixedWidth(50)
        lay.addWidget(play_bar, alignment=Qt.AlignCenter)
