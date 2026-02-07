"""
Piškvorky / Gomoku UI - Professional Version

Features:
- Overlay notifications over the game board
- Turn indicator with transparent player symbol in background
- Fixed Swap2 logic for 13×13 (Gomoku)
- Async AI computation to prevent UI freezing
- Smooth animations and visual feedback
"""
from __future__ import annotations

import importlib.util
import math
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable

from PySide6.QtCore import (
    Qt, QTimer, QRectF, QVariantAnimation, QEasingCurve, 
    QPointF
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QFont, QPainterPath, QBrush,
    QLinearGradient, QRadialGradient
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QComboBox, QFrame, QSizePolicy, QStackedLayout, QGraphicsOpacityEffect
)
from hub.worker import WorkerHandle, run_in_worker

_THIS_DIR = Path(__file__).resolve().parent


def _load_local_module(module_name: str, path: Path):
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_engine_module = _load_local_module("piskvorky_engine", _THIS_DIR / "engine.py")
_ai_module = _load_local_module("piskvorky_ai", _THIS_DIR / "ai.py")
_stats_module = _load_local_module("piskvorky_stats", _THIS_DIR / "stats.py")

GameState = _engine_module.GameState
check_winner = _engine_module.check_winner
get_cell_lines = _engine_module.get_cell_lines

best_move_easy = _ai_module.best_move_easy
best_move_medium = _ai_module.best_move_medium
best_move_hard = _ai_module.best_move_hard
evaluate = _ai_module.evaluate
win_probability_from_score = _ai_module.win_probability_from_score
SearchResult = _ai_module.SearchResult
warmup = _ai_module.warmup

appdata_file = _stats_module.appdata_file
load_stats = _stats_module.load_stats
save_stats = _stats_module.save_stats
expected_score = _stats_module.expected_score
update_elo = _stats_module.update_elo
get_config_key = _stats_module.get_config_key
get_rating = _stats_module.get_rating
get_record = _stats_module.get_record
set_rating = _stats_module.set_rating
set_record = _stats_module.set_record
add_history = _stats_module.add_history
Record = _stats_module.Record


DIFF_MAP = {"Lehká": "easy", "Střední": "medium", "Těžká": "hard"}
DIFF_LABELS = {"easy": "Lehká", "medium": "Střední", "hard": "Těžká"}
BOT_RATING = {"easy": 800.0, "medium": 1200.0, "hard": 1600.0}

# Colors
COLOR_X = QColor(110, 231, 255)      # Cyan for X
COLOR_O = QColor(167, 139, 250)      # Purple for O
COLOR_OVERLAY_BG = QColor(14, 17, 26, 230)
COLOR_WIN_LINE = QColor(110, 231, 255, 180)


@dataclass
class AnimMark:
    progress: float = 0.0


@dataclass
class ConfettiParticle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    age: float
    size: float
    color: QColor


class BoardWidget(QWidget):
    """Game board with turn indicator and overlay support."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 400)
        self.n = 3
        self.state = GameState.new(3, to_move=1)
        self.human = 1
        self.bot = -1
        self.enabled_input = True
        self.winning_coords: Optional[List[Tuple[int, int]]] = None
        self._marks: Dict[int, AnimMark] = {}
        self._win_anim = 0.0
        self._bounce_curve = QEasingCurve(QEasingCurve.OutBounce)
        self._trail_steps = 3

        # Confetti
        self._confetti: List[ConfettiParticle] = []
        self._confetti_timer: Optional[QTimer] = None
        self._last_confetti_tick = time.time()

        # Turn indicator animation
        self._turn_pulse = 0.0
        self._turn_pulse_timer = QTimer(self)
        self._turn_pulse_timer.setInterval(50)
        self._turn_pulse_timer.timeout.connect(self._pulse_turn)
        self._turn_pulse_timer.start()

        # Overlay state
        self._overlay_visible = False
        self._overlay_opacity = 0.0
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._overlay_timer: Optional[QTimer] = None
        self._overlay_button_callback: Optional[Callable] = None
        self._overlay_button_rect: Optional[QRectF] = None

        self.on_human_move: Optional[Callable[[int], None]] = None
        self.on_free_place: Optional[Callable[[int], None]] = None

    def reset(self, n: int, to_move: int, human: int, bot: int) -> None:
        self.n = n
        self.state = GameState.new(n, to_move=to_move)
        self.human = human
        self.bot = bot
        self.enabled_input = True
        self.winning_coords = None
        self._marks.clear()
        self._win_anim = 0.0
        self._stop_confetti()
        self._hide_overlay_immediate()
        self.update()

    def sizeHint(self):
        return self.minimumSize()

    def disable(self) -> None:
        self.enabled_input = False
        self.update()

    def enable(self) -> None:
        self.enabled_input = True
        self.update()

    def _pulse_turn(self):
        """Animate turn indicator pulse."""
        self._turn_pulse = (self._turn_pulse + 0.08) % (2 * math.pi)
        self.update()

    def cell_at_pos(self, x: float, y: float) -> Optional[int]:
        n = self.n
        size = min(self.width(), self.height())
        margin = 18
        board_size = size - 2 * margin
        if board_size <= 0:
            return None
        left = (self.width() - board_size) / 2
        top = (self.height() - board_size) / 2
        if not (left <= x <= left + board_size and top <= y <= top + board_size):
            return None
        cell = board_size / n
        c = int((x - left) // cell)
        r = int((y - top) // cell)
        if 0 <= r < n and 0 <= c < n:
            return r * n + c
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        
        # Check if clicking overlay button
        if (self._overlay_visible and self._overlay_button_callback 
            and self._overlay_button_rect is not None):
            pos = event.position()
            if self._overlay_button_rect.contains(pos):
                callback = self._overlay_button_callback
                self._hide_overlay_immediate()
                callback()
                return
        
        if not self.enabled_input:
            return
        idx = self.cell_at_pos(event.position().x(), event.position().y())
        if idx is None:
            return
        if self.state.board[idx] != 0:
            return
        if self.on_free_place:
            self.on_free_place(idx)
            return
        if self.state.to_move != self.human:
            return
        if self.on_human_move:
            self.on_human_move(idx)

    def animate_mark(self, idx: int) -> None:
        am = AnimMark(progress=0.0)
        self._marks[idx] = am
        anim = QVariantAnimation(self)
        anim.setDuration(190)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutBack)

        def on_val(v):
            am.progress = float(v)
            self.update()

        anim.valueChanged.connect(on_val)
        anim.start()
        self._marks[idx]._anim = anim  # type: ignore

    def animate_win(self) -> None:
        self._win_anim = 0.0
        anim = QVariantAnimation(self)
        anim.setDuration(380)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def on_val(v):
            self._win_anim = float(v)
            self.update()

        anim.valueChanged.connect(on_val)
        anim.start()
        self._win_anim_obj = anim  # type: ignore

    def show_overlay(self, title: str, subtitle: str = "", duration_ms: int = 2500) -> None:
        """Show overlay notification over the board."""
        self._overlay_title = title
        self._overlay_subtitle = subtitle
        self._overlay_visible = True
        self._overlay_opacity = 0.0
        self._overlay_button_callback = None  # No button
        
        # Fade in animation
        anim = QVariantAnimation(self)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        
        def on_fade_in(v):
            self._overlay_opacity = float(v)
            self.update()
        
        anim.valueChanged.connect(on_fade_in)
        anim.start()
        self._overlay_fade_anim = anim
        
        # Auto-hide after duration
        if self._overlay_timer:
            self._overlay_timer.stop()
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setSingleShot(True)
        self._overlay_timer.timeout.connect(self._fade_out_overlay)
        self._overlay_timer.start(duration_ms)

    def show_overlay_with_button(self, title: str, subtitle: str = "", 
                                  on_button_click: Optional[Callable] = None) -> None:
        """Show overlay with 'Play Again' button - stays until button clicked."""
        self._overlay_title = title
        self._overlay_subtitle = subtitle
        self._overlay_visible = True
        self._overlay_opacity = 0.0
        self._overlay_button_callback = on_button_click
        
        # Stop any existing timer
        if self._overlay_timer:
            self._overlay_timer.stop()
            self._overlay_timer = None
        
        # Fade in animation
        anim = QVariantAnimation(self)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        
        def on_fade_in(v):
            self._overlay_opacity = float(v)
            self.update()
        
        anim.valueChanged.connect(on_fade_in)
        anim.start()
        self._overlay_fade_anim = anim

    def _fade_out_overlay(self) -> None:
        """Fade out the overlay."""
        anim = QVariantAnimation(self)
        anim.setDuration(300)
        anim.setStartValue(self._overlay_opacity)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InCubic)
        
        def on_fade_out(v):
            self._overlay_opacity = float(v)
            if float(v) <= 0.01:
                self._overlay_visible = False
            self.update()
        
        anim.valueChanged.connect(on_fade_out)
        anim.start()
        self._overlay_fade_anim = anim

    def _hide_overlay_immediate(self) -> None:
        """Immediately hide overlay without animation."""
        if self._overlay_timer:
            self._overlay_timer.stop()
            self._overlay_timer = None
        self._overlay_visible = False
        self._overlay_opacity = 0.0
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        n = self.n
        size = min(self.width(), self.height())
        margin = 18
        board_size = size - 2 * margin
        left = (self.width() - board_size) / 2
        top = (self.height() - board_size) / 2

        # Draw turn indicator background with transparent symbol
        self._draw_turn_background(painter, left, top, board_size)

        # Board background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(18, 22, 32, 140))
        painter.drawRoundedRect(QRectF(left - 10, top - 10, board_size + 20, board_size + 20), 16, 16)

        # Grid
        grid_pen = QPen(QColor(255, 255, 255, 35), 2)
        painter.setPen(grid_pen)
        cell = board_size / n
        for i in range(1, n):
            x = left + i * cell
            y = top + i * cell
            painter.drawLine(int(x), int(top), int(x), int(top + board_size))
            painter.drawLine(int(left), int(y), int(left + board_size), int(y))

        # Marks
        for idx, v in enumerate(self.state.board):
            if v == 0:
                continue
            r = idx // n
            c = idx % n
            cx = left + c * cell
            cy = top + r * cell
            rect = QRectF(cx, cy, cell, cell)

            prog = self._marks.get(idx, AnimMark(1.0)).progress if idx in self._marks else 1.0
            self._paint_mark_with_trail(painter, rect, v, prog)

        # Winning highlight
        if self.winning_coords:
            painter.save()
            painter.setOpacity(0.25 + 0.55 * self._win_anim)
            pen = QPen(COLOR_WIN_LINE, 8)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            pts = []
            for (rr, cc) in self.winning_coords:
                pts.append(QRectF(left + cc * cell, top + rr * cell, cell, cell).center())
            if len(pts) >= 2:
                painter.drawLine(pts[0], pts[-1])
            painter.restore()

        # Confetti overlay
        if self._confetti:
            painter.save()
            painter.setPen(Qt.NoPen)
            for p in self._confetti:
                life_ratio = max(0.0, 1.0 - p.age / p.life)
                painter.setOpacity(life_ratio)
                painter.setBrush(p.color)
                painter.drawRect(QRectF(p.x, p.y, p.size, p.size))
            painter.restore()

        # Draw overlay notification
        if self._overlay_visible and self._overlay_opacity > 0.01:
            self._draw_overlay(painter, left, top, board_size)

        painter.end()

    def _draw_turn_background(self, painter: QPainter, left: float, top: float, board_size: float) -> None:
        """Draw turn indicator with large transparent symbol in background."""
        if self.winning_coords is not None:
            return  # Don't show turn indicator when game is over
        
        current_player = self.state.to_move
        is_human_turn = (current_player == self.human)
        
        # Pulsing opacity - STRONGER visibility
        pulse = 0.18 + 0.08 * math.sin(self._turn_pulse)
        
        # Color based on whose turn
        if current_player == 1:
            color = QColor(COLOR_X.red(), COLOR_X.green(), COLOR_X.blue(), int(255 * pulse))
        else:
            color = QColor(COLOR_O.red(), COLOR_O.green(), COLOR_O.blue(), int(255 * pulse))
        
        painter.save()
        
        # Draw large symbol in center
        symbol_size = board_size * 0.6
        cx = left + board_size / 2
        cy = top + board_size / 2
        rect = QRectF(cx - symbol_size/2, cy - symbol_size/2, symbol_size, symbol_size)
        
        if current_player == 1:
            # Draw large X
            pad = symbol_size * 0.15
            pen = QPen(color, symbol_size * 0.08)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(
                QPointF(rect.left() + pad, rect.top() + pad),
                QPointF(rect.right() - pad, rect.bottom() - pad)
            )
            painter.drawLine(
                QPointF(rect.left() + pad, rect.bottom() - pad),
                QPointF(rect.right() - pad, rect.top() + pad)
            )
        else:
            # Draw large O
            pad = symbol_size * 0.15
            pen = QPen(color, symbol_size * 0.08)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawEllipse(rect.adjusted(pad, pad, -pad, -pad))
        
        painter.restore()

    def _draw_overlay(self, painter: QPainter, left: float, top: float, board_size: float) -> None:
        """Draw overlay notification over the board."""
        painter.save()
        painter.setOpacity(self._overlay_opacity)
        
        # Semi-transparent background
        overlay_rect = QRectF(left - 10, top - 10, board_size + 20, board_size + 20)
        painter.setPen(Qt.NoPen)
        painter.setBrush(COLOR_OVERLAY_BG)
        painter.drawRoundedRect(overlay_rect, 16, 16)
        
        # Border glow
        border_pen = QPen(QColor(110, 231, 255, 100), 2)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(overlay_rect.adjusted(2, 2, -2, -2), 14, 14)
        
        # Title
        title_font = QFont("Segoe UI", 22, QFont.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255))
        
        title_rect = QRectF(left, top + board_size * 0.30, board_size, 40)
        painter.drawText(title_rect, Qt.AlignCenter, self._overlay_title)
        
        # Subtitle
        if self._overlay_subtitle:
            sub_font = QFont("Segoe UI", 13)
            painter.setFont(sub_font)
            painter.setPen(QColor(255, 255, 255, 180))
            
            sub_rect = QRectF(left + 20, top + board_size * 0.42, board_size - 40, 60)
            painter.drawText(sub_rect, Qt.AlignCenter | Qt.TextWordWrap, self._overlay_subtitle)
        
        # Draw "Play Again" button if callback is set
        if self._overlay_button_callback is not None:
            btn_w, btn_h = 160, 44
            btn_x = left + (board_size - btn_w) / 2
            btn_y = top + board_size * 0.65
            btn_rect = QRectF(btn_x, btn_y, btn_w, btn_h)
            self._overlay_button_rect = btn_rect
            
            # Button gradient background
            gradient = QLinearGradient(btn_rect.topLeft(), btn_rect.bottomRight())
            gradient.setColorAt(0, QColor(110, 231, 255, 220))
            gradient.setColorAt(1, QColor(167, 139, 250, 220))
            
            painter.setPen(Qt.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(btn_rect, 10, 10)
            
            # Button text
            btn_font = QFont("Segoe UI", 14, QFont.Bold)
            painter.setFont(btn_font)
            painter.setPen(QColor(20, 24, 36))
            painter.drawText(btn_rect, Qt.AlignCenter, "🔄 Hrát znovu")
        else:
            self._overlay_button_rect = None
        
        painter.restore()

    def _board_geometry(self) -> Tuple[float, float, float, float]:
        size = min(self.width(), self.height())
        margin = 18
        board_size = size - 2 * margin
        left = (self.width() - board_size) / 2
        top = (self.height() - board_size) / 2
        cell = board_size / self.n
        return left, top, board_size, cell

    def _spawn_confetti(self) -> None:
        left, top, board_size, _ = self._board_geometry()
        colors = [COLOR_X, COLOR_O, QColor(255, 200, 87), QColor(255, 138, 128)]

        count = 60 + self.n * 12
        self._confetti = []
        for _ in range(count):
            x = left + random.random() * board_size
            y = top - random.random() * board_size * 0.25
            speed = random.uniform(140.0, 240.0)
            angle = random.uniform(-math.pi / 3, math.pi / 3)
            vx = speed * math.sin(angle)
            vy = -abs(speed * math.cos(angle) * 0.7)
            size = random.uniform(5.0, 10.0)
            life = random.uniform(1.2, 1.9)
            color = random.choice(colors)
            self._confetti.append(
                ConfettiParticle(x=x, y=y, vx=vx, vy=vy, life=life, age=0.0, size=size, color=color)
            )

        self._ensure_confetti_timer()

    def _ensure_confetti_timer(self) -> None:
        self._last_confetti_tick = time.time()
        if self._confetti_timer is None:
            timer = QTimer(self)
            timer.setInterval(16)
            timer.timeout.connect(self._tick_confetti)
            timer.start()
            self._confetti_timer = timer

    def _tick_confetti(self) -> None:
        now = time.time()
        dt = max(0.001, now - self._last_confetti_tick)
        self._last_confetti_tick = now

        gravity = 920.0
        damping = 0.985
        alive: List[ConfettiParticle] = []
        for p in self._confetti:
            p.age += dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += gravity * dt
            p.vx *= damping
            p.vy *= damping

            if p.age < p.life and p.y < self.height() + 60:
                alive.append(p)

        self._confetti = alive
        if not self._confetti:
            self._stop_confetti()
        self.update()

    def _stop_confetti(self) -> None:
        if self._confetti_timer:
            self._confetti_timer.stop()
            self._confetti_timer.deleteLater()
            self._confetti_timer = None
        self._confetti.clear()

    def celebrate_win(self) -> None:
        self._spawn_confetti()

    def _draw_x(self, painter: QPainter, rect: QRectF) -> None:
        pad = rect.width() * 0.22
        pen = QPen(QColor(110, 231, 255, 220), 6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(
            QPointF(rect.left() + pad, rect.top() + pad),
            QPointF(rect.right() - pad, rect.bottom() - pad)
        )
        painter.drawLine(
            QPointF(rect.left() + pad, rect.bottom() - pad),
            QPointF(rect.right() - pad, rect.top() + pad)
        )

    def _draw_o(self, painter: QPainter, rect: QRectF) -> None:
        pad = rect.width() * 0.22
        pen = QPen(QColor(167, 139, 250, 220), 6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(rect.adjusted(pad, pad, -pad, -pad))

    def _paint_mark_with_trail(self, painter: QPainter, rect: QRectF, value: int, prog: float) -> None:
        base_opacity = min(1.0, 0.2 + 0.8 * prog)
        bounce_base = 12 + max(0, self.n - 3) * 2

        for step in range(self._trail_steps, -1, -1):
            trail_prog = prog - step * 0.12
            if trail_prog <= 0:
                continue

            decay = 1.0 - (step / (self._trail_steps + 1))
            opacity = base_opacity * decay * (0.65 if step else 1.0)
            eased = self._bounce_curve.valueForProgress(min(1.0, trail_prog))
            bounce = (1.0 - eased) * bounce_base
            scale = 0.72 + 0.28 * trail_prog

            painter.save()
            center = rect.center()
            painter.translate(center)
            painter.translate(0, -bounce + step * 2.5)
            painter.scale(scale, scale)
            painter.translate(-center)
            painter.setOpacity(opacity)

            if value == 1:
                self._draw_x(painter, rect)
            else:
                self._draw_o(painter, rect)

            painter.restore()


class PiskvorkyWidget(QWidget):
    """Main game widget with all controls and game logic."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PiskvorkyRoot")

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

        # Controls row - toggle buttons instead of comboboxes
        row = QHBoxLayout()
        row.setSpacing(8)

        # Size buttons
        lbl_size = QLabel("⬜ Pole:")
        lbl_size.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 12px;")
        row.addWidget(lbl_size)
        
        self._size_buttons = {}
        size_group = QHBoxLayout()
        size_group.setSpacing(4)
        for size_key, size_label in [("3", "3×3"), ("8", "8×8"), ("13", "13×13")]:
            btn = QPushButton(size_label)
            btn.setObjectName(f"SizeBtn_{size_key}")
            btn.setCheckable(True)
            btn.setMinimumWidth(60)
            btn.setStyleSheet(self._get_toggle_btn_style())
            btn.clicked.connect(lambda checked, s=size_key: self._on_size_selected(s))
            self._size_buttons[size_key] = btn
            size_group.addWidget(btn)
        row.addLayout(size_group)
        
        row.addSpacing(16)
        
        # Difficulty buttons
        lbl_diff = QLabel("🤖 Bot:")
        lbl_diff.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 12px;")
        row.addWidget(lbl_diff)
        
        self._diff_buttons = {}
        diff_group = QHBoxLayout()
        diff_group.setSpacing(4)
        for diff_key, diff_label, emoji in [("easy", "Lehká", "😊"), ("medium", "Střední", "🤔"), ("hard", "Těžká", "🔥")]:
            btn = QPushButton(f"{emoji} {diff_label}")
            btn.setObjectName(f"DiffBtn_{diff_key}")
            btn.setCheckable(True)
            btn.setMinimumWidth(90)
            btn.setStyleSheet(self._get_toggle_btn_style())
            btn.clicked.connect(lambda checked, d=diff_key: self._on_diff_selected(d))
            self._diff_buttons[diff_key] = btn
            diff_group.addWidget(btn)
        row.addLayout(diff_group)
        
        row.addStretch(1)

        self.btn_new = QPushButton("🎲  Nová hra")
        self.btn_new.setObjectName("PrimaryBtn")
        self.btn_new.setStyleSheet("""
            QPushButton#PrimaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(110,231,255,0.85), stop:1 rgba(167,139,250,0.85));
                color: #111318;
                font-weight: 600;
                padding: 7px 18px;
                border-radius: 8px;
                border: none;
            }
            QPushButton#PrimaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(130,245,255,0.95), stop:1 rgba(190,165,255,0.95));
            }
        """)
        self.btn_new.clicked.connect(self.new_game)
        row.addWidget(self.btn_new)

        # Info labels
        info = QHBoxLayout()
        info.setSpacing(12)
        self.lbl_roles = QLabel("")
        self.lbl_score = QLabel("")
        self.lbl_chance = QLabel("")
        for lbl in (self.lbl_roles, self.lbl_score, self.lbl_chance):
            lbl.setStyleSheet("color: rgba(255,255,255,0.72); font-size: 12px;")
        info.addWidget(self.lbl_roles)
        info.addWidget(self.lbl_score)
        info.addWidget(self.lbl_chance)
        info.addStretch(1)

        # Status label - shows turn info
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-size: 15px; font-weight: 500; color: rgba(255,255,255,0.92); margin: 4px 0;")

        # Board
        self.board = BoardWidget()
        self.board.on_human_move = self._on_human_move

        lay.addLayout(row)
        lay.addLayout(info)
        lay.addWidget(self.lbl_status)
        lay.addWidget(self.board, 1)

        outer.addWidget(frame, 1)

        # Stats storage
        self.stats_path = appdata_file("piskvorky_stats.json")
        self.stats = load_stats(self.stats_path)

        # Runtime state
        self.n = 3
        self.difficulty = "easy"
        self.human = 1
        self.bot = -1
        self.game_over = False
        self._ai_thinking = False

        # AI background task
        self._ai_task: Optional[WorkerHandle] = None
        self._ai_task_id = 0

        # Swap2 state (for 13×13)
        self.swap_enabled = False
        self.swap_phase = "none"  # none, p1_place3, p2_choice, p2_add, p1_choose_color, playing
        self.swap_proposer_is_human = True
        self.swap_counts: Dict[int, int] = {1: 0, -1: 0}

        # Initialize button states
        self._update_size_buttons("3")
        self._update_diff_buttons("easy")

        # Start first game after UI is ready
        QTimer.singleShot(0, self.new_game)

    def _get_toggle_btn_style(self) -> str:
        """Return stylesheet for toggle buttons."""
        return """
            QPushButton {
                background: rgba(40, 48, 70, 0.7);
                border: 1px solid rgba(110, 231, 255, 0.2);
                border-radius: 6px;
                color: rgba(255, 255, 255, 0.7);
                font-size: 12px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background: rgba(60, 70, 95, 0.8);
                border: 1px solid rgba(110, 231, 255, 0.4);
                color: rgba(255, 255, 255, 0.9);
            }
            QPushButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(110,231,255,0.3), stop:1 rgba(167,139,250,0.3));
                border: 2px solid rgba(110, 231, 255, 0.7);
                color: rgba(255, 255, 255, 1.0);
                font-weight: 600;
            }
        """

    def _on_size_selected(self, size_key: str) -> None:
        """Handle size button click."""
        self._update_size_buttons(size_key)
        self.n = int(size_key)
        self.new_game()

    def _on_diff_selected(self, diff_key: str) -> None:
        """Handle difficulty button click."""
        self._update_diff_buttons(diff_key)
        self.difficulty = diff_key
        self.new_game()

    def _update_size_buttons(self, active: str) -> None:
        """Update size button checked states."""
        for key, btn in self._size_buttons.items():
            btn.setChecked(key == active)

    def _update_diff_buttons(self, active: str) -> None:
        """Update difficulty button checked states."""
        for key, btn in self._diff_buttons.items():
            btn.setChecked(key == active)

    def closeEvent(self, event) -> None:
        """Properly cleanup AI thread before closing."""
        self._stop_ai_thread()
        super().closeEvent(event)

    # Lifecycle hooks (called by hub on mount/unmount)
    def on_activate(self) -> None:
        self.board.setFocus()

    def on_deactivate(self) -> None:
        self._stop_ai_thread()

    def dispose(self) -> None:
        self._stop_ai_thread()

    def config_key(self) -> str:
        return get_config_key(self.n, self.difficulty)

    def _refresh_score_labels(self) -> float:
        key = self.config_key()
        r_player = get_rating(self.stats, key, 1000.0)
        rec = get_record(self.stats, key)
        r_bot = BOT_RATING[self.difficulty]
        pwin = expected_score(r_player, r_bot)
        points = rec.w * 3 + rec.d * 1
        self.lbl_score.setText(f"🏆 {r_player:.0f} Elo · {rec.w}V / {rec.d}R / {rec.l}P · {points} bodů")
        self.lbl_chance.setText(f"⚖️ Šance: {pwin*100:.0f}%")
        return pwin

    def new_game(self) -> None:
        """Start a new game."""
        # Stop any pending AI
        self._stop_ai_thread()
        
        # n and difficulty are already set by button clicks
        # Just sync the button states
        self._update_size_buttons(str(self.n))
        self._update_diff_buttons(self.difficulty)
        
        # Swap2 only for 13×13
        self.swap_enabled = (self.n == 13)
        self.swap_phase = "none"
        self.board.on_free_place = None
        self._ai_thinking = False

        if self.swap_enabled:
            self._start_swap2_game()
            return

        # Random who starts (X always moves first)
        bot_starts = random.choice([True, False])

        if bot_starts:
            self.bot = 1
            self.human = -1
            starter = "Bot"
        else:
            self.human = 1
            self.bot = -1
            starter = "Hráč"
        
        self.board.reset(self.n, to_move=1, human=self.human, bot=self.bot)
        self.game_over = False

        self._show_start_info(starter)

        # If bot starts, make its move
        if self.board.state.to_move == self.bot:
            QTimer.singleShot(300, self._bot_move_async)

    def _show_start_info(self, starter: str) -> None:
        """Show game start information via overlay."""
        human_mark = "X" if self.human == 1 else "O"
        bot_mark = "X" if self.bot == 1 else "O"
        
        self.lbl_roles.setText(f"🎮 Ty: {human_mark} · Bot: {bot_mark}")
        self._refresh_score_labels()
        self._update_turn_status()
        
        # Show overlay notification
        self.board.show_overlay(
            "🎯 Nová hra",
            f"{starter} začíná jako X\nTy hraješ {human_mark}, bot {bot_mark}",
            2000
        )

    def _update_turn_status(self) -> None:
        """Update status label to show whose turn it is."""
        if self.game_over:
            return
        if self.swap_phase not in ("none", "playing"):
            return
            
        turn_mark = "X" if self.board.state.to_move == 1 else "O"
        is_human = self.board.state.to_move == self.human
        who = "Ty" if is_human else "Bot"
        icon = "🟢" if is_human else "🔴"
        thinking = " (přemýšlí...)" if self._ai_thinking else ""
        self.lbl_status.setText(f"{icon} Na tahu: {turn_mark} ({who}){thinking}")

    def _set_status(self, txt: str) -> None:
        self.lbl_status.setText(txt)

    def _on_human_move(self, idx: int) -> None:
        """Handle human player's move."""
        if self.game_over or self._ai_thinking:
            return
        if self.board.state.to_move != self.human:
            return

        self.board.state.apply(idx)
        self.board.animate_mark(idx)
        self._post_move()

    def _bot_move_async(self) -> None:
        """Start AI computation in background thread."""
        if self.game_over:
            return
        if self.board.state.to_move != self.bot:
            return
        if self._ai_thinking:
            return

        # Pre-compile Numba functions (first call only)
        warmup()

        self._ai_thinking = True
        self._update_turn_status()
        self.board.disable()
        self._ai_task_id += 1
        task_id = self._ai_task_id
        state_snapshot = self.board.state.clone()
        bot = self.bot
        difficulty = self.difficulty

        def _compute_ai() -> SearchResult:
            try:
                if difficulty == "easy":
                    mv = best_move_easy(state_snapshot)
                    score = evaluate(state_snapshot, bot)
                    return SearchResult(move=mv, score=score, depth=1)
                if difficulty == "medium":
                    mv = best_move_medium(state_snapshot, bot)
                    score = evaluate(state_snapshot, bot)
                    return SearchResult(move=mv, score=score, depth=2)
                return best_move_hard(state_snapshot, bot)
            except Exception as exc:
                print(f"AI Error: {exc}")
                moves = state_snapshot.legal_moves()
                if moves:
                    return SearchResult(move=moves[0], score=0, depth=0)
                raise

        def _done(result: SearchResult) -> None:
            if task_id != self._ai_task_id:
                return
            self._ai_task = None
            self._on_ai_finished(result)

        def _error(exc: Exception) -> None:
            if task_id != self._ai_task_id:
                return
            self._ai_task = None
            self._ai_thinking = False
            self.board.enable()
            self._update_turn_status()
            print(f"AI Worker failed: {exc}")

        self._ai_task = run_in_worker(
            fn=_compute_ai,
            on_done=_done,
            on_error=_error,
            parent=self,
        )

    def _on_ai_finished(self, result: SearchResult) -> None:
        """Handle AI computation result."""
        self._ai_thinking = False
        self._ai_task = None
        
        if self.game_over:
            return
        if self.board.state.to_move != self.bot:
            return

        self.board.state.apply(result.move)
        self.board.animate_mark(result.move)
        self._post_move(last_bot_eval=result.score)

    def _stop_ai_thread(self) -> None:
        """Stop AI background task if running."""
        self._ai_thinking = False
        self._ai_task_id += 1

        if self._ai_task is not None:
            self._ai_task.cancel()
            self._ai_task = None

        self.board.enable()
        self._update_turn_status()

    def _post_move(self, last_bot_eval: Optional[int] = None) -> None:
        """Handle post-move logic: check winner, switch turns."""
        winner, coords, draw = check_winner(self.board.state)
        
        if winner is not None:
            self.game_over = True
            self.board.disable()
            self.board.winning_coords = coords
            self.board.animate_win()

            if winner == self.human:
                self._set_status("✅ Vyhrál jsi!")
                delta = self._calc_rating_delta("W")
                sign = "+" if delta >= 0 else ""
                self.board.show_overlay_with_button("🏆 Vítězství!", f"Skvělá práce!\nRating: {sign}{delta:.0f}", self.new_game)
                self.board.celebrate_win()  # Konfety jen při výhře!
                self._finish_game("W")
            else:
                self._set_status("❌ Bot vyhrál.")
                delta = self._calc_rating_delta("L")
                sign = "+" if delta >= 0 else ""
                self.board.show_overlay_with_button("💥 Prohra", f"Zkus jinou strategii\nRating: {sign}{delta:.0f}", self.new_game)
                # NO confetti on loss!
                self._finish_game("L")
            return

        if draw:
            self.game_over = True
            self.board.disable()
            self._set_status("🤝 Remíza.")
            delta = self._calc_rating_delta("D")
            sign = "+" if delta >= 0 else ""
            self.board.show_overlay_with_button("⚖️ Remíza", f"Vyrovnaná partie!\nRating: {sign}{delta:.0f}", self.new_game)
            # NO confetti on draw
            self._finish_game("D")
            return

        # Continue game
        self._update_turn_status()
        self._update_position_chance(last_bot_eval)
        
        # Enable input for human turn
        if self.board.state.to_move == self.human:
            self.board.enable()
        else:
            self.board.disable()
            QTimer.singleShot(150, self._bot_move_async)

    def _update_position_chance(self, last_bot_eval: Optional[int] = None) -> None:
        """Update position evaluation display."""
        if self.game_over:
            return
        if self.swap_enabled and self.swap_phase not in ("none", "playing"):
            return

        st = self.board.state
        
        if last_bot_eval is not None:
            p_bot = win_probability_from_score(last_bot_eval, self.n)
            p_h = 1.0 - p_bot
        else:
            score = evaluate(st, self.human)
            p_h = win_probability_from_score(score, self.n)
        
        base = self.lbl_chance.text().split(" · ")[0]
        self.lbl_chance.setText(f"{base} · Pozice: {p_h*100:.0f}%")

    def _calc_rating_delta(self, result: str) -> float:
        key = self.config_key()
        r_player = get_rating(self.stats, key, 1000.0)
        r_bot = BOT_RATING[self.difficulty]
        exp = expected_score(r_player, r_bot)
        actual = 1.0 if result == "W" else (0.5 if result == "D" else 0.0)
        return update_elo(r_player, exp, actual, k=32.0) - r_player

    def _finish_game(self, result: str) -> None:
        """Record game result and update stats."""
        key = self.config_key()
        r_player = get_rating(self.stats, key, 1000.0)
        r_bot = BOT_RATING[self.difficulty]
        exp = expected_score(r_player, r_bot)
        actual = 1.0 if result == "W" else (0.5 if result == "D" else 0.0)
        new_r = update_elo(r_player, exp, actual, k=32.0)
        delta = new_r - r_player

        rec = get_record(self.stats, key)
        rec.add(result)
        set_record(self.stats, key, rec)
        set_rating(self.stats, key, new_r)

        add_history(self.stats, {
            "ts": int(time.time()),
            "n": self.n,
            "difficulty": self.difficulty,
            "result": result,
            "delta": round(delta, 2),
            "new_rating": round(new_r, 2),
        })

        save_stats(self.stats_path, self.stats)

        points = rec.w * 3 + rec.d * 1
        self.lbl_score.setText(f"🏆 {new_r:.0f} Elo · {rec.w}V / {rec.d}R / {rec.l}P · {points} bodů")

    # ==================== SWAP2 IMPLEMENTATION ====================

    def _start_swap2_game(self) -> None:
        """Start a Swap2 opening for 13×13 Gomoku."""
        self.board.reset(self.n, to_move=1, human=1, bot=-1)
        self.game_over = False
        self.swap_phase = "p1_place3"
        self.swap_counts = {1: 2, -1: 1}  # P1 places 2×X, 1×O

        self._refresh_score_labels()

        # Randomly decide who is P1 (proposer)
        self.swap_proposer_is_human = random.choice([True, False])
        proposer = "Ty" if self.swap_proposer_is_human else "Bot"

        self.lbl_roles.setText(f"🔄 Swap2: P1={proposer}")
        self._set_status(f"🔄 Swap2: {proposer} umisťuje 3 kameny (2×X, 1×O)")

        if self.swap_proposer_is_human:
            self.board.enable()
            self.board.on_free_place = self._swap_place_stone
            self.board.show_overlay(
                "🔄 Swap2: Tvůj návrh",
                "Umísti 3 kameny: 2× X a 1× O\nKlikni na pole",
                3000
            )
        else:
            self.board.disable()
            self.board.show_overlay(
                "🔄 Swap2: Bot navrhuje",
                "Bot umisťuje 3 kameny...",
                1500
            )
            QTimer.singleShot(800, self._bot_swap_place_stones)

    def _place_mark_direct(self, idx: int, mark: int) -> bool:
        """Place a mark without switching turns."""
        if self.board.state.board[idx] != 0:
            return False
        self.board.state.board[idx] = mark
        # Update line sums manually
        if self.board.state._line_sums is not None:
            cell_lines = get_cell_lines(self.n, self.board.state.win_len)
            for line_idx in cell_lines[idx]:
                self.board.state._line_sums[line_idx] += mark
        return True

    def _swap_place_stone(self, idx: int) -> None:
        """Human places a stone during Swap2 phase."""
        if self.swap_phase == "p1_place3":
            # Placing initial 3 stones
            mark = 1 if self.swap_counts[1] > 0 else -1
            if not self._place_mark_direct(idx, mark):
                return
            self.swap_counts[mark] -= 1
            self.board.animate_mark(idx)

            remaining = self.swap_counts[1] + self.swap_counts[-1]
            if remaining == 0:
                self.swap_phase = "p2_choice"
                self.board.on_free_place = None
                QTimer.singleShot(400, self._swap_p2_choice)
            else:
                which = "X" if self.swap_counts[1] > 0 else "O"
                self._set_status(f"🔄 Umísti {which} (zbývá: X={self.swap_counts[1]}, O={self.swap_counts[-1]})")

        elif self.swap_phase == "p2_add":
            # P2 adding 2 stones
            mark = 1 if self.swap_counts[1] > 0 else -1
            if not self._place_mark_direct(idx, mark):
                return
            self.swap_counts[mark] -= 1
            self.board.animate_mark(idx)

            remaining = self.swap_counts[1] + self.swap_counts[-1]
            if remaining == 0:
                self.swap_phase = "p1_choose_color"
                self.board.on_free_place = None
                QTimer.singleShot(400, self._swap_p1_choose_color)
            else:
                which = "X" if self.swap_counts[1] > 0 else "O"
                self._set_status(f"🔄 Umísti {which}")

    def _bot_swap_place_stones(self) -> None:
        """Bot places stones during Swap2."""
        if self.swap_phase == "p1_place3":
            # Bot as P1 places 3 stones
            center = self.n // 2
            positions = []
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    r, c = center + dr, center + dc
                    if 0 <= r < self.n and 0 <= c < self.n:
                        positions.append(r * self.n + c)
            
            random.shuffle(positions)
            
            placed = {1: 0, -1: 0}
            for pos in positions:
                if self.board.state.board[pos] != 0:
                    continue
                if placed[1] < 2:
                    self._place_mark_direct(pos, 1)
                    self.board.animate_mark(pos)
                    placed[1] += 1
                elif placed[-1] < 1:
                    self._place_mark_direct(pos, -1)
                    self.board.animate_mark(pos)
                    placed[-1] += 1
                
                if placed[1] == 2 and placed[-1] == 1:
                    break
            
            self.swap_phase = "p2_choice"
            QTimer.singleShot(600, self._swap_p2_choice)

        elif self.swap_phase == "p2_add":
            # Bot as P2 adds 2 stones
            center = self.n // 2
            positions = []
            for dr in range(-3, 4):
                for dc in range(-3, 4):
                    r, c = center + dr, center + dc
                    if 0 <= r < self.n and 0 <= c < self.n:
                        if self.board.state.board[r * self.n + c] == 0:
                            positions.append(r * self.n + c)
            
            random.shuffle(positions)
            
            placed = {1: 0, -1: 0}
            for pos in positions[:2]:
                mark = 1 if placed[1] < 1 else -1
                self._place_mark_direct(pos, mark)
                self.board.animate_mark(pos)
                placed[mark] += 1
            
            self.swap_phase = "p1_choose_color"
            QTimer.singleShot(600, self._swap_p1_choose_color)

    def _swap_p2_choice(self) -> None:
        """P2 chooses: take X, take O, or add 2 stones."""
        p2_is_human = not self.swap_proposer_is_human
        
        if p2_is_human:
            # Show choice buttons
            self._show_swap_choice_dialog()
        else:
            # Bot decides
            self._set_status("🔄 Bot přemýšlí...")
            QTimer.singleShot(500, self._bot_swap_p2_decide)

    def _show_swap_choice_dialog(self) -> None:
        """Show Swap2 choice dialog for human P2."""
        self.board.show_overlay(
            "🔄 Vyber si",
            "Klikni na tlačítko níže",
            10000
        )
        self._set_status("🔄 Vyber: X, O, nebo přidej kameny")
        
        # Add choice buttons
        self._swap_choice_frame = QFrame(self)
        self._swap_choice_frame.setStyleSheet("""
            QFrame {
                background: rgba(14, 17, 26, 0.95);
                border: 1px solid rgba(110, 231, 255, 0.3);
                border-radius: 12px;
            }
        """)
        choice_lay = QHBoxLayout(self._swap_choice_frame)
        choice_lay.setSpacing(10)
        choice_lay.setContentsMargins(12, 10, 12, 10)
        
        btn_x = QPushButton("❌ Hraju X")
        btn_o = QPushButton("⭕ Hraju O")
        btn_add = QPushButton("➕ Přidám 2")
        
        for btn in (btn_x, btn_o, btn_add):
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(110,231,255,0.15);
                    color: white;
                    font-weight: 500;
                    padding: 8px 14px;
                    border-radius: 8px;
                    border: 1px solid rgba(110,231,255,0.25);
                }
                QPushButton:hover {
                    background: rgba(110,231,255,0.3);
                }
            """)
        
        btn_x.clicked.connect(lambda: self._swap_human_choice("x"))
        btn_o.clicked.connect(lambda: self._swap_human_choice("o"))
        btn_add.clicked.connect(lambda: self._swap_human_choice("add"))
        
        choice_lay.addWidget(btn_x)
        choice_lay.addWidget(btn_o)
        choice_lay.addWidget(btn_add)
        
        # Position the frame
        self._swap_choice_frame.adjustSize()
        self._swap_choice_frame.move(
            (self.width() - self._swap_choice_frame.width()) // 2,
            self.height() - self._swap_choice_frame.height() - 60
        )
        self._swap_choice_frame.show()

    def _swap_human_choice(self, choice: str) -> None:
        """Handle human P2's Swap2 choice."""
        if hasattr(self, '_swap_choice_frame'):
            self._swap_choice_frame.hide()
            self._swap_choice_frame.deleteLater()
        
        self.board._hide_overlay_immediate()
        
        if choice == "x":
            self._finalize_swap(human_mark=1)
        elif choice == "o":
            self._finalize_swap(human_mark=-1)
        else:
            # Add 2 stones
            self.swap_phase = "p2_add"
            self.swap_counts = {1: 1, -1: 1}
            self.board.enable()
            self.board.on_free_place = self._swap_place_stone
            self._set_status("🔄 Umísti 1×X a 1×O")
            self.board.show_overlay("🔄 Přidej kameny", "Umísti 1×X a 1×O", 2000)

    def _bot_swap_p2_decide(self) -> None:
        """Bot as P2 makes Swap2 decision."""
        # Simple heuristic: evaluate position
        score_x = evaluate(self.board.state, 1)
        score_o = evaluate(self.board.state, -1)
        
        if self.difficulty == "easy":
            choice = random.choice(["x", "o", "add"])
        elif self.difficulty == "medium":
            if abs(score_x - score_o) > 300:
                choice = "x" if score_x > score_o else "o"
            else:
                choice = random.choice(["x", "o", "add"])
        else:
            if abs(score_x - score_o) > 200:
                choice = "x" if score_x > score_o else "o"
            else:
                choice = "add"
        
        if choice == "x":
            self.board.show_overlay("🔄 Bot vybral X", "", 1500)
            QTimer.singleShot(800, lambda: self._finalize_swap(human_mark=-1))
        elif choice == "o":
            self.board.show_overlay("🔄 Bot vybral O", "", 1500)
            QTimer.singleShot(800, lambda: self._finalize_swap(human_mark=1))
        else:
            self.board.show_overlay("🔄 Bot přidává kameny", "", 1500)
            self.swap_phase = "p2_add"
            self.swap_counts = {1: 1, -1: 1}
            QTimer.singleShot(800, self._bot_swap_place_stones)

    def _swap_p1_choose_color(self) -> None:
        """P1 chooses color after P2 added stones."""
        p1_is_human = self.swap_proposer_is_human
        
        if p1_is_human:
            self._show_swap_color_dialog()
        else:
            # Bot chooses
            score_x = evaluate(self.board.state, 1)
            score_o = evaluate(self.board.state, -1)
            
            if self.difficulty == "hard":
                bot_mark = 1 if score_x >= score_o else -1
            else:
                bot_mark = random.choice([1, -1])
            
            human_mark = -bot_mark
            self.board.show_overlay(f"🔄 Bot vybral {'X' if bot_mark == 1 else 'O'}", "", 1500)
            QTimer.singleShot(800, lambda: self._finalize_swap(human_mark=human_mark))

    def _show_swap_color_dialog(self) -> None:
        """Show color choice for human P1."""
        self.board.show_overlay("🔄 Vyber barvu", "Soupeř přidal kameny", 10000)
        self._set_status("🔄 Vyber si barvu")
        
        self._swap_choice_frame = QFrame(self)
        self._swap_choice_frame.setStyleSheet("""
            QFrame {
                background: rgba(14, 17, 26, 0.95);
                border: 1px solid rgba(110, 231, 255, 0.3);
                border-radius: 12px;
            }
        """)
        choice_lay = QHBoxLayout(self._swap_choice_frame)
        choice_lay.setSpacing(10)
        choice_lay.setContentsMargins(12, 10, 12, 10)
        
        btn_x = QPushButton("❌ Hraju X")
        btn_o = QPushButton("⭕ Hraju O")
        
        for btn in (btn_x, btn_o):
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(110,231,255,0.15);
                    color: white;
                    font-weight: 500;
                    padding: 8px 14px;
                    border-radius: 8px;
                    border: 1px solid rgba(110,231,255,0.25);
                }
                QPushButton:hover {
                    background: rgba(110,231,255,0.3);
                }
            """)
        
        btn_x.clicked.connect(lambda: self._swap_color_chosen(1))
        btn_o.clicked.connect(lambda: self._swap_color_chosen(-1))
        
        choice_lay.addWidget(btn_x)
        choice_lay.addWidget(btn_o)
        
        self._swap_choice_frame.adjustSize()
        self._swap_choice_frame.move(
            (self.width() - self._swap_choice_frame.width()) // 2,
            self.height() - self._swap_choice_frame.height() - 60
        )
        self._swap_choice_frame.show()

    def _swap_color_chosen(self, human_mark: int) -> None:
        """Handle human P1's color choice."""
        if hasattr(self, '_swap_choice_frame'):
            self._swap_choice_frame.hide()
            self._swap_choice_frame.deleteLater()
        
        self.board._hide_overlay_immediate()
        self._finalize_swap(human_mark=human_mark)

    def _finalize_swap(self, human_mark: int) -> None:
        """Finalize Swap2 and start regular game."""
        self.swap_phase = "playing"
        self.human = human_mark
        self.bot = -human_mark
        self.board.human = self.human
        self.board.bot = self.bot
        
        # Determine who moves first
        # Count pieces to determine whose turn it should be
        x_count = sum(1 for v in self.board.state.board if v == 1)
        o_count = sum(1 for v in self.board.state.board if v == -1)
        
        # X moves first, so if X has more pieces, it's O's turn
        if x_count > o_count:
            self.board.state.to_move = -1  # O's turn
        else:
            self.board.state.to_move = 1   # X's turn
        
        human_mark_str = "X" if self.human == 1 else "O"
        bot_mark_str = "X" if self.bot == 1 else "O"
        
        self.lbl_roles.setText(f"🎮 Ty: {human_mark_str} · Bot: {bot_mark_str} [Swap2]")
        self._refresh_score_labels()
        self._update_turn_status()
        
        starter = "Ty" if self.board.state.to_move == self.human else "Bot"
        self.board.show_overlay(
            "🎯 Hra začíná",
            f"{starter} na tahu\nTy: {human_mark_str}, Bot: {bot_mark_str}",
            2000
        )
        
        # Enable/disable input based on whose turn
        if self.board.state.to_move == self.human:
            self.board.enable()
            self.board.on_free_place = None
        else:
            self.board.disable()
            self.board.on_free_place = None
            QTimer.singleShot(500, self._bot_move_async)

    def resizeEvent(self, event) -> None:
        """Handle resize to reposition swap choice frame."""
        super().resizeEvent(event)
        if hasattr(self, '_swap_choice_frame') and self._swap_choice_frame.isVisible():
            self._swap_choice_frame.move(
                (self.width() - self._swap_choice_frame.width()) // 2,
                self.height() - self._swap_choice_frame.height() - 60
            )
