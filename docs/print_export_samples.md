# Print Export Samples

Tento dokument drží transparentní přehled ukázkových exportů a jak je reprodukovat.

## Co je v repozitáři

- Print dialog screenshoty:
  - `docs/media/print_dialog_sudoku.png`
  - `docs/media/print_dialog_kenken.png`
  - `docs/media/print_dialog_slitherlink.png`
- PDF sample exporty layoutů:
  - Sudoku: `docs/samples/sudoku_layout_{1,2,4,6,9}.pdf`
  - KenKen: `docs/samples/kenken_layout_{1,2,4,6,9}.pdf`
  - Slitherlink: `docs/samples/slitherlink_layout_{1,2,4,6,9}.pdf`

## Reprodukce

1. Aktualizace herních screenshotů:

```bash
python scripts/capture_screenshots.py --output-dir docs/media
```

2. Vygenerování print dialog screenshotů a PDF sample exportů:

```bash
python scripts/generate_print_assets.py --media-dir docs/media --sample-dir docs/samples
```

Skript použije stejné render funkce jako runtime tisk:

- `games/sudoku/ui.py::_draw_print_sudoku`
- `games/kenken/ui.py::_draw_print_kenken`
- `games/slitherlink/ui.py::_draw_print_slitherlink`

a stejné layout rozložení přes `hub/printing.py::draw_square_batch`.

