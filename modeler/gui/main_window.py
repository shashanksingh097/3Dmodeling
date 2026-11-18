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
    QInputDialog,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..commands import Processor, Result
from ..lang.expr import format_value
from ..viewport.occ_view import OccViewport
from . import assist
from . import body_menu as bm
from . import feature_actions as fa
from . import form_dialog as fd
from .progress import RebuildProgress


def _mono() -> QFont:
    f = QFont("Monospace")
    f.setStyleHint(QFont.TypeWriter)
    return f


def strip_comment_lines(text: str) -> str:
    """An entry's text without its leading comment and blank lines."""
    lines = text.splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("!")):
        lines.pop(0)
    return "\n".join(lines)


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
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)  # several rows: make a part of them
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
        inside = False
        for i, e in enumerate(p.history):
            label = e.label + ("  …" if "\n" in e.text.strip() and not e.text.strip().startswith("!") else "")
            word = e.label.split(",")[0].strip().upper()
            if inside and word not in ("SKETCH", "EXTRUDE", "REVOLVE"):
                label = "    " + label  # a step inside the sketch above
            if word == "SKETCH" and e.ok and not e.suppressed and "DELETE" not in e.label.upper():
                inside = True
            elif word in ("ENDSKETCH", "EXTRUDE", "REVOLVE") or (word == "SKETCH" and not e.ok):
                inside = False
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
        rows = sorted({i.row() for i in self.selectedIndexes()})
        if len(rows) > 1 and rows[-1] < p.cursor and rows == list(range(rows[0], rows[-1] + 1)):
            a, b = rows[0] + 1, rows[-1] + 1
            menu.addAction(f"Make a part from steps {a} to {b}…", lambda: self.make_part(a, b))
            menu.addSeparator()
        if 0 <= row < p.cursor:
            n = row + 1
            e = p.history[row]
            menu.addAction("Edit…", lambda: self.edit_row(row))
            if fd.F.has_form(e.text):
                menu.addAction("Edit in form…", lambda: self.win.open_form("", e.text, row))
            from .sweep_editor import _is_sweep

            if _is_sweep(e.text):
                menu.addAction("Sweep editor…", lambda: self.win.open_sweep_editor(row))
            menu.addAction("Insert before…", lambda: self._insert(n))
            menu.addAction("Resume" if e.suppressed else "Suppress",
                           lambda: self.win.execute(hist_command("RESUME" if e.suppressed else "SUPPRESS", n)))
            menu.addAction("Delete", lambda: self.win.execute(hist_command("DELETE", n)))
            import re

            pm = re.match(r"\s*\*PART\s*,\s*([A-Za-z_][A-Za-z0-9_]*)", strip_comment_lines(e.text))
            if pm:
                menu.addAction(f"Edit part {pm.group(1).lower()}…", lambda: self.win.edit_part(pm.group(1)))
            sk = self._sketch_of(row)
            if sk:
                menu.addAction(f"Sizes of sketch {sk}…", lambda: self.win.sketch_ui.edit_sizes(sk))
            made = bm.entry_bodies(p, row)
            if made:
                what = f"body {made[0]}" if len(made) == 1 else f"{len(made)} bodies"
                sub = menu.addMenu(f"Made by this step ({what})")
                self.win.fill_menu(sub, bm.entry_items(p, row))
            menu.addSeparator()
            back = p.cursor - n
            if back:
                menu.addAction(f"Roll back to here ({back} later step{'s' if back > 1 else ''} kept to redo)", lambda: self.win.execute(f"HIST, ROLLBACK, {n}"))
        elif row >= p.cursor and row < len(p.history):
            menu.addAction(f"Redo up to here ({row + 1 - p.cursor})",
                           lambda: self.win.execute(f"HIST, ROLLBACK, {row + 1}"))
        menu.addAction("Add at the end…", lambda: self._insert(p.cursor + 1))
        menu.addAction("Replay all", lambda: self.win.execute("HIST, REPLAY"))
        menu.exec(self.viewport().mapToGlobal(pos))

    def select_entry(self, uid: int) -> bool:
        """Select and show the row of the history entry with this uid."""
        for i, e in enumerate(self.win.processor.history):
            if e.uid == uid:
                self.selectRow(i)
                self.scrollToItem(self.item(i, 0))
                return True
        return False

    def make_part(self, first: int, last: int, name: str | None = None) -> None:
        """Turn history steps into a reusable part, placed once where it was."""
        if name is None:
            from .feature_actions import free_name

            suggestion = free_name(self.win.processor, "part")
            name, ok = QInputDialog.getText(self, "Make a part", f"Steps {first} to {last} become a part named:",
                                            text=suggestion)
            if not ok or not name.strip():
                return
        self.win.execute(hist_command("PART", first, f"{last}, {name.strip()}"))

    def _sketch_of(self, row: int) -> str | None:
        """The sketch a history row belongs to (its SKETCH line or a step inside it)."""
        p = self.win.processor
        for i in range(row, -1, -1):
            word = p.history[i].label.split(",")
            head = word[0].strip().upper()
            if head == "SKETCH" and len(word) > 1:
                name = word[1].strip()
                return name if name.upper() in p.model.sketches else None
            if head == "ENDSKETCH" and i != row:
                return None
            if head in ("EXTRUDE", "REVOLVE") and len(word) > 1:
                name = word[1].strip()
                return name if name.upper() in p.model.sketches else None
        return None

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
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def _menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction("New parameter…", lambda: self.win.open_form("="))
        menu.exec(self.viewport().mapToGlobal(pos))

    def refresh(self) -> None:
        p = self.win.processor
        inputs: set[str] = set()
        if p.part_doc is not None:
            from ..commands.partdoc_handlers import part_inputs

            inputs = {k for k, _ in part_inputs(p)}
        self._filling = True
        try:
            self.setRowCount(len(p.params))
            for row, (name, value) in enumerate(sorted(p.params.items())):
                key = QTableWidgetItem(name)
                key.setFlags(key.flags() & ~Qt.ItemIsEditable)
                if name in inputs:
                    f = key.font()
                    f.setBold(True)
                    key.setFont(f)
                    key.setToolTip(f"An input of part {p.part_doc.name}: its value here is the part's default")
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
        from .item_model import param_edit

        res = self.win.execute(param_edit(p, name, new))
        if not res.ok:
            self.refresh()


class MainWindow(QMainWindow):
    def __init__(self, processor: Processor | None = None, autosave: str | None = None,
                 settings=None, guard=None) -> None:
        super().__init__()
        self.setWindowTitle("3Dmodeling")
        self.resize(1400, 860)
        self.processor = processor or Processor()

        self.viewport = OccViewport(self.processor.model)
        self.viewport.command.connect(self.execute)
        self.viewport.body_menu.connect(self.show_body_menu)
        self.processor.view = self.viewport
        self.rebuild_progress = RebuildProgress(self)
        self.processor.progress = self.rebuild_progress

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
        self.form_button = QPushButton("Form")
        self.form_button.setToolTip("Fill in the typed command in a form (F2); with nothing typed, find a command")
        self.form_button.setShortcut(QKeySequence("F2"))
        self.form_button.clicked.connect(self.form_for_typed)
        row.addWidget(self.form_button)
        lay.addWidget(self.cmdline.hint)  # above the line, so the completion list never covers it
        lay.addLayout(row)
        self.setCentralWidget(central)

        self.history_panel = HistoryPanel(self)
        self.param_panel = ParamPanel(self)
        out = self._dock("Output", self.output, Qt.BottomDockWidgetArea)
        hist = self._dock("History", self.history_panel, Qt.RightDockWidgetArea)
        params = self._dock("Parameters", self.param_panel, Qt.RightDockWidgetArea)
        from .layer_panel import LayerPanel

        self.layer_panel = LayerPanel(self)
        layers = self._dock("Layers", self.layer_panel, Qt.RightDockWidgetArea)
        self.tabifyDockWidget(params, layers)
        from .assistant_panel import AssistantPanel

        self.assistant_panel = AssistantPanel(self)
        assistant = self._dock("Assistant", self.assistant_panel, Qt.RightDockWidgetArea)
        self.tabifyDockWidget(params, assistant)
        self.assistant_dock = assistant
        params.raise_()
        self.layers_dock = layers
        from .model_tree import ModelTree

        from PySide6.QtWidgets import QSplitter

        from .item_panel import ItemPanel

        self.model_tree = ModelTree(self)
        self.item_panel = ItemPanel(self)  # the steps of the picked body, under the tree
        split = QSplitter(Qt.Vertical)
        split.setObjectName("model_split")
        split.addWidget(self.model_tree)
        split.addWidget(self.item_panel)
        split.setSizes([480, 320])
        self.tree_dock = self._dock("Model", split, Qt.LeftDockWidgetArea)
        self.resizeDocks([self.tree_dock], [300], Qt.Horizontal)
        self.resizeDocks([hist, params], [460, 460], Qt.Horizontal)
        self.resizeDocks([hist, params], [520, 260], Qt.Vertical)
        self.resizeDocks([out], [170], Qt.Vertical)

        self.processor.listeners.append(self._on_result)
        self.processor.history_listeners.append(self._on_history)
        from .app_shell import AppShell

        self.shell = AppShell(self, settings, guard)
        self._build_toolbar()
        self.shell.build_file_menu()
        fd.command_menu(self, self.menuBar().addMenu("&Commands"))
        from .sketch_ui import SketchUI

        self.sketch_ui = SketchUI(self)
        self.build_view_menu()
        self.shell.build_help_menu()
        self.statusBar().showMessage(
            "Left drag: orbit · Middle/right drag: pan · Wheel: zoom · Click: pick (Ctrl adds, Alt removes)"
        )
        self._setup_autosave(autosave)
        from .link_watch import LinkWatcher

        self.link_watch = LinkWatcher(self)  # linked part files changed on disk: RELOAD
        self._on_history()
        self.shell.update_title()
        self.shell.restore_layout()
        from . import toolbars as _tbs

        _tbs.restore(self)
        from . import prefs as _prefs

        _prefs.restore(self)
        self.shell.report_last_session()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt name
        self.shell.close_event(event)

    def _dock(self, title: str, widget: QWidget, area) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        dock.setObjectName(title.lower())
        self.addDockWidget(area, dock)
        return dock

    # ---- toolbars: every button is just command text -----------------------
    def _build_toolbar(self) -> None:
        """The toolbar groups (gui/toolbars.py): each button has an icon and
        keeps its name, and only builds command text and runs it."""
        from . import toolbars as tbs

        def cmd(tb, label: str, icon: str, text: str, tip: str = "", shortcut=None) -> QAction:
            return tbs.action(self, tb, label, icon, f"{tip or label}\nRuns: {text}",
                              lambda _=False, t=text: self.execute(t), shortcut)

        def form(tb, label: str, icon: str, name: str, tip: str) -> QAction:
            return tbs.action(self, tb, label, icon, f"{tip}: opens its form\nRuns: {name}, ...",
                              lambda _=False, n=name: self.open_form(n))

        def dlg(tb, label: str, icon: str, tip: str, slot, shortcut=None) -> QAction:
            return tbs.action(self, tb, label, icon, tip, lambda _=False: slot(), shortcut)

        tb = tbs.group(self, "File", "file", "Home")
        dlg(tb, "Open…", "open", "Open a project (.m3d) (Ctrl+O)\nRuns: OPEN, file", self._open_project)
        dlg(tb, "Save", "save", "Save the project (.m3d) (Ctrl+S)\nRuns: SAVE, file", self._save_project)
        dlg(tb, "Import…", "import", "Import STEP, IGES, BREP, STL, OBJ, 3MF, glTF, PLY, VTK... (Ctrl+I)\n"
                                     "Runs: IMPORT, format, file", self._import_file)
        dlg(tb, "Export…", "export", "Export all bodies as STEP, IGES, STL, OBJ, 3MF, glTF or BREP (Ctrl+E)\n"
                                     "Runs: EXPORT, format, file", lambda: self.shell.export_file())
        self.recover_action = cmd(tb, "Recover", "recover", "OPEN, AUTOSAVE", "Open the autosave from the last session")
        self.recover_action.setVisible(False)
        dlg(tb, "Save log…", "savelog", "Save the history as a script that rebuilds this model", self._save_log)
        dlg(tb, "Run script…", "runscript", "Run a .cmd script\nRuns: RUN, file", self._run_file)

        tb = tbs.group(self, "Edit", "edit", "Home")
        self.undo_action = cmd(tb, "Undo", "undo", "UNDO", "Undo the last step", QKeySequence.Undo)
        self.redo_action = cmd(tb, "Redo", "redo", "REDO", "Redo", QKeySequence.Redo)
        tbs.action(self, tb, "Commands…", "commands",
                   "Find any command by name or by what it does, and fill in its form (Ctrl+K)",
                   lambda: fd.find_command(self), "Ctrl+K")
        cmd(tb, "Clear", "clear", "CLEAR", "Delete every body")

        tb = tbs.group(self, "Shapes", "shapes", "Model")
        form(tb, "Block…", "block", "BLOCK", "Add a block")
        form(tb, "Cylinder…", "cylinder", "CYL", "Add a cylinder")
        form(tb, "Sphere…", "sphere", "SPHERE", "Add a sphere")
        form(tb, "Cone…", "cone", "CONE", "Add a cone")
        form(tb, "Torus…", "torus", "TORUS", "Add a torus")

        tb = tbs.group(self, "Booleans", "booleans", "Model")
        form(tb, "Union…", "union", "UNION", "Join bodies into one")
        form(tb, "Subtract…", "subtract", "SUBTRACT", "Cut bodies out of a body")
        form(tb, "Intersect…", "intersect", "INTERSECT", "Keep what bodies share")

        tb = tbs.group(self, "Patterns", "patterns", "Model")
        form(tb, "Array…", "array", "ARRAY", "Copies of a body in a row, a grid or round an axis")
        form(tb, "Pattern…", "pattern", "PATTERN", "Repeat history steps (a hole, a boss) along a row or round an axis")
        form(tb, "Mirror…", "mirror", "MIRROR", "A mirror copy of a body")

        # picking and the view are on Home, and in the quick-access icons on every tab
        tb = tbs.group(self, "Pick", "pick", "Home")
        group = QActionGroup(self)
        group.setExclusive(True)
        self._mode_actions: dict[str, QAction] = {}
        for kind in ("BODY", "FACE", "EDGE", "VERTEX"):
            act = cmd(tb, kind.title(), f"pick_{kind.lower()}", f"PICKMODE, {kind}", f"Pick {kind.lower()}s")
            act.setCheckable(True)
            group.addAction(act)
            self._mode_actions[kind] = act
        self._mode_actions["FACE"].setChecked(True)

        tb = tbs.group(self, "View", "view", "Home")
        for name in ("ISO", "TOP", "FRONT", "RIGHT"):
            cmd(tb, name.title(), name.lower(), f"VIEW, {name}", f"{name.title()} view")
        fit = cmd(tb, "Fit", "fit", "FIT", "Zoom to fit", "F")
        self._build_feature_toolbar()
        tbs.quick_access(self, [self.undo_action, self.redo_action, None,
                                *self._mode_actions.values(), None, fit])

    def _build_feature_toolbar(self) -> None:
        """Sketches, datums, features and measuring, in groups. Each button
        reads the selection, builds the command text and runs it, exactly as
        if it were typed."""
        from . import toolbars as tbs

        def act(tb, label: str, icon: str, tip: str, build) -> QAction:
            return tbs.action(self, tb, label, icon, tip, lambda _=False, b=build: self.run_feature(b))

        def ask(title: str, label: str, value: float, lo: float = 0.0, hi: float = 1e6):
            v, ok = QInputDialog.getDouble(self, title, label, value, lo, hi, 3)
            if not ok:
                raise fa.NeedInput("")
            return v

        p = self.processor
        tb = tbs.group(self, "Sketch", "sketching", "Features")
        act(tb, "Sketch", "sketch", "Start a 2D sketch on the picked flat face, or on a plane you choose\n"
                                    "Runs: SKETCH, name, FACE, id / SKETCH, name, plane",
            lambda: self.sketch_ui.new_sketch() or [])
        act(tb, "Extrude…", "extrude", "Push a sketch into a solid: a new body, or added to / cut from a body\n"
                                       "Runs: EXTRUDE, sketch, d [, ADD/CUT, body]", lambda: self.sketch_ui.extrude() or [])
        act(tb, "Revolve…", "revolve", "Turn a sketch about an axis into a solid\nRuns: REVOLVE, sketch, axis, angle",
            lambda: self.sketch_ui.revolve() or [])
        act(tb, "Sweep editor…", "sweep", "Shape the twist and scale of a SWEEP by dragging handles, with a preview\n"
                                          "Edits the step selected in History, or the last SWEEP; Apply runs HIST, EDIT",
            lambda: (self.open_sweep_editor(), [])[1])

        tb = tbs.group(self, "Datums", "datums", "Features")
        act(tb, "Plane", "plane", "Datum plane on the picked flat face\nRuns: PLANE, P1, FACE, id",
            lambda: fa.plane_on_face(p))
        act(tb, "Work plane", "workplane", "Draw new shapes on the picked flat face (press again to go back to world XY)\n"
                                           "Runs: PLANE, WP1, FACE, id then WORKPLANE, WP1", lambda: fa.workplane_on_face(p))

        tb = tbs.group(self, "Features", "features", "Features")
        act(tb, "Hole…", "hole", "Through hole at the middle of the picked flat face\nRuns: HOLE, body, x,y,z, d",
            lambda: fa.hole_on_face(p, ask("Hole", "Diameter:", 6.0, 0.001)))
        tbs.action(self, tb, "Fillet…", "s_fillet", "Round the picked edges: opens its form\nRuns: FILLET, ...",
                   lambda: self.open_form("FILLET"))
        tbs.action(self, tb, "Chamfer…", "s_chamfer", "Bevel the picked edges: opens its form\nRuns: CHAMFER, ...",
                   lambda: self.open_form("CHAMFER"))
        act(tb, "Shell…", "shell", "Hollow the part, open at the selected faces (or closed, for selected bodies)\n"
                                   "Runs: SHELL, t",
            lambda: fa.faces_selected(p, "SHELL", ask("Shell", "Wall thickness:", 2.0, 0.001)))
        act(tb, "Draft…", "draft", "Tilt the selected side faces for moulding\nRuns: DRAFT, angle",
            lambda: fa.faces_selected(p, "DRAFT", ask("Draft", "Angle (degrees):", 3.0, -89, 89)))
        act(tb, "Push/Pull…", "pushpull", "Move the selected faces along their normals (+ adds material, - removes it)\n"
                                          "Runs: PUSHPULL, d",
            lambda: fa.faces_selected(p, "PUSHPULL", ask("Push/Pull", "Distance:", 2.0, -1e6)))
        act(tb, "Delete faces", "delface", "Remove the selected faces and close the gap (a hole, boss or fillet goes "
                                           "away)\nRuns: DELFACE", lambda: fa.faces_selected(p, "DELFACE", None))

        tb = tbs.group(self, "Freeform", "freeform", "Freeform")
        act(tb, "Control points", "cpoints", "Show the control points of the picked curve or surface; drag one to "
                                             "move it (press again to hide them)\nRuns: CPOINTS, body; each drag runs MOVEPT",
            lambda: fa.control_points_toggle(p))
        knife = tbs.action(self, tb, "Knife", "knife",
                           "Draw a stroke across a body to cut it straight through, along the view direction; "
                           "end where you started to cut out the inside (Esc ends the tool)\n"
                           "Each stroke runs: SPLINE, ... then KNIFE, body, LAST, 0, view direction "
                           "(a width in place of the 0 cuts a slot)", checkable=True)
        knife.toggled.connect(lambda on: self.viewport.set_knife(on) if self.viewport.knife != on else None)
        self.viewport.knife_changed.connect(lambda on: knife.setChecked(on) if knife.isChecked() != on else None)
        self.knife_action = knife
        act(tb, "Zebra", "zebra", "Zebra stripes on the picked body, and each join between its faces judged G2, G1 or "
                                  "creased (press again to end it; the form has curvature and draft maps)\n"
                                  "Runs: ANALYZE, body, ZEBRA / ANALYZE, OFF", lambda: fa.zebra_toggle(p))

        from . import sculpt_tool

        sculpt_tool.build(self)

        tb = tbs.group(self, "Measure", "measure", "Inspect")
        act(tb, "Distance", "distance", "Shortest distance between the two selected things\nRuns: DIST",
            lambda: fa.two_selected(p, "DIST"))
        act(tb, "Angle", "angle", "Angle between the two selected faces or edges\nRuns: ANGLE",
            lambda: fa.two_selected(p, "ANGLE"))
        act(tb, "Mass", "mass", "Volume, centre and inertia of the bodies\nRuns: MASSPROP", lambda: ["MASSPROP"])
        act(tb, "Clash", "clash", "Check whether any bodies overlap\nRuns: CLASH", lambda: ["CLASH"])
        act(tb, "Section", "section", "Cut the view open at the last datum plane (or XY); press again to close it\n"
                                      "Runs: SECTION, plane / SECTION, OFF", lambda: fa.section_toggle(p))

    def build_view_menu(self) -> None:
        """View > Toolbar buttons (icons and names, icons only ...), Collapse ribbon and Ribbon tab."""
        from . import toolbars as tbs

        m = self.menuBar().addMenu("&View")
        tbs.style_menu(self, m)
        tbs.ribbon_menu(self, m)
        m.addSeparator()
        a = m.addAction("&Preferences…")
        a.setShortcut("Ctrl+,")
        a.setToolTip("Theme (light, dark or the system's), the 3D view's background and the toolbar buttons")
        a.triggered.connect(self.open_preferences)
        self.preferences_action = a
        self.view_menu = m

    def open_preferences(self):
        from .prefs import open_dialog

        return open_dialog(self)

    def open_sweep_editor(self, row: int | None = None):
        """Shape a SWEEP's twist and scale by dragging handles (see gui/sweep_editor.py)."""
        from .sweep_editor import open_editor

        return open_editor(self, row)

    # ---- right-click menus on bodies (gui/body_menu.py says what they hold) ----
    def show_body_menu(self, bid: int, global_pos) -> None:
        """The menu for a right click in the 3D view: on a body, or on empty space."""
        m = self.processor.model
        items = bm.body_items(m, bid, self.processor.part_files) if bid in m.bodies else bm.empty_items(m)
        menu = QMenu(self)
        self.fill_menu(menu, items)
        self._body_menu = menu  # tests read it
        menu.popup(global_pos)

    def fill_menu(self, menu: QMenu, items: list) -> None:
        for item in items:
            if not item.label:
                menu.addSeparator()
            elif item.title:
                act = menu.addAction(item.label)
                f = act.font()
                f.setBold(True)
                act.setFont(f)
                act.setEnabled(False)
            else:
                act = menu.addAction(item.label, lambda it=item: self.run_menu_item(it))
                act.setEnabled(item.enabled)

    def edit_part(self, name: str):
        """Open a part defined in this project (its *PART step) in a part window of
        its own; saving there writes the new block back with HIST, EDIT."""
        from ..commands import CommandError
        from ..commands.lineage import part_entry
        from ..commands.partdoc_handlers import open_part_text

        p = self.processor
        row = part_entry(p, name, p.cursor)
        if row is None and name.upper() in p.part_files:
            return self.open_file_part(name)
        if row is None:
            self.statusBar().showMessage(
                f"Part {name.lower()} is not defined in this project's history (it may come from a part file: "
                "use File > Open part)", 8000)
            return None

        def sink(block: str) -> str:
            at = part_entry(p, name, p.cursor)  # the history may have moved since the window opened
            if at is None:
                raise CommandError(f"SAVEPART: part {name.lower()} is no longer in the project")
            lines = p.history[at].text.splitlines()
            head = next(i for i, ln in enumerate(lines) if ln.lstrip().upper().startswith("*PART"))
            text = "\n".join(lines[:head] + [block])  # keep the comments above the block
            res = self.execute(hist_command("EDIT", at + 1, text))
            if not res.ok:
                raise CommandError(f"SAVEPART: the project did not take the new part: {res.message}")
            return f"part {name.lower()} updated in the project (history step {at + 1}); every copy is rebuilt"

        w = self._part_window()
        try:
            open_part_text(w.processor, p.history[row].text, name, sink=sink,
                           where=f"step {row + 1} of {self.shell.file_label()}")
        except CommandError as exc:
            w.close()
            self.statusBar().showMessage(str(exc), 8000)
            return None
        w.shell.mark_saved()
        w.output.appendPlainText(f"Editing part {name.lower()} from {self.shell.file_label()}. "
                                 "File > Save puts it back into that project.")
        w.show()
        self._part_windows = [x for x in getattr(self, "_part_windows", []) if x.isVisible()] + [w]
        return w

    def _part_window(self) -> MainWindow:
        w = MainWindow(Processor(), autosave="off")  # (never touch this window's autosave)
        if self.shell.keep_layout:  # the app: ask before unsaved part edits are closed
            w.shell.ask_unsaved = w.shell._ask_unsaved_dialog
        return w

    def open_file_part(self, name: str):
        """Open a part read from a part file (LIB, LINK or LOAD) in a part window.
        Saving there writes the file; for a linked part this window then
        re-reads it, so every copy updates."""
        from ..commands import CommandError
        from ..commands.partdoc_handlers import open_part_text

        p = self.processor
        path, kind = p.part_files[name.upper()]
        if kind == "copy" or not os.path.isfile(path):
            self.statusBar().showMessage(f"The part file of {name.lower()} is missing: {path}", 8000)
            return None
        w = self._part_window()
        try:
            with open(path, encoding="utf-8") as fh:
                open_part_text(w.processor, fh.read(), name, file=path)
        except (OSError, CommandError) as exc:
            w.close()
            self.statusBar().showMessage(str(exc), 8000)
            return None
        w.shell.mark_saved()
        if kind == "linked":
            w.output.appendPlainText(f"Editing part {name.lower()} from {path}. File > Save writes the file, and "
                                     f"{self.shell.file_label()} updates every copy.")
        else:
            w.output.appendPlainText(f"Editing part {name.lower()} from {path}. {self.shell.file_label()} loaded a "
                                     "copy of it (LIB, LOAD), so saving here changes the file only; link it with "
                                     "LIB, LINK to follow the file.")

        def saved(res) -> None:
            if res.ok and res.line and res.line.split(",")[0].strip().upper() == "SAVEPART":
                QTimer.singleShot(0, self.reload_links)

        w.processor.listeners.append(saved)
        w.show()
        self._part_windows = [x for x in getattr(self, "_part_windows", []) if x.isVisible()] + [w]
        return w

    def reload_links(self) -> bool:
        """Re-read linked part files that changed (RELOAD); True when it ran."""
        from ..commands.part_handlers import links_changed

        p = self.processor
        if p.pending or not links_changed(p):
            return False
        res = self.execute("RELOAD")
        if res.ok:
            self.statusBar().showMessage(res.message.splitlines()[0], 8000)
        return True

    def run_menu_item(self, item) -> None:
        if item.edit_part:
            self.edit_part(item.edit_part)
            return
        if item.find_entry:
            if self.history_panel.select_entry(item.find_entry):
                self.history_panel.setFocus()
            return
        if item.form:
            self.open_form(item.form, item.commands[0] if item.commands else "")
            return
        cmds = list(item.commands)
        if item.ask:
            text, ok = QInputDialog.getText(self, "3Dmodeling", item.ask)
            if not ok or not text.strip():
                return
            cmds = [c.replace("{}", text.strip()) for c in cmds]
        for c in cmds:
            if not self.execute(c).ok:
                break

    def open_form(self, name: str, text: str = "", edit_row: int | None = None, edit_line: int | None = None):
        """Open a command's fill-in form (see gui/forms.py); with edit_line, for one line inside an entry."""
        return fd.open_form(self, name, text, edit_row, edit_line)

    def form_for_typed(self) -> None:
        text = self.cmdline.text().strip()
        if not text:
            fd.find_command(self)
            return
        name = text.split(",")[0].strip().upper()
        if self.open_form(name, text) is not None:
            self.cmdline.clear()

    def run_feature(self, build) -> None:
        try:
            lines = build()
        except fa.NeedInput as exc:
            if str(exc):
                self.statusBar().showMessage(str(exc), 6000)
            return
        for line in lines:
            if not self.execute(line).ok:
                break

    # ---- running commands --------------------------------------------------
    def execute(self, text: str) -> Result:
        """The single entry point for GUI actions, clicks and typed text."""
        self.cmdline.remember(text)
        try:
            if "\n" in text and not text.upper().startswith("HIST"):
                results = self.processor.run_script(text)
                return results[-1] if results else Result("", True)
            return self.processor.run(text)
        finally:
            self.rebuild_progress.finish()

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
        self.undo_action.setEnabled(p.can_undo)
        self.redo_action.setEnabled(p.can_redo)

    def _save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save command log", "session.cmd", "Command scripts (*.cmd)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.processor.script(standalone=True))
            self.statusBar().showMessage(f"Saved {self.processor.cursor} history entries to {path}", 5000)

    def _open_project(self) -> None:
        self.shell.open()

    def _save_project(self) -> None:
        self.shell.save()

    def _import_file(self) -> None:
        self.shell.import_file()

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
        self.shell.run_script()
