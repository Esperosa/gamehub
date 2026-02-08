from __future__ import annotations

import json
import sys
from typing import Any, Dict


GL_VENDOR = 0x1F00
GL_RENDERER = 0x1F01
GL_VERSION = 0x1F02


def _decode_gl_string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="ignore")
    return str(value)


def run_probe() -> Dict[str, Any]:
    from PySide6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    fmt = QSurfaceFormat()
    surface = QOffscreenSurface()
    surface.setFormat(fmt)
    surface.create()
    if not surface.isValid():
        return {"ok": False, "reason": "offscreen-surface-invalid"}

    ctx = QOpenGLContext()
    ctx.setFormat(surface.format())
    if not ctx.create():
        return {"ok": False, "reason": "context-create-failed"}
    if not ctx.makeCurrent(surface):
        return {"ok": False, "reason": "makeCurrent-failed"}

    funcs = ctx.functions()
    vendor = _decode_gl_string(funcs.glGetString(GL_VENDOR))
    renderer = _decode_gl_string(funcs.glGetString(GL_RENDERER))
    version = _decode_gl_string(funcs.glGetString(GL_VERSION))
    ctx.doneCurrent()

    # Probe the real widget path used by app.
    from hub.widgets.background_gpu import GpuAnimatedBackground

    widget = GpuAnimatedBackground()
    widget.resize(128, 88)
    widget.show()
    for _ in range(12):
        app.processEvents()
    widget.hide()
    widget.deleteLater()
    app.processEvents()

    return {
        "ok": True,
        "vendor": vendor,
        "renderer": renderer,
        "version": version,
        "qt_opengl_env": __import__("os").environ.get("QT_OPENGL", ""),
    }


def main() -> int:
    try:
        out = run_probe()
    except Exception as exc:  # pragma: no cover - runtime diagnostic path
        out = {"ok": False, "reason": f"exception:{exc.__class__.__name__}", "error": repr(exc)}
    print(json.dumps(out, ensure_ascii=True))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

