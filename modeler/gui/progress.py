"""Progress and Cancel while the history is re-run (after an edit far back).

The processor calls this before each entry it re-runs. Nothing shows for
short rebuilds; after half a second a modal dialog shows which step is
running, with a Cancel button. Cancel puts the model and the history back
as they were before the edit (see ``HIST`` in commands/handlers.py).
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QProgressDialog

SHOW_AFTER = 0.5  # seconds


class RebuildProgress:
    def __init__(self, parent) -> None:
        self.parent = parent
        self.dialog: QProgressDialog | None = None
        self.started = 0.0

    def __call__(self, done: int, total: int, label: str) -> bool:
        now = time.monotonic()
        if done == 0:
            self.finish()
            self.started = now
        if self.dialog is None and now - self.started >= SHOW_AFTER and total > 1:
            d = QProgressDialog("Re-running the history…", "Cancel", 0, total, self.parent)
            d.setWindowTitle("Rebuilding")
            d.setWindowModality(Qt.WindowModal)
            d.setMinimumDuration(0)
            d.setAutoClose(False)
            d.setAutoReset(False)
            d.setMinimumWidth(420)
            d.show()
            self.dialog = d
        if self.dialog is not None:
            self.dialog.setMaximum(total)
            self.dialog.setValue(done)
            short = label if len(label) <= 60 else label[:57] + "…"
            self.dialog.setLabelText(f"Step {done + 1} of {total}: {short}")
            QApplication.processEvents()
            if self.dialog.wasCanceled():
                self.finish()
                return False
        return True

    def finish(self) -> None:
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
