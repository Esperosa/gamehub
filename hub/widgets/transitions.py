from __future__ import annotations

from PySide6.QtWidgets import QWidget


def fade_in(widget: QWidget, duration_ms: int = 220):
    """
    Simple show widget - no animation to avoid QGraphicsEffect QPainter issues.
    The widget is simply shown immediately.
    """
    widget.show()
    widget.update()
