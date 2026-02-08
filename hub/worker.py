from __future__ import annotations

import logging
from typing import Callable, Optional, TypeVar

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

_T = TypeVar("_T")

_log = logging.getLogger(__name__)


class WorkerHandle:
    """Cancellation handle for tasks started via run_in_worker()."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled


class _WorkerSignals(QObject):
    done = Signal(object)
    error = Signal(object)


class _WorkerRunnable(QRunnable):
    def __init__(
        self,
        fn: Callable[[], _T],
        signals: _WorkerSignals,
        handle: WorkerHandle,
    ) -> None:
        super().__init__()
        self._fn = fn
        self._signals = signals
        self._handle = handle

    @Slot()
    def run(self) -> None:
        if self._handle.cancelled:
            return

        def _safe_emit(kind: str, payload: object) -> None:
            try:
                if kind == "error":
                    self._signals.error.emit(payload)
                else:
                    self._signals.done.emit(payload)
            except RuntimeError:
                _log.debug("Worker %s callback dropped because signal source is gone.", kind)

        try:
            result = self._fn()
        except Exception as exc:
            _log.exception("Background task failed.")
            _safe_emit("error", exc)
            return

        _safe_emit("done", result)


def run_in_worker(
    fn: Callable[[], _T],
    on_done: Optional[Callable[[_T], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
    parent: Optional[QObject] = None,
    pool: Optional[QThreadPool] = None,
) -> WorkerHandle:
    """
    Execute fn on a Qt worker thread and marshal callbacks back to the UI thread.

    Returns a WorkerHandle; calling cancel() prevents callbacks from being delivered.
    """
    worker_pool = pool or QThreadPool.globalInstance()
    handle = WorkerHandle()
    # Keep signal source independent from short-lived widget parents.
    # Parent destruction still cancels callbacks via WorkerHandle below.
    signals = _WorkerSignals()

    def _done(result: object) -> None:
        if handle.cancelled:
            return
        if on_done is not None:
            on_done(result)  # type: ignore[arg-type]

    def _error(exc: object) -> None:
        if handle.cancelled:
            return
        if on_error is not None:
            if isinstance(exc, Exception):
                on_error(exc)
            else:
                on_error(RuntimeError(f"Worker error: {exc!r}"))
            return
        _log.error("Unhandled worker error: %r", exc)

    signals.done.connect(_done)
    signals.error.connect(_error)

    if parent is not None:
        parent.destroyed.connect(lambda *_: handle.cancel())

    runnable = _WorkerRunnable(fn=fn, signals=signals, handle=handle)
    worker_pool.start(runnable)
    return handle
