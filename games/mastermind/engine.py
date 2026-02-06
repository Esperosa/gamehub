"""
Mastermind Game Engine

Classic code-breaking game where one player tries to guess a secret code.
After each guess, feedback is given:
- Black pegs: correct color AND position
- White pegs: correct color, wrong position
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import IntEnum


class Color(IntEnum):
    """Available peg colors."""
    RED = 0
    GREEN = 1
    BLUE = 2
    YELLOW = 3
    ORANGE = 4
    PURPLE = 5
    CYAN = 6
    PINK = 7


# Color names for display
COLOR_NAMES = {
    Color.RED: "Červená",
    Color.GREEN: "Zelená",
    Color.BLUE: "Modrá",
    Color.YELLOW: "Žlutá",
    Color.ORANGE: "Oranžová",
    Color.PURPLE: "Fialová",
    Color.CYAN: "Tyrkysová",
    Color.PINK: "Růžová",
}

# Hex colors for UI
COLOR_HEX = {
    Color.RED: "#E53935",
    Color.GREEN: "#43A047",
    Color.BLUE: "#1E88E5",
    Color.YELLOW: "#FDD835",
    Color.ORANGE: "#FB8C00",
    Color.PURPLE: "#8E24AA",
    Color.CYAN: "#00ACC1",
    Color.PINK: "#EC407A",
}


@dataclass
class Feedback:
    """Feedback for a guess."""
    black: int  # Correct color AND position
    white: int  # Correct color, wrong position
    
    @property
    def total(self) -> int:
        return self.black + self.white
    
    def is_correct(self, code_length: int) -> bool:
        """Check if this feedback indicates a correct guess."""
        return self.black == code_length


@dataclass
class Guess:
    """A single guess with its feedback."""
    code: List[Color]
    feedback: Feedback


@dataclass
class MastermindGame:
    """Represents a Mastermind game state."""
    secret: List[Color]
    num_colors: int = 6
    max_attempts: int = 10
    guesses: List[Guess] = field(default_factory=list)
    
    @property
    def code_length(self) -> int:
        return len(self.secret)
    
    @property
    def attempts_left(self) -> int:
        return self.max_attempts - len(self.guesses)
    
    @property
    def is_won(self) -> bool:
        """Check if the game is won."""
        if not self.guesses:
            return False
        return self.guesses[-1].feedback.is_correct(self.code_length)
    
    @property
    def is_lost(self) -> bool:
        """Check if the game is lost (no attempts left and not won)."""
        return self.attempts_left <= 0 and not self.is_won
    
    @property
    def is_over(self) -> bool:
        """Check if the game is over."""
        return self.is_won or self.is_lost
    
    def available_colors(self) -> List[Color]:
        """Get list of available colors for this game."""
        return list(Color)[:self.num_colors]


def calculate_feedback(guess: List[Color], secret: List[Color]) -> Feedback:
    """
    Calculate feedback for a guess against the secret code.
    
    Handles duplicates correctly:
    - First counts exact matches (black pegs)
    - Then counts color matches in remaining positions (white pegs)
    
    Example:
    - Secret: [R, R, G, B], Guess: [R, G, R, Y]
    - Position 0: R matches R → black
    - Position 1: G doesn't match R
    - Position 2: R doesn't match G
    - Position 3: Y doesn't match B
    - Remaining secret: [R, G, B], Remaining guess: [G, R, Y]
    - G is in remaining secret → white
    - R is in remaining secret → white
    - Result: black=1, white=2
    """
    if len(guess) != len(secret):
        raise ValueError("Guess and secret must have same length")
    
    n = len(secret)
    black = 0
    
    # Track which positions are used (for duplicate handling)
    secret_used = [False] * n
    guess_used = [False] * n
    
    # First pass: count exact matches (black pegs)
    for i in range(n):
        if guess[i] == secret[i]:
            black += 1
            secret_used[i] = True
            guess_used[i] = True
    
    # Second pass: count color matches in remaining positions (white pegs)
    white = 0
    for i in range(n):
        if guess_used[i]:
            continue
        # Look for this color in unused secret positions
        for j in range(n):
            if not secret_used[j] and guess[i] == secret[j]:
                white += 1
                secret_used[j] = True
                break
    
    return Feedback(black=black, white=white)


def create_game(
    code_length: int = 4,
    num_colors: int = 6,
    max_attempts: int = 10,
    allow_duplicates: bool = True,
    seed: Optional[int] = None
) -> MastermindGame:
    """
    Create a new Mastermind game with a random secret code.
    
    Args:
        code_length: Length of the secret code (default 4)
        num_colors: Number of different colors to use (default 6)
        max_attempts: Maximum number of guesses allowed (default 10)
        allow_duplicates: Whether colors can repeat in code (default True)
        seed: Random seed for reproducibility
    """
    if seed is not None:
        random.seed(seed)
    
    available = list(Color)[:num_colors]
    
    if allow_duplicates:
        secret = [random.choice(available) for _ in range(code_length)]
    else:
        if code_length > num_colors:
            raise ValueError("Code length cannot exceed number of colors when duplicates disabled")
        secret = random.sample(available, code_length)
    
    return MastermindGame(
        secret=secret,
        num_colors=num_colors,
        max_attempts=max_attempts
    )


def make_guess(game: MastermindGame, guess: List[Color]) -> Feedback:
    """
    Make a guess and get feedback.
    
    Args:
        game: The current game state
        guess: List of colors (must match code length)
        
    Returns:
        Feedback object with black and white peg counts
        
    Raises:
        ValueError: If game is over or guess is invalid
    """
    if game.is_over:
        raise ValueError("Game is already over")
    
    if len(guess) != game.code_length:
        raise ValueError(f"Guess must have {game.code_length} colors")
    
    # Validate colors
    available = game.available_colors()
    for color in guess:
        if color not in available:
            raise ValueError(f"Color {color} is not available in this game")
    
    feedback = calculate_feedback(guess, game.secret)
    game.guesses.append(Guess(code=list(guess), feedback=feedback))
    
    return feedback


def get_all_possible_codes(code_length: int, num_colors: int) -> List[List[Color]]:
    """Generate all possible codes for the given parameters."""
    from itertools import product
    colors = list(Color)[:num_colors]
    return [list(code) for code in product(colors, repeat=code_length)]


def filter_compatible_codes(
    codes: List[List[Color]], 
    guess: List[Color], 
    feedback: Feedback
) -> List[List[Color]]:
    """
    Filter codes that are compatible with the given guess and feedback.
    Used for AI/hint functionality.
    """
    return [
        code for code in codes
        if calculate_feedback(guess, code) == feedback
    ]


def suggest_guess(game: MastermindGame) -> List[Color]:
    """
    Suggest a good next guess using minimax strategy.
    
    This finds the guess that minimizes the maximum remaining possibilities
    after receiving any feedback.
    """
    if not game.guesses:
        # First guess: use a pattern like [0,0,1,1] which is known to be good
        colors = game.available_colors()
        if game.code_length == 4 and len(colors) >= 2:
            return [colors[0], colors[0], colors[1], colors[1]]
        else:
            return [colors[i % len(colors)] for i in range(game.code_length)]
    
    # Get all possible codes
    all_codes = get_all_possible_codes(game.code_length, game.num_colors)
    
    # Filter to only codes compatible with all previous guesses
    possible = all_codes
    for guess_obj in game.guesses:
        possible = filter_compatible_codes(possible, guess_obj.code, guess_obj.feedback)
    
    if len(possible) <= 1:
        return possible[0] if possible else game.available_colors()[:game.code_length]
    
    if len(possible) <= 2:
        return possible[0]
    
    # For performance, limit search to first 100 candidates
    # In practice, checking all possibilities is too slow
    candidates = possible[:100] if len(possible) > 100 else all_codes[:500]
    
    best_guess = None
    best_score = float('inf')
    
    for candidate in candidates:
        # Calculate worst-case remaining possibilities for this guess
        feedback_counts = {}
        for secret in possible:
            fb = calculate_feedback(candidate, secret)
            key = (fb.black, fb.white)
            feedback_counts[key] = feedback_counts.get(key, 0) + 1
        
        max_remaining = max(feedback_counts.values())
        
        # Prefer candidates that are also possible secrets
        is_possible = candidate in possible
        score = (max_remaining, 0 if is_possible else 1)
        
        if score < (best_score, 1) if not isinstance(best_score, tuple) else score < best_score:
            best_score = score
            best_guess = candidate
    
    return best_guess if best_guess else possible[0]


def count_remaining_possibilities(game: MastermindGame) -> int:
    """Count how many codes are still possible given the guesses so far."""
    if not game.guesses:
        return game.num_colors ** game.code_length
    
    all_codes = get_all_possible_codes(game.code_length, game.num_colors)
    possible = all_codes
    
    for guess_obj in game.guesses:
        possible = filter_compatible_codes(possible, guess_obj.code, guess_obj.feedback)
    
    return len(possible)
