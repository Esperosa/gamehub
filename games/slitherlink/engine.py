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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Set, Dict, FrozenSet

from hub.solver_contract import Hint, SolveStatus, SolverResult


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


_DIR4: Tuple[Tuple[int, int], ...] = ((-1, 0), (0, 1), (1, 0), (0, -1))


def _inside_to_solution_edges(
    width: int,
    height: int,
    inside: Set[Tuple[int, int]],
) -> Tuple[List[List[bool]], List[List[bool]]]:
    """Convert an inside-cell region to its boundary loop edges."""
    solution_h = [[False] * width for _ in range(height + 1)]
    solution_v = [[False] * (width + 1) for _ in range(height)]

    for r, c in inside:
        if r == 0 or (r - 1, c) not in inside:
            solution_h[r][c] = True
        if r == height - 1 or (r + 1, c) not in inside:
            solution_h[r + 1][c] = True
        if c == 0 or (r, c - 1) not in inside:
            solution_v[r][c] = True
        if c == width - 1 or (r, c + 1) not in inside:
            solution_v[r][c + 1] = True

    return solution_h, solution_v


def _solution_to_lines(
    solution_h: List[List[bool]],
    solution_v: List[List[bool]],
) -> Set[Tuple[Tuple[int, int], Tuple[int, int]]]:
    """Convert solution matrices to a set of line segments."""
    lines: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()

    for r in range(len(solution_h)):
        for c in range(len(solution_h[0])):
            if solution_h[r][c]:
                lines.add(((r, c), (r, c + 1)))

    for r in range(len(solution_v)):
        for c in range(len(solution_v[0])):
            if solution_v[r][c]:
                lines.add(((r, c), (r + 1, c)))

    return lines


def _is_single_cycle_solution(solution_h: List[List[bool]], solution_v: List[List[bool]]) -> bool:
    """Check that solution represents exactly one simple loop."""
    lines = _solution_to_lines(solution_h, solution_v)
    if not lines:
        return False

    degree: Dict[Tuple[int, int], int] = {}
    for v1, v2 in lines:
        degree[v1] = degree.get(v1, 0) + 1
        degree[v2] = degree.get(v2, 0) + 1
    if any(d != 2 for d in degree.values()):
        return False

    components = _find_components(lines)
    return len(components) == 1


def _count_loop_turns(solution_h: List[List[bool]], solution_v: List[List[bool]]) -> int:
    """Count 90-degree turns in a single closed loop."""
    lines = _solution_to_lines(solution_h, solution_v)
    if not lines:
        return 0

    adj: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    for a, b in lines:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    if not adj:
        return 0

    start = next(iter(adj))
    if len(adj[start]) < 2:
        return 0

    prev = start
    curr = adj[start][0]
    first_dir = (curr[0] - start[0], curr[1] - start[1])
    prev_dir = first_dir
    turns = 0

    guard = len(lines) + 5
    while curr != start and guard > 0:
        guard -= 1
        neighbors = adj.get(curr, [])
        if len(neighbors) != 2:
            return 0
        nxt = neighbors[0] if neighbors[1] == prev else neighbors[1]
        d = (nxt[0] - curr[0], nxt[1] - curr[1])
        if d != prev_dir:
            turns += 1
        prev_dir = d
        prev, curr = curr, nxt

    if curr != start:
        return 0

    if prev_dir != first_dir:
        turns += 1
    return turns


def _compute_clues_from_solution(
    width: int,
    height: int,
    solution_h: List[List[bool]],
    solution_v: List[List[bool]],
) -> List[List[int]]:
    clues: List[List[int]] = []
    for r in range(height):
        row: List[int] = []
        for c in range(width):
            cnt = 0
            if solution_h[r][c]:
                cnt += 1
            if solution_h[r + 1][c]:
                cnt += 1
            if solution_v[r][c]:
                cnt += 1
            if solution_v[r][c + 1]:
                cnt += 1
            row.append(cnt)
        clues.append(row)
    return clues


def _generate_inside_path_cells(
    width: int,
    height: int,
    target_cells: int,
    turn_bias: float,
    branch_bias: float,
    rng: random.Random,
) -> Optional[Set[Tuple[int, int]]]:
    """Generate a connected acyclic region quickly (frontier growth)."""
    total_cells = width * height
    target = max(4, min(total_cells, target_cells))

    for _ in range(14):
        start = (rng.randrange(height), rng.randrange(width))
        inside: Set[Tuple[int, int]] = {start}
        parent: Dict[Tuple[int, int], Tuple[int, int]] = {}
        deg: Dict[Tuple[int, int], int] = {start: 0}
        frontier: List[Tuple[Tuple[int, int], Tuple[int, int], int]] = []

        def push_neighbors(cell: Tuple[int, int]) -> None:
            r, c = cell
            for d_idx, (dr, dc) in enumerate(_DIR4):
                nr, nc = r + dr, c + dc
                if 0 <= nr < height and 0 <= nc < width and (nr, nc) not in inside:
                    frontier.append((cell, (nr, nc), d_idx))

        push_neighbors(start)
        stall_count = 0
        steps_left = max(40, target * 6)

        while len(inside) < target and steps_left > 0:
            steps_left -= 1
            if not frontier:
                break

            # Random subset to keep per-step work constant and fast.
            if stall_count == 0:
                sample_size = min(56, len(frontier))
                picked: List[Tuple[Tuple[int, int], Tuple[int, int], int]] = []
                for _k in range(sample_size):
                    picked.append(frontier[rng.randrange(len(frontier))])
            else:
                # On stalls inspect full frontier once to avoid random misses.
                picked = frontier

            candidates: List[Tuple[float, Tuple[int, int], Tuple[int, int]]] = []
            for parent_cell, child_cell, d_idx in picked:
                pr, pc = parent_cell
                nr, nc = child_cell
                if (nr, nc) in inside:
                    continue

                # Keep tree property: child must touch exactly one inside cell.
                neighbors_inside: List[Tuple[int, int]] = []
                for adr, adc in _DIR4:
                    ar, ac = nr + adr, nc + adc
                    if 0 <= ar < height and 0 <= ac < width and (ar, ac) in inside:
                        neighbors_inside.append((ar, ac))
                if len(neighbors_inside) != 1:
                    continue

                real_parent = neighbors_inside[0]
                pdeg = deg.get(real_parent, 0)

                weight = 1.0

                # Branch preference (hard strongly prefers nodes of degree 2 -> 3).
                if pdeg == 2:
                    weight *= 1.0 + 4.5 * branch_bias
                elif pdeg == 1:
                    weight *= 1.0 + 0.6 * (1.0 - branch_bias)
                else:
                    weight *= max(0.06, 1.0 - 0.70 * branch_bias)

                # Turn preference from parent's incoming direction.
                if real_parent in parent:
                    ppr, ppc = parent[real_parent]
                    incoming = (real_parent[0] - ppr, real_parent[1] - ppc)
                    step = (nr - real_parent[0], nc - real_parent[1])
                    if step == incoming:
                        weight *= max(0.04, 1.0 - turn_bias)
                    else:
                        weight *= 1.0 + turn_bias

                # Mild outward bias for harder levels => larger map coverage.
                border_dist = min(nr, nc, height - 1 - nr, width - 1 - nc)
                weight *= 1.0 + (0.10 + 0.12 * branch_bias) * border_dist
                candidates.append((weight, real_parent, (nr, nc)))

            if not candidates:
                stall_count += 1

                # Prune permanently-dead frontier entries:
                # - child already inside
                # - child currently touches 2+ inside cells (can never become valid later)
                pruned: List[Tuple[Tuple[int, int], Tuple[int, int], int]] = []
                seen = set()
                for pcell, ccell, didx in frontier:
                    if ccell in inside:
                        continue
                    nr, nc = ccell
                    adj_count = 0
                    for adr, adc in _DIR4:
                        ar, ac = nr + adr, nc + adc
                        if 0 <= ar < height and 0 <= ac < width and (ar, ac) in inside:
                            adj_count += 1
                            if adj_count > 1:
                                break
                    if adj_count != 1:
                        continue
                    key = (pcell, ccell, didx)
                    if key in seen:
                        continue
                    seen.add(key)
                    pruned.append((pcell, ccell, didx))
                frontier = pruned

                if not frontier or stall_count >= 3:
                    break
                continue

            total_w = sum(w for w, _, _ in candidates)
            roll = rng.random() * total_w
            chosen_parent = candidates[0][1]
            chosen_cell = candidates[0][2]
            acc = 0.0
            for w, pcell, cell in candidates:
                acc += w
                if roll <= acc:
                    chosen_parent = pcell
                    chosen_cell = cell
                    break

            inside.add(chosen_cell)
            parent[chosen_cell] = chosen_parent
            deg[chosen_parent] = deg.get(chosen_parent, 0) + 1
            deg[chosen_cell] = 1
            push_neighbors(chosen_cell)
            stall_count = 0

        if len(inside) >= max(4, int(target * 0.90)):
            return inside

    return None


def _mask_clues_for_difficulty(
    full_clues: List[List[int]],
    difficulty: str,
    keep_ratio: float,
    rng: random.Random,
) -> List[List[Optional[int]]]:
    """Remove clues quickly with difficulty-specific weighting."""
    height = len(full_clues)
    width = len(full_clues[0]) if height else 0
    total = width * height
    target_keep = max(1, min(total, int(round(total * keep_ratio))))
    to_remove = total - target_keep
    if to_remove <= 0:
        return [[int(v) for v in row] for row in full_clues]

    center_r0 = height // 4
    center_r1 = height - height // 4
    center_c0 = width // 4
    center_c1 = width - width // 4

    # Higher weight => higher chance to be removed.
    value_remove_weights = {
        "easy": {0: 1.00, 1: 0.85, 2: 1.10, 3: 0.80},
        "medium": {0: 1.25, 1: 0.65, 2: 1.80, 3: 0.60},
        "hard": {0: 1.50, 1: 0.40, 2: 2.30, 3: 0.35},
    }
    weight_by_value = value_remove_weights.get(difficulty, value_remove_weights["medium"])
    center_mult = {"easy": 0.65, "medium": 0.85, "hard": 0.95}.get(difficulty, 0.85)

    ranked: List[Tuple[float, int, int]] = []
    for r in range(height):
        for c in range(width):
            clue = full_clues[r][c]
            w = weight_by_value.get(clue, 1.0)
            if center_r0 <= r < center_r1 and center_c0 <= c < center_c1:
                w *= center_mult

            priority = rng.random() * w
            ranked.append((priority, r, c))

    ranked.sort(reverse=True, key=lambda x: x[0])
    remove_set = {(r, c) for _, r, c in ranked[:to_remove]}

    # Post-balance: for medium/hard, ensure enough visible 1/3 clues (not mostly 2).
    target_shown13 = {"easy": 0.30, "medium": 0.40, "hard": 0.50}.get(difficulty, 0.40)
    removed_13: List[Tuple[int, int]] = []
    shown_2: List[Tuple[int, int]] = []
    shown_count = 0
    shown13_count = 0
    for r in range(height):
        for c in range(width):
            v = full_clues[r][c]
            if (r, c) in remove_set:
                if v in (1, 3):
                    removed_13.append((r, c))
            else:
                shown_count += 1
                if v in (1, 3):
                    shown13_count += 1
                elif v == 2:
                    shown_2.append((r, c))

    rng.shuffle(removed_13)
    rng.shuffle(shown_2)
    while removed_13 and shown_2 and (shown13_count / max(1, shown_count)) < target_shown13:
        add_r, add_c = removed_13.pop()
        rem_r, rem_c = shown_2.pop()
        if (add_r, add_c) in remove_set and (rem_r, rem_c) not in remove_set:
            remove_set.remove((add_r, add_c))
            remove_set.add((rem_r, rem_c))
            shown13_count += 1

    clues: List[List[Optional[int]]] = []
    for r in range(height):
        row: List[Optional[int]] = []
        for c in range(width):
            row.append(None if (r, c) in remove_set else int(full_clues[r][c]))
        clues.append(row)
    return clues


def _loop_area_ratio(solution_h: List[List[bool]], solution_v: List[List[bool]], width: int, height: int) -> float:
    """Compute enclosed area ratio via polygon shoelace on the loop path."""
    lines = _solution_to_lines(solution_h, solution_v)
    if not lines:
        return 0.0

    adj: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    for a, b in lines:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)

    start = next(iter(adj))
    if len(adj[start]) < 2:
        return 0.0

    prev = start
    curr = adj[start][0]
    path = [start, curr]
    guard = len(lines) + 5

    while curr != start and guard > 0:
        guard -= 1
        nbs = adj.get(curr, [])
        if len(nbs) != 2:
            return 0.0
        nxt = nbs[0] if nbs[1] == prev else nbs[1]
        prev, curr = curr, nxt
        path.append(curr)

    if path[-1] != start:
        return 0.0

    area2 = 0
    for i in range(len(path) - 1):
        x1, y1 = path[i][1], path[i][0]
        x2, y2 = path[i + 1][1], path[i + 1][0]
        area2 += x1 * y2 - x2 * y1
    area = abs(area2) / 2.0

    return area / max(1, width * height)


def _fast_generate_puzzle(
    width: int,
    height: int,
    difficulty: str,
    seed: Optional[int] = None,
) -> Optional[SlitherlinkPuzzle]:
    """Fast seed-driven generator focused on speed and turn-complexity."""
    difficulty_key = (difficulty or "medium").lower().strip()
    profiles = {
        "easy": {
            "target_turn_density": 0.28,
            "target_area_ratio": 0.26,
            "target_13_ratio": 0.26,
            "turn_bias": 0.35,
            "branch_bias": 0.25,
            "keep_ratio": (0.72, 0.86),
            "attempts": 5,
            "accept": (0.15, 0.40, 0.16, 0.42, 0.24),
        },
        "medium": {
            "target_turn_density": 0.37,
            "target_area_ratio": 0.40,
            "target_13_ratio": 0.36,
            "turn_bias": 0.75,
            "branch_bias": 0.60,
            "keep_ratio": (0.68, 0.86),
            "attempts": 7,
            "accept": (0.30, 0.50, 0.28, 0.52, 0.30),
        },
        "hard": {
            "target_turn_density": 0.48,
            "target_area_ratio": 0.50,
            "target_13_ratio": 0.45,
            "turn_bias": 1.10,
            "branch_bias": 1.00,
            "keep_ratio": (0.70, 0.90),
            "attempts": 9,
            "accept": (0.42, 0.58, 0.38, 0.60, 0.40),
        },
    }
    profile = profiles.get(difficulty_key, profiles["medium"])

    base_seed = seed if seed is not None else random.randrange(1 << 30)
    rng = random.Random(base_seed ^ 0x9E3779B9)
    total_cells = width * height

    best: Optional[SlitherlinkPuzzle] = None
    best_score = -10**9

    for attempt in range(profile["attempts"]):
        local_rng = random.Random(base_seed + 7919 * (attempt + 1))
        loop = generate_random_loop(width, height, seed=base_seed + 104729 * (attempt + 1))
        if loop is not None:
            solution_h, solution_v = loop
        else:
            # SAT unavailable/failed: build a complex loop from a connected cell region.
            area_target = max(0.10, min(0.85, profile["target_area_ratio"] + local_rng.uniform(-0.08, 0.08)))
            target_cells = max(4, int(width * height * area_target))
            inside = _generate_inside_path_cells(
                width=width,
                height=height,
                target_cells=target_cells,
                turn_bias=profile["turn_bias"],
                branch_bias=profile["branch_bias"],
                rng=local_rng,
            )
            if not inside:
                continue
            solution_h, solution_v = _inside_to_solution_edges(width, height, inside)

        if not _is_single_cycle_solution(solution_h, solution_v):
            continue

        lines = _solution_to_lines(solution_h, solution_v)
        edge_count = len(lines)
        if edge_count < 8:
            continue

        turns = _count_loop_turns(solution_h, solution_v)
        turn_density = turns / edge_count
        area_ratio = _loop_area_ratio(solution_h, solution_v, width, height)

        clues_full = _compute_clues_from_solution(width, height, solution_h, solution_v)
        k_lo, k_hi = profile["keep_ratio"]
        keep_ratio = local_rng.uniform(k_lo, k_hi)
        clues = _mask_clues_for_difficulty(clues_full, difficulty_key, keep_ratio, local_rng)

        clue_count = sum(1 for r in range(height) for c in range(width) if clues[r][c] is not None)
        clue_ratio = clue_count / max(1, total_cells)

        one_three_full = sum(1 for r in range(height) for c in range(width) if clues_full[r][c] in (1, 3))
        one_three_ratio = one_three_full / max(1, total_cells)

        shown_total = 0
        shown_one_three = 0
        for r in range(height):
            for c in range(width):
                v = clues[r][c]
                if v is None:
                    continue
                shown_total += 1
                if v in (1, 3):
                    shown_one_three += 1
        shown_one_three_ratio = shown_one_three / max(1, shown_total)

        # Score: prioritize turn + area by difficulty, then clue profile.
        target_td = profile["target_turn_density"]
        target_area = profile["target_area_ratio"]
        complexity_score = -abs(turn_density - target_td) * 140.0
        area_score = -abs(area_ratio - target_area) * 120.0
        target_13 = profile["target_13_ratio"]
        dist_13_score = -abs(one_three_ratio - target_13) * 110.0
        clue_target = (k_lo + k_hi) / 2.0
        clue_score = -abs(clue_ratio - clue_target) * 50.0
        shown_13_bonus = shown_one_three_ratio * 35.0
        edge_bonus = min(20.0, edge_count / max(1.0, total_cells) * 26.0)
        score = complexity_score + area_score + dist_13_score + clue_score + shown_13_bonus + edge_bonus

        puzzle = SlitherlinkPuzzle(
            width=width,
            height=height,
            clues=clues,
            solution_h=solution_h,
            solution_v=solution_v,
        )

        if score > best_score:
            best_score = score
            best = puzzle

        # Accept early when difficulty target is clearly met.
        t_min, t_max, a_min, a_max, shown13_min = profile["accept"]
        if difficulty_key == "hard":
            if (
                t_min <= turn_density <= t_max
                and a_min <= area_ratio <= a_max
                and clue_ratio >= 0.70
                and shown_one_three_ratio >= shown13_min
            ):
                return puzzle
        elif difficulty_key == "medium":
            if (
                t_min <= turn_density <= t_max
                and a_min <= area_ratio <= a_max
                and 0.66 <= clue_ratio <= 0.90
                and shown_one_three_ratio >= shown13_min
            ):
                return puzzle
        else:
            if (
                t_min <= turn_density <= t_max
                and a_min <= area_ratio <= a_max
                and clue_ratio >= 0.72
            ):
                return puzzle

    if best is not None:
        return best

    # Soft fallback: a few more SAT-loop attempts, then give up to caller fallback.
    for extra in range(4):
        loop = generate_random_loop(width, height, seed=base_seed + 19937 * (extra + 1))
        if loop is None:
            continue
        solution_h, solution_v = loop
        clues_full = _compute_clues_from_solution(width, height, solution_h, solution_v)
        k_lo, k_hi = profile["keep_ratio"]
        keep_ratio = (k_lo + k_hi) / 2.0
        clues = _mask_clues_for_difficulty(clues_full, difficulty_key, keep_ratio, rng)
        return SlitherlinkPuzzle(
            width=width,
            height=height,
            clues=clues,
            solution_h=solution_h,
            solution_v=solution_v,
        )

    # Non-SAT final fallback (still non-trivial, not a forced perimeter frame).
    for extra in range(6):
        local_rng = random.Random(base_seed + 65537 * (extra + 1))
        target_cells = max(4, int(width * height * max(0.10, min(0.85, profile["target_area_ratio"]))))
        inside = _generate_inside_path_cells(
            width=width,
            height=height,
            target_cells=target_cells,
            turn_bias=profile["turn_bias"],
            branch_bias=profile["branch_bias"],
            rng=local_rng,
        )
        if not inside:
            continue
        solution_h, solution_v = _inside_to_solution_edges(width, height, inside)
        if not _is_single_cycle_solution(solution_h, solution_v):
            continue
        clues_full = _compute_clues_from_solution(width, height, solution_h, solution_v)
        k_lo, k_hi = profile["keep_ratio"]
        keep_ratio = (k_lo + k_hi) / 2.0
        clues = _mask_clues_for_difficulty(clues_full, difficulty_key, keep_ratio, local_rng)
        return SlitherlinkPuzzle(
            width=width,
            height=height,
            clues=clues,
            solution_h=solution_h,
            solution_v=solution_v,
        )

    return None


def create_puzzle(
    size: int = 10,
    difficulty: str = 'medium',
    seed: Optional[int] = None,
) -> Optional[SlitherlinkState]:
    """Create a puzzle quickly with seed-driven complexity profiles."""
    puzzle = _fast_generate_puzzle(size, size, difficulty, seed=seed)
    if puzzle is not None:
        return SlitherlinkState.from_puzzle(puzzle)

    # Fallback to templates (packaged mode or unexpected generation failure).
    difficulty_key = (difficulty or "medium").lower().strip()
    return load_random_puzzle(size=size, difficulty=difficulty_key)


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

    def get_hint_result(self) -> Optional[Hint]:
        hint = self.get_hint()
        if hint is None:
            return None
        edge_type, row, col, value = hint
        explanation = "Draw this edge." if value == 1 else "Mark this edge as empty."
        return Hint(
            type="edge_state",
            cells=((row, col),),
            explanation=explanation,
            confidence=0.75,
            payload={"edge_type": edge_type, "value": value},
        )
    
    def solve(self) -> Optional[SlitherlinkState]:
        """Fully solve using SAT solver. Returns solved state or None."""
        return solve_with_sat(self.state)

    def solve_result(self, timeout: Optional[float] = None, detect_multiple: bool = True) -> SolverResult:
        """Normalized solver output for hub-level consumption."""
        start = time.perf_counter()
        deadline = None if timeout is None else (start + max(0.0, timeout))
        searcher = _SatSlitherlinkSearch(self.state)

        try:
            solved = searcher.search(deadline=deadline)
        except _SatSlitherlinkSearch._SolveTimeout:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return SolverResult(
                status=SolveStatus.TIMEOUT,
                solution=None,
                solutions_found=None,
                elapsed_ms=elapsed_ms,
                message="Solver timed out before completion.",
            )

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        if solved is None:
            return SolverResult(
                status=SolveStatus.UNSOLVABLE,
                solution=None,
                solutions_found=0,
                elapsed_ms=elapsed_ms,
                message="No satisfying loop found.",
            )

        status = SolveStatus.SOLVED
        solutions_found: Optional[int] = None
        if detect_multiple:
            try:
                has_alt = searcher.has_alternative_solution(solved, deadline=deadline)
            except _SatSlitherlinkSearch._SolveTimeout:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                return SolverResult(
                    status=SolveStatus.TIMEOUT,
                    solution=None,
                    solutions_found=None,
                    elapsed_ms=elapsed_ms,
                    message="Alternative-solution check timed out.",
                )
            solutions_found = 2 if has_alt else 1
            if has_alt:
                status = SolveStatus.MULTIPLE_SOLUTIONS

        return SolverResult(
            status=status,
            solution=solved,
            solutions_found=solutions_found,
            elapsed_ms=elapsed_ms,
            message="Solved" if status == SolveStatus.SOLVED else "Multiple valid solutions found.",
        )


def solve_with_sat(state: SlitherlinkState) -> Optional[SlitherlinkState]:
    """Solve Slitherlink using SAT search pipeline."""
    return _SatSlitherlinkSearch(state).search()


class _SatSlitherlinkSearch:
    @dataclass(frozen=True)
    class Encoding:
        clauses: List[List[int]]
        max_var: int

    class _SolveTimeout(Exception):
        pass

    def __init__(self, state: SlitherlinkState):
        self.state = state
        self.puzzle = state.puzzle
        self.h_rows, self.h_cols = self.puzzle.h_edges_shape
        self.v_rows, self.v_cols = self.puzzle.v_edges_shape

        try:
            from pysat.solvers import Solver  # type: ignore
            from pysat.card import CardEnc, EncType  # type: ignore
            self._Solver = Solver
            self._CardEnc = CardEnc
            self._EncType = EncType
            self._sat_available = True
        except ImportError:
            self._sat_available = False
            self._Solver = None
            self._CardEnc = None
            self._EncType = None

    def h_var(self, r: int, c: int) -> int:
        return 1 + r * self.h_cols + c

    def v_var(self, r: int, c: int) -> int:
        return 1 + self.h_rows * self.h_cols + r * self.v_cols + c

    def parse(self) -> Optional[SlitherlinkState]:
        """Validate state shape and edge value domain before SAT encoding."""
        if not self._sat_available:
            return None

        if len(self.state.h_edges) != self.h_rows:
            return None
        if len(self.state.v_edges) != self.v_rows:
            return None

        for row in self.state.h_edges:
            if len(row) != self.h_cols:
                return None
            for value in row:
                if value not in (-1, 0, 1):
                    return None

        for row in self.state.v_edges:
            if len(row) != self.v_cols:
                return None
            for value in row:
                if value not in (-1, 0, 1):
                    return None

        if len(self.puzzle.clues) != self.puzzle.height:
            return None
        for row in self.puzzle.clues:
            if len(row) != self.puzzle.width:
                return None
            for clue in row:
                if clue is not None and (clue < 0 or clue > 3):
                    return None

        return self.state

    def _check_deadline(self, deadline: Optional[float]) -> None:
        if deadline is not None and time.perf_counter() >= deadline:
            raise _SatSlitherlinkSearch._SolveTimeout()

    def _edges_at_vertex(self, vr: int, vc: int) -> List[int]:
        edges: List[int] = []
        if vc > 0 and vr < self.h_rows:
            edges.append(self.h_var(vr, vc - 1))
        if vc < self.puzzle.width and vr < self.h_rows:
            edges.append(self.h_var(vr, vc))
        if vr > 0 and vc < self.v_cols:
            edges.append(self.v_var(vr - 1, vc))
        if vr < self.puzzle.height and vc < self.v_cols:
            edges.append(self.v_var(vr, vc))
        return edges

    def _edges_around_cell(self, r: int, c: int) -> List[int]:
        return [
            self.h_var(r, c),
            self.h_var(r + 1, c),
            self.v_var(r, c),
            self.v_var(r, c + 1),
        ]

    def encode_constraints(self) -> Optional["_SatSlitherlinkSearch.Encoding"]:
        """Encode clues + degree constraints + fixed edges into CNF clauses."""
        from itertools import combinations

        parsed = self.parse()
        if parsed is None:
            return None

        max_var = self.h_rows * self.h_cols + self.v_rows * self.v_cols
        clauses: List[List[int]] = []

        for r in range(self.puzzle.height):
            for c in range(self.puzzle.width):
                clue = self.puzzle.clues[r][c]
                if clue is None:
                    continue
                cell_edges = self._edges_around_cell(r, c)
                enc = self._CardEnc.equals(
                    lits=cell_edges,
                    bound=clue,
                    top_id=max_var,
                    encoding=self._EncType.seqcounter,
                )
                if enc.clauses:
                    max_in_enc = max(abs(lit) for cl in enc.clauses for lit in cl)
                    max_var = max(max_var, max_in_enc)
                clauses.extend(enc.clauses)

        for vr in range(self.puzzle.height + 1):
            for vc in range(self.puzzle.width + 1):
                v_edges = self._edges_at_vertex(vr, vc)
                if len(v_edges) < 2:
                    for edge in v_edges:
                        clauses.append([-edge])
                    continue

                for edge in v_edges:
                    others = [x for x in v_edges if x != edge]
                    clauses.append([-edge] + others)

                for triple in combinations(v_edges, 3):
                    clauses.append([-triple[0], -triple[1], -triple[2]])

        for r in range(self.h_rows):
            for c in range(self.h_cols):
                if parsed.h_edges[r][c] == 1:
                    clauses.append([self.h_var(r, c)])
                elif parsed.h_edges[r][c] == -1:
                    clauses.append([-self.h_var(r, c)])

        for r in range(self.v_rows):
            for c in range(self.v_cols):
                if parsed.v_edges[r][c] == 1:
                    clauses.append([self.v_var(r, c)])
                elif parsed.v_edges[r][c] == -1:
                    clauses.append([-self.v_var(r, c)])

        return _SatSlitherlinkSearch.Encoding(clauses=clauses, max_var=max_var)

    def propagate(self, encoding: "_SatSlitherlinkSearch.Encoding", deadline: Optional[float] = None) -> Optional[Set[int]]:
        """Run one SAT solve step and return positive literals from the model."""
        self._check_deadline(deadline)
        solver = self._Solver(name="g3")
        for clause in encoding.clauses:
            solver.add_clause(clause)

        self._check_deadline(deadline)
        if not solver.solve():
            solver.delete()
            return None

        model = solver.get_model() or []
        solver.delete()
        self._check_deadline(deadline)
        return {v for v in model if v > 0}

    def _decode_model(self, true_vars: Set[int]) -> SlitherlinkState:
        import copy

        result = copy.deepcopy(self.state)
        for r in range(self.h_rows):
            for c in range(self.h_cols):
                result.h_edges[r][c] = 1 if self.h_var(r, c) in true_vars else 0

        for r in range(self.v_rows):
            for c in range(self.v_cols):
                result.v_edges[r][c] = 1 if self.v_var(r, c) in true_vars else 0

        return result

    def select_var(self, candidate: SlitherlinkState) -> Optional[List[int]]:
        """Build a blocking clause for one loop component to force change."""
        lines = candidate._collect_lines()
        if not lines:
            return None

        components = _find_components(lines)
        if len(components) <= 1:
            return None

        smallest = min(components, key=lambda comp: len(comp))
        blocking: List[int] = []
        for v1, v2 in smallest:
            if v1[0] == v2[0]:
                r = v1[0]
                c = min(v1[1], v2[1])
                blocking.append(-self.h_var(r, c))
            else:
                c = v1[1]
                r = min(v1[0], v2[0])
                blocking.append(-self.v_var(r, c))

        return blocking if blocking else None

    def validate_solution(self, candidate: SlitherlinkState) -> bool:
        complete, _ = candidate.is_complete()
        return bool(complete)

    def _full_solution_blocking_clause(self, solution: SlitherlinkState) -> List[int]:
        clause: List[int] = []
        for r in range(self.h_rows):
            for c in range(self.h_cols):
                var = self.h_var(r, c)
                clause.append(-var if solution.h_edges[r][c] == 1 else var)
        for r in range(self.v_rows):
            for c in range(self.v_cols):
                var = self.v_var(r, c)
                clause.append(-var if solution.v_edges[r][c] == 1 else var)
        return clause

    def search(
        self,
        max_iterations: int = 100,
        deadline: Optional[float] = None,
        extra_clauses: Optional[List[List[int]]] = None,
    ) -> Optional[SlitherlinkState]:
        """Iterative SAT solving with loop-component blocking search."""
        encoding = self.encode_constraints()
        if encoding is None:
            return None

        clauses = [clause[:] for clause in encoding.clauses]
        if extra_clauses:
            clauses.extend([clause[:] for clause in extra_clauses])

        for _ in range(max_iterations):
            self._check_deadline(deadline)
            step_encoding = _SatSlitherlinkSearch.Encoding(clauses=clauses, max_var=encoding.max_var)
            true_vars = self.propagate(step_encoding, deadline=deadline)
            if true_vars is None:
                return None

            candidate = self._decode_model(true_vars)
            if self.validate_solution(candidate):
                return candidate

            if not candidate._collect_lines():
                return None

            blocking = self.select_var(candidate)
            if blocking is None:
                # Preserve prior behavior for unusual single-component non-complete models.
                return candidate

            clauses.append(blocking)

        return None

    def has_alternative_solution(self, solution: SlitherlinkState, deadline: Optional[float] = None) -> bool:
        """Check if a second distinct valid solution exists."""
        block = self._full_solution_blocking_clause(solution)
        alt = self.search(deadline=deadline, extra_clauses=[block])
        return alt is not None


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


def _propagation_resolved_ratio(puzzle: SlitherlinkPuzzle) -> float:
    """Estimate logical easiness by simple propagation-only progress.

    Returns:
        Ratio (0..1) of edges resolved by the built-in propagation rules from an empty board.
        Higher means easier for human-like basic deductions.
    """
    state = SlitherlinkState.from_puzzle(puzzle)
    solver = SlitherlinkSolver(state)
    solver.propagate()

    total_edges = (
        len(state.h_edges) * len(state.h_edges[0]) +
        len(state.v_edges) * len(state.v_edges[0])
    )
    if total_edges == 0:
        return 0.0

    resolved = (
        sum(1 for row in state.h_edges for v in row if v != 0) +
        sum(1 for row in state.v_edges for v in row if v != 0)
    )
    return resolved / total_edges


def generate_puzzle(
    width: int,
    height: int,
    seed: Optional[int] = None,
    min_clues_ratio: float = 0.3,
    max_clues_ratio: Optional[float] = None,
    protect_strong_clues: bool = True,
    center_keep_ratio: float = 0.25,
    max_uniqueness_checks: Optional[int] = None,
) -> Optional[SlitherlinkPuzzle]:
    """Generate a random Slitherlink puzzle with unique solution.
    
    Args:
        width: Grid width (cells)
        height: Grid height (cells)
        seed: Random seed for reproducibility
        min_clues_ratio: Minimum ratio of cells that must have clues
        max_clues_ratio: Maximum ratio of cells that may remain (randomized target)
        protect_strong_clues: If True, keep most 0/4 clues (strong constraints)
        center_keep_ratio: Minimum fraction of non-zero center clues to keep
        max_uniqueness_checks: Upper limit of SAT uniqueness checks during clue removal
    
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
    min_clues_ratio = max(0.0, min(1.0, min_clues_ratio))
    if max_clues_ratio is None:
        max_clues_ratio = min(1.0, min_clues_ratio + 0.15)
    max_clues_ratio = max(min_clues_ratio, min(1.0, max_clues_ratio))

    target_ratio = random.uniform(min_clues_ratio, max_clues_ratio)
    target_clues = max(1, min(total_cells, int(round(total_cells * target_ratio))))
    
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
    
    removed = 0
    max_to_remove = max(0, total_cells - target_clues)
    
    # Minimum non-zero clues required in center
    center_cells_count = max(1, (center_end_r - center_start_r) * (center_end_c - center_start_c))
    min_center_nonzero = int(center_cells_count * max(0.0, min(1.0, center_keep_ratio)))
    center_nonzero = count_center_nonzero()
    
    if max_uniqueness_checks is None:
        max_uniqueness_checks = max(80, min(1000, max_to_remove * 6))
    checks_done = 0
    
    # Single-pass removal with uniqueness checks.
    random.shuffle(edge_cells)
    random.shuffle(center_cells)
    all_cells = edge_cells + center_cells
    
    for r, c in all_cells:
        if removed >= max_to_remove or checks_done >= max_uniqueness_checks:
            break
        
        clue = puzzle.clues[r][c]
        if clue is None:
            continue
        
        if protect_strong_clues and clue in (0, 4):
            continue
        
        in_center = is_in_center(r, c)
        center_positive = in_center and clue > 0
        
        # Protect center non-zero clues according to difficulty profile.
        if min_center_nonzero > 0 and center_positive and center_nonzero <= min_center_nonzero:
            continue
        
        # Try removing this clue.
        puzzle.clues[r][c] = None
        checks_done += 1
        
        # Keep only if uniqueness is preserved.
        solutions = count_solutions(puzzle, limit=2)
        if solutions == 1:
            removed += 1
            if center_positive:
                center_nonzero -= 1
        else:
            puzzle.clues[r][c] = clue
    
    return puzzle
