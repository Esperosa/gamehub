from __future__ import annotations

from typing import Optional, Callable

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QCursor, QIcon, QResizeEvent
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QHBoxLayout, QSizePolicy


class GameCard(QFrame):
    """Responsive clickable card with prominent decorative graphics."""

    def __init__(
        self,
        title: str,
        desc: str,
        on_click: Optional[Callable[[], None]] = None,
        icon: Optional[QIcon] = None,
        graphic_text: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("GameCard")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._on_click = on_click
        self._graphic_text = graphic_text
        self._title = title
        self._icon = icon

        # Responsive size - expands to fill available space
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(100, 80)

        # Use CSS-based styling (base styles, fonts updated dynamically)
        self.setStyleSheet("""
            QFrame#GameCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(30,35,50,0.56), stop:1 rgba(20,24,36,0.62));
                border: 1px solid rgba(110,231,255,0.26);
                border-radius: 16px;
            }
            QFrame#GameCard:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(45,52,75,0.72), stop:1 rgba(30,36,55,0.78));
                border: 2px solid rgba(110,231,255,0.62);
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        # Large decorative graphic at top - THIS IS THE MAIN VISUAL
        self._graphic_label = QLabel()
        self._graphic_label.setAlignment(Qt.AlignCenter)
        self._graphic_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self._graphic_label, 3)

        # Title - centered, compact
        self._title_label = QLabel(title)
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setWordWrap(True)
        self._title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(self._title_label, 1)

        # Play hint at bottom
        self._play_hint = QLabel("▶ Hrát")
        self._play_hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._play_hint)

        # Initial update
        self._update_font_sizes()

    def hasHeightForWidth(self) -> bool:
        # Keep card sizing controlled by the grid, not by multiline label content.
        return False

    def sizeHint(self) -> QSize:
        return QSize(140, 140)

    def minimumSizeHint(self) -> QSize:
        return QSize(80, 80)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_font_sizes()

    def _update_font_sizes(self) -> None:
        """Update font sizes based on card dimensions."""
        w = self.width()
        h = self.height()

        # Use smaller dimension for proportional scaling
        size = min(w, h)

        # Graphic: ~35% of card size
        graphic_font_size = max(16, int(size * 0.30))

        # Title: ~10% of card size
        title_font_size = max(9, int(size * 0.09))

        # Play hint: ~7% of card size
        hint_font_size = max(8, int(size * 0.065))

        # Update graphic label
        if self._graphic_text:
            lines = self._graphic_text.splitlines() or [self._graphic_text]
            line_count = len(lines)
            max_line_len = max(len(line.strip()) for line in lines)

            # Multi-line or long glyph groups need a smaller scale to avoid clipping.
            text_scale = 0.30
            if line_count > 1:
                text_scale *= 0.72
            if max_line_len >= 6:
                text_scale *= 0.9
            if max_line_len >= 10:
                text_scale *= 0.8

            text_font_size = max(14, int(size * text_scale))
            letter_spacing = 0 if line_count > 1 else max(1, text_font_size // 12)

            self._graphic_label.setText(self._graphic_text)
            self._graphic_label.setWordWrap(line_count > 1)
            self._graphic_label.setStyleSheet(f"""
                font-size: {text_font_size}px;
                color: rgba(110,231,255,0.9);
                letter-spacing: {letter_spacing}px;
            """)
        elif self._icon is not None:
            icon_size = max(24, int(size * 0.35))
            self._graphic_label.setPixmap(self._icon.pixmap(icon_size, icon_size))
        else:
            first_char = self._title[:1].upper() if self._title else "🎮"
            self._graphic_label.setText(first_char)
            self._graphic_label.setStyleSheet(f"""
                font-size: {graphic_font_size}px;
                font-weight: 700;
                color: rgba(110,231,255,0.9);
            """)

        # Update title
        self._title_label.setStyleSheet(f"""
            font-size: {title_font_size}px;
            font-weight: 600;
            color: rgba(255,255,255,0.95);
            background: transparent;
        """)

        # Update play hint
        self._play_hint.setStyleSheet(f"""
            font-size: {hint_font_size}px;
            color: rgba(110,231,255,0.6);
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._on_click:
            self._on_click()
        super().mousePressEvent(event)
