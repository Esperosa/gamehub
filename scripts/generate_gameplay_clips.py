from __future__ import annotations

import argparse
import io
import os
import random
import sys
import time
from pathlib import Path
from typing import Callable, Dict

from PIL import Image, ImageDraw
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hub.main_window import MainWindow  # noqa: E402
from hub.theme import apply_theme  # noqa: E402

GAME_ORDER = [
    "game2048",
    "kenken",
    "mastermind",
    "nonogram",
    "othello",
    "piskvorky",
    "simon",
    "slitherlink",
    "sudoku",
]

GAME_LABELS = {
    "game2048": "2048",
    "kenken": "KenKen",
    "mastermind": "Mastermind",
    "nonogram": "Nonogram",
    "othello": "Othello",
    "piskvorky": "Piskvorky",
    "simon": "Simon",
    "slitherlink": "Slitherlink",
    "sudoku": "Sudoku",
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
    step_ms: int = 25,
) -> bool:
    deadline = time.perf_counter() + (timeout_ms / 1000.0)
    while time.perf_counter() < deadline:
        if predicate():
            return True
        process_events(app, step_ms)
    return bool(predicate())


def wait_for_home_ready(app: QApplication, window: MainWindow) -> None:
    ok = wait_until(
        app,
        lambda: (
            window._home is not None  # noqa: SLF001
            and window._stack.currentWidget() == window._home  # noqa: SLF001
            and len(window._plugins) >= len(GAME_ORDER)  # noqa: SLF001
        ),
        timeout_ms=18000,
    )
    if not ok:
        raise RuntimeError("Hub home page did not finish loading in time.")
    process_events(app, 300)


def wait_for_plugin_open(app: QApplication, window: MainWindow, game_id: str) -> object:
    ready = wait_until(
        app,
        lambda: (
            window._active_plugin_widget is not None  # noqa: SLF001
            and window._active_plugin_page is not None  # noqa: SLF001
            and window._stack.currentWidget() == window._active_plugin_page  # noqa: SLF001
        ),
        timeout_ms=10000,
    )
    if not ready:
        raise RuntimeError(f"{game_id}: plugin page did not open.")
    return window._active_plugin_widget  # noqa: SLF001


def wait_for_game_ready(app: QApplication, game_id: str, widget: object, timeout_ms: int = 35000) -> None:
    checks: Dict[str, Callable[[], bool]] = {
        "game2048": lambda: getattr(getattr(widget, "_board", None), "game", None) is not None,
        "kenken": lambda: (
            not getattr(widget, "_generating", True)
            and getattr(getattr(widget, "board", None), "state", None) is not None
        ),
        "mastermind": lambda: getattr(getattr(widget, "_board", None), "game", None) is not None,
        "nonogram": lambda: (
            not getattr(widget, "_generating", True)
            and getattr(getattr(widget, "board", None), "state", None) is not None
        ),
        "othello": lambda: getattr(widget, "_game", None) is not None,
        "piskvorky": lambda: getattr(getattr(widget, "board", None), "state", None) is not None,
        "simon": lambda: getattr(getattr(widget, "_board", None), "game", None) is not None,
        "slitherlink": lambda: (
            not getattr(widget, "_loading_puzzle", True)
            and getattr(getattr(widget, "_board", None), "state", None) is not None
        ),
        "sudoku": lambda: (
            not getattr(widget, "_generating", True)
            and getattr(getattr(widget, "board", None), "state", None) is not None
        ),
    }
    check = checks[game_id]
    ok = wait_until(app, check, timeout_ms=timeout_ms)
    if not ok:
        raise RuntimeError(f"{game_id}: widget did not become ready in time.")
    process_events(app, 250)


def apply_random_settings(game_id: str, widget: object, rng: random.Random) -> None:
    if game_id == "game2048":
        widget.new_game()
        return
    if game_id == "kenken":
        widget._on_size_selected(rng.choice(["5", "6", "7", "8", "9"]))  # noqa: SLF001
        return
    if game_id == "mastermind":
        widget._set_difficulty(rng.choice(["easy", "medium", "hard"]))  # noqa: SLF001
        widget._set_code_length(rng.choice([4, 5, 6]))  # noqa: SLF001
        return
    if game_id == "nonogram":
        widget._on_size_selected(rng.choice(["5", "10", "15"]))  # noqa: SLF001
        widget._on_diff_selected(rng.choice(["easy", "medium", "hard"]))  # noqa: SLF001
        return
    if game_id == "othello":
        widget._set_difficulty(rng.choice(["easy", "medium", "hard"]))  # noqa: SLF001
        return
    if game_id == "piskvorky":
        widget._on_size_selected(rng.choice(["3", "8", "13"]))  # noqa: SLF001
        widget._on_diff_selected(rng.choice(["easy", "medium", "hard"]))  # noqa: SLF001
        return
    if game_id == "simon":
        widget._set_level(rng.choice(["easy", "medium", "hard"]))  # noqa: SLF001
        widget.set_mode(rng.choice(["classic", "reverse", "speed", "chaos"]))
        return
    if game_id == "slitherlink":
        widget._set_size(rng.choice([7, 10, 15]))  # noqa: SLF001
        widget._set_difficulty(rng.choice(["easy", "medium", "hard"]))  # noqa: SLF001
        return
    if game_id == "sudoku":
        widget._on_size_selected(rng.choice(["4", "6", "9"]))  # noqa: SLF001
        widget._on_diff_selected(rng.choice(["easy", "medium", "hard"]))  # noqa: SLF001
        return


def _step_game2048(widget: object, rng: random.Random) -> None:
    board = getattr(widget, "_board", None)
    if board is None:
        return
    board.setFocus()
    key = rng.choice([Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down])
    QTest.keyClick(board, key)


def _step_kenken(widget: object, rng: random.Random) -> None:
    _ = rng
    if getattr(widget, "_generating", False):
        return
    if getattr(getattr(widget, "board", None), "state", None) is None:
        return
    widget._on_hint()  # noqa: SLF001


def _step_mastermind(widget: object, rng: random.Random) -> None:
    _ = rng
    board = getattr(widget, "_board", None)
    if board is None:
        return
    game = getattr(board, "game", None)
    if game is None or game.is_over:
        widget.new_game()
        return
    board.show_hint()
    board.submit_guess()


def _step_nonogram(widget: object, rng: random.Random) -> None:
    _ = rng
    if getattr(widget, "_generating", False) or getattr(widget, "_hinting", False):
        return
    widget._on_hint()  # noqa: SLF001


def _step_othello(widget: object, rng: random.Random) -> None:
    game = getattr(widget, "_game", None)
    if game is None:
        return
    if game.game_over:
        widget.new_game()
        return
    if game.current_player == getattr(widget, "_human_player", 1):
        moves = game.valid_moves(game.current_player)
        if moves:
            row, col = rng.choice(moves)
            widget._on_cell_clicked(row, col)  # noqa: SLF001
    else:
        if not getattr(widget, "_ai_pending", False):
            widget._do_ai_move(widget._ai_task_id)  # noqa: SLF001


def _step_piskvorky(widget: object, rng: random.Random) -> None:
    board = getattr(widget, "board", None)
    if board is None:
        return
    state = getattr(board, "state", None)
    if state is None:
        return
    if getattr(widget, "game_over", False):
        widget.new_game()
        return
    if state.to_move == getattr(widget, "human", 1):
        legal = state.legal_moves()
        if legal:
            widget._on_human_move(rng.choice(legal))  # noqa: SLF001
    else:
        widget._bot_move_async()  # noqa: SLF001


def _step_simon(widget: object, rng: random.Random) -> None:
    board = getattr(widget, "_board", None)
    if board is None:
        return
    game = getattr(board, "game", None)
    if game is None:
        widget.new_game()
        return
    state_value = getattr(getattr(game, "state", None), "value", "")
    if state_value == "game_over":
        widget.new_game()
        return
    if state_value != "waiting":
        return
    expected = game.get_expected_sequence()
    index = len(game.player_input)
    if index < len(expected):
        board._on_button_click(expected[index])  # noqa: SLF001
    elif expected:
        board._on_button_click(rng.choice(expected))  # noqa: SLF001


def _step_slitherlink(widget: object, rng: random.Random) -> None:
    _ = rng
    if getattr(widget, "_loading_puzzle", False):
        return
    board = getattr(widget, "_board", None)
    if board is None or getattr(board, "state", None) is None:
        return
    board.show_hint()


def _step_sudoku(widget: object, rng: random.Random) -> None:
    _ = rng
    if getattr(widget, "_generating", False):
        return
    board = getattr(widget, "board", None)
    if board is None or getattr(board, "state", None) is None:
        return
    widget._on_hint()  # noqa: SLF001


STEP_FN: Dict[str, Callable[[object, random.Random], None]] = {
    "game2048": _step_game2048,
    "kenken": _step_kenken,
    "mastermind": _step_mastermind,
    "nonogram": _step_nonogram,
    "othello": _step_othello,
    "piskvorky": _step_piskvorky,
    "simon": _step_simon,
    "slitherlink": _step_slitherlink,
    "sudoku": _step_sudoku,
}


def pixmap_to_image(pixmap, label: str, size: tuple[int, int]) -> Image.Image:
    data = QByteArray()
    buffer = QBuffer(data)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Failed to open image buffer for clip frame.")
    try:
        if not pixmap.save(buffer, "PNG"):
            raise RuntimeError("Failed to encode frame from window pixmap.")
    finally:
        buffer.close()

    image = Image.open(io.BytesIO(bytes(data))).convert("RGB")
    image = image.resize(size, Image.Resampling.LANCZOS)

    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle([(20, 20), (300, 68)], radius=12, fill=(16, 30, 52, 190), outline=(79, 216, 255, 210), width=2)
    draw.text((34, 34), f"GameHub | {label}", fill=(230, 245, 255, 245))
    return image


def save_gif(frames: list[Image.Image], output: Path, fps: int) -> None:
    if not frames:
        raise RuntimeError(f"No frames produced for {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    prepared = [frame.convert("P", palette=Image.Palette.ADAPTIVE) for frame in frames]
    prepared[0].save(
        output,
        save_all=True,
        append_images=prepared[1:],
        duration=max(1, int(1000 / fps)),
        loop=0,
        optimize=True,
        disposal=2,
    )


def capture_clip(
    app: QApplication,
    window: MainWindow,
    game_id: str,
    widget: object,
    output: Path,
    rng: random.Random,
    duration_s: float,
    fps: int,
    size: tuple[int, int],
) -> None:
    frame_count = max(1, int(duration_s * fps))
    frame_interval_ms = max(1, int(1000 / fps))
    step_fn = STEP_FN[game_id]

    frames: list[Image.Image] = []
    for idx in range(frame_count):
        if idx % 2 == 0:
            step_fn(widget, rng)
        process_events(app, int(frame_interval_ms * 0.45))
        pix = window.grab()
        if pix.isNull():
            raise RuntimeError(f"{game_id}: failed to capture frame.")
        frames.append(pixmap_to_image(pix, GAME_LABELS[game_id], size=size))
        process_events(app, int(frame_interval_ms * 0.55))

    save_gif(frames, output, fps=fps)


def verify_outputs(paths: list[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise RuntimeError(f"Missing clip output: {path}")
        if path.stat().st_size < 60_000:
            raise RuntimeError(f"Clip looks too small: {path} ({path.stat().st_size} bytes)")


def run(output_dir: Path, duration_s: float, fps: int, seed: int, width: int, height: int) -> list[Path]:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    apply_theme(app, font_size=10, theme="midnight")

    rng = random.Random(seed)
    window = MainWindow(app=app)
    window.resize(1600, 900)
    window.show()

    wait_for_home_ready(app, window)

    plugins_by_id = {lp.manifest.id: lp for lp in window._plugins}  # noqa: SLF001
    outputs: list[Path] = []

    for game_id in GAME_ORDER:
        plugin = plugins_by_id.get(game_id)
        if plugin is None:
            raise RuntimeError(f"Missing plugin for clip capture: {game_id}")

        window.open_plugin(plugin)
        widget = wait_for_plugin_open(app, window, game_id)
        wait_for_game_ready(app, game_id, widget)
        apply_random_settings(game_id, widget, rng)
        wait_for_game_ready(app, game_id, widget)

        clip_path = output_dir / f"{game_id}.gif"
        capture_clip(
            app=app,
            window=window,
            game_id=game_id,
            widget=widget,
            output=clip_path,
            rng=rng,
            duration_s=duration_s,
            fps=fps,
            size=(width, height),
        )
        outputs.append(clip_path)
        print(f"[ok] {game_id} -> {clip_path}")

        window._go_home()  # noqa: SLF001
        wait_until(app, lambda: window._stack.currentWidget() == window._home, timeout_ms=6000)  # noqa: SLF001
        process_events(app, 220)

    verify_outputs(outputs)
    window.close()
    process_events(app, 150)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate short gameplay clips for all GameHub games.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "docs" / "media" / "clips",
        help="Destination directory for gameplay GIF clips.",
    )
    parser.add_argument("--seconds", type=float, default=4.0, help="Clip duration per game in seconds.")
    parser.add_argument("--fps", type=int, default=8, help="Frames per second.")
    parser.add_argument("--seed", type=int, default=20260208, help="Random seed for game setting selection.")
    parser.add_argument("--width", type=int, default=960, help="Clip frame width.")
    parser.add_argument("--height", type=int, default=540, help="Clip frame height.")
    args = parser.parse_args()

    if "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "windows"

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = run(
        output_dir=args.output_dir,
        duration_s=args.seconds,
        fps=args.fps,
        seed=args.seed,
        width=args.width,
        height=args.height,
    )
    for path in outputs:
        print(f"[done] {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
