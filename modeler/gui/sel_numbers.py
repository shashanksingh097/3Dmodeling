"""The numbers of what is picked, always in view (PLAN item 86).

``SelectionNumbers`` sits at the right of the status bar. Whenever the pick
changes it shows one line from commands/selinfo.py: one face's type and area,
one edge's length and radius, a body's volume and mass, or for several picks
the count and total, and for two picks the distance and angle between them.
A click copies the line (and the full SELINFO report) to the clipboard.

``HoverNumbers`` shows the same kind of line as a tooltip when the mouse rests
on something in the 3D view, without picking it. Preferences > "Numbers on
hover" turns that off.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QToolTip

from ..commands import selinfo as si

HOVER_SETTING = "view/hoverNumbers"
UPDATE_MS = 60  # several selection events in a row (a box pick) make one update


def _on(win, key: str, default: bool = True) -> bool:
    shell = getattr(win, "shell", None)
    if shell is None:
        return default
    v = shell.settings.value(key, default)
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")


def hover_enabled(win) -> bool:
    return _on(win, HOVER_SETTING)


def set_hover_enabled(win, on: bool) -> None:
    shell = getattr(win, "shell", None)
    if shell is not None:
        shell.settings.setValue(HOVER_SETTING, bool(on))
    if not on:
        QToolTip.hideText()


class SelectionNumbers(QLabel):
    def __init__(self, win) -> None:
        super().__init__()
        self.setObjectName("selection_numbers")
        self.win = win
        self.info: dict = {}
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self.setCursor(Qt.PointingHandCursor)
        self.setContentsMargins(6, 0, 6, 0)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(UPDATE_MS)
        self._timer.timeout.connect(self.refresh)
        win.processor.model.subscribe(self._event)
        win.processor.listeners.append(self._result)
        self.refresh()

    def _result(self, res) -> None:
        if res.ok and res.line.strip().upper().startswith("/UNITS"):
            self._timer.start()  # shown in other units now

    def _event(self, ev) -> None:
        if ev.kind in ("selection", "cleared", "restored", "body_added", "body_removed", "style", "layers"):
            self._timer.start()

    def refresh(self) -> None:
        p = self.win.processor
        try:
            self.info = si.selection_info(p) if p.model.selection else {}
        except Exception as exc:  # noqa: BLE001 - never let the status bar break the window
            self.info = {}
            self.setText("")
            self.setToolTip(f"Could not measure the pick: {exc}")
            return
        text = si.line(self.info) if self.info else ""
        self.setText(text)
        if text:
            self.setToolTip("The numbers of what is picked (SELINFO prints them all). Click to copy.\n\n"
                            + si.report_text(self.info))
        else:
            self.setToolTip("Pick a face, an edge, a vertex or a body to see its numbers here")

    def copy_text(self) -> str:
        if not self.info:
            return ""
        return si.line(self.info) + ("\n" + si.report_text(self.info) if self.info.get("count", 0) > 1 else "")

    def mousePressEvent(self, e) -> None:
        txt = self.copy_text()
        if txt and e.button() == Qt.LeftButton:
            QGuiApplication.clipboard().setText(txt)
            self.win.statusBar().showMessage("Copied the numbers of the pick", 3000)
        super().mousePressEvent(e)


class HoverNumbers:
    """Shows the numbers of what the mouse rests on (the viewport's ``hovered`` signal)."""

    def __init__(self, win) -> None:
        self.win = win
        self.last: tuple[str, int] | None = None
        self.text = ""
        win.viewport.hovered.connect(self.show)
        win.viewport.hover_left.connect(self.hide)

    def show(self, kind: str, gid: int, at: QPoint) -> None:
        if not hover_enabled(self.win) or not kind:
            self.hide()
            return
        self.last = (kind, gid)
        self.text = si.hover_text(self.win.processor, kind, gid)
        if self.text:
            QToolTip.showText(at + QPoint(14, 16), self.text, self.win.viewport)

    def hide(self) -> None:
        if self.last is not None:
            QToolTip.hideText()
        self.last = None
        self.text = ""
