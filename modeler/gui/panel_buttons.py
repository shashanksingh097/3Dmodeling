"""Buttons at the right of the status bar that open and close the panels kept out of the way
(PLAN item 120): History (with the number of steps, red when one failed), Output and Assistant.

The history itself is always kept (UNDO, the assistant and replay read it); only its panel is
closed at first, so the 3D view gets the room. Ctrl+H opens and closes the History. A command
typed in the command line whose answer is text (a query, LIST, DESCRIBE ...) opens the Output so
the answer is seen.
"""

from __future__ import annotations

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QToolButton

HISTORY_KEY = "Ctrl+H"


def history_text(p) -> tuple[str, int]:
    """The History button's words and the number of failed steps."""
    n = p.cursor
    failed = sum(1 for e in p.history[:n] if not e.ok and not e.suppressed)
    text = f"History: {n} step{'s' if n != 1 else ''}"
    if failed:
        text += f", {failed} failed"
    return text, failed


class PanelButtons:
    def __init__(self, win) -> None:
        self.win = win
        self.buttons: dict[str, QToolButton] = {}
        for key, dock, tip in (
            ("history", win.history_dock, f"Show or hide the History: every step, to change, reorder or "
                                          f"roll back ({HISTORY_KEY})"),
            ("output", win.output_dock, "Show or hide the Output: what each command answered"),
            ("assistant", win.assistant_dock, "Show or hide the Assistant"),
        ):
            b = QToolButton()
            b.setCheckable(True)
            b.setAutoRaise(True)
            b.setToolTip(tip)
            b.setText(dock.windowTitle())
            b.setChecked(dock.isVisible())
            b.toggled.connect(lambda on, d=dock: self._toggle(d, on))
            dock.visibilityChanged.connect(lambda _on, d=dock, btn=b: self._sync(d, btn))
            win.statusBar().addPermanentWidget(b)
            self.buttons[key] = b
        self.shortcut = QShortcut(QKeySequence(HISTORY_KEY), win)
        self.shortcut.activated.connect(lambda: self.toggle("history"))
        win.processor.history_listeners.append(self.refresh)
        self.refresh()

    def _toggle(self, dock, on: bool) -> None:
        if on == dock.isVisible():
            return
        dock.setVisible(on)
        if on:
            dock.raise_()

    def _sync(self, dock, btn) -> None:
        # a dock hidden behind another tab is still open: the button follows open/closed, not on top
        on = not dock.isHidden()
        if btn.isChecked() != on:
            btn.blockSignals(True)
            btn.setChecked(on)
            btn.blockSignals(False)

    def toggle(self, key: str) -> None:
        b = self.buttons[key]
        b.setChecked(not b.isChecked())

    def refresh(self) -> None:
        text, failed = history_text(self.win.processor)
        b = self.buttons["history"]
        b.setText(text)
        b.setStyleSheet("color: #c62828; font-weight: bold;" if failed else "")

    def show_output(self) -> None:
        d = self.win.output_dock
        if d.isHidden():
            d.show()
