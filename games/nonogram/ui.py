"""
Nonogram UI - Modern game interface

Features:
- Multiple board sizes (5×5 to 15×15)
- Three difficulty levels
- Mouse input with drag support
- Hint system
- Victory celebration with confetti
"""
from __future__ import annotations

import math
import random
import time
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import (
    Qt, QTimer, QRectF, QVariantAnimation, QEasingCurve
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QFont, QLinearGradient
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)

# Import engine from the same directory
_this_dir = Path(__file__).resolve().parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

import importlib.util
_engine_spec = importlib.util.spec_from_file_location("nonogram_engine", _this_dir / "engine.py")
_engine_module = importlib.util.module_from_spec(_engine_spec)
sys.modules["nonogram_engine"] = _engine_module
_engine_spec.loader.exec_module(_engine_module)

NonogramPuzzle = _engine_module.NonogramPuzzle
NonogramState = _engine_module.NonogramState
NonogramSolver = _engine_module.NonogramSolver
create_puzzle = _engine_module.create_puzzle


# Colors - matching other games
COLOR_PRIMARY = QColor(110, 231, 255)      # Cyan
COLOR_SECONDARY = QColor(167, 139, 250)    # Purple
COLOR_FILLED = QColor(110, 231, 255)       # Cyan - filled cells
COLOR_MARKED = QColor(255, 100, 100, 60)   # Red transparent - marked X
COLOR_SELECTED = QColor(110, 231, 255, 40) # Selection highlight
COLOR_HINT = QColor(255, 200, 87)          # Yellow - hint
COLOR_GRID_LINE = QColor(255, 255, 255, 25)
COLOR_GRID_THICK = QColor(255, 255, 255, 60)
COLOR_CLUE_DONE = QColor(110, 231, 255, 30)


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


class NonogramBoard(QWidget):
    """Interactive Nonogram board widget - fixed size like Sudoku/KenKen."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 400)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        
        self.state: Optional[NonogramState] = None
        self.hover_cell: Optional[Tuple[int, int]] = None
        self.hint_cell: Optional[Tuple[int, int]] = None
        self.hint_timer: Optional[QTimer] = None
        
        # Drag state
        self.dragging = False
        self.drag_value = 0
        
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
    
    def set_state(self, state: NonogramState) -> None:
        self.state = state
        self.hover_cell = None
        self.hint_cell = None
        self._hide_overlay()
        self._stop_confetti()
        self.update()
    
    def _board_geometry(self) -> Tuple[float, float, float, float]:
        """
        Calculate board geometry: (left, top, board_size, cell_size).
        Uses fixed square area like Sudoku/KenKen.
        """
        # Use the smaller dimension to create a square board
        available = min(self.width(), self.height())
        margin = 20
        board_size = available - 2 * margin
        
        # Center the board
        left = (self.width() - board_size) / 2
        top = (self.height() - board_size) / 2
        
        # Calculate cell size based on grid size + clue areas
        if self.state:
            puzzle = self.state.puzzle
            max_row_clues = max(len(c) for c in puzzle.row_clues) if puzzle.row_clues else 1
            max_col_clues = max(len(c) for c in puzzle.col_clues) if puzzle.col_clues else 1
            
            # Clue area takes about 25% of the space
            clue_ratio = 0.25
            grid_area = board_size * (1 - clue_ratio)
            cell = grid_area / max(puzzle.width, puzzle.height)
        else:
            cell = board_size / 10
        
        return left, top, board_size, cell
    
    def _get_layout(self) -> Tuple[float, float, float, float, float, float]:
        """Get detailed layout: (left, top, cell, clue_w, clue_h, grid_size)."""
        if not self.state:
            return 0, 0, 30, 50, 50, 300
        
        left, top, board_size, cell = self._board_geometry()
        
        puzzle = self.state.puzzle
        max_row_clues = max(len(c) for c in puzzle.row_clues) if puzzle.row_clues else 1
        max_col_clues = max(len(c) for c in puzzle.col_clues) if puzzle.col_clues else 1
        
        clue_cell = cell * 0.6  # Smaller cells for clues
        clue_w = max_row_clues * clue_cell
        clue_h = max_col_clues * clue_cell
        
        grid_w = puzzle.width * cell
        grid_h = puzzle.height * cell
        
        # Center within board area
        total_w = clue_w + grid_w
        total_h = clue_h + grid_h
        
        adj_left = left + (board_size - total_w) / 2
        adj_top = top + (board_size - total_h) / 2
        
        return adj_left, adj_top, cell, clue_w, clue_h, clue_cell
    
    def _cell_at_pos(self, x: float, y: float) -> Optional[Tuple[int, int]]:
        """Get grid cell at position."""
        if not self.state:
            return None
        
        adj_left, adj_top, cell, clue_w, clue_h, _ = self._get_layout()
        grid_x = adj_left + clue_w
        grid_y = adj_top + clue_h
        
        col = int((x - grid_x) / cell)
        row = int((y - grid_y) / cell)
        
        if 0 <= row < self.state.puzzle.height and 0 <= col < self.state.puzzle.width:
            return (row, col)
        return None
    
    def _check_line_complete(self, line: list, clue: list) -> bool:
        """Check if a line matches its clue."""
        blocks = []
        current = 0
        for c in line:
            if c == 1:
                current += 1
            else:
                if current > 0:
                    blocks.append(current)
                    current = 0
        if current > 0:
            blocks.append(current)
        
        # Handle empty line case: clue [0] means no blocks
        if not blocks:
            return clue == [0] or clue == []
        
        return blocks == clue
    
    def mousePressEvent(self, event) -> None:
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        
        # Check overlay button
        if (self._overlay_visible and self._overlay_button_callback 
            and self._overlay_button_rect):
            if self._overlay_button_rect.contains(event.position()):
                callback = self._overlay_button_callback
                self._hide_overlay()
                callback()
                return
        
        if not self.state:
            return
        
        cell = self._cell_at_pos(event.position().x(), event.position().y())
        if not cell:
            return
        
        row, col = cell
        current = self.state.get_cell(row, col)
        
        if event.button() == Qt.LeftButton:
            if current == 1:
                self.state.set_cell(row, col, 0)
                self.drag_value = 0
            else:
                self.state.set_cell(row, col, 1)
                self.drag_value = 1
        else:
            if current == -1:
                self.state.set_cell(row, col, 0)
                self.drag_value = 0
            else:
                self.state.set_cell(row, col, -1)
                self.drag_value = -1
        
        self.dragging = True
        self._animate_cell(row, col)
        self.hint_cell = None
        self.update()
        self._check_complete()
    
    def mouseMoveEvent(self, event) -> None:
        cell = self._cell_at_pos(event.position().x(), event.position().y())
        self.hover_cell = cell
        
        if self.dragging and cell and self.state:
            row, col = cell
            current = self.state.get_cell(row, col)
            if current != self.drag_value:
                self.state.set_cell(row, col, self.drag_value)
                self._animate_cell(row, col)
                self._check_complete()
        
        self.update()
    
    def mouseReleaseEvent(self, event) -> None:
        self.dragging = False
    
    def leaveEvent(self, event) -> None:
        self.hover_cell = None
        self.update()
    
    def _animate_cell(self, row: int, col: int) -> None:
        self._cell_anims[(row, col)] = 0.0
        
        anim = QVariantAnimation(self)
        anim.setDuration(120)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutBack)
        
        def on_val(v):
            self._cell_anims[(row, col)] = float(v)
            self.update()
        
        anim.valueChanged.connect(on_val)
        anim.start()
    
    def _check_complete(self) -> None:
        if self.state and self.state.is_complete():
            self._celebrate()
            if self.on_complete:
                self.on_complete()
    
    def show_hint(self) -> bool:
        if not self.state:
            return False
        
        solver = NonogramSolver(self.state)
        hint = solver.get_hint()
        
        if hint:
            row, col, value = hint
            self.state.set_cell(row, col, value)
            self.hint_cell = (row, col)
            self._animate_cell(row, col)
            self.update()
            
            if self.hint_timer:
                self.hint_timer.stop()
            self.hint_timer = QTimer(self)
            self.hint_timer.setSingleShot(True)
            self.hint_timer.timeout.connect(self._clear_hint)
            self.hint_timer.start(2000)
            
            self._check_complete()
            return True
        return False
    
    def _clear_hint(self) -> None:
        self.hint_cell = None
        self.update()
    
    def _celebrate(self) -> None:
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
        
        left, top, board_size, _ = self._board_geometry()
        adj_left, adj_top, cell, clue_w, clue_h, clue_cell = self._get_layout()
        
        puzzle = self.state.puzzle
        grid_x = adj_left + clue_w
        grid_y = adj_top + clue_h
        grid_w = puzzle.width * cell
        grid_h = puzzle.height * cell
        
        # Board background (full area)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(18, 22, 32, 180))
        painter.drawRoundedRect(QRectF(left - 8, top - 8, board_size + 16, board_size + 16), 12, 12)
        
        # Clue backgrounds with completion highlighting
        for row in range(puzzle.height):
            y = grid_y + row * cell
            clue = puzzle.row_clues[row]
            line = self.state.get_row(row)
            is_complete = self._check_line_complete(line, clue)
            
            if is_complete:
                painter.setBrush(COLOR_CLUE_DONE)
            else:
                painter.setBrush(QColor(255, 255, 255, 8))
            painter.drawRect(QRectF(adj_left, y, clue_w, cell))
        
        for col in range(puzzle.width):
            x = grid_x + col * cell
            clue = puzzle.col_clues[col]
            line = self.state.get_col(col)
            is_complete = self._check_line_complete(line, clue)
            
            if is_complete:
                painter.setBrush(COLOR_CLUE_DONE)
            else:
                painter.setBrush(QColor(255, 255, 255, 8))
            painter.drawRect(QRectF(x, adj_top, cell, clue_h))
        
        # Draw clue numbers
        clue_font = QFont("Segoe UI", max(7, int(clue_cell * 0.55)))
        painter.setFont(clue_font)
        painter.setPen(QColor(255, 255, 255, 200))
        
        # Row clues (right-aligned)
        for row in range(puzzle.height):
            y = grid_y + row * cell + cell / 2
            clue = puzzle.row_clues[row]
            for i, num in enumerate(reversed(clue)):
                x = adj_left + clue_w - (i + 1) * clue_cell + clue_cell / 2
                rect = QRectF(x - clue_cell/2, y - cell/2, clue_cell, cell)
                painter.drawText(rect, Qt.AlignCenter, str(num))
        
        # Column clues (bottom-aligned)
        for col in range(puzzle.width):
            x = grid_x + col * cell + cell / 2
            clue = puzzle.col_clues[col]
            for i, num in enumerate(reversed(clue)):
                y = adj_top + clue_h - (i + 1) * clue_cell + clue_cell / 2
                rect = QRectF(x - cell/2, y - clue_cell/2, cell, clue_cell)
                painter.drawText(rect, Qt.AlignCenter, str(num))
        
        # Hover highlight row/column
        if self.hover_cell:
            hr, hc = self.hover_cell
            painter.setBrush(COLOR_SELECTED)
            painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(grid_x, grid_y + hr * cell, grid_w, cell))
            painter.drawRect(QRectF(grid_x + hc * cell, grid_y, cell, grid_h))
        
        # Draw grid cells
        for row in range(puzzle.height):
            for col in range(puzzle.width):
                x = grid_x + col * cell
                y = grid_y + row * cell
                val = self.state.get_cell(row, col)
                
                scale = self._cell_anims.get((row, col), 1.0)
                rect = QRectF(x + 1, y + 1, cell - 2, cell - 2)
                if scale < 1.0:
                    center = rect.center()
                    sw = (cell - 2) * scale
                    rect = QRectF(center.x() - sw/2, center.y() - sw/2, sw, sw)
                
                is_hint = self.hint_cell == (row, col)
                
                if val == 1:  # Filled
                    if is_hint:
                        painter.setBrush(COLOR_HINT)
                    else:
                        painter.setBrush(COLOR_FILLED)
                    painter.setPen(Qt.NoPen)
                    painter.drawRoundedRect(rect, 3, 3)
                elif val == -1:  # Marked X
                    painter.setBrush(COLOR_MARKED)
                    painter.setPen(Qt.NoPen)
                    painter.drawRoundedRect(rect, 3, 3)
                    
                    painter.setPen(QPen(QColor(255, 100, 100), 2))
                    m = max(4, cell * 0.2)
                    painter.drawLine(int(x + m), int(y + m), int(x + cell - m), int(y + cell - m))
                    painter.drawLine(int(x + cell - m), int(y + m), int(x + m), int(y + cell - m))
        
        # Draw grid lines
        for row in range(1, puzzle.height):
            y = grid_y + row * cell
            if row % 5 == 0:
                painter.setPen(QPen(COLOR_GRID_THICK, 2))
            else:
                painter.setPen(QPen(COLOR_GRID_LINE, 1))
            painter.drawLine(int(grid_x), int(y), int(grid_x + grid_w), int(y))
        
        for col in range(1, puzzle.width):
            x = grid_x + col * cell
            if col % 5 == 0:
                painter.setPen(QPen(COLOR_GRID_THICK, 2))
            else:
                painter.setPen(QPen(COLOR_GRID_LINE, 1))
            painter.drawLine(int(x), int(grid_y), int(x), int(grid_y + grid_h))
        
        # Border
        painter.setPen(QPen(COLOR_PRIMARY.darker(150), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(left - 4, top - 4, board_size + 8, board_size + 8), 8, 8)
        
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
    
    def _draw_overlay(self, painter: QPainter, left: float, top: float, size: float) -> None:
        painter.save()
        painter.setOpacity(self._overlay_opacity)
        
        overlay_rect = QRectF(left - 10, top - 10, size + 20, size + 20)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(14, 17, 26, 230))
        painter.drawRoundedRect(overlay_rect, 16, 16)
        
        painter.setPen(QPen(COLOR_PRIMARY.darker(150), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(overlay_rect.adjusted(2, 2, -2, -2), 14, 14)
        
        font = QFont("Segoe UI", 22, QFont.Bold)
        painter.setFont(font)
        painter.setPen(Qt.white)
        title_rect = QRectF(left, top + size * 0.3, size, 40)
        painter.drawText(title_rect, Qt.AlignCenter, self._overlay_title)
        
        if self._overlay_subtitle:
            font = QFont("Segoe UI", 13)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, 180))
            sub_rect = QRectF(left + 20, top + size * 0.42, size - 40, 50)
            painter.drawText(sub_rect, Qt.AlignCenter | Qt.TextWordWrap, self._overlay_subtitle)
        
        if self._overlay_button_callback:
            btn_w, btn_h = 160, 44
            btn_x = left + (size - btn_w) / 2
            btn_y = top + size * 0.62
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


class NonogramWidget(QWidget):
    """Main Nonogram game widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NonogramRoot")
        
        self.game_complete = False
        self.start_time = time.time()
        self.hints_used = 0
        self.size = 10
        self.difficulty = "medium"
        
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
        
        # Controls row
        row = QHBoxLayout()
        row.setSpacing(8)
        
        # Size buttons
        lbl_size = QLabel("📐 Velikost:")
        lbl_size.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 12px;")
        row.addWidget(lbl_size)
        
        self._size_buttons = {}
        for size_key, size_label in [("5", "5×5"), ("10", "10×10"), ("15", "15×15")]:
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
        for diff_key, diff_label, emoji in [("easy", "Lehká", "😊"), ("medium", "Střední", "🤔"), ("hard", "Těžká", "🔥")]:
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
                font-size: 12px;
                padding: 6px 14px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(130,240,255,0.95), stop:1 rgba(180,155,255,0.95));
            }
        """)
        self.btn_new.clicked.connect(self.new_game)
        row.addWidget(self.btn_new)
        
        lay.addLayout(row)
        
        # Status row
        status_row = QHBoxLayout()
        
        self.lbl_status = QLabel("🧩 10×10")
        self.lbl_status.setStyleSheet("color: rgba(255,255,255,0.9); font-size: 13px;")
        status_row.addWidget(self.lbl_status)
        
        status_row.addStretch(1)
        
        self.lbl_progress = QLabel("LMB = vyplnit · RMB = označit ✕")
        self.lbl_progress.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 12px;")
        status_row.addWidget(self.lbl_progress)
        
        lay.addLayout(status_row)
        
        # Game board
        self.board = NonogramBoard()
        self.board.on_complete = self._on_complete
        lay.addWidget(self.board, 1)
        
        outer.addWidget(frame)
        
        # Set initial state
        self._size_buttons["10"].setChecked(True)
        self._diff_buttons["medium"].setChecked(True)
        
        self.new_game()
    
    def _get_toggle_style(self) -> str:
        return """
            QPushButton {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px;
                color: rgba(255,255,255,0.6);
                font-size: 11px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
                border: 1px solid rgba(110,231,255,0.3);
                color: rgba(255,255,255,0.8);
            }
            QPushButton:checked {
                background: rgba(110,231,255,0.2);
                border: 1px solid rgba(110,231,255,0.5);
                color: rgba(110,231,255,0.95);
            }
        """
    
    def _on_size_selected(self, size: str) -> None:
        for key, btn in self._size_buttons.items():
            btn.setChecked(key == size)
        self.size = int(size)
        self.new_game()
    
    def _on_diff_selected(self, diff: str) -> None:
        for key, btn in self._diff_buttons.items():
            btn.setChecked(key == diff)
        self.difficulty = diff
        self.new_game()
    
    def new_game(self) -> None:
        self.game_complete = False
        self.start_time = time.time()
        self.hints_used = 0
        
        state = create_puzzle(self.size, self.difficulty)
        self.board.set_state(state)
        
        self.lbl_status.setText(f"🧩 {self.size}×{self.size}")
        self.lbl_progress.setText("LMB = vyplnit · RMB = označit ✕")
    
    def _on_hint(self) -> None:
        if self.game_complete:
            return
        if self.board.show_hint():
            self.hints_used += 1
            self._update_progress()
    
    def _update_progress(self) -> None:
        if not self.board.state:
            return
        filled = sum(1 for r in range(self.board.state.puzzle.height) 
                     for c in range(self.board.state.puzzle.width) 
                     if self.board.state.get_cell(r, c) == 1)
        self.lbl_progress.setText(f"📝 {filled} vyplněno · 💡 {self.hints_used} nápověd")
    
    def _on_complete(self) -> None:
        self.game_complete = True
        elapsed = time.time() - self.start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        
        time_str = f"{mins}:{secs:02d}"
        hint_str = f"{self.hints_used} nápověd" if self.hints_used else "bez nápověd"
        
        self.lbl_status.setText("🏆 Vyřešeno!")
        self.board.show_overlay(
            "🎉 Gratulace!",
            f"Čas: {time_str}\n{hint_str}",
            self.new_game
        )
