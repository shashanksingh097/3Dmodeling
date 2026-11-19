"""Why? on a failed step: the message, the usual fixes tried on a copy of the model
(ai/diagnose.py), a button to run each one that works, and the guide for the command.
It needs no assistant and no network."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..ai import diagnose as dg


def diagnose_with_wait(p, step=None, line=None) -> dict:
    QGuiApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        return dg.diagnose(p, step, line)
    finally:
        QGuiApplication.restoreOverrideCursor()


class WhyDialog(QDialog):
    def __init__(self, win, result: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent or win)
        self.win = win
        self.result = result
        self.ran: list[str] = []
        title = f"Why did step {result['step']} fail?" if "step" in result else "Why did it fail?"
        if not result.get("failed", True):
            title = f"Step {result['step']}: a warning" if "step" in result else "It runs"
        self.setWindowTitle(title)
        self.resize(760, 520)
        lay = QVBoxLayout(self)
        self.text = QPlainTextEdit(dg.why_text(result))
        self.text.setReadOnly(True)
        lay.addWidget(self.text, 1)
        self.fix_buttons: list[QPushButton] = []
        fixes = result.get("fixes") or []
        if fixes:
            lay.addWidget(QLabel("Run a fix (Undo takes it back):"))
            for f in fixes:
                b = QPushButton(f["fix"][:110] + ("…" if len(f["fix"]) > 110 else ""))
                b.setToolTip(f["run"])
                b.setStyleSheet("text-align: left; padding: 4px 8px;")
                b.clicked.connect(lambda _=False, run=f["run"]: self.run_fix(run))
                lay.addWidget(b)
                self.fix_buttons.append(b)
        row = QHBoxLayout()
        self.guide_buttons: list[QPushButton] = []
        for g in (result.get("guides") or [])[:3]:
            b = QPushButton(f"Guide: {g.replace('-', ' ')}")
            b.clicked.connect(lambda _=False, g=g: self.open_guide(g))
            row.addWidget(b)
            self.guide_buttons.append(b)
        self.ask_button = QPushButton("Ask the assistant")
        self.ask_button.setToolTip("Open the assistant with this failure in the question box")
        self.ask_button.clicked.connect(self.ask)
        self.ask_button.setEnabled(getattr(win, "shell", None) is not None)
        row.addWidget(self.ask_button)
        row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        lay.addLayout(row)

    def run_fix(self, run: str) -> bool:
        ok = True
        for line in run.splitlines():
            if line.strip():
                r = self.win.execute(line)
                self.ran.append(line)
                if not r.ok:
                    ok = False
                    break
        if ok:
            self.accept()
        return ok

    def open_guide(self, name: str) -> None:
        shell = getattr(self.win, "shell", None)
        if shell is not None:
            shell.show_guides(name)

    def ask(self) -> None:
        shell = getattr(self.win, "shell", None)
        if shell is None:
            return
        shell.show_assistant()
        panel = getattr(self.win, "assistant_panel", None)
        if panel is None:
            return
        r = self.result
        where = f"Step {r['step']}" if "step" in r else "This line"
        msg = (r.get("message") or "").splitlines()[0] if r.get("message") else ""
        panel.input.setText(f"{where} failed: {dg.first_code_line(r['line'])} ({msg}) How do I fix it?")
        panel.input.setFocus()
        self.accept()
