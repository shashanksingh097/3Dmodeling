"""Main window: viewport, toolbar, command line, output, history and parameters.

Every button, every viewport click and every edit in the History and
Parameters panels builds command text and sends it to the same
:meth:`MainWindow.execute` that the command line uses. The panels only show
what the processor holds; they never change the model themselves.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QStandardPaths, QStringListModel, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor, QFont, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..commands import Processor, Result
from ..lang.expr import format_value
from ..lang.script import strip_comment
from ..viewport.occ_view import OccViewport
from . import assist


def _mono() -> QFont:
    f = QFont("Monospace")
    f.setStyleHint(QFont.TypeWriter)
    return f


def hist_command(action: str, n: int, text: str | None = None) -> str:
    """Command text for a history action, e.g. HIST, EDIT, 3, "W = 60"."""
    return f"HIST, {action}, {n}" + (f", {format_value(text)}" if text is not None else "")


class CommandLine(QLineEdit):
    """Single-line command entry with Up/Down history, completion and argument hints.

    Completion offers the words that fit where the cursor is: command names
    at the start of a line, keywords for the argument being typed, and
    parameter and body names. Tab or Enter in the list takes a word.
    """

    def __init__(self, processor: Processor | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Type a command, e.g.  BLOCK, 0,0,0, W, 10, 10   ·   W = 40   ·   HELP")
        self.history: list[str] = []
        self._pos = 0
        self.processor = processor
        self.hint = QLabel()
        self.hint.setTextFormat(Qt.RichText)
        self._model = QStringListModel(self)
        self.completer = QCompleter(self._model, self)
        self.completer.setWidget(self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.activated.connect(self.insert_completion)
        self.textEdited.connect(self._update_assist)
        self.cursorPositionChanged.connect(lambda *_: self._update_hint())

    def remember(self, text: str) -> None:
        if text and (not self.history or self.history[-1] != text):
            self.history.append(text)
        self._pos = len(self.history)

    # ---- completion -------------------------------------------------------
    def _update_hint(self) -> None:
        if self.processor is not None:
            self.hint.setText(assist.signature(self.processor, self.text(), self.cursorPosition()))

    def _update_assist(self, *_):
        self._update_hint()
        if self.processor is None:
            return
        words = assist.completions(self.processor, self.text(), self.cursorPosition())
        ctx = assist.context(self.text(), self.cursorPosition())
        if not words or not ctx.prefix:
            self.completer.popup().hide()
            return
        self._model.setStringList(words)
        self.completer.setCompletionPrefix("")
        rect = self.cursorRect()
        rect.setWidth(max(160, self.completer.popup().sizeHintForColumn(0) + 30))
        self.completer.complete(rect)

    def insert_completion(self, word: str) -> None:
        ctx = assist.context(self.text(), self.cursorPosition())
        text, pos = self.text(), self.cursorPosition()
        new = text[: ctx.start] + word + text[pos:]
        self.setText(new)
        self.setCursorPosition(ctx.start + len(word))
        self.completer.popup().hide()
        self._update_hint()

    def keyPressEvent(self, e) -> None:
        popup = self.completer.popup()
        if popup.isVisible():
            if e.key() in (Qt.Key_Tab, Qt.Key_Return, Qt.Key_Enter):
                idx = popup.currentIndex()
                word = idx.data() if idx.isValid() else self._model.stringList()[0]
                self.insert_completion(word)
                return
            if e.key() == Qt.Key_Escape:
                popup.hide()
                return
        if e.key() == Qt.Key_Up and self.history:
            self._pos = max(0, self._pos - 1)
            self.setText(self.history[self._pos])
        elif e.key() == Qt.Key_Down and self.history:
            self._pos = min(len(self.history), self._pos + 1)
            self.setText(self.history[self._pos] if self._pos < len(self.history) else "")
        else:
            super().keyPressEvent(e)

    def focusNextPrevChild(self, nxt: bool) -> bool:  # keep Tab for completion
        return False


class EntryDialog(QDialog):
    """Edit the text of one history entry (one statement or a whole block)."""

    def __init__(self, title: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 300)
        self.edit = QPlainTextEdit(text)
        self.edit.setFont(_mono())
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("The model re-runs from this step when you press OK."))
        lay.addWidget(self.edit)
        lay.addWidget(buttons)

    def text(self) -> str:
        return self.edit.toPlainText()


class HistoryPanel(QTableWidget):
    """The history as a table: number, statement, result. Edits run HIST commands."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(0, 3)
        self.win = window
        self.setHorizontalHeaderLabels(["#", "Statement", "Result"])
        self.verticalHeader().hide()
        self.setFont(_mono())
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        h = self.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Interactive)
        h.resizeSection(2, 160)
        self.verticalHeader().setDefaultSectionSize(22)
        self.setWordWrap(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.cellDoubleClicked.connect(lambda row, _c: self.edit_row(row))

    def refresh(self) -> None:
        p = self.win.processor
        self.setRowCount(len(p.history))
        grey = QBrush(QColor(140, 140, 140))
        red = QBrush(QColor(200, 40, 40))
        amber = QBrush(QColor(176, 108, 0))
        for i, e in enumerate(p.history):
            label = e.label + ("  …" if "\n" in e.text.strip() and not e.text.strip().startswith("!") else "")
            first = (e.message or "").splitlines()[-1] if e.message else ""
            status = "suppressed" if e.suppressed else ("ERROR: " + first if not e.ok else first)
            if e.ok and e.warning and not e.suppressed:
                status = "CHECK: " + e.warning.splitlines()[0]
            cells = [str(i + 1), label, status]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(e.text if c == 1 else (e.message or ""))
                if i >= p.cursor or e.suppressed:
                    item.setForeground(grey)
                elif not e.ok:
                    item.setForeground(red)
                elif e.warning:
                    item.setForeground(amber)
                self.setItem(i, c, item)
        if p.cursor:
            self.scrollToItem(self.item(p.cursor - 1, 0))

    def _menu(self, pos) -> None:
        row = self.rowAt(pos.y())
        p = self.win.processor
        menu = QMenu(self)
        if 0 <= row < p.cursor:
            n = row + 1
            e = p.history[row]
            menu.addAction("Edit…", lambda: self.edit_row(row))
            menu.addAction("Insert before…", lambda: self._insert(n))
            menu.addAction("Resume" if e.suppressed else "Suppress",
                           lambda: self.win.execute(hist_command("RESUME" if e.suppressed else "SUPPRESS", n)))
            menu.addAction("Delete", lambda: self.win.execute(hist_command("DELETE", n)))
            menu.addSeparator()
            back = p.cursor - n
            if back:
                menu.addAction(f"Roll back to here (undo {back})", lambda: self.win.execute(f"UNDO, {back}"))
        elif row >= p.cursor and row < len(p.history):
            menu.addAction(f"Redo up to here ({row + 1 - p.cursor})",
                           lambda: self.win.execute(f"REDO, {row + 1 - p.cursor}"))
        menu.addAction("Add at the end…", lambda: self._insert(p.cursor + 1))
        menu.addAction("Replay all", lambda: self.win.execute("HIST, REPLAY"))
        menu.exec(self.viewport().mapToGlobal(pos))

    def edit_row(self, row: int) -> None:
        p = self.win.processor
        if not 0 <= row < p.cursor:
            return
        dlg = EntryDialog(f"Edit history entry {row + 1}", p.history[row].text, self)
        if dlg.exec() == QDialog.Accepted and dlg.text().strip() != p.history[row].text.strip():
            self.win.execute(hist_command("EDIT", row + 1, dlg.text()))

    def _insert(self, n: int) -> None:
        dlg = EntryDialog(f"New history entry at {n}", "", self)
        if dlg.exec() == QDialog.Accepted and dlg.text().strip():
            self.win.execute(hist_command("INSERT", n, dlg.text()))


class ParamPanel(QTableWidget):
    """Parameters and their values. Editing a value edits the entry that defines it."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(0, 2)
        self.win = window
        self._filling = False
        self.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.verticalHeader().hide()
        self.setFont(_mono())
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.verticalHeader().setDefaultSectionSize(22)
        self.itemChanged.connect(self._changed)

    def refresh(self) -> None:
        p = self.win.processor
        self._filling = True
        try:
            self.setRowCount(len(p.params))
            for row, (name, value) in enumerate(sorted(p.params.items())):
                key = QTableWidgetItem(name)
                key.setFlags(key.flags() & ~Qt.ItemIsEditable)
                val = QTableWidgetItem(format_value(value))
                entry = p.entry_for_param(name)
                if entry is None:
                    val.setFlags(val.flags() & ~Qt.ItemIsEditable)
                    val.setForeground(QBrush(QColor(140, 140, 140)))
                    val.setToolTip("Set inside a block or macro: edit it in the History panel")
                else:
                    val.setToolTip(f"Defined by history entry {entry}: {p.history[entry - 1].label}\n"
                                   "Type a new value or expression to rebuild the model")
                self.setItem(row, 0, key)
                self.setItem(row, 1, val)
        finally:
            self._filling = False

    def _changed(self, item: QTableWidgetItem) -> None:
        if self._filling or item.column() != 1:
            return
        p = self.win.processor
        name = self.item(item.row(), 0).text()
        entry = p.entry_for_param(name)
        new = item.text().strip()
        if entry is None or not new:
            self.refresh()
            return
        old_text = p.history[entry - 1].text
        # keep comment lines above the assignment
        lines = old_text.splitlines()
        comment = lines[-1][len(strip_comment(lines[-1])):].strip()
        lines[-1] = f"{name} = {new}" + (f"    {comment}" if comment else "")
        res = self.win.execute(hist_command("EDIT", entry, "\n".join(lines)))
        if not res.ok:
            self.refresh()


class MainWindow(QMainWindow):
    def __init__(self, processor: Processor | None = None, autosave: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("3Dmodeling")
        self.resize(1400, 860)
        self.processor = processor or Processor()

        self.viewport = OccViewport(self.processor.model)
        self.viewport.command.connect(self.execute)
        self.processor.view = self.viewport

        self.output = QPlainTextEdit(readOnly=True)
        self.output.setFont(_mono())
        self.prompt = QLabel(">")
        self.prompt.setFont(_mono())
        self.cmdline = CommandLine(self.processor)
        self.cmdline.setFont(_mono())
        self.cmdline.hint.setContentsMargins(22, 2, 4, 0)
        self.cmdline.returnPressed.connect(self._on_enter)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.viewport, 1)
        row = QHBoxLayout()
        row.setContentsMargins(4, 0, 0, 0)
        row.addWidget(self.prompt)
        row.addWidget(self.cmdline, 1)
        lay.addWidget(self.cmdline.hint)  # above the line, so the completion list never covers it
        lay.addLayout(row)
        self.setCentralWidget(central)

        self.history_panel = HistoryPanel(self)
        self.param_panel = ParamPanel(self)
        out = self._dock("Output", self.output, Qt.BottomDockWidgetArea)
        hist = self._dock("History", self.history_panel, Qt.RightDockWidgetArea)
        params = self._dock("Parameters", self.param_panel, Qt.RightDockWidgetArea)
        self.resizeDocks([hist, params], [460, 460], Qt.Horizontal)
        self.resizeDocks([hist, params], [520, 260], Qt.Vertical)
        self.resizeDocks([out], [170], Qt.Vertical)

        self.processor.listeners.append(self._on_result)
        self.processor.history_listeners.append(self._on_history)
        self._build_toolbar()
        self.statusBar().showMessage(
            "Left drag: orbit · Middle/right drag: pan · Wheel: zoom · Click: pick (Ctrl adds, Alt removes)"
        )
        self._setup_autosave(autosave)
        self._on_history()

    def _dock(self, title: str, widget: QWidget, area) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        dock.setObjectName(title.lower())
        self.addDockWidget(area, dock)
        return dock

    # ---- toolbar: every action is just command text ---------------------
    def _build_toolbar(self) -> None:
        tb = QToolBar("Main", self)
        tb.setObjectName("main")
        self.addToolBar(tb)

        def cmd_action(label: str, text: str, tip: str = "", shortcut=None) -> QAction:
            act = QAction(label, self)
            act.setToolTip(f"{tip or label}\nRuns: {text}")
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(lambda _=False, t=text: self.execute(t))
            tb.addAction(act)
            return act

        self.undo_action = cmd_action("Undo", "UNDO", "Undo the last step", QKeySequence.Undo)
        self.redo_action = cmd_action("Redo", "REDO", "Redo", QKeySequence.Redo)
        tb.addSeparator()
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
        cmd_action("Clear", "CLEAR", "Delete every body")

        def dlg_action(label: str, tip: str, slot, shortcut=None) -> QAction:
            act = QAction(label, self)
            act.setToolTip(tip)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(slot)
            tb.addAction(act)
            return act

        dlg_action("Open…", "Open a project (.m3d)\nRuns: OPEN, file", self._open_project, QKeySequence.Open)
        dlg_action("Save…", "Save the project (.m3d)\nRuns: SAVE, file", self._save_project, QKeySequence.Save)
        dlg_action("Import…", "Import STEP, IGES, BREP or STL\nRuns: IMPORT, format, file", self._import_file)
        self.recover_action = cmd_action("Recover", "OPEN, AUTOSAVE", "Open the autosave from the last session")
        self.recover_action.setVisible(False)
        tb.addSeparator()
        dlg_action("Save log…", "Save the history as a script that rebuilds this model", self._save_log)
        dlg_action("Run script…", "Run a .cmd script\nRuns: RUN, file", self._run_file)

    # ---- running commands --------------------------------------------------
    def execute(self, text: str) -> Result:
        """The single entry point for GUI actions, clicks and typed text."""
        self.cmdline.remember(text)
        if "\n" in text and not text.upper().startswith("HIST"):
            results = self.processor.run_script(text)
            return results[-1] if results else Result("", True)
        return self.processor.run(text)

    def _on_enter(self) -> None:
        text = self.cmdline.text()
        self.cmdline.clear()
        if text.strip() or self.processor.pending:
            self.execute(text)

    def _on_result(self, res: Result) -> None:
        if res.pending:
            self.output.appendPlainText(f"{self.prompt.text()} {res.line}")
            self.prompt.setText("…")
            self.cmdline.setPlaceholderText("Block continues: type its lines, then the closing *END... line")
            return
        self.prompt.setText(">")
        self.cmdline.setPlaceholderText("Type a command, e.g.  BLOCK, 0,0,0, W, 10, 10   ·   W = 40   ·   HELP")
        if not res.line:
            return
        self.output.appendPlainText("> " + "\n  ".join(res.line.splitlines()))
        if res.message:
            prefix = "" if res.ok else "ERROR: "
            self.output.appendPlainText(prefix + res.message)
        if res.ok and res.line.upper().startswith("PICKMODE"):
            kind = res.line.split(",")[1].strip().upper()
            if kind in self._mode_actions:
                self._mode_actions[kind].setChecked(True)
        self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())

    def _on_history(self) -> None:
        p = self.processor
        self.history_panel.refresh()
        self.param_panel.refresh()
        self.undo_action.setEnabled(p.cursor > 0)
        self.redo_action.setEnabled(p.cursor < len(p.history))

    def _save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save command log", "session.cmd", "Command scripts (*.cmd)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.processor.script())
            self.statusBar().showMessage(f"Saved {self.processor.cursor} history entries to {path}", 5000)

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "Projects (*.m3d);;All files (*)")
        if path:
            self.execute(f'OPEN, "{path}"')

    def _save_project(self) -> None:
        start = self.processor.project_path or "model.m3d"
        path, _ = QFileDialog.getSaveFileName(self, "Save project", start, "Projects (*.m3d)")
        if path:
            self.execute(f'SAVE, "{path}"')

    def _import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import", "", "Shapes (*.step *.stp *.iges *.igs *.brep *.stl);;All files (*)")
        if path:
            ext = os.path.splitext(path)[1].lower()
            fmt = {".stp": "STEP", ".step": "STEP", ".igs": "IGES", ".iges": "IGES", ".stl": "STL"}.get(ext, "BREP")
            self.execute(f'IMPORT, {fmt}, "{path}"')

    # ---- autosave -----------------------------------------------------------
    def _setup_autosave(self, path: str | None) -> None:
        """Save the project a moment after every change. The autosave of the
        last session is moved aside first, so OPEN, AUTOSAVE can bring it back."""
        if path is None:
            path = os.environ.get("MODELER_AUTOSAVE") or os.path.join(
                QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or os.path.expanduser("~/.modeler3d"),
                "autosave.m3d")
        self.autosave_path = path if path != "off" else None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(1500)
        self._autosave_timer.timeout.connect(self.autosave_now)
        if not self.autosave_path:
            return
        previous = os.path.splitext(self.autosave_path)[0] + "-previous.m3d"
        if os.path.isfile(self.autosave_path):
            os.replace(self.autosave_path, previous)
        if os.path.isfile(previous):
            self.processor.autosave_path = previous
            self.recover_action.setVisible(True)
            self.statusBar().showMessage(
                "Work from the last session was autosaved: press Recover, or type OPEN, AUTOSAVE", 15000)
        self.processor.history_listeners.append(self._autosave_timer.start)

    def autosave_now(self) -> None:
        if not self.autosave_path or self.processor.cursor == 0:
            return
        from ..commands.project_handlers import save_project

        try:
            save_project(self.processor, self.autosave_path)
        except OSError as exc:
            self.statusBar().showMessage(f"Autosave failed: {exc}", 5000)

    def _run_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Run command script", "", "Command scripts (*.cmd);;All files (*)")
        if path:
            self.execute(f'RUN, "{path}"')
