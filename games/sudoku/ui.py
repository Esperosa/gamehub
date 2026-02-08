"""
Sudoku UI - Modern game interface

Features:
- Multiple board sizes (4×4, 6×6, 9×9)
- Three difficulty levels
- Keyboard and mouse wheel input
- Hint system
- Conflict highlighting
- Victory celebration
"""

from __future__ import annotations

import math
import random
import time
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

from PySide6.QtCore import Qt, QTimer, QRectF, QVariantAnimation, QEasingCurve, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QBrush, QLinearGradient
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QMessageBox,
    QProgressDialog,
)
from hub.printing import BatchPrintDialog, VariantOption, create_output_printer, draw_square_batch

# Import engine from the same directory (avoid conflicts with piskvorky engine)
_this_dir = Path(__file__).resolve().parent
_engine_spec = importlib.util.spec_from_file_location("sudoku_engine", _this_dir / "engine.py")
_engine_module = importlib.util.module_from_spec(_engine_spec)
import sys

sys.modules["sudoku_engine"] = _engine_module  # Required for dataclass to work
_engine_spec.loader.exec_module(_engine_module)
create_puzzle = _engine_module.create_puzzle
SudokuState = _engine_module.SudokuState


# Colors
COLOR_PRIMARY = QColor(110, 231, 255)  # Cyan
COLOR_SECONDARY = QColor(167, 139, 250)  # Purple
COLOR_INITIAL = QColor(255, 255, 255)  # White - given numbers
COLOR_USER = QColor(110, 231, 255)  # Cyan - user input
COLOR_WRONG = QColor(255, 100, 100)  # Red - conflicts
COLOR_SELECTED = QColor(110, 231, 255, 60)  # Selection highlight
COLOR_HINT = QColor(255, 200, 87)  # Yellow - hint
COLOR_BOX_LINE = QColor(255, 255, 255, 80)
COLOR_GRID_LINE = QColor(255, 255, 255, 30)
SUDOKU_DIFF_LABELS = {"easy": "Lehká", "medium": "Střední", "hard": "Těžká"}


def _draw_print_sudoku(
    painter: QPainter,
    tile_rect: QRectF,
    item: Tuple[SudokuState, str],
    _: int,
) -> None:
    state, _label = item
    painter.save()

    device = painter.device()
    dpi = max(96.0, float(device.logicalDpiX() if device is not None else 300.0))

    def mm(mm_value: float) -> float:
        return (mm_value / 25.4) * dpi

    painter.fillRect(tile_rect, Qt.white)

    pad = max(mm(1.0), tile_rect.width() * 0.015)
    board_rect = tile_rect.adjusted(pad, pad, -pad, -pad)

    border_w = max(mm(0.90), board_rect.width() * 0.0070)
    thin_w = max(mm(0.25), board_rect.width() * 0.0022)
    box_w = max(mm(0.70), thin_w * 2.2)

    painter.setPen(QPen(Qt.black, border_w))
    painter.drawRect(board_rect)

    n = state.size
    cell = board_rect.width() / float(n)
    board_left = board_rect.left()
    board_top = board_rect.top()
    board_side = board_rect.width()

    painter.setPen(QPen(Qt.black, thin_w))
    for i in range(1, n):
        x = board_left + i * cell
        y = board_top + i * cell
        painter.drawLine(QPointF(x, board_top), QPointF(x, board_top + board_side))
        painter.drawLine(QPointF(board_left, y), QPointF(board_left + board_side, y))

    box_r = state.config.box_rows
    box_c = state.config.box_cols
    painter.setPen(QPen(Qt.black, box_w))
    for i in range(1, n // box_c):
        x = board_left + i * box_c * cell
        painter.drawLine(QPointF(x, board_top), QPointF(x, board_top + board_side))
    for i in range(1, n // box_r):
        y = board_top + i * box_r * cell
        painter.drawLine(QPointF(board_left, y), QPointF(board_left + board_side, y))

    num_px = int(max(mm(1.9), min(cell * 0.64, cell - mm(0.7))))
    num_font = QFont("Arial")
    num_font.setBold(True)
    num_font.setPixelSize(max(8, num_px))
    painter.setFont(num_font)
    painter.setPen(Qt.black)
    for r in range(n):
        for c in range(n):
            idx = r * n + c
            if not state.initial[idx]:
                continue
            val = state.board[idx]
            if val == 0:
                continue
            rect = QRectF(board_left + c * cell, board_top + r * cell, cell, cell)
            painter.drawText(rect, Qt.AlignCenter, str(val))

    painter.restore()


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


class SudokuBoard(QWidget):
    """Interactive Sudoku board widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 400)
        self.setFocusPolicy(Qt.StrongFocus)

        self.state: Optional[SudokuState] = None
        self.selected_cell: Optional[Tuple[int, int]] = None
        self.hint_cell: Optional[Tuple[int, int]] = None
        self.hint_timer: Optional[QTimer] = None

        # Confetti
        self._confetti: List[ConfettiParticle] = []
        self._confetti_timer: Optional[QTimer] = None
        self._last_confetti_tick = time.time()

        # Animation
        self._cell_anims: Dict[Tuple[int, int], float] = {}

        # Overlay
        self._overlay_visible = False
        self._overlay_opacity = 0.0
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._overlay_button_callback = None
        self._overlay_button_rect: Optional[QRectF] = None

        # Callbacks
        self.on_complete = None
        self.on_state_changed = None

    def set_state(self, state: SudokuState) -> None:
        self.state = state
        self.selected_cell = None
        self.hint_cell = None
        self._cell_anims.clear()
        self._stop_confetti()
        self._hide_overlay()
        self._notify_state_changed()
        self.update()

    def _notify_state_changed(self) -> None:
        cb = self.on_state_changed
        if callable(cb):
            cb()

    def _board_geometry(self) -> Tuple[float, float, float, float]:
        size = min(self.width(), self.height())
        margin = 20
        board_size = size - 2 * margin
        left = (self.width() - board_size) / 2
        top = (self.height() - board_size) / 2
        if self.state:
            cell = board_size / self.state.size
        else:
            cell = board_size / 9
        return left, top, board_size, cell

    def cell_at_pos(self, x: float, y: float) -> Optional[Tuple[int, int]]:
        if not self.state:
            return None

        left, top, board_size, cell = self._board_geometry()

        if not (left <= x <= left + board_size and top <= y <= top + board_size):
            return None

        col = int((x - left) / cell)
        row = int((y - top) / cell)

        if 0 <= row < self.state.size and 0 <= col < self.state.size:
            return (row, col)
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return

        # Check overlay button
        if self._overlay_visible and self._overlay_button_callback and self._overlay_button_rect:
            if self._overlay_button_rect.contains(event.position()):
                callback = self._overlay_button_callback
                self._hide_overlay()
                callback()
                return

        cell = self.cell_at_pos(event.position().x(), event.position().y())
        if cell:
            self.selected_cell = cell
            self.hint_cell = None
            self.update()
            self.setFocus()

    def wheelEvent(self, event) -> None:
        """Handle mouse wheel to change selected cell value."""
        if not self.state or not self.selected_cell:
            return

        row, col = self.selected_cell
        if self.state.is_initial(row, col):
            return

        current = self.state.get(row, col)
        delta = 1 if event.angleDelta().y() > 0 else -1

        # Cycle through values: 0 -> 1 -> 2 -> ... -> 9 -> 0 (always 1-9)
        new_val = (current + delta) % 10

        self.state.set(row, col, new_val)
        self._notify_state_changed()
        self._animate_cell(row, col)
        self.update()
        self._check_complete()

    def keyPressEvent(self, event) -> None:
        if not self.state:
            return

        key = event.key()

        # Arrow navigation
        if self.selected_cell:
            row, col = self.selected_cell
            if key == Qt.Key_Up and row > 0:
                self.selected_cell = (row - 1, col)
            elif key == Qt.Key_Down and row < self.state.size - 1:
                self.selected_cell = (row + 1, col)
            elif key == Qt.Key_Left and col > 0:
                self.selected_cell = (row, col - 1)
            elif key == Qt.Key_Right and col < self.state.size - 1:
                self.selected_cell = (row, col + 1)
            elif key in (Qt.Key_Delete, Qt.Key_Backspace, Qt.Key_0):
                if not self.state.is_initial(row, col):
                    self.state.set(row, col, 0)
                    self._notify_state_changed()
                    self._animate_cell(row, col)
            elif Qt.Key_1 <= key <= Qt.Key_9:
                # Always allow 1-9 for all sudoku sizes
                num = key - Qt.Key_1 + 1
                if not self.state.is_initial(row, col):
                    self.state.set(row, col, num)
                    self._notify_state_changed()
                    self._animate_cell(row, col)
                    self._check_complete()

            self.hint_cell = None
            self.update()

    def _animate_cell(self, row: int, col: int) -> None:
        """Animate cell value change."""
        self._cell_anims[(row, col)] = 0.0

        anim = QVariantAnimation(self)
        anim.setDuration(150)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutBack)

        def on_val(v):
            self._cell_anims[(row, col)] = float(v)
            self.update()

        anim.valueChanged.connect(on_val)
        anim.start()

    def _check_complete(self) -> None:
        """Check if puzzle is complete and correct."""
        if self.state and self.state.is_complete():
            self._celebrate()
            if self.on_complete:
                self.on_complete()

    def show_hint(self) -> None:
        """Show a hint for one cell."""
        if not self.state:
            return

        hint_obj = self.state.get_hint_result()
        if hint_obj and hint_obj.cells:
            row, col = hint_obj.cells[0]
            value = int(hint_obj.payload.get("value", 0))
            hint = (row, col, value)
        else:
            hint = self.state.get_hint()
        if hint:
            row, col, value = hint
            self.state.set(row, col, value)
            self._notify_state_changed()
            self.hint_cell = (row, col)
            self.selected_cell = (row, col)
            self._animate_cell(row, col)
            self.update()

            # Clear hint highlight after 2 seconds
            if self.hint_timer:
                self.hint_timer.stop()
            self.hint_timer = QTimer(self)
            self.hint_timer.setSingleShot(True)
            self.hint_timer.timeout.connect(self._clear_hint)
            self.hint_timer.start(2000)

            self._check_complete()

    def _clear_hint(self) -> None:
        self.hint_cell = None
        self.update()

    def _celebrate(self) -> None:
        """Victory celebration with confetti."""
        left, top, board_size, _ = self._board_geometry()
        colors = [COLOR_PRIMARY, COLOR_SECONDARY, QColor(255, 200, 87), QColor(255, 138, 128)]

        self._confetti = []
        for _ in range(80):
            x = left + random.random() * board_size
            y = top - random.random() * board_size * 0.3
            speed = random.uniform(150, 250)
            angle = random.uniform(-math.pi / 3, math.pi / 3)
            vx = speed * math.sin(angle)
            vy = -abs(speed * math.cos(angle) * 0.7)
            size = random.uniform(5, 10)
            life = random.uniform(1.5, 2.5)
            color = random.choice(colors)
            self._confetti.append(ConfettiParticle(x, y, vx, vy, life, size, color))

        self._last_confetti_tick = time.time()
        if not self._confetti_timer:
            self._confetti_timer = QTimer(self)
            self._confetti_timer.setInterval(16)
            self._confetti_timer.timeout.connect(self._tick_confetti)
            self._confetti_timer.start()

    def _tick_confetti(self) -> None:
        now = time.time()
        dt = max(0.001, now - self._last_confetti_tick)
        self._last_confetti_tick = now

        gravity = 900
        alive = []
        for p in self._confetti:
            p.age += dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += gravity * dt
            p.vx *= 0.99

            if p.age < p.life and p.y < self.height() + 50:
                alive.append(p)

        self._confetti = alive
        if not self._confetti:
            self._stop_confetti()
        self.update()

    def _stop_confetti(self) -> None:
        if self._confetti_timer:
            self._confetti_timer.stop()
            self._confetti_timer = None
        self._confetti.clear()

    def show_overlay(self, title: str, subtitle: str, on_button=None) -> None:
        self._overlay_title = title
        self._overlay_subtitle = subtitle
        self._overlay_visible = True
        self._overlay_opacity = 0.0
        self._overlay_button_callback = on_button

        anim = QVariantAnimation(self)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def on_fade(v):
            self._overlay_opacity = float(v)
            self.update()

        anim.valueChanged.connect(on_fade)
        anim.start()

    def _hide_overlay(self) -> None:
        self._overlay_visible = False
        self._overlay_opacity = 0.0
        self._overlay_button_callback = None
        self.update()

    def paintEvent(self, event) -> None:
        if not self.state:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        left, top, board_size, cell = self._board_geometry()
        size = self.state.size
        box_r = self.state.config.box_rows
        box_c = self.state.config.box_cols

        # Board background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(18, 22, 32, 180))
        painter.drawRoundedRect(QRectF(left - 8, top - 8, board_size + 16, board_size + 16), 12, 12)

        # Selection highlight
        if self.selected_cell:
            r, c = self.selected_cell
            rect = QRectF(left + c * cell, top + r * cell, cell, cell)
            painter.setBrush(COLOR_SELECTED)
            painter.drawRect(rect)

            # Highlight row and column
            painter.setBrush(QColor(110, 231, 255, 20))
            painter.drawRect(QRectF(left, top + r * cell, board_size, cell))
            painter.drawRect(QRectF(left + c * cell, top, cell, board_size))

        # Draw grid lines
        painter.setPen(QPen(COLOR_GRID_LINE, 1))
        for i in range(1, size):
            x = left + i * cell
            y = top + i * cell
            painter.drawLine(int(x), int(top), int(x), int(top + board_size))
            painter.drawLine(int(left), int(y), int(left + board_size), int(y))

        # Draw box lines (thicker)
        # All sizes use 3×3 boxes:
        # - 3×3: no box lines (entire grid is one box)
        # - 6×6: cross pattern (1 vertical + 1 horizontal line)
        # - 9×9: 2 vertical + 2 horizontal lines
        painter.setPen(QPen(COLOR_BOX_LINE, 2))
        # Vertical box lines: every box_cols columns
        num_box_cols = size // box_c  # Number of box columns
        for i in range(1, num_box_cols):
            x = left + i * box_c * cell
            painter.drawLine(int(x), int(top), int(x), int(top + board_size))
        # Horizontal box lines: every box_rows rows
        num_box_rows = size // box_r  # Number of box rows
        for i in range(1, num_box_rows):
            y = top + i * box_r * cell
            painter.drawLine(int(left), int(y), int(left + board_size), int(y))

        # Border
        painter.setPen(QPen(COLOR_PRIMARY.darker(150), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(left - 4, top - 4, board_size + 8, board_size + 8), 8, 8)

        # Draw numbers
        font_size = max(12, int(cell * 0.5))
        font = QFont("Segoe UI", font_size, QFont.Bold)
        painter.setFont(font)

        for r in range(size):
            for c in range(size):
                val = self.state.get(r, c)
                if val == 0:
                    continue

                rect = QRectF(left + c * cell, top + r * cell, cell, cell)

                # Animation scale
                scale = self._cell_anims.get((r, c), 1.0)
                if scale < 1.0:
                    center = rect.center()
                    rect = QRectF(
                        center.x() - cell * scale / 2,
                        center.y() - cell * scale / 2,
                        cell * scale,
                        cell * scale,
                    )

                # Color based on state
                # Don't show correct/wrong during play - only after completion
                if self.state.is_initial(r, c):
                    color = COLOR_INITIAL
                elif self.hint_cell == (r, c):
                    color = COLOR_HINT
                else:
                    # All user-entered numbers are cyan - no red for conflicts
                    color = COLOR_USER

                painter.setPen(color)

                # Number text (for 16×16 use hex-like: 1-9, A-G)
                if val <= 9:
                    text = str(val)
                else:
                    text = chr(ord("A") + val - 10)

                painter.drawText(rect, Qt.AlignCenter, text)

        # Confetti
        if self._confetti:
            painter.setPen(Qt.NoPen)
            for p in self._confetti:
                alpha = max(0, 1 - p.age / p.life)
                color = QColor(p.color)
                color.setAlphaF(alpha)
                painter.setBrush(color)
                painter.drawRect(QRectF(p.x, p.y, p.size, p.size))

        # Overlay
        if self._overlay_visible and self._overlay_opacity > 0.01:
            self._draw_overlay(painter, left, top, board_size)

        painter.end()

    def _draw_overlay(self, painter: QPainter, left: float, top: float, board_size: float) -> None:
        painter.save()
        painter.setOpacity(self._overlay_opacity)

        # Background
        overlay_rect = QRectF(left - 10, top - 10, board_size + 20, board_size + 20)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(14, 17, 26, 230))
        painter.drawRoundedRect(overlay_rect, 16, 16)

        # Border
        painter.setPen(QPen(COLOR_PRIMARY.darker(150), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(overlay_rect.adjusted(2, 2, -2, -2), 14, 14)

        # Title
        font = QFont("Segoe UI", 22, QFont.Bold)
        painter.setFont(font)
        painter.setPen(Qt.white)
        title_rect = QRectF(left, top + board_size * 0.3, board_size, 40)
        painter.drawText(title_rect, Qt.AlignCenter, self._overlay_title)

        # Subtitle
        if self._overlay_subtitle:
            font = QFont("Segoe UI", 13)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, 180))
            sub_rect = QRectF(left + 20, top + board_size * 0.42, board_size - 40, 50)
            painter.drawText(sub_rect, Qt.AlignCenter | Qt.TextWordWrap, self._overlay_subtitle)

        # Button
        if self._overlay_button_callback:
            btn_w, btn_h = 160, 44
            btn_x = left + (board_size - btn_w) / 2
            btn_y = top + board_size * 0.62
            btn_rect = QRectF(btn_x, btn_y, btn_w, btn_h)
            self._overlay_button_rect = btn_rect

            gradient = QLinearGradient(btn_rect.topLeft(), btn_rect.bottomRight())
            gradient.setColorAt(0, QColor(110, 231, 255, 220))
            gradient.setColorAt(1, QColor(167, 139, 250, 220))

            painter.setPen(Qt.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(btn_rect, 10, 10)

            font = QFont("Segoe UI", 14, QFont.Bold)
            painter.setFont(font)
            painter.setPen(QColor(20, 24, 36))
            painter.drawText(btn_rect, Qt.AlignCenter, "🔄 Nová hra")

        painter.restore()


class SudokuWidget(QWidget):
    """Main Sudoku game widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SudokuRoot")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        frame = QFrame()
        frame.setObjectName("GameFrame")
        frame.setStyleSheet("""
            QFrame#GameFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(22,26,40,0.92), stop:1 rgba(14,17,26,0.96));
                border: 1px solid rgba(110,231,255,0.15);
                border-radius: 18px;
            }
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(12)

        # Controls row - toggle buttons
        row = QHBoxLayout()
        row.setSpacing(8)

        # Size buttons - standard sudoku variants
        lbl_size = QLabel("📐 Velikost:")
        lbl_size.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 12px;")
        row.addWidget(lbl_size)

        self._size_buttons = {}
        for size_key, size_label in [("3", "3×3"), ("6", "6×6"), ("9", "9×9")]:
            btn = QPushButton(size_label)
            btn.setCheckable(True)
            btn.setMinimumWidth(55)
            btn.setStyleSheet(self._get_toggle_style())
            btn.clicked.connect(lambda checked, s=size_key: self._on_size_selected(s))
            self._size_buttons[size_key] = btn
            row.addWidget(btn)

        row.addSpacing(12)

        # Difficulty buttons
        lbl_diff = QLabel("🎯 Obtížnost:")
        lbl_diff.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 12px;")
        row.addWidget(lbl_diff)

        self._diff_buttons = {}
        for diff_key, diff_label, emoji in [
            ("easy", "Lehká", "😊"),
            ("medium", "Střední", "🤔"),
            ("hard", "Těžká", "🔥"),
        ]:
            btn = QPushButton(f"{emoji}")
            btn.setToolTip(diff_label)
            btn.setCheckable(True)
            btn.setMinimumWidth(45)
            btn.setStyleSheet(self._get_toggle_style())
            btn.clicked.connect(lambda checked, d=diff_key: self._on_diff_selected(d))
            self._diff_buttons[diff_key] = btn
            row.addWidget(btn)

        row.addStretch(1)

        # Hint button
        self.btn_hint = QPushButton("💡 Nápověda")
        self.btn_hint.setStyleSheet("""
            QPushButton {
                background: rgba(255, 200, 87, 0.2);
                border: 1px solid rgba(255, 200, 87, 0.4);
                border-radius: 6px;
                color: rgba(255, 200, 87, 0.9);
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background: rgba(255, 200, 87, 0.3);
                border: 1px solid rgba(255, 200, 87, 0.6);
            }
        """)
        self.btn_hint.clicked.connect(self._on_hint)
        row.addWidget(self.btn_hint)

        # New game button
        self.btn_new = QPushButton("🎲 Nová hra")
        self.btn_new.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(110,231,255,0.85), stop:1 rgba(167,139,250,0.85));
                color: #111318;
                font-weight: 600;
                padding: 7px 16px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(130,245,255,0.95), stop:1 rgba(190,165,255,0.95));
            }
        """)
        self.btn_new.clicked.connect(self.new_game)
        row.addWidget(self.btn_new)

        # Print/PDF button
        self.btn_print = QPushButton("🖨 Tisk/PDF")
        self.btn_print.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.20);
                border-radius: 6px;
                color: rgba(255, 255, 255, 0.92);
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.14);
            }
        """)
        self.btn_print.clicked.connect(self._on_print)
        row.addWidget(self.btn_print)

        # Info row
        info = QHBoxLayout()
        info.setSpacing(12)
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-size: 14px; color: rgba(255,255,255,0.85);")
        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.6);")
        info.addWidget(self.lbl_status)
        info.addWidget(self.lbl_progress)
        info.addStretch(1)

        # Board
        self.board = SudokuBoard()
        self.board.on_complete = self._on_complete
        self.board.on_state_changed = self._update_progress

        lay.addLayout(row)
        lay.addLayout(info)
        lay.addWidget(self.board, 1)

        outer.addWidget(frame, 1)

        # State
        self.size = 9
        self.difficulty = "medium"
        self.game_complete = False
        self.start_time = 0
        self.hints_used = 0

        # Initialize buttons
        self._update_size_buttons("9")
        self._update_diff_buttons("medium")

        # Start game
        QTimer.singleShot(100, self.new_game)

    def _get_toggle_style(self) -> str:
        return """
            QPushButton {
                background: rgba(40, 48, 70, 0.7);
                border: 1px solid rgba(110, 231, 255, 0.2);
                border-radius: 6px;
                color: rgba(255, 255, 255, 0.7);
                font-size: 12px;
                padding: 6px 8px;
            }
            QPushButton:hover {
                background: rgba(60, 70, 95, 0.8);
                border: 1px solid rgba(110, 231, 255, 0.4);
            }
            QPushButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(110,231,255,0.3), stop:1 rgba(167,139,250,0.3));
                border: 2px solid rgba(110, 231, 255, 0.7);
                color: rgba(255, 255, 255, 1.0);
                font-weight: 600;
            }
        """

    def _on_size_selected(self, size: str) -> None:
        self._update_size_buttons(size)
        self.size = int(size)
        self.new_game()

    def _on_diff_selected(self, diff: str) -> None:
        self._update_diff_buttons(diff)
        self.difficulty = diff
        self.new_game()

    def _update_size_buttons(self, active: str) -> None:
        for key, btn in self._size_buttons.items():
            btn.setChecked(key == active)

    def _update_diff_buttons(self, active: str) -> None:
        for key, btn in self._diff_buttons.items():
            btn.setChecked(key == active)

    def new_game(self) -> None:
        self.game_complete = False
        self.start_time = time.time()
        self.hints_used = 0

        self.lbl_status.setText("⏳ Generuji puzzle...")
        self.update()

        # Generate puzzle (use timer to not block UI)
        QTimer.singleShot(50, self._generate_puzzle)

    def _generate_puzzle(self) -> None:
        try:
            state = create_puzzle(self.size, self.difficulty)
        except Exception as exc:
            self.lbl_status.setText("❌ Chyba generování")
            self.lbl_progress.setText("Zkus prosím Nová hra")
            QMessageBox.warning(self, "Sudoku", f"Nepodařilo se vygenerovat puzzle:\n{exc}")
            return

        self.board.set_state(state)

        filled = state.count_filled()
        total = self.size * self.size
        empty = total - filled

        diff_names = {"easy": "Lehká", "medium": "Střední", "hard": "Těžká"}
        self.lbl_status.setText(f"🎯 {self.size}×{self.size} · {diff_names[self.difficulty]}")
        self.lbl_progress.setText(f"📝 {filled}/{total} ({empty} prázdných)")

        self.update()

    def _on_hint(self) -> None:
        if self.game_complete:
            return
        self.board.show_hint()
        self.hints_used += 1
        self._update_progress()

    def _on_print(self) -> None:
        variants: List[VariantOption] = []
        for size in (3, 6, 9):
            for diff in ("easy", "medium", "hard"):
                variants.append(
                    VariantOption(
                        key=f"{size}:{diff}",
                        label=f"{size}×{size} · {SUDOKU_DIFF_LABELS[diff]}",
                    )
                )

        dlg = BatchPrintDialog(
            "Sudoku tisk",
            variants,
            default_variant_key=f"{self.size}:{self.difficulty}",
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        requests = dlg.selected_requests()
        total = sum(count for _, count in requests)
        items: List[Tuple[SudokuState, str]] = []
        failures = 0

        progress = QProgressDialog("Generuji sudoku pro tisk...", "Zrušit", 0, total, self)
        progress.setWindowTitle("Sudoku")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        generated = 0
        for variant, count in requests:
            size_s, diff = variant.key.split(":")
            size = int(size_s)
            for _ in range(count):
                if progress.wasCanceled():
                    return
                try:
                    state = create_puzzle(size, diff)
                except Exception:
                    state = None

                if state is not None:
                    items.append((state, variant.label))
                else:
                    failures += 1
                generated += 1
                progress.setValue(generated)
                QApplication.processEvents()
        progress.setValue(total)

        if not items:
            QMessageBox.warning(self, "Sudoku", "Nepodařilo se vygenerovat žádnou úlohu pro tisk.")
            return

        printer, pdf_path = create_output_printer(
            self,
            "BrainHub Sudoku",
            dlg.output_mode(),
            dlg.pdf_path(),
        )
        if printer is None:
            return

        try:
            draw_square_batch(printer, items, dlg.puzzles_per_page(), _draw_print_sudoku)
        except Exception as exc:
            QMessageBox.critical(self, "Sudoku", f"Tisk se nepodařil:\n{exc}")
            return

        if pdf_path:
            QMessageBox.information(self, "Sudoku", f"PDF vytvořeno:\n{pdf_path}")

        if failures:
            QMessageBox.warning(
                self,
                "Sudoku",
                f"{failures} úloh se nepodařilo vygenerovat a nebyly zahrnuty do výstupu.",
            )

    def _update_progress(self) -> None:
        if not self.board.state:
            return
        filled = self.board.state.count_filled()
        total = self.size * self.size
        self.lbl_progress.setText(f"📝 {filled}/{total} · 💡 {self.hints_used} nápověd")

    def _on_complete(self) -> None:
        self.game_complete = True
        elapsed = time.time() - self.start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)

        time_str = f"{mins}:{secs:02d}"
        hint_str = f"{self.hints_used} nápověd" if self.hints_used else "bez nápověd"

        self.lbl_status.setText("🏆 Vyřešeno!")
        self.board.show_overlay("🎉 Gratulace!", f"Čas: {time_str}\n{hint_str}", self.new_game)
