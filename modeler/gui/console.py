"""View > Python console (PLAN item 106): a Python prompt with the model at hand, off until opened.

The console's own names:

* ``run("BLOCK, 0,0,0, 10,10,10")`` runs a command as if typed; it goes into the history.
* ``c.BLOCK(0, 0, 0, 10, 10, 10)`` builds the same command from Python values
  (``c.FILLET("SEL", 2)``, ``c.HOLE("plate", 20, 15, 8, 6)``); it returns the result.
* ``model``, ``p`` (the processor), ``body("plate")`` (a body by name or ID), ``bodies()``,
  ``report("MASSPROP")`` (the newest answer of a check, as data), ``value("BBOX(1).dx")`` (a query),
  ``np`` and ``math``.

Reading is free. Changing the model only counts through commands: a line that changes the model
directly (``model.bodies.pop(1)``) is undone at once, and the console says to use ``run`` or ``c``,
so the history stays the whole story of the model.
"""

from __future__ import annotations

import code
import contextlib
import io
import math
import traceback
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from .main_window import MainWindow

BANNER = ("Python console. run(\"BLOCK, 0,0,0, 10,10,10\") or c.BLOCK(0,0,0, 10,10,10) runs a command (it goes "
          "into the history); model, p, body(name), bodies(), report(name), value(query), np and math are here "
          "to read. Changes made to the model directly are undone: use commands.")


def _arg(v) -> str:
    """A Python value as command text."""
    if isinstance(v, bool):
        return "YES" if v else "NO"
    if isinstance(v, (int, float)):
        return f"{v:.12g}"
    if isinstance(v, (tuple, list)):
        return "(" + ", ".join(_arg(x) for x in v) + ")"
    if v is None:
        return ""
    s = str(v)
    if any(ch in s for ch in ",;!") and not (s[:1] == s[-1:] == '"'):
        return '"' + s.replace('"', "'") + '"'
    return s


class Commands:
    """``c.NAME(args...)`` runs ``NAME, args...``."""

    def __init__(self, run) -> None:
        self._run = run

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def call(*args, **kw):
            parts = [name.upper(), *[_arg(a) for a in args]]
            if kw:
                parts += [f"{k}={_arg(v)}" for k, v in kw.items()]
            while len(parts) > 1 and parts[-1] == "":
                parts.pop()
            return self._run(", ".join(parts))

        call.__name__ = name.upper()
        return call

    def __dir__(self):
        from ..commands.processor import REGISTRY

        return sorted(REGISTRY)


class Console(QWidget):
    def __init__(self, win: MainWindow) -> None:
        super().__init__()
        self.win = win
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setMaximumBlockCount(5000)
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.TypeWriter)
        self.out.setFont(mono)
        self.prompt = QLabel(">>>")
        self.prompt.setFont(mono)
        self.inp = QLineEdit()
        self.inp.setFont(mono)
        self.inp.setPlaceholderText("Python: c.BLOCK(0, 0, 0, 10, 10, 10) · report('MASSPROP') · help(c)")
        self.inp.returnPressed.connect(self._enter)
        self.inp.installEventFilter(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(self.out, 1)
        row = QWidget()
        from PySide6.QtWidgets import QHBoxLayout

        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.prompt)
        h.addWidget(self.inp, 1)
        lay.addWidget(row)
        self.past: list[str] = []
        self._at = 0
        self.ns = self._namespace()
        self.interp = code.InteractiveConsole(self.ns, filename="<console>")
        self._write(BANNER + "\n")

    # ---- the names it offers ----------------------------------------------------------------
    def _namespace(self) -> dict:
        import numpy as np

        win = self.win

        def run(text: str):
            res = win.execute(text)
            print(res.message if res.ok else f"error: {res.message}")
            return res

        def body(ref):
            p = win.processor
            if isinstance(ref, int):
                return p.model.body(ref)
            b = p.model.body_by_name(str(ref))
            if b is None:
                raise KeyError(f"no body named {ref!r}")
            return b

        def bodies():
            return {b.id: b.name for b in win.processor.model.bodies.values()}

        def report(name: str):
            return win.processor.reports.get(str(name).upper())

        def value(query: str):
            return win.processor.evaluate(query)

        return {"__name__": "__console__", "run": run, "c": Commands(run), "body": body, "bodies": bodies,
                "report": report, "value": value, "np": np, "math": math,
                "p": win.processor, "model": win.processor.model, "win": win}

    # ---- typing -------------------------------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt's name
        if obj is self.inp and event.type() == QEvent.KeyPress and self.past:
            if event.key() == Qt.Key_Up:
                self._at = max(0, self._at - 1)
                self.inp.setText(self.past[self._at])
                return True
            if event.key() == Qt.Key_Down:
                self._at = min(len(self.past), self._at + 1)
                self.inp.setText(self.past[self._at] if self._at < len(self.past) else "")
                return True
        return super().eventFilter(obj, event)

    def _write(self, text: str) -> None:
        self.out.moveCursor(QTextCursor.End)
        self.out.insertPlainText(text)
        self.out.moveCursor(QTextCursor.End)

    def _enter(self) -> None:
        line = self.inp.text()
        self.inp.clear()
        self.push(line)

    def push(self, line: str) -> str:
        """Run one line (as typed); returns what it printed."""
        if line.strip():
            self.past.append(line)
        self._at = len(self.past)
        self._write(f"{self.prompt.text()} {line}\n")
        p = self.win.processor
        self.ns["model"] = p.model  # a NEW or OPEN may have swapped it
        before_snap = p.model.snapshot()
        before_ids = {k: id(v) for k, v in p.model.bodies.items()}
        before_len = (len(p.history), p.cursor)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                more = self.interp.push(line)
            except SystemExit:
                more = False
                print("the console cannot close the program")
            except Exception:  # noqa: BLE001 - shown in the console
                more = False
                traceback.print_exc()
        text = buf.getvalue()
        # the model changed but no command ran: undo it, so the history stays the whole story
        now_ids = {k: id(v) for k, v in p.model.bodies.items()}
        if now_ids != before_ids and (len(p.history), p.cursor) == before_len:
            p.model.restore(before_snap)
            text += ("direct changes to the model are not kept (they would not be in the history): use run(...) "
                     "or c.COMMAND(...)\n")
        self._write(text)
        self.prompt.setText("..." if more else ">>>")
        return text


def toggle(win: MainWindow, on: bool | None = None):
    """Show or hide the console dock (made on first use)."""
    from PySide6.QtCore import Qt as _Qt

    dock = getattr(win, "console_dock", None)
    if dock is None:
        if on is False:
            return None
        win.console = Console(win)
        dock = win._dock("Python console", win.console, _Qt.BottomDockWidgetArea)
        out = getattr(win, "output_dock", None)
        if out is not None and not out.isFloating():
            win.tabifyDockWidget(out, dock)  # a tab beside Output, full width
        win.console_dock = dock
        dock.visibilityChanged.connect(lambda vis: win.console_action.setChecked(vis)
                                       if hasattr(win, "console_action") else None)
    show = (not dock.isVisible()) if on is None else on
    dock.setVisible(show)
    if show:
        dock.raise_()
        win.console.inp.setFocus()
    return dock
