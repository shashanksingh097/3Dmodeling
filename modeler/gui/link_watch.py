"""Keep linked part files in step: when one changes on disk, run RELOAD.

The window watches the files its ``LIB, LINK`` steps read (and checks them
again whenever the app comes back to the front, since some editors replace
a file instead of writing it). A change waits a moment, so a file still
being written is read once, whole.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QFileSystemWatcher, QObject, Qt, QTimer
from PySide6.QtGui import QGuiApplication


class LinkWatcher(QObject):
    DELAY_MS = 400

    def __init__(self, window) -> None:
        super().__init__(window)
        self.win = window
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._changed)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.DELAY_MS)
        self.timer.timeout.connect(self.check)
        window.processor.history_listeners.append(self.update_paths)
        app = QGuiApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._app_state)
        self.update_paths()

    def paths(self) -> list[str]:
        p = self.win.processor
        return sorted({lk.path for lk in p.links.values()
                       if not lk.copy and 0 <= lk.row < p.cursor and os.path.isfile(lk.path)})

    def update_paths(self) -> None:
        want = set(self.paths())
        have = set(self.watcher.files())
        if have - want:
            self.watcher.removePaths(sorted(have - want))
        if want - have:
            self.watcher.addPaths(sorted(want - have))

    def _changed(self, _path: str) -> None:
        self.timer.start()

    def _app_state(self, state) -> None:
        if state == Qt.ApplicationActive and self.win.processor.links:
            self.timer.start()

    def check(self) -> bool:
        """RELOAD when a linked file changed; True when it ran."""
        ran = self.win.reload_links()
        self.update_paths()  # a replaced file drops out of the watch: add it again
        return ran
