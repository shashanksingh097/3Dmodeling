"""Long history edits run in the rebuild helper (core/helper.py) while the window stays live.

``MainWindow.execute`` asks ``Offload.wants(text)`` first. A ``HIST`` edit whose
re-run is expected to take longer than ``OFFLOAD_AFTER`` (the time the steps
took when they last ran, from the edited entry on) is sent to the helper. The
window keeps drawing and the view can be turned while it runs; a small dialog
shows the step and has Cancel. Commands typed or clicked meanwhile are
refused with a note. When the helper answers, the window takes over its state
and tells every panel, the same as after a local run. Cancel stops the helper
and leaves the window's model exactly as it was. If the helper cannot be
started or fails, the edit simply runs here instead.
"""

from __future__ import annotations

import queue
import re
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication, QProgressDialog

from ..commands.processor import Result
from ..core import helper as _helper
from ..core import transfer

if TYPE_CHECKING:
    from .main_window import MainWindow

OFFLOAD_AFTER = 1.0  # seconds of expected re-run time
POLL_MS = 30
_HIST = re.compile(r"\s*HIST\s*,\s*([A-Za-z]+)\s*(?:,\s*([^,]+))?", re.IGNORECASE)
_REBUILDS = {"EDIT", "INSERT", "INS", "DELETE", "DEL", "SUPPRESS", "SUP", "RESUME", "UNSUPPRESS", "MOVE",
             "REPLAY", "PART"}


def expected_seconds(p, text: str) -> float:
    """How long re-running for this line should take (0 when it is no rebuild)."""
    m = _HIST.match(text)
    if not m or m.group(1).upper() not in _REBUILDS or "\n" in text:
        return 0.0
    action = m.group(1).upper()
    first = 1
    if action != "REPLAY":
        try:
            first = int(m.group(2))
        except (TypeError, ValueError):
            return 0.0  # an expression or a mistake: the local run says what is wrong
        if action == "MOVE":
            try:
                first = min(first, int(text.rsplit(",", 1)[1]))
            except (ValueError, IndexError):
                pass
    first = max(1, first)
    return sum(e.seconds for e in p.history[first - 1: p.cursor])


class Offload:
    def __init__(self, win: MainWindow) -> None:
        self.win = win
        self.helper = _helper.Helper()
        self.busy = False
        self.enabled = True
        self.dialog: QProgressDialog | None = None

    # ---- deciding --------------------------------------------------------------
    def wants(self, text: str) -> bool:
        p = self.win.processor
        if not self.enabled or self.busy or p.pending or p.model.active_sketch:
            return False
        return expected_seconds(p, text) >= OFFLOAD_AFTER

    def warm_up(self) -> None:
        """Start the helper ahead of time (it takes about a second), once a model is big enough."""
        try:
            self.helper.start()
        except OSError:
            self.enabled = False

    # ---- running ---------------------------------------------------------------
    def run(self, text: str) -> Result | None:
        """Run ``text`` in the helper; None means "run it here instead"."""
        p = self.win.processor
        try:
            state = transfer.processor_state(p)
            self.helper.submit(state, text)
        except Exception:  # noqa: BLE001 - no helper: run it here, the old way
            self.helper.cancel()
            return None
        self.busy = True
        self._open_dialog(text)
        self.win.cmdline.setEnabled(False)
        answer = None
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(POLL_MS)

        def poll() -> None:
            nonlocal answer
            while True:
                try:
                    msg = self.helper.messages.get_nowait()
                except queue.Empty:
                    break
                if msg[0] == "progress":
                    self._progress(*msg[1:])
                    continue
                answer = msg
                loop.quit()
                return
            if self.dialog is not None and self.dialog.wasCanceled():
                self.helper.cancel()
                answer = ("cancelled",)
                loop.quit()

        timer.timeout.connect(poll)
        timer.start()
        started = time.monotonic()
        try:
            loop.exec()
        finally:
            timer.stop()
            self._close_dialog()
            self.win.cmdline.setEnabled(True)
            self.win.cmdline.setFocus()
            self.busy = False
        return self._take(text, answer, time.monotonic() - started)

    def _take(self, text: str, answer: tuple | None, took: float) -> Result | None:
        p = self.win.processor
        kind = answer[0] if answer else "gone"
        if kind == "cancelled":
            word = text.split(",")[1].strip().upper() if "," in text else "EDIT"
            return p._finish(Result(text.strip(), False,
                                    f"HIST, {word}: cancelled; the model and the history are as they were"))
        if kind != "done":
            self.helper.cancel()
            return None  # the helper broke: the window runs it itself
        ok, line, message, warning, state = answer[1:]
        if ok:
            transfer.set_processor_state(p, state)
            p.model.restore(p.model.snapshot())  # every panel and the view redraw from the new model
            p._history_changed()
        return p._finish(Result(line, ok, message, warning=warning))

    # ---- the small dialog ------------------------------------------------------
    def _open_dialog(self, text: str) -> None:
        d = QProgressDialog("Starting the rebuild…", "Cancel", 0, 0, self.win)
        d.setWindowTitle("Rebuilding")
        d.setWindowModality(Qt.NonModal)  # the view can still be turned while it runs
        d.setMinimumDuration(0)
        d.setAutoClose(False)
        d.setAutoReset(False)
        d.setMinimumWidth(420)
        d.show()
        self.dialog = d
        QApplication.setOverrideCursor(Qt.BusyCursor)

    def _progress(self, done: int, total: int, label: str) -> None:
        if self.dialog is None:
            return
        self.dialog.setMaximum(max(total, 1))
        self.dialog.setValue(done)
        short = label if len(label) <= 60 else label[:57] + "…"
        self.dialog.setLabelText(f"Step {done + 1} of {total}: {short}\n(the window stays usable for looking)")

    def _close_dialog(self) -> None:
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
            QApplication.restoreOverrideCursor()

    def close(self) -> None:
        self.helper.close()
