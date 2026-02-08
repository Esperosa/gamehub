from __future__ import annotations

import argparse
import io
import os
import random
import sys
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from PIL import Image, ImageDraw
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hub.main_window import MainWindow  # noqa: E402
from hub.printing import BatchPrintDialog, VariantOption  # noqa: E402
from hub.theme import apply_theme  # noqa: E402

try:
    from PySide6.QtPdf import QPdfDocument  # type: ignore
    from PySide6.QtPdfWidgets import QPdfView  # type: ignore

    HAS_QTPDF = True
except Exception:
    HAS_QTPDF = False

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
    "piskvorky": "Piškvorky",
    "simon": "Simon",
    "slitherlink": "Slitherlink",
    "sudoku": "Sudoku",
}

ACTION_INTERVALS_S = {
    "game2048": 1.0,
    "kenken": 1.4,
    "mastermind": 1.4,
    "nonogram": 1.5,
    "othello": 1.5,
    "piskvorky": 1.4,
    "simon": 1.0,
    "slitherlink": 1.5,
    "sudoku": 1.4,
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
    process_events(app, 260)


def wait_for_plugin_open(app: QApplication, window: MainWindow, game_id: str) -> object:
    ready = wait_until(
        app,
        lambda: (
            window._active_plugin_widget is not None  # noqa: SLF001
            and window._active_plugin_page is not None  # noqa: SLF001
            and window._stack.currentWidget() == window._active_plugin_page  # noqa: SLF001
        ),
        timeout_ms=12000,
    )
    if not ready:
        raise RuntimeError(f"{game_id}: plugin page did not open.")
    return window._active_plugin_widget  # noqa: SLF001


def wait_for_game_ready(app: QApplication, game_id: str, widget: object, timeout_ms: int = 50000) -> None:
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
    ok = wait_until(app, checks[game_id], timeout_ms=timeout_ms)
    if not ok:
        raise RuntimeError(f"{game_id}: widget did not become ready in time.")
    process_events(app, 240)


def _board_of(widget: object) -> Optional[object]:
    board = getattr(widget, "board", None)
    if board is None:
        board = getattr(widget, "_board", None)
    return board


def _overlay_active(board: object) -> bool:
    visible = bool(getattr(board, "_overlay_visible", False))
    if not visible:
        return False
    opacity = float(getattr(board, "_overlay_opacity", 1.0))
    return opacity > 0.05


def is_game_busy(game_id: str, widget: object) -> bool:
    if game_id in ("kenken", "sudoku", "nonogram") and bool(getattr(widget, "_generating", False)):
        return True
    if game_id == "nonogram" and bool(getattr(widget, "_hinting", False)):
        return True
    if game_id == "slitherlink" and bool(getattr(widget, "_loading_puzzle", False)):
        return True
    if game_id == "othello" and bool(getattr(widget, "_ai_pending", False)):
        return True
    if game_id == "piskvorky" and bool(getattr(widget, "_ai_thinking", False)):
        return True

    board = _board_of(widget)
    if board is not None and _overlay_active(board):
        return True
    if game_id == "game2048" and board is not None and bool(getattr(board, "_animating", False)):
        return True
    if game_id == "piskvorky":
        if getattr(widget, "swap_phase", "none") not in ("none", "playing"):
            return True
        frame = getattr(widget, "_swap_choice_frame", None)
        if frame is not None and frame.isVisible():
            return True
    return False


def apply_medium_settings(game_id: str, widget: object) -> None:
    if game_id == "game2048":
        widget.new_game()
        return
    if game_id == "kenken":
        widget._on_size_selected("6")  # noqa: SLF001
        return
    if game_id == "mastermind":
        widget._set_difficulty("medium")  # noqa: SLF001
        widget._set_code_length(5)  # noqa: SLF001
        return
    if game_id == "nonogram":
        widget._on_size_selected("15")  # noqa: SLF001
        widget._on_diff_selected("medium")  # noqa: SLF001
        return
    if game_id == "othello":
        widget._set_difficulty("medium")  # noqa: SLF001
        return
    if game_id == "piskvorky":
        _setup_large_piskvorky(widget)
        return
    if game_id == "simon":
        widget._set_level("medium")  # noqa: SLF001
        widget.set_mode("classic")
        return
    if game_id == "slitherlink":
        widget._set_size(10)  # noqa: SLF001
        widget._set_difficulty("medium")  # noqa: SLF001
        return
    if game_id == "sudoku":
        widget._on_size_selected("9")  # noqa: SLF001
        widget._on_diff_selected("medium")  # noqa: SLF001
        return


def _setup_large_piskvorky(widget: object) -> None:
    if hasattr(widget, "_stop_ai_thread"):
        widget._stop_ai_thread()  # noqa: SLF001
    widget.n = 13
    widget.difficulty = "medium"
    widget._update_size_buttons("13")  # noqa: SLF001
    widget._update_diff_buttons("medium")  # noqa: SLF001
    widget.swap_enabled = False
    widget.swap_phase = "none"
    widget.board.on_free_place = None
    widget._ai_thinking = False
    widget.game_over = False
    widget.human = 1
    widget.bot = -1
    widget.board.reset(13, to_move=1, human=widget.human, bot=widget.bot)
    widget.board.enable()
    widget._show_start_info("Hráč")  # noqa: SLF001


def _step_game2048(widget: object, rng: random.Random, ctx: dict) -> None:
    _ = rng
    board = getattr(widget, "_board", None)
    if board is None:
        return
    keys = [Qt.Key_Left, Qt.Key_Up, Qt.Key_Right, Qt.Key_Down]
    idx = int(ctx.get("move_idx", 0))
    board.setFocus()
    QTest.keyClick(board, keys[idx % len(keys)])
    ctx["move_idx"] = idx + 1


def _step_kenken(widget: object, rng: random.Random, ctx: dict) -> None:
    _ = rng, ctx
    widget._on_hint()  # noqa: SLF001


def _step_mastermind(widget: object, rng: random.Random, ctx: dict) -> None:
    _ = rng
    board = getattr(widget, "_board", None)
    if board is None:
        return
    game = getattr(board, "game", None)
    if game is None:
        return
    if game.is_over:
        widget.new_game()
        ctx["phase"] = "hint"
        return
    phase = str(ctx.get("phase", "hint"))
    if phase == "hint":
        board.show_hint()
        ctx["phase"] = "submit"
    else:
        board.submit_guess()
        ctx["phase"] = "hint"


def _step_nonogram(widget: object, rng: random.Random, ctx: dict) -> None:
    _ = rng, ctx
    widget._on_hint()  # noqa: SLF001


def _step_othello(widget: object, rng: random.Random, ctx: dict) -> None:
    _ = ctx
    game = getattr(widget, "_game", None)
    if game is None:
        return
    if game.game_over:
        widget.new_game()
        return
    if game.current_player == getattr(widget, "_human_player", 1):
        moves = game.valid_moves(game.current_player)
        if not moves:
            return
        center = 3.5
        move = min(
            moves,
            key=lambda m: (abs(m[0] - center) + abs(m[1] - center), rng.random()),
        )
        widget._on_cell_clicked(move[0], move[1])  # noqa: SLF001
    elif not getattr(widget, "_ai_pending", False):
        widget._do_ai_move(widget._ai_task_id)  # noqa: SLF001


def _step_piskvorky(widget: object, rng: random.Random, ctx: dict) -> None:
    _ = ctx
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
        if not legal:
            return
        n = int(state.n)
        center = (n * n) // 2
        move = min(legal, key=lambda idx: (abs(idx - center), rng.random()))
        widget._on_human_move(move)  # noqa: SLF001
    else:
        widget._bot_move_async()  # noqa: SLF001


def _step_simon(widget: object, rng: random.Random, ctx: dict) -> None:
    _ = rng, ctx
    board = getattr(widget, "_board", None)
    if board is None:
        return
    game = getattr(board, "game", None)
    if game is None:
        return
    state_value = getattr(getattr(game, "state", None), "value", "")
    if state_value == "game_over":
        widget.new_game()
        return
    if state_value != "waiting":
        return
    expected = game.get_expected_sequence()
    idx = len(game.player_input)
    if idx < len(expected):
        board._on_button_click(expected[idx])  # noqa: SLF001


def _step_slitherlink(widget: object, rng: random.Random, ctx: dict) -> None:
    _ = rng, ctx
    board = getattr(widget, "_board", None)
    if board is None:
        return
    board.show_hint()


def _step_sudoku(widget: object, rng: random.Random, ctx: dict) -> None:
    _ = rng, ctx
    widget._on_hint()  # noqa: SLF001


STEP_FN: Dict[str, Callable[[object, random.Random, dict], None]] = {
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


def pixmap_to_image(
    pixmap,
    label: str,
    size: tuple[int, int],
    progress: float = 0.0,
) -> Image.Image:
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
    draw.rounded_rectangle(
        [(18, 18), (340, 74)],
        radius=12,
        fill=(15, 30, 52, 195),
        outline=(79, 216, 255, 220),
        width=2,
    )
    draw.text((34, 36), f"GameHub | {label}", fill=(230, 245, 255, 245))
    bar_x0, bar_y0, bar_x1, bar_y1 = 360, 46, size[0] - 24, 56
    draw.rounded_rectangle(
        [(bar_x0, bar_y0), (bar_x1, bar_y1)],
        radius=5,
        fill=(10, 24, 42, 140),
        outline=(66, 112, 150, 120),
        width=1,
    )
    p = max(0.0, min(1.0, float(progress)))
    fill_x = int(bar_x0 + (bar_x1 - bar_x0) * p)
    draw.rounded_rectangle(
        [(bar_x0 + 1, bar_y0 + 1), (max(bar_x0 + 2, fill_x), bar_y1 - 1)],
        radius=4,
        fill=(79, 216, 255, 175),
    )
    return image


def save_animation(frames: list[Image.Image], output: Path, fps: int) -> None:
    if not frames:
        raise RuntimeError(f"No frames produced for {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = max(1, int(1000 / fps))
    if output.suffix.lower() == ".webp":
        rgb = [frame.convert("RGB") for frame in frames]
        rgb[0].save(
            output,
            save_all=True,
            append_images=rgb[1:],
            duration=duration,
            loop=0,
            format="WEBP",
            method=6,
            quality=74,
        )
        return

    # GIF fallback.
    prepared = [frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=220) for frame in frames]
    prepared[0].save(
        output,
        save_all=True,
        append_images=prepared[1:],
        duration=duration,
        loop=0,
        optimize=True,
        disposal=2,
    )


def capture_widget_clip(
    app: QApplication,
    widget: QWidget,
    output: Path,
    label: str,
    size: tuple[int, int],
    duration_s: float,
    fps: int,
    action_fn: Optional[Callable[[dict], None]] = None,
    busy_fn: Optional[Callable[[], bool]] = None,
    action_interval_s: float = 1.25,
    initial_wait_s: float = 1.7,
) -> None:
    frame_count = max(1, int(round(duration_s * fps)))
    frame_ms = max(1, int(1000 / fps))
    frames: list[Image.Image] = []
    ctx: dict = {}
    next_action_s = initial_wait_s

    process_events(app, 260)

    for frame_idx in range(frame_count):
        elapsed_s = frame_idx / float(fps)
        while action_fn is not None and elapsed_s >= next_action_s - 1e-9:
            if busy_fn is None or not busy_fn():
                action_fn(ctx)
            next_action_s += action_interval_s
        process_events(app, frame_ms)
        pix = widget.grab()
        if pix.isNull():
            raise RuntimeError(f"Failed to capture frame for {output.name}")
        frames.append(
            pixmap_to_image(
                pixmap=pix,
                label=label,
                size=size,
                progress=(frame_idx + 1) / float(frame_count),
            )
        )

    save_animation(frames, output, fps=fps)


def _build_sudoku_variants() -> list[VariantOption]:
    labels = {"easy": "Lehká", "medium": "Střední", "hard": "Těžká"}
    out: list[VariantOption] = []
    for size in (4, 6, 9, 16):
        for diff in ("easy", "medium", "hard"):
            out.append(VariantOption(key=f"{size}:{diff}", label=f"{size}×{size} · {labels[diff]}"))
    return out


def _set_variant_count(dialog: BatchPrintDialog, key: str, value: int) -> None:
    for variant, spin in dialog._variant_inputs:  # noqa: SLF001
        if variant.key == key:
            spin.setValue(value)
            return


def capture_print_dialog_clip(
    app: QApplication,
    output: Path,
    size: tuple[int, int],
    duration_s: float,
    fps: int,
) -> None:
    dialog = BatchPrintDialog("Sudoku tisk / PDF export", _build_sudoku_variants(), default_variant_key="9:medium")
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    process_events(app, 320)

    def _action(ctx: dict) -> None:
        step = int(ctx.get("step", 0))
        if step == 0:
            _set_variant_count(dialog, "9:medium", 8)
        elif step == 1:
            _set_variant_count(dialog, "16:hard", 2)
        elif step == 2:
            _set_variant_count(dialog, "6:medium", 4)
        elif step == 3:
            idx = dialog._per_page.findData(4)  # noqa: SLF001
            if idx >= 0:
                dialog._per_page.setCurrentIndex(idx)  # noqa: SLF001
        elif step == 4:
            idx = dialog._per_page.findData(6)  # noqa: SLF001
            if idx >= 0:
                dialog._per_page.setCurrentIndex(idx)  # noqa: SLF001
        elif step == 5:
            idx = dialog._per_page.findData(9)  # noqa: SLF001
            if idx >= 0:
                dialog._per_page.setCurrentIndex(idx)  # noqa: SLF001
        ctx["step"] = step + 1

    capture_widget_clip(
        app=app,
        widget=dialog,
        output=output,
        label="Print / PDF",
        size=size,
        duration_s=duration_s,
        fps=fps,
        action_fn=_action,
        busy_fn=None,
        action_interval_s=1.15,
        initial_wait_s=1.1,
    )
    dialog.close()
    process_events(app, 140)


def _resolve_pdf_preview_path() -> Path:
    candidates = [
        ROOT / "benchmarks" / "sudoku_16x16_medium_10.pdf",
        ROOT / "docs" / "samples" / "sudoku_layout_1.pdf",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("No PDF file available for preview clip.")


def capture_pdf_preview_clip(
    app: QApplication,
    output: Path,
    size: tuple[int, int],
    duration_s: float,
    fps: int,
) -> None:
    if not HAS_QTPDF:
        raise RuntimeError("QtPdf is not available; cannot render PDF preview clip.")

    pdf_path = _resolve_pdf_preview_path()
    window = QWidget()
    window.setWindowTitle("PDF preview")
    window.resize(1280, 760)

    layout = QVBoxLayout(window)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)

    caption = QLabel(f"Náhled exportu: {pdf_path.name}")
    caption.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.88);")
    layout.addWidget(caption)

    view = QPdfView(window)
    doc = QPdfDocument(window)
    status = doc.load(str(pdf_path))
    if status != QPdfDocument.Error.None_:
        raise RuntimeError(f"Failed to load preview PDF: {pdf_path}")
    view.setDocument(doc)
    view.setPageMode(QPdfView.PageMode.MultiPage)
    view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
    layout.addWidget(view, 1)

    window.show()
    window.raise_()
    window.activateWindow()
    process_events(app, 420)

    def _action(ctx: dict) -> None:
        bar = view.verticalScrollBar()
        if bar.maximum() <= 0:
            return
        direction = int(ctx.get("direction", 1))
        step = max(120, int(bar.pageStep() * 0.42))
        nxt = bar.value() + direction * step
        if nxt >= bar.maximum():
            nxt = bar.maximum()
            direction = -1
        elif nxt <= 0:
            nxt = 0
            direction = 1
        bar.setValue(nxt)
        ctx["direction"] = direction

    capture_widget_clip(
        app=app,
        widget=window,
        output=output,
        label="PDF Preview",
        size=size,
        duration_s=duration_s,
        fps=fps,
        action_fn=_action,
        busy_fn=None,
        action_interval_s=0.9,
        initial_wait_s=1.2,
    )
    window.close()
    process_events(app, 140)


def capture_hub_clip(
    app: QApplication,
    window: MainWindow,
    plugins_by_id: Dict[str, object],
    output: Path,
    size: tuple[int, int],
    duration_s: float,
    fps: int,
) -> None:
    wait_until(app, lambda: window._stack.currentWidget() == window._home, timeout_ms=5000)  # noqa: SLF001
    process_events(app, 180)

    sequence = [("open", "sudoku"), ("home", ""), ("open", "othello"), ("home", "")]

    def _action(ctx: dict) -> None:
        idx = int(ctx.get("idx", 0))
        if idx >= len(sequence):
            return
        action, game_id = sequence[idx]
        if action == "open":
            plugin = plugins_by_id.get(game_id)
            if plugin is not None:
                window.open_plugin(plugin)
                widget = wait_for_plugin_open(app, window, game_id)
                wait_for_game_ready(app, game_id, widget, timeout_ms=25000)
        else:
            window._go_home()  # noqa: SLF001
            wait_until(app, lambda: window._stack.currentWidget() == window._home, timeout_ms=6000)  # noqa: SLF001
        ctx["idx"] = idx + 1

    capture_widget_clip(
        app=app,
        widget=window,
        output=output,
        label="Hub",
        size=size,
        duration_s=duration_s,
        fps=fps,
        action_fn=_action,
        busy_fn=None,
        action_interval_s=2.1,
        initial_wait_s=1.3,
    )

    window._go_home()  # noqa: SLF001
    wait_until(app, lambda: window._stack.currentWidget() == window._home, timeout_ms=6000)  # noqa: SLF001
    process_events(app, 160)


def capture_game_clips(
    app: QApplication,
    window: MainWindow,
    plugins_by_id: Dict[str, object],
    output_dir: Path,
    size: tuple[int, int],
    duration_s: float,
    fps: int,
    seed: int,
) -> list[Path]:
    rng = random.Random(seed)
    outputs: list[Path] = []

    for game_id in GAME_ORDER:
        plugin = plugins_by_id.get(game_id)
        if plugin is None:
            raise RuntimeError(f"Missing plugin for clip capture: {game_id}")

        window.open_plugin(plugin)
        widget = wait_for_plugin_open(app, window, game_id)
        wait_for_game_ready(app, game_id, widget)
        apply_medium_settings(game_id, widget)
        wait_for_game_ready(app, game_id, widget)

        wait_until(app, lambda: not is_game_busy(game_id, widget), timeout_ms=9000)
        process_events(app, 220)

        clip_path = output_dir / f"{game_id}.webp"

        def _busy() -> bool:
            return is_game_busy(game_id, widget)

        def _action(ctx: dict) -> None:
            STEP_FN[game_id](widget, rng, ctx)

        capture_widget_clip(
            app=app,
            widget=window,
            output=clip_path,
            label=GAME_LABELS[game_id],
            size=size,
            duration_s=duration_s,
            fps=fps,
            action_fn=_action,
            busy_fn=_busy,
            action_interval_s=ACTION_INTERVALS_S.get(game_id, 1.3),
            initial_wait_s=1.9,
        )
        outputs.append(clip_path)
        print(f"[ok] {game_id} -> {clip_path}")

        window._go_home()  # noqa: SLF001
        wait_until(app, lambda: window._stack.currentWidget() == window._home, timeout_ms=7000)  # noqa: SLF001
        process_events(app, 200)

    return outputs


def verify_outputs(paths: list[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise RuntimeError(f"Missing clip output: {path}")
        if path.stat().st_size < 120_000:
            raise RuntimeError(f"Clip looks too small: {path} ({path.stat().st_size} bytes)")


def run(
    output_dir: Path,
    duration_s: float,
    fps: int,
    seed: int,
    width: int,
    height: int,
) -> list[Path]:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    apply_theme(app, font_size=10, theme="midnight")

    window = MainWindow(app=app)
    window.resize(1600, 900)
    window.show()

    wait_for_home_ready(app, window)
    plugins_by_id = {lp.manifest.id: lp for lp in window._plugins}  # noqa: SLF001

    output_dir.mkdir(parents=True, exist_ok=True)
    produced: list[Path] = []

    hub_clip = output_dir / "hub.webp"
    capture_hub_clip(
        app=app,
        window=window,
        plugins_by_id=plugins_by_id,
        output=hub_clip,
        size=(width, height),
        duration_s=duration_s,
        fps=fps,
    )
    produced.append(hub_clip)
    print(f"[ok] hub -> {hub_clip}")

    produced.extend(
        capture_game_clips(
            app=app,
            window=window,
            plugins_by_id=plugins_by_id,
            output_dir=output_dir,
            size=(width, height),
            duration_s=duration_s,
            fps=fps,
            seed=seed,
        )
    )

    print_clip = output_dir / "print_dialog.webp"
    capture_print_dialog_clip(
        app=app,
        output=print_clip,
        size=(width, height),
        duration_s=duration_s,
        fps=fps,
    )
    produced.append(print_clip)
    print(f"[ok] print dialog -> {print_clip}")

    pdf_clip = output_dir / "pdf_preview.webp"
    capture_pdf_preview_clip(
        app=app,
        output=pdf_clip,
        size=(width, height),
        duration_s=duration_s,
        fps=fps,
    )
    produced.append(pdf_clip)
    print(f"[ok] pdf preview -> {pdf_clip}")

    verify_outputs(produced)

    window.close()
    process_events(app, 180)
    return produced


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate calm 8s gameplay/preview clips for README "
            "(Hub, games, print dialog, PDF preview)."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "docs" / "media" / "clips",
        help="Destination directory for gameplay WebP clips.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=8.0,
        help="Clip duration per scene in seconds.",
    )
    parser.add_argument("--fps", type=int, default=10, help="Frames per second.")
    parser.add_argument("--seed", type=int, default=20260208, help="Random seed for deterministic behavior.")
    parser.add_argument("--width", type=int, default=1280, help="Clip frame width.")
    parser.add_argument("--height", type=int, default=720, help="Clip frame height.")
    args = parser.parse_args()

    if "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "windows"

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
