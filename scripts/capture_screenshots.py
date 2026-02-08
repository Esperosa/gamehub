from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Callable

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hub.main_window import MainWindow  # noqa: E402
from hub.theme import apply_theme  # noqa: E402

GAME_SCREENSHOTS = {
    "game2048": "game2048.png",
    "kenken": "kenken.png",
    "mastermind": "mastermind.png",
    "nonogram": "nonogram.png",
    "othello": "othello.png",
    "piskvorky": "piskvorky.png",
    "simon": "simon.png",
    "slitherlink": "slitherlink.png",
    "sudoku": "sudoku.png",
}


def process_events(app: QApplication, ms: int) -> None:
    deadline = time.perf_counter() + (ms / 1000.0)
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.01)


def wait_until(
    app: QApplication,
    predicate: Callable[[], bool],
    timeout_ms: int,
    step_ms: int = 20,
) -> bool:
    deadline = time.perf_counter() + (timeout_ms / 1000.0)
    while time.perf_counter() < deadline:
        if predicate():
            return True
        process_events(app, step_ms)
    return bool(predicate())


def capture_window(window: MainWindow, output: Path) -> None:
    process_events(QApplication.instance(), 220)
    pix = window.grab()
    if pix.isNull():
        raise RuntimeError(f"Failed to grab screenshot for: {output.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if not pix.save(str(output)):
        raise RuntimeError(f"Failed to save screenshot to: {output}")


def wait_for_home_ready(app: QApplication, window: MainWindow) -> None:
    ok = wait_until(
        app,
        lambda: (
            window._home is not None  # noqa: SLF001
            and window._stack.currentWidget() == window._home  # noqa: SLF001
            and len(window._plugins) >= len(GAME_SCREENSHOTS)  # noqa: SLF001
        ),
        timeout_ms=15000,
    )
    if not ok:
        raise RuntimeError("Hub home page did not finish loading in time.")
    process_events(app, 500)


def wait_for_game_ready(app: QApplication, game_id: str, widget: object) -> None:
    def _ready_default() -> bool:
        return True

    checks: dict[str, Callable[[], bool]] = {
        "kenken": lambda: (
            not getattr(widget, "_generating", True)
            and getattr(getattr(widget, "board", None), "state", None) is not None
        ),
        "slitherlink": lambda: (
            not getattr(widget, "_loading_puzzle", True)
            and getattr(getattr(widget, "_board", None), "state", None) is not None
        ),
        "sudoku": lambda: (
            getattr(getattr(widget, "board", None), "state", None) is not None
            and "Generuji" not in getattr(getattr(widget, "lbl_status", None), "text", lambda: "")()
        ),
        "othello": lambda: getattr(widget, "_game", None) is not None,
        "piskvorky": lambda: getattr(getattr(widget, "board", None), "state", None) is not None,
    }

    check = checks.get(game_id, _ready_default)
    ok = wait_until(app, check, timeout_ms=25000)
    if not ok:
        raise RuntimeError(f"{game_id}: widget did not become ready in time.")
    process_events(app, 300)


def nudge_game_state(app: QApplication, game_id: str, widget: object) -> None:
    if game_id == "game2048":
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        board = getattr(widget, "_board", None)
        game = getattr(board, "game", None)
        if board is not None and game is not None and game.moves == 0:
            board.setFocus()
            process_events(app, 60)
            for key in (Qt.Key_Left, Qt.Key_Up, Qt.Key_Right, Qt.Key_Down):
                before = game.moves
                QTest.keyClick(board, key)
                wait_until(
                    app,
                    lambda: not getattr(board, "_animating", False),
                    timeout_ms=2000,
                )
                process_events(app, 140)
                game = getattr(board, "game", None)
                if game is not None and game.moves > before:
                    break

    elif game_id == "kenken":
        if hasattr(widget, "_on_hint"):
            widget._on_hint()  # noqa: SLF001
            process_events(app, 220)

    elif game_id == "mastermind":
        board = getattr(widget, "_board", None)
        if board is not None:
            board.show_hint()
            process_events(app, 120)
            board.submit_guess()
            process_events(app, 180)

    elif game_id == "nonogram":
        if hasattr(widget, "_on_hint"):
            widget._on_hint()  # noqa: SLF001
            process_events(app, 220)

    elif game_id == "othello":
        game = getattr(widget, "_game", None)
        if game is not None and game.move_count == 0:
            if game.current_player == getattr(widget, "_human_player", 1):
                moves = game.valid_moves(game.current_player)
                if moves:
                    widget._on_cell_clicked(*moves[0])  # noqa: SLF001
            else:
                widget._do_ai_move()  # noqa: SLF001
            process_events(app, 450)

    elif game_id == "piskvorky":
        board = getattr(widget, "board", None)
        if board is None:
            return
        if hasattr(board, "_hide_overlay_immediate"):
            board._hide_overlay_immediate()  # noqa: SLF001
        process_events(app, 160)

        state = getattr(board, "state", None)
        if state is not None and state.move_count() == 0:
            if state.to_move == getattr(widget, "human", 1):
                center = (state.n * state.n) // 2
                move = center if state.board[center] == 0 else state.legal_moves()[0]
                widget._on_human_move(move)  # noqa: SLF001
            else:
                widget._bot_move_async()  # noqa: SLF001
                wait_until(app, lambda: board.state.move_count() > 0, timeout_ms=8000)
        wait_until(app, lambda: not getattr(widget, "_ai_thinking", False), timeout_ms=8000)
        process_events(app, 350)
        if hasattr(board, "_hide_overlay_immediate"):
            board._hide_overlay_immediate()  # noqa: SLF001

    elif game_id == "simon":
        if hasattr(widget, "new_game"):
            widget.new_game()
        process_events(app, 900)

    elif game_id == "slitherlink":
        board = getattr(widget, "_board", None)
        if board is not None and getattr(board, "state", None) is not None:
            board.show_hint()
            process_events(app, 250)

    elif game_id == "sudoku":
        if hasattr(widget, "_on_hint"):
            widget._on_hint()  # noqa: SLF001
            process_events(app, 250)


def verify_images(paths: list[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise RuntimeError(f"Missing screenshot: {path}")
        if path.stat().st_size < 12_000:
            raise RuntimeError(f"Screenshot looks too small/empty: {path}")
        img = QImage(str(path))
        if img.isNull():
            raise RuntimeError(f"Screenshot is not a valid image: {path}")
        if img.width() < 1200 or img.height() < 700:
            raise RuntimeError(f"Screenshot has too small resolution: {path} ({img.width()}x{img.height()})")


def run(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    apply_theme(app, font_size=10, theme="midnight")

    window = MainWindow(app=app)
    window.resize(1600, 900)
    window.show()

    wait_for_home_ready(app, window)

    generated: list[Path] = []

    home_path = output_dir / "home.png"
    capture_window(window, home_path)
    generated.append(home_path)
    print(f"[ok] home -> {home_path}")

    plugins_by_id = {lp.manifest.id: lp for lp in window._plugins}  # noqa: SLF001

    for game_id, filename in GAME_SCREENSHOTS.items():
        plugin = plugins_by_id.get(game_id)
        if plugin is None:
            raise RuntimeError(f"Missing plugin: {game_id}")

        window.open_plugin(plugin)
        ready = wait_until(
            app,
            lambda: (
                window._active_plugin_widget is not None  # noqa: SLF001
                and window._active_plugin_page is not None  # noqa: SLF001
                and window._stack.currentWidget() == window._active_plugin_page  # noqa: SLF001
            ),
            timeout_ms=8000,
        )
        if not ready:
            raise RuntimeError(f"{game_id}: plugin page did not open.")

        widget = window._active_plugin_widget  # noqa: SLF001
        wait_for_game_ready(app, game_id, widget)
        nudge_game_state(app, game_id, widget)
        process_events(app, 500)

        shot_path = output_dir / filename
        capture_window(window, shot_path)
        generated.append(shot_path)
        print(f"[ok] {game_id} -> {shot_path}")

        window._go_home()  # noqa: SLF001
        wait_until(app, lambda: window._stack.currentWidget() == window._home, timeout_ms=5000)  # noqa: SLF001
        process_events(app, 220)

    verify_images(generated)
    print(f"[done] generated {len(generated)} screenshots in {output_dir}")

    window.close()
    process_events(app, 200)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture hub and game screenshots from the current local build."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "docs" / "media",
        help="Output directory for PNG screenshots (default: docs/media).",
    )
    args = parser.parse_args()

    if "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "windows"

    run(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
