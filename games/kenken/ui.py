"""
KenKen UI - Modern game interface

Features:
- Multiple board sizes (4×4 to 9×9)
- Cage visualization with target numbers and operations (+, -, *, /)
- Keyboard and mouse wheel input
- Hint system
- Victory celebration
- Background puzzle generation with loading animation
"""
from __future__ import annotations

import math
import random
import time
from typing import Dict, List, Optional, Tuple, Set

from PySide6.QtCore import (
    Qt, QTimer, QRectF, QVariantAnimation, QEasingCurve, QPointF,
    QThread, Signal, QObject
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QFont, QBrush, QLinearGradient, QPainterPath
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QProgressDialog
)
from hub.printing import BatchPrintDialog, VariantOption, create_output_printer, draw_square_batch

# Import engine - works both as package and standalone
try:
    from . import engine as _engine_module
except ImportError:
    import importlib.util
    from pathlib import Path
    _this_dir = Path(__file__).resolve().parent
    _engine_spec = importlib.util.spec_from_file_location("kenken_engine", _this_dir / "engine.py")
    _engine_module = importlib.util.module_from_spec(_engine_spec)
    import sys
    sys.modules["kenken_engine"] = _engine_module
    _engine_spec.loader.exec_module(_engine_module)

create_puzzle = _engine_module.create_puzzle
KenKenState = _engine_module.KenKenState
Cage = _engine_module.Cage


# Colors
COLOR_PRIMARY = QColor(110, 231, 255)      # Cyan
COLOR_SECONDARY = QColor(167, 139, 250)    # Purple
COLOR_USER = QColor(110, 231, 255)         # Cyan - user input
COLOR_SELECTED = QColor(110, 231, 255, 60) # Selection highlight
COLOR_HINT = QColor(255, 200, 87)          # Yellow - hint
COLOR_CAGE_LINE = QColor(255, 255, 255, 180)
COLOR_GRID_LINE = QColor(255, 255, 255, 25)
COLOR_CAGE_TARGET = QColor(255, 255, 255, 200)


def _cage_edges_for_print(cage: Cage) -> Set[Tuple[Tuple[int, int], str]]:
    cells_set = set(cage.cells)
    edges: Set[Tuple[Tuple[int, int], str]] = set()

    for r, c in cage.cells:
        if (r - 1, c) not in cells_set:
            edges.add(((r, c), "top"))
        if (r + 1, c) not in cells_set:
            edges.add(((r, c), "bottom"))
        if (r, c - 1) not in cells_set:
            edges.add(((r, c), "left"))
        if (r, c + 1) not in cells_set:
            edges.add(((r, c), "right"))

    return edges


def _cage_top_left_for_print(cage: Cage) -> Tuple[int, int]:
    min_row = min(r for r, _ in cage.cells)
    top_row_cells = [(r, c) for r, c in cage.cells if r == min_row]
    min_col = min(c for _, c in top_row_cells)
    return min_row, min_col


def _draw_print_kenken(
    painter: QPainter,
    tile_rect: QRectF,
    item: Tuple[KenKenState, str],
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

    n = state.size
    board_side = board_rect.width()
    board_left = board_rect.left()
    board_top = board_rect.top()
    cell = board_side / float(n)

    board_border = max(mm(0.95), board_side * 0.0070)
    thin_w = max(mm(0.34), board_side * 0.0030)
    cage_w = max(mm(0.95), board_side * 0.0080)

    painter.setPen(QPen(Qt.black, board_border))
    painter.drawRect(board_rect)

    painter.setPen(QPen(Qt.black, thin_w))
    for i in range(1, n):
        x = board_left + i * cell
        y = board_top + i * cell
        painter.drawLine(QPointF(x, board_top), QPointF(x, board_top + board_side))
        painter.drawLine(QPointF(board_left, y), QPointF(board_left + board_side, y))

    painter.setPen(QPen(Qt.black, cage_w))
    for cage in state.cages:
        for (r, c), direction in _cage_edges_for_print(cage):
            x = board_left + c * cell
            y = board_top + r * cell
            if direction == "top":
                painter.drawLine(QPointF(x, y), QPointF(x + cell, y))
            elif direction == "bottom":
                painter.drawLine(QPointF(x, y + cell), QPointF(x + cell, y + cell))
            elif direction == "left":
                painter.drawLine(QPointF(x, y), QPointF(x, y + cell))
            elif direction == "right":
                painter.drawLine(QPointF(x + cell, y), QPointF(x + cell, y + cell))

    op_symbols = {"+": "+", "-": "−", "*": "×", "/": "÷", "": ""}
    target_px = int(max(mm(1.8), min(cell * 0.34, cell * 0.52)))
    target_font = QFont("Arial")
    target_font.setBold(True)
    target_font.setPixelSize(max(7, target_px))
    painter.setFont(target_font)
    painter.setPen(Qt.black)
    metrics = painter.fontMetrics()
    for cage in state.cages:
        tr, tc = _cage_top_left_for_print(cage)
        op = op_symbols.get(cage.operation, cage.operation)
        text = f"{cage.target}{op}"
        x = board_left + tc * cell + max(mm(0.35), cell * 0.06)
        y = board_top + tr * cell + max(mm(0.20), cell * 0.04) + metrics.ascent()
        painter.drawText(QPointF(x, y), text)

    painter.restore()


class PuzzleGeneratorWorker(QObject):
    """Worker to generate puzzles in background thread."""
    finished = Signal(object)  # Emits KenKenState
    
    def __init__(self, size: int):
        super().__init__()
        self.size = size
    
    def run(self):
        """Generate puzzle - runs in background thread."""
        try:
            state = create_puzzle(self.size)
            self.finished.emit(state)
        except Exception as e:
            print(f"[KenKen] Generation error: {e}")
            self.finished.emit(None)


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


class KenKenBoard(QWidget):
    """Interactive KenKen board widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 400)
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.state: Optional[KenKenState] = None
        self.selected_cell: Optional[Tuple[int, int]] = None
        self.hint_cell: Optional[Tuple[int, int]] = None
        self.hint_timer: Optional[QTimer] = None
        
        # Loading state
        self._loading = False
        self._loading_angle = 0.0
        self._loading_timer: Optional[QTimer] = None
        self._loading_size = 6  # Preview size during loading
        self._no_templates = False  # True when templates are missing
        
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
    
    def set_loading(self, loading: bool, preview_size: int = 6) -> None:
        """Set loading state with spinner animation."""
        self._loading = loading
        self._loading_size = preview_size
        
        if loading:
            self.state = None
            self._loading_angle = 0.0
            if not self._loading_timer:
                self._loading_timer = QTimer(self)
                self._loading_timer.setInterval(16)  # ~60 FPS
                self._loading_timer.timeout.connect(self._tick_loading)
            self._loading_timer.start()
        else:
            if self._loading_timer:
                self._loading_timer.stop()
        
        self.update()
    
    def _tick_loading(self) -> None:
        """Animate loading spinner."""
        self._loading_angle += 5.0
        if self._loading_angle >= 360.0:
            self._loading_angle -= 360.0
        self.update()
    
    def set_no_templates(self, size: int = 6) -> None:
        """Show 'no templates' error state with red X."""
        self._loading = False
        self._no_templates = True
        self._loading_size = size
        self.state = None
        if self._loading_timer:
            self._loading_timer.stop()
        self.update()
    
    def set_state(self, state: KenKenState) -> None:
        self.state = state
        self.selected_cell = None
        self.hint_cell = None
        self._cell_anims.clear()
        self._no_templates = False
        self._stop_confetti()
        self._hide_overlay()
        self.update()
    
    def _board_geometry(self) -> Tuple[float, float, float, float]:
        size = min(self.width(), self.height())
        margin = 20
        board_size = size - 2 * margin
        left = (self.width() - board_size) / 2
        top = (self.height() - board_size) / 2
        if self.state:
            cell = board_size / self.state.size
        elif self._loading:
            cell = board_size / self._loading_size
        else:
            cell = board_size / 6
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
        if (self._overlay_visible and self._overlay_button_callback 
            and self._overlay_button_rect):
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
        current = self.state.get(row, col)
        delta = 1 if event.angleDelta().y() > 0 else -1
        max_val = self.state.size
        
        # Cycle through values: 0 -> 1 -> 2 -> ... -> N -> 0
        new_val = (current + delta) % (max_val + 1)
        
        self.state.set(row, col, new_val)
        self._animate_cell(row, col)
        self.update()
        self._check_complete()
    
    def keyPressEvent(self, event) -> None:
        if not self.state:
            return
        
        key = event.key()
        max_val = self.state.size
        
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
                self.state.set(row, col, 0)
                self._animate_cell(row, col)
            elif Qt.Key_1 <= key <= Qt.Key_9:
                num = key - Qt.Key_1 + 1
                if num <= max_val:
                    self.state.set(row, col, num)
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
        
        hint = self.state.get_hint()
        if hint:
            row, col, value = hint
            self.state.set(row, col, value)
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
    
    def _get_cage_edges(self, cage: Cage) -> Set[Tuple[Tuple[int, int], str]]:
        """Get cage border edges: (cell, direction) for cells on the border."""
        cells_set = set(cage.cells)
        edges = set()
        
        for r, c in cage.cells:
            # Top edge
            if (r - 1, c) not in cells_set:
                edges.add(((r, c), 'top'))
            # Bottom edge
            if (r + 1, c) not in cells_set:
                edges.add(((r, c), 'bottom'))
            # Left edge
            if (r, c - 1) not in cells_set:
                edges.add(((r, c), 'left'))
            # Right edge
            if (r, c + 1) not in cells_set:
                edges.add(((r, c), 'right'))
        
        return edges
    
    def _get_cage_top_left(self, cage: Cage) -> Tuple[int, int]:
        """Get the top-left cell of a cage for placing the target."""
        min_row = min(r for r, c in cage.cells)
        top_row_cells = [(r, c) for r, c in cage.cells if r == min_row]
        min_col = min(c for r, c in top_row_cells)
        return (min_row, min_col)
    
    def _draw_no_templates(self, painter: QPainter, left: float, top: float, board_size: float) -> None:
        """Draw 'no templates' error state with red X."""
        # Board background (dimmed red tint)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(40, 18, 18, 220))
        painter.drawRoundedRect(QRectF(left - 8, top - 8, board_size + 16, board_size + 16), 12, 12)
        
        # Draw preview grid (very dim)
        grid_size = self._loading_size
        cell = board_size / grid_size
        
        painter.setPen(QPen(QColor(255, 100, 100, 20), 1))
        for i in range(1, grid_size):
            x = left + i * cell
            y = top + i * cell
            painter.drawLine(int(x), int(top), int(x), int(top + board_size))
            painter.drawLine(int(left), int(y), int(left + board_size), int(y))
        
        # Border (red)
        painter.setPen(QPen(QColor(220, 60, 60), 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(left - 4, top - 4, board_size + 8, board_size + 8), 8, 8)
        
        # Draw big red X in center
        center_x = left + board_size / 2
        center_y = top + board_size / 2
        x_size = min(100, board_size * 0.25)
        
        x_pen = QPen(QColor(220, 60, 60), 8, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(x_pen)
        painter.drawLine(
            int(center_x - x_size), int(center_y - x_size),
            int(center_x + x_size), int(center_y + x_size)
        )
        painter.drawLine(
            int(center_x + x_size), int(center_y - x_size),
            int(center_x - x_size), int(center_y + x_size)
        )
        
        # Error text
        font = QFont("Segoe UI", 14, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor(220, 60, 60))
        text_rect = QRectF(left, center_y + x_size + 20, board_size, 30)
        painter.drawText(text_rect, Qt.AlignCenter, "Šablony nejsou k dispozici")
        
        # Smaller hint text
        font2 = QFont("Segoe UI", 10)
        painter.setFont(font2)
        painter.setPen(QColor(180, 100, 100))
        text_rect2 = QRectF(left, center_y + x_size + 50, board_size, 25)
        painter.drawText(text_rect2, Qt.AlignCenter, "Spusťte generátor šablon")
    
    def _draw_loading(self, painter: QPainter, left: float, top: float, board_size: float) -> None:
        """Draw loading animation with spinner."""
        # Board background (dimmed)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(18, 22, 32, 200))
        painter.drawRoundedRect(QRectF(left - 8, top - 8, board_size + 16, board_size + 16), 12, 12)
        
        # Draw preview grid
        grid_size = self._loading_size
        cell = board_size / grid_size
        
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        for i in range(1, grid_size):
            x = left + i * cell
            y = top + i * cell
            painter.drawLine(int(x), int(top), int(x), int(top + board_size))
            painter.drawLine(int(left), int(y), int(left + board_size), int(y))
        
        # Border
        painter.setPen(QPen(COLOR_PRIMARY.darker(180), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(left - 4, top - 4, board_size + 8, board_size + 8), 8, 8)
        
        # Draw spinner in center
        center_x = left + board_size / 2
        center_y = top + board_size / 2
        spinner_radius = min(60, board_size * 0.15)
        
        # Spinner arc
        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(self._loading_angle)
        
        # Draw gradient arc
        arc_pen = QPen(COLOR_PRIMARY, 4, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(arc_pen)
        arc_rect = QRectF(-spinner_radius, -spinner_radius, spinner_radius * 2, spinner_radius * 2)
        painter.drawArc(arc_rect, 0, 270 * 16)  # 270 degrees
        
        # Fade tail
        for i in range(4):
            alpha = 200 - i * 50
            color = QColor(COLOR_PRIMARY)
            color.setAlpha(max(0, alpha))
            painter.setPen(QPen(color, 4, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(arc_rect, (270 + i * 20) * 16, 15 * 16)
        
        painter.restore()
        
        # Loading text
        font = QFont("Segoe UI", 14)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 200))
        text_rect = QRectF(left, center_y + spinner_radius + 20, board_size, 30)
        painter.drawText(text_rect, Qt.AlignCenter, "Generuji puzzle...")
    
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        left, top, board_size, cell = self._board_geometry()
        
        # Draw "no templates" error state
        if self._no_templates:
            self._draw_no_templates(painter, left, top, board_size)
            painter.end()
            return
        
        # Draw loading state
        if self._loading:
            self._draw_loading(painter, left, top, board_size)
            painter.end()
            return
        
        if not self.state:
            painter.end()
            return
        
        grid_size = self.state.size
        
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
        
        # Draw thin grid lines
        painter.setPen(QPen(COLOR_GRID_LINE, 1))
        for i in range(1, grid_size):
            x = left + i * cell
            y = top + i * cell
            painter.drawLine(int(x), int(top), int(x), int(top + board_size))
            painter.drawLine(int(left), int(y), int(left + board_size), int(y))
        
        # Draw cage borders (thick lines)
        painter.setPen(QPen(COLOR_CAGE_LINE, 2.5))
        for cage in self.state.cages:
            edges = self._get_cage_edges(cage)
            for (r, c), direction in edges:
                x = left + c * cell
                y = top + r * cell
                
                if direction == 'top':
                    painter.drawLine(int(x), int(y), int(x + cell), int(y))
                elif direction == 'bottom':
                    painter.drawLine(int(x), int(y + cell), int(x + cell), int(y + cell))
                elif direction == 'left':
                    painter.drawLine(int(x), int(y), int(x), int(y + cell))
                elif direction == 'right':
                    painter.drawLine(int(x + cell), int(y), int(x + cell), int(y + cell))
        
        # Border
        painter.setPen(QPen(COLOR_PRIMARY.darker(150), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(left - 4, top - 4, board_size + 8, board_size + 8), 8, 8)
        
        # Draw cage targets in top-left corner
        target_font_size = max(8, int(cell * 0.25))
        target_font = QFont("Segoe UI", target_font_size, QFont.Bold)
        painter.setFont(target_font)
        painter.setPen(COLOR_CAGE_TARGET)
        
        op_symbols = {'+': '+', '-': '−', '*': '×', '/': '÷', '': ''}
        
        for cage in self.state.cages:
            tr, tc = self._get_cage_top_left(cage)
            x = left + tc * cell + 3
            y = top + tr * cell + 2
            
            op = op_symbols.get(cage.operation, cage.operation)
            target_text = f"{cage.target}{op}"
            
            # Small background for readability
            fm = painter.fontMetrics()
            text_rect = fm.boundingRect(target_text)
            bg_rect = QRectF(x - 1, y, text_rect.width() + 4, text_rect.height() + 2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(18, 22, 32, 200))
            painter.drawRoundedRect(bg_rect, 2, 2)
            
            painter.setPen(COLOR_CAGE_TARGET)
            painter.drawText(int(x), int(y + fm.ascent() + 1), target_text)
        
        # Draw numbers
        num_font_size = max(12, int(cell * 0.45))
        num_font = QFont("Segoe UI", num_font_size, QFont.Bold)
        painter.setFont(num_font)
        
        for r in range(grid_size):
            for c in range(grid_size):
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
                        cell * scale, cell * scale
                    )
                
                # Color
                if self.hint_cell == (r, c):
                    color = COLOR_HINT
                else:
                    color = COLOR_USER
                
                painter.setPen(color)
                painter.drawText(rect, Qt.AlignCenter, str(val))
        
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


class KenKenWidget(QWidget):
    """Main KenKen game widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("KenKenRoot")
        
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
        
        # Size buttons
        lbl_size = QLabel("📐 Velikost:")
        lbl_size.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 12px;")
        row.addWidget(lbl_size)
        
        self._size_buttons = {}
        for size_key, size_label in [("4", "4×4"), ("5", "5×5"), ("6", "6×6"), ("7", "7×7"), ("8", "8×8"), ("9", "9×9")]:
            btn = QPushButton(size_label)
            btn.setCheckable(True)
            btn.setMinimumWidth(48)
            btn.setStyleSheet(self._get_toggle_style())
            btn.clicked.connect(lambda checked, s=size_key: self._on_size_selected(s))
            self._size_buttons[size_key] = btn
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
        self.board = KenKenBoard()
        self.board.on_complete = self._on_complete
        
        lay.addLayout(row)
        lay.addLayout(info)
        lay.addWidget(self.board, 1)
        
        outer.addWidget(frame, 1)
        
        # State
        self.size = 6
        self.game_complete = False
        self.start_time = 0
        self.hints_used = 0
        
        # Background generation
        self._gen_thread: Optional[QThread] = None
        self._gen_worker: Optional[PuzzleGeneratorWorker] = None
        self._generating = False
        
        # Initialize buttons
        self._update_size_buttons("6")
        
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
                padding: 6px 6px;
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
        if self._generating:
            return  # Don't change during generation
        self._update_size_buttons(size)
        self.size = int(size)
        self.new_game()
    
    def _update_size_buttons(self, active: str) -> None:
        for key, btn in self._size_buttons.items():
            btn.setChecked(key == active)
    
    def _cleanup_gen_thread(self) -> None:
        """Clean up previous generation thread if exists."""
        if self._gen_thread is not None:
            if self._gen_thread.isRunning():
                self._gen_thread.quit()
                self._gen_thread.wait(100)  # Wait max 100ms
            self._gen_thread.deleteLater()
            self._gen_thread = None
        if self._gen_worker is not None:
            self._gen_worker.deleteLater()
            self._gen_worker = None
    
    def new_game(self) -> None:
        # Clean up previous thread
        self._cleanup_gen_thread()
        
        self.game_complete = False
        self.start_time = time.time()
        self.hints_used = 0
        self._generating = True
        
        self.lbl_status.setText("⏳ Generuji puzzle...")
        self.lbl_progress.setText("")
        
        # Show loading animation on board
        self.board.set_loading(True, preview_size=self.size)
        
        # Disable buttons during generation
        self.btn_new.setEnabled(False)
        self.btn_hint.setEnabled(False)
        self.btn_print.setEnabled(False)
        
        # Create worker and thread
        self._gen_thread = QThread()
        self._gen_worker = PuzzleGeneratorWorker(self.size)
        self._gen_worker.moveToThread(self._gen_thread)
        
        # Connect signals
        self._gen_thread.started.connect(self._gen_worker.run)
        self._gen_worker.finished.connect(self._on_puzzle_ready)
        self._gen_worker.finished.connect(self._gen_thread.quit)
        
        # Start generation
        self._gen_thread.start()
    
    def _on_puzzle_ready(self, state: Optional[KenKenState]) -> None:
        """Called when puzzle generation is complete."""
        self._generating = False
        
        # Check if generation failed
        if state is None:
            self.board.set_loading(False)
            self.btn_new.setEnabled(True)
            self.btn_hint.setEnabled(False)
            self.btn_print.setEnabled(True)
            self.lbl_status.setText(f"❌ Chyba generování")
            self.lbl_progress.setText("Zkuste znovu")
            return
        
        # Stop loading animation and set state
        self.board.set_loading(False)
        self.board.set_state(state)
        
        # Re-enable buttons
        self.btn_new.setEnabled(True)
        self.btn_hint.setEnabled(True)
        self.btn_print.setEnabled(True)
        
        filled = state.count_filled()
        total = self.size * self.size
        num_cages = len(state.cages)
        
        self.lbl_status.setText(f"🧮 {self.size}×{self.size}")
        self.lbl_progress.setText(f"📦 {num_cages} klecí · 📝 {filled}/{total}")
        
        self.update()
    
    def _on_hint(self) -> None:
        if self.game_complete:
            return
        self.board.show_hint()
        self.hints_used += 1
        self._update_progress()

    def _on_print(self) -> None:
        if self._generating:
            QMessageBox.information(self, "KenKen", "Počkej na dokončení generování aktuální hry.")
            return

        variants = [VariantOption(key=str(size), label=f"{size}×{size}") for size in range(4, 10)]
        dlg = BatchPrintDialog(
            "KenKen tisk",
            variants,
            default_variant_key=str(self.size),
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        requests = dlg.selected_requests()
        total = sum(count for _, count in requests)
        items: List[Tuple[KenKenState, str]] = []
        failures = 0

        progress = QProgressDialog("Generuji KenKen pro tisk...", "Zrušit", 0, total, self)
        progress.setWindowTitle("KenKen")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        generated = 0
        for variant, count in requests:
            size = int(variant.key)
            for _ in range(count):
                if progress.wasCanceled():
                    return
                try:
                    state = create_puzzle(size)
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
            QMessageBox.warning(self, "KenKen", "Nepodařilo se vygenerovat žádnou úlohu pro tisk.")
            return

        printer, pdf_path = create_output_printer(
            self,
            "BrainHub KenKen",
            dlg.output_mode(),
            dlg.pdf_path(),
        )
        if printer is None:
            return

        try:
            draw_square_batch(printer, items, dlg.puzzles_per_page(), _draw_print_kenken)
        except Exception as exc:
            QMessageBox.critical(self, "KenKen", f"Tisk se nepodařil:\n{exc}")
            return

        if pdf_path:
            QMessageBox.information(self, "KenKen", f"PDF vytvořeno:\n{pdf_path}")

        if failures:
            QMessageBox.warning(
                self,
                "KenKen",
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
        self.board.show_overlay(
            "🎉 Gratulace!",
            f"Čas: {time_str}\n{hint_str}",
            self.new_game
        )

    # Lifecycle hooks (called by hub on mount/unmount)
    def on_activate(self) -> None:
        self.board.setFocus()

    def on_deactivate(self) -> None:
        self._cleanup_gen_thread()

    def dispose(self) -> None:
        self._cleanup_gen_thread()
