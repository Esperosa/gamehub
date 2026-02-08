from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    backend_label: str
    env_override: Optional[str]
    details: str
    raw_stdout: str = ""
    raw_stderr: str = ""


def _run_probe_once(project_root: Path, backend_label: str, env_override: Optional[str]) -> ProbeResult:
    env = os.environ.copy()
    if env_override:
        env["QT_OPENGL"] = env_override

    cmd = [sys.executable, "-m", "hub.diagnostics.gpu_probe_runner"]
    result = subprocess.run(
        cmd,
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    payload: Dict[str, object] = {}
    if stdout:
        last_line = stdout.splitlines()[-1]
        try:
            payload = json.loads(last_line)
        except json.JSONDecodeError:
            payload = {}

    ok = bool(result.returncode == 0 and payload.get("ok") is True)
    exit_u32 = result.returncode & 0xFFFFFFFF
    if ok:
        vendor = str(payload.get("vendor", ""))
        renderer = str(payload.get("renderer", ""))
        version = str(payload.get("version", ""))
        details = f"ok vendor={vendor!r} renderer={renderer!r} version={version!r}"
    else:
        reason = str(payload.get("reason", "")) if payload else ""
        details = f"exit={result.returncode}"
        if reason:
            details += f" reason={reason}"
        if not reason and exit_u32 == 0xC0000005:
            details += " reason=access-violation"

    return ProbeResult(
        ok=ok,
        backend_label=backend_label,
        env_override=env_override,
        details=details,
        raw_stdout=stdout[-700:],
        raw_stderr=stderr[-700:],
    )


def probe_gpu_backend(project_root: Path) -> ProbeResult:
    candidates = [
        ("default", None),
        ("desktop", "desktop"),
        ("angle", "angle"),
    ]

    failures: list[ProbeResult] = []
    for label, override in candidates:
        outcome = _run_probe_once(project_root, label, override)
        if outcome.ok:
            return outcome
        failures.append(outcome)

    summary = " | ".join(f"{f.backend_label}:{f.details}" for f in failures)
    return ProbeResult(
        ok=False,
        backend_label="none",
        env_override=None,
        details=summary,
        raw_stdout="\n".join(f"[{f.backend_label}] {f.raw_stdout}" for f in failures if f.raw_stdout),
        raw_stderr="\n".join(f"[{f.backend_label}] {f.raw_stderr}" for f in failures if f.raw_stderr),
    )
