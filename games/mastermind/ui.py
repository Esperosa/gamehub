"""
Mastermind UI - Modern game interface

Features:
- Classic code-breaking gameplay
- Color picker for guesses
- Feedback pegs (black/white)
- Multiple difficulty settings
- Victory celebration
"""

from __future__ import annotations

import math
import random
import time
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, QRectF, QVariantAnimation, QEasingCurve, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QBrush, QLinearGradient, QRadialGradient
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame

# Import engine from the same directory
_this_dir = Path(__file__).resolve().parent
_engine_spec = importlib.util.spec_from_file_location("mastermind_engine", _this_dir / "engine.py")
_engine_module = importlib.util.module_from_spec(_engine_spec)
import sys

sys.modules["mastermind_engine"] = _engine_module
_engine_spec.loader.exec_module(_engine_module)

Color = _engine_module.Color
COLOR_HEX = _engine_module.COLOR_HEX
create_game = _engine_module.create_game
make_guess = _engine_module.make_guess
suggest_guess = _engine_module.suggest_guess
count_remaining_possibilities = _engine_module.count_remaining_possibilities
MastermindGame = _engine_module.MastermindGame


# UI Colors
COLOR_PRIMARY = QColor(110, 231, 255)  # Cyan
COLOR_SECONDARY = QColor(167, 139, 250)  # Purple
COLOR_BACKGROUND = QColor(30, 32, 40)
COLOR_CARD = QColor(40, 44, 55)
COLOR_TEXT = QColor(255, 255, 255)
COLOR_MUTED = QColor(180, 180, 180)
COLOR_BLACK_PEG = QColor(20, 20, 20)
COLOR_WHITE_PEG = QColor(240, 240, 240)
COLOR_EMPTY_SLOT = QColor(60, 65, 80)


# Game color palette
GAME_COLORS = [
    QColor("#E53935"),  # Red
    QColor("#43A047"),  # Green
    QColor("#1E88E5"),  # Blue
    QColor("#FDD835"),  # Yellow
    QColor("#FB8C00"),  # Orange
    QColor("#8E24AA"),  # Purple
    QColor("#00ACC1"),  # Cyan
    QColor("#EC407A"),  # Pink
]


class ConfettiParticle:
    def __init__(self, x, y, vx, vy, life, size, color):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.age = 0.0
        self.size = size
        self.color = color


class MastermindBoard(QWidget):
    """Interactive Mastermind game board."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 600)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        self.game: Optional[MastermindGame] = None
        self.current_guess: List[Optional[Color]] = []
        self.selected_slot: int = 0

        # Geometry caches
        self._slot_rects: List[QRectF] = []
        self._color_rects: List[QRectF] = []
        self._history_panel_rect: Optional[QRectF] = None
        self._history_scroll = 0.0
        self._history_max_scroll = 0.0
        self._history_hover = 0.0
        self._history_hover_target = False
        self._history_hover_anim: Optional[QVariantAnimation] = None

        # Confetti
        self._confetti: List[ConfettiParticle] = []
        self._confetti_timer: Optional[QTimer] = None
        self._last_confetti_tick = time.time()

        # Overlay
        self._overlay_visible = False
        self._overlay_opacity = 0.0
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._overlay_button_callback = None
        self._overlay_button_rect: Optional[QRectF] = None

        # Callbacks
        self.on_complete = None

    def set_game(self, game: MastermindGame) -> None:
        """Set a new game state."""
        self.game = game
        self.current_guess = [None] * game.code_length
        self.selected_slot = 0
        self._history_scroll = 0.0
        self._history_max_scroll = 0.0
        self._history_panel_rect = None
        self._set_history_hover(False, immediate=True)
        self._stop_confetti()
        self._hide_overlay()
        self.update()

    def _board_geometry(self) -> Tuple[float, float, float, float]:
        """Calculate board layout."""
        w, h = self.width(), self.height()
        margin = 20
        board_w = w - 2 * margin
        board_h = h - 2 * margin
        return margin, margin, board_w, board_h

    def _layout_regions(self) -> Tuple[QRectF, Optional[QRectF]]:
        left, top, board_w, board_h = self._board_geometry()
        full = QRectF(left, top, board_w, board_h)

        # Narrow layouts: keep single-column rendering.
        if board_w < 760:
            return full, None

        gap = 16.0
        panel_w = max(220.0, min(330.0, board_w * 0.34))
        play_w = board_w - panel_w - gap
        if play_w < 320.0:
            panel_w = max(180.0, board_w - 320.0 - gap)
            play_w = board_w - panel_w - gap
        if panel_w < 180.0 or play_w < 300.0:
            return full, None

        play_rect = QRectF(left, top, play_w, board_h)
        panel_rect = QRectF(play_rect.right() + gap, top, panel_w, board_h)
        return play_rect, panel_rect

    def _set_history_hover(self, hovered: bool, immediate: bool = False) -> None:
        if hovered == self._history_hover_target and not immediate:
            return
        self._history_hover_target = hovered
        target = 1.0 if hovered else 0.0
        if immediate:
            self._history_hover = target
            self.update()
            return

        if self._history_hover_anim:
            self._history_hover_anim.stop()
            self._history_hover_anim = None
        anim = QVariantAnimation(self)
        anim.setDuration(160)
        anim.setStartValue(self._history_hover)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _on_val(v):
            self._history_hover = float(v)
            self.update()

        anim.valueChanged.connect(_on_val)
        anim.start()
        self._history_hover_anim = anim

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return

        pos = event.position()

        # Check overlay button
        if self._overlay_visible and self._overlay_button_callback and self._overlay_button_rect:
            if self._overlay_button_rect.contains(pos):
                callback = self._overlay_button_callback
                self._hide_overlay()
                callback()
                return

        if not self.game or self.game.is_over:
            return

        # Check current guess slots
        for i, rect in enumerate(self._slot_rects):
            if rect.contains(pos):
                self.selected_slot = i
                self.update()
                return

        # Check color picker
        for i, rect in enumerate(self._color_rects):
            if rect.contains(pos):
                if i < len(self.game.available_colors()):
                    color = self.game.available_colors()[i]
                    self.current_guess[self.selected_slot] = color
                    # Move to next slot
                    if self.selected_slot < self.game.code_length - 1:
                        self.selected_slot += 1
                    self.update()
                return

    def mouseMoveEvent(self, event) -> None:
        _, panel_rect = self._layout_regions()
        hovered = panel_rect is not None and panel_rect.contains(event.position())
        self._set_history_hover(hovered)

    def leaveEvent(self, event) -> None:
        self._set_history_hover(False)
        super().leaveEvent(event)

    def wheelEvent(self, event) -> None:
        _, panel_rect = self._layout_regions()
        if (
            panel_rect is not None
            and panel_rect.contains(event.position())
            and self._history_max_scroll > 0.0
        ):
            step = 34.0
            self._history_scroll -= (event.angleDelta().y() / 120.0) * step
            self._history_scroll = max(0.0, min(self._history_scroll, self._history_max_scroll))
            self.update()
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:
        if not self.game or self.game.is_over:
            return

        key = event.key()

        # Navigate slots
        if key == Qt.Key_Left:
            self.selected_slot = max(0, self.selected_slot - 1)
            self.update()
        elif key == Qt.Key_Right:
            self.selected_slot = min(self.game.code_length - 1, self.selected_slot + 1)
            self.update()
        elif key == Qt.Key_Return or key == Qt.Key_Enter:
            self._submit_guess()
        elif key == Qt.Key_Backspace or key == Qt.Key_Delete:
            self.current_guess[self.selected_slot] = None
            self.update()
        elif Qt.Key_1 <= key <= Qt.Key_8:
            # Quick color selection with number keys
            idx = key - Qt.Key_1
            if idx < self.game.num_colors:
                self.current_guess[self.selected_slot] = self.game.available_colors()[idx]
                if self.selected_slot < self.game.code_length - 1:
                    self.selected_slot += 1
                self.update()

    def _submit_guess(self) -> None:
        """Submit the current guess."""
        if not self.game or self.game.is_over:
            return

        # Check if all slots are filled
        if None in self.current_guess:
            return

        # Make the guess
        feedback = make_guess(self.game, self.current_guess)

        # Reset current guess
        self.current_guess = [None] * self.game.code_length
        self.selected_slot = 0
        self.update()

        # Check for win/loss
        if self.game.is_won:
            self._celebrate()
            if self.on_complete:
                self.on_complete()
        elif self.game.is_lost:
            self._show_loss()

    def submit_guess(self) -> None:
        """Public method to submit guess."""
        self._submit_guess()

    def show_hint(self) -> None:
        """Fill current guess with AI suggestion."""
        if not self.game or self.game.is_over:
            return

        suggested = suggest_guess(self.game)
        self.current_guess = list(suggested)
        self.selected_slot = 0
        self.update()

    def _celebrate(self) -> None:
        """Start victory celebration."""
        self._start_confetti()
        attempts = len(self.game.guesses)
        self._show_overlay(
            "Výborně!",
            f"Uhádli jste kód na {attempts}. pokus!",
            "Nová hra",
            lambda: self._request_new_game(),
        )

    def _show_loss(self) -> None:
        """Show loss screen."""
        secret_str = " ".join([f"•" for _ in self.game.secret])
        self._show_overlay(
            "Prohrál jste", f"Správný kód byl tajný", "Nová hra", lambda: self._request_new_game()
        )

    def _request_new_game(self) -> None:
        """Request a new game from parent widget."""
        parent = self.parent()
        while parent:
            if hasattr(parent, "new_game"):
                parent.new_game()
                return
            parent = parent.parent()

    def _start_confetti(self) -> None:
        """Start confetti animation."""
        if self._confetti_timer:
            return

        w, h = self.width(), self.height()
        colors = GAME_COLORS

        for _ in range(80):
            self._confetti.append(
                ConfettiParticle(
                    x=random.uniform(0, w),
                    y=random.uniform(-50, 0),
                    vx=random.uniform(-2, 2),
                    vy=random.uniform(2, 5),
                    life=random.uniform(2, 4),
                    size=random.uniform(4, 8),
                    color=random.choice(colors),
                )
            )

        self._confetti_timer = QTimer(self)
        self._confetti_timer.timeout.connect(self._update_confetti)
        self._confetti_timer.start(16)
        self._last_confetti_tick = time.time()

    def _stop_confetti(self) -> None:
        """Stop confetti animation."""
        if self._confetti_timer:
            self._confetti_timer.stop()
            self._confetti_timer = None
        self._confetti.clear()

    def _update_confetti(self) -> None:
        """Update confetti particles."""
        now = time.time()
        dt = now - self._last_confetti_tick
        self._last_confetti_tick = now

        h = self.height()
        alive = []

        for p in self._confetti:
            p.x += p.vx
            p.y += p.vy
            p.vy += 0.1  # gravity
            p.age += dt

            if p.age < p.life and p.y < h + 50:
                alive.append(p)

        self._confetti = alive

        if not self._confetti:
            self._confetti_timer.stop()
            self._confetti_timer = None

        self.update()

    def _show_overlay(self, title: str, subtitle: str, button_text: str, callback) -> None:
        """Show overlay with animation."""
        self._overlay_visible = True
        self._overlay_title = title
        self._overlay_subtitle = subtitle
        self._overlay_button_callback = callback

        anim = QVariantAnimation(self)
        anim.setDuration(300)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def on_val(v):
            self._overlay_opacity = float(v)
            self.update()

        anim.valueChanged.connect(on_val)
        anim.start()

    def _hide_overlay(self) -> None:
        """Hide overlay."""
        self._overlay_visible = False
        self._overlay_opacity = 0.0
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.game:
            self._draw_empty(painter)
            return

        # Draw game elements
        self._draw_current_guess(painter)
        self._draw_color_picker(painter)
        self._draw_info(painter)
        # History panel is drawn after left-side controls so it can float above them.
        self._draw_guess_history(painter)

        # Draw overlay
        if self._overlay_visible:
            self._draw_overlay(painter)

        # Draw confetti on top
        self._draw_confetti(painter)

    def _draw_empty(self, painter: QPainter) -> None:
        """Draw empty state."""
        painter.setPen(QPen(COLOR_MUTED))
        font = QFont("Segoe UI", 14)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, "Klikněte na 'Nová hra' pro start")

    def _draw_guess_history(self, painter: QPainter) -> None:
        """Draw guess history; on wide layout in a dedicated right panel."""
        if not self.game:
            return

        play_rect, panel_rect = self._layout_regions()
        if panel_rect is None:
            # Compact fallback for narrower windows.
            self._history_panel_rect = None
            self._history_max_scroll = 0.0
            self._history_scroll = 0.0
            panel_rect = QRectF(
                play_rect.left(),
                play_rect.top(),
                play_rect.width(),
                max(120.0, play_rect.height() * 0.33),
            )
            hover = 0.0
        else:
            self._history_panel_rect = panel_rect
            hover = self._history_hover

        float_pad = 4.0 * hover
        panel_draw = panel_rect.adjusted(-float_pad, -float_pad, float_pad, float_pad)

        # Glow + bright hover lift.
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(130, 245, 255, int(22 + 30 * hover)))
        painter.drawRoundedRect(panel_draw.adjusted(-2, -2, 2, 2), 16, 16)

        bg_grad = QLinearGradient(panel_draw.topLeft(), panel_draw.bottomLeft())
        bg_grad.setColorAt(0.0, QColor(255, 255, 255, int(26 + 38 * hover)))
        bg_grad.setColorAt(1.0, QColor(255, 255, 255, int(11 + 20 * hover)))
        painter.setBrush(QBrush(bg_grad))
        painter.setPen(QPen(QColor(110, 231, 255, int(70 + 120 * hover)), 1.4))
        painter.drawRoundedRect(panel_draw, 14, 14)

        header_rect = QRectF(
            panel_draw.left() + 12, panel_draw.top() + 8, panel_draw.width() - 24, 24
        )
        painter.setPen(QPen(QColor(225, 245, 255)))
        painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
        painter.drawText(header_rect, Qt.AlignLeft | Qt.AlignVCenter, "Pokusy")
        painter.setPen(QPen(QColor(170, 180, 200)))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(
            header_rect,
            Qt.AlignRight | Qt.AlignVCenter,
            f"{len(self.game.guesses)}/{self.game.max_attempts}",
        )

        content = panel_draw.adjusted(10, 38, -10, -10)
        label_w = 24.0
        code_len = self.game.code_length
        peg_size = max(
            15.0,
            min(
                28.0,
                (content.width() - label_w - 14.0) / (code_len + 0.65 * code_len + 2.8),
            ),
        )
        peg_gap = max(3.0, peg_size * 0.16)
        fb_size = max(7.0, peg_size * 0.45)
        fb_gap = max(2.0, fb_size * 0.2)
        row_gap = max(3.0, peg_size * 0.2)
        row_height = peg_size + row_gap

        total_h = len(self.game.guesses) * row_height
        self._history_max_scroll = max(0.0, total_h - content.height())
        self._history_scroll = max(0.0, min(self._history_scroll, self._history_max_scroll))

        painter.setClipRect(content)
        start_y = content.top() - self._history_scroll
        for i, guess in enumerate(self.game.guesses):
            y = start_y + i * row_height
            if y + peg_size < content.top() - 4:
                continue
            if y > content.bottom() + 4:
                break

            painter.setPen(QPen(QColor(190, 200, 220)))
            painter.setFont(QFont("Segoe UI", max(8, int(peg_size * 0.42))))
            painter.drawText(
                QRectF(content.left(), y, label_w, peg_size), Qt.AlignCenter, f"{i + 1}"
            )

            peg_x = content.left() + label_w + 4.0
            for j, color in enumerate(guess.code):
                rect = QRectF(peg_x + j * (peg_size + peg_gap), y, peg_size, peg_size)
                self._draw_peg(painter, rect, GAME_COLORS[color])

            fb_x = peg_x + code_len * (peg_size + peg_gap) + max(6.0, peg_size * 0.22)
            for b in range(guess.feedback.black):
                bx = fb_x + b * (fb_size + fb_gap)
                rect = QRectF(bx, y + peg_size * 0.26, fb_size, fb_size)
                self._draw_feedback_peg(painter, rect, is_correct=True)
            for w in range(guess.feedback.white):
                wx = fb_x + (guess.feedback.black + w) * (fb_size + fb_gap)
                rect = QRectF(wx, y + peg_size * 0.26, fb_size, fb_size)
                self._draw_feedback_peg(painter, rect, is_correct=False)

        painter.setClipping(False)
        if self._history_max_scroll > 0.0:
            track = QRectF(panel_draw.right() - 5.0, content.top(), 2.5, content.height())
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 40))
            painter.drawRoundedRect(track, 2, 2)
            thumb_h = max(20.0, content.height() * (content.height() / max(total_h, 1.0)))
            thumb_y = content.top()
            if self._history_max_scroll > 0.0:
                thumb_y += (self._history_scroll / self._history_max_scroll) * (
                    content.height() - thumb_h
                )
            thumb = QRectF(track.left(), thumb_y, track.width(), thumb_h)
            painter.setBrush(QColor(110, 231, 255, 170))
            painter.drawRoundedRect(thumb, 2, 2)
        painter.restore()

    def _draw_current_guess(self, painter: QPainter) -> None:
        """Draw current guess slots."""
        if not self.game or self.game.is_over:
            return

        play_rect, panel_rect = self._layout_regions()
        left, top, board_w, board_h = (
            play_rect.left(),
            play_rect.top(),
            play_rect.width(),
            play_rect.height(),
        )

        # Slightly larger than history pegs, but still responsive.
        history_peg = max(
            30.0,
            min(
                board_w / (self.game.code_length + 2.2),
                board_h / (self.game.max_attempts + 3.6),
                150.0,
            ),
        )
        peg_size = max(42.0, min(180.0, history_peg * 1.38))
        slot_gap = max(10.0, peg_size * 0.18)
        row_gap = max(6.0, history_peg * 0.12)

        # Position current guess; on wide layout keep it independent of history panel.
        if panel_rect is not None:
            y = top + max(48.0, board_h * 0.44)
        else:
            history_height = len(self.game.guesses) * (history_peg + row_gap) + max(
                44.0, peg_size * 0.72
            )
            y = top + history_height

        # Reserve space using the same responsive picker sizing as _draw_color_picker.
        picker_peg = min(
            board_w / (self.game.num_colors + 1.8),
            board_h * 0.17,
            170.0,
        )
        picker_peg = max(36.0, picker_peg)
        picker_reserve = (
            picker_peg
            + max(40.0, picker_peg * 1.02)
            + max(20.0, picker_peg * 0.25)  # label + numeric hints breathing room
        )
        max_y = play_rect.bottom() - picker_reserve - peg_size
        y = min(y, max_y)

        # Center the guess slots
        total_width = self.game.code_length * peg_size + (self.game.code_length - 1) * slot_gap
        start_x = left + (board_w - total_width) / 2

        # Label
        painter.setPen(QPen(COLOR_PRIMARY))
        font = QFont("Segoe UI", max(11, int(peg_size * 0.24)), QFont.Bold)
        painter.setFont(font)
        painter.drawText(
            QRectF(left, y - 30, board_w, 25),
            Qt.AlignCenter,
            f"Pokus {len(self.game.guesses) + 1} z {self.game.max_attempts}",
        )

        self._slot_rects = []

        for i in range(self.game.code_length):
            x = start_x + i * (peg_size + slot_gap)
            rect = QRectF(x, y, peg_size, peg_size)
            self._slot_rects.append(rect)

            # Draw slot background
            is_selected = i == self.selected_slot

            if is_selected:
                # Selection highlight
                pad = max(2.0, peg_size * 0.06)
                highlight = rect.adjusted(-pad, -pad, pad, pad)
                painter.setPen(QPen(COLOR_PRIMARY, 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(highlight, 8, 8)

            color = self.current_guess[i]
            if color is not None:
                self._draw_peg(painter, rect, GAME_COLORS[color])
            else:
                # Empty slot
                painter.setPen(QPen(COLOR_EMPTY_SLOT, max(2, int(peg_size * 0.04))))
                painter.setBrush(QBrush(COLOR_EMPTY_SLOT.darker(120)))
                painter.drawEllipse(rect)

    def _draw_color_picker(self, painter: QPainter) -> None:
        """Draw color selection palette."""
        if not self.game or self.game.is_over:
            return

        play_rect, _panel_rect = self._layout_regions()
        left, top, board_w, board_h = (
            play_rect.left(),
            play_rect.top(),
            play_rect.width(),
            play_rect.height(),
        )

        num_colors = self.game.num_colors

        # Responsive color palette sizing.
        peg_size = min(
            board_w / (num_colors + 1.8),
            board_h * 0.17,
            170.0,
        )
        peg_size = max(36.0, peg_size)
        peg_gap = max(10.0, peg_size * 0.18)

        # Position picker at bottom
        total_width = num_colors * peg_size + (num_colors - 1) * peg_gap
        start_x = left + (board_w - total_width) / 2
        y = play_rect.bottom() - (peg_size + max(40.0, peg_size * 1.02))

        # Label
        painter.setPen(QPen(COLOR_MUTED))
        label_font_size = max(11, int(peg_size * 0.26))
        font = QFont("Segoe UI", label_font_size)
        painter.setFont(font)
        label_height = max(24.0, peg_size * 0.34)
        label_y = y - max(34.0, peg_size * 0.56)
        painter.drawText(
            QRectF(left, label_y, board_w, label_height),
            Qt.AlignCenter,
            "Vyberte barvu (nebo klávesy 1-8)",
        )

        self._color_rects = []

        for i, color_enum in enumerate(self.game.available_colors()):
            x = start_x + i * (peg_size + peg_gap)
            rect = QRectF(x, y, peg_size, peg_size)
            self._color_rects.append(rect)

            self._draw_peg(painter, rect, GAME_COLORS[color_enum])

            # Draw number hint
            painter.setPen(QPen(COLOR_MUTED))
            font = QFont("Segoe UI", max(9, int(peg_size * 0.18)))
            painter.setFont(font)
            painter.drawText(QRectF(x, y + peg_size + 4, peg_size, 18), Qt.AlignCenter, str(i + 1))

    def _draw_peg(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        """Draw a 3D-looking color peg."""
        # Gradient for 3D effect
        gradient = QRadialGradient(
            rect.center().x() - rect.width() * 0.2,
            rect.center().y() - rect.height() * 0.2,
            rect.width() * 0.7,
        )
        gradient.setColorAt(0, color.lighter(140))
        gradient.setColorAt(0.5, color)
        gradient.setColorAt(1, color.darker(130))

        painter.setPen(QPen(color.darker(150), 1))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(rect)

    def _draw_feedback_peg(self, painter: QPainter, rect: QRectF, is_correct: bool) -> None:
        """Draw a feedback peg with symbol.

        is_correct=True: White peg with green checkmark (correct color & position)
        is_correct=False: Black peg with red X (correct color, wrong position)
        """
        if is_correct:
            # White/light peg
            color = QColor(240, 240, 240)
        else:
            # Black/dark peg
            color = QColor(40, 40, 40)

        gradient = QRadialGradient(
            rect.center().x() - rect.width() * 0.2,
            rect.center().y() - rect.height() * 0.2,
            rect.width() * 0.6,
        )
        gradient.setColorAt(0, color.lighter(120))
        gradient.setColorAt(1, color.darker(110))

        painter.setPen(QPen(color.darker(130), 1))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(rect)

        # Draw symbol
        cx, cy = rect.center().x(), rect.center().y()
        s = rect.width() * 0.3  # symbol size

        if is_correct:
            # Green checkmark ✓
            painter.setPen(QPen(QColor("#2ECC71"), 2.5))
            painter.drawLine(QPointF(cx - s, cy), QPointF(cx - s * 0.3, cy + s * 0.7))
            painter.drawLine(QPointF(cx - s * 0.3, cy + s * 0.7), QPointF(cx + s, cy - s * 0.5))
        else:
            # Red cross ✗
            painter.setPen(QPen(QColor("#E74C3C"), 2.5))
            painter.drawLine(QPointF(cx - s, cy - s), QPointF(cx + s, cy + s))
            painter.drawLine(QPointF(cx + s, cy - s), QPointF(cx - s, cy + s))

    def _draw_info(self, painter: QPainter) -> None:
        """Draw game info."""
        if not self.game:
            return
        play_rect, _ = self._layout_regions()

        # Draw remaining possibilities (for advanced players)
        if self.game.guesses and not self.game.is_over:
            remaining = count_remaining_possibilities(self.game)

            painter.setPen(QPen(COLOR_MUTED))
            font = QFont("Segoe UI", 9)
            painter.setFont(font)
            text = f"Možných kódů: {remaining}"
            painter.drawText(
                QRectF(play_rect.left() + 8, play_rect.bottom() - 22, play_rect.width() - 16, 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                text,
            )

    def _draw_overlay(self, painter: QPainter) -> None:
        """Draw victory/loss overlay."""
        opacity = self._overlay_opacity

        # Dark background
        bg = QColor(0, 0, 0, int(180 * opacity))
        painter.fillRect(self.rect(), bg)

        center_y = self.height() / 2

        # Title
        painter.setPen(QPen(QColor(255, 255, 255, int(255 * opacity))))
        font = QFont("Segoe UI", 28, QFont.Bold)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, center_y - 60, self.width(), 50), Qt.AlignCenter, self._overlay_title
        )

        # Subtitle (show secret code if lost)
        if self.game and self.game.is_lost:
            # Draw secret code
            peg_size = max(24.0, min(44.0, self.width() / (self.game.code_length + 8.0)))
            peg_gap = max(4.0, peg_size * 0.18)
            total_w = self.game.code_length * peg_size + (self.game.code_length - 1) * peg_gap
            start_x = (self.width() - total_w) / 2
            y = center_y - 10

            for i, color in enumerate(self.game.secret):
                rect = QRectF(start_x + i * (peg_size + peg_gap), y, peg_size, peg_size)
                self._draw_peg(painter, rect, GAME_COLORS[color])
        else:
            painter.setPen(QPen(QColor(180, 180, 180, int(255 * opacity))))
            font = QFont("Segoe UI", 14)
            painter.setFont(font)
            painter.drawText(
                QRectF(0, center_y - 10, self.width(), 30), Qt.AlignCenter, self._overlay_subtitle
            )

        # Button
        btn_w, btn_h = 160, 45
        btn_x = (self.width() - btn_w) / 2
        btn_y = center_y + 40
        self._overlay_button_rect = QRectF(btn_x, btn_y, btn_w, btn_h)

        # Button gradient
        grad = QLinearGradient(btn_x, btn_y, btn_x, btn_y + btn_h)
        grad.setColorAt(0, QColor(110, 231, 255, int(255 * opacity)))
        grad.setColorAt(1, QColor(167, 139, 250, int(255 * opacity)))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(self._overlay_button_rect, 8, 8)

        # Button text
        painter.setPen(QPen(QColor(0, 0, 0, int(255 * opacity))))
        font = QFont("Segoe UI", 12, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self._overlay_button_rect, Qt.AlignCenter, "Nová hra")

    def _draw_confetti(self, painter: QPainter) -> None:
        """Draw confetti particles."""
        for p in self._confetti:
            alpha = 1.0 - (p.age / p.life)
            color = QColor(p.color)
            color.setAlphaF(alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPointF(p.x, p.y), p.size / 2, p.size / 2)


class MastermindWidget(QWidget):
    """Main Mastermind game widget with controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.new_game()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Top controls
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        # Difficulty buttons
        self._diff_label = QLabel("Obtížnost:")
        self._diff_label.setStyleSheet("color: #B4B4B4; font-size: 12px;")
        top_bar.addWidget(self._diff_label)

        self._difficulty = "medium"

        for diff, label in [("easy", "Lehká"), ("medium", "Střední"), ("hard", "Těžká")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(diff == self._difficulty)
            btn.setFixedHeight(32)
            btn.clicked.connect(lambda checked, d=diff: self._set_difficulty(d))
            btn.setStyleSheet(self._button_style(diff == self._difficulty))
            setattr(self, f"_btn_{diff}", btn)
            top_bar.addWidget(btn)

        top_bar.addStretch()

        # Code length selector
        self._len_label = QLabel("Délka kódu:")
        self._len_label.setStyleSheet("color: #B4B4B4; font-size: 12px;")
        top_bar.addWidget(self._len_label)

        self._code_length = 4

        for length in [4, 5, 6]:
            btn = QPushButton(str(length))
            btn.setCheckable(True)
            btn.setChecked(length == self._code_length)
            btn.setFixedSize(40, 32)
            btn.clicked.connect(lambda checked, l=length: self._set_code_length(l))
            btn.setStyleSheet(self._button_style(length == self._code_length))
            setattr(self, f"_btn_len_{length}", btn)
            top_bar.addWidget(btn)

        layout.addLayout(top_bar)

        # Game board
        self._board = MastermindBoard(self)
        self._board.on_complete = self._on_complete
        layout.addWidget(self._board, 1)

        # Bottom controls
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        self._btn_new = QPushButton("Nová hra")
        self._btn_new.setFixedHeight(40)
        self._btn_new.clicked.connect(self.new_game)
        self._btn_new.setStyleSheet(self._accent_button_style())
        bottom_bar.addWidget(self._btn_new)

        self._btn_hint = QPushButton("Nápověda")
        self._btn_hint.setFixedHeight(40)
        self._btn_hint.clicked.connect(self._board.show_hint)
        self._btn_hint.setStyleSheet(self._ghost_button_style())
        bottom_bar.addWidget(self._btn_hint)

        self._btn_submit = QPushButton("Potvrdit")
        self._btn_submit.setFixedHeight(40)
        self._btn_submit.clicked.connect(self._board.submit_guess)
        self._btn_submit.setStyleSheet(self._accent_button_style())
        bottom_bar.addWidget(self._btn_submit)

        layout.addLayout(bottom_bar)

    def _button_style(self, active: bool = False) -> str:
        if active:
            return """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #6EE7FF, stop:1 #A78BFA);
                    color: black;
                    border: none;
                    border-radius: 6px;
                    font-weight: bold;
                    padding: 4px 12px;
                }
            """
        return """
            QPushButton {
                background: rgba(255,255,255,0.1);
                color: #B4B4B4;
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 6px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.15);
                color: white;
            }
        """

    def _accent_button_style(self) -> str:
        return """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #6EE7FF, stop:1 #A78BFA);
                color: black;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8EEFFF, stop:1 #B79BFA);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5ED7EF, stop:1 #977BEA);
            }
        """

    def _ghost_button_style(self) -> str:
        return """
            QPushButton {
                background: transparent;
                color: #6EE7FF;
                border: 1px solid #6EE7FF;
                border-radius: 8px;
                font-size: 13px;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background: rgba(110, 231, 255, 0.1);
            }
            QPushButton:pressed {
                background: rgba(110, 231, 255, 0.2);
            }
        """

    def _set_difficulty(self, diff: str) -> None:
        """Change difficulty and start new game."""
        self._difficulty = diff

        # Update button states
        for d in ["easy", "medium", "hard"]:
            btn = getattr(self, f"_btn_{d}")
            btn.setChecked(d == diff)
            btn.setStyleSheet(self._button_style(d == diff))

        self.new_game()

    def _set_code_length(self, length: int) -> None:
        """Change code length and start new game."""
        self._code_length = length

        # Update button states
        for l in [4, 5, 6]:
            btn = getattr(self, f"_btn_len_{l}")
            btn.setChecked(l == length)
            btn.setStyleSheet(self._button_style(l == length))

        self.new_game()

    def new_game(self) -> None:
        """Start a new game with current settings."""
        # Difficulty affects number of colors and attempts
        if self._difficulty == "easy":
            num_colors = 4
            max_attempts = 12
        elif self._difficulty == "hard":
            num_colors = 8
            max_attempts = 8
        else:  # medium
            num_colors = 6
            max_attempts = 10

        game = create_game(
            code_length=self._code_length,
            num_colors=num_colors,
            max_attempts=max_attempts,
            allow_duplicates=True,
        )

        self._board.set_game(game)

    def _on_complete(self) -> None:
        """Called when game is won."""
        pass  # Overlay is shown by board
