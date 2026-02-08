from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QStackedWidget, QGridLayout,
    QFrame, QMessageBox, QStyle, QSizePolicy
)

from hub.plugin_loader import discover_plugins, LoadedPlugin
from hub.widgets.background import AnimatedBackground
from hub.widgets.game_card import GameCard
from hub.widgets.transitions import fade_in
from hub.widgets.skeleton import SkeletonCard
from hub.theme import apply_theme


_log = logging.getLogger(__name__)


class HomePage(QWidget):
    """Home page with 3×3 grid of game cards (9 games total)."""
    
    def __init__(self, plugins: List[LoadedPlugin], on_open, loading: bool = False, card_width: int = 160, parent=None):
        super().__init__(parent)
        self._plugins = plugins
        self._on_open = on_open
        self._loading = loading
        self._cols = 3  # Fixed 3 columns
        self._rows = 3  # Fixed 3 rows
        self._total_slots = 9  # Always 9 slots for 9 games

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # Grid container - takes all remaining space
        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_container)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(10)

        # Set equal stretch for all rows and columns immediately
        for i in range(self._cols):
            self._grid.setColumnStretch(i, 1)
        for i in range(self._rows):
            self._grid.setRowStretch(i, 1)

        outer.addWidget(self._grid_container, 1)

        self._cards: List[QWidget] = []

        if self._loading:
            # Show 9 skeleton cards during loading
            for _ in range(self._total_slots):
                sk = SkeletonCard()
                sk.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
                self._cards.append(sk)
        else:
            # Create cards for plugins
            for lp in self._plugins[:self._total_slots]:  # Max 9 games
                icon = None
                if lp.plugin.meta.icon_path:
                    icon_file = lp.folder / lp.plugin.meta.icon_path
                    if icon_file.exists():
                        icon = QIcon(str(icon_file))
                graphic = getattr(lp.plugin.meta, 'graphic_text', None)
                if self._on_open:
                    card = GameCard(
                        lp.plugin.meta.name,
                        lp.plugin.meta.description,
                        on_click=lambda lp=lp: self._on_open(lp),
                        icon=icon,
                        graphic_text=graphic,
                    )
                else:
                    card = GameCard(lp.plugin.meta.name, lp.plugin.meta.description, 
                                   on_click=None, icon=icon, graphic_text=graphic)
                # Force equal cell sizing in the 3x3 grid regardless of card content hints.
                card.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
                self._cards.append(card)
            
            # Fill remaining slots with empty placeholders if less than 9 games
            while len(self._cards) < self._total_slots:
                placeholder = QWidget()
                placeholder.setStyleSheet("background: rgba(255,255,255,0.03); border-radius: 12px;")
                placeholder.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
                self._cards.append(placeholder)

        # Build grid
        self._build_grid()

    def _build_grid(self) -> None:
        """Build the 3×3 grid with cards that fill the entire space."""
        # Clear existing
        while self._grid.count():
            it = self._grid.takeAt(0)
            if it and it.widget():
                it.widget().setParent(None)

        # Add cards to grid - they will expand to fill available space
        for idx, card in enumerate(self._cards):
            r = idx // self._cols
            c = idx % self._cols
            self._grid.addWidget(card, r, c)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)



class MainWindow(QMainWindow):
    def __init__(self, app=None):
        super().__init__()
        self._app = app
        self.setWindowTitle("BrainHub")
        self.resize(1000, 680)

        root = QWidget()
        self.setCentralWidget(root)

        self._bg = AnimatedBackground(root)
        self._content = QWidget(root)
        self._content.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._content)

        self._main_layout = QVBoxLayout(self._content)
        self._main_layout.setContentsMargins(24, 20, 24, 20)
        self._main_layout.setSpacing(12)

        # Stack (no sidebar - cleaner UI)
        self._stack = QStackedWidget()
        self._main_layout.addWidget(self._stack, 1)

        self._plugins: List[LoadedPlugin] = []
        self._home: Optional[HomePage] = None
        self._active_plugin_page: Optional[QWidget] = None
        self._active_plugin_widget: Optional[QWidget] = None

        self._loading_home = HomePage([], on_open=None, loading=True, card_width=200)
        self._stack.addWidget(self._loading_home)
        self._stack.setCurrentWidget(self._loading_home)

        if self._app is not None:
            apply_theme(self._app, font_size=10, theme="midnight")

        self._last_runs = self._load_last_runs()

        self._reload_plugins(initial=True)

        # TODO: Temporarily disabled by request.
        # Keep this snippet for quick re-enable of top menu "Quit" action.
        # act_quit = QAction("Quit", self)
        # act_quit.triggered.connect(self.close)
        # self.menuBar().addAction(act_quit)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._bg.setGeometry(self.rect())

    def _games_dir(self) -> Path:
        return Path(__file__).resolve().parents[1] / "games"

    def _last_runs_path(self) -> Path:
        return self._games_dir() / ".last_runs.json"

    def _load_last_runs(self) -> dict:
        p = self._last_runs_path()
        if p.exists():
            try:
                import json

                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_last_runs(self) -> None:
        try:
            import json

            self._last_runs_path().write_text(json.dumps(self._last_runs), encoding="utf-8")
        except Exception:
            pass

    def _sorted_plugins(self) -> List[LoadedPlugin]:
        def key(lp: LoadedPlugin):
            ts = self._last_runs.get(lp.plugin.meta.id, 0)
            return (-ts, lp.plugin.meta.name.lower())
        return sorted(self._plugins, key=key)

    def _reload_plugins(self, initial: bool = False) -> None:
        self._show_loading_state()

        def finish():
            self._plugins = discover_plugins(self._games_dir())

            # Rebuild UI
            self._rebuild_home()

            if not initial and not self._plugins:
                QMessageBox.information(self, "GameHub", "Nenašel jsem žádné pluginy ve složce games/.")

        QTimer.singleShot(150, finish)

    def _show_loading_state(self) -> None:
        self._teardown_active_plugin()

        if self._home is not None:
            idx = self._stack.indexOf(self._home)
            if idx >= 0:
                self._stack.removeWidget(self._home)
            self._home.deleteLater()

        self._loading_home = HomePage([], on_open=None, loading=True, card_width=200)
        self._stack.insertWidget(0, self._loading_home)
        self._stack.setCurrentWidget(self._loading_home)

    def _rebuild_home(self) -> None:
        """Rebuild home page with current plugins."""
        filtered = self._sorted_plugins()

        # rebuild home cards
        if self._home is not None:
            idx = self._stack.indexOf(self._home)
            if idx >= 0:
                self._stack.removeWidget(self._home)
            self._home.deleteLater()

        self._home = HomePage(filtered, on_open=self.open_plugin, card_width=200)
        self._stack.insertWidget(0, self._home)
        self._stack.setCurrentWidget(self._home)
        fade_in(self._home)

    def _go_home(self) -> None:
        self._teardown_active_plugin()

        if self._home:
            self._stack.setCurrentWidget(self._home)
            fade_in(self._home)
        elif self._loading_home:
            self._stack.setCurrentWidget(self._loading_home)

    def _call_lifecycle_hook(self, widget: QWidget, hook_name: str) -> None:
        hook: Optional[Callable[[], None]] = getattr(widget, hook_name, None)
        if not callable(hook):
            return
        try:
            hook()
        except Exception as exc:
            _log.exception("Widget lifecycle hook '%s' failed: %r", hook_name, exc)

    def _teardown_active_plugin(self) -> None:
        page = self._active_plugin_page
        widget = self._active_plugin_widget
        if page is None:
            return

        if widget is not None:
            self._call_lifecycle_hook(widget, "on_deactivate")
            self._call_lifecycle_hook(widget, "dispose")

        idx = self._stack.indexOf(page)
        if idx >= 0:
            self._stack.removeWidget(page)
        page.deleteLater()

        self._active_plugin_page = None
        self._active_plugin_widget = None

    def open_plugin(self, lp: LoadedPlugin) -> None:
        # update last-run info
        self._last_runs[lp.plugin.meta.id] = time.time()
        self._save_last_runs()
        self._teardown_active_plugin()

        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        top = QFrame()
        top.setObjectName("TopBar")
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(12, 10, 12, 10)

        btn_back = QPushButton("Zpět")
        btn_back.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        btn_back.clicked.connect(self._go_home)

        name = QLabel(lp.plugin.meta.name)
        name.setObjectName("Header2")

        top_l.addWidget(btn_back)
        top_l.addWidget(name)
        top_l.addStretch(1)

        v.addWidget(top)

        try:
            widget = lp.plugin.create_widget(parent=page)
            v.addWidget(widget, 1)
            self._active_plugin_widget = widget
        except Exception as e:
            err = QLabel(f"Plugin spadl při vytváření widgetu:\n{e!r}")
            err.setWordWrap(True)
            v.addWidget(err, 1)
            self._active_plugin_widget = None

        self._stack.addWidget(page)
        self._stack.setCurrentWidget(page)
        self._active_plugin_page = page
        if self._active_plugin_widget is not None:
            self._call_lifecycle_hook(self._active_plugin_widget, "on_activate")
        fade_in(page)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._go_home()
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._teardown_active_plugin()
        super().closeEvent(event)
