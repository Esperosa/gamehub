"""
Piškvorky/Gomoku AI - Optimized with NumPy + Numba (non-recursive only)

Performance targets:
- Easy: <5ms per move (instant)
- Medium: <30ms per move
- Hard: <300ms per move (max 500ms)

Strategy:
- Numba JIT for evaluation and move generation (20-50x speedup)
- Pure Python minimax (avoids Numba recursive compilation issues)
- Transposition table for caching
- Smart move ordering for better alpha-beta pruning
"""
from __future__ import annotations

import importlib.util
import numpy as np
try:
    from numba import njit, int8, int32, int64, boolean, prange
    from numba.typed import List as NumbaList
except ImportError:
    # Packaged/runtime fallback when numba is unavailable.
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator

    int8 = np.int8
    int32 = np.int32
    int64 = np.int64
    boolean = np.bool_
    prange = range
    NumbaList = list
import random
import math
import time
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from functools import lru_cache

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
GameState = _engine_module.GameState
check_winner_fast = _engine_module.check_winner_fast
find_winning_move = _engine_module.find_winning_move
find_fork_moves = _engine_module.find_fork_moves
get_cell_lines = _engine_module.get_cell_lines
get_cached_lines = _engine_module.get_cached_lines


# =============================================================================
# CONSTANTS
# =============================================================================

WIN_SCORE = 1_000_000
FORK_SCORE = 100_000
THREAT_WIN = 50_000
THREAT_HIGH = 10_000
THREAT_MED = 1_000
CENTER_BONUS = 300

# Transposition table
_tt: Dict[int, Tuple[int, int, int, int]] = {}  # hash -> (score, depth, flag, move)
TT_EXACT = 0
TT_LOWER = 1
TT_UPPER = 2


# =============================================================================
# NUMBA JIT OPTIMIZED FUNCTIONS (NON-RECURSIVE)
# =============================================================================

@njit(cache=True, fastmath=True)
def evaluate_position_fast(board: np.ndarray, n: int32, win_len: int32, 
                           player: int8) -> int32:
    """
    Fast position evaluation using Numba JIT.
    Counts patterns in all 4 directions.
    """
    score = int32(0)
    
    # Direction vectors
    dirs = ((0, 1), (1, 0), (1, 1), (1, -1))
    
    for r in range(n):
        for c in range(n):
            idx = r * n + c
            if board[idx] != player:
                continue
            
            for dr, dc in dirs:
                # Only count from leftmost/topmost position
                pr, pc = r - dr, c - dc
                if 0 <= pr < n and 0 <= pc < n:
                    pi = pr * n + pc
                    if board[pi] == player:
                        continue  # Will be counted from that position
                
                # Count consecutive pieces
                count = 1
                open_ends = 0
                
                # Check backward for open end
                if 0 <= pr < n and 0 <= pc < n:
                    pi = pr * n + pc
                    if board[pi] == 0:
                        open_ends += 1
                
                # Forward
                nr, nc = r + dr, c + dc
                while 0 <= nr < n and 0 <= nc < n:
                    ni = nr * n + nc
                    if board[ni] == player:
                        count += 1
                        nr += dr
                        nc += dc
                    elif board[ni] == 0:
                        open_ends += 1
                        break
                    else:
                        break
                else:
                    pass  # Hit edge
                
                # Score pattern
                if count >= win_len:
                    return int32(WIN_SCORE)
                elif count == win_len - 1:
                    if open_ends == 2:
                        score += THREAT_WIN  # Open 4 - unstoppable
                    elif open_ends == 1:
                        score += THREAT_HIGH  # Half-open 4
                elif count == win_len - 2:
                    if open_ends == 2:
                        score += THREAT_MED  # Open 3
                    elif open_ends == 1:
                        score += THREAT_MED // 3
                elif count >= 2:
                    score += count * 10 * open_ends
    
    # Center bonus
    center = n // 2
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            cr, cc = center + dr, center + dc
            if 0 <= cr < n and 0 <= cc < n:
                ci = cr * n + cc
                if board[ci] == player:
                    dist = abs(dr) + abs(dc)
                    score += CENTER_BONUS // (dist + 1)
    
    return score


@njit(cache=True, fastmath=True)
def evaluate_board_fast(board: np.ndarray, n: int32, win_len: int32, 
                        perspective: int8) -> int32:
    """Evaluate board from perspective's point of view."""
    my_score = evaluate_position_fast(board, n, win_len, perspective)
    opp_score = evaluate_position_fast(board, n, win_len, int8(-perspective))
    return my_score - opp_score


@njit(cache=True)
def get_nearby_moves_fast(board: np.ndarray, n: int32, radius: int32) -> np.ndarray:
    """Get empty cells near existing pieces - returns array of indices."""
    result = np.zeros(n * n, dtype=np.int32)
    count = 0
    
    for idx in range(n * n):
        if board[idx] != 0:
            continue
        
        r, c = idx // n, idx % n
        found = False
        
        for dr in range(-radius, radius + 1):
            if found:
                break
            for dc in range(-radius, radius + 1):
                nr, nc = r + dr, c + dc
                if 0 <= nr < n and 0 <= nc < n:
                    ni = nr * n + nc
                    if board[ni] != 0:
                        found = True
                        break
        
        if found:
            result[count] = idx
            count += 1
    
    # If no nearby moves, return center
    if count == 0:
        center = (n // 2) * n + (n // 2)
        if board[center] == 0:
            result[0] = center
            count = 1
    
    return result[:count]


@njit(cache=True, fastmath=True)
def score_move_fast(board: np.ndarray, move: int32, n: int32, 
                    win_len: int32, player: int8) -> int32:
    """Score a move for move ordering."""
    center = n // 2
    r, c = move // n, move % n
    
    # Center distance bonus
    dist = abs(r - center) + abs(c - center)
    score = (n * 2 - dist) * 50
    
    # Check if move creates threat
    board[move] = player
    my_eval = evaluate_position_fast(board, n, win_len, player)
    board[move] = 0
    
    score += my_eval // 10
    
    # Check if move blocks threat
    board[move] = int8(-player)
    opp_eval = evaluate_position_fast(board, n, win_len, int8(-player))
    board[move] = 0
    
    score += opp_eval // 20
    
    return score


@njit(cache=True)
def order_moves_fast(board: np.ndarray, moves: np.ndarray, n: int32, 
                     win_len: int32, player: int8) -> np.ndarray:
    """Order moves by heuristic score for better pruning."""
    scores = np.zeros(len(moves), dtype=np.int32)
    
    for i in range(len(moves)):
        scores[i] = score_move_fast(board, moves[i], n, win_len, player)
    
    # Sort by score descending
    indices = np.argsort(-scores)
    return moves[indices]


@njit(cache=True)
def check_immediate_win(board: np.ndarray, n: int32, win_len: int32, 
                        player: int8) -> int32:
    """Check if player can win immediately. Returns move index or -1."""
    for idx in range(n * n):
        if board[idx] != 0:
            continue
        
        board[idx] = player
        if evaluate_position_fast(board, n, win_len, player) >= WIN_SCORE:
            board[idx] = 0
            return int32(idx)
        board[idx] = 0
    
    return int32(-1)


@njit(cache=True)
def hash_board(board: np.ndarray) -> int64:
    """Simple board hash for transposition table."""
    h = int64(0)
    for i in range(len(board)):
        h = h * 3 + (board[i] + 1)
    return h


# =============================================================================
# PYTHON MINIMAX (with NumPy arrays, no Numba for recursion)
# =============================================================================

def minimax_ab(board: np.ndarray, n: int, win_len: int,
               depth: int, alpha: int, beta: int,
               maximizing: bool, player: int, 
               tt: Dict) -> Tuple[int, int]:
    """
    Minimax with alpha-beta pruning and transposition table.
    Returns (score, best_move).
    """
    # Terminal check using fast Numba functions
    my_eval = int(evaluate_position_fast(board, np.int32(n), np.int32(win_len), np.int8(player)))
    opp_eval = int(evaluate_position_fast(board, np.int32(n), np.int32(win_len), np.int8(-player)))
    
    if my_eval >= WIN_SCORE:
        return WIN_SCORE + depth, -1  # Prefer faster wins
    if opp_eval >= WIN_SCORE:
        return -WIN_SCORE - depth, -1
    
    # Transposition table lookup
    board_hash = int(hash_board(board))
    tt_key = (board_hash, player if maximizing else -player)
    
    if tt_key in tt:
        tt_score, tt_depth, tt_flag, tt_move = tt[tt_key]
        if tt_depth >= depth:
            if tt_flag == TT_EXACT:
                return tt_score, tt_move
            elif tt_flag == TT_LOWER and tt_score >= beta:
                return tt_score, tt_move
            elif tt_flag == TT_UPPER and tt_score <= alpha:
                return tt_score, tt_move
    
    if depth == 0:
        return my_eval - opp_eval, -1
    
    # Get and order moves
    moves = get_nearby_moves_fast(board, np.int32(n), np.int32(2))
    if len(moves) == 0:
        return 0, -1
    
    curr_player = np.int8(player if maximizing else -player)
    moves = order_moves_fast(board, moves, np.int32(n), np.int32(win_len), curr_player)
    
    # Limit branching factor
    max_moves = 15 if depth > 2 else 20
    if len(moves) > max_moves:
        moves = moves[:max_moves]
    
    best_move = int(moves[0])
    orig_alpha = alpha
    
    if maximizing:
        max_score = -100000000
        
        for i in range(len(moves)):
            m = int(moves[i])
            board[m] = player
            score, _ = minimax_ab(board, n, win_len, depth - 1, 
                                  alpha, beta, False, player, tt)
            board[m] = 0
            
            if score > max_score:
                max_score = score
                best_move = m
            
            alpha = max(alpha, score)
            if beta <= alpha:
                break
        
        # Store in transposition table
        if max_score <= orig_alpha:
            tt_flag = TT_UPPER
        elif max_score >= beta:
            tt_flag = TT_LOWER
        else:
            tt_flag = TT_EXACT
        tt[tt_key] = (max_score, depth, tt_flag, best_move)
        
        return max_score, best_move
    else:
        min_score = 100000000
        
        for i in range(len(moves)):
            m = int(moves[i])
            board[m] = -player
            score, _ = minimax_ab(board, n, win_len, depth - 1,
                                  alpha, beta, True, player, tt)
            board[m] = 0
            
            if score < min_score:
                min_score = score
                best_move = m
            
            beta = min(beta, score)
            if beta <= alpha:
                break
        
        # Store in transposition table
        if min_score <= orig_alpha:
            tt_flag = TT_UPPER
        elif min_score >= beta:
            tt_flag = TT_LOWER
        else:
            tt_flag = TT_EXACT
        tt[tt_key] = (min_score, depth, tt_flag, best_move)
        
        return min_score, best_move


# =============================================================================
# SEARCH RESULT
# =============================================================================

@dataclass
class SearchResult:
    """AI search result."""
    move: int
    score: int = 0
    depth: int = 0
    time_ms: float = 0.0


# =============================================================================
# PUBLIC API
# =============================================================================

def evaluate(state: GameState, perspective: int) -> int:
    """Evaluate position from perspective's view."""
    board = np.array(state.board, dtype=np.int8)
    return int(evaluate_board_fast(board, np.int32(state.n), 
                                   np.int32(state.win_len), np.int8(perspective)))


def evaluate_fast(state: GameState, perspective: int) -> int:
    """Alias for evaluate."""
    return evaluate(state, perspective)


def win_probability_from_score(score: int, n: int) -> float:
    """Convert score to win probability."""
    if score >= WIN_SCORE:
        return 1.0
    if score <= -WIN_SCORE:
        return 0.0
    k = 0.0001 * (14 - n)
    return 1.0 / (1.0 + math.exp(-k * score))


def best_move_easy(state: GameState) -> int:
    """
    EASY AI - Makes mistakes intentionally.
    - Takes wins
    - Often misses blocks (50%)
    - Random otherwise with center bias
    """
    bot = state.to_move
    
    # Always take a win
    win = find_winning_move(state, bot)
    if win is not None:
        return win
    
    # Only block 50% of the time
    if random.random() < 0.5:
        block = find_winning_move(state, -bot)
        if block is not None:
            return block
    
    # Random move with slight center preference
    moves = state.smart_moves(radius=2)
    if not moves:
        return 0
    
    # 70% random, 30% center-biased
    if random.random() < 0.7:
        return random.choice(moves)
    
    # Center-biased
    center = state.n // 2
    def dist(m):
        r, c = m // state.n, m % state.n
        return abs(r - center) + abs(c - center)
    
    return min(moves, key=dist)


def best_move_medium(state: GameState, bot: int) -> int:
    """
    MEDIUM AI - Makes strategic mistakes.
    Target: <30ms per move.
    - Always takes wins
    - Sometimes misses blocks (30% miss rate)
    - Rarely finds forks (30%)
    - Shallow search (depth 2)
    """
    opp = -bot
    
    # Always take wins
    win = find_winning_move(state, bot)
    if win is not None:
        return win
    
    # Block immediate threats (70% - sometimes misses!)
    if random.random() < 0.7:
        block = find_winning_move(state, opp)
        if block is not None:
            return block
    
    # Forks (30% chance - often misses)
    if random.random() < 0.3:
        forks = find_fork_moves(state, bot)
        if forks:
            return random.choice(forks)
    
    # Block forks (20% - usually misses)
    if random.random() < 0.2:
        opp_forks = find_fork_moves(state, opp)
        if opp_forks:
            return random.choice(opp_forks)
    
    # Shallow search with some randomness
    if random.random() < 0.5:
        board = np.array(state.board, dtype=np.int8)
        tt = {}
        _, move = minimax_ab(board, state.n, state.win_len, 2, 
                            -100000000, 100000000, True, bot, tt)
        if move >= 0:
            return move
    
    # Center-biased random
    moves = state.smart_moves(radius=2)
    if not moves:
        return 0
    
    if random.random() < 0.6:
        return random.choice(moves)
    
    center = state.n // 2
    def dist(m):
        r, c = m // state.n, m % state.n
        return abs(r - center) + abs(c - center)
    
    return min(moves, key=dist)


def best_move_hard(state: GameState, bot: int, 
                   time_limit: float = 0.5) -> SearchResult:
    """
    HARD AI - Deep strategic search with transposition table.
    Target: <500ms average, <800ms max.
    
    Strategy:
    - 3×3: Perfect minimax (depth 9)
    - 8×8: Deep alpha-beta (depth 8) - very strong
    - 13×13: Alpha-beta (depth 6)
    """
    start = time.perf_counter()
    opp = -bot
    n = state.n
    
    # First move - center
    if state.move_count() == 0:
        center = n // 2
        return SearchResult(move=center * n + center, depth=1)
    
    # Second move - adjacent to center or corner
    if state.move_count() == 1:
        center = n // 2
        center_idx = center * n + center
        if state.board[center_idx] != 0:
            # Opponent took center, play adjacent
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1)]:
                r, c = center + dr, center + dc
                if 0 <= r < n and 0 <= c < n:
                    idx = r * n + c
                    if state.board[idx] == 0:
                        return SearchResult(move=idx, depth=1)
        else:
            # Take center
            return SearchResult(move=center_idx, depth=1)
    
    # Immediate tactics using fast Numba check
    board = np.array(state.board, dtype=np.int8)
    
    win = int(check_immediate_win(board, np.int32(n), np.int32(state.win_len), np.int8(bot)))
    if win >= 0:
        return SearchResult(move=win, score=WIN_SCORE, depth=1)
    
    block = int(check_immediate_win(board, np.int32(n), np.int32(state.win_len), np.int8(opp)))
    if block >= 0:
        return SearchResult(move=block, score=0, depth=1)
    
    # Forks
    forks = find_fork_moves(state, bot)
    if forks:
        best = max(forks, key=lambda m: _eval_move(state, m, bot))
        return SearchResult(move=best, score=FORK_SCORE, depth=2)
    
    opp_forks = find_fork_moves(state, opp)
    if opp_forks:
        best = max(opp_forks, key=lambda m: _eval_move(state, m, bot))
        return SearchResult(move=best, score=0, depth=2)
    
    # Deep search with iterative deepening
    tt = {}  # Fresh transposition table
    
    if n <= 3:
        result = _search_iterative(state, bot, max_depth=9, time_limit=time_limit, tt=tt)
    elif n <= 8:
        # Stronger search for 8×8 - depth 8
        result = _search_iterative(state, bot, max_depth=8, time_limit=time_limit, tt=tt)
    else:
        # 13×13 - depth 6
        result = _search_iterative(state, bot, max_depth=6, time_limit=time_limit, tt=tt)
    
    result.time_ms = (time.perf_counter() - start) * 1000
    return result


def _eval_move(state: GameState, move: int, bot: int) -> int:
    """Evaluate position after move."""
    state.apply(move)
    score = evaluate(state, bot)
    state.undo(move)
    return score


def _search_iterative(state: GameState, bot: int, max_depth: int, 
                      time_limit: float, tt: Dict) -> SearchResult:
    """Iterative deepening search with time limit."""
    board = np.array(state.board, dtype=np.int8)
    start = time.perf_counter()
    
    best_result = SearchResult(move=0, score=0, depth=0)
    
    for d in range(2, max_depth + 1):
        if time.perf_counter() - start > time_limit * 0.8:
            break
        
        score, move = minimax_ab(
            board.copy(), state.n, state.win_len,
            d, -100000000, 100000000,
            True, bot, tt
        )
        
        if move >= 0:
            best_result = SearchResult(move=move, score=score, depth=d)
        
        # Stop if found forced win
        if score >= WIN_SCORE - 100:
            break
    
    if best_result.move == 0:
        moves = state.smart_moves()
        if moves:
            best_result.move = moves[0]
    
    return best_result


def best_move(state: GameState, bot: int, difficulty: str = "hard") -> int:
    """
    Main AI interface.
    
    Args:
        state: Current game state
        bot: Player to move (1 or -1)
        difficulty: 'easy', 'medium', or 'hard'
    
    Returns:
        Best move index
    """
    if difficulty == "easy":
        return best_move_easy(state)
    elif difficulty == "medium":
        return best_move_medium(state, bot)
    else:
        return best_move_hard(state, bot).move


# =============================================================================
# WARMUP - Pre-compile Numba functions
# =============================================================================

_warmed_up = False

def warmup():
    """Pre-compile Numba functions. Call this before first AI use."""
    global _warmed_up
    if _warmed_up:
        return
    
    try:
        # Warmup with small boards
        board3 = np.zeros(9, dtype=np.int8)
        board3[4] = 1
        _ = evaluate_position_fast(board3, np.int32(3), np.int32(3), np.int8(1))
        _ = evaluate_board_fast(board3, np.int32(3), np.int32(3), np.int8(1))
        _ = get_nearby_moves_fast(board3, np.int32(3), np.int32(2))
        _ = check_immediate_win(board3, np.int32(3), np.int32(3), np.int8(1))
        _ = hash_board(board3)
        
        moves = get_nearby_moves_fast(board3, np.int32(3), np.int32(2))
        if len(moves) > 0:
            _ = order_moves_fast(board3, moves, np.int32(3), np.int32(3), np.int8(1))
            _ = score_move_fast(board3, moves[0], np.int32(3), np.int32(3), np.int8(1))
        
        # Warmup 8x8
        board8 = np.zeros(64, dtype=np.int8)
        board8[27] = 1
        _ = evaluate_position_fast(board8, np.int32(8), np.int32(4), np.int8(1))
        _ = get_nearby_moves_fast(board8, np.int32(8), np.int32(2))
        
        _warmed_up = True
    except Exception as e:
        print(f"Warmup error: {e}")
        _warmed_up = True  # Don't retry
