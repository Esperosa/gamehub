from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


def _qss_midnight() -> str:
    return r"""
    QWidget { color: #E6E9F2; font-family: "Segoe UI"; }
    QMainWindow { background: #07090F; }

    #Sidebar {
        background: rgba(13, 16, 24, 0.96);
        border-right: 1px solid rgba(255,255,255,0.04);
    }

    #AppTitle { font-size: 19px; font-weight: 800; letter-spacing: 0.35px; }
    #SubtleText { color: rgba(230,233,242,0.62); }

    QPushButton {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(255,255,255,0.07), stop:1 rgba(255,255,255,0.03));
        border: 1px solid rgba(255,255,255,0.08);
        padding: 9px 12px;
        border-radius: 10px;
        color: #E6E9F2;
    }
    QPushButton:hover {
        border: 1px solid rgba(100, 190, 255, 0.45);
        background: rgba(255,255,255,0.09);
    }
    QPushButton:pressed { background: rgba(255,255,255,0.12); }

    QPushButton:disabled {
        color: rgba(230,233,242,0.35);
        border: 1px solid rgba(255,255,255,0.04);
        background: rgba(255,255,255,0.03);
    }

    QListWidget { background: transparent; border: none; outline: none; }
    QListWidget::item { padding: 10px 10px; border-radius: 10px; }
    QListWidget::item:selected {
        background: rgba(96, 165, 250, 0.18);
        border: 1px solid rgba(96, 165, 250, 0.32);
    }
    QListWidget::item:hover { background: rgba(255,255,255,0.05); }

    QScrollArea { background: transparent; border: none; }
    QScrollBar:vertical { background: transparent; width: 10px; margin: 0px; }
    QScrollBar::handle:vertical {
        background: rgba(255,255,255,0.14);
        border-radius: 5px;
        min-height: 20px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

    GameCard {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 14px;
    }
    GameCard:hover {
        border: 1px solid rgba(96, 165, 250, 0.45);
        background: rgba(255,255,255,0.06);
    }

    #CardIcon[variant="placeholder"] {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(96,165,250,0.32), stop:1 rgba(59,130,246,0.18));
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 12px;
        color: rgba(255,255,255,0.55);
        font-weight: 700;
    }

    SkeletonCard {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.04);
        border-radius: 14px;
    }

    QLabel#Header1 { font-size: 22px; font-weight: 900; }
    QLabel#Header2 { font-size: 15px; font-weight: 700; color: rgba(230,233,242,0.88); }

    QFrame#TopBar {
        background: rgba(12, 15, 23, 0.82);
        border: 1px solid rgba(255,255,255,0.05);
        border-radius: 12px;
    }

    QDialog, QMessageBox, QFileDialog {
        background: rgba(10, 14, 22, 0.98);
    }
    QDialog, QMessageBox {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
    }
    QDialog QLabel, QMessageBox QLabel {
        color: #E6E9F2;
    }
    QDialog QGroupBox {
        margin-top: 10px;
        padding-top: 12px;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        background: rgba(255,255,255,0.03);
        font-weight: 700;
    }
    QDialog QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: rgba(230,233,242,0.88);
    }
    QDialog QLineEdit, QDialog QComboBox {
        background: rgba(7, 11, 19, 0.95);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 8px;
        padding: 6px 8px;
        selection-background-color: rgba(96, 165, 250, 0.35);
    }
    QDialog QLineEdit:focus, QDialog QComboBox:focus {
        border: 1px solid rgba(100, 190, 255, 0.65);
    }
    QDialog QSpinBox {
        background: rgba(7, 11, 19, 0.95);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 8px;
        padding: 4px 8px;
        min-height: 30px;
        selection-background-color: rgba(96, 165, 250, 0.35);
    }
    QDialog QSpinBox:focus {
        border: 1px solid rgba(100, 190, 255, 0.65);
    }
    QDialog QWidget#SpinEditor {
        background: rgba(7, 11, 19, 0.95);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 8px;
    }
    QDialog QWidget#SpinEditor QSpinBox {
        background: transparent;
        border: none;
        padding: 0px 8px;
        min-height: 30px;
        color: #E6E9F2;
    }
    QDialog QWidget#SpinEditor QWidget#SpinStepper {
        border-left: 1px solid rgba(255,255,255,0.12);
    }
    QDialog QPushButton#SpinStepUp, QDialog QPushButton#SpinStepDown {
        padding: 0px;
        border: none;
        border-radius: 0px;
        background: rgba(255,255,255,0.04);
        color: #E6E9F2;
        font-weight: 800;
    }
    QDialog QPushButton#SpinStepUp {
        border-top-right-radius: 8px;
        border-bottom: 1px solid rgba(255,255,255,0.10);
    }
    QDialog QPushButton#SpinStepDown {
        border-bottom-right-radius: 8px;
    }
    QDialog QPushButton#SpinStepUp:hover, QDialog QPushButton#SpinStepDown:hover {
        background: rgba(96, 165, 250, 0.20);
    }
    QDialog QPushButton#SpinStepUp:pressed, QDialog QPushButton#SpinStepDown:pressed {
        background: rgba(96, 165, 250, 0.28);
    }
    QDialog QComboBox::drop-down {
        border: none;
        width: 22px;
    }
    QComboBox QAbstractItemView {
        background: rgba(10, 14, 22, 0.98);
        color: #E6E9F2;
        border: 1px solid rgba(255,255,255,0.14);
        selection-background-color: rgba(96, 165, 250, 0.25);
    }
    QDialog QTreeView, QDialog QListView, QDialog QTableView {
        background: rgba(7, 11, 19, 0.95);
        color: #E6E9F2;
        border: 1px solid rgba(255,255,255,0.10);
        alternate-background-color: rgba(255,255,255,0.03);
    }
    QDialog QTreeView::item:selected, QDialog QListView::item:selected, QDialog QTableView::item:selected {
        background: rgba(96, 165, 250, 0.25);
        color: #E6E9F2;
    }
    """


def _qss_slate() -> str:
    return r"""
    QWidget { color: #1E2430; font-family: "Segoe UI"; }
    QMainWindow { background: #F5F7FB; }

    #Sidebar {
        background: #FFFFFF;
        border-right: 1px solid rgba(0,0,0,0.08);
    }

    #AppTitle { font-size: 19px; font-weight: 800; letter-spacing: 0.35px; color: #111827; }
    #SubtleText { color: rgba(30,36,48,0.60); }

    QPushButton {
        background: #F3F4F6;
        border: 1px solid rgba(0,0,0,0.06);
        padding: 9px 12px;
        border-radius: 10px;
        color: #111827;
    }
    QPushButton:hover {
        border: 1px solid #60A5FA;
        background: #E8F0FF;
    }
    QPushButton:pressed { background: #DBEAFE; }

    QPushButton:disabled {
        color: rgba(17,24,39,0.35);
        border: 1px solid rgba(0,0,0,0.05);
        background: rgba(0,0,0,0.02);
    }

    QListWidget { background: transparent; border: none; outline: none; }
    QListWidget::item { padding: 10px 10px; border-radius: 10px; }
    QListWidget::item:selected {
        background: rgba(96, 165, 250, 0.20);
        border: 1px solid rgba(96, 165, 250, 0.42);
    }
    QListWidget::item:hover { background: rgba(0,0,0,0.035); }

    QScrollArea { background: transparent; border: none; }
    QScrollBar:vertical { background: transparent; width: 10px; margin: 0px; }
    QScrollBar::handle:vertical {
        background: rgba(0,0,0,0.12);
        border-radius: 5px;
        min-height: 20px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

    GameCard {
        background: #FFFFFF;
        border: 1px solid rgba(0,0,0,0.05);
        border-radius: 14px;
    }
    GameCard:hover {
        border: 1px solid rgba(96, 165, 250, 0.55);
        background: #F8FAFF;
    }

    #CardIcon[variant="placeholder"] {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #DBEAFE, stop:1 #BFDBFE);
        border: 1px solid rgba(0,0,0,0.06);
        border-radius: 12px;
        color: #1E3A8A;
        font-weight: 700;
    }

    SkeletonCard {
        background: #FFFFFF;
        border: 1px solid rgba(0,0,0,0.05);
        border-radius: 14px;
    }

    QLabel#Header1 { font-size: 22px; font-weight: 900; color: #0F172A; }
    QLabel#Header2 { font-size: 15px; font-weight: 700; color: #1F2937; }

    QFrame#TopBar {
        background: #FFFFFF;
        border: 1px solid rgba(0,0,0,0.06);
        border-radius: 12px;
    }

    QDialog, QMessageBox, QFileDialog {
        background: #FFFFFF;
    }
    QDialog, QMessageBox {
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 12px;
    }
    QDialog QLabel, QMessageBox QLabel {
        color: #1E2430;
    }
    QDialog QGroupBox {
        margin-top: 10px;
        padding-top: 12px;
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 10px;
        background: #F8FAFF;
        font-weight: 700;
    }
    QDialog QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: #334155;
    }
    QDialog QLineEdit, QDialog QComboBox {
        background: #FFFFFF;
        border: 1px solid rgba(0,0,0,0.14);
        border-radius: 8px;
        padding: 6px 8px;
        selection-background-color: rgba(96, 165, 250, 0.30);
    }
    QDialog QLineEdit:focus, QDialog QComboBox:focus {
        border: 1px solid #60A5FA;
    }
    QDialog QSpinBox {
        background: #FFFFFF;
        border: 1px solid rgba(0,0,0,0.14);
        border-radius: 8px;
        padding: 4px 8px;
        min-height: 30px;
        selection-background-color: rgba(96, 165, 250, 0.30);
    }
    QDialog QSpinBox:focus {
        border: 1px solid #60A5FA;
    }
    QDialog QWidget#SpinEditor {
        background: #FFFFFF;
        border: 1px solid rgba(0,0,0,0.14);
        border-radius: 8px;
    }
    QDialog QWidget#SpinEditor QSpinBox {
        background: transparent;
        border: none;
        padding: 0px 8px;
        min-height: 30px;
        color: #1E2430;
    }
    QDialog QWidget#SpinEditor QWidget#SpinStepper {
        border-left: 1px solid rgba(0,0,0,0.12);
    }
    QDialog QPushButton#SpinStepUp, QDialog QPushButton#SpinStepDown {
        padding: 0px;
        border: none;
        border-radius: 0px;
        background: #F3F4F6;
        color: #1F2937;
        font-weight: 800;
    }
    QDialog QPushButton#SpinStepUp {
        border-top-right-radius: 8px;
        border-bottom: 1px solid rgba(0,0,0,0.08);
    }
    QDialog QPushButton#SpinStepDown {
        border-bottom-right-radius: 8px;
    }
    QDialog QPushButton#SpinStepUp:hover, QDialog QPushButton#SpinStepDown:hover {
        background: #E8F0FF;
    }
    QDialog QPushButton#SpinStepUp:pressed, QDialog QPushButton#SpinStepDown:pressed {
        background: #DBEAFE;
    }
    QDialog QComboBox::drop-down {
        border: none;
        width: 22px;
    }
    QComboBox QAbstractItemView {
        background: #FFFFFF;
        color: #1E2430;
        border: 1px solid rgba(0,0,0,0.15);
        selection-background-color: rgba(96, 165, 250, 0.25);
    }
    QDialog QTreeView, QDialog QListView, QDialog QTableView {
        background: #FFFFFF;
        color: #1E2430;
        border: 1px solid rgba(0,0,0,0.10);
        alternate-background-color: #F8FAFF;
    }
    QDialog QTreeView::item:selected, QDialog QListView::item:selected, QDialog QTableView::item:selected {
        background: rgba(96, 165, 250, 0.20);
        color: #0F172A;
    }
    """


def apply_theme(app: QApplication, font_size: int = 10, theme: str = "midnight") -> None:
    app.setFont(QFont("Segoe UI", font_size))

    themes = {
        "midnight": _qss_midnight(),
        "slate": _qss_slate(),
    }
    qss = themes.get(theme, themes["midnight"])
    app.setStyleSheet(qss)
