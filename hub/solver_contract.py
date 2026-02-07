from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class SolveStatus(str, Enum):
    SOLVED = "Solved"
    UNSOLVABLE = "Unsolvable"
    MULTIPLE_SOLUTIONS = "MultipleSolutions"
    TIMEOUT = "Timeout"


@dataclass(frozen=True)
class SolverResult:
    status: SolveStatus
    solution: Optional[Any] = None
    solutions_found: Optional[int] = None
    elapsed_ms: Optional[int] = None
    message: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Hint:
    type: str
    cells: Tuple[Tuple[int, int], ...]
    explanation: str
    confidence: float
    payload: Dict[str, Any] = field(default_factory=dict)
