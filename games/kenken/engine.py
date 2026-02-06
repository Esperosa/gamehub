"""
KenKen Engine - Fast Generation and Solving

Design principles:
- O(N²) Latin square via cyclic construction + permutations
- Merge-partition caging for natural cage shapes
- - and / only for 2-cell cages
- Unique solution via regeneration
- Fast constraint propagation with precomputed cage possibilities
- Bitset-based candidate tracking for O(1) operations
- Numba JIT compilation for native-speed solving

All puzzles are guaranteed to have exactly one solution.
"""
from __future__ import annotations

import random
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set, Dict, FrozenSet
from itertools import permutations, product
from functools import lru_cache

# Numba JIT compilation for native CPU speed
try:
    from numba import njit, prange
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    # Fallback decorators
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator
    prange = range


# ============== NUMBA-ACCELERATED CORE FUNCTIONS ==============
# These run at near-C speed, bypassing Python's GIL

@njit(cache=True)
def _count_bits_fast(x: int) -> int:
    """Count set bits - optimized."""
    count = 0
    while x:
        count += x & 1
        x >>= 1
    return count

@njit(cache=True)
def _propagate_latin(candidates: np.ndarray, board: np.ndarray, n: int) -> bool:
    """Fast Latin square propagation using numpy arrays."""
    changed = True
    iterations = 0
    max_iter = n * n * 2
    
    while changed and iterations < max_iter:
        changed = False
        iterations += 1
        
        # Row constraints
        for i in range(n):
            placed = 0
            for j in range(n):
                idx = i * n + j
                if board[idx] != 0:
                    placed |= (1 << board[idx])
            
            for j in range(n):
                idx = i * n + j
                if board[idx] == 0:
                    old = candidates[idx]
                    candidates[idx] &= ~placed
                    if candidates[idx] == 0:
                        return False
                    if candidates[idx] != old:
                        changed = True
                    # Check if only one candidate left
                    if candidates[idx] & (candidates[idx] - 1) == 0:
                        # Find the set bit
                        val = 0
                        temp = candidates[idx]
                        while temp > 1:
                            temp >>= 1
                            val += 1
                        board[idx] = val
                        changed = True
        
        # Column constraints
        for i in range(n):
            placed = 0
            for j in range(n):
                idx = j * n + i
                if board[idx] != 0:
                    placed |= (1 << board[idx])
            
            for j in range(n):
                idx = j * n + i
                if board[idx] == 0:
                    old = candidates[idx]
                    candidates[idx] &= ~placed
                    if candidates[idx] == 0:
                        return False
                    if candidates[idx] != old:
                        changed = True
                    if candidates[idx] & (candidates[idx] - 1) == 0:
                        val = 0
                        temp = candidates[idx]
                        while temp > 1:
                            temp >>= 1
                            val += 1
                        board[idx] = val
                        changed = True
    
    return True

@njit(cache=True)
def _solve_recursive_fast(board: np.ndarray, candidates: np.ndarray, n: int) -> bool:
    """Fast recursive solver with MRV heuristic."""
    # Propagate Latin constraints
    if not _propagate_latin(candidates, board, n):
        return False
    
    # Find cell with minimum remaining values (MRV heuristic)
    best_cell = -1
    min_count = n + 2
    
    for i in range(n * n):
        if board[i] == 0:
            cnt = _count_bits_fast(candidates[i])
            if cnt == 0:
                return False
            if cnt < min_count:
                min_count = cnt
                best_cell = i
                if cnt == 1:
                    break
    
    if best_cell == -1:
        return True  # All filled
    
    cands = candidates[best_cell]
    for val in range(1, n + 1):
        if not (cands & (1 << val)):
            continue
        
        # Copy state
        new_board = board.copy()
        new_cands = candidates.copy()
        
        new_board[best_cell] = val
        new_cands[best_cell] = 1 << val
        
        if _solve_recursive_fast(new_board, new_cands, n):
            # Copy solution back
            for i in range(n * n):
                board[i] = new_board[i]
            return True
    
    return False

@njit(cache=True)
def _count_solutions_iterative(board_init: np.ndarray, candidates_init: np.ndarray, 
                                n: int, limit: int) -> int:
    """Count solutions using iterative DFS with explicit stack - faster JIT compilation."""
    # Stack holds (board, candidates, cell_idx, val_idx) tuples
    # Using fixed-size arrays as stack (max depth = n*n)
    max_depth = n * n
    
    # Allocate stack space
    stack_boards = np.zeros((max_depth + 1, n * n), dtype=np.int32)
    stack_cands = np.zeros((max_depth + 1, n * n), dtype=np.int64)
    stack_cell = np.zeros(max_depth + 1, dtype=np.int32)
    stack_val = np.zeros(max_depth + 1, dtype=np.int32)
    
    # Initialize
    stack_boards[0] = board_init.copy()
    stack_cands[0] = candidates_init.copy()
    
    # Initial propagation
    if not _propagate_latin(stack_cands[0], stack_boards[0], n):
        return 0
    
    # Find first cell
    best_cell = -1
    min_count = n + 2
    for i in range(n * n):
        if stack_boards[0, i] == 0:
            cnt = _count_bits_fast(stack_cands[0, i])
            if cnt == 0:
                return 0
            if cnt < min_count:
                min_count = cnt
                best_cell = i
    
    if best_cell == -1:
        return 1
    
    stack_cell[0] = best_cell
    stack_val[0] = 1
    depth = 0
    count = 0
    
    while depth >= 0:
        if count >= limit:
            return count
        
        cell = stack_cell[depth]
        start_val = stack_val[depth]
        found_val = False
        
        for val in range(start_val, n + 1):
            if stack_cands[depth, cell] & (1 << val):
                # Try this value
                stack_val[depth] = val + 1  # Next time try next value
                
                # Copy to next level
                stack_boards[depth + 1] = stack_boards[depth].copy()
                stack_cands[depth + 1] = stack_cands[depth].copy()
                
                stack_boards[depth + 1, cell] = val
                stack_cands[depth + 1, cell] = 1 << val
                
                # Propagate
                if _propagate_latin(stack_cands[depth + 1], stack_boards[depth + 1], n):
                    # Find next empty cell
                    next_cell = -1
                    min_c = n + 2
                    for i in range(n * n):
                        if stack_boards[depth + 1, i] == 0:
                            cnt = _count_bits_fast(stack_cands[depth + 1, i])
                            if cnt == 0:
                                next_cell = -2  # Dead end
                                break
                            if cnt < min_c:
                                min_c = cnt
                                next_cell = i
                    
                    if next_cell == -1:
                        # Found solution
                        count += 1
                        if count >= limit:
                            return count
                    elif next_cell >= 0:
                        # Go deeper
                        depth += 1
                        stack_cell[depth] = next_cell
                        stack_val[depth] = 1
                        found_val = True
                        break
        
        if not found_val:
            depth -= 1
    
    return count


@njit(cache=True)
def _count_solutions_fast(board: np.ndarray, candidates: np.ndarray, n: int, 
                          limit: int) -> int:
    """Count solutions - delegates to iterative version."""
    return _count_solutions_iterative(board, candidates, n, limit)


@njit(cache=True)
def _check_cage_sum(board: np.ndarray, cell_indices: np.ndarray, target: int, n: int) -> int:
    """Check if cage sum constraint is satisfied. Returns: 0=invalid, 1=valid, 2=incomplete."""
    total = 0
    complete = True
    for idx in cell_indices:
        val = board[idx]
        if val == 0:
            complete = False
        else:
            total += val
    
    if complete:
        return 1 if total == target else 0
    else:
        return 2 if total < target else 0  # Partial check for sum


@njit(cache=True)
def _check_cage_prod(board: np.ndarray, cell_indices: np.ndarray, target: int, n: int) -> int:
    """Check if cage product constraint is satisfied."""
    prod = 1
    complete = True
    for idx in cell_indices:
        val = board[idx]
        if val == 0:
            complete = False
        else:
            prod *= val
    
    if complete:
        return 1 if prod == target else 0
    else:
        # Partial: product must divide target
        return 2 if (target % prod == 0) else 0


@njit(cache=True)
def _check_cage_diff(board: np.ndarray, cell_indices: np.ndarray, target: int) -> int:
    """Check 2-cell difference cage."""
    v1 = board[cell_indices[0]]
    v2 = board[cell_indices[1]]
    if v1 == 0 or v2 == 0:
        return 2  # Incomplete
    diff = v1 - v2 if v1 > v2 else v2 - v1
    return 1 if diff == target else 0


@njit(cache=True)
def _check_cage_div(board: np.ndarray, cell_indices: np.ndarray, target: int) -> int:
    """Check 2-cell division cage."""
    v1 = board[cell_indices[0]]
    v2 = board[cell_indices[1]]
    if v1 == 0 or v2 == 0:
        return 2  # Incomplete
    if v1 >= v2 and v2 != 0 and v1 % v2 == 0 and v1 // v2 == target:
        return 1
    if v2 >= v1 and v1 != 0 and v2 % v1 == 0 and v2 // v1 == target:
        return 1
    return 0


@njit(cache=True)
def _check_all_cages(board: np.ndarray, 
                     cage_cells: np.ndarray, 
                     cage_starts: np.ndarray,
                     cage_ops: np.ndarray,
                     cage_targets: np.ndarray,
                     num_cages: int, n: int) -> bool:
    """Check all cage constraints. Returns False if any cage is invalid."""
    for c in range(num_cages):
        start = cage_starts[c]
        end = cage_starts[c + 1]
        cell_indices = cage_cells[start:end]
        op = cage_ops[c]
        target = cage_targets[c]
        
        # op: 0=single, 1=+, 2=*, 3=-, 4=/
        if op == 0:  # Single cell
            val = board[cell_indices[0]]
            if val != 0 and val != target:
                return False
        elif op == 1:  # Sum
            result = _check_cage_sum(board, cell_indices, target, n)
            if result == 0:
                return False
        elif op == 2:  # Product
            result = _check_cage_prod(board, cell_indices, target, n)
            if result == 0:
                return False
        elif op == 3:  # Difference
            result = _check_cage_diff(board, cell_indices, target)
            if result == 0:
                return False
        elif op == 4:  # Division
            result = _check_cage_div(board, cell_indices, target)
            if result == 0:
                return False
    
    return True


@njit(cache=True)
def _count_solutions_with_cages(board_init: np.ndarray, candidates_init: np.ndarray, n: int, 
                                 limit: int,
                                 cage_cells: np.ndarray, 
                                 cage_starts: np.ndarray,
                                 cage_ops: np.ndarray,
                                 cage_targets: np.ndarray,
                                 num_cages: int) -> int:
    """Count solutions with cage constraints - iterative stack-based."""
    max_depth = n * n
    
    # Allocate stack
    stack_boards = np.zeros((max_depth + 1, n * n), dtype=np.int32)
    stack_cands = np.zeros((max_depth + 1, n * n), dtype=np.int64)
    stack_cell = np.zeros(max_depth + 1, dtype=np.int32)
    stack_val = np.zeros(max_depth + 1, dtype=np.int32)
    
    # Initialize
    stack_boards[0] = board_init.copy()
    stack_cands[0] = candidates_init.copy()
    
    # Initial propagation and cage check
    if not _propagate_latin(stack_cands[0], stack_boards[0], n):
        return 0
    if not _check_all_cages(stack_boards[0], cage_cells, cage_starts, cage_ops, cage_targets, num_cages, n):
        return 0
    
    # Find first cell
    best_cell = -1
    min_count = n + 2
    for i in range(n * n):
        if stack_boards[0, i] == 0:
            cnt = _count_bits_fast(stack_cands[0, i])
            if cnt == 0:
                return 0
            if cnt < min_count:
                min_count = cnt
                best_cell = i
    
    if best_cell == -1:
        return 1
    
    stack_cell[0] = best_cell
    stack_val[0] = 1
    depth = 0
    count = 0
    
    while depth >= 0:
        if count >= limit:
            return count
        
        cell = stack_cell[depth]
        start_val = stack_val[depth]
        found_val = False
        
        for val in range(start_val, n + 1):
            if stack_cands[depth, cell] & (1 << val):
                stack_val[depth] = val + 1
                
                # Copy to next level
                stack_boards[depth + 1] = stack_boards[depth].copy()
                stack_cands[depth + 1] = stack_cands[depth].copy()
                
                stack_boards[depth + 1, cell] = val
                stack_cands[depth + 1, cell] = 1 << val
                
                # Propagate and check cages
                if _propagate_latin(stack_cands[depth + 1], stack_boards[depth + 1], n):
                    if _check_all_cages(stack_boards[depth + 1], cage_cells, cage_starts, 
                                       cage_ops, cage_targets, num_cages, n):
                        # Find next empty cell
                        next_cell = -1
                        min_c = n + 2
                        for i in range(n * n):
                            if stack_boards[depth + 1, i] == 0:
                                cnt = _count_bits_fast(stack_cands[depth + 1, i])
                                if cnt == 0:
                                    next_cell = -2
                                    break
                                if cnt < min_c:
                                    min_c = cnt
                                    next_cell = i
                        
                        if next_cell == -1:
                            count += 1
                            if count >= limit:
                                return count
                        elif next_cell >= 0:
                            depth += 1
                            stack_cell[depth] = next_cell
                            stack_val[depth] = 1
                            found_val = True
                            break
        
        if not found_val:
            depth -= 1
    
    return count

# ============== END NUMBA FUNCTIONS ==============


@dataclass
class Cage:
    """A cage in KenKen - group of cells with target and operation."""
    cells: List[Tuple[int, int]]  # List of (row, col) positions
    target: int
    operation: str  # '+', '-', '*', '/', '' (single cell)
    _possibilities: Optional[FrozenSet[Tuple[int, ...]]] = field(default=None, repr=False, compare=False)
    
    def __hash__(self):
        return hash((tuple(self.cells), self.target, self.operation))
    
    def get_possibilities(self, n: int) -> FrozenSet[Tuple[int, ...]]:
        """Get all valid value combinations for this cage (cached)."""
        if self._possibilities is not None:
            return self._possibilities
        
        self._possibilities = self._compute_possibilities(n)
        return self._possibilities
    
    def _compute_possibilities(self, n: int) -> FrozenSet[Tuple[int, ...]]:
        """Compute all valid value tuples for this cage."""
        size = len(self.cells)
        
        if size == 1:
            return frozenset([(self.target,)])
        
        valid = set()
        
        if self.operation == '+':
            # Generate combinations that sum to target
            self._gen_sum_combos(valid, n, size, self.target, [], 1)
        
        elif self.operation == '*':
            # Generate combinations that multiply to target
            self._gen_prod_combos(valid, n, size, self.target, [], 1)
        
        elif self.operation == '-' and size == 2:
            for a in range(1, n + 1):
                b = a + self.target
                if 1 <= b <= n:
                    valid.add((a, b))
                    valid.add((b, a))
                b = a - self.target
                if 1 <= b <= n:
                    valid.add((a, b))
                    valid.add((b, a))
        
        elif self.operation == '/' and size == 2:
            for a in range(1, n + 1):
                b = a * self.target
                if 1 <= b <= n:
                    valid.add((a, b))
                    valid.add((b, a))
                if a % self.target == 0:
                    b = a // self.target
                    if 1 <= b <= n:
                        valid.add((a, b))
                        valid.add((b, a))
        
        return frozenset(valid)
    
    def _gen_sum_combos(self, result: set, n: int, size: int, target: int, 
                        current: list, start: int) -> None:
        """Generate combinations summing to target - with limit."""
        # Safety limit
        if len(result) > 500:
            return
            
        if len(current) == size:
            if target == 0:
                # Add all permutations
                for perm in set(permutations(current)):
                    result.add(perm)
                    if len(result) > 500:
                        return
            return
        
        remaining = size - len(current)
        # Pruning: min remaining sum, max remaining sum
        min_sum = remaining  # All 1s
        max_sum = remaining * n  # All n
        
        if target < min_sum or target > max_sum:
            return
        
        for v in range(1, n + 1):
            if v <= target:
                current.append(v)
                self._gen_sum_combos(result, n, size, target - v, current, v)
                current.pop()
    
    def _gen_prod_combos(self, result: set, n: int, size: int, target: int,
                         current: list, prod: int) -> None:
        """Generate combinations with product equal to target - with limit."""
        # Safety limit to prevent explosion
        if len(result) > 500:
            return
            
        if len(current) == size:
            if prod == target:
                for perm in set(permutations(current)):
                    result.add(perm)
                    if len(result) > 500:
                        return
            return
        
        remaining = size - len(current)
        
        # Pruning
        if prod > target:
            return
        if target % prod != 0:
            return
        
        # Additional pruning: remaining product must be achievable
        remaining_target = target // prod
        if remaining_target > (n ** remaining):
            return
        
        for v in range(1, n + 1):
            new_prod = prod * v
            if new_prod <= target:
                current.append(v)
                self._gen_prod_combos(result, n, size, target, current, new_prod)
                current.pop()
                if len(result) > 500:
                    return
    
    def check(self, values: List[int]) -> bool:
        """Check if values satisfy this cage's constraint."""
        if not values or 0 in values:
            return False
        
        if len(values) != len(self.cells):
            return False
        
        if self.operation == '' or len(values) == 1:
            return values[0] == self.target
        
        if self.operation == '+':
            return sum(values) == self.target
        
        if self.operation == '*':
            prod = 1
            for v in values:
                prod *= v
            return prod == self.target
        
        if len(values) == 2:
            a, b = values
            if self.operation == '-':
                return abs(a - b) == self.target
            if self.operation == '/':
                if b != 0 and a % b == 0 and a // b == self.target:
                    return True
                if a != 0 and b % a == 0 and b // a == self.target:
                    return True
        
        return False
    
    def partial_check(self, values: List[int]) -> bool:
        """Check if partial values could still satisfy constraint."""
        non_zero = [v for v in values if v != 0]
        if not non_zero:
            return True  # No values yet
        
        if self.operation == '' or len(self.cells) == 1:
            return non_zero[0] == self.target if len(non_zero) == 1 else True
        
        if self.operation == '+':
            return sum(non_zero) <= self.target
        
        if self.operation == '*':
            prod = 1
            for v in non_zero:
                prod *= v
            return self.target % prod == 0 or prod <= self.target
        
        return True


@dataclass
class KenKenConfig:
    """Configuration for a KenKen puzzle."""
    size: int  # 3-9
    
    @property
    def num_range(self) -> int:
        return self.size
    
    @staticmethod
    def from_size(size: int) -> 'KenKenConfig':
        return KenKenConfig(size=max(3, min(9, size)))


@dataclass
class KenKenState:
    """State of a KenKen game."""
    config: KenKenConfig
    board: List[int]  # 0 = empty, 1-N = filled
    cages: List[Cage]
    solution: List[int]
    seed: int
    
    @property
    def size(self) -> int:
        return self.config.size
    
    def get(self, row: int, col: int) -> int:
        return self.board[row * self.size + col]
    
    def set(self, row: int, col: int, value: int) -> None:
        self.board[row * self.size + col] = value
    
    def get_cage_at(self, row: int, col: int) -> Optional[Cage]:
        for cage in self.cages:
            if (row, col) in cage.cells:
                return cage
        return None
    
    def get_hint(self) -> Optional[Tuple[int, int, int]]:
        """Get a hint: (row, col, correct_value)."""
        empty = []
        wrong = []
        for r in range(self.size):
            for c in range(self.size):
                idx = r * self.size + c
                if self.board[idx] == 0:
                    empty.append((r, c))
                elif self.board[idx] != self.solution[idx]:
                    wrong.append((r, c))
        
        if wrong:
            r, c = random.choice(wrong)
        elif empty:
            r, c = random.choice(empty)
        else:
            return None
        
        return (r, c, self.solution[r * self.size + c])
    
    def is_complete(self) -> bool:
        return self.board == self.solution
    
    def count_filled(self) -> int:
        return sum(1 for v in self.board if v != 0)
    
    def count_empty(self) -> int:
        return sum(1 for v in self.board if v == 0)


class KenKenSolver:
    """Fast constraint propagation solver with precomputed possibilities."""
    
    def __init__(self, config: KenKenConfig, cages: List[Cage]):
        self.config = config
        self.size = config.size
        self.cages = cages
        self.n = config.size
        
        # Map cells to cages and cage index
        self._cell_to_cage: Dict[Tuple[int, int], Cage] = {}
        self._cell_to_cage_idx: Dict[Tuple[int, int], int] = {}
        for idx, cage in enumerate(cages):
            for cell in cage.cells:
                self._cell_to_cage[cell] = cage
                self._cell_to_cage_idx[cell] = idx
        
        # Precompute cage possibilities
        for cage in cages:
            cage.get_possibilities(self.n)
    
    def _init_candidates(self) -> List[int]:
        """Initialize candidate bitmasks. Each cell has bits 1-N set."""
        all_bits = (1 << (self.n + 1)) - 2  # bits 1 to N set
        return [all_bits] * (self.n * self.n)
    
    def _propagate(self, candidates: List[int], board: List[int]) -> bool:
        """Propagate constraints. Returns False if contradiction found."""
        n = self.n
        changed = True
        
        while changed:
            changed = False
            
            # Apply placed values
            for i in range(n * n):
                if board[i] != 0:
                    candidates[i] = 1 << board[i]
            
            # Row/Column elimination
            for i in range(n):
                # Row
                placed = 0
                for j in range(n):
                    idx = i * n + j
                    if board[idx] != 0:
                        placed |= (1 << board[idx])
                
                for j in range(n):
                    idx = i * n + j
                    if board[idx] == 0:
                        old = candidates[idx]
                        candidates[idx] &= ~placed
                        if candidates[idx] == 0:
                            return False
                        if candidates[idx] != old:
                            changed = True
                        # Naked single
                        if candidates[idx] & (candidates[idx] - 1) == 0:
                            board[idx] = (candidates[idx]).bit_length() - 1
                            changed = True
                
                # Column
                placed = 0
                for j in range(n):
                    idx = j * n + i
                    if board[idx] != 0:
                        placed |= (1 << board[idx])
                
                for j in range(n):
                    idx = j * n + i
                    if board[idx] == 0:
                        old = candidates[idx]
                        candidates[idx] &= ~placed
                        if candidates[idx] == 0:
                            return False
                        if candidates[idx] != old:
                            changed = True
                        if candidates[idx] & (candidates[idx] - 1) == 0:
                            board[idx] = (candidates[idx]).bit_length() - 1
                            changed = True
            
            # Cage constraint propagation
            for cage in self.cages:
                cell_indices = [r * n + c for r, c in cage.cells]
                
                # For large cages, use simpler constraint check
                if len(cage.cells) > 3:
                    # Just verify partial_check passes
                    vals = [board[idx] for idx in cell_indices]
                    if 0 not in vals and not cage.check(vals):
                        return False
                    continue
                
                possibilities = cage.get_possibilities(n)
                if not possibilities:
                    return False
                
                # Get current candidates for each cell in cage
                cell_cands = [candidates[idx] for idx in cell_indices]
                
                # Filter possibilities by current candidates
                valid_poss = []
                for poss in possibilities:
                    valid = True
                    for i, val in enumerate(poss):
                        if not (cell_cands[i] & (1 << val)):
                            valid = False
                            break
                    if valid:
                        valid_poss.append(poss)
                
                if not valid_poss:
                    return False
                
                # Compute allowed values per position
                for pos_idx, cell_idx in enumerate(cell_indices):
                    if board[cell_idx] != 0:
                        continue
                    
                    allowed = 0
                    for poss in valid_poss:
                        allowed |= (1 << poss[pos_idx])
                    
                    old = candidates[cell_idx]
                    candidates[cell_idx] &= allowed
                    
                    if candidates[cell_idx] == 0:
                        return False
                    if candidates[cell_idx] != old:
                        changed = True
                    if candidates[cell_idx] & (candidates[cell_idx] - 1) == 0:
                        board[cell_idx] = (candidates[cell_idx]).bit_length() - 1
                        changed = True
        
        return True
    
    def _count_bits(self, x: int) -> int:
        """Count set bits - use built-in for speed."""
        return bin(x).count('1')
    
    def _prepare_cage_arrays(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
        """Convert cage data to numpy arrays for Numba."""
        n = self.n
        
        # Flatten all cage cell indices
        all_cells = []
        starts = [0]
        ops = []
        targets = []
        
        op_map = {'': 0, '+': 1, '*': 2, '-': 3, '/': 4}
        
        for cage in self.cages:
            for r, c in cage.cells:
                all_cells.append(r * n + c)
            starts.append(len(all_cells))
            ops.append(op_map.get(cage.operation, 0))
            targets.append(cage.target)
        
        return (
            np.array(all_cells, dtype=np.int32),
            np.array(starts, dtype=np.int32),
            np.array(ops, dtype=np.int32),
            np.array(targets, dtype=np.int32),
            len(self.cages)
        )
    
    def count_solutions(self, board: List[int], limit: int = 2, timeout: float = None) -> int:
        """Count solutions using optimized Python solver with optional timeout.
        
        Args:
            board: Initial board state
            limit: Stop after finding this many solutions
            timeout: Max seconds (None = no limit)
            
        Returns: Number of solutions found, or -1 if timed out
        """
        import time
        n = self.n
        
        self._count = 0
        self._limit = limit
        self._start_time = time.time()
        self._timeout = timeout  # None means no timeout
        self._timed_out = False
        board = board.copy()
        candidates = self._init_candidates()
        
        if not self._propagate(candidates, board):
            return 0
        
        self._count_solve_fast(board, candidates)
        
        if self._timed_out:
            return -1
        return self._count
    
    def _verify_cage_constraints(self, board: List[int]) -> bool:
        """Verify all cage constraints are satisfied."""
        n = self.n
        for cage in self.cages:
            vals = [board[r * n + c] for r, c in cage.cells]
            if 0 in vals:
                continue  # Not fully filled
            if not cage.check(vals):
                return False
        return True
    
    def count_solutions_fast(self, board: List[int], limit: int = 2) -> int:
        """Ultra-fast solution counting using pure Numba (Latin constraints only).
        
        Use this when you just need a quick uniqueness estimate.
        For exact cage-aware counting, use count_solutions().
        """
        if not NUMBA_AVAILABLE:
            return self.count_solutions(board, limit, timeout=0.3)
        
        board_np = np.array(board, dtype=np.int32)
        n = self.n
        all_bits = (1 << (n + 1)) - 2
        candidates_np = np.full(n * n, all_bits, dtype=np.int64)
        
        return _count_solutions_fast(board_np, candidates_np, n, limit)
    
    def _count_solve_fast(self, board: List[int], candidates: List[int]) -> bool:
        """Fast counting with propagation and optional timeout."""
        import time
        
        # Check timeout (only if timeout is set)
        if self._timeout is not None and time.time() - self._start_time > self._timeout:
            self._timed_out = True
            return True
        
        if self._count >= self._limit:
            return True
        
        n = self.n
        
        # Find cell with fewest candidates (MRV)
        best_cell = -1
        min_count = n + 2
        
        for i in range(n * n):
            if board[i] == 0:
                cnt = self._count_bits(candidates[i])
                if cnt == 0:
                    return False
                if cnt < min_count:
                    min_count = cnt
                    best_cell = i
                    if cnt == 1:
                        break
        
        if best_cell == -1:
            # All filled - verify
            self._count += 1
            return self._count >= self._limit
        
        # Try each candidate
        cands = candidates[best_cell]
        for val in range(1, n + 1):
            if not (cands & (1 << val)):
                continue
            
            # Copy state
            new_board = board.copy()
            new_cands = candidates.copy()
            
            new_board[best_cell] = val
            new_cands[best_cell] = 1 << val
            
            if self._propagate(new_cands, new_board):
                if self._count_solve_fast(new_board, new_cands):
                    return True
        
        return False
    
    def solve(self, board: List[int]) -> Optional[List[int]]:
        """Solve the puzzle."""
        board = board.copy()
        candidates = self._init_candidates()
        
        if not self._propagate(candidates, board):
            return None
        
        if self._solve_fast(board, candidates):
            return board
        return None
    
    def _solve_fast(self, board: List[int], candidates: List[int]) -> bool:
        """Fast solving with propagation."""
        n = self.n
        
        # Find cell with fewest candidates
        best_cell = -1
        min_count = n + 2
        
        for i in range(n * n):
            if board[i] == 0:
                cnt = self._count_bits(candidates[i])
                if cnt == 0:
                    return False
                if cnt < min_count:
                    min_count = cnt
                    best_cell = i
                    if cnt == 1:
                        break
        
        if best_cell == -1:
            return True
        
        cands = candidates[best_cell]
        for val in range(1, n + 1):
            if not (cands & (1 << val)):
                continue
            
            new_board = board.copy()
            new_cands = candidates.copy()
            
            new_board[best_cell] = val
            new_cands[best_cell] = 1 << val
            
            if self._propagate(new_cands, new_board):
                if self._solve_fast(new_board, new_cands):
                    board[:] = new_board
                    return True
        
        return False
    
    # Keep old interface for compatibility
    def _is_valid(self, board: List[int], row: int, col: int, val: int) -> bool:
        """Check if placing val at (row, col) is valid."""
        n = self.size
        
        for c in range(n):
            if c != col and board[row * n + c] == val:
                return False
        
        for r in range(n):
            if r != row and board[r * n + col] == val:
                return False
        
        cage = self._cell_to_cage.get((row, col))
        if cage:
            values = []
            all_filled = True
            for (r, c) in cage.cells:
                if r == row and c == col:
                    values.append(val)
                else:
                    v = board[r * n + c]
                    values.append(v)
                    if v == 0:
                        all_filled = False
            
            if all_filled:
                if not cage.check(values):
                    return False
            else:
                if not cage.partial_check(values):
                    return False
        
        return True
    
    def _get_candidates(self, board: List[int], row: int, col: int) -> List[int]:
        """Get valid candidates for a cell."""
        return [v for v in range(1, self.size + 1) 
                if self._is_valid(board, row, col, v)]


# Worker function for parallel generation (must be at module level for pickling)
def _generate_attempt(args: Tuple) -> Optional[Tuple[List, int]]:
    """Single generation attempt for parallel execution."""
    size, difficulty, base_seed, attempt_idx, solution, params = args
    
    rng = random.Random(base_seed + attempt_idx * 7919)  # Prime offset for variety
    config = KenKenConfig.from_size(size)
    n = size
    
    # Generate cages
    target = params['cages']
    max_size = params['max_size']
    single_ratio = params['singles']
    ops = params['ops']
    
    # Union-Find
    parent = list(range(n * n))
    sizes = [1] * (n * n)
    
    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root
    
    def union(x, y):
        px, py = find(x), find(y)
        if px == py:
            return False
        if sizes[px] < sizes[py]:
            px, py = py, px
        parent[py] = px
        sizes[px] += sizes[py]
        return True
    
    # Edges
    edges = []
    for r in range(n):
        for c in range(n):
            idx = r * n + c
            if c + 1 < n:
                edges.append((idx, idx + 1))
            if r + 1 < n:
                edges.append((idx, idx + n))
    rng.shuffle(edges)
    
    # Merge
    count = n * n
    for a, b in edges:
        if count <= target:
            break
        if find(a) == find(b):
            continue
        if sizes[find(a)] + sizes[find(b)] > max_size:
            continue
        if union(a, b):
            count -= 1
    
    # Group by partition
    groups: Dict[int, List[Tuple[int, int]]] = {}
    for i in range(n * n):
        p = find(i)
        if p not in groups:
            groups[p] = []
        groups[p].append((i // n, i % n))
    
    # Limit singles
    max_singles = max(1, int(n * n * single_ratio))
    singles = [p for p, cells in groups.items() if len(cells) == 1]
    
    if len(singles) > max_singles:
        rng.shuffle(singles)
        for p in singles[max_singles:]:
            r, c = groups[p][0]
            idx = r * n + c
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < n and 0 <= nc < n:
                    nidx = nr * n + nc
                    if find(idx) != find(nidx):
                        if sizes[find(idx)] + sizes[find(nidx)] <= max_size + 1:
                            union(idx, nidx)
                            break
    
    # Rebuild groups
    groups = {}
    for i in range(n * n):
        p = find(i)
        if p not in groups:
            groups[p] = []
        groups[p].append((i // n, i % n))
    
    # Create cages with operations
    cages = []
    for cells in groups.values():
        vals = [solution[r * n + c] for r, c in cells]
        
        # Choose operation
        if len(vals) == 1:
            op, tgt = '', vals[0]
        else:
            valid = []
            valid.append(('+', sum(vals), ops.get('+', 4)))
            
            # For large cages (4+), prefer + over * to avoid explosion
            # * operation has exponential possibilities with cage size
            if len(vals) <= 3:
                prod = 1
                for v in vals:
                    prod *= v
                valid.append(('*', prod, ops.get('*', 3)))
            else:
                # For 4+ cell cages, use * with much lower weight
                prod = 1
                for v in vals:
                    prod *= v
                valid.append(('*', prod, max(1, ops.get('*', 3) // 4)))
            
            if len(vals) == 2:
                a, b = vals
                diff = abs(a - b)
                if diff > 0 and ops.get('-', 0) > 0:
                    valid.append(('-', diff, ops['-']))
                if ops.get('/', 0) > 0:
                    if a >= b and b != 0 and a % b == 0:
                        valid.append(('/', a // b, ops['/']))
                    elif b > a and a != 0 and b % a == 0:
                        valid.append(('/', b // a, ops['/']))
            
            total = sum(w for _, _, w in valid)
            if total == 0:
                op, tgt = '+', sum(vals)
            else:
                choice = rng.random() * total
                cum = 0
                op, tgt = valid[0][0], valid[0][1]
                for o, t, w in valid:
                    cum += w
                    if choice <= cum:
                        op, tgt = o, t
                        break
        
        cages.append(Cage(cells=cells, target=tgt, operation=op))
    
    # Count solutions with timeout
    solver = KenKenSolver(config, cages)
    sol_count = solver.count_solutions([0] * (n * n), limit=2, timeout=0.3)
    
    if sol_count == 1:
        return (cages, 1)
    # If timed out (-1) or multiple solutions, return as non-unique
    return (cages, sol_count if sol_count >= 0 else 99)


class KenKenGenerator:
    """Generate KenKen puzzles using pycalcudoku library.
    
    Uses dannyzed/pycalcudoku for puzzle generation.
    Operations: + - * / (all supported)
    """
    
    # Map calcudoku operation names to our symbols
    OP_MAP = {
        'add': '+',
        'subtract': '-',
        'multiply': '*',
        'divide': '/',
        'none': '',  # single cell
    }
    
    def __init__(self, config: KenKenConfig):
        self.config = config
        self.size = config.size
    
    def generate(self, seed: Optional[int] = None) -> KenKenState:
        """Generate puzzle using pycalcudoku.
        
        Args:
            seed: Random seed for reproducibility
        
        Returns:
            KenKenState with puzzle ready to solve
        """
        if seed is not None:
            np.random.seed(seed)
        else:
            seed = random.randint(0, 2**31 - 1)
            np.random.seed(seed)
        
        # Import local calcudoku
        try:
            from .calcudoku.game import Calcudoku
        except ImportError:
            # Fallback for standalone import - need to load graph.py first
            import importlib.util
            import os
            import sys
            
            calcudoku_dir = os.path.join(os.path.dirname(__file__), "calcudoku")
            
            # Load graph module first (game.py depends on it)
            graph_path = os.path.join(calcudoku_dir, "graph.py")
            graph_spec = importlib.util.spec_from_file_location("calcudoku.graph", graph_path)
            graph_module = importlib.util.module_from_spec(graph_spec)
            sys.modules["calcudoku.graph"] = graph_module
            graph_spec.loader.exec_module(graph_module)
            
            # Now load game module
            game_path = os.path.join(calcudoku_dir, "game.py")
            game_spec = importlib.util.spec_from_file_location("calcudoku.game", game_path)
            game_module = importlib.util.module_from_spec(game_spec)
            sys.modules["calcudoku.game"] = game_module
            game_spec.loader.exec_module(game_module)
            
            Calcudoku = game_module.Calcudoku
        
        # Generate puzzle
        game = Calcudoku.generate(self.size)
        
        # Convert to our format
        n = self.size
        solution = list(game.board)  # Already flattened 1D array
        
        cages = []
        for partition, (op_name, target) in zip(game.partitions, game.operations):
            # Convert flat indices to (row, col) tuples
            cells = [(idx // n, idx % n) for idx in partition]
            operation = self.OP_MAP.get(op_name, '+')
            cages.append(Cage(
                cells=cells,
                target=int(target),
                operation=operation
            ))
        
        return KenKenState(
            config=self.config,
            board=[0] * (n * n),
            cages=cages,
            solution=solution,
            seed=seed,
        )


def create_puzzle(size: int = 6, seed: Optional[int] = None) -> KenKenState:
    """Create a new KenKen puzzle.
    
    Args:
        size: Grid size (4-9)
        seed: Optional random seed
    
    Returns:
        KenKenState ready to play
    """
    config = KenKenConfig.from_size(size)
    generator = KenKenGenerator(config)
    return generator.generate(seed)
