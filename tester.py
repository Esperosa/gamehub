from __future__ import annotations

import argparse
import importlib.util
import io
import logging
import os
import sys
import time
import traceback
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parent
GAMES_DIR = ROOT / "games"
TESTS_DIR = ROOT / "tests"


@dataclass
class CheckResult:
    name: str
    passed: bool
    duration_ms: int
    detail: str = ""


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _status_label(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def _print_header(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def _print_result(result: CheckResult) -> None:
    suffix = f" - {result.detail}" if result.detail else ""
    print(f"[{_status_label(result.passed)}] {result.name} ({result.duration_ms} ms){suffix}")


def _call_hook(widget: object, hook_name: str) -> None:
    hook = getattr(widget, hook_name, None)
    if callable(hook):
        hook()


def _normalize_adapter_outcome(outcome: object) -> Tuple[bool, str]:
    if isinstance(outcome, bool):
        return outcome, ""
    if isinstance(outcome, tuple) and len(outcome) == 2 and isinstance(outcome[0], bool):
        return outcome[0], str(outcome[1])
    raise TypeError("Adapter run_audit() must return bool or (bool, detail)")


def run_plugin_smoke() -> List[CheckResult]:
    start = time.perf_counter()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    try:
        from PySide6.QtWidgets import QApplication, QWidget
        from hub.plugin_loader import discover_plugins
    except Exception as exc:
        return [CheckResult("plugin-smoke", False, _ms(start), f"import error: {exc!r}")]

    app = QApplication.instance() or QApplication([])
    plugin_logger = logging.getLogger("hub.plugin_loader")
    previous_level = plugin_logger.level
    plugin_logger.setLevel(logging.ERROR)
    try:
        loaded = discover_plugins(GAMES_DIR)
    finally:
        plugin_logger.setLevel(previous_level)
    results: List[CheckResult] = [
        CheckResult(
            name="plugin-discovery",
            passed=len(loaded) > 0,
            duration_ms=_ms(start),
            detail=f"discovered {len(loaded)} plugin(s)",
        )
    ]
    if not loaded:
        return results

    for lp in loaded:
        plugin_start = time.perf_counter()
        check_name = f"plugin:{lp.plugin.meta.id}"
        try:
            widget = lp.plugin.create_widget(parent=None)
            if not isinstance(widget, QWidget):
                raise TypeError(f"create_widget() returned {type(widget)!r}, expected QWidget")

            _call_hook(widget, "on_activate")
            app.processEvents()
            _call_hook(widget, "on_deactivate")
            _call_hook(widget, "dispose")
            widget.deleteLater()
            app.processEvents()
            detail = f"widget={widget.__class__.__name__}"
            results.append(CheckResult(check_name, True, _ms(plugin_start), detail))
        except Exception as exc:
            detail = f"{exc.__class__.__name__}: {exc}"
            results.append(CheckResult(check_name, False, _ms(plugin_start), detail))

    return results


def run_game_adapters() -> List[CheckResult]:
    start = time.perf_counter()
    adapter_files = sorted(GAMES_DIR.glob("*/tester.py"))
    if not adapter_files:
        return [
            CheckResult(
                name="game-adapters",
                passed=True,
                duration_ms=_ms(start),
                detail="no per-game adapters found (expected: games/<game>/tester.py)",
            )
        ]

    results: List[CheckResult] = []
    for file_path in adapter_files:
        case_start = time.perf_counter()
        game_id = file_path.parent.name
        case_name = f"adapter:{game_id}"
        try:
            module_name = f"gamehub_tester_adapter_{game_id}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot import {file_path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[attr-defined]

            run_audit = getattr(module, "run_audit", None)
            if not callable(run_audit):
                raise AttributeError("missing callable run_audit()")

            passed, detail = _normalize_adapter_outcome(run_audit())
            results.append(CheckResult(case_name, passed, _ms(case_start), detail))
        except Exception as exc:
            detail = f"{exc.__class__.__name__}: {exc}"
            results.append(CheckResult(case_name, False, _ms(case_start), detail))

    return results


def run_unit_tests(verbosity: int = 2) -> List[CheckResult]:
    start = time.perf_counter()
    if not TESTS_DIR.exists():
        return [
            CheckResult(
                name="unit-tests",
                passed=False,
                duration_ms=_ms(start),
                detail=f"missing test directory: {TESTS_DIR}",
            )
        ]

    suite = unittest.defaultTestLoader.discover(str(TESTS_DIR), pattern="test_*.py")
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=verbosity)
    result = runner.run(suite)
    run_output = stream.getvalue().strip()
    detail = (
        f"ran={result.testsRun}, failures={len(result.failures)}, "
        f"errors={len(result.errors)}, skipped={len(result.skipped)}"
    )
    if not result.wasSuccessful() and run_output:
        detail = f"{detail} | {run_output.splitlines()[-1]}"
    return [CheckResult("unit-tests", result.wasSuccessful(), _ms(start), detail)]


def run_checks(steps: Sequence[Callable[[], List[CheckResult]]]) -> List[CheckResult]:
    all_results: List[CheckResult] = []
    for step in steps:
        try:
            all_results.extend(step())
        except Exception:
            all_results.append(
                CheckResult(
                    name=f"internal:{step.__name__}",
                    passed=False,
                    duration_ms=0,
                    detail=traceback.format_exc(limit=1).strip(),
                )
            )
    return all_results


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit-friendly GameHub test runner with auto-discovery."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tests-only", action="store_true", help="run only unittest suite")
    group.add_argument("--plugins-only", action="store_true", help="run only plugin smoke checks")
    group.add_argument("--adapters-only", action="store_true", help="run only per-game adapters")
    parser.add_argument("--quiet", action="store_true", help="lower unittest verbosity")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    _print_header("GameHub Tester")
    print(f"Root: {ROOT}")

    if args.tests_only:
        steps: List[Callable[[], List[CheckResult]]] = [
            lambda: run_unit_tests(verbosity=1 if args.quiet else 2)
        ]
    elif args.plugins_only:
        steps = [run_plugin_smoke]
    elif args.adapters_only:
        steps = [run_game_adapters]
    else:
        steps = [
            run_plugin_smoke,
            run_game_adapters,
            lambda: run_unit_tests(verbosity=1 if args.quiet else 2),
        ]

    results = run_checks(steps)

    _print_header("Summary")
    for item in results:
        _print_result(item)

    failed = [item for item in results if not item.passed]
    if failed:
        print(f"\nFAILURES: {len(failed)}")
        return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
