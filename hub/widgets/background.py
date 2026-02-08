from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from hub.diagnostics import probe_gpu_backend
from hub.widgets.background_fallback import FallbackAnimatedBackground


_log = logging.getLogger(__name__)

_probe_prepared = False
_gpu_allowed = False
_gpu_env_override: str | None = None
_probe_summary = ""


def prepare_background_runtime() -> None:
    """Run GPU diagnostics once and configure runtime backend selection."""
    global _probe_prepared, _gpu_allowed, _gpu_env_override, _probe_summary
    if _probe_prepared:
        return
    _probe_prepared = True

    if os.environ.get("GAMEHUB_BACKGROUND_CPU", "").strip() == "1":
        _gpu_allowed = False
        _probe_summary = "forced-cpu"
        _log.warning("GPU background disabled by GAMEHUB_BACKGROUND_CPU=1.")
        return

    if os.environ.get("GAMEHUB_BACKGROUND_GPU", "").strip() == "1":
        _gpu_allowed = True
        _probe_summary = "forced-gpu"
        _log.warning("GPU probe bypassed by GAMEHUB_BACKGROUND_GPU=1.")
        return

    if getattr(sys, "frozen", False):
        # One-file EXE cannot safely use the python-style `-m` subprocess probe path.
        # TODO(gpu-probe): Add frozen-compatible in-process probe and re-enable GPU auto-select.
        _gpu_allowed = False
        _probe_summary = "frozen-skip-probe"
        _log.warning("GPU probe disabled in frozen build. Using CPU fallback background.")
        return

    project_root = Path(__file__).resolve().parents[2]
    result = probe_gpu_backend(project_root)
    _gpu_allowed = result.ok
    _gpu_env_override = result.env_override
    _probe_summary = result.details

    if result.ok:
        if _gpu_env_override and not os.environ.get("QT_OPENGL"):
            # Apply working backend mode before QApplication startup.
            os.environ["QT_OPENGL"] = _gpu_env_override
        _log.info(
            "GPU probe success via %s (%s). QT_OPENGL=%r",
            result.backend_label,
            result.details,
            os.environ.get("QT_OPENGL", ""),
        )
    else:
        _log.error("GPU probe failed. %s", result.details)
        if result.raw_stdout:
            _log.error("GPU probe stdout: %s", result.raw_stdout)
        if result.raw_stderr:
            _log.error("GPU probe stderr: %s", result.raw_stderr)


class AnimatedBackground(QWidget):
    """Safe background host with automatic GPU->CPU fallback."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._effect_mode = "particles"
        self._backend_name = "fallback"
        self._impl: QWidget

        prepare_background_runtime()
        self._init_backend()

    def _init_backend(self) -> None:
        if _gpu_allowed:
            try:
                from hub.widgets.background_gpu import GpuAnimatedBackground

                impl = GpuAnimatedBackground(self)
                impl.set_effect_mode(self._effect_mode)
                impl.setGeometry(self.rect())
                impl.show()
                self._impl = impl
                self._backend_name = "gpu"
                _log.info("Background backend: GPU (%s)", _probe_summary)
                return
            except Exception as exc:
                _log.exception(
                    "GPU background backend failed to initialize (%s). Falling back to CPU.",
                    exc,
                )

        self._impl = FallbackAnimatedBackground(self)
        self._backend_name = "fallback"
        self._impl.set_effect_mode(self._effect_mode)
        self._impl.setGeometry(self.rect())
        self._impl.show()
        _log.warning("Background backend: CPU fallback (%s)", _probe_summary or "gpu-unavailable")

    def _mode_supported_by_impl(self, mode: str) -> bool:
        supports = getattr(self._impl, "supports_effect_mode", None)
        if not callable(supports):
            return True
        try:
            return bool(supports(mode))
        except Exception as exc:
            _log.warning("Background mode support check failed for %r: %r", mode, exc)
            return False

    def _switch_to_fallback(self, reason: str) -> None:
        if isinstance(self._impl, FallbackAnimatedBackground):
            return
        previous = self._impl
        self._impl = FallbackAnimatedBackground(self)
        self._backend_name = "fallback"
        self._impl.set_effect_mode(self._effect_mode)
        self._impl.setGeometry(self.rect())
        self._impl.show()
        previous.hide()
        previous.deleteLater()
        _log.warning("Background backend switched to CPU fallback (%s).", reason)

    def set_effect_mode(self, mode: str) -> None:
        # TODO(metaballs): Re-enable external mode switching after metaballs QA is complete.
        del mode
        normalized = "particles"
        # TODO(metaballs): Restore this check when mode switching is active again.
        # if normalized == "metaballs" and not self._mode_supported_by_impl("metaballs"):
        #     self._switch_to_fallback("gpu-metaballs-unsupported")
        self._effect_mode = "particles"
        if hasattr(self._impl, "set_effect_mode"):
            getattr(self._impl, "set_effect_mode")(normalized)

    @property
    def effect_mode(self) -> str:
        return self._effect_mode

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._impl.setGeometry(self.rect())
