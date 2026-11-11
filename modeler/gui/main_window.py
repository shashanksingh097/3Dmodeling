"""Main window for the M0 spike: viewport, toolbar, command line, log.

Every button and every viewport click builds command text and sends it to
the same :meth:`MainWindow.execute` that the command line uses.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QFont, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..commands import Processor, Result
from ..viewport.occ_view import OccViewport


class CommandLine(QLineEdit):
    """Single-line command entry with Up/Down history."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Type a command, e.g.  BLOCK, 0,0,0, 10,10,10   (HELP lists commands)")
        self.history: list[str] = []
        self._pos = 0

    def remember(self, text: str) -> None:
        if text and (not self.history or self.history[-1] != text):
            self.history.append(text)
        self._pos = len(self.history)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Up and self.history:
            self._pos = max(0, self._pos - 1)
            self.setText(self.history[self._pos])
        elif e.key() == Qt.Key_Down and self.history:
            self._pos = min(len(self.history), self._pos + 1)
            self.setText(self.history[self._pos] if self._pos < len(self.history) else "")
        else:
            super().keyPressEvent(e)


class MainWindow(QMainWindow):
    def __init__(self, processor: Processor | None = None) -> None:
        super().__init__()
        self.setWindowTitle("3Dmodeling (M0 spike)")
        self.resize(1200, 800)
        self.processor = processor or Processor()

        self.viewport = OccViewport(self.processor.model)
        self.viewport.command.connect(self.execute)
        self.processor.view = self.viewport

        self.output = QPlainTextEdit(readOnly=True)
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.TypeWriter)
        self.output.setFont(mono)
        self.cmdline = CommandLine()
        self.cmdline.setFont(mono)
        self.cmdline.returnPressed.connect(self._on_enter)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.viewport, 1)
        lay.addWidget(self.cmdline)
        self.setCentralWidget(central)

        dock = QDockWidget("Output", self)
        dock.setWidget(self.output)
        dock.setObjectName("output")
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

        self.processor.listeners.append(self._on_result)
        self._build_toolbar()
        self.statusBar().showMessage(
            "Left drag: orbit · Middle/right drag: pan · Wheel: zoom · Click: pick (Ctrl adds, Alt removes)"
        )

    # ---- toolbar: every action is just command text ---------------------
    def _build_toolbar(self) -> None:
        tb = QToolBar("Main", self)
        tb.setObjectName("main")
        self.addToolBar(tb)

        def cmd_action(label: str, text: str, tip: str = "", shortcut: str = "") -> QAction:
            act = QAction(label, self)
            act.setToolTip(f"{tip or label}\nRuns: {text}")
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(lambda _=False, t=text: self.execute(t))
            tb.addAction(act)
            return act

        cmd_action("Block", "BLOCK, 0,0,0, 20,10,5", "Add a block")
        cmd_action("Cylinder", "CYL, 30,5,0, 4,12", "Add a cylinder")
        cmd_action("Sphere", "SPHERE, 0,25,5, 6", "Add a sphere")
        tb.addSeparator()

        group = QActionGroup(self)
        group.setExclusive(True)
        self._mode_actions: dict[str, QAction] = {}
        for kind in ("BODY", "FACE", "EDGE", "VERTEX"):
            act = cmd_action(kind.title(), f"PICKMODE, {kind}", f"Pick {kind.lower()}s")
            act.setCheckable(True)
            group.addAction(act)
            self._mode_actions[kind] = act
        self._mode_actions["FACE"].setChecked(True)
        tb.addSeparator()

        for name in ("ISO", "TOP", "FRONT", "RIGHT"):
            cmd_action(name.title(), f"VIEW, {name}", f"{name.title()} view")
        cmd_action("Fit", "FIT", "Zoom to fit", "F")
        tb.addSeparator()
        cmd_action("Clear", "CLEAR", "Delete everything")

        save = QAction("Save log…", self)
        save.setShortcut(QKeySequence.Save)
        save.triggered.connect(self._save_log)
        tb.addAction(save)

        run = QAction("Run script…", self)
        run.setShortcut(QKeySequence.Open)
        run.triggered.connect(self._run_file)
        tb.addAction(run)

    # ---- running commands --------------------------------------------------
    def execute(self, text: str) -> Result:
        """The single entry point for GUI actions, clicks and typed text."""
        self.cmdline.remember(text)
        return self.processor.run(text)

    def _on_enter(self) -> None:
        text = self.cmdline.text().strip()
        self.cmdline.clear()
        if text:
            self.execute(text)

    def _on_result(self, res: Result) -> None:
        if not res.line:
            return
        self.output.appendPlainText(f"> {res.line}")
        if res.message:
            prefix = "" if res.ok else "ERROR: "
            self.output.appendPlainText(prefix + res.message)
        if res.ok and res.line.upper().startswith("PICKMODE"):
            kind = res.line.split(",")[1].strip().upper()
            if kind in self._mode_actions:
                self._mode_actions[kind].setChecked(True)
        self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())

    def _save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save command log", "session.cmd", "Command scripts (*.cmd)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.processor.log) + "\n")
            self.statusBar().showMessage(f"Saved {len(self.processor.log)} commands to {path}", 5000)

    def _run_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Run command script", "", "Command scripts (*.cmd);;All files (*)")
        if path:
            with open(path, encoding="utf-8") as f:
                self.processor.run_script(f.read())
