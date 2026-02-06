"""
Slitherlink Engine - Puzzle loading, validation, and solving

Rules:
- Draw a single closed loop on grid edges
- Numbers indicate how many of the 4 surrounding edges are part of the loop
- Loop cannot branch or cross itself
- Every vertex has degree 0 or 2
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Set, Dict, FrozenSet


@dataclass
class SlitherlinkPuzzle:
    """Represents a Slitherlink puzzle."""
    width: int  # Number of cells horizontally
    height: int  # Number of cells vertically
    clues: List[List[Optional[int]]]  # None = no clue, 0-3 = clue
    solution_h: Optional[List[List[bool]]] = None  # Horizontal edges solution
    solution_v: Optional[List[List[bool]]] = None  # Vertical edges solution
    
    @property
    def h_edges_shape(self) -> Tuple[int, int]:
        """Horizontal edges: (height+1) rows, width columns."""
        return (self.height + 1, self.width)
    
    @property
    def v_edges_shape(self) -> Tuple[int, int]:
        """Vertical edges: height rows, (width+1) columns."""
        return (self.height, self.width + 1)


@dataclass 
class SlitherlinkState:
    """Game state for a Slitherlink puzzle."""
    puzzle: SlitherlinkPuzzle
    h_edges: List[List[int]]  # 0=unknown, 1=line, -1=X (no line)
    v_edges: List[List[int]]  # 0=unknown, 1=line, -1=X (no line)
    
    @classmethod
    def from_puzzle(cls, puzzle: SlitherlinkPuzzle) -> "SlitherlinkState":
        """Create initial state from puzzle."""
        h_rows, h_cols = puzzle.h_edges_shape
        v_rows, v_cols = puzzle.v_edges_shape
        return cls(
            puzzle=puzzle,
            h_edges=[[0] * h_cols for _ in range(h_rows)],
            v_edges=[[0] * v_cols for _ in range(v_rows)],
        )
    
    def toggle_h_edge(self, row: int, col: int) -> None:
        """Toggle horizontal edge: unknown -> line -> X -> unknown."""
        current = self.h_edges[row][col]
        self.h_edges[row][col] = {0: 1, 1: -1, -1: 0}[current]
    
    def toggle_v_edge(self, row: int, col: int) -> None:
        """Toggle vertical edge."""
        current = self.v_edges[row][col]
        self.v_edges[row][col] = {0: 1, 1: -1, -1: 0}[current]
    
    def set_h_edge(self, row: int, col: int, value: int) -> None:
        """Set horizontal edge to specific value."""
        self.h_edges[row][col] = value
    
    def set_v_edge(self, row: int, col: int, value: int) -> None:
        """Set vertical edge to specific value."""
        self.v_edges[row][col] = value
    
    def clear(self) -> None:
        """Clear all edges."""
        for row in self.h_edges:
            for i in range(len(row)):
                row[i] = 0
        for row in self.v_edges:
            for i in range(len(row)):
                row[i] = 0
    
    def get_edges_around_cell(self, row: int, col: int) -> Tuple[int, int, int, int]:
        """Get edge values around a cell (top, right, bottom, left)."""
        top = self.h_edges[row][col]
        bottom = self.h_edges[row + 1][col]
        left = self.v_edges[row][col]
        right = self.v_edges[row][col + 1]
        return (top, right, bottom, left)
    
    def count_lines_around_cell(self, row: int, col: int) -> int:
        """Count lines (value=1) around a cell."""
        edges = self.get_edges_around_cell(row, col)
        return sum(1 for e in edges if e == 1)
    
    def get_vertex_degree(self, row: int, col: int) -> int:
        """Get degree (number of lines) at vertex (row, col).
        Vertex (row, col) is at the top-left corner of cell (row, col).
        """
        degree = 0
        # Top horizontal edge (if exists)
        if row > 0 and col < self.puzzle.width:
            if self.h_edges[row][col] == 1:
                degree += 1
        # Bottom horizontal edge
        if row < self.puzzle.height + 1 and col < self.puzzle.width:
            if row < len(self.h_edges) and self.h_edges[row][col] == 1:
                degree += 1
        # Left vertical edge
        if col > 0 and row < self.puzzle.height:
            if self.v_edges[row][col] == 1:
                degree += 1
        # Right vertical edge
        if col < self.puzzle.width + 1 and row < self.puzzle.height:
            if row < len(self.v_edges) and col < len(self.v_edges[0]) and self.v_edges[row][col] == 1:
                degree += 1
        return degree
    
    def is_valid(self) -> Tuple[bool, str]:
        """Check if current state is valid (not necessarily complete).
        Returns (is_valid, error_message).
        """
        puzzle = self.puzzle
        
        # Check clue constraints
        for r in range(puzzle.height):
            for c in range(puzzle.width):
                clue = puzzle.clues[r][c]
                if clue is not None:
                    count = self.count_lines_around_cell(r, c)
                    # Count X's around cell
                    edges = self.get_edges_around_cell(r, c)
                    x_count = sum(1 for e in edges if e == -1)
                    remaining = 4 - x_count
                    
                    if count > clue:
                        return False, f"Cell ({r},{c}) has {count} lines but needs {clue}"
                    if remaining < clue:
                        return False, f"Cell ({r},{c}) cannot reach {clue} lines"
        
        # Check vertex degrees (must be 0 or 2 for lines, ignoring unknowns)
        for r in range(puzzle.height + 1):
            for c in range(puzzle.width + 1):
                degree = self._count_lines_at_vertex(r, c)
                if degree > 2:
                    return False, f"Vertex ({r},{c}) has degree {degree} > 2"
        
        return True, ""
    
    def _count_lines_at_vertex(self, vr: int, vc: int) -> int:
        """Count lines at vertex (vr, vc)."""
        count = 0
        # Edges connected to this vertex:
        # - Horizontal edge to the left: h_edges[vr][vc-1] if vc > 0
        # - Horizontal edge to the right: h_edges[vr][vc] if vc < width
        # - Vertical edge above: v_edges[vr-1][vc] if vr > 0
        # - Vertical edge below: v_edges[vr][vc] if vr < height
        
        if vc > 0 and vr < len(self.h_edges):
            if self.h_edges[vr][vc - 1] == 1:
                count += 1
        if vc < self.puzzle.width and vr < len(self.h_edges):
            if self.h_edges[vr][vc] == 1:
                count += 1
        if vr > 0 and vc < len(self.v_edges[0]):
            if self.v_edges[vr - 1][vc] == 1:
                count += 1
        if vr < self.puzzle.height and vc < len(self.v_edges[0]):
            if self.v_edges[vr][vc] == 1:
                count += 1
        
        return count
    
    def is_complete(self) -> Tuple[bool, str]:
        """Check if solution is complete and correct."""
        puzzle = self.puzzle
        
        # First check basic validity
        valid, msg = self.is_valid()
        if not valid:
            return False, msg
        
        # Check all clues are satisfied exactly
        for r in range(puzzle.height):
            for c in range(puzzle.width):
                clue = puzzle.clues[r][c]
                if clue is not None:
                    count = self.count_lines_around_cell(r, c)
                    if count != clue:
                        return False, f"Cell ({r},{c}) needs exactly {clue} lines"
        
        # Check all vertices have degree 0 or 2
        for vr in range(puzzle.height + 1):
            for vc in range(puzzle.width + 1):
                degree = self._count_lines_at_vertex(vr, vc)
                if degree != 0 and degree != 2:
                    return False, f"Vertex ({vr},{vc}) has degree {degree}"
        
        # Check exactly one loop (no multiple components)
        lines = self._collect_lines()
        if not lines:
            return False, "No loop drawn"
        
        if not self._is_single_loop(lines):
            return False, "Multiple loops or open path"
        
        return True, "Solved!"
    
    def _collect_lines(self) -> Set[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """Collect all drawn lines as set of (vertex1, vertex2) pairs."""
        lines = set()
        
        # Horizontal edges
        for r in range(len(self.h_edges)):
            for c in range(len(self.h_edges[0])):
                if self.h_edges[r][c] == 1:
                    v1 = (r, c)
                    v2 = (r, c + 1)
                    lines.add((v1, v2))
        
        # Vertical edges  
        for r in range(len(self.v_edges)):
            for c in range(len(self.v_edges[0])):
                if self.v_edges[r][c] == 1:
                    v1 = (r, c)
                    v2 = (r + 1, c)
                    lines.add((v1, v2))
        
        return lines
    
    def _is_single_loop(self, lines: Set[Tuple[Tuple[int, int], Tuple[int, int]]]) -> bool:
        """Check if lines form exactly one closed loop."""
        if not lines:
            return False
        
        # Build adjacency list
        adj: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        for v1, v2 in lines:
            adj.setdefault(v1, []).append(v2)
            adj.setdefault(v2, []).append(v1)
        
        # Every vertex must have degree 2
        for v, neighbors in adj.items():
            if len(neighbors) != 2:
                return False
        
        # DFS to check single component
        start = next(iter(adj.keys()))
        visited = set()
        stack = [start]
        
        while stack:
            v = stack.pop()
            if v in visited:
                continue
            visited.add(v)
            for neighbor in adj[v]:
                if neighbor not in visited:
                    stack.append(neighbor)
        
        return len(visited) == len(adj)
    
    def apply_solution(self) -> bool:
        """Apply puzzle's solution to state. Returns False if no solution."""
        if self.puzzle.solution_h is None or self.puzzle.solution_v is None:
            return False
        
        for r in range(len(self.h_edges)):
            for c in range(len(self.h_edges[0])):
                self.h_edges[r][c] = 1 if self.puzzle.solution_h[r][c] else 0
        
        for r in range(len(self.v_edges)):
            for c in range(len(self.v_edges[0])):
                self.v_edges[r][c] = 1 if self.puzzle.solution_v[r][c] else 0
        
        return True


def parse_slk(content: str) -> SlitherlinkPuzzle:
    """Parse .slk format puzzle file."""
    # Filter comments and clean lines
    raw_lines = content.strip().split('\n')
    lines = []
    for l in raw_lines:
        # Remove inline comments
        if '#' in l:
            l = l[:l.index('#')]
        l = l.rstrip()
        lines.append(l)
    
    # Find first non-empty line (dimensions)
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    
    dims = lines[idx].split()
    height, width = int(dims[0]), int(dims[1])
    idx += 1
    
    # Skip empty lines before clue data
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    
    # Parse clues
    clues: List[List[Optional[int]]] = []
    for _ in range(height):
        line = lines[idx] if idx < len(lines) else ''
        idx += 1
        row = []
        for j in range(width):
            if j < len(line):
                c = line[j]
                if c.isdigit():
                    row.append(int(c))
                else:
                    row.append(None)
            else:
                row.append(None)
        clues.append(row)
    
    # Parse solution if present (skip empty separator line first)
    solution_h = None
    solution_v = None
    
    # Skip to empty line separator before solution
    while idx < len(lines) and lines[idx].strip():
        idx += 1
    
    # Skip the empty line
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    
    # Check if there's solution data
    if idx < len(lines) and lines[idx].strip():
        # Parse horizontal edges (height+1 rows)
        solution_h = []
        for _ in range(height + 1):
            line = lines[idx] if idx < len(lines) else ''
            if line.strip() and not line.strip().startswith('#'):
                row = []
                for j in range(width):
                    if j < len(line):
                        row.append(line[j] == '-')
                    else:
                        row.append(False)
                solution_h.append(row)
            idx += 1
        
        # Skip separator before vertical edges
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        
        # Parse vertical edges (height rows)
        if idx < len(lines):
            solution_v = []
            for _ in range(height):
                line = lines[idx] if idx < len(lines) else ''
                if line.strip():
                    row = []
                    for j in range(width + 1):
                        if j < len(line):
                            row.append(line[j] == '-')
                        else:
                            row.append(False)
                    solution_v.append(row)
                idx += 1
    
    return SlitherlinkPuzzle(
        width=width,
        height=height,
        clues=clues,
        solution_h=solution_h,
        solution_v=solution_v,
    )


def load_puzzle_from_file(path: Path) -> SlitherlinkPuzzle:
    """Load puzzle from .slk file."""
    return parse_slk(path.read_text(encoding='utf-8'))


def load_puzzle_from_json(path: Path) -> SlitherlinkPuzzle:
    """Load puzzle from JSON format."""
    data = json.loads(path.read_text(encoding='utf-8'))
    return SlitherlinkPuzzle(
        width=data['width'],
        height=data['height'],
        clues=data['clues'],
        solution_h=data.get('solution_h'),
        solution_v=data.get('solution_v'),
    )


def save_puzzle_to_json(puzzle: SlitherlinkPuzzle, path: Path) -> None:
    """Save puzzle to JSON format."""
    data = {
        'width': puzzle.width,
        'height': puzzle.height,
        'clues': puzzle.clues,
        'solution_h': puzzle.solution_h,
        'solution_v': puzzle.solution_v,
    }
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def get_templates_dir() -> Path:
    """Get templates directory path."""
    return Path(__file__).parent / 'templates'


def list_available_puzzles() -> List[Tuple[str, int, int, str]]:
    """List available puzzles as (filename, width, height, difficulty)."""
    templates = get_templates_dir()
    puzzles = []
    
    for f in templates.glob('*.json'):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            puzzles.append((
                f.stem,
                data.get('width', 0),
                data.get('height', 0),
                data.get('difficulty', 'medium'),
            ))
        except Exception:
            pass
    
    for f in templates.glob('*.slk'):
        try:
            puzzle = load_puzzle_from_file(f)
            puzzles.append((f.stem, puzzle.width, puzzle.height, 'medium'))
        except Exception:
            pass
    
    return sorted(puzzles, key=lambda x: (x[1] * x[2], x[0]))


def load_random_puzzle(
    size: Optional[int] = None,
    difficulty: Optional[str] = None
) -> Optional[SlitherlinkState]:
    """Load a random puzzle matching criteria."""
    templates = get_templates_dir()
    
    candidates = []
    
    for f in templates.glob('*.json'):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            w, h = data.get('width', 0), data.get('height', 0)
            d = data.get('difficulty', 'medium')
            
            if size and max(w, h) != size:
                continue
            if difficulty and d != difficulty:
                continue
            
            candidates.append(('json', f))
        except Exception:
            pass
    
    for f in templates.glob('*.slk'):
        try:
            puzzle = load_puzzle_from_file(f)
            if size and max(puzzle.width, puzzle.height) != size:
                continue
            candidates.append(('slk', f))
        except Exception:
            pass
    
    if not candidates:
        return None
    
    fmt, path = random.choice(candidates)
    if fmt == 'json':
        puzzle = load_puzzle_from_json(path)
    else:
        puzzle = load_puzzle_from_file(path)
    
    return SlitherlinkState.from_puzzle(puzzle)


def create_puzzle(
    size: int = 10,
    difficulty: str = 'medium'
) -> Optional[SlitherlinkState]:
    """Create a puzzle using real-time generation.
    
    Args:
        size: Grid size (both width and height)
        difficulty: 'easy', 'medium', or 'hard' - affects clue density
    
    Returns:
        SlitherlinkState ready to play
    """
    # Difficulty affects minimum clue ratio
    clue_ratios = {
        'easy': 0.5,      # More clues = easier
        'medium': 0.35,
        'hard': 0.2,      # Fewer clues = harder
    }
    min_clues_ratio = clue_ratios.get(difficulty, 0.35)
    
    # Try generating with random seed.
    puzzle = generate_puzzle(size, size, seed=None, min_clues_ratio=min_clues_ratio)
    if puzzle is not None:
        return SlitherlinkState.from_puzzle(puzzle)

    # Runtime fallback for packaged environments where SAT backend may be unavailable.
    # If templates are bundled, load a matching puzzle instead of failing hard.
    return load_random_puzzle(size=size, difficulty=difficulty)


# Simple constraint propagation solver for hints
class SlitherlinkSolver:
    """Simple constraint propagation solver."""
    
    def __init__(self, state: SlitherlinkState):
        self.state = state
        self.puzzle = state.puzzle
    
    def propagate(self) -> bool:
        """Apply constraint propagation. Returns True if progress made."""
        changed = True
        any_change = False
        
        while changed:
            changed = False
            
            # Rule 1: If a clue is satisfied, mark remaining edges as X
            for r in range(self.puzzle.height):
                for c in range(self.puzzle.width):
                    clue = self.puzzle.clues[r][c]
                    if clue is None:
                        continue
                    
                    lines = self.state.count_lines_around_cell(r, c)
                    edges = self.state.get_edges_around_cell(r, c)
                    unknowns = sum(1 for e in edges if e == 0)
                    
                    if lines == clue and unknowns > 0:
                        # Mark remaining as X
                        if edges[0] == 0:
                            self.state.h_edges[r][c] = -1
                            changed = True
                        if edges[1] == 0:
                            self.state.v_edges[r][c + 1] = -1
                            changed = True
                        if edges[2] == 0:
                            self.state.h_edges[r + 1][c] = -1
                            changed = True
                        if edges[3] == 0:
                            self.state.v_edges[r][c] = -1
                            changed = True
                    
                    # Rule 2: If we need all remaining edges
                    x_count = sum(1 for e in edges if e == -1)
                    remaining_slots = 4 - x_count
                    needed = clue - lines
                    
                    if needed == remaining_slots and unknowns > 0:
                        if edges[0] == 0:
                            self.state.h_edges[r][c] = 1
                            changed = True
                        if edges[1] == 0:
                            self.state.v_edges[r][c + 1] = 1
                            changed = True
                        if edges[2] == 0:
                            self.state.h_edges[r + 1][c] = 1
                            changed = True
                        if edges[3] == 0:
                            self.state.v_edges[r][c] = 1
                            changed = True
            
            # Rule 3: Vertex degree constraints
            for vr in range(self.puzzle.height + 1):
                for vc in range(self.puzzle.width + 1):
                    lines_at_v, unknowns_at_v, edges_info = self._get_vertex_info(vr, vc)
                    
                    # If 2 lines already, mark others as X
                    if lines_at_v == 2:
                        for edge_type, er, ec, val in edges_info:
                            if val == 0:
                                if edge_type == 'h':
                                    self.state.h_edges[er][ec] = -1
                                else:
                                    self.state.v_edges[er][ec] = -1
                                changed = True
                    
                    # If 1 line and only 1 unknown, that unknown must be line
                    if lines_at_v == 1 and unknowns_at_v == 1:
                        for edge_type, er, ec, val in edges_info:
                            if val == 0:
                                if edge_type == 'h':
                                    self.state.h_edges[er][ec] = 1
                                else:
                                    self.state.v_edges[er][ec] = 1
                                changed = True
            
            if changed:
                any_change = True
        
        return any_change
    
    def _get_vertex_info(self, vr: int, vc: int):
        """Get info about edges at vertex."""
        lines = 0
        unknowns = 0
        edges = []
        
        # Left horizontal
        if vc > 0 and vr < len(self.state.h_edges):
            val = self.state.h_edges[vr][vc - 1]
            edges.append(('h', vr, vc - 1, val))
            if val == 1:
                lines += 1
            elif val == 0:
                unknowns += 1
        
        # Right horizontal
        if vc < self.puzzle.width and vr < len(self.state.h_edges):
            val = self.state.h_edges[vr][vc]
            edges.append(('h', vr, vc, val))
            if val == 1:
                lines += 1
            elif val == 0:
                unknowns += 1
        
        # Top vertical
        if vr > 0 and vc < len(self.state.v_edges[0]) and vr - 1 < len(self.state.v_edges):
            val = self.state.v_edges[vr - 1][vc]
            edges.append(('v', vr - 1, vc, val))
            if val == 1:
                lines += 1
            elif val == 0:
                unknowns += 1
        
        # Bottom vertical
        if vr < self.puzzle.height and vc < len(self.state.v_edges[0]):
            val = self.state.v_edges[vr][vc]
            edges.append(('v', vr, vc, val))
            if val == 1:
                lines += 1
            elif val == 0:
                unknowns += 1
        
        return lines, unknowns, edges
    
    def get_hint(self) -> Optional[Tuple[str, int, int, int]]:
        """Get a hint (edge_type, row, col, value). Returns None if solved/stuck."""
        # Make a copy and try to propagate
        import copy
        test_state = copy.deepcopy(self.state)
        test_solver = SlitherlinkSolver(test_state)
        test_solver.propagate()
        
        # Find a difference from propagation
        for r in range(len(self.state.h_edges)):
            for c in range(len(self.state.h_edges[0])):
                if self.state.h_edges[r][c] == 0 and test_state.h_edges[r][c] != 0:
                    return ('h', r, c, test_state.h_edges[r][c])
        
        for r in range(len(self.state.v_edges)):
            for c in range(len(self.state.v_edges[0])):
                if self.state.v_edges[r][c] == 0 and test_state.v_edges[r][c] != 0:
                    return ('v', r, c, test_state.v_edges[r][c])
        
        # If propagation didn't help, try full solve and compare
        solution = self.solve()
        if solution:
            for r in range(len(self.state.h_edges)):
                for c in range(len(self.state.h_edges[0])):
                    if self.state.h_edges[r][c] == 0:
                        return ('h', r, c, 1 if solution.h_edges[r][c] == 1 else -1)
            for r in range(len(self.state.v_edges)):
                for c in range(len(self.state.v_edges[0])):
                    if self.state.v_edges[r][c] == 0:
                        return ('v', r, c, 1 if solution.v_edges[r][c] == 1 else -1)
        
        return None
    
    def solve(self) -> Optional[SlitherlinkState]:
        """Fully solve using SAT solver. Returns solved state or None."""
        return solve_with_sat(self.state)


def solve_with_sat(state: SlitherlinkState) -> Optional[SlitherlinkState]:
    """Solve Slitherlink using SAT solver with iterative loop detection."""
    import copy
    from itertools import combinations
    
    try:
        from pysat.solvers import Solver
        from pysat.card import CardEnc, EncType
    except ImportError:
        return None  # SAT solver not available
    
    puzzle = state.puzzle
    h_rows, h_cols = puzzle.h_edges_shape
    v_rows, v_cols = puzzle.v_edges_shape
    
    # Create variable mapping
    # h_edge[r][c] -> variable 1 + r*h_cols + c
    # v_edge[r][c] -> variable 1 + h_rows*h_cols + r*v_cols + c
    
    def h_var(r: int, c: int) -> int:
        return 1 + r * h_cols + c
    
    def v_var(r: int, c: int) -> int:
        return 1 + h_rows * h_cols + r * v_cols + c
    
    max_var = h_rows * h_cols + v_rows * v_cols
    
    # Get edges at a vertex
    def edges_at_vertex(vr: int, vc: int) -> List[int]:
        edges = []
        # Left horizontal
        if vc > 0 and vr < h_rows:
            edges.append(h_var(vr, vc - 1))
        # Right horizontal
        if vc < puzzle.width and vr < h_rows:
            edges.append(h_var(vr, vc))
        # Top vertical
        if vr > 0 and vc < v_cols:
            edges.append(v_var(vr - 1, vc))
        # Bottom vertical
        if vr < puzzle.height and vc < v_cols:
            edges.append(v_var(vr, vc))
        return edges
    
    # Get edges around a cell
    def edges_around_cell(r: int, c: int) -> List[int]:
        return [
            h_var(r, c),      # top
            h_var(r + 1, c),  # bottom
            v_var(r, c),      # left
            v_var(r, c + 1),  # right
        ]
    
    # Build clauses
    clauses = []
    
    # Clue constraints: exactly N edges around cell
    for r in range(puzzle.height):
        for c in range(puzzle.width):
            clue = puzzle.clues[r][c]
            if clue is not None:
                cell_edges = edges_around_cell(r, c)
                # Use cardinality encoding for exactly N
                enc = CardEnc.equals(lits=cell_edges, bound=clue, top_id=max_var, encoding=EncType.seqcounter)
                max_var = max(max_var, max(abs(l) for cl in enc.clauses for l in cl) if enc.clauses else max_var)
                clauses.extend(enc.clauses)
    
    # Vertex constraints: degree 0 or 2 at each vertex
    for vr in range(puzzle.height + 1):
        for vc in range(puzzle.width + 1):
            v_edges = edges_at_vertex(vr, vc)
            if len(v_edges) < 2:
                # Boundary vertex with <2 edges: must be degree 0
                for e in v_edges:
                    clauses.append([-e])
            else:
                # Degree can be 0, 2 (not 1, 3, 4)
                # Forbid degree 1 and 3+
                
                # Forbid exactly 1: at least one pair must both be present, or none
                # For each single edge, if it's on, at least one other must be on
                for e in v_edges:
                    others = [x for x in v_edges if x != e]
                    # e -> (o1 OR o2 OR ...)
                    clauses.append([-e] + others)
                
                # Forbid degree 3+: each triple cannot all be true
                for triple in combinations(v_edges, 3):
                    clauses.append([-triple[0], -triple[1], -triple[2]])
    
    # Add constraints from current state (fixed edges)
    for r in range(len(state.h_edges)):
        for c in range(len(state.h_edges[0])):
            if state.h_edges[r][c] == 1:
                clauses.append([h_var(r, c)])
            elif state.h_edges[r][c] == -1:
                clauses.append([-h_var(r, c)])
    
    for r in range(len(state.v_edges)):
        for c in range(len(state.v_edges[0])):
            if state.v_edges[r][c] == 1:
                clauses.append([v_var(r, c)])
            elif state.v_edges[r][c] == -1:
                clauses.append([-v_var(r, c)])
    
    # Iteratively solve and add loop-breaking constraints
    max_iterations = 100
    for iteration in range(max_iterations):
        solver = Solver(name='g3')
        for cl in clauses:
            solver.add_clause(cl)
        
        if not solver.solve():
            solver.delete()
            return None
        
        model = solver.get_model()
        solver.delete()
        
        # Build set of true variables for easy lookup
        true_vars = set(v for v in model if v > 0)
        
        # Extract solution
        result = copy.deepcopy(state)
        for r in range(len(result.h_edges)):
            for c in range(len(result.h_edges[0])):
                var = h_var(r, c)
                result.h_edges[r][c] = 1 if var in true_vars else 0
        
        for r in range(len(result.v_edges)):
            for c in range(len(result.v_edges[0])):
                var = v_var(r, c)
                result.v_edges[r][c] = 1 if var in true_vars else 0
        
        # Check if it's a single loop
        complete, msg = result.is_complete()
        if complete:
            return result
        
        # Find components and add constraint to break multiple loops
        lines = result._collect_lines()
        if not lines:
            return None
        
        components = _find_components(lines)
        if len(components) == 1:
            # Single component but not complete (maybe empty areas?)
            # This shouldn't happen if is_complete works correctly
            return result
        
        # Add constraint: at least one edge between components must change
        # Pick the smaller component and require at least one of its edges to be different
        smallest = min(components, key=lambda c: len(c))
        blocking = []
        for v1, v2 in smallest:
            # Find the edge variable
            if v1[0] == v2[0]:  # horizontal
                r = v1[0]
                c = min(v1[1], v2[1])
                blocking.append(-h_var(r, c))
            else:  # vertical
                c = v1[1]
                r = min(v1[0], v2[0])
                blocking.append(-v_var(r, c))
        
        clauses.append(blocking)
    
    return None


def _find_components(lines: Set[Tuple[Tuple[int, int], Tuple[int, int]]]) -> List[Set]:
    """Find connected components in a set of edges."""
    if not lines:
        return []
    
    # Build adjacency
    adj: Dict[Tuple[int, int], Set[Tuple[Tuple[int, int], Tuple[int, int]]]] = {}
    for v1, v2 in lines:
        adj.setdefault(v1, set()).add((v1, v2))
        adj.setdefault(v2, set()).add((v1, v2))
    
    visited_edges = set()
    components = []
    
    for start_edge in lines:
        if start_edge in visited_edges:
            continue
        
        component = set()
        stack = [start_edge]
        
        while stack:
            edge = stack.pop()
            if edge in visited_edges:
                continue
            visited_edges.add(edge)
            component.add(edge)
            
            v1, v2 = edge
            for neighbor_edge in adj.get(v1, set()) | adj.get(v2, set()):
                if neighbor_edge not in visited_edges:
                    stack.append(neighbor_edge)
        
        if component:
            components.append(component)
    
    return components


# =============================================================================
# PUZZLE GENERATOR - Real-time generation without templates
# =============================================================================

def _generate_perimeter_loop(width: int, height: int) -> Tuple[List[List[bool]], List[List[bool]]]:
    """DEPRECATED - not used anymore, complex loops are always generated."""
    raise NotImplementedError("Use generate_random_loop instead")


def _calculate_loop_complexity(solution_h: List[List[bool]], solution_v: List[List[bool]], 
                                width: int, height: int) -> Tuple[int, int, bool]:
    """Calculate loop complexity metrics.
    
    Returns (total_edges, interior_edges, passes_center)
    - total_edges: Total number of edges in the loop
    - interior_edges: Edges not on the perimeter
    - passes_center: Whether loop passes through center region
    """
    h_rows, h_cols = height + 1, width
    v_rows, v_cols = height, width + 1
    
    total_edges = 0
    interior_edges = 0
    
    # Count horizontal edges
    for r in range(h_rows):
        for c in range(h_cols):
            if solution_h[r][c]:
                total_edges += 1
                # Interior if not on top or bottom row
                if r > 0 and r < height:
                    interior_edges += 1
    
    # Count vertical edges
    for r in range(v_rows):
        for c in range(v_cols):
            if solution_v[r][c]:
                total_edges += 1
                # Interior if not on left or right column
                if c > 0 and c < width:
                    interior_edges += 1
    
    # Check if loop passes through center region (middle 50%)
    center_r_min = height // 4
    center_r_max = height - height // 4
    center_c_min = width // 4
    center_c_max = width - width // 4
    
    passes_center = False
    for r in range(center_r_min, center_r_max + 1):
        for c in range(center_c_min, center_c_max):
            if solution_h[r][c]:
                passes_center = True
                break
        if passes_center:
            break
    
    if not passes_center:
        for r in range(center_r_min, center_r_max):
            for c in range(center_c_min, center_c_max + 1):
                if solution_v[r][c]:
                    passes_center = True
                    break
            if passes_center:
                break
    
    return total_edges, interior_edges, passes_center


def generate_random_loop(width: int, height: int, seed: Optional[int] = None) -> Optional[Tuple[List[List[bool]], List[List[bool]]]]:
    """Generate a random valid closed loop on a grid.
    
    Creates complex, interesting loops that:
    - Pass through the center of the grid
    - Have significant interior complexity (not just perimeter)
    - Scale complexity with grid size
    
    Returns (solution_h, solution_v) where each is a 2D list of bools indicating
    whether that edge is part of the loop.
    """
    from itertools import combinations
    
    if seed is not None:
        random.seed(seed)
    
    h_rows, h_cols = height + 1, width
    v_rows, v_cols = height, width + 1
    
    try:
        from pysat.solvers import Solver
    except ImportError:
        return None
    
    def h_var(r: int, c: int) -> int:
        return 1 + r * h_cols + c
    
    def v_var(r: int, c: int) -> int:
        return 1 + h_rows * h_cols + r * v_cols + c
    
    max_var = h_rows * h_cols + v_rows * v_cols
    
    def edges_at_vertex(vr: int, vc: int) -> List[int]:
        edges = []
        if vc > 0 and vr < h_rows:
            edges.append(h_var(vr, vc - 1))
        if vc < width and vr < h_rows:
            edges.append(h_var(vr, vc))
        if vr > 0 and vc < v_cols:
            edges.append(v_var(vr - 1, vc))
        if vr < height and vc < v_cols:
            edges.append(v_var(vr, vc))
        return edges
    
    def edges_around_cell(cr: int, cc: int) -> List[int]:
        """Get the 4 edges around a cell (cr, cc)."""
        return [
            h_var(cr, cc),      # top
            h_var(cr + 1, cc),  # bottom
            v_var(cr, cc),      # left
            v_var(cr, cc + 1),  # right
        ]
    
    # Build base clauses
    clauses = []
    
    # Vertex constraints: degree 0 or 2
    for vr in range(height + 1):
        for vc in range(width + 1):
            v_edges = edges_at_vertex(vr, vc)
            if len(v_edges) < 2:
                for e in v_edges:
                    clauses.append([-e])
            else:
                # If one edge is on, at least one other must be on
                for e in v_edges:
                    others = [x for x in v_edges if x != e]
                    clauses.append([-e] + others)
                # Forbid 3+ edges
                for triple in combinations(v_edges, 3):
                    clauses.append([-triple[0], -triple[1], -triple[2]])
    
    # At least some edges must be on (non-trivial loop)
    all_edge_vars = list(range(1, max_var + 1))
    clauses.append(all_edge_vars)
    
    # CRITICAL: Force loop to pass through center region - not just around it!
    # Pick INTERIOR edges in center that MUST be part of the loop
    center_r = height // 2
    center_c = width // 2
    
    # Collect only INTERIOR edges around center cells (not on perimeter)
    center_interior_edges = []
    for dr in range(-1, 2):
        for dc in range(-1, 2):
            cr, cc = center_r + dr, center_c + dc
            if 0 <= cr < height and 0 <= cc < width:
                # Only add interior edges (not touching grid boundary)
                # Top edge of cell (if not on row 0)
                if cr > 0:
                    center_interior_edges.append(h_var(cr, cc))
                # Bottom edge of cell (if not on last row)
                if cr < height - 1:
                    center_interior_edges.append(h_var(cr + 1, cc))
                # Left edge of cell (if not on column 0)
                if cc > 0:
                    center_interior_edges.append(v_var(cr, cc))
                # Right edge of cell (if not on last column)
                if cc < width - 1:
                    center_interior_edges.append(v_var(cr, cc + 1))
    
    # At least one interior center edge must be on
    if center_interior_edges:
        clauses.append(list(set(center_interior_edges)))
    
    # For larger grids, require more interior edges to prevent simple perimeter loops
    # Calculate minimum complexity based on grid size
    min_interior_ratio = min(0.3, 0.1 + (width * height) / 500)  # Scales with size
    
    # Generate random preferences favoring interior edges
    interior_h_edges = []
    interior_v_edges = []
    
    for r in range(1, h_rows - 1):  # Skip top/bottom rows
        for c in range(h_cols):
            interior_h_edges.append(h_var(r, c))
    
    for r in range(v_rows):
        for c in range(1, v_cols - 1):  # Skip left/right columns
            interior_v_edges.append(v_var(r, c))
    
    all_interior = interior_h_edges + interior_v_edges
    
    # Prefer interior edges more strongly
    preferences = []
    for var in all_interior:
        if random.random() < 0.5:  # 50% chance to prefer interior edges on
            preferences.append(var)
    random.shuffle(preferences)
    
    # Solve iteratively until we get a GOOD single loop
    max_iterations = 200
    best_solution = None
    best_complexity = 0
    
    for iteration in range(max_iterations):
        solver = Solver(name='g3')
        for cl in clauses:
            solver.add_clause(cl)
        
        # Use preferences as soft constraints
        num_assumptions = min(30 + iteration // 10, len(preferences))
        if preferences and solver.solve(assumptions=preferences[:num_assumptions]):
            model = solver.get_model()
        elif solver.solve():
            model = solver.get_model()
        else:
            solver.delete()
            break
        
        solver.delete()
        true_vars = set(v for v in model if v > 0)
        
        # Extract solution
        solution_h = [[False] * h_cols for _ in range(h_rows)]
        solution_v = [[False] * v_cols for _ in range(v_rows)]
        
        for r in range(h_rows):
            for c in range(h_cols):
                if h_var(r, c) in true_vars:
                    solution_h[r][c] = True
        
        for r in range(v_rows):
            for c in range(v_cols):
                if v_var(r, c) in true_vars:
                    solution_v[r][c] = True
        
        # Check for single loop
        lines = set()
        for r in range(h_rows):
            for c in range(h_cols):
                if solution_h[r][c]:
                    lines.add(((r, c), (r, c + 1)))
        for r in range(v_rows):
            for c in range(v_cols):
                if solution_v[r][c]:
                    lines.add(((r, c), (r + 1, c)))
        
        if not lines:
            clauses.append(all_edge_vars)
            continue
        
        components = _find_components(lines)
        
        if len(components) == 1:
            # Single loop - check quality
            total_edges, interior_edges, passes_center = _calculate_loop_complexity(
                solution_h, solution_v, width, height
            )
            
            # Calculate complexity score
            # Prefer loops with more interior edges and that pass through center
            complexity = interior_edges + (10 if passes_center else 0)
            
            # Minimum requirements
            min_edges = 2 * (width + height)  # At least perimeter
            min_interior = int(total_edges * min_interior_ratio)
            
            # Check if loop is good enough
            is_acceptable = (
                total_edges >= min_edges and
                interior_edges >= min_interior and
                passes_center
            )
            
            if is_acceptable:
                return solution_h, solution_v
            
            # Keep best solution so far
            if complexity > best_complexity:
                best_complexity = complexity
                best_solution = (solution_h, solution_v)
            
            # Block this solution to find a better one
            blocking = []
            for v in model:
                if abs(v) <= max_var:
                    blocking.append(-v)
            if blocking:
                clauses.append(blocking)
        else:
            # Multiple components - block smallest
            smallest = min(components, key=lambda comp: len(comp))
            blocking = []
            for v1, v2 in smallest:
                if v1[0] == v2[0]:  # horizontal
                    r = v1[0]
                    c = min(v1[1], v2[1])
                    blocking.append(-h_var(r, c))
                else:  # vertical
                    c = v1[1]
                    r = min(v1[0], v2[0])
                    blocking.append(-v_var(r, c))
            clauses.append(blocking)
        
        # Rotate preferences for variety
        if iteration % 10 == 0:
            random.shuffle(preferences)
    
    # Return best solution found, even if not perfect
    return best_solution


def count_solutions(puzzle: SlitherlinkPuzzle, limit: int = 2) -> int:
    """Count solutions up to limit. Used for uniqueness checking."""
    from itertools import combinations
    
    try:
        from pysat.solvers import Solver
        from pysat.card import CardEnc, EncType
    except ImportError:
        return 0
    
    h_rows, h_cols = puzzle.h_edges_shape
    v_rows, v_cols = puzzle.v_edges_shape
    
    def h_var(r: int, c: int) -> int:
        return 1 + r * h_cols + c
    
    def v_var(r: int, c: int) -> int:
        return 1 + h_rows * h_cols + r * v_cols + c
    
    max_var = h_rows * h_cols + v_rows * v_cols
    
    def edges_at_vertex(vr: int, vc: int) -> List[int]:
        edges = []
        if vc > 0 and vr < h_rows:
            edges.append(h_var(vr, vc - 1))
        if vc < puzzle.width and vr < h_rows:
            edges.append(h_var(vr, vc))
        if vr > 0 and vc < v_cols:
            edges.append(v_var(vr - 1, vc))
        if vr < puzzle.height and vc < v_cols:
            edges.append(v_var(vr, vc))
        return edges
    
    def edges_around_cell(r: int, c: int) -> List[int]:
        return [h_var(r, c), h_var(r + 1, c), v_var(r, c), v_var(r, c + 1)]
    
    clauses = []
    
    # Clue constraints
    for r in range(puzzle.height):
        for c in range(puzzle.width):
            clue = puzzle.clues[r][c]
            if clue is not None:
                cell_edges = edges_around_cell(r, c)
                enc = CardEnc.equals(lits=cell_edges, bound=clue, top_id=max_var, encoding=EncType.seqcounter)
                max_var = max(max_var, max(abs(l) for cl in enc.clauses for l in cl) if enc.clauses else max_var)
                clauses.extend(enc.clauses)
    
    # Vertex constraints
    for vr in range(puzzle.height + 1):
        for vc in range(puzzle.width + 1):
            v_edges = edges_at_vertex(vr, vc)
            if len(v_edges) < 2:
                for e in v_edges:
                    clauses.append([-e])
            else:
                for e in v_edges:
                    others = [x for x in v_edges if x != e]
                    clauses.append([-e] + others)
                for triple in combinations(v_edges, 3):
                    clauses.append([-triple[0], -triple[1], -triple[2]])
    
    count = 0
    max_loop_iterations = 100
    
    for _ in range(max_loop_iterations):
        solver = Solver(name='g3')
        for cl in clauses:
            solver.add_clause(cl)
        
        if not solver.solve():
            solver.delete()
            break
        
        model = solver.get_model()
        solver.delete()
        
        true_vars = set(v for v in model if v > 0)
        
        # Check single loop
        lines = set()
        for r in range(h_rows):
            for c in range(h_cols):
                if h_var(r, c) in true_vars:
                    lines.add(((r, c), (r, c + 1)))
        for r in range(v_rows):
            for c in range(v_cols):
                if v_var(r, c) in true_vars:
                    lines.add(((r, c), (r + 1, c)))
        
        if not lines:
            break
        
        components = _find_components(lines)
        if len(components) == 1:
            count += 1
            if count >= limit:
                return count
        
        # Block this solution
        blocking = []
        for v in model:
            if abs(v) <= h_rows * h_cols + v_rows * v_cols:
                blocking.append(-v)
        if blocking:
            clauses.append(blocking)
        else:
            break
    
    return count


def generate_puzzle(width: int, height: int, seed: Optional[int] = None, 
                    min_clues_ratio: float = 0.3) -> Optional[SlitherlinkPuzzle]:
    """Generate a random Slitherlink puzzle with unique solution.
    
    Args:
        width: Grid width (cells)
        height: Grid height (cells)
        seed: Random seed for reproducibility
        min_clues_ratio: Minimum ratio of cells that must have clues
    
    Returns:
        SlitherlinkPuzzle with guaranteed unique solution, or None if generation fails
    """
    if seed is not None:
        random.seed(seed)
    
    # Generate random loop
    result = generate_random_loop(width, height, seed)
    if result is None:
        return None
    
    solution_h, solution_v = result
    
    # Calculate clues from the loop
    clues: List[List[Optional[int]]] = []
    for r in range(height):
        row = []
        for c in range(width):
            count = 0
            if solution_h[r][c]:
                count += 1
            if solution_h[r + 1][c]:
                count += 1
            if solution_v[r][c]:
                count += 1
            if solution_v[r][c + 1]:
                count += 1
            row.append(count)
        clues.append(row)
    
    # Create puzzle with all clues
    puzzle = SlitherlinkPuzzle(
        width=width,
        height=height,
        clues=clues,
        solution_h=solution_h,
        solution_v=solution_v,
    )
    
    # Clue removal with uniqueness checking
    total_cells = width * height
    min_clues = int(total_cells * min_clues_ratio)
    
    # Identify center region - must keep some non-zero clues there
    center_start_r = height // 4
    center_end_r = height - height // 4
    center_start_c = width // 4
    center_end_c = width - width // 4
    
    def count_center_nonzero():
        """Count non-zero clues in center region."""
        return sum(1 for r in range(center_start_r, center_end_r)
                   for c in range(center_start_c, center_end_c)
                   if puzzle.clues[r][c] is not None and puzzle.clues[r][c] > 0)
    
    def is_in_center(r, c):
        """Check if cell is in center region."""
        return center_start_r <= r < center_end_r and center_start_c <= c < center_end_c
    
    # All cells are candidates for removal, but prioritize edges over center
    edge_cells = [(r, c) for r in range(height) for c in range(width) 
                  if not is_in_center(r, c)]
    center_cells = [(r, c) for r in range(height) for c in range(width) 
                    if is_in_center(r, c)]
    
    random.shuffle(edge_cells)
    random.shuffle(center_cells)
    
    # Process edge cells first, then center cells
    all_cells = edge_cells + center_cells
    
    removed = 0
    max_to_remove = total_cells - min_clues
    
    # Minimum non-zero clues required in center
    min_center_nonzero = max(1, (center_end_r - center_start_r) * (center_end_c - center_start_c) // 4)
    
    # For larger puzzles, skip uniqueness checking and just randomly remove some clues
    if total_cells > 120:
        # Random removal without uniqueness checking for large puzzles
        target_removal = int(total_cells * 0.25)  # Remove ~25% of clues
        for r, c in all_cells:
            if removed >= target_removal:
                break
            clue = puzzle.clues[r][c]
            if clue is not None and clue not in (0, 4):
                # Protect center non-zero clues
                if is_in_center(r, c) and clue > 0:
                    if count_center_nonzero() <= min_center_nonzero:
                        continue  # Don't remove - would leave center empty
                if random.random() < 0.6:
                    puzzle.clues[r][c] = None
                    removed += 1
        return puzzle
    
    # For smaller puzzles, use uniqueness checking
    max_checks = 50 if total_cells <= 80 else 25
    checks_done = 0
    
    for r, c in all_cells:
        if removed >= max_to_remove or checks_done >= max_checks:
            break
        
        clue = puzzle.clues[r][c]
        if clue is None:
            continue
        
        # Skip clues that are definitely needed (0 and 4 are strong constraints)
        if clue in (0, 4):
            continue
        
        # Protect center non-zero clues
        if is_in_center(r, c) and clue > 0:
            if count_center_nonzero() <= min_center_nonzero:
                continue  # Don't remove - would leave center empty
        
        # Try removing this clue
        puzzle.clues[r][c] = None
        checks_done += 1
        
        # Check if puzzle still has unique solution
        solutions = count_solutions(puzzle, limit=2)
        
        if solutions == 1:
            # Uniqueness preserved, keep it removed
            removed += 1
        else:
            # Restore clue to maintain uniqueness
            puzzle.clues[r][c] = clue
    
    return puzzle
