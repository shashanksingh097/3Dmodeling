"""The error bar above the command line (PLAN item 89).

When a typed line or a history step fails, the bar shows the first line of the
message, lights up the faces, edges or bodies at fault in red, and offers
buttons: "Use BLOCK" for a misspelt command or name (the line is put back on
the command line with it fixed, so Enter runs it), "Find fixes" (the usual
fixes, tried on a copy of the model; each one that works becomes a button),
"Why?" (the full Why? window) and a close button. The next command that works
hides it again, and the red goes with it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QToolButton, QVBoxLayout

from ..commands import why_handlers as wh

MAX_FIXES = 3


class ErrorBar(QFrame):
    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        self.setObjectName("errorBar")
        self.setStyleSheet("#errorBar { background: #fdecec; border: 1px solid #e3a5a5; border-radius: 3px; }"
                           "#errorBar QLabel { color: #8a1c1c; }"
                           "#errorBar QPushButton { padding: 2px 8px; }")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 3, 2, 3)
        outer.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(4)
        self.icon = QLabel("✖")
        top.addWidget(self.icon, 0, Qt.AlignTop)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.label.setMinimumWidth(80)
        top.addWidget(self.label, 1)
        self.close_button = QToolButton()
        self.close_button.setText("✕")
        self.close_button.setAutoRaise(True)
        self.close_button.setToolTip("Hide this (Esc in the command line)")
        self.close_button.clicked.connect(self.dismiss)
        top.addWidget(self.close_button, 0, Qt.AlignTop)
        outer.addLayout(top)
        lay = QHBoxLayout()
        lay.setSpacing(4)
        lay.setContentsMargins(14, 0, 0, 0)
        self.near_buttons: list[QPushButton] = []
        self.fix_buttons: list[QPushButton] = []
        self._dyn = QHBoxLayout()
        self._dyn.setSpacing(4)
        lay.addLayout(self._dyn)
        lay.addStretch(1)
        self.find_button = QPushButton("Find fixes")
        self.find_button.setToolTip("Try the usual fixes on a copy of the model; each one that works becomes a button")
        self.find_button.clicked.connect(self.find_fixes)
        lay.addWidget(self.find_button)
        self.why_button = QPushButton("Why?")
        self.why_button.setToolTip("The whole reason, the fixes tried and the guide (WHY in the command line)")
        self.why_button.clicked.connect(self.open_why)
        lay.addWidget(self.why_button)
        outer.addLayout(lay)
        self._fixes = QVBoxLayout()  # the fixes that work, one per row (the view can be narrow)
        self._fixes.setContentsMargins(14, 0, 0, 0)
        self._fixes.setSpacing(2)
        outer.addLayout(self._fixes)
        self.line = ""
        self.message = ""
        self.step: int | None = None
        self.fault: dict | None = None
        self._showing_fault = False
        self.hide()

    # ---- showing ---------------------------------------------------------------------------
    def show_failure(self, line: str, message: str, step: int | None = None) -> None:
        p = self.win.processor
        self.line, self.message, self.step = line, message or "", step
        first = (message or "it failed").splitlines()[0]
        if len(first) > 260:
            first = first[:257] + "…"
        self.label.setText(first if step is None else f"Step {step}: {first}")
        self.label.setToolTip(message or "")
        self._clear_buttons()
        for text, fixed in wh.near_fixes(line, message):
            b = QPushButton(text)
            b.setToolTip(f"Put this on the command line; Enter runs it:\n{fixed}")
            b.clicked.connect(lambda _=False, f=fixed: self.use_line(f))
            self._dyn.addWidget(b)
            self.near_buttons.append(b)
        self.find_button.setEnabled(True)
        self.find_button.setText("Find fixes")
        if step is not None:
            self.fault = wh.step_fault(p, step)
        else:
            self.fault = wh.fault_for(p, line, message, typed=True)
        self._showing_fault = bool(self.fault) and wh.show_fault(p, self.fault) > 0
        if self.fault:
            self.label.setText(self.label.text() + f"   ({wh.fault_text(self.fault)}, red in the view)")
        self.show()

    def _clear_buttons(self) -> None:
        for b in self.near_buttons + self.fix_buttons:
            (self._dyn if b in self.near_buttons else self._fixes).removeWidget(b)
            b.hide()
            b.deleteLater()
        self.near_buttons, self.fix_buttons = [], []

    def dismiss(self) -> None:
        if self._showing_fault:
            self.win.processor.model.set_preview([])
        self._showing_fault = False
        self.fault = None
        self._clear_buttons()
        self.hide()

    # ---- the buttons -----------------------------------------------------------------------
    def use_line(self, text: str) -> None:
        self.win.cmdline.setText(text)
        self.win.cmdline.setFocus()

    def diagnose(self) -> dict:
        from ..ai import diagnose as dg

        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if self.step is not None:
                return dg.diagnose(self.win.processor, self.step)
            return dg.diagnose(self.win.processor, line=self.line)
        except dg.DiagnoseError as exc:
            return {"failed": True, "message": str(exc), "line": self.line, "fixes": []}
        finally:
            QGuiApplication.restoreOverrideCursor()

    def find_fixes(self) -> list[dict]:
        d = self.diagnose()
        fixes = (d.get("fixes") or [])[:MAX_FIXES]
        for f in fixes:
            run1 = f["run"].splitlines()[0] + (" …" if "\n" in f["run"] else "")
            b = QPushButton(f"Fix: {f['fix'][:70]}{'…' if len(f['fix']) > 70 else ''}   ({run1[:40]})")
            b.setStyleSheet("text-align: left;")
            b.setToolTip(f"{f['fix']}\nRuns (Undo takes it back):\n{f['run']}")
            b.clicked.connect(lambda _=False, run=f["run"]: self.run_fix(run))
            self._fixes.addWidget(b)
            self.fix_buttons.append(b)
        self.find_button.setEnabled(False)
        self.find_button.setText("No usual fix works" if not fixes else "Fixes below")
        if not fixes:
            self.find_button.setToolTip(d.get("next", "") or "no usual fix worked")
        return fixes

    def run_fix(self, run: str) -> bool:
        ok = True
        for ln in run.splitlines():
            if ln.strip():
                r = self.win.execute(ln)
                if not r.ok:
                    ok = False
                    break
        return ok

    def open_why(self):
        from .why_dialog import WhyDialog

        dlg = WhyDialog(self.win, self.diagnose())
        dlg.setModal(False)
        dlg.show()
        self.why_dialog = dlg
        return dlg

    # ---- following the commands ------------------------------------------------------------
    def on_result(self, res) -> None:
        if res.pending or not res.line:
            return
        word = res.line.split(",")[0].strip().upper()
        if word in ("WHY", "SELINFO", "HELP"):
            return  # looking at the failure does not end it
        if res.ok:
            if self.isVisible():
                self.dismiss()
            return
        self.show_failure(res.line, res.message)

    def show_step(self, row: int) -> None:
        """A failed history row was clicked: show its failure."""
        p = self.win.processor
        if 0 <= row < p.cursor:
            e = p.history[row]
            if not e.ok and not e.suppressed:
                self.show_failure(e.text, e.message, row + 1)
