from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
from pathlib import Path
from typing import Iterable, Sequence

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hub.printing import BatchPrintDialog, VariantOption, create_output_printer, draw_square_batch  # noqa: E402
from hub.theme import apply_theme  # noqa: E402


def _load_local_module(module_name: str, path: Path):
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_sudoku_ui = _load_local_module("sudoku_ui_print_assets", ROOT / "games" / "sudoku" / "ui.py")
_kenken_ui = _load_local_module("kenken_ui_print_assets", ROOT / "games" / "kenken" / "ui.py")
_slitherlink_ui = _load_local_module("slitherlink_ui_print_assets", ROOT / "games" / "slitherlink" / "ui.py")

_draw_print_sudoku = _sudoku_ui._draw_print_sudoku
create_sudoku_puzzle = _sudoku_ui.create_puzzle

_draw_print_kenken = _kenken_ui._draw_print_kenken
create_kenken_puzzle = _kenken_ui.create_puzzle

_draw_print_slitherlink = _slitherlink_ui._draw_print_slitherlink
create_slitherlink_puzzle = _slitherlink_ui.create_puzzle


def _process_events(app: QApplication, ms: int = 220) -> None:
    deadline = time.perf_counter() + (ms / 1000.0)
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.01)


def _build_sudoku_variants() -> list[VariantOption]:
    out: list[VariantOption] = []
    labels = {"easy": "Lehká", "medium": "Střední", "hard": "Těžká"}
    for size in (4, 6, 9, 16):
        for diff in ("easy", "medium", "hard"):
            out.append(
                VariantOption(
                    key=f"{size}:{diff}",
                    label=f"{size}×{size} · {labels[diff]}",
                )
            )
    return out


def _build_kenken_variants() -> list[VariantOption]:
    return [VariantOption(key=str(size), label=f"{size}×{size}") for size in range(4, 10)]


def _build_slitherlink_variants() -> list[VariantOption]:
    out: list[VariantOption] = []
    labels = {"easy": "Lehká", "medium": "Střední", "hard": "Těžká"}
    for size in (7, 10, 15):
        for diff in ("easy", "medium", "hard"):
            out.append(
                VariantOption(
                    key=f"{size}:{diff}",
                    label=f"{size}×{size} · {labels[diff]}",
                )
            )
    return out


def _capture_dialog(
    app: QApplication,
    output: Path,
    title: str,
    variants: Sequence[VariantOption],
    default_key: str,
    selected_key: str,
    selected_count: int,
    per_page: int,
) -> None:
    dlg = BatchPrintDialog(title, variants, default_variant_key=default_key)
    for variant, spin in dlg._variant_inputs:  # noqa: SLF001
        if variant.key == selected_key:
            spin.setValue(selected_count)
            break
    idx = dlg._per_page.findData(per_page)  # noqa: SLF001
    if idx >= 0:
        dlg._per_page.setCurrentIndex(idx)  # noqa: SLF001

    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    _process_events(app, 320)

    pix = dlg.grab()
    if pix.isNull():
        raise RuntimeError(f"Failed to capture dialog screenshot: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if not pix.save(str(output)):
        raise RuntimeError(f"Failed to save dialog screenshot: {output}")

    dlg.close()
    _process_events(app, 120)


def _build_sudoku_items(count: int) -> list[tuple[object, str]]:
    variants = [
        (4, "easy"),
        (6, "medium"),
        (9, "easy"),
        (9, "medium"),
        (6, "hard"),
    ]
    out: list[tuple[object, str]] = []
    for i in range(count):
        size, diff = variants[i % len(variants)]
        state = create_sudoku_puzzle(size, diff)
        out.append((state, f"{size}×{size} · {diff}"))
    return out


def _build_kenken_items(count: int) -> list[tuple[object, str]]:
    sizes = [4, 5, 6, 7, 8, 9]
    out: list[tuple[object, str]] = []
    for i in range(count):
        size = sizes[i % len(sizes)]
        state = create_kenken_puzzle(size)
        out.append((state, f"{size}×{size}"))
    return out


def _build_slitherlink_items(count: int) -> list[tuple[object, str]]:
    variants = [
        (7, "easy"),
        (10, "easy"),
        (10, "medium"),
        (15, "easy"),
        (7, "hard"),
    ]
    out: list[tuple[object, str]] = []
    for i in range(count):
        size, diff = variants[i % len(variants)]
        state = create_slitherlink_puzzle(size, diff)
        out.append((state, f"{size}×{size} · {diff}"))
    return out


def _render_layout_pdfs(
    sample_dir: Path,
    game_name: str,
    per_page_values: Iterable[int],
    make_items,
    draw_fn,
) -> list[Path]:
    out: list[Path] = []
    for per_page in per_page_values:
        pdf_path = sample_dir / f"{game_name}_layout_{per_page}.pdf"
        items = make_items(per_page)
        printer, _ = create_output_printer(
            parent=None,
            document_name=f"BrainHub {game_name} sample layout {per_page}",
            output_mode="pdf",
            pdf_path=str(pdf_path),
        )
        if printer is None:
            raise RuntimeError(f"Failed to create PDF printer for {pdf_path}")
        draw_square_batch(printer, items, per_page, draw_fn)
        out.append(pdf_path)
    return out


def _verify_paths(paths: Sequence[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise RuntimeError(f"Missing output file: {path}")
        if path.stat().st_size < 4_000:
            raise RuntimeError(f"Output file seems too small: {path} ({path.stat().st_size} bytes)")


def run(media_dir: Path, sample_dir: Path) -> None:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    apply_theme(app, font_size=10, theme="midnight")

    produced: list[Path] = []

    # Dialog screenshots
    _capture_dialog(
        app=app,
        output=media_dir / "print_dialog_sudoku.png",
        title="Sudoku tisk",
        variants=_build_sudoku_variants(),
        default_key="9:medium",
        selected_key="9:medium",
        selected_count=12,
        per_page=4,
    )
    produced.append(media_dir / "print_dialog_sudoku.png")

    _capture_dialog(
        app=app,
        output=media_dir / "print_dialog_kenken.png",
        title="KenKen tisk",
        variants=_build_kenken_variants(),
        default_key="6",
        selected_key="6",
        selected_count=10,
        per_page=6,
    )
    produced.append(media_dir / "print_dialog_kenken.png")

    _capture_dialog(
        app=app,
        output=media_dir / "print_dialog_slitherlink.png",
        title="Slitherlink tisk",
        variants=_build_slitherlink_variants(),
        default_key="10:medium",
        selected_key="10:medium",
        selected_count=9,
        per_page=9,
    )
    produced.append(media_dir / "print_dialog_slitherlink.png")

    # PDF samples
    per_page_values = (1, 2, 4, 6, 9)
    produced.extend(
        _render_layout_pdfs(
            sample_dir=sample_dir,
            game_name="sudoku",
            per_page_values=per_page_values,
            make_items=_build_sudoku_items,
            draw_fn=_draw_print_sudoku,
        )
    )
    produced.extend(
        _render_layout_pdfs(
            sample_dir=sample_dir,
            game_name="kenken",
            per_page_values=per_page_values,
            make_items=_build_kenken_items,
            draw_fn=_draw_print_kenken,
        )
    )
    produced.extend(
        _render_layout_pdfs(
            sample_dir=sample_dir,
            game_name="slitherlink",
            per_page_values=per_page_values,
            make_items=_build_slitherlink_items,
            draw_fn=_draw_print_slitherlink,
        )
    )

    _verify_paths(produced)
    for file in produced:
        print(f"[ok] {file}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate print-dialog screenshots and PDF sample exports."
    )
    parser.add_argument(
        "--media-dir",
        type=Path,
        default=ROOT / "docs" / "media",
        help="Directory for print dialog screenshots.",
    )
    parser.add_argument(
        "--sample-dir",
        type=Path,
        default=ROOT / "docs" / "samples",
        help="Directory for sample PDF exports.",
    )
    args = parser.parse_args()

    if "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "windows"

    args.media_dir.mkdir(parents=True, exist_ok=True)
    args.sample_dir.mkdir(parents=True, exist_ok=True)
    run(args.media_dir, args.sample_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
