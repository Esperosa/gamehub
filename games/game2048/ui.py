"""
2048 UI - Modern dark theme game interface

Features:
- Classic 4×4 sliding puzzle with dark theme
- Smooth animated tile movements
- Colorful tiles with values
- Arrow key controls
- Score tracking
- Victory and game over overlays
"""
from __future__ import annotations

import math
import random
import time
import copy
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from PySide6.QtCore import (
    Qt, QTimer, QRectF, QVariantAnimation, QEasingCurve, QPointF
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QFont, QBrush, QLinearGradient
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)

# Import engine from the same directory
_this_dir = Path(__file__).resolve().parent
_engine_spec = importlib.util.spec_from_file_location("game2048_engine", _this_dir / "engine.py")
_engine_module = importlib.util.module_from_spec(_engine_spec)
import sys
sys.modules["game2048_engine"] = _engine_module
_engine_spec.loader.exec_module(_engine_module)

Game2048 = _engine_module.Game2048
Direction = _engine_module.Direction
create_game = _engine_module.create_game
get_tile_colors = _engine_module.get_tile_colors

# Import solver
_solver_spec = importlib.util.spec_from_file_location("game2048_solver", _this_dir / "solver.py")
_solver_module = importlib.util.module_from_spec(_solver_spec)
sys.modules["game2048_solver"] = _solver_module
_solver_spec.loader.exec_module(_solver_module)
Solver2048 = _solver_module.Solver2048


# Dark theme UI Colors
COLOR_BACKGROUND = QColor(30, 32, 40)
COLOR_BOARD_BG = QColor(50, 55, 70)
COLOR_EMPTY_CELL = QColor(65, 70, 85)
COLOR_TEXT = QColor(255, 255, 255)
COLOR_MUTED = QColor(180, 180, 180)
COLOR_PRIMARY = QColor(110, 231, 255)      # Cyan
COLOR_SECONDARY = QColor(167, 139, 250)    # Purple


@dataclass
class AnimatedTile:
    """A tile with animation state."""
    value: int
    # Current interpolated position (0-based grid coords, can be fractional)
    x: float
    y: float
    # Target position
    target_x: float
    target_y: float
    # Scale for spawn animation (0.0 to 1.0)
    scale: float = 1.0
    # Is this a newly spawned tile?
    is_spawning: bool = False


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


class Game2048Board(QWidget):
    """Interactive 2048 game board with smooth animations."""
    
    ANIM_DURATION_MS = 100  # Animation duration in milliseconds
    SPAWN_DURATION_MS = 80  # Spawn animation duration
    ANIM_FPS = 60
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(450, 450)  # Larger minimum size
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.game: Optional[Game2048] = None
        
        # Animation state
        self._animating = False
        self._animated_tiles: List[AnimatedTile] = []
        self._anim_timer: Optional[QTimer] = None
        self._anim_start_time: float = 0
        self._pending_spawn: Optional[Tuple[int, int, int]] = None  # (row, col, value)
        self._spawn_scale: float = 0.0
        
        # Confetti
        self._confetti: List[ConfettiParticle] = []
        self._confetti_timer: Optional[QTimer] = None
        self._last_confetti_tick = time.time()
        
        # Overlay
        self._overlay_visible = False
        self._overlay_opacity = 0.0
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._overlay_button_text = ""
        self._overlay_button_callback = None
        self._overlay_button_rect: Optional[QRectF] = None
        self._overlay_continue_callback = None
        self._overlay_continue_rect: Optional[QRectF] = None
        self._overlay_anim: Optional[QVariantAnimation] = None
        
        # Callbacks
        self.on_score_change = None
        self.on_win = None
        self.on_game_over = None
    
    def set_game(self, game: Game2048) -> None:
        """Set a new game state."""
        self.game = game
        self._stop_animation()
        self._animated_tiles.clear()
        self._pending_spawn = None
        self._spawn_scale = 0.0
        self._stop_confetti()
        self._hide_overlay()
        self.update()
    
    def _board_geometry(self) -> Tuple[float, float, float, float]:
        """Calculate board layout - maximizes board size."""
        size = min(self.width(), self.height())
        margin = 6  # Minimal margin
        board_size = size - 2 * margin
        left = (self.width() - board_size) / 2
        top = (self.height() - board_size) / 2
        grid_size = self.game.size if self.game else 4
        return left, top, board_size, board_size / grid_size
    
    def _compute_tile_movements(self, old_grid: List[List[int]], direction: Direction) -> List[AnimatedTile]:
        """
        Compute how tiles move from old_grid in the given direction.
        Returns list of AnimatedTile with start positions and target positions.
        """
        size = len(old_grid)
        tiles = []
        
        if direction == Direction.LEFT:
            for r in range(size):
                row_tiles = [(c, old_grid[r][c]) for c in range(size) if old_grid[r][c] != 0]
                target_col = 0
                i = 0
                while i < len(row_tiles):
                    from_c, val = row_tiles[i]
                    if i + 1 < len(row_tiles) and row_tiles[i + 1][1] == val:
                        # Merge: both tiles move to same position
                        from_c2, _ = row_tiles[i + 1]
                        tiles.append(AnimatedTile(value=val, x=from_c, y=r, target_x=target_col, target_y=r))
                        tiles.append(AnimatedTile(value=val, x=from_c2, y=r, target_x=target_col, target_y=r))
                        target_col += 1
                        i += 2
                    else:
                        tiles.append(AnimatedTile(value=val, x=from_c, y=r, target_x=target_col, target_y=r))
                        target_col += 1
                        i += 1
        
        elif direction == Direction.RIGHT:
            for r in range(size):
                row_tiles = [(c, old_grid[r][c]) for c in range(size - 1, -1, -1) if old_grid[r][c] != 0]
                target_col = size - 1
                i = 0
                while i < len(row_tiles):
                    from_c, val = row_tiles[i]
                    if i + 1 < len(row_tiles) and row_tiles[i + 1][1] == val:
                        from_c2, _ = row_tiles[i + 1]
                        tiles.append(AnimatedTile(value=val, x=from_c, y=r, target_x=target_col, target_y=r))
                        tiles.append(AnimatedTile(value=val, x=from_c2, y=r, target_x=target_col, target_y=r))
                        target_col -= 1
                        i += 2
                    else:
                        tiles.append(AnimatedTile(value=val, x=from_c, y=r, target_x=target_col, target_y=r))
                        target_col -= 1
                        i += 1
        
        elif direction == Direction.UP:
            for c in range(size):
                col_tiles = [(r, old_grid[r][c]) for r in range(size) if old_grid[r][c] != 0]
                target_row = 0
                i = 0
                while i < len(col_tiles):
                    from_r, val = col_tiles[i]
                    if i + 1 < len(col_tiles) and col_tiles[i + 1][1] == val:
                        from_r2, _ = col_tiles[i + 1]
                        tiles.append(AnimatedTile(value=val, x=c, y=from_r, target_x=c, target_y=target_row))
                        tiles.append(AnimatedTile(value=val, x=c, y=from_r2, target_x=c, target_y=target_row))
                        target_row += 1
                        i += 2
                    else:
                        tiles.append(AnimatedTile(value=val, x=c, y=from_r, target_x=c, target_y=target_row))
                        target_row += 1
                        i += 1
        
        elif direction == Direction.DOWN:
            for c in range(size):
                col_tiles = [(r, old_grid[r][c]) for r in range(size - 1, -1, -1) if old_grid[r][c] != 0]
                target_row = size - 1
                i = 0
                while i < len(col_tiles):
                    from_r, val = col_tiles[i]
                    if i + 1 < len(col_tiles) and col_tiles[i + 1][1] == val:
                        from_r2, _ = col_tiles[i + 1]
                        tiles.append(AnimatedTile(value=val, x=c, y=from_r, target_x=c, target_y=target_row))
                        tiles.append(AnimatedTile(value=val, x=c, y=from_r2, target_x=c, target_y=target_row))
                        target_row -= 1
                        i += 2
                    else:
                        tiles.append(AnimatedTile(value=val, x=c, y=from_r, target_x=c, target_y=target_row))
                        target_row -= 1
                        i += 1
        
        return tiles
    
    def keyPressEvent(self, event) -> None:
        if not self.game:
            return
        
        if self._overlay_visible or self._animating:
            return
        
        key = event.key()
        direction = None
        
        if key == Qt.Key_Up or key == Qt.Key_W:
            direction = Direction.UP
        elif key == Qt.Key_Down or key == Qt.Key_S:
            direction = Direction.DOWN
        elif key == Qt.Key_Left or key == Qt.Key_A:
            direction = Direction.LEFT
        elif key == Qt.Key_Right or key == Qt.Key_D:
            direction = Direction.RIGHT
        
        if direction:
            self._execute_move(direction)
    
    def _execute_move(self, direction: Direction) -> bool:
        """Execute a move with animation. Returns True if move was made."""
        if not self.game or self._overlay_visible or self._animating:
            return False
        
        # Save old grid
        old_grid = copy.deepcopy(self.game.grid)
        
        # Make the move
        moved = self.game.move(direction)
        
        if moved:
            # Compute tile animations
            self._animated_tiles = self._compute_tile_movements(old_grid, direction)
            
            # Find spawn position
            new_grid = self.game.grid
            size = self.game.size
            
            # Track where tiles end up after animation
            target_positions = set()
            for tile in self._animated_tiles:
                target_positions.add((int(tile.target_y), int(tile.target_x)))
            
            # Find the newly spawned tile
            self._pending_spawn = None
            for r in range(size):
                for c in range(size):
                    val = new_grid[r][c]
                    if val != 0 and (r, c) not in target_positions:
                        self._pending_spawn = (r, c, val)
                        break
                if self._pending_spawn:
                    break
            
            self._spawn_scale = 0.0
            
            # Start animation
            self._start_animation()
        
        return moved
    
    def _start_animation(self) -> None:
        """Start smooth tile animation."""
        self._animating = True
        self._anim_start_time = time.time()
        
        if self._anim_timer:
            self._anim_timer.stop()
        
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_animation)
        self._anim_timer.start(1000 // self.ANIM_FPS)
    
    def _stop_animation(self) -> None:
        """Stop animation."""
        if self._anim_timer:
            self._anim_timer.stop()
            self._anim_timer = None
        self._animating = False
    
    def _tick_animation(self) -> None:
        """Update animation frame."""
        elapsed_ms = (time.time() - self._anim_start_time) * 1000
        
        # Move animation progress (0 to 1)
        move_progress = min(1.0, elapsed_ms / self.ANIM_DURATION_MS)
        eased_move = self._ease_out_quad(move_progress)
        
        # Update tile positions with linear interpolation
        for tile in self._animated_tiles:
            start_x = tile.x if not hasattr(tile, '_start_x') else tile._start_x
            start_y = tile.y if not hasattr(tile, '_start_y') else tile._start_y
            
            # Store start position on first frame
            if not hasattr(tile, '_start_x'):
                tile._start_x = tile.x
                tile._start_y = tile.y
            
            # Interpolate position
            tile.x = tile._start_x + (tile.target_x - tile._start_x) * eased_move
            tile.y = tile._start_y + (tile.target_y - tile._start_y) * eased_move
        
        # Spawn animation starts slightly before move ends
        spawn_start_ms = self.ANIM_DURATION_MS * 0.6
        if elapsed_ms >= spawn_start_ms and self._pending_spawn:
            spawn_elapsed = elapsed_ms - spawn_start_ms
            spawn_progress = min(1.0, spawn_elapsed / self.SPAWN_DURATION_MS)
            self._spawn_scale = self._ease_out_quad(spawn_progress)
        
        self.update()
        
        # Check if animation complete
        total_duration = self.ANIM_DURATION_MS + self.SPAWN_DURATION_MS * 0.4
        if elapsed_ms >= total_duration:
            self._finish_animation()
    
    def _finish_animation(self) -> None:
        """Complete animation and clean up."""
        self._stop_animation()
        self._animated_tiles.clear()
        self._pending_spawn = None
        self._spawn_scale = 0.0
        
        # Notify callbacks
        if self.on_score_change:
            self.on_score_change(self.game.score)
        
        # Check for win
        if self.game.won and not self._overlay_visible:
            self._celebrate()
            self._show_win_overlay()
        
        # Check for game over
        elif self.game.game_over:
            self._show_game_over_overlay()
        
        self.update()
    
    def _ease_out_quad(self, t: float) -> float:
        """Quadratic ease out for smooth animation."""
        return 1 - (1 - t) * (1 - t)
    
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        
        pos = event.position()
        
        # Check overlay buttons
        if self._overlay_visible:
            if self._overlay_button_callback and self._overlay_button_rect:
                if self._overlay_button_rect.contains(pos):
                    callback = self._overlay_button_callback
                    self._hide_overlay()
                    callback()
                    return
            
            if self._overlay_continue_callback and self._overlay_continue_rect:
                if self._overlay_continue_rect.contains(pos):
                    callback = self._overlay_continue_callback
                    self._hide_overlay()
                    callback()
                    return
    
    def _show_win_overlay(self) -> None:
        """Show victory overlay."""
        self._show_overlay(
            "Výborně!",
            f"Dosáhli jste 2048!",
            "Nová hra",
            lambda: self._request_new_game(),
            continue_callback=lambda: self._continue_game() if self.game.can_continue() else None
        )
    
    def _show_game_over_overlay(self) -> None:
        """Show game over overlay."""
        self._show_overlay(
            "Konec hry",
            f"Skóre: {self.game.score}",
            "Nová hra",
            lambda: self._request_new_game()
        )
    
    def _continue_game(self) -> None:
        """Continue playing after winning."""
        self._hide_overlay()
        self.setFocus()
    
    def _request_new_game(self) -> None:
        """Request a new game from parent widget."""
        parent = self.parent()
        while parent:
            if hasattr(parent, 'new_game'):
                parent.new_game()
                return
            parent = parent.parent()
    
    def _celebrate(self) -> None:
        """Start victory celebration."""
        self._start_confetti()
    
    def _start_confetti(self) -> None:
        """Start confetti animation."""
        if self._confetti_timer:
            return
        
        w, h = self.width(), self.height()
        colors = [
            QColor("#EDC22E"),  # Gold (2048 color)
            QColor("#6EE7FF"),  # Cyan
            QColor("#A78BFA"),  # Purple
            QColor("#F59563"),  # Orange
            QColor("#34D399"),  # Green
        ]
        
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
            p.vy += 0.1
            p.age += dt
            
            if p.age < p.life and p.y < h + 50:
                alive.append(p)
        
        self._confetti = alive
        
        if not self._confetti:
            self._confetti_timer.stop()
            self._confetti_timer = None
        
        self.update()
    
    def _show_overlay(self, title: str, subtitle: str, button_text: str, callback, continue_callback=None) -> None:
        """Show overlay with animation."""
        # Stop any parent widget's solve timer
        parent = self.parent()
        while parent:
            if hasattr(parent, '_stop_solving'):
                parent._stop_solving()
                break
            parent = parent.parent()
        
        self._overlay_visible = True
        self._overlay_title = title
        self._overlay_subtitle = subtitle
        self._overlay_button_text = button_text
        self._overlay_button_callback = callback
        self._overlay_continue_callback = continue_callback
        
        # Store animation as instance variable to prevent garbage collection
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
        self._overlay_continue_callback = None
        self.update()
    
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if not self.game:
            self._draw_empty(painter)
            return
        
        # Draw board
        self._draw_board(painter)
        
        # Draw overlay (only if visible and opacity > 0)
        if self._overlay_visible and self._overlay_opacity > 0.01:
            self._draw_overlay(painter)
        
        # Draw confetti on top
        self._draw_confetti(painter)
    
    def _draw_empty(self, painter: QPainter) -> None:
        """Draw empty state."""
        painter.setPen(QPen(COLOR_MUTED))
        font = QFont("Segoe UI", 14)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, "Klikněte na 'Nová hra' pro start")
    
    def _draw_board(self, painter: QPainter) -> None:
        """Draw the game board with tiles."""
        left, top, board_size, cell_size = self._board_geometry()
        
        # Board background
        board_rect = QRectF(left, top, board_size, board_size)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(COLOR_BOARD_BG))
        painter.drawRoundedRect(board_rect, 8, 8)
        
        gap = cell_size * 0.04
        tile_size = cell_size - 2 * gap
        
        # Draw empty cells
        for r in range(self.game.size):
            for c in range(self.game.size):
                x = left + c * cell_size + gap
                y = top + r * cell_size + gap
                rect = QRectF(x, y, tile_size, tile_size)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(COLOR_EMPTY_CELL))
                painter.drawRoundedRect(rect, 6, 6)
        
        if self._animating and self._animated_tiles:
            # Draw animating tiles at their interpolated positions
            for tile in self._animated_tiles:
                px = left + tile.x * cell_size + gap
                py = top + tile.y * cell_size + gap
                rect = QRectF(px, py, tile_size, tile_size)
                self._draw_tile(painter, rect, tile.value)
            
            # Draw spawn tile with scale animation
            if self._pending_spawn and self._spawn_scale > 0.01:
                r, c, val = self._pending_spawn
                scale = self._spawn_scale
                scaled_size = tile_size * scale
                offset = (tile_size - scaled_size) / 2
                px = left + c * cell_size + gap + offset
                py = top + r * cell_size + gap + offset
                rect = QRectF(px, py, scaled_size, scaled_size)
                self._draw_tile(painter, rect, val)
        else:
            # Static drawing - no animation
            for r in range(self.game.size):
                for c in range(self.game.size):
                    value = self.game.grid[r][c]
                    if value != 0:
                        x = left + c * cell_size + gap
                        y = top + r * cell_size + gap
                        rect = QRectF(x, y, tile_size, tile_size)
                        self._draw_tile(painter, rect, value)
    
    def _draw_tile(self, painter: QPainter, rect: QRectF, value: int) -> None:
        """Draw a single tile."""
        if value == 0:
            return
            
        bg_hex, text_hex = get_tile_colors(value)
        bg_color = QColor(bg_hex)
        text_color = QColor(text_hex)
        
        # Tile background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(rect, 6, 6)
        
        # Tile text
        painter.setPen(QPen(text_color))
        
        # Font size based on number of digits and tile size
        base_size = rect.height()
        if value < 100:
            font_size = base_size * 0.45
        elif value < 1000:
            font_size = base_size * 0.38
        else:
            font_size = base_size * 0.28
        
        font = QFont("Segoe UI", int(max(font_size, 8)), QFont.Bold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, str(value))
    
    def _draw_overlay(self, painter: QPainter) -> None:
        """Draw victory/game over overlay - matches other games' style."""
        left, top, board_size, _ = self._board_geometry()
        
        painter.save()
        painter.setOpacity(self._overlay_opacity)
        
        # Background over board area
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
        
        # Buttons
        btn_w, btn_h = 130, 40
        btn_y = top + board_size * 0.58
        
        if self._overlay_continue_callback:
            # Two buttons side by side
            total_w = btn_w * 2 + 15
            btn_x = left + (board_size - total_w) / 2
        else:
            btn_x = left + (board_size - btn_w) / 2
        
        self._overlay_button_rect = QRectF(btn_x, btn_y, btn_w, btn_h)
        
        # Button gradient
        grad = QLinearGradient(btn_x, btn_y, btn_x, btn_y + btn_h)
        grad.setColorAt(0, QColor(110, 231, 255))
        grad.setColorAt(1, QColor(167, 139, 250))
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(self._overlay_button_rect, 8, 8)
        
        # Button text
        painter.setPen(QPen(QColor(0, 0, 0)))
        font = QFont("Segoe UI", 11, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self._overlay_button_rect, Qt.AlignCenter, self._overlay_button_text)
        
        # Continue button (if available)
        if self._overlay_continue_callback:
            cont_x = btn_x + btn_w + 15
            self._overlay_continue_rect = QRectF(cont_x, btn_y, btn_w, btn_h)
            
            painter.setPen(QPen(COLOR_PRIMARY, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(self._overlay_continue_rect, 8, 8)
            
            painter.setPen(COLOR_PRIMARY)
            painter.drawText(self._overlay_continue_rect, Qt.AlignCenter, "Pokračovat")
        
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


class Game2048Widget(QWidget):
    """Main 2048 game widget with dark theme controls."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Auto-solve state
        self._solving = False
        self._solve_timer: Optional[QTimer] = None
        self._solver = Solver2048(depth=5, fast_mode=False)
        
        self._setup_ui()
        self.new_game()
    
    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        
        # Header with title and score
        header = QHBoxLayout()
        header.setSpacing(12)
        
        # Title
        title = QLabel("2048")
        title.setStyleSheet("font-size: 32px; font-weight: bold; color: #6EE7FF;")
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
        
        # Best tile box
        best_box = QFrame()
        best_box.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
            }
        """)
        best_layout = QVBoxLayout(best_box)
        best_layout.setContentsMargins(20, 8, 20, 8)
        best_layout.setSpacing(2)
        
        best_label = QLabel("NEJVYŠŠÍ")
        best_label.setStyleSheet("color: #B4B4B4; font-size: 11px; font-weight: bold; border: none;")
        best_label.setAlignment(Qt.AlignCenter)
        best_layout.addWidget(best_label)
        
        self._best_value = QLabel("0")
        self._best_value.setStyleSheet("color: #A78BFA; font-size: 24px; font-weight: bold; border: none;")
        self._best_value.setAlignment(Qt.AlignCenter)
        best_layout.addWidget(self._best_value)
        
        header.addWidget(best_box)
        
        layout.addLayout(header)
        
        # Game board - takes most space
        self._board = Game2048Board(self)
        self._board.on_score_change = self._on_score_change
        layout.addWidget(self._board, 1)
        
        # Bottom controls
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)
        
        self._btn_new = QPushButton("Nová hra")
        self._btn_new.setFixedHeight(34)
        self._btn_new.clicked.connect(self.new_game)
        self._btn_new.setStyleSheet(self._accent_button_style())
        bottom_bar.addWidget(self._btn_new)
        
        # Auto-solve button
        self._btn_solve = QPushButton("AI Vyřešit")
        self._btn_solve.setFixedHeight(34)
        self._btn_solve.clicked.connect(self._toggle_solve)
        self._btn_solve.setStyleSheet(self._solve_button_style())
        bottom_bar.addWidget(self._btn_solve)
        
        bottom_bar.addStretch()
        
        # Moves counter
        self._moves_label = QLabel("Tahy: 0")
        self._moves_label.setStyleSheet("color: #888; font-size: 12px;")
        bottom_bar.addWidget(self._moves_label)
        
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
    
    def _solve_button_style(self, active: bool = False) -> str:
        """Style for the auto-solve button."""
        if active:
            return """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #F65E3B, stop:1 #F59563);
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 12px;
                    padding: 6px 16px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #F87E5B, stop:1 #F7A583);
                }
            """
        return """
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: #6EE7FF;
                border: 1px solid rgba(110, 231, 255, 0.5);
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background: rgba(110, 231, 255, 0.15);
                border: 1px solid rgba(110, 231, 255, 0.8);
            }
            QPushButton:pressed {
                background: rgba(110, 231, 255, 0.25);
            }
        """
    
    def _toggle_solve(self) -> None:
        """Toggle auto-solve mode."""
        if self._solving:
            self._stop_solving()
        else:
            self._start_solving()
    
    def _start_solving(self) -> None:
        """Start auto-solving the game."""
        if self._solving or not self._board.game:
            return
        
        if self._board.game.game_over:
            return
        
        self._solving = True
        self._btn_solve.setText("⬛ Zastavit")
        self._btn_solve.setStyleSheet(self._solve_button_style(active=True))
        
        # Create timer for solving steps
        self._solve_timer = QTimer(self)
        self._solve_timer.timeout.connect(self._solve_step)
        # Fast interval - make move when animation finishes
        self._solve_timer.start(60)  # Check every 60ms
    
    def _stop_solving(self) -> None:
        """Stop auto-solving."""
        if self._solve_timer:
            self._solve_timer.stop()
            self._solve_timer = None
        
        self._solving = False
        self._btn_solve.setText("AI Vyřešit")
        self._btn_solve.setStyleSheet(self._solve_button_style(active=False))
    
    def _solve_step(self) -> None:
        """Make one solving step."""
        if not self._board.game or self._board.game.game_over or self._board._overlay_visible:
            self._stop_solving()
            return
        
        # Don't make move while animating
        if self._board._animating:
            return
        
        # Get best move from solver
        solver_move = self._solver.get_move(self._board.game.grid)
        if solver_move is None:
            self._stop_solving()
            return
        
        # Convert solver Direction to engine Direction (same values)
        move = Direction(solver_move.value)
        
        # Execute the move with animation
        self._board._execute_move(move)
        self._update_display()
    
    def new_game(self) -> None:
        """Start a new game."""
        # Stop solving if active
        if self._solving:
            self._stop_solving()
        
        game = create_game(4)
        self._board.set_game(game)
        self._update_display()
        self._board.setFocus()
    
    def _on_score_change(self, score: int) -> None:
        """Called when score changes."""
        self._update_display()
    
    def _update_display(self) -> None:
        """Update score and moves display."""
        if self._board.game:
            self._score_value.setText(str(self._board.game.score))
            self._best_value.setText(str(self._board.game.best_tile))
            self._moves_label.setText(f"Tahy: {self._board.game.moves}")
