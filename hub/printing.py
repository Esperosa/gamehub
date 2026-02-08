from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple, TypeVar

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


T = TypeVar("T")


@dataclass(frozen=True)
class VariantOption:
    key: str
    label: str


class BatchPrintDialog(QDialog):
    """Collects batch print settings for game puzzle generation/export."""

    def __init__(
        self,
        title: str,
        variants: Sequence[VariantOption],
        default_variant_key: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(520, 640)

        self._variant_inputs: List[Tuple[VariantOption, QSpinBox]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        variants_box = QGroupBox("Počet úloh podle varianty")
        variants_lay = QVBoxLayout(variants_box)
        variants_lay.setContentsMargins(10, 10, 10, 10)
        variants_lay.setSpacing(6)

        for variant in variants:
            row = QHBoxLayout()
            row.setSpacing(8)

            lbl = QLabel(variant.label)
            control = QWidget()
            control.setObjectName("SpinEditor")
            control_lay = QHBoxLayout(control)
            control_lay.setContentsMargins(0, 0, 0, 0)
            control_lay.setSpacing(0)

            spin = QSpinBox(control)
            spin.setRange(0, 500)
            spin.setSingleStep(1)
            spin.setButtonSymbols(QSpinBox.NoButtons)
            spin.setAlignment(Qt.AlignCenter)
            spin.setFixedSize(72, 30)
            spin.setValue(0)

            stepper = QWidget(control)
            stepper.setObjectName("SpinStepper")
            stepper_lay = QVBoxLayout(stepper)
            stepper_lay.setContentsMargins(0, 0, 0, 0)
            stepper_lay.setSpacing(0)

            btn_plus = QPushButton("+", stepper)
            btn_plus.setObjectName("SpinStepUp")
            btn_plus.setFixedSize(24, 15)
            btn_plus.setAutoRepeat(True)
            btn_plus.setFocusPolicy(Qt.NoFocus)
            btn_plus.clicked.connect(spin.stepUp)

            btn_minus = QPushButton("-", stepper)
            btn_minus.setObjectName("SpinStepDown")
            btn_minus.setFixedSize(24, 15)
            btn_minus.setAutoRepeat(True)
            btn_minus.setFocusPolicy(Qt.NoFocus)
            btn_minus.clicked.connect(spin.stepDown)

            stepper_lay.addWidget(btn_plus)
            stepper_lay.addWidget(btn_minus)

            control_lay.addWidget(spin)
            control_lay.addWidget(stepper)

            row.addWidget(lbl, 1)
            row.addWidget(control, 0)
            variants_lay.addLayout(row)
            self._variant_inputs.append((variant, spin))

        root.addWidget(variants_box)

        options_box = QGroupBox("Tisk")
        options_lay = QFormLayout(options_box)
        options_lay.setContentsMargins(10, 10, 10, 10)
        options_lay.setSpacing(8)

        self._per_page = QComboBox()
        self._per_page.addItem("1 na stránku", 1)
        self._per_page.addItem("2 na stránku", 2)
        self._per_page.addItem("4 na stránku", 4)
        self._per_page.addItem("6 na stránku", 6)
        self._per_page.addItem("9 na stránku", 9)
        self._per_page.setCurrentIndex(0)  # 1 per page by default
        options_lay.addRow("Rozložení:", self._per_page)

        self._output = QComboBox()
        self._output.addItem("PDF soubor", "pdf")
        self._output.addItem("Tiskárna", "printer")
        self._output.setCurrentIndex(0)
        options_lay.addRow("Výstup:", self._output)

        self._pdf_path = QLineEdit()
        default_name = f"brainhub_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        downloads_dir = Path.home() / "Downloads"
        self._pdf_path.setText(str(downloads_dir / default_name))
        self._pdf_browse = QPushButton("Vybrat…")
        self._pdf_browse.clicked.connect(self._browse_pdf_path)

        pdf_row = QHBoxLayout()
        pdf_row.setContentsMargins(0, 0, 0, 0)
        pdf_row.setSpacing(6)
        pdf_row.addWidget(self._pdf_path, 1)
        pdf_row.addWidget(self._pdf_browse, 0)

        self._pdf_row_widget = QWidget()
        self._pdf_row_widget.setLayout(pdf_row)
        options_lay.addRow("PDF soubor:", self._pdf_row_widget)

        self._output.currentIndexChanged.connect(self._update_pdf_visibility)
        self._update_pdf_visibility()

        root.addWidget(options_box)

        self._info = QLabel("Poznámka: výstup je čistě černobílý a optimalizovaný pro A4.")
        self._info.setStyleSheet("color: rgba(255,255,255,0.65); font-size: 11px;")
        root.addWidget(self._info)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        if ok_btn is not None:
            ok_btn.setText("Spustit")
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if cancel_btn is not None:
            cancel_btn.setText("Zrušit")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _update_pdf_visibility(self) -> None:
        self._pdf_row_widget.setVisible(self.output_mode() == "pdf")

    def _browse_pdf_path(self) -> None:
        current = self._pdf_path.text().strip() or str(Path.home())
        dlg = QFileDialog(
            self,
            "Vyber PDF",
            current,
            "PDF soubory (*.pdf)",
        )
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        dlg.setDefaultSuffix("pdf")
        dlg.setOption(QFileDialog.DontUseNativeDialog, True)
        if dlg.exec() == QDialog.Accepted:
            files = dlg.selectedFiles()
            if not files:
                return
            p = Path(files[0])
            if p.suffix.lower() != ".pdf":
                p = p.with_suffix(".pdf")
            self._pdf_path.setText(str(p))

    def selected_requests(self) -> List[Tuple[VariantOption, int]]:
        result: List[Tuple[VariantOption, int]] = []
        for variant, spin in self._variant_inputs:
            count = int(spin.value())
            if count > 0:
                result.append((variant, count))
        return result

    def puzzles_per_page(self) -> int:
        return int(self._per_page.currentData())

    def output_mode(self) -> str:
        return str(self._output.currentData())

    def pdf_path(self) -> str:
        return self._pdf_path.text().strip()

    def accept(self) -> None:
        total = sum(count for _, count in self.selected_requests())
        if total <= 0:
            QMessageBox.warning(self, "Tisk", "Zadej alespoň 1 úlohu.")
            return

        if self.output_mode() == "pdf":
            text = self.pdf_path()
            if not text:
                QMessageBox.warning(self, "Tisk", "Vyber cestu k PDF souboru.")
                return
            p = Path(text)
            if p.suffix.lower() != ".pdf":
                p = p.with_suffix(".pdf")
                self._pdf_path.setText(str(p))

        super().accept()


def _mm_to_px(mm: float, dpi: int) -> float:
    return (mm / 25.4) * float(dpi)


def _slot_grid(per_page: int) -> Tuple[int, int]:
    mapping = {
        1: (1, 1),
        2: (2, 1),
        4: (2, 2),
        6: (3, 2),
        9: (3, 3),
    }
    return mapping.get(per_page, (2, 2))


def _compute_square_slots(page_rect: QRectF, per_page: int, dpi: int) -> List[QRectF]:
    rows, cols = _slot_grid(per_page)
    gap_mm = 0.0 if per_page == 1 else 6.0
    gap = _mm_to_px(gap_mm, dpi)

    usable_w = page_rect.width() - gap * (cols - 1)
    usable_h = page_rect.height() - gap * (rows - 1)
    slot_side = min(usable_w / cols, usable_h / rows)

    total_w = slot_side * cols + gap * (cols - 1)
    total_h = slot_side * rows + gap * (rows - 1)
    start_x = page_rect.x() + (page_rect.width() - total_w) / 2.0
    start_y = page_rect.y() + (page_rect.height() - total_h) / 2.0

    slots: List[QRectF] = []
    for r in range(rows):
        for c in range(cols):
            x = start_x + c * (slot_side + gap)
            y = start_y + r * (slot_side + gap)
            slots.append(QRectF(x, y, slot_side, slot_side))
    return slots


def create_output_printer(
    parent: Optional[QWidget],
    document_name: str,
    output_mode: str,
    pdf_path: str = "",
) -> Tuple[Optional[QPrinter], Optional[str]]:
    """Create and configure printer target for print dialog or PDF export."""
    printer = QPrinter(QPrinter.HighResolution)
    printer.setResolution(300)
    printer.setDocName(document_name)
    printer.setFullPage(False)

    layout = printer.pageLayout()
    layout.setPageSize(QPageSize(QPageSize.A4))
    layout.setOrientation(QPageLayout.Portrait)
    layout.setUnits(QPageLayout.Millimeter)
    layout.setMargins(QMarginsF(5.0, 5.0, 5.0, 5.0))
    printer.setPageLayout(layout)

    if output_mode == "pdf":
        path = Path(pdf_path).expanduser()
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        path.parent.mkdir(parents=True, exist_ok=True)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(str(path))
        return printer, str(path)

    dlg = QPrintDialog(printer, parent)
    dlg.setWindowTitle("Tisk")
    if dlg.exec() != QDialog.Accepted:
        return None, None
    return printer, None


def draw_square_batch(
    printer: QPrinter,
    items: Sequence[T],
    per_page: int,
    draw_item: Callable[[QPainter, QRectF, T, int], None],
) -> None:
    """Render a batch of square puzzle items over one or more A4 pages."""
    if not items:
        return

    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("Nepodařilo se spustit tiskový výstup.")

    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        raw_page_rect = printer.pageRect(QPrinter.DevicePixel)
        # Qt printers can report non-zero x/y here while painter already uses printable-area origin.
        # Normalize to local (0,0) to keep layouts centered on page.
        page_rect = QRectF(0.0, 0.0, float(raw_page_rect.width()), float(raw_page_rect.height()))
        dpi = max(96, printer.resolution())
        slots = _compute_square_slots(page_rect, per_page, dpi)
        if not slots:
            return

        per_page_actual = len(slots)
        pages = int(math.ceil(len(items) / float(per_page_actual)))
        index = 0

        for page in range(pages):
            painter.fillRect(page_rect, Qt.white)
            for slot_idx in range(per_page_actual):
                if index >= len(items):
                    break
                draw_item(painter, slots[slot_idx], items[index], index)
                index += 1

            if page < pages - 1:
                printer.newPage()
    finally:
        painter.end()
