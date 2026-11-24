"""The small toolbar that appears beside a fresh pick (PLAN item 85).

After a plain click picks something in the 3D view, a row of the tools that
fit it (gui/body_menu.py ``pick_tools``: Sketch on this face, Pull, Hole ...
for a flat face; Fillet, Chamfer ... for edges) shows next to the cursor, so
the next step is one click away. The last button opens the full right-click
menu. Like every other GUI action, a button only writes command text or opens
a form.

It goes away when the mouse moves well away from it, after a few seconds
untouched, on Esc, when something else is picked, or when one of its tools
is used. Preferences > "Tools beside a pick" turns it off.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton

from . import body_menu as bm
from . import icons

AWAY_PX = 220  # the mouse this far from the bar: it goes
IDLE_MS = 6000  # untouched this long: it goes


def enabled(win) -> bool:
    shell = getattr(win, "shell", None)
    if shell is None:
        return True
    v = shell.settings.value(bm.PICK_TOOLS_SETTING, True)
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")


def set_enabled(win, on: bool) -> None:
    shell = getattr(win, "shell", None)
    if shell is not None:
        shell.settings.setValue(bm.PICK_TOOLS_SETTING, bool(on))
    if not on and getattr(win, "pick_bar", None) is not None:
        win.pick_bar.hide()


class PickBar(QFrame):
    def __init__(self, win) -> None:
        super().__init__(win, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("pick_bar")
        self.setFrameShape(QFrame.StyledPanel)
        self.win = win
        self.items: list[bm.MenuItem] = []
        self.buttons: list[QToolButton] = []
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(3, 3, 3, 3)
        self._lay.setSpacing(2)
        self._at = QPoint()
        self._sel = None
        self._watch = QTimer(self)
        self._watch.setInterval(150)
        self._watch.timeout.connect(self._check)
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.setInterval(IDLE_MS)
        self._idle.timeout.connect(self._idle_out)
        self.hide()

    def show_for_pick(self, global_pos: QPoint) -> bool:
        """Show the tools for the current pick beside ``global_pos``. False when none fit."""
        if not enabled(self.win):
            return False
        p = self.win.processor
        items = bm.pick_tools(p)[: bm.BAR_SIZE]
        if not items:
            self.hide()
            return False
        for b in self.buttons:
            self._lay.removeWidget(b)
            b.deleteLater()
        self.buttons = []
        self.items = items
        for it in items:
            b = QToolButton(self)
            b.setIcon(icons.icon(it.icon or "commands"))
            b.setText(it.short or it.label.rstrip("…"))
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setToolTip(it.label + ("\nRuns: " + " / ".join(it.first + it.commands) if (it.first or it.commands)
                                     else f"\nOpens the {it.form} form, filled in from the pick"))
            b.setAutoRaise(True)
            b.clicked.connect(lambda _=False, item=it: self.use(item))
            self._lay.addWidget(b)
            self.buttons.append(b)
        more = QToolButton(self)
        more.setText("⋯")
        more.setToolTip("Every tool for the pick, and the body's menu (the right-click menu)")
        more.setAutoRaise(True)
        more.clicked.connect(self._more)
        self._lay.addWidget(more)
        self.buttons.append(more)
        self.adjustSize()
        self._at = QPoint(global_pos)
        self._sel = (p.model.selection_kind, tuple(p.model.selection))
        self.move(global_pos + QPoint(18, 14))
        self.show()
        self.raise_()
        self._watch.start()
        self._idle.start()
        return True

    def use(self, item: bm.MenuItem) -> None:
        self.hide()
        self.win.run_menu_item(item)

    def _more(self) -> None:
        m = self.win.processor.model
        owners = bm.selected_bodies(m)
        at = QPoint(self._at)
        self.hide()
        self.win.show_body_menu(owners[0] if owners else 0, at)

    def hideEvent(self, e) -> None:
        self._watch.stop()
        self._idle.stop()
        super().hideEvent(e)

    def _idle_out(self) -> None:
        if not self.underMouse():
            self.hide()
        else:
            self._idle.start()

    def _check(self) -> None:
        if not self.isVisible():
            return
        m = self.win.processor.model
        if (m.selection_kind, tuple(m.selection)) != self._sel:  # something else picked (or nothing)
            self.hide()
            return
        if self.underMouse():
            self._idle.start()
            return
        d = QCursor.pos() - self.geometry().center()
        if d.manhattanLength() > AWAY_PX:
            self.hide()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(e)
