"""
Simon Says UI - Modern dark theme memory game interface

Features:
- Dynamic circular board (4/6/8 segments by level)
- Smooth lighting animations when buttons activate
- Sound feedback with distinct tones
- Multiple game modes: Classic, Reverse, Speed, Chaos
- Score and combo tracking
- Confetti celebration on new high score
"""
from __future__ import annotations

import random
import time
import threading
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import (
    Qt, QTimer, QRectF, QVariantAnimation, QEasingCurve, QPointF
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QFont, QBrush, QLinearGradient, QRadialGradient,
    QPainterPath
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)

try:
    import winsound
except ImportError:  # pragma: no cover
    winsound = None

# Import engine from the same directory
_this_dir = Path(__file__).resolve().parent
_engine_spec = importlib.util.spec_from_file_location("simon_engine", _this_dir / "engine.py")
_engine_module = importlib.util.module_from_spec(_engine_spec)
import sys
sys.modules["simon_engine"] = _engine_module
_engine_spec.loader.exec_module(_engine_module)

SimonGame = _engine_module.SimonGame
Color = _engine_module.Color
GameMode = _engine_module.GameMode
GameState = _engine_module.GameState
COLOR_INFO = _engine_module.COLOR_INFO
create_game = _engine_module.create_game


# UI Colors
COLOR_BACKGROUND = QColor(30, 32, 40)
COLOR_CARD = QColor(40, 44, 55)
COLOR_TEXT = QColor(255, 255, 255)
COLOR_MUTED = QColor(180, 180, 180)
COLOR_PRIMARY = QColor(110, 231, 255)
COLOR_SECONDARY = QColor(167, 139, 250)
BASE_SATURATION = 0.20  # 20% when inactive


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


class SimonBoard(QWidget):
    """Interactive Simon Says game board."""
    BOARD_RADIUS_FACTOR = 0.46
    CENTER_RADIUS_FACTOR = 0.105
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(450, 450)
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.game: Optional[SimonGame] = None
        
        # Button state: which buttons are currently "lit"
        self._lit_buttons: Dict[Color, float] = {c: 0.0 for c in Color}
        self._lit_hold_until: Dict[Color, float] = {c: 0.0 for c in Color}
        
        # Sequence playback
        self._sequence_playing = False
        self._sequence_index = 0
        self._sequence_timer: Optional[QTimer] = None
        self._note_timer: Optional[QTimer] = None
        
        # Button rects for hit detection
        self._button_rects: Dict[Color, QRectF] = {}
        
        # Animation timer for smooth lighting
        self._anim_timer: Optional[QTimer] = None
        self._last_tick = time.time()
        
        # Confetti
        self._confetti: List[ConfettiParticle] = []
        self._confetti_timer: Optional[QTimer] = None
        
        # Overlay
        self._overlay_visible = False
        self._overlay_opacity = 0.0
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._overlay_button_callback = None
        self._overlay_button_rect: Optional[QRectF] = None
        self._overlay_anim: Optional[QVariantAnimation] = None

        # Sound
        self._sound_enabled = True
        
        # Callbacks
        self.on_score_change = None
        self.on_round_complete = None
        self.on_game_over = None
        
        # Start animation timer
        self._start_anim_timer()

    def set_sound_enabled(self, enabled: bool) -> None:
        """Enable/disable audio feedback."""
        self._sound_enabled = enabled

    def _active_colors(self) -> List[Color]:
        """Colors used by current level."""
        if self.game:
            return self.game.active_colors()
        return [Color.RED, Color.BLUE, Color.GREEN, Color.YELLOW]

    def _display_colors(self) -> List[Color]:
        """Colors in the order they are rendered on the circle."""
        if self.game and self.game.mode == GameMode.CHAOS and self.game.color_positions:
            return self.game.color_positions
        return self._active_colors()

    def _segment_color(self, color: Color, lit_factor: float) -> QColor:
        """
        Calculate segment color with dynamic saturation.

        Inactive: 20% saturation
        Lit:      100% saturation
        """
        base = QColor(COLOR_INFO[color]["hex"])
        h, s, v, a = base.getHsv()
        if h < 0:
            h = 0
        sat_factor = BASE_SATURATION + (1.0 - BASE_SATURATION) * max(0.0, min(1.0, lit_factor))
        new_s = max(0, min(255, int(s * sat_factor)))
        return QColor.fromHsv(h, new_s, v, a)

    def _play_tone(self, color: Color, duration: float = 0.25) -> None:
        """Play a unique tone for a color."""
        if not self._sound_enabled:
            return

        freq = int(COLOR_INFO[color].get("sound_freq", 440))
        dur_ms = max(80, int(duration * 1000))

        if winsound is None:
            return

        # winsound.Beep is blocking, so run it off-thread.
        threading.Thread(
            target=lambda: winsound.Beep(freq, dur_ms),
            daemon=True,
        ).start()
    
    def _start_anim_timer(self) -> None:
        """Start smooth animation timer."""
        if self._anim_timer:
            return
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_animation)
        self._anim_timer.start(16)  # ~60 FPS
    
    def _tick_animation(self) -> None:
        """Update animations."""
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now
        
        # Fade out lit buttons
        any_lit = False
        for color in Color:
            if now < self._lit_hold_until[color]:
                self._lit_buttons[color] = 1.0
                any_lit = True
                continue
            if self._lit_buttons[color] > 0:
                # Slower fade so full saturation stays visible longer.
                self._lit_buttons[color] = max(0, self._lit_buttons[color] - dt * 1.8)
                any_lit = True
        
        # Check timeout in speed mode
        if self.game and self.game.state == GameState.WAITING_INPUT:
            if self.game.check_timeout():
                self._on_game_over()
        
        if any_lit or (self.game and self.game.mode == GameMode.SPEED and 
                       self.game.state == GameState.WAITING_INPUT):
            self.update()
    
    def set_game(self, game: SimonGame) -> None:
        """Set a new game state."""
        self.game = game
        self._stop_sequence()
        self._lit_buttons = {c: 0.0 for c in Color}
        self._lit_hold_until = {c: 0.0 for c in Color}
        self._stop_confetti()
        self._hide_overlay()
        self.update()
    
    def start_game(self) -> None:
        """Start the game."""
        if not self.game:
            return
        self.game.start_game()
        self._play_sequence()
    
    def _play_sequence(self) -> None:
        """Play the current sequence with animations."""
        if not self.game:
            return
        
        self._sequence_playing = True
        self._sequence_index = 0
        
        # Start with small delay
        self._sequence_timer = QTimer(self)
        self._sequence_timer.setSingleShot(True)
        self._sequence_timer.timeout.connect(self._play_next_note)
        self._sequence_timer.start(500)
    
    def _play_next_note(self) -> None:
        """Play the next note in sequence."""
        if not self.game or self._sequence_index >= len(self.game.sequence):
            # Sequence complete
            self._sequence_playing = False
            self.game.start_input_phase()
            self.update()
            return
        
        # Light up current button
        color = self.game.sequence[self._sequence_index]
        self._light_button(color)
        
        self._sequence_index += 1
        
        # Schedule next note
        self._sequence_timer = QTimer(self)
        self._sequence_timer.setSingleShot(True)
        self._sequence_timer.timeout.connect(self._play_next_note)
        self._sequence_timer.start(self.game.speed_ms)
    
    def _stop_sequence(self) -> None:
        """Stop sequence playback."""
        self._sequence_playing = False
        if self._sequence_timer:
            self._sequence_timer.stop()
            self._sequence_timer = None
        if self._note_timer:
            self._note_timer.stop()
            self._note_timer = None
    
    def _light_button(self, color: Color, duration: float = 0.45) -> None:
        """Light up a button with animation."""
        self._lit_buttons[color] = 1.0
        self._lit_hold_until[color] = time.time() + max(0.0, duration)
        self._play_tone(color, duration)
        self.update()
    
    def _board_geometry(self) -> Tuple[float, float, float]:
        """Calculate board dimensions."""
        footer_space = 44
        available_height = max(120, self.height() - footer_space)
        size = min(self.width(), available_height)
        center_x = self.width() / 2
        center_y = available_height / 2
        return center_x, center_y, size
    
    def _get_button_path(self, color: Color, center_x: float, center_y: float, size: float) -> QPainterPath:
        """Get path for one circular segment."""
        colors = self._display_colors()
        count = len(colors)
        if count == 0 or color not in colors:
            return QPainterPath()

        idx = colors.index(color)
        radius = size * self.BOARD_RADIUS_FACTOR
        outer_rect = QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)

        span = 360.0 / count
        gap = 0.0

        # Start at top and go clockwise.
        start_angle = 90.0 - idx * span - gap / 2.0
        sweep = -(span - gap)

        path = QPainterPath()
        path.moveTo(center_x, center_y)
        path.arcTo(outer_rect, start_angle, sweep)
        path.closeSubpath()
        return path
    
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
        
        if not self.game or self._sequence_playing:
            return
        
        if self.game.state != GameState.WAITING_INPUT:
            return
        
        # Check which button was clicked
        center_x, center_y, size = self._board_geometry()
        dx = pos.x() - center_x
        dy = pos.y() - center_y
        if dx * dx + dy * dy < (size * self.CENTER_RADIUS_FACTOR) ** 2:
            return
        
        for color in self._display_colors():
            path = self._get_button_path(color, center_x, center_y, size)
            if path.contains(pos):
                self._on_button_click(color)
                return
    
    def _on_button_click(self, color: Color) -> None:
        """Handle button click."""
        if not self.game:
            return
        
        # Light up the button
        self._light_button(color)
        
        # Process input
        correct = self.game.input_color(color)
        
        if self.on_score_change:
            self.on_score_change(self.game.score)
        
        if not correct:
            self._on_game_over()
        elif self.game.state == GameState.SUCCESS:
            self._on_round_complete()
    
    def _on_round_complete(self) -> None:
        """Handle round completion."""
        if self.on_round_complete:
            self.on_round_complete(self.game.round)
        
        # Short delay then next round
        QTimer.singleShot(800, self._next_round)
    
    def _next_round(self) -> None:
        """Start next round."""
        if not self.game:
            return
        self.game.next_round()
        self._play_sequence()
    
    def _on_game_over(self) -> None:
        """Handle game over."""
        title = "Konec hry"
        
        subtitle = (
            f"Skóre: {self.game.score}  |  Správně: {self.game.correct_inputs_total}"
            f"  |  Dokončeno kol: {max(0, self.game.round - 1)}"
        )
        
        if self.on_game_over:
            self.on_game_over()
        
        self._show_overlay(title, subtitle, "Hrát znovu", self._request_restart)
    
    def _request_restart(self) -> None:
        """Request game restart."""
        if self.game:
            self.start_game()
    
    def _start_confetti(self) -> None:
        """Start confetti animation."""
        if self._confetti_timer:
            return
        
        w, h = self.width(), self.height()
        colors = [QColor(COLOR_INFO[c]["hex"]) for c in self._active_colors()]
        if not colors:
            colors = [QColor("#6EE7FF")]
        
        for _ in range(60):
            self._confetti.append(ConfettiParticle(
                x=random.uniform(0, w),
                y=random.uniform(-50, 0),
                vx=random.uniform(-2, 2),
                vy=random.uniform(2, 5),
                life=random.uniform(2, 4),
                size=random.uniform(4, 8),
                color=random.choice(colors)
            ))
        
        self._confetti_timer = QTimer(self)
        self._confetti_timer.timeout.connect(self._update_confetti)
        self._confetti_timer.start(16)
    
    def _stop_confetti(self) -> None:
        """Stop confetti animation."""
        if self._confetti_timer:
            self._confetti_timer.stop()
            self._confetti_timer = None
        self._confetti.clear()
    
    def _update_confetti(self) -> None:
        """Update confetti particles."""
        now = time.time()
        dt = 0.016  # Approximate
        h = self.height()
        
        alive = []
        for p in self._confetti:
            p.x += p.vx
            p.y += p.vy
            p.vy += 0.1
            p.age += dt
            
            if p.age < p.life and p.y < h + 50:
                alive.append(p)
        
        self._confetti = alive
        
        if not self._confetti:
            self._stop_confetti()
        
        self.update()
    
    def _show_overlay(self, title: str, subtitle: str, button_text: str, callback) -> None:
        """Show overlay with animation."""
        self._overlay_visible = True
        self._overlay_title = title
        self._overlay_subtitle = subtitle
        self._overlay_button_callback = callback
        
        self._overlay_anim = QVariantAnimation(self)
        self._overlay_anim.setDuration(300)
        self._overlay_anim.setStartValue(0.0)
        self._overlay_anim.setEndValue(1.0)
        self._overlay_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        def on_val(v):
            self._overlay_opacity = float(v)
            self.update()
        
        self._overlay_anim.valueChanged.connect(on_val)
        self._overlay_anim.start()
    
    def _hide_overlay(self) -> None:
        """Hide overlay."""
        if self._overlay_anim:
            self._overlay_anim.stop()
            self._overlay_anim = None
        self._overlay_visible = False
        self._overlay_opacity = 0.0
        self.update()
    
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if not self.game:
            self._draw_empty(painter)
            return
        
        self._draw_board(painter)
        
        if self._overlay_visible and self._overlay_opacity > 0.01:
            self._draw_overlay(painter)
        
        self._draw_confetti(painter)
    
    def _draw_empty(self, painter: QPainter) -> None:
        """Draw empty state."""
        painter.setPen(QPen(COLOR_MUTED))
        font = QFont("Segoe UI", 14)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, "Klikněte na 'Nová hra' pro start")
    
    def _draw_board(self, painter: QPainter) -> None:
        """Draw the Simon board with colored buttons."""
        center_x, center_y, size = self._board_geometry()

        # Draw a circular base to keep the board visually true-round.
        board_radius = size * self.BOARD_RADIUS_FACTOR
        board_rect = QRectF(center_x - board_radius, center_y - board_radius, board_radius * 2, board_radius * 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(22, 24, 33)))
        painter.drawEllipse(board_rect)
        painter.setPen(QPen(QColor(55, 60, 72), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(board_rect)

        # Draw segments
        for color in self._display_colors():
            path = self._get_button_path(color, center_x, center_y, size)
            lit_factor = self._lit_buttons.get(color, 0.0)
            seg_color = self._segment_color(color, lit_factor)

            gradient = QRadialGradient(center_x, center_y, board_radius)
            gradient.setColorAt(0.20, seg_color.lighter(118))
            gradient.setColorAt(1.00, seg_color)

            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.NoPen)
            painter.drawPath(path)

            if lit_factor > 0.4:
                glow_color = QColor(seg_color)
                glow_color.setAlphaF(0.28 * lit_factor)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(glow_color, 7))
                painter.drawPath(path)

        # Draw center info
        center_radius = size * self.CENTER_RADIUS_FACTOR
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(45, 48, 58)))
        painter.drawEllipse(QPointF(center_x, center_y), center_radius, center_radius)
        self._draw_center_info(painter, center_x, center_y, center_radius)
        
        # Draw progress/timer
        self._draw_status(painter, center_x, center_y, size)
    
    def _draw_center_info(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        """Draw info in center circle."""
        if not self.game:
            return
        
        # Round number
        font = QFont("Segoe UI", 24, QFont.Bold)
        painter.setFont(font)
        painter.setPen(COLOR_TEXT)
        
        text = str(self.game.round) if self.game.round > 0 else "?"
        rect = QRectF(cx - radius, cy - radius * 0.5, radius * 2, radius)
        painter.drawText(rect, Qt.AlignCenter, text)
    
    def _draw_status(self, painter: QPainter, cx: float, cy: float, size: float) -> None:
        """Draw status info (progress, timer)."""
        if not self.game:
            return
        
        # Keep status clearly below the circular board.
        board_bottom = cy + size * self.BOARD_RADIUS_FACTOR
        status_y = min(board_bottom + 16, self.height() - 34)
        
        painter.setPen(COLOR_MUTED)
        font = QFont("Segoe UI", 11)
        painter.setFont(font)
        
        if self._sequence_playing:
            text = "Sleduj sekvenci..."
        elif self.game.state == GameState.WAITING_INPUT:
            done, total = self.game.get_progress()
            text = f"Tvůj tah: {done}/{total}"
            
            # Timer bar in speed mode
            if self.game.mode == GameMode.SPEED:
                remaining = self.game.get_time_remaining_ms()
                progress = remaining / self.game.time_limit_ms
                
                bar_w = size * 0.5
                bar_h = 6
                bar_x = cx - bar_w / 2
                bar_y = status_y + 20
                
                # Background
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(60, 60, 70))
                painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 3, 3)
                
                # Progress
                color = QColor("#43A047") if progress > 0.3 else QColor("#E53935")
                painter.setBrush(color)
                painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w * progress, bar_h), 3, 3)
        elif self.game.state == GameState.IDLE:
            text = "Stiskni 'Nová hra'"
        elif self.game.state == GameState.SUCCESS:
            text = "Správně..."
        else:
            text = ""
        
        if text:
            rect = QRectF(0, status_y, self.width(), 30)
            painter.drawText(rect, Qt.AlignCenter, text)
    
    def _draw_overlay(self, painter: QPainter) -> None:
        """Draw game over overlay."""
        center_x, center_y, size = self._board_geometry()
        
        painter.save()
        painter.setOpacity(self._overlay_opacity)
        
        # Background
        overlay_rect = QRectF(center_x - size * 0.4, center_y - size * 0.3,
                             size * 0.8, size * 0.6)
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
        title_rect = QRectF(overlay_rect.left(), overlay_rect.top() + 30,
                           overlay_rect.width(), 40)
        painter.drawText(title_rect, Qt.AlignCenter, self._overlay_title)
        
        # Subtitle
        font = QFont("Segoe UI", 13)
        painter.setFont(font)
        painter.setPen(QColor(180, 180, 180))
        sub_rect = QRectF(overlay_rect.left(), overlay_rect.top() + 75,
                         overlay_rect.width(), 30)
        painter.drawText(sub_rect, Qt.AlignCenter, self._overlay_subtitle)
        
        # Button
        btn_w, btn_h = 130, 40
        btn_x = center_x - btn_w / 2
        btn_y = overlay_rect.bottom() - 60
        self._overlay_button_rect = QRectF(btn_x, btn_y, btn_w, btn_h)
        
        grad = QLinearGradient(btn_x, btn_y, btn_x, btn_y + btn_h)
        grad.setColorAt(0, COLOR_PRIMARY)
        grad.setColorAt(1, COLOR_SECONDARY)
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(self._overlay_button_rect, 8, 8)
        
        painter.setPen(Qt.black)
        font = QFont("Segoe UI", 11, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self._overlay_button_rect, Qt.AlignCenter, "Hrát znovu")
        
        painter.restore()
    
    def _draw_confetti(self, painter: QPainter) -> None:
        """Draw confetti particles."""
        for p in self._confetti:
            alpha = 1.0 - (p.age / p.life)
            color = QColor(p.color)
            color.setAlphaF(alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPointF(p.x, p.y), p.size / 2, p.size / 2)


class SimonWidget(QWidget):
    """Main Simon Says game widget with controls."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_mode = "classic"
        self._current_level = "medium"
        self._setup_ui()
        self.new_game()
    
    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        
        # Header
        header = QHBoxLayout()
        header.setSpacing(12)
        
        # Title
        title = QLabel("Simon")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #6EE7FF;")
        header.addWidget(title)
        
        header.addStretch()
        
        # Score box
        score_box = QFrame()
        score_box.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
            }
        """)
        score_layout = QVBoxLayout(score_box)
        score_layout.setContentsMargins(20, 8, 20, 8)
        score_layout.setSpacing(2)
        
        score_label = QLabel("SKÓRE")
        score_label.setStyleSheet("color: #B4B4B4; font-size: 11px; font-weight: bold; border: none;")
        score_label.setAlignment(Qt.AlignCenter)
        score_layout.addWidget(score_label)
        
        self._score_value = QLabel("0")
        self._score_value.setStyleSheet("color: #6EE7FF; font-size: 24px; font-weight: bold; border: none;")
        self._score_value.setAlignment(Qt.AlignCenter)
        score_layout.addWidget(self._score_value)
        
        header.addWidget(score_box)
        
        # High score box
        high_box = QFrame()
        high_box.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
            }
        """)
        high_layout = QVBoxLayout(high_box)
        high_layout.setContentsMargins(20, 8, 20, 8)
        high_layout.setSpacing(2)
        
        high_label = QLabel("REKORD")
        high_label.setStyleSheet("color: #B4B4B4; font-size: 11px; font-weight: bold; border: none;")
        high_label.setAlignment(Qt.AlignCenter)
        high_layout.addWidget(high_label)
        
        self._high_value = QLabel("0")
        self._high_value.setStyleSheet("color: #A78BFA; font-size: 24px; font-weight: bold; border: none;")
        self._high_value.setAlignment(Qt.AlignCenter)
        high_layout.addWidget(self._high_value)
        
        header.addWidget(high_box)
        
        layout.addLayout(header)

        # Settings row - style aligned with other games (toggle buttons)
        settings_row = QHBoxLayout()
        settings_row.setSpacing(8)

        diff_label = QLabel("Obtížnost:")
        diff_label.setStyleSheet("color: #B4B4B4; font-size: 12px;")
        settings_row.addWidget(diff_label)

        self._diff_buttons = {}
        for key, label in [("easy", "Lehká"), ("medium", "Střední"), ("hard", "Těžká")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == self._current_level)
            btn.setFixedHeight(32)
            btn.setStyleSheet(self._option_button_style(key == self._current_level))
            btn.clicked.connect(lambda checked, level=key: self._set_level(level))
            self._diff_buttons[key] = btn
            settings_row.addWidget(btn)

        settings_row.addSpacing(10)

        self._btn_sound = QPushButton("Zvuk")
        self._btn_sound.setCheckable(True)
        self._btn_sound.setChecked(True)
        self._btn_sound.setFixedHeight(32)
        self._btn_sound.setStyleSheet(self._option_button_style(True))
        self._btn_sound.toggled.connect(self._on_sound_toggle)
        settings_row.addWidget(self._btn_sound)

        settings_row.addStretch()
        layout.addLayout(settings_row)
        
        # Game board
        self._board = SimonBoard(self)
        self._board.on_score_change = self._on_score_change
        self._board.on_round_complete = self._on_round_complete
        self._board.on_game_over = self._on_game_over
        self._board.set_sound_enabled(self._btn_sound.isChecked())
        layout.addWidget(self._board, 1)
        
        # Bottom controls
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)
        
        self._btn_new = QPushButton("Nová hra")
        self._btn_new.setFixedHeight(34)
        self._btn_new.clicked.connect(self.new_game)
        self._btn_new.setStyleSheet(self._accent_button_style())
        bottom_bar.addWidget(self._btn_new)
        
        bottom_bar.addStretch()
        
        # Round counter
        self._round_label = QLabel("Kolo: 0")
        self._round_label.setStyleSheet("color: #888; font-size: 12px;")
        bottom_bar.addWidget(self._round_label)
        
        layout.addLayout(bottom_bar)
    
    def _accent_button_style(self) -> str:
        return """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #6EE7FF, stop:1 #A78BFA);
                color: black;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
                padding: 6px 16px;
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

    def _option_button_style(self, active: bool = False) -> str:
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

    def _set_level(self, level: str) -> None:
        """Set difficulty and restart game."""
        if level not in ("easy", "medium", "hard"):
            return
        self._current_level = level
        for key, btn in self._diff_buttons.items():
            active = key == level
            btn.setChecked(active)
            btn.setStyleSheet(self._option_button_style(active))
        if self._board.game is not None:
            self.new_game()

    def _on_sound_toggle(self, checked: bool) -> None:
        """Enable/disable sound effects."""
        self._btn_sound.setStyleSheet(self._option_button_style(checked))
        self._board.set_sound_enabled(checked)

    def set_mode(self, mode: str) -> None:
        """
        Set internal game mode and restart immediately.

        Mode is intentionally not exposed in UI, but remains configurable by code.
        """
        allowed = {"classic", "reverse", "speed", "chaos"}
        mode_norm = mode.lower()
        if mode_norm not in allowed:
            return
        if self._current_mode != mode_norm:
            self._current_mode = mode_norm
            if self._board.game is not None:
                self.new_game()
    
    def new_game(self) -> None:
        """Start a new game."""
        game = create_game(self._current_mode, self._current_level)
        self._board.set_game(game)
        self._board.set_sound_enabled(self._btn_sound.isChecked())
        self._board.start_game()
        self._update_display()
        self._board.setFocus()
    
    def _on_score_change(self, score: int) -> None:
        """Called when score changes."""
        self._update_display()
    
    def _on_round_complete(self, round_num: int) -> None:
        """Called when a round is completed."""
        self._update_display()
    
    def _on_game_over(self) -> None:
        """Called on game over."""
        self._update_display()
    
    def _update_display(self) -> None:
        """Update score and round display."""
        if self._board.game:
            self._score_value.setText(str(self._board.game.score))
            self._high_value.setText(str(self._board.game.high_score))
            self._round_label.setText(f"Kolo: {self._board.game.round}")
