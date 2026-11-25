"""The window's side of PLAN item 117: Help > What's new, Help > Check for a new version, the What's new
page shown once after an update, and the check at start that Preferences can turn on (off by default).
The check runs in a thread, so a slow or missing network never holds the window up."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QMessageBox, QPushButton, QTextBrowser, QVBoxLayout

from .. import __version__, updates

CHECK_SETTING = "updates/checkAtStart"
LAST_VERSION_SETTING = "updates/lastVersion"
LAST_CHECK_SETTING = "updates/lastCheck"
CHECK_EVERY = 20 * 3600  # at most about once a day


def _settings(win):
    shell = getattr(win, "shell", None)
    return getattr(shell, "settings", None)


def enabled(win) -> bool:
    s = _settings(win)
    if s is None:
        return False
    v = s.value(CHECK_SETTING, False)
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")


def set_enabled(win, on: bool) -> None:
    s = _settings(win)
    if s is not None:
        s.setValue(CHECK_SETTING, bool(on))


def show_whats_new(win, since: str = "") -> QDialog:
    """What changed in this version (with ``since``: in every version after that one), from CHANGELOG.md."""
    secs = updates.notes(__version__, since)
    dlg = QDialog(win)
    dlg.setWindowTitle(f"What's new in {__version__}")
    dlg.resize(760, 640)
    lay = QVBoxLayout(dlg)
    view = QTextBrowser()
    view.setOpenExternalLinks(True)
    if secs:
        view.setMarkdown(updates.as_markdown(secs))
    else:
        view.setMarkdown(f"# {__version__}\n\nThe list of changes is not here. It is on the "
                         f"[releases page]({updates.RELEASES_URL}).")
    lay.addWidget(view, 1)
    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    every = QPushButton("All releases (web)")
    every.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(updates.RELEASES_URL)))
    buttons.addButton(every, QDialogButtonBox.ActionRole)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    dlg.view = view
    dlg.setModal(False)
    dlg.show()
    return dlg


class _Check(QThread):
    done = Signal(object)  # a dict from updates.check(), or an error text

    def run(self) -> None:  # noqa: D401 - QThread's
        try:
            self.done.emit(updates.check())
        except updates.UpdateError as exc:
            self.done.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - a check never takes the app down
            self.done.emit(f"the check failed ({exc})")


class Checker(QObject):
    """One check in the background; tells the user what it found (quiet: only when a newer one is out)."""

    def __init__(self, win, quiet: bool) -> None:
        super().__init__(win)
        self.win, self.quiet = win, quiet
        self.result = None
        self.box = None
        self.thread = _Check(self)
        self.thread.done.connect(self._done)

    def start(self) -> None:
        self.thread.start()

    def _done(self, r) -> None:
        self.result = r
        win = self.win
        s = _settings(win)
        if s is not None and isinstance(r, dict):
            s.setValue(LAST_CHECK_SETTING, int(time.time()))
        if isinstance(r, str):
            if not self.quiet:
                self.box = _box(win, QMessageBox.Warning, "Check for a new version",
                                f"Could not check: {r}.\n\nThe releases page has every version: {updates.RELEASES_URL}")
            return
        if r["newer"]:
            box = _box(win, QMessageBox.Information, "A new version is out",
                       f"Version {r['latest']} is out; this is {__version__}.\n\n"
                       "Download it from the release page. Your projects open in it as they are.")
            get = box.addButton("Open the release page", QMessageBox.AcceptRole)
            get.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(r["url"])))
            box.addButton("Later", QMessageBox.RejectRole)
            self.box = box
            try:
                win.statusBar().showMessage(f"Version {r['latest']} is out (Help > Check for a new version)", 15000)
            except Exception:  # noqa: BLE001
                pass
        elif not self.quiet:
            self.box = _box(win, QMessageBox.Information, "Check for a new version",
                            f"This is the newest version ({__version__}).")


def _box(win, icon, title: str, text: str) -> QMessageBox:
    box = QMessageBox(icon, title, text, QMessageBox.NoButton, win)
    if icon == QMessageBox.Warning or "newest" in text:
        box.addButton(QMessageBox.Close)
    box.setModal(False)
    box.show()
    return box


def check_now(win, quiet: bool = False) -> Checker:
    c = Checker(win, quiet)
    win._update_checker = c  # kept alive until the next one
    c.start()
    return c


def on_start(win) -> None:
    """When the app starts: What's new once after an update, then the check if Preferences turned it on."""
    s = _settings(win)
    if s is None:
        return
    last = str(s.value(LAST_VERSION_SETTING, "") or "")
    s.setValue(LAST_VERSION_SETTING, __version__)
    if last and updates.is_newer(__version__, last):
        win._whats_new = show_whats_new(win, since=last)
    if enabled(win):
        try:
            when = int(s.value(LAST_CHECK_SETTING, 0) or 0)
        except (TypeError, ValueError):
            when = 0
        if time.time() - when > CHECK_EVERY:
            check_now(win, quiet=True)
