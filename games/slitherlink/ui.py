"""
Slitherlink UI - Modern game interface

Features:
- Interactive edge drawing (click to toggle line/X/empty)
- Visual feedback for clues and constraints
- Hint system with constraint propagation
- Victory celebration with confetti
- Multiple puzzle sizes and difficulties
"""
from __future__ import annotations

import math
import random
import time
from typing import Dict, List, Optional, Tuple, Set

from PySide6.QtCore import (
    Qt, QTimer, QRectF, QPointF, QThread, Signal, QObject
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QFont, QBrush, QLinearGradient, QPainterPath
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QProgressDialog
)
from hub.printing import BatchPrintDialog, VariantOption, create_output_printer, draw_square_batch

# Import engine
try:
    from . import engine as _engine_module
except ImportError:
    import importlib.util
    from pathlib import Path
    _this_dir = Path(__file__).resolve().parent
    _engine_spec = importlib.util.spec_from_file_location("slitherlink_engine", _this_dir / "engine.py")
    _engine_module = importlib.util.module_from_spec(_engine_spec)
    import sys
    sys.modules["slitherlink_engine"] = _engine_module
    _engine_spec.loader.exec_module(_engine_module)

SlitherlinkState = _engine_module.SlitherlinkState
SlitherlinkPuzzle = _engine_module.SlitherlinkPuzzle
SlitherlinkSolver = _engine_module.SlitherlinkSolver
load_random_puzzle = _engine_module.load_random_puzzle
create_puzzle = _engine_module.create_puzzle


# Colors
COLOR_PRIMARY = QColor(110, 231, 255)      # Cyan
COLOR_SECONDARY = QColor(167, 139, 250)    # Purple
COLOR_LINE = QColor(110, 231, 255)         # Cyan - drawn lines
COLOR_X = QColor(255, 100, 100, 150)       # Red - X marks
COLOR_DOT = QColor(255, 255, 255, 200)     # White - grid dots
COLOR_CLUE = QColor(255, 255, 255, 220)    # White - clue numbers
COLOR_CLUE_SATISFIED = QColor(100, 255, 150, 220)  # Green - satisfied clue
COLOR_CLUE_ERROR = QColor(255, 100, 100, 220)  # Red - error clue
COLOR_HINT = QColor(255, 200, 87)          # Yellow - hint
COLOR_GRID = QColor(255, 255, 255, 30)     # Subtle grid
SLITHERLINK_DIFF_LABELS = {"easy": "Lehká", "medium": "Střední", "hard": "Těžká"}


def _draw_print_slitherlink(
    painter: QPainter,
    tile_rect: QRectF,
    item: Tuple[SlitherlinkState, str],
    _: int,
) -> None:
    state, _label = item
    puzzle = state.puzzle

    painter.save()

    device = painter.device()
    dpi = max(96.0, float(device.logicalDpiX() if device is not None else 300.0))

    def mm(mm_value: float) -> float:
        return (mm_value / 25.4) * dpi

    painter.fillRect(tile_rect, Qt.white)

    pad = max(mm(1.0), tile_rect.width() * 0.015)
    board_rect = tile_rect.adjusted(pad, pad, -pad, -pad)
    board_side = board_rect.width()
    board_left = board_rect.left()
    board_top = board_rect.top()

    n = max(puzzle.width, puzzle.height)
    cell = board_side / float(max(1, n))
    grid_w = puzzle.width * cell
    grid_h = puzzle.height * cell
    grid_left = board_left + (board_side - grid_w) / 2.0
    grid_top = board_top + (board_side - grid_h) / 2.0
    grid_rect = QRectF(grid_left, grid_top, grid_w, grid_h)

    border_w = max(mm(0.95), board_side * 0.0070)
    dot_r = max(mm(1.10), cell * 0.16)

    painter.setPen(QPen(Qt.black, border_w))
    painter.drawRect(grid_rect)

    painter.setPen(Qt.NoPen)
    painter.setBrush(Qt.black)
    for r in range(puzzle.height + 1):
        for c in range(puzzle.width + 1):
            x = grid_left + c * cell
            y = grid_top + r * cell
            painter.drawEllipse(QPointF(x, y), dot_r, dot_r)

    clue_px = int(max(mm(2.0), min(cell * 0.62, cell - mm(0.7))))
    clue_font = QFont("Arial")
    clue_font.setBold(True)
    clue_font.setPixelSize(max(7, clue_px))
    painter.setFont(clue_font)
    painter.setPen(Qt.black)
    for r in range(puzzle.height):
        for c in range(puzzle.width):
            clue = puzzle.clues[r][c]
            if clue is None:
                continue
            rect = QRectF(grid_left + c * cell, grid_top + r * cell, cell, cell)
            painter.drawText(rect, Qt.AlignCenter, str(clue))

    painter.restore()


class PuzzleLoaderWorker(QObject):
    """Worker to load puzzles in background thread."""
    finished = Signal(object)
    
    def __init__(self, size: int, difficulty: str):
        super().__init__()
        self.size = size
        self.difficulty = difficulty
    
    def run(self):
        state = create_puzzle(self.size, self.difficulty)
        self.finished.emit(state)


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


class SlitherlinkBoard(QWidget):
    """Interactive Slitherlink board widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 400)
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.state: Optional[SlitherlinkState] = None
        self.hover_edge: Optional[Tuple[str, int, int]] = None  # ('h'|'v', row, col)
        self.hint_edge: Optional[Tuple[str, int, int, int]] = None  # type, row, col, value
        self.hint_timer: Optional[QTimer] = None
        
        # Loading state
        self._loading = False
        self._loading_angle = 0.0
        self._loading_timer: Optional[QTimer] = None
        self._loading_size = 10
        self._no_templates = False
        
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
        
        self.setMouseTracking(True)
    
    def set_loading(self, loading: bool, preview_size: int = 10) -> None:
        self._loading = loading
        self._loading_size = preview_size
        
        if loading:
            self.state = None
            self._loading_angle = 0.0
            if not self._loading_timer:
                self._loading_timer = QTimer(self)
                self._loading_timer.setInterval(16)
                self._loading_timer.timeout.connect(self._tick_loading)
            self._loading_timer.start()
        else:
            if self._loading_timer:
                self._loading_timer.stop()
        
        self.update()
    
    def _tick_loading(self) -> None:
        self._loading_angle += 5.0
        if self._loading_angle >= 360.0:
            self._loading_angle -= 360.0
        self.update()
    
    def set_no_templates(self, size: int = 10) -> None:
        self._loading = False
        self._no_templates = True
        self._loading_size = size
        self.state = None
        if self._loading_timer:
            self._loading_timer.stop()
        self.update()
    
    def set_state(self, state: SlitherlinkState) -> None:
        self.state = state
        self.hover_edge = None
        self.hint_edge = None
        self._no_templates = False
        self._stop_confetti()
        self._hide_overlay()
        self.update()
    
    def _board_geometry(self) -> Tuple[float, float, float, float]:
        """Get board geometry: (left, top, board_size, cell_size)."""
        size = min(self.width(), self.height())
        margin = 30
        board_size = size - 2 * margin
        left = (self.width() - board_size) / 2
        top = (self.height() - board_size) / 2
        
        if self.state:
            # Use max dimension for cell size
            n = max(self.state.puzzle.width, self.state.puzzle.height)
        else:
            n = self._loading_size
        
        cell = board_size / n if n > 0 else board_size / 10
        return left, top, board_size, cell
    
    def _edge_at_pos(self, x: float, y: float) -> Optional[Tuple[str, int, int]]:
        """Get edge at position, returns ('h'|'v', row, col) or None."""
        if not self.state:
            return None
        
        left, top, board_size, cell = self._board_geometry()
        puzzle = self.state.puzzle
        
        # Convert to grid coordinates
        gx = (x - left) / cell
        gy = (y - top) / cell
        
        # Check bounds
        if gx < -0.3 or gx > puzzle.width + 0.3:
            return None
        if gy < -0.3 or gy > puzzle.height + 0.3:
            return None
        
        # Detection threshold (in cell units)
        threshold = 0.25
        
        # Check horizontal edges
        # H edges are at y = 0, 1, 2, ..., height (between dots)
        for hr in range(puzzle.height + 1):
            if abs(gy - hr) < threshold:
                # We're near a horizontal edge row
                hc = int(gx + 0.5)
                if 0 <= hc < puzzle.width:
                    # Check if we're on the edge (not near a dot)
                    edge_center_x = hc + 0.5
                    if abs(gx - edge_center_x) < 0.4:
                        return ('h', hr, hc)
        
        # Check vertical edges
        for vc in range(puzzle.width + 1):
            if abs(gx - vc) < threshold:
                vr = int(gy + 0.5)
                if 0 <= vr < puzzle.height:
                    edge_center_y = vr + 0.5
                    if abs(gy - edge_center_y) < 0.4:
                        return ('v', vr, vc)
        
        return None
    
    def mousePressEvent(self, event):
        if not self.state or self._overlay_visible:
            # Check overlay button
            if self._overlay_visible and self._overlay_button_rect:
                if self._overlay_button_rect.contains(event.position()):
                    if self._overlay_button_callback:
                        self._overlay_button_callback()
            return
        
        edge = self._edge_at_pos(event.position().x(), event.position().y())
        if edge:
            edge_type, row, col = edge
            if edge_type == 'h':
                self.state.toggle_h_edge(row, col)
            else:
                self.state.toggle_v_edge(row, col)
            
            # Clear hint if we clicked on it
            if self.hint_edge and (edge_type, row, col) == self.hint_edge[:3]:
                self.hint_edge = None
            
            self._check_completion()
            self.update()
    
    def mouseMoveEvent(self, event):
        if not self.state:
            return
        
        edge = self._edge_at_pos(event.position().x(), event.position().y())
        if edge != self.hover_edge:
            self.hover_edge = edge
            self.update()
    
    def leaveEvent(self, event):
        self.hover_edge = None
        self.update()
    
    def _check_completion(self):
        if not self.state:
            return
        
        complete, msg = self.state.is_complete()
        if complete:
            self._show_victory()
    
    def _show_victory(self):
        self._start_confetti()
        self._show_overlay("Vyřešeno!", "Gratulace!", self._hide_overlay)
        if self.on_complete:
            self.on_complete()
    
    def _start_confetti(self):
        if self._confetti_timer:
            return
        
        self._confetti = []
        self._last_confetti_tick = time.time()
        
        # Initial burst
        cx, cy = self.width() / 2, self.height() / 3
        for _ in range(80):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(200, 500)
            self._confetti.append(ConfettiParticle(
                cx, cy,
                math.cos(angle) * speed,
                math.sin(angle) * speed - 200,
                random.uniform(2.0, 4.0),
                random.uniform(6, 14),
                random.choice([COLOR_PRIMARY, COLOR_SECONDARY, QColor(255, 200, 87), QColor(100, 255, 150)])
            ))
        
        self._confetti_timer = QTimer(self)
        self._confetti_timer.setInterval(16)
        self._confetti_timer.timeout.connect(self._tick_confetti)
        self._confetti_timer.start()
    
    def _tick_confetti(self):
        now = time.time()
        dt = now - self._last_confetti_tick
        self._last_confetti_tick = now
        
        gravity = 600
        alive = []
        for p in self._confetti:
            p.age += dt
            if p.age < p.life:
                p.x += p.vx * dt
                p.y += p.vy * dt
                p.vy += gravity * dt
                p.vx *= 0.99
                alive.append(p)
        
        self._confetti = alive
        if not self._confetti:
            self._stop_confetti()
        self.update()
    
    def _stop_confetti(self):
        if self._confetti_timer:
            self._confetti_timer.stop()
            self._confetti_timer = None
        self._confetti = []
    
    def _show_overlay(self, title: str, subtitle: str, callback):
        self._overlay_visible = True
        self._overlay_opacity = 0.0
        self._overlay_title = title
        self._overlay_subtitle = subtitle
        self._overlay_button_callback = callback
        self.update()
    
    def _hide_overlay(self):
        self._overlay_visible = False
        self._overlay_opacity = 0.0
        self._overlay_button_rect = None
        self._stop_confetti()
        self.update()
    
    def show_hint(self):
        """Show and apply a hint using constraint propagation."""
        if not self.state:
            return
        
        solver = SlitherlinkSolver(self.state)
        hint_obj = solver.get_hint_result()
        if hint_obj and hint_obj.cells:
            row, col = hint_obj.cells[0]
            edge_type = str(hint_obj.payload.get("edge_type", "h"))
            value = int(hint_obj.payload.get("value", 0))
            hint = (edge_type, row, col, value)
        else:
            hint = solver.get_hint()
        
        if hint:
            edge_type, row, col, value = hint
            
            # Apply the hint to the state
            if edge_type == 'h':
                self.state.h_edges[row][col] = value
            else:
                self.state.v_edges[row][col] = value
            
            # Show visual feedback
            self.hint_edge = hint
            if self.hint_timer:
                self.hint_timer.stop()
            self.hint_timer = QTimer(self)
            self.hint_timer.setSingleShot(True)
            self.hint_timer.timeout.connect(self._clear_hint)
            self.hint_timer.start(800)  # Shorter time since it's applied
            
            # Check if puzzle is now complete
            self._check_completion()
            self.update()
    
    def _clear_hint(self):
        self.hint_edge = None
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self._loading:
            self._draw_loading(painter)
            return
        
        if self._no_templates:
            self._draw_no_templates(painter)
            return
        
        if not self.state:
            return
        
        self._draw_board(painter)
        self._draw_confetti(painter)
        
        if self._overlay_visible:
            self._draw_overlay(painter)
    
    def _draw_loading(self, painter: QPainter):
        left, top, board_size, cell = self._board_geometry()
        n = self._loading_size
        
        # Draw faint grid
        pen = QPen(COLOR_GRID)
        pen.setWidth(1)
        painter.setPen(pen)
        
        for i in range(n + 1):
            y = top + i * cell
            painter.drawLine(QPointF(left, y), QPointF(left + n * cell, y))
        for j in range(n + 1):
            x = left + j * cell
            painter.drawLine(QPointF(x, top), QPointF(x, top + n * cell))
        
        # Draw spinner
        cx = self.width() / 2
        cy = self.height() / 2
        radius = min(board_size / 4, 60)
        
        for i in range(12):
            angle = math.radians(self._loading_angle + i * 30)
            alpha = int(255 * (1 - i / 12))
            color = QColor(110, 231, 255, alpha)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            
            px = cx + math.cos(angle) * radius
            py = cy + math.sin(angle) * radius
            painter.drawEllipse(QPointF(px, py), 6, 6)
    
    def _draw_no_templates(self, painter: QPainter):
        left, top, board_size, cell = self._board_geometry()
        n = self._loading_size
        
        # Draw faint grid
        pen = QPen(COLOR_GRID)
        pen.setWidth(1)
        painter.setPen(pen)
        
        for i in range(n + 1):
            y = top + i * cell
            painter.drawLine(QPointF(left, y), QPointF(left + n * cell, y))
        for j in range(n + 1):
            x = left + j * cell
            painter.drawLine(QPointF(x, top), QPointF(x, top + n * cell))
        
        # Draw red X
        cx = self.width() / 2
        cy = self.height() / 2
        size = min(board_size / 3, 80)
        
        pen = QPen(QColor(255, 100, 100))
        pen.setWidth(8)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(cx - size, cy - size), QPointF(cx + size, cy + size))
        painter.drawLine(QPointF(cx + size, cy - size), QPointF(cx - size, cy + size))
        
        # Text
        font = QFont()
        font.setPixelSize(16)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 100, 100))
        painter.drawText(
            QRectF(left, cy + size + 20, board_size, 40),
            Qt.AlignCenter,
            "Žádné šablony"
        )
    
    def _draw_board(self, painter: QPainter):
        left, top, board_size, cell = self._board_geometry()
        puzzle = self.state.puzzle
        
        # Draw subtle cell backgrounds
        for r in range(puzzle.height):
            for c in range(puzzle.width):
                x = left + c * cell
                y = top + r * cell
                
                # Very subtle alternating pattern
                if (r + c) % 2 == 0:
                    painter.fillRect(QRectF(x, y, cell, cell), QColor(255, 255, 255, 5))
        
        # Draw edges
        self._draw_edges(painter, left, top, cell)
        
        # Draw dots at vertices
        self._draw_dots(painter, left, top, cell)
        
        # Draw clues
        self._draw_clues(painter, left, top, cell)
        
        # Draw hover
        if self.hover_edge:
            self._draw_hover(painter, left, top, cell)
        
        # Draw hint
        if self.hint_edge:
            self._draw_hint(painter, left, top, cell)
    
    def _draw_edges(self, painter: QPainter, left: float, top: float, cell: float):
        puzzle = self.state.puzzle
        
        line_pen = QPen(COLOR_LINE)
        line_pen.setWidth(max(3, int(cell / 10)))
        line_pen.setCapStyle(Qt.RoundCap)
        
        x_pen = QPen(COLOR_X)
        x_pen.setWidth(2)
        x_pen.setCapStyle(Qt.RoundCap)
        
        # Draw horizontal edges
        for r in range(puzzle.height + 1):
            for c in range(puzzle.width):
                val = self.state.h_edges[r][c]
                x1 = left + c * cell
                x2 = left + (c + 1) * cell
                y = top + r * cell
                
                if val == 1:
                    painter.setPen(line_pen)
                    painter.drawLine(QPointF(x1 + 4, y), QPointF(x2 - 4, y))
                elif val == -1:
                    painter.setPen(x_pen)
                    cx = (x1 + x2) / 2
                    sz = cell / 6
                    painter.drawLine(QPointF(cx - sz, y - sz), QPointF(cx + sz, y + sz))
                    painter.drawLine(QPointF(cx + sz, y - sz), QPointF(cx - sz, y + sz))
        
        # Draw vertical edges
        for r in range(puzzle.height):
            for c in range(puzzle.width + 1):
                val = self.state.v_edges[r][c]
                x = left + c * cell
                y1 = top + r * cell
                y2 = top + (r + 1) * cell
                
                if val == 1:
                    painter.setPen(line_pen)
                    painter.drawLine(QPointF(x, y1 + 4), QPointF(x, y2 - 4))
                elif val == -1:
                    painter.setPen(x_pen)
                    cy = (y1 + y2) / 2
                    sz = cell / 6
                    painter.drawLine(QPointF(x - sz, cy - sz), QPointF(x + sz, cy + sz))
                    painter.drawLine(QPointF(x + sz, cy - sz), QPointF(x - sz, cy + sz))
    
    def _draw_dots(self, painter: QPainter, left: float, top: float, cell: float):
        puzzle = self.state.puzzle
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(COLOR_DOT))
        
        dot_size = max(3, cell / 12)
        
        for r in range(puzzle.height + 1):
            for c in range(puzzle.width + 1):
                x = left + c * cell
                y = top + r * cell
                painter.drawEllipse(QPointF(x, y), dot_size, dot_size)
    
    def _draw_clues(self, painter: QPainter, left: float, top: float, cell: float):
        puzzle = self.state.puzzle
        
        font = QFont()
        font.setPixelSize(int(cell * 0.5))
        font.setBold(True)
        painter.setFont(font)
        
        for r in range(puzzle.height):
            for c in range(puzzle.width):
                clue = puzzle.clues[r][c]
                if clue is None:
                    continue
                
                x = left + c * cell
                y = top + r * cell
                
                # Determine color based on satisfaction
                lines = self.state.count_lines_around_cell(r, c)
                edges = self.state.get_edges_around_cell(r, c)
                x_count = sum(1 for e in edges if e == -1)
                remaining = 4 - x_count
                
                if lines == clue and sum(1 for e in edges if e == 0) == 0:
                    color = COLOR_CLUE_SATISFIED
                elif lines > clue or remaining < clue:
                    color = COLOR_CLUE_ERROR
                else:
                    color = COLOR_CLUE
                
                painter.setPen(color)
                painter.drawText(
                    QRectF(x, y, cell, cell),
                    Qt.AlignCenter,
                    str(clue)
                )
    
    def _draw_hover(self, painter: QPainter, left: float, top: float, cell: float):
        if not self.hover_edge:
            return
        
        edge_type, row, col = self.hover_edge
        
        pen = QPen(QColor(255, 255, 255, 100))
        pen.setWidth(max(4, int(cell / 8)))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        
        if edge_type == 'h':
            x1 = left + col * cell
            x2 = left + (col + 1) * cell
            y = top + row * cell
            painter.drawLine(QPointF(x1 + 4, y), QPointF(x2 - 4, y))
        else:
            x = left + col * cell
            y1 = top + row * cell
            y2 = top + (row + 1) * cell
            painter.drawLine(QPointF(x, y1 + 4), QPointF(x, y2 - 4))
    
    def _draw_hint(self, painter: QPainter, left: float, top: float, cell: float):
        if not self.hint_edge:
            return
        
        edge_type, row, col, val = self.hint_edge
        
        pen = QPen(COLOR_HINT)
        pen.setWidth(max(4, int(cell / 8)))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        
        if edge_type == 'h':
            x1 = left + col * cell
            x2 = left + (col + 1) * cell
            y = top + row * cell
            if val == 1:
                painter.drawLine(QPointF(x1 + 4, y), QPointF(x2 - 4, y))
            else:
                cx = (x1 + x2) / 2
                sz = cell / 6
                painter.drawLine(QPointF(cx - sz, y - sz), QPointF(cx + sz, y + sz))
                painter.drawLine(QPointF(cx + sz, y - sz), QPointF(cx - sz, y + sz))
        else:
            x = left + col * cell
            y1 = top + row * cell
            y2 = top + (row + 1) * cell
            if val == 1:
                painter.drawLine(QPointF(x, y1 + 4), QPointF(x, y2 - 4))
            else:
                cy = (y1 + y2) / 2
                sz = cell / 6
                painter.drawLine(QPointF(x - sz, cy - sz), QPointF(x + sz, cy + sz))
                painter.drawLine(QPointF(x + sz, cy - sz), QPointF(x - sz, cy + sz))
    
    def _draw_confetti(self, painter: QPainter):
        painter.setPen(Qt.NoPen)
        for p in self._confetti:
            alpha = int(255 * (1 - p.age / p.life))
            color = QColor(p.color.red(), p.color.green(), p.color.blue(), alpha)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPointF(p.x, p.y), p.size, p.size)
    
    def _draw_overlay(self, painter: QPainter):
        # Background
        painter.fillRect(self.rect(), QColor(0, 0, 0, 180))
        
        cx = self.width() / 2
        cy = self.height() / 2
        
        # Title
        font = QFont()
        font.setPixelSize(48)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(COLOR_PRIMARY)
        painter.drawText(
            QRectF(0, cy - 80, self.width(), 60),
            Qt.AlignCenter,
            self._overlay_title
        )
        
        # Subtitle
        font.setPixelSize(20)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 180))
        painter.drawText(
            QRectF(0, cy - 20, self.width(), 30),
            Qt.AlignCenter,
            self._overlay_subtitle
        )
        
        # Button
        btn_w, btn_h = 160, 44
        btn_rect = QRectF(cx - btn_w / 2, cy + 40, btn_w, btn_h)
        self._overlay_button_rect = btn_rect
        
        painter.setBrush(QBrush(COLOR_PRIMARY))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(btn_rect, 8, 8)
        
        font.setPixelSize(16)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(0, 0, 0))
        painter.drawText(btn_rect, Qt.AlignCenter, "Pokračovat")


class SlitherlinkWidget(QWidget):
    """Main Slitherlink game widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._current_size = 10
        self._current_difficulty = "medium"
        self._loading_puzzle = False
        self._loader_thread: Optional[QThread] = None
        self._loader_worker: Optional[PuzzleLoaderWorker] = None
        self._solve_timer: Optional[QTimer] = None
        
        self._setup_ui()
        self._load_puzzle()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Header
        header = QHBoxLayout()
        header.setSpacing(8)
        
        title = QLabel("Slitherlink")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #6ee7ff;")
        header.addWidget(title)
        header.addStretch()
        
        # Size selector
        size_label = QLabel("Velikost:")
        size_label.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.7);")
        header.addWidget(size_label)
        
        self._size_buttons = {}
        for size in [7, 10, 15]:
            btn = QPushButton(f"{size}×{size}")
            btn.setCheckable(True)
            btn.setChecked(size == self._current_size)
            btn.setStyleSheet(self._button_style(size == self._current_size))
            btn.clicked.connect(lambda checked, s=size: self._set_size(s))
            header.addWidget(btn)
            self._size_buttons[size] = btn
        
        header.addSpacing(16)
        
        # Difficulty selector
        diff_label = QLabel("Obtížnost:")
        diff_label.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.7);")
        header.addWidget(diff_label)
        
        self._diff_buttons = {}
        for diff, label in [("easy", "Lehká"), ("medium", "Střední"), ("hard", "Těžká")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(diff == self._current_difficulty)
            btn.setStyleSheet(self._button_style(diff == self._current_difficulty))
            btn.clicked.connect(lambda checked, d=diff: self._set_difficulty(d))
            header.addWidget(btn)
            self._diff_buttons[diff] = btn
        
        layout.addLayout(header)
        
        # Board
        self._board = SlitherlinkBoard()
        layout.addWidget(self._board, 1)
        
        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(8)
        
        self._new_btn = QPushButton("Nová hra")
        self._new_btn.setStyleSheet(self._action_button_style())
        self._new_btn.clicked.connect(self._load_puzzle)
        footer.addWidget(self._new_btn)
        
        self._hint_btn = QPushButton("Nápověda")
        self._hint_btn.setStyleSheet(self._action_button_style(secondary=True))
        self._hint_btn.clicked.connect(self._board.show_hint)
        footer.addWidget(self._hint_btn)
        
        self._solve_btn = QPushButton("Vyřešit")
        self._solve_btn.setStyleSheet(self._action_button_style(secondary=True))
        self._solve_btn.clicked.connect(self._auto_solve)
        footer.addWidget(self._solve_btn)
        
        self._clear_btn = QPushButton("Vymazat")
        self._clear_btn.setStyleSheet(self._action_button_style(secondary=True))
        self._clear_btn.clicked.connect(self._clear_board)
        footer.addWidget(self._clear_btn)

        self._print_btn = QPushButton("Tisk/PDF")
        self._print_btn.setStyleSheet(self._action_button_style(secondary=True))
        self._print_btn.clicked.connect(self._on_print)
        footer.addWidget(self._print_btn)
        
        footer.addStretch()
        
        # Status
        self._status = QLabel("")
        self._status.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.6);")
        footer.addWidget(self._status)
        
        layout.addLayout(footer)
        
    def _stop_solve_timer(self) -> None:
        if self._solve_timer:
            self._solve_timer.stop()
            self._solve_timer.deleteLater()
            self._solve_timer = None

    def _cleanup_loader_thread(self) -> None:
        if self._loader_thread is not None:
            if self._loader_thread.isRunning():
                self._loader_thread.quit()
                if not self._loader_thread.wait(1200):
                    self._loader_thread.terminate()
                    self._loader_thread.wait()
            self._loader_thread.deleteLater()
            self._loader_thread = None

        if self._loader_worker is not None:
            self._loader_worker.deleteLater()
            self._loader_worker = None
    
    def _button_style(self, selected: bool) -> str:
        if selected:
            return """
                QPushButton {
                    background: rgba(110, 231, 255, 0.2);
                    border: 1px solid rgba(110, 231, 255, 0.5);
                    border-radius: 6px;
                    padding: 6px 12px;
                    color: #6ee7ff;
                    font-size: 13px;
                    font-weight: bold;
                }
            """
        return """
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 6px 12px;
                color: rgba(255, 255, 255, 0.7);
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                border-color: rgba(255, 255, 255, 0.2);
            }
        """
    
    def _action_button_style(self, secondary: bool = False) -> str:
        if secondary:
            return """
                QPushButton {
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 8px;
                    padding: 10px 20px;
                    color: rgba(255, 255, 255, 0.9);
                    font-size: 14px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.12);
                }
            """
        return """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(110, 231, 255, 0.9), stop:1 rgba(167, 139, 250, 0.9));
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                color: #000;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(130, 241, 255, 1), stop:1 rgba(187, 159, 255, 1));
            }
        """
    
    def _set_size(self, size: int):
        self._current_size = size
        for s, btn in self._size_buttons.items():
            btn.setChecked(s == size)
            btn.setStyleSheet(self._button_style(s == size))
        self._load_puzzle()
    
    def _set_difficulty(self, diff: str):
        self._current_difficulty = diff
        for d, btn in self._diff_buttons.items():
            btn.setChecked(d == diff)
            btn.setStyleSheet(self._button_style(d == diff))
        self._load_puzzle()
    
    def _load_puzzle(self):
        self._cleanup_loader_thread()
        self._loading_puzzle = True
        self._board.set_loading(True, self._current_size)
        self._status.setText("Načítání...")
        self._print_btn.setEnabled(False)
        
        # Load in background
        self._loader_thread = QThread()
        self._loader_worker = PuzzleLoaderWorker(self._current_size, self._current_difficulty)
        self._loader_worker.moveToThread(self._loader_thread)
        
        self._loader_thread.started.connect(self._loader_worker.run)
        self._loader_worker.finished.connect(self._on_puzzle_loaded)
        self._loader_worker.finished.connect(self._loader_thread.quit)
        self._loader_thread.finished.connect(self._cleanup_loader_thread)
        
        self._loader_thread.start()
    
    def _on_puzzle_loaded(self, state: Optional[SlitherlinkState]):
        self._loading_puzzle = False
        self._board.set_loading(False)
        self._print_btn.setEnabled(True)
        
        if state:
            self._board.set_state(state)
            w, h = state.puzzle.width, state.puzzle.height
            self._status.setText(f"{w}×{h} | {self._current_difficulty.capitalize()}")
        else:
            self._board.set_no_templates(self._current_size)
            self._status.setText("Žádné šablony k dispozici")

    def _on_print(self):
        if self._loading_puzzle:
            QMessageBox.information(self, "Slitherlink", "Počkej na dokončení načítání aktuální hry.")
            return

        variants: List[VariantOption] = []
        for size in (7, 10, 15):
            for diff in ("easy", "medium", "hard"):
                variants.append(
                    VariantOption(
                        key=f"{size}:{diff}",
                        label=f"{size}×{size} · {SLITHERLINK_DIFF_LABELS[diff]}",
                    )
                )

        dlg = BatchPrintDialog(
            "Slitherlink tisk",
            variants,
            default_variant_key=f"{self._current_size}:{self._current_difficulty}",
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        requests = dlg.selected_requests()
        total = sum(count for _, count in requests)
        items: List[Tuple[SlitherlinkState, str]] = []
        failures = 0

        progress = QProgressDialog("Generuji Slitherlink pro tisk...", "Zrušit", 0, total, self)
        progress.setWindowTitle("Slitherlink")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        generated = 0
        for variant, count in requests:
            size_s, diff = variant.key.split(":")
            size = int(size_s)
            for _ in range(count):
                if progress.wasCanceled():
                    return
                state: Optional[SlitherlinkState] = None
                for _attempt in range(3):
                    state = create_puzzle(size, diff)
                    if state is not None:
                        break
                if state is not None:
                    items.append((state, variant.label))
                else:
                    failures += 1
                generated += 1
                progress.setValue(generated)
                QApplication.processEvents()
        progress.setValue(total)

        if not items:
            QMessageBox.warning(self, "Slitherlink", "Nepodařilo se vygenerovat žádnou úlohu pro tisk.")
            return

        printer, pdf_path = create_output_printer(
            self,
            "BrainHub Slitherlink",
            dlg.output_mode(),
            dlg.pdf_path(),
        )
        if printer is None:
            return

        try:
            draw_square_batch(printer, items, dlg.puzzles_per_page(), _draw_print_slitherlink)
        except Exception as exc:
            QMessageBox.critical(self, "Slitherlink", f"Tisk se nepodařil:\n{exc}")
            return

        if pdf_path:
            QMessageBox.information(self, "Slitherlink", f"PDF vytvořeno:\n{pdf_path}")

        if failures:
            QMessageBox.warning(
                self,
                "Slitherlink",
                f"{failures} úloh se nepodařilo vygenerovat a nebyly zahrnuty do výstupu.",
            )
    
    def _auto_solve(self):
        """Automatically solve the puzzle step by step with animation using stored solution."""
        if not self._board.state:
            return
        
        puzzle = self._board.state.puzzle
        
        # Stop any existing solve timer
        self._stop_solve_timer()
        
        # Try to get solution - first from stored, then from solver
        solution_h = puzzle.solution_h
        solution_v = puzzle.solution_v
        
        if not solution_h or not solution_v:
            # No stored solution, use full solver
            self._status.setText("Řeším...")
            QApplication.processEvents()
            
            solver = SlitherlinkSolver(self._board.state)
            solved = solver.solve()
            
            if solved:
                solution_h = [[1 if e == 1 else 0 for e in row] for row in solved.h_edges]
                solution_v = [[1 if e == 1 else 0 for e in row] for row in solved.v_edges]
                self._status.setText("Řešení nalezeno")
            else:
                self._status.setText("Nelze vyřešit")
                return
        
        # Build list of edges to reveal from solution
        self._solve_edges = []
        
        # Collect horizontal edges that should be lines
        for r in range(len(solution_h)):
            for c in range(len(solution_h[r])):
                if solution_h[r][c]:
                    if self._board.state.h_edges[r][c] != 1:
                        self._solve_edges.append(('h', r, c, 1))
        
        # Collect vertical edges that should be lines
        for r in range(len(solution_v)):
            for c in range(len(solution_v[r])):
                if solution_v[r][c]:
                    if self._board.state.v_edges[r][c] != 1:
                        self._solve_edges.append(('v', r, c, 1))
        
        # Shuffle for visual interest
        import random
        random.shuffle(self._solve_edges)
        
        # Start animation
        self._solve_index = 0
        self._solve_timer = QTimer(self)
        self._solve_timer.setInterval(50)  # 50ms between edges
        self._solve_timer.timeout.connect(self._solve_step_from_solution)
        self._solve_timer.start()
    
    def _solve_step_from_solution(self):
        """Apply one edge from the stored solution."""
        if not self._board.state or self._solve_index >= len(self._solve_edges):
            self._stop_solve_timer()
            self._board.hint_edge = None
            self._board._check_completion()
            self._board.update()
            return
        
        edge_type, row, col, value = self._solve_edges[self._solve_index]
        self._solve_index += 1
        
        if edge_type == 'h':
            self._board.state.h_edges[row][col] = value
        else:
            self._board.state.v_edges[row][col] = value
        
        self._board.hint_edge = (edge_type, row, col, value)
        self._board.update()
    
    def _auto_solve_with_hints(self):
        """Fallback: solve using constraint propagation hints."""
        self._stop_solve_timer()
        
        self._solve_timer = QTimer(self)
        self._solve_timer.setInterval(100)
        self._solve_timer.timeout.connect(self._solve_step)
        self._solve_timer.start()
    
    def _solve_step(self):
        """Apply one hint step."""
        if not self._board.state:
            self._stop_solve_timer()
            return
        
        # Check if already solved
        complete, _ = self._board.state.is_complete()
        if complete:
            self._stop_solve_timer()
            return
        
        # Try to get and apply a hint
        solver = SlitherlinkSolver(self._board.state)
        hint = solver.get_hint()
        
        if hint:
            edge_type, row, col, value = hint
            if edge_type == 'h':
                self._board.state.h_edges[row][col] = value
            else:
                self._board.state.v_edges[row][col] = value
            
            self._board.hint_edge = hint
            self._board.update()
            
            # Check completion
            self._board._check_completion()
        else:
            # No more hints available (stuck or solved)
            self._stop_solve_timer()
            self._board.hint_edge = None
            self._board.update()
    
    def _clear_board(self):
        # Stop auto-solve if running
        self._stop_solve_timer()
        if self._board.state:
            self._board.state.clear()
            self._board.update()

    # Lifecycle hooks (called by hub on mount/unmount)
    def on_activate(self) -> None:
        self._board.setFocus()

    def on_deactivate(self) -> None:
        self._stop_solve_timer()
        self._cleanup_loader_thread()
        self._loading_puzzle = False

    def dispose(self) -> None:
        self._stop_solve_timer()
        self._cleanup_loader_thread()
        self._loading_puzzle = False

    def closeEvent(self, event) -> None:
        self.dispose()
        super().closeEvent(event)
