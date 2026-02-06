"""
Othello (Reversi) UI.

Features:
- Classic 8x8 Othello rules
- Human (Black) vs AI (White)
- Difficulty levels with minimax alpha-beta depth
- Pass handling when a player has no legal move
- End-game overlay with score
"""
from __future__ import annotations

import importlib.util
import random
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import Qt, QTimer, QRectF, QVariantAnimation, QEasingCurve, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QBrush, QLinearGradient, QRadialGradient
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame

# Import engine from the same directory
_this_dir = Path(__file__).resolve().parent
_engine_spec = importlib.util.spec_from_file_location("othello_engine", _this_dir / "engine.py")
_engine_module = importlib.util.module_from_spec(_engine_spec)
import sys
sys.modules["othello_engine"] = _engine_module
_engine_spec.loader.exec_module(_engine_module)

OthelloGame = _engine_module.OthelloGame
OthelloAI = _engine_module.OthelloAI
create_game = _engine_module.create_game
BLACK = _engine_module.BLACK
WHITE = _engine_module.WHITE
EMPTY = _engine_module.EMPTY


COLOR_PRIMARY = QColor(110, 231, 255)
COLOR_SECONDARY = QColor(167, 139, 250)
COLOR_MUTED = QColor(180, 180, 180)
COLOR_TEXT = QColor(245, 245, 245)

COLOR_BOARD_LIGHT = QColor(40, 122, 72)
COLOR_BOARD_DARK = QColor(25, 92, 54)
COLOR_GRID = QColor(14, 62, 34)
COLOR_VALID_MOVE = QColor(255, 255, 255, 160)


class OthelloBoard(QWidget):
    """Board rendering and mouse interactions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 500)
        self.setFocusPolicy(Qt.StrongFocus)

        self.game: Optional[OthelloGame] = None
        self._valid_moves: Set[Tuple[int, int]] = set()
        self.on_cell_clicked: Optional[Callable[[int, int], None]] = None

        # Overlay
        self._overlay_visible = False
        self._overlay_opacity = 0.0
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._overlay_button_text = "Nová hra"
        self._overlay_button_rect: Optional[QRectF] = None
        self._overlay_button_callback = None
        self._overlay_anim: Optional[QVariantAnimation] = None

    def set_game(self, game: OthelloGame) -> None:
        self.game = game
        self._valid_moves.clear()
        self.hide_overlay()
        self.update()

    def set_valid_moves(self, moves: List[Tuple[int, int]]) -> None:
        self._valid_moves = set(moves)
        self.update()

    def _board_geometry(self) -> Tuple[float, float, float, float]:
        """Return (left, top, board_size, cell_size)."""
        size = min(self.width(), self.height())
        margin = 14
        board_size = size - 2 * margin
        left = (self.width() - board_size) / 2
        top = (self.height() - board_size) / 2
        cell = board_size / 8
        return left, top, board_size, cell

    def _cell_at(self, x: float, y: float) -> Optional[Tuple[int, int]]:
        if not self.game:
            return None
        left, top, board_size, cell = self._board_geometry()
        if not (left <= x <= left + board_size and top <= y <= top + board_size):
            return None
        col = int((x - left) / cell)
        row = int((y - top) / cell)
        if 0 <= row < 8 and 0 <= col < 8:
            return (row, col)
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return

        pos = event.position()

        if self._overlay_visible and self._overlay_button_rect and self._overlay_button_callback:
            if self._overlay_button_rect.contains(pos):
                callback = self._overlay_button_callback
                self.hide_overlay()
                callback()
                return

        if not self.game or self._overlay_visible:
            return

        cell = self._cell_at(pos.x(), pos.y())
        if not cell:
            return

        if cell in self._valid_moves and self.on_cell_clicked:
            self.on_cell_clicked(cell[0], cell[1])

    def show_overlay(self, title: str, subtitle: str, button_text: str, callback) -> None:
        self._overlay_visible = True
        self._overlay_title = title
        self._overlay_subtitle = subtitle
        self._overlay_button_text = button_text
        self._overlay_button_callback = callback

        self._overlay_anim = QVariantAnimation(self)
        self._overlay_anim.setDuration(280)
        self._overlay_anim.setStartValue(0.0)
        self._overlay_anim.setEndValue(1.0)
        self._overlay_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._overlay_anim.valueChanged.connect(self._on_overlay_anim)
        self._overlay_anim.start()

    def hide_overlay(self) -> None:
        if self._overlay_anim:
            self._overlay_anim.stop()
            self._overlay_anim = None
        self._overlay_visible = False
        self._overlay_opacity = 0.0
        self.update()

    def _on_overlay_anim(self, value) -> None:
        self._overlay_opacity = float(value)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.game:
            painter.setPen(QPen(COLOR_MUTED))
            painter.setFont(QFont("Segoe UI", 14))
            painter.drawText(self.rect(), Qt.AlignCenter, "Klikněte na 'Nová hra' pro start")
            return

        self._draw_board(painter)
        self._draw_disks(painter)
        self._draw_valid_moves(painter)

        if self._overlay_visible and self._overlay_opacity > 0.01:
            self._draw_overlay(painter)

    def _draw_board(self, painter: QPainter) -> None:
        left, top, board_size, cell = self._board_geometry()
        board_rect = QRectF(left, top, board_size, board_size)

        bg_grad = QLinearGradient(board_rect.topLeft(), board_rect.bottomRight())
        bg_grad.setColorAt(0, COLOR_BOARD_LIGHT)
        bg_grad.setColorAt(1, COLOR_BOARD_DARK)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg_grad))
        painter.drawRoundedRect(board_rect, 14, 14)

        # Border
        painter.setPen(QPen(QColor(12, 45, 26), 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(board_rect.adjusted(1, 1, -1, -1), 12, 12)

        # Grid
        painter.setPen(QPen(COLOR_GRID, 1.5))
        for i in range(1, 8):
            x = left + i * cell
            y = top + i * cell
            painter.drawLine(int(x), int(top), int(x), int(top + board_size))
            painter.drawLine(int(left), int(y), int(left + board_size), int(y))

    def _draw_disks(self, painter: QPainter) -> None:
        left, top, _, cell = self._board_geometry()
        for r in range(8):
            for c in range(8):
                val = self.game.board[r][c]
                if val == EMPTY:
                    continue
                rect = QRectF(left + c * cell, top + r * cell, cell, cell)
                disk_rect = rect.adjusted(cell * 0.12, cell * 0.12, -cell * 0.12, -cell * 0.12)
                self._draw_disk(painter, disk_rect, val)

    def _draw_disk(self, painter: QPainter, rect: QRectF, disk: int) -> None:
        if disk == BLACK:
            base = QColor(40, 44, 55)
            edge = QColor(8, 8, 8)
            shine = QColor(130, 140, 165)
        else:
            base = QColor(235, 240, 250)
            edge = QColor(170, 175, 185)
            shine = QColor(255, 255, 255)

        grad = QRadialGradient(
            rect.center().x() - rect.width() * 0.2,
            rect.center().y() - rect.height() * 0.2,
            rect.width() * 0.75,
        )
        grad.setColorAt(0.0, shine)
        grad.setColorAt(0.55, base)
        grad.setColorAt(1.0, edge)

        painter.setPen(QPen(edge.darker(130), 1.5))
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(rect)

    def _draw_valid_moves(self, painter: QPainter) -> None:
        if not self._valid_moves:
            return
        left, top, _, cell = self._board_geometry()
        radius = max(3.0, cell * 0.10)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(COLOR_VALID_MOVE))
        for r, c in self._valid_moves:
            cx = left + (c + 0.5) * cell
            cy = top + (r + 0.5) * cell
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

    def _draw_overlay(self, painter: QPainter) -> None:
        left, top, board_size, _ = self._board_geometry()
        painter.save()
        painter.setOpacity(self._overlay_opacity)

        overlay_rect = QRectF(left - 10, top - 10, board_size + 20, board_size + 20)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(14, 17, 26, 228))
        painter.drawRoundedRect(overlay_rect, 16, 16)

        painter.setPen(QPen(COLOR_PRIMARY.darker(150), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(overlay_rect.adjusted(2, 2, -2, -2), 14, 14)

        painter.setPen(Qt.white)
        painter.setFont(QFont("Segoe UI", 22, QFont.Bold))
        painter.drawText(QRectF(left, top + board_size * 0.30, board_size, 40), Qt.AlignCenter, self._overlay_title)

        painter.setPen(QColor(220, 220, 220))
        painter.setFont(QFont("Segoe UI", 13))
        painter.drawText(
            QRectF(left + 24, top + board_size * 0.42, board_size - 48, 50),
            Qt.AlignCenter | Qt.TextWordWrap,
            self._overlay_subtitle,
        )

        btn_w, btn_h = 150, 42
        btn_x = left + (board_size - btn_w) / 2
        btn_y = top + board_size * 0.62
        self._overlay_button_rect = QRectF(btn_x, btn_y, btn_w, btn_h)

        grad = QLinearGradient(btn_x, btn_y, btn_x, btn_y + btn_h)
        grad.setColorAt(0.0, COLOR_PRIMARY)
        grad.setColorAt(1.0, COLOR_SECONDARY)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(self._overlay_button_rect, 8, 8)

        painter.setPen(Qt.black)
        painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
        painter.drawText(self._overlay_button_rect, Qt.AlignCenter, self._overlay_button_text)
        painter.restore()


class OthelloWidget(QWidget):
    """Main Othello widget with controls."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._difficulty = "medium"
        self._human_player = BLACK
        self._ai_player = WHITE
        self._ai_pending = False

        self._game = create_game()
        self._ai = OthelloAI(skill=self._difficulty)

        self._setup_ui()
        self.new_game()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        header.setSpacing(12)

        title = QLabel("Othello")
        title.setStyleSheet("font-size: 30px; font-weight: bold; color: #6EE7FF;")
        header.addWidget(title)
        header.addStretch()

        self._black_value = QLabel("2")
        header.addWidget(self._score_box("ČERNÁ", self._black_value, "#F2F2F2"))

        self._white_value = QLabel("2")
        header.addWidget(self._score_box("BÍLÁ", self._white_value, "#A78BFA"))

        layout.addLayout(header)

        # Settings row
        settings = QHBoxLayout()
        settings.setSpacing(8)

        lbl_diff = QLabel("Obtížnost:")
        lbl_diff.setStyleSheet("color: #B4B4B4; font-size: 12px;")
        settings.addWidget(lbl_diff)

        self._diff_buttons: Dict[str, QPushButton] = {}
        for key, label in [("easy", "Lehká"), ("medium", "Střední"), ("hard", "Těžká")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == self._difficulty)
            btn.setFixedHeight(32)
            btn.setStyleSheet(self._option_button_style(key == self._difficulty))
            btn.clicked.connect(lambda checked, d=key: self._set_difficulty(d))
            self._diff_buttons[key] = btn
            settings.addWidget(btn)

        settings.addStretch()

        self._btn_new = QPushButton("Nová hra")
        self._btn_new.setFixedHeight(34)
        self._btn_new.clicked.connect(self.new_game)
        self._btn_new.setStyleSheet(self._accent_button_style())
        settings.addWidget(self._btn_new)

        layout.addLayout(settings)

        # Board
        self._board = OthelloBoard(self)
        self._board.on_cell_clicked = self._on_cell_clicked
        layout.addWidget(self._board, 1)

        # Bottom info
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self._turn_label = QLabel("Tah: Černá")
        self._turn_label.setStyleSheet("color: #DADADA; font-size: 12px;")
        bottom.addWidget(self._turn_label)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #A0A7B6; font-size: 12px;")
        bottom.addWidget(self._status_label)

        self._starter_label = QLabel("Začíná: -")
        self._starter_label.setStyleSheet("color: #8EA5B5; font-size: 12px;")
        bottom.addWidget(self._starter_label)
        bottom.addStretch()

        self._moves_label = QLabel("Tahů: 0")
        self._moves_label.setStyleSheet("color: #888; font-size: 12px;")
        bottom.addWidget(self._moves_label)
        layout.addLayout(bottom)

    def _score_box(self, title: str, value_label: QLabel, value_color: str) -> QFrame:
        box = QFrame()
        box.setStyleSheet(
            """
            QFrame {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
            }
            """
        )
        lay = QVBoxLayout(box)
        lay.setContentsMargins(20, 8, 20, 8)
        lay.setSpacing(2)

        lbl = QLabel(title)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #B4B4B4; font-size: 11px; font-weight: bold; border: none;")
        lay.addWidget(lbl)

        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet(f"color: {value_color}; font-size: 24px; font-weight: bold; border: none;")
        lay.addWidget(value_label)
        return box

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

    def _set_difficulty(self, diff: str) -> None:
        if diff not in ("easy", "medium", "hard"):
            return
        self._difficulty = diff
        for key, btn in self._diff_buttons.items():
            active = key == diff
            btn.setChecked(active)
            btn.setStyleSheet(self._option_button_style(active))
        self.new_game()

    def _coord_name(self, row: int, col: int) -> str:
        return f"{chr(ord('A') + col)}{row + 1}"

    def _player_display_name(self, player: int) -> str:
        if player == self._human_player:
            return "Ty (Černá)"
        return "AI (Bílá)"

    def new_game(self) -> None:
        self._ai_pending = False
        self._ai = OthelloAI(skill=self._difficulty)
        self._game = create_game()
        starter = random.choice([self._human_player, self._ai_player])
        self._game.current_player = starter
        self._starter_label.setText(f"Začíná: {self._player_display_name(starter)}")
        self._status_label.setText(f"Start: {self._player_display_name(starter)}")
        self._board.set_game(self._game)
        self._update_display()
        self._advance_turn()
        self._board.setFocus()

    def _update_display(self) -> None:
        black, white = self._game.score()
        self._black_value.setText(str(black))
        self._white_value.setText(str(white))
        self._moves_label.setText(f"Tahů: {self._game.move_count}")

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if self._game.game_over or self._ai_pending:
            return
        if self._game.current_player != self._human_player:
            return
        if not self._game.make_move(row, col):
            return

        self._status_label.setText(f"Zahráno: {self._coord_name(row, col)}")
        self._advance_turn()

    def _advance_turn(self) -> None:
        self._update_display()

        if self._game.game_over:
            self._board.set_valid_moves([])
            self._show_game_over()
            return

        current = self._game.current_player
        moves = self._game.valid_moves(current)

        if not moves:
            player_name = "Černá" if current == BLACK else "Bílá"
            self._board.set_valid_moves([])
            if self._game.pass_turn():
                self._update_display()
                if self._game.game_over:
                    self._show_game_over()
                    return
                self._status_label.setText(f"{player_name} nemá tah (pass).")
                QTimer.singleShot(700, self._advance_turn)
            return

        if current == self._human_player:
            self._turn_label.setText("Tah: Černá (Ty)")
            self._status_label.setText(f"Tvůj tah ({len(moves)} možností)")
            self._board.set_valid_moves(moves)
            return

        # AI turn
        self._turn_label.setText("Tah: Bílá (AI)")
        self._status_label.setText("AI přemýšlí...")
        self._board.set_valid_moves([])
        if not self._ai_pending:
            self._ai_pending = True
            QTimer.singleShot(220, self._do_ai_move)

    def _do_ai_move(self) -> None:
        self._ai_pending = False
        if self._game.game_over or self._game.current_player != self._ai_player:
            return

        move = self._ai.choose_move(self._game, self._ai_player)
        if move is None:
            self._advance_turn()
            return

        self._game.make_move(*move)
        self._status_label.setText(f"AI zahrála: {self._coord_name(*move)}")
        self._advance_turn()

    def _show_game_over(self) -> None:
        black, white = self._game.score()
        if self._game.winner == BLACK:
            title = "Vyhrál jsi!"
        elif self._game.winner == WHITE:
            title = "AI vyhrála"
        else:
            title = "Remíza"

        subtitle = f"Černá: {black}  |  Bílá: {white}"
        self._turn_label.setText("Konec hry")
        self._status_label.setText("Spusť novou hru pro další partii.")
        self._board.show_overlay(title, subtitle, "Nová hra", self.new_game)
