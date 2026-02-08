from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Tuple

from PySide6.QtCore import QStandardPaths

_log = logging.getLogger(__name__)


def appdata_file(filename: str) -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p / filename


def expected_score(r_player: float, r_opp: float) -> float:
    return 1.0 / (1.0 + 10 ** ((r_opp - r_player) / 400.0))


def update_elo(r: float, expected: float, actual: float, k: float = 32.0) -> float:
    return r + k * (actual - expected)


@dataclass
class Record:
    w: int = 0
    d: int = 0
    l: int = 0

    @property
    def games(self) -> int:
        return self.w + self.d + self.l

    def add(self, result: str) -> None:
        if result == "W":
            self.w += 1
        elif result == "D":
            self.d += 1
        elif result == "L":
            self.l += 1


def _default_data() -> Dict[str, Any]:
    return {
        "version": 1,
        "ratings": {},
        "records": {},
        "history": [],
    }


def load_stats(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return _default_data()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        _log.warning("Invalid stats payload at %s: expected object, got %s.", path, type(data).__name__)
        return _default_data()
    except Exception:
        _log.error("Failed to load piskvorky stats from %s.", path, exc_info=True)
        return _default_data()


def save_stats(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_config_key(n: int, difficulty: str) -> str:
    return f"{n}_{difficulty}"


def get_rating(data: Dict[str, Any], key: str, default: float = 1000.0) -> float:
    return float(data.get("ratings", {}).get(key, default))


def get_record(data: Dict[str, Any], key: str) -> Record:
    rec = data.get("records", {}).get(key)
    if not isinstance(rec, dict):
        return Record()
    return Record(w=int(rec.get("w", 0)), d=int(rec.get("d", 0)), l=int(rec.get("l", 0)))


def set_record(data: Dict[str, Any], key: str, record: Record) -> None:
    data.setdefault("records", {})[key] = {"w": record.w, "d": record.d, "l": record.l}


def set_rating(data: Dict[str, Any], key: str, rating: float) -> None:
    data.setdefault("ratings", {})[key] = float(rating)


def add_history(data: Dict[str, Any], entry: Dict[str, Any]) -> None:
    data.setdefault("history", []).append(entry)
    # keep last 200
    if len(data["history"]) > 200:
        data["history"] = data["history"][-200:]
