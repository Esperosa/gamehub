"""
Simon Says / Memory Sequence Game Engine

Classic memory game where players repeat increasingly long sequences.
Supports multiple game modes and difficulty levels with wider color palettes.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class Color(Enum):
    """Available Simon colors."""

    RED = 0
    BLUE = 1
    GREEN = 2
    YELLOW = 3
    ORANGE = 4
    PURPLE = 5
    CYAN = 6
    MAGENTA = 7


class GameMode(Enum):
    """Game modes with different challenges."""

    CLASSIC = "classic"  # Standard - repeat sequence
    REVERSE = "reverse"  # Repeat sequence backwards
    SPEED = "speed"  # Time limit per input
    CHAOS = "chaos"  # Colors shuffle positions each round


class GameLevel(Enum):
    """Difficulty level controls active palette size."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class GameState(Enum):
    """Current state of the game."""

    IDLE = "idle"  # Waiting to start
    SHOWING = "showing"  # Playing the sequence
    WAITING_INPUT = "waiting"  # Waiting for player input
    SUCCESS = "success"  # Round completed
    GAME_OVER = "game_over"  # Failed


@dataclass
class SimonGame:
    """
    Simon Says game state.

    The selected level changes only how many colors are available.
    Core rules and scoring remain the same.
    """

    mode: GameMode = GameMode.CLASSIC
    level: GameLevel = GameLevel.EASY
    sequence: List[Color] = field(default_factory=list)
    player_input: List[Color] = field(default_factory=list)
    score: int = 0
    high_score: int = 0
    round: int = 0
    state: GameState = GameState.IDLE
    speed_ms: int = 600  # Initial speed between notes
    time_limit_ms: int = 3000  # 3 seconds per input in speed mode
    last_input_time: float = 0.0
    combo: int = 0  # Consecutive correct answers
    correct_inputs_total: int = 0

    # In chaos mode, this list controls what color is shown at each segment index.
    color_positions: List[Color] = field(default_factory=list)

    def active_colors(self) -> List[Color]:
        """Return active palette based on selected level."""
        if self.level == GameLevel.EASY:
            return [Color.RED, Color.BLUE, Color.GREEN, Color.YELLOW]
        if self.level == GameLevel.MEDIUM:
            return [
                Color.RED,
                Color.BLUE,
                Color.GREEN,
                Color.YELLOW,
                Color.ORANGE,
                Color.PURPLE,
            ]
        return [
            Color.RED,
            Color.BLUE,
            Color.GREEN,
            Color.YELLOW,
            Color.ORANGE,
            Color.PURPLE,
            Color.CYAN,
            Color.MAGENTA,
        ]

    def start_game(self) -> None:
        """Start or restart the game."""
        self.sequence = []
        self.player_input = []
        self.score = 0
        self.round = 0
        self.combo = 0
        self.speed_ms = 600
        self.time_limit_ms = 3000
        self.state = GameState.IDLE
        self.correct_inputs_total = 0
        self.color_positions = self.active_colors().copy()

        if self.mode == GameMode.CHAOS:
            self._shuffle_positions()

        self.next_round()

    def _shuffle_positions(self) -> None:
        """Shuffle color positions for chaos mode."""
        self.color_positions = self.active_colors().copy()
        random.shuffle(self.color_positions)

    def next_round(self) -> None:
        """Start the next round by adding a color to the sequence."""
        self.round += 1
        self.player_input = []

        # Add random color from active palette
        new_color = random.choice(self.active_colors())
        self.sequence.append(new_color)

        # Increase speed every few rounds
        if self.round > 1 and self.round % 4 == 0:
            self.speed_ms = max(200, self.speed_ms - 50)
            if self.mode == GameMode.SPEED:
                self.time_limit_ms = max(1000, self.time_limit_ms - 200)

        # Shuffle positions in chaos mode
        if self.mode == GameMode.CHAOS and self.round > 1:
            self._shuffle_positions()

        self.state = GameState.SHOWING

    def start_input_phase(self) -> None:
        """Called after sequence is shown, player can now input."""
        self.state = GameState.WAITING_INPUT
        self.last_input_time = time.time()

    def get_expected_sequence(self) -> List[Color]:
        """Get the sequence player should input (reversed in reverse mode)."""
        if self.mode == GameMode.REVERSE:
            return list(reversed(self.sequence))
        return self.sequence

    def input_color(self, color: Color) -> bool:
        """
        Player inputs a color.

        Returns True if correct, False if wrong (game over).
        """
        if self.state != GameState.WAITING_INPUT:
            return False

        # Check time limit in speed mode
        if self.mode == GameMode.SPEED:
            elapsed = (time.time() - self.last_input_time) * 1000
            if elapsed > self.time_limit_ms:
                self._game_over()
                return False

        expected = self.get_expected_sequence()
        current_pos = len(self.player_input)

        if current_pos >= len(expected):
            return False

        self.player_input.append(color)
        self.last_input_time = time.time()

        if color != expected[current_pos]:
            self._game_over()
            return False

        # Correct input
        self.combo += 1
        self.correct_inputs_total += 1

        # Calculate score: base points + combo bonus + speed bonus
        base_points = 10
        combo_bonus = min(self.combo, 10) * 2  # Up to 20 bonus
        speed_bonus = max(0, (600 - self.speed_ms) // 10)  # Faster = more points
        self.score += base_points + combo_bonus + speed_bonus

        # Check if sequence complete
        if len(self.player_input) == len(expected):
            self.state = GameState.SUCCESS
            # Bonus points for completing round
            round_bonus = self.round * 25
            self.score += round_bonus

        return True

    def _game_over(self) -> None:
        """Handle game over."""
        self.state = GameState.GAME_OVER
        self.combo = 0
        if self.score > self.high_score:
            self.high_score = self.score

    def check_timeout(self) -> bool:
        """Check if player has timed out in speed mode."""
        if self.state != GameState.WAITING_INPUT:
            return False
        if self.mode != GameMode.SPEED:
            return False

        elapsed = (time.time() - self.last_input_time) * 1000
        if elapsed > self.time_limit_ms:
            self._game_over()
            return True
        return False

    def get_time_remaining_ms(self) -> int:
        """Get remaining time in speed mode."""
        if self.mode != GameMode.SPEED or self.state != GameState.WAITING_INPUT:
            return self.time_limit_ms

        elapsed = (time.time() - self.last_input_time) * 1000
        return max(0, int(self.time_limit_ms - elapsed))

    def get_progress(self) -> tuple[int, int]:
        """Get progress in current round (inputs_made, total_needed)."""
        expected = self.get_expected_sequence()
        return len(self.player_input), len(expected)


def create_game(mode: str = "classic", level: str = "easy") -> SimonGame:
    """Create a new Simon game."""
    mode_map = {
        "classic": GameMode.CLASSIC,
        "reverse": GameMode.REVERSE,
        "speed": GameMode.SPEED,
        "chaos": GameMode.CHAOS,
    }
    level_map = {
        "easy": GameLevel.EASY,
        "medium": GameLevel.MEDIUM,
        "hard": GameLevel.HARD,
    }
    game_mode = mode_map.get(mode.lower(), GameMode.CLASSIC)
    game_level = level_map.get(level.lower(), GameLevel.EASY)
    return SimonGame(mode=game_mode, level=game_level)


# Color display info
COLOR_INFO = {
    Color.RED: {"name": "Červená", "hex": "#E53935", "sound_freq": 261.63},  # C4
    Color.BLUE: {"name": "Modrá", "hex": "#1E88E5", "sound_freq": 293.66},  # D4
    Color.GREEN: {"name": "Zelená", "hex": "#43A047", "sound_freq": 329.63},  # E4
    Color.YELLOW: {"name": "Žlutá", "hex": "#FDD835", "sound_freq": 349.23},  # F4
    Color.ORANGE: {"name": "Oranžová", "hex": "#FB8C00", "sound_freq": 392.00},  # G4
    Color.PURPLE: {"name": "Fialová", "hex": "#8E24AA", "sound_freq": 440.00},  # A4
    Color.CYAN: {"name": "Azurová", "hex": "#00ACC1", "sound_freq": 493.88},  # B4
    Color.MAGENTA: {"name": "Magenta", "hex": "#D81B60", "sound_freq": 523.25},  # C5
}

MODE_INFO = {
    GameMode.CLASSIC: {"name": "Klasický", "desc": "Opakuj sekvenci"},
    GameMode.REVERSE: {"name": "Zpětně", "desc": "Opakuj pozpátku"},
    GameMode.SPEED: {"name": "Rychlost", "desc": "Časový limit"},
    GameMode.CHAOS: {"name": "Chaos", "desc": "Barvy se mění"},
}

LEVEL_INFO = {
    GameLevel.EASY: {"name": "Easy", "desc": "4 barvy"},
    GameLevel.MEDIUM: {"name": "Medium", "desc": "6 barev"},
    GameLevel.HARD: {"name": "Hard", "desc": "8 barev"},
}
