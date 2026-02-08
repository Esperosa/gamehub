from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QLocale, QSignalBlocker, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from hub.i18n import normalize_language, tr
from hub.plugin_api import resolve_i18n_text
from hub.plugin_loader import LoadedPlugin, discover_plugins
from hub.theme import apply_theme
from hub.widgets.background import AnimatedBackground
from hub.widgets.game_card import GameCard
from hub.widgets.skeleton import SkeletonCard
from hub.widgets.transitions import fade_in

_log = logging.getLogger(__name__)


class HomePage(QWidget):
    """Home page with 3×3 grid of game cards (9 games total)."""
    
    def __init__(
        self,
        plugins: List[LoadedPlugin],
        on_open,
        loading: bool = False,
        card_width: int = 160,
        language: str = "cs",
        play_hint_text: str = "▶ Hrát",
        parent=None,
    ):
        super().__init__(parent)
        self._plugins = plugins
        self._on_open = on_open
        self._loading = loading
        self._language = normalize_language(language)
        self._play_hint_text = play_hint_text
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
                if lp.manifest.icon_path:
                    icon_file = lp.folder / lp.manifest.icon_path
                    if icon_file.exists():
                        icon = QIcon(str(icon_file))
                display_name = resolve_i18n_text(lp.manifest.name_i18n, self._language, lp.manifest.name)
                display_desc = resolve_i18n_text(lp.manifest.description_i18n, self._language, lp.manifest.description)
                graphic = getattr(lp.manifest, 'graphic_text', None)
                if self._on_open:
                    card = GameCard(
                        display_name,
                        display_desc,
                        on_click=lambda lp=lp: self._on_open(lp),
                        icon=icon,
                        graphic_text=graphic,
                        play_hint_text=self._play_hint_text,
                    )
                else:
                    card = GameCard(
                        display_name,
                        display_desc,
                        on_click=None,
                        icon=icon,
                        graphic_text=graphic,
                        play_hint_text=self._play_hint_text,
                    )
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

        self._language = self._default_language()
        self._settings_error_notified = False
        self._last_runs_error_notified = False
        self._active_plugin_loaded: Optional[LoadedPlugin] = None
        self._active_back_button: Optional[QPushButton] = None
        self._active_plugin_title_label: Optional[QLabel] = None

        settings = self._load_settings()
        configured_lang = settings.get("language")
        if isinstance(configured_lang, str):
            self._language = normalize_language(configured_lang)

        self._header = QFrame()
        self._header.setObjectName("TopBar")
        self._header_l = QHBoxLayout(self._header)
        self._header_l.setContentsMargins(12, 10, 12, 10)
        self._header_l.setSpacing(10)

        self._header_title = QLabel()
        self._header_title.setObjectName("Header2")
        self._header_subtitle = QLabel()

        header_texts = QVBoxLayout()
        header_texts.setContentsMargins(0, 0, 0, 0)
        header_texts.setSpacing(0)
        header_texts.addWidget(self._header_title)
        header_texts.addWidget(self._header_subtitle)
        self._header_l.addLayout(header_texts)
        self._header_l.addStretch(1)

        self._lang_label = QLabel()
        self._language_combo = QComboBox()
        self._language_combo.setObjectName("LangCombo")
        self._language_combo.addItem("", "cs")
        self._language_combo.addItem("", "en")
        self._language_combo.currentIndexChanged.connect(self._on_language_combo_changed)

        self._header_l.addWidget(self._lang_label)
        self._header_l.addWidget(self._language_combo)
        self._main_layout.addWidget(self._header)

        # Stack (no sidebar - cleaner UI)
        self._stack = QStackedWidget()
        self._main_layout.addWidget(self._stack, 1)

        self._plugins: List[LoadedPlugin] = []
        self._home: Optional[HomePage] = None
        self._active_plugin_page: Optional[QWidget] = None
        self._active_plugin_widget: Optional[QWidget] = None

        self._loading_home = HomePage(
            [],
            on_open=None,
            loading=True,
            card_width=200,
            language=self._language,
            play_hint_text=self._tr("play_hint"),
        )
        self._stack.addWidget(self._loading_home)
        self._stack.setCurrentWidget(self._loading_home)

        if self._app is not None:
            apply_theme(self._app, font_size=10, theme="midnight")

        self._last_runs = self._load_last_runs()
        self._apply_language_to_ui()
        self._set_language_combo_value(self._language)

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

    def _default_language(self) -> str:
        locale_name = QLocale.system().name().lower()
        if locale_name.startswith("cs"):
            return "cs"
        return "en"

    def _tr(self, key: str, **kwargs: object) -> str:
        return tr(self._language, key, **kwargs)

    def _app_data_dir(self) -> Path:
        app_data = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        if not app_data:
            app_data = str(Path.home() / ".brainhub")
        p = Path(app_data)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _settings_path(self) -> Path:
        return self._app_data_dir() / "settings.json"

    def _last_runs_path(self) -> Path:
        return self._app_data_dir() / "last_runs.json"

    def _load_settings(self) -> dict:
        try:
            p = self._settings_path()
            if not p.exists():
                return {}
            import json

            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            _log.warning("Invalid settings payload at %s: expected object, got %s.", p, type(data).__name__)
            return {}
        except Exception as exc:
            self._report_settings_error(exc)
            return {}

    def _save_settings(self, settings: dict) -> None:
        try:
            import json

            p = self._settings_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            self._report_settings_error(exc)

    def _report_settings_error(self, exc: Exception) -> None:
        _log.error("Failed to read/write runtime settings.", exc_info=self._exc_info(exc))
        if self._settings_error_notified:
            return
        self._settings_error_notified = True
        QMessageBox.warning(self, self._tr("dialog_title"), self._tr("settings_io_failed"))

    @staticmethod
    def _exc_info(exc: Exception):
        return (type(exc), exc, exc.__traceback__)

    def _report_last_runs_error(self, exc: Exception) -> None:
        _log.error("Failed to read/write last-run metadata.", exc_info=self._exc_info(exc))
        if self._last_runs_error_notified:
            return
        self._last_runs_error_notified = True
        QMessageBox.warning(self, self._tr("dialog_title"), self._tr("last_runs_io_failed"))

    def _load_last_runs(self) -> dict:
        try:
            p = self._last_runs_path()
            if not p.exists():
                return {}
            import json

            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            _log.warning("Invalid last-runs payload at %s: expected object, got %s.", p, type(data).__name__)
            return {}
        except Exception as exc:
            self._report_last_runs_error(exc)
            return {}

    def _save_last_runs(self) -> None:
        try:
            import json

            p = self._last_runs_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self._last_runs), encoding="utf-8")
        except Exception as exc:
            self._report_last_runs_error(exc)

    def _plugin_name(self, lp: LoadedPlugin) -> str:
        return resolve_i18n_text(lp.manifest.name_i18n, self._language, lp.manifest.name)

    def _plugin_description(self, lp: LoadedPlugin) -> str:
        return resolve_i18n_text(lp.manifest.description_i18n, self._language, lp.manifest.description)

    def _set_language_combo_value(self, language: str) -> None:
        target = normalize_language(language)
        idx = self._language_combo.findData(target)
        if idx < 0:
            idx = self._language_combo.findData("cs")
        with QSignalBlocker(self._language_combo):
            self._language_combo.setCurrentIndex(idx)

    def _apply_language_to_ui(self) -> None:
        self._header_title.setText(self._tr("header_title"))
        self._header_subtitle.setText(self._tr("header_subtitle"))
        self._lang_label.setText(f"{self._tr('language_label')}:")
        with QSignalBlocker(self._language_combo):
            for i in range(self._language_combo.count()):
                lang = self._language_combo.itemData(i)
                if lang == "cs":
                    self._language_combo.setItemText(i, self._tr("language_cs"))
                elif lang == "en":
                    self._language_combo.setItemText(i, self._tr("language_en"))
        if self._active_back_button is not None:
            self._active_back_button.setText(self._tr("back"))
        if self._active_plugin_title_label is not None and self._active_plugin_loaded is not None:
            self._active_plugin_title_label.setText(self._plugin_name(self._active_plugin_loaded))

    def _set_language(self, language: str, persist: bool = True) -> None:
        new_lang = normalize_language(language)
        if new_lang == self._language:
            self._apply_language_to_ui()
            self._set_language_combo_value(new_lang)
            return
        self._language = new_lang
        self._apply_language_to_ui()
        self._set_language_combo_value(new_lang)
        if persist:
            self._save_settings({"language": self._language})
        self._rebuild_home()

    def _on_language_combo_changed(self, index: int) -> None:
        lang = self._language_combo.itemData(index)
        if isinstance(lang, str):
            self._set_language(lang, persist=True)

    def _sorted_plugins(self) -> List[LoadedPlugin]:
        def key(lp: LoadedPlugin):
            ts = self._last_runs.get(lp.manifest.id, 0)
            return (-ts, self._plugin_name(lp).lower())
        return sorted(self._plugins, key=key)

    def _reload_plugins(self, initial: bool = False) -> None:
        self._show_loading_state()

        def finish():
            try:
                self._plugins = discover_plugins(self._games_dir())

                # Rebuild UI
                self._rebuild_home()

                if not initial and not self._plugins:
                    QMessageBox.information(self, self._tr("dialog_title"), self._tr("no_plugins"))
            except Exception as exc:
                _log.error("Plugin reload failed.", exc_info=self._exc_info(exc))
                self._plugins = []
                self._rebuild_home()
                QMessageBox.critical(self, self._tr("dialog_title"), self._tr("plugin_reload_failed"))

        QTimer.singleShot(150, finish)

    def _show_loading_state(self) -> None:
        self._teardown_active_plugin()

        if self._home is not None:
            idx = self._stack.indexOf(self._home)
            if idx >= 0:
                self._stack.removeWidget(self._home)
            self._home.deleteLater()

        self._loading_home = HomePage(
            [],
            on_open=None,
            loading=True,
            card_width=200,
            language=self._language,
            play_hint_text=self._tr("play_hint"),
        )
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

        self._home = HomePage(
            filtered,
            on_open=self.open_plugin,
            card_width=200,
            language=self._language,
            play_hint_text=self._tr("play_hint"),
        )
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
        self._active_plugin_loaded = None
        self._active_back_button = None
        self._active_plugin_title_label = None

    def open_plugin(self, lp: LoadedPlugin) -> None:
        # update last-run info
        self._last_runs[lp.manifest.id] = time.time()
        self._save_last_runs()
        self._teardown_active_plugin()
        display_name = self._plugin_name(lp)

        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        top = QFrame()
        top.setObjectName("TopBar")
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(12, 10, 12, 10)

        btn_back = QPushButton(self._tr("back"))
        btn_back.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        btn_back.clicked.connect(self._go_home)

        name = QLabel(display_name)
        name.setObjectName("Header2")

        top_l.addWidget(btn_back)
        top_l.addWidget(name)
        top_l.addStretch(1)

        v.addWidget(top)

        try:
            widget = lp.manifest.create_widget(parent=page)
            v.addWidget(widget, 1)
            self._active_plugin_widget = widget
        except Exception as exc:
            _log.error(
                "Plugin '%s' failed during widget creation.",
                lp.manifest.id,
                exc_info=self._exc_info(exc),
            )
            QMessageBox.critical(
                self,
                self._tr("dialog_title"),
                self._tr("plugin_open_failed", name=display_name),
            )
            err = QLabel(self._tr("plugin_widget_crash", error=repr(exc)))
            err.setWordWrap(True)
            v.addWidget(err, 1)
            self._active_plugin_widget = None

        self._stack.addWidget(page)
        self._stack.setCurrentWidget(page)
        self._active_plugin_page = page
        self._active_plugin_loaded = lp
        self._active_back_button = btn_back
        self._active_plugin_title_label = name
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
