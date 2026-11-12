"""The fill-in form for one command, drawn from ``gui/forms.py``.

The dialog shows a field per argument, the command text it will send (kept
up to date as you type), and what is wrong before you press Run. Run and OK
send that text through ``MainWindow.execute``, exactly as if it were typed;
when the form edits a history entry, OK sends ``HIST, EDIT`` instead.
The dialog does not block the window, so you can pick faces and bodies in
the 3D view while it is open and press "← Selection" to use them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..lang.script import ScriptError, split_args, strip_comment
from . import forms as F

if TYPE_CHECKING:
    from .main_window import MainWindow

_BAD = "border: 1px solid #c62828;"


def _mono() -> QFont:
    f = QFont("Monospace")
    f.setStyleHint(QFont.TypeWriter)
    return f


class _FieldWidget(QWidget):
    """One field: an editor, plus a "← Selection" or "…" button where it helps."""

    def __init__(self, dlg: "FormDialog", f: F.Field) -> None:
        super().__init__()
        self.dlg, self.f = dlg, f
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        p = dlg.win.processor
        self.parts: list[QLineEdit] = []
        self.combo: QComboBox | None = None
        self.check: QCheckBox | None = None
        self.box: QPlainTextEdit | None = None
        self.line: QLineEdit | None = None
        tip = f.help or ""
        if f.kind in ("flag", "bool"):
            self.check = QCheckBox(f.label if f.kind == "flag" else "")
            self.check.toggled.connect(dlg.update_preview)
            lay.addWidget(self.check)
        elif f.kind == "choice":
            self.combo = QComboBox()
            items = list(f.choices)
            if not f.required and f.default not in items:
                items = [""] + items
            self.combo.addItems(items)
            self.combo.currentTextChanged.connect(dlg.update_preview)
            lay.addWidget(self.combo, 1)
        elif f.kind in ("body", "datum", "sketch"):
            self.combo = QComboBox()
            self.combo.setEditable(True)
            opts = F.options(p, f, dlg.spec.command)
            if f.choices:
                opts = list(dict.fromkeys(opts + list(f.choices)))
            self.combo.addItems(([""] if not f.required else []) + opts)
            self.combo.setEditText("")
            self.combo.currentTextChanged.connect(dlg.update_preview)
            lay.addWidget(self.combo, 1)
        elif f.kind == "point":
            for axis in ("x", "y", "z"):
                e = QLineEdit()
                e.setPlaceholderText(axis)
                e.textChanged.connect(dlg.update_preview)
                self.parts.append(e)
                lay.addWidget(e, 1)
            d = f.defaults()
            if any(d):
                for e, v in zip(self.parts, d):
                    e.setPlaceholderText(v)
        elif f.kind == "points":
            self.box = QPlainTextEdit()
            self.box.setFont(_mono())
            self.box.setPlaceholderText("0, 0, 0\n10, 0, 0\n10, 10, 5")
            self.box.setFixedHeight(96)
            self.box.textChanged.connect(dlg.update_preview)
            lay.addWidget(self.box, 1)
        else:
            self.line = QLineEdit()
            if f.default:
                self.line.setPlaceholderText(f.default)
            elif f.kind in ("bodies", "ids"):
                self.line.setPlaceholderText("pick, then press ← Selection" if f.pick else "")
            self.line.textChanged.connect(dlg.update_preview)
            lay.addWidget(self.line, 1)
        if f.kind in ("body", "bodies", "ids", "point", "points"):
            b = QPushButton("← Selection")
            b.setToolTip("Use what is picked in the 3D view")
            b.clicked.connect(self.use_selection)
            lay.addWidget(b)
        if f.kind == "path":
            b = QPushButton("…")
            b.setFixedWidth(32)
            b.clicked.connect(self.browse)
            lay.addWidget(b)
        if tip:
            self.setToolTip(tip)

    def value(self) -> str:
        if self.check is not None:
            if self.f.kind == "flag":
                return "1" if self.check.isChecked() else ""
            return "1" if self.check.isChecked() else "0"
        if self.combo is not None:
            return self.combo.currentText().strip()
        if self.parts:
            vals = [e.text().strip() for e in self.parts]
            if not any(vals):
                return ""
            if vals[0] and not any(vals[1:]) and (vals[0].startswith("(") or "," in vals[0]):
                return vals[0]
            d = self.f.defaults()
            return ", ".join(v or d[i] or "0" for i, v in enumerate(vals))
        if self.box is not None:
            return self.box.toPlainText()
        return self.line.text().strip() if self.line else ""

    def set_value(self, v: str) -> None:
        v = v or ""
        if self.check is not None:
            self.check.setChecked(v.lower() in ("1", "true", "yes", "on"))
        elif self.combo is not None:
            if self.combo.isEditable():
                self.combo.setEditText(v)
            else:
                i = self.combo.findText(v, Qt.MatchFixedString)
                self.combo.setCurrentIndex(max(i, 0))
        elif self.parts:
            raw = v[1:-1] if v.startswith("(") and v.endswith(")") else v
            try:
                bits = split_args(raw) if raw else []
            except ScriptError:
                bits = [v]
            if len(bits) != 3:
                bits = [v, "", ""] if v else ["", "", ""]
            for e, b in zip(self.parts, bits):
                e.setText(b)
        elif self.box is not None:
            self.box.setPlainText(v)
        elif self.line is not None:
            self.line.setText(v)

    def mark(self, problem: str) -> None:
        targets = self.parts or [w for w in (self.combo, self.line, self.box) if w is not None]
        for w in targets:
            w.setStyleSheet(_BAD if problem else "")
            w.setToolTip(problem or self.f.help)

    def use_selection(self) -> None:
        try:
            got = F.from_selection(self.dlg.win.processor, self.f)
        except F.FormError as exc:
            self.dlg.show_error(str(exc))
            return
        if self.f.kind == "body":
            got = got.split(",")[0].strip()
        self.set_value(got)

    def browse(self) -> None:
        save = self.dlg.spec.command == "EXPORT"
        filt = "All files (*)"
        if save:
            path, _ = QFileDialog.getSaveFileName(self, "Export to", "part.step", filt)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Choose a file", "", filt)
        if path:
            self.set_value(path)


class FormDialog(QDialog):
    def __init__(self, win: "MainWindow", spec: F.FormSpec, variant: str = "",
                 values: dict[str, str] | None = None, edit_row: int | None = None) -> None:
        super().__init__(win)
        self.win, self.spec = win, spec
        self.edit_row = edit_row  # 0-based history row being edited, or None
        self.setWindowTitle(f"{spec.title}" + (f" (history entry {edit_row + 1})" if edit_row is not None else ""))
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMinimumWidth(520)
        self.fields: dict[str, _FieldWidget] = {}
        self._hidden: list[_FieldWidget] = []

        lay = QVBoxLayout(self)
        about = QLabel(spec.help)
        about.setWordWrap(True)
        about.setStyleSheet("color: #555;")
        lay.addWidget(about)
        self.variant_box: QComboBox | None = None
        if len(spec.variants) > 1:
            row = QHBoxLayout()
            row.addWidget(QLabel("How:"))
            self.variant_box = QComboBox()
            for v in spec.variants:
                self.variant_box.addItem(v.label or v.key, v.key)
            row.addWidget(self.variant_box, 1)
            lay.addLayout(row)
        self.body = QWidget()
        self.form = QFormLayout(self.body)
        self.form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        lay.addWidget(self.body)
        self.variant_help = QLabel()
        self.variant_help.setWordWrap(True)
        lay.addWidget(self.variant_help)
        lay.addStretch(1)

        self.preview = QLabel()
        self.preview.setFont(_mono())
        self.preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet("background: #f3f5f8; color: #1a237e; padding: 6px; border-radius: 3px;")
        lay.addWidget(QLabel("Runs:"))
        lay.addWidget(self.preview)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #c62828;")
        lay.addWidget(self.error)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.run_button = QPushButton("Run")
        self.run_button.setToolTip("Run it and keep the form open for another")
        self.run_button.clicked.connect(lambda: self.submit(close=False))
        self.ok_button = QPushButton("OK")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(lambda: self.submit(close=True))
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        if edit_row is None:
            buttons.addWidget(self.run_button)
        else:
            self.ok_button.setText("Change step")
            self.ok_button.setToolTip("Change this history entry; the model re-runs from it")
        buttons.addWidget(self.ok_button)
        buttons.addWidget(cancel)
        lay.addLayout(buttons)

        self.variant = spec.variant(variant).key
        self._build(values)
        if self.variant_box is not None:
            self.variant_box.setCurrentIndex(max(0, self.variant_box.findData(self.variant)))
            self.variant_box.currentIndexChanged.connect(self._variant_changed)

    # ---- layout ----------------------------------------------------------------
    def _build(self, values: dict[str, str] | None) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        for w in self._hidden:  # the hidden fixed words are not rows
            w.deleteLater()
        self._hidden = []
        self.fields.clear()
        v = self.spec.variant(self.variant)
        vals = values if values is not None else F.initial(self.win.processor, self.spec, self.variant)
        for f in v.fields:
            w = _FieldWidget(self, f)
            self.fields[f.key] = w
            w.set_value(vals.get(f.key, ""))
            label = "" if f.kind == "flag" else (f.label + ("" if f.required else " (optional)") if f.label else "")
            if f.kind == "choice" and len(f.choices) == 1:
                w.setParent(self.body)
                w.setVisible(False)  # a fixed word of this variant
                self._hidden.append(w)
                continue
            self.form.addRow(label, w)
        self.variant_help.setText(v.help)
        self.variant_help.setVisible(bool(v.help))
        self.update_preview()

    def _variant_changed(self, i: int) -> None:
        self.variant = self.variant_box.itemData(i)
        self._build(None)

    # ---- values, preview, running ------------------------------------------------
    def values(self) -> dict[str, str]:
        return {k: w.value() for k, w in self.fields.items()}

    def command_text(self) -> str:
        return F.build(self.spec, self.values(), self.variant)

    def update_preview(self, *_) -> None:
        text, problems = F.check(self.win.processor, self.spec, self.values(), self.variant)
        for k, w in self.fields.items():
            w.mark(problems.get(k, ""))
        self.preview.setText(text or "…")
        labels = {f.key: f.label or f.key for f in self.spec.variant(self.variant).fields}
        msgs = [f"{labels.get(k, k)}: {m}" for k, m in problems.items() if k]
        if "" in problems:
            msgs.insert(0, problems[""])
        self.error.setText("\n".join(msgs))
        ok = "" not in problems and not [k for k in problems if k]
        self.ok_button.setEnabled(bool(text) and ok)
        self.run_button.setEnabled(bool(text) and ok)

    def show_error(self, msg: str) -> None:
        self.error.setText(msg)

    def submit(self, close: bool) -> bool:
        try:
            text = self.command_text()
        except F.FormError as exc:
            self.show_error(str(exc))
            return False
        if self.edit_row is not None:
            old = self.win.processor.history[self.edit_row].text
            new = _replace_code_line(old, text)
            from .main_window import hist_command

            res = self.win.execute(hist_command("EDIT", self.edit_row + 1, new))
        else:
            res = self.win.execute(text)
        if not res.ok:
            self.show_error(res.message or "the command failed")
            return False
        if close:
            self.accept()
        else:
            self._refresh_options()
            self.update_preview()
        return True

    def _refresh_options(self) -> None:
        """New bodies or datums appear in the lists after Run."""
        p = self.win.processor
        for w in self.fields.values():
            if w.combo is not None and w.combo.isEditable():
                cur = w.combo.currentText()
                w.combo.blockSignals(True)
                w.combo.clear()
                opts = F.options(p, w.f, self.spec.command)
                w.combo.addItems(([""] if not w.f.required else []) + opts)
                w.combo.setEditText(cur)
                w.combo.blockSignals(False)
        if "name" in self.fields and self.spec.command in ("PLANE", "AXIS", "POINT", "SKETCH", "CM"):
            fresh = F.initial(p, self.spec, self.variant).get("name", "")
            self.fields["name"].set_value(fresh)


def _replace_code_line(old: str, new: str) -> str:
    """Put a new command in place of an entry's command line, keeping its comments."""
    lines = old.splitlines()
    for i, raw in enumerate(lines):
        code = strip_comment(raw).strip()
        if code:
            comment = raw[len(strip_comment(raw)):].strip()
            lines[i] = new + (f"    {comment}" if comment else "")
            return "\n".join(lines)
    return new


def open_form(win: "MainWindow", name: str, text: str = "", edit_row: int | None = None) -> FormDialog | None:
    """Open the form for a command (filled from ``text`` if given). Returns
    None, with a note in the status bar, when there is no form for it."""
    try:
        if text.strip():
            sp, variant, values = F.parse(text)
        else:
            sp, variant, values = F.spec(name), "", None
    except F.FormError as exc:
        if edit_row is not None or not name:
            win.statusBar().showMessage(str(exc), 6000)
            return None
        try:  # the typed line does not fit the form: open it fresh
            sp, variant, values = F.spec(name), "", None
        except F.FormError as exc2:
            win.statusBar().showMessage(str(exc2), 6000)
            return None
    dlg = FormDialog(win, sp, variant, values, edit_row)
    dlg.show()
    dlg.raise_()
    return dlg


def command_menu(win: "MainWindow", menu) -> None:
    """Fill a menu with every form, under the same headings as forms.CATEGORIES."""
    by_cat: dict[str, list[F.FormSpec]] = {}
    for sp in F.specs().values():
        by_cat.setdefault(sp.category, []).append(sp)
    for cat, _names in F.CATEGORIES:
        sub = menu.addMenu(cat)
        sub.setToolTipsVisible(True)
        for sp in by_cat.get(cat, []):
            act = sub.addAction(f"{sp.title}…")
            act.setToolTip(sp.help.split(". ")[0])
            act.setStatusTip(sp.help.split(". ")[0])
            act.triggered.connect(lambda _=False, n=sp.command: open_form(win, n))


def find_command(win: "MainWindow") -> FormDialog | None:
    """Ask for a command by name or by what it does, then open its form."""
    from PySide6.QtWidgets import QInputDialog

    items = [f"{sp.command}  —  {sp.help.split('. ')[0]}" for sp in F.specs().values()]
    got, ok = QInputDialog.getItem(win, "Find a command", "Command (type to search):", items, 0, True)
    if not ok or not got.strip():
        return None
    word = got.split("—")[0].strip().split(",")[0].strip().upper()
    if word not in F.specs():  # typed words: the first command whose name or help mentions them
        low = got.strip().lower()
        hits = [sp.command for sp in F.specs().values() if low in sp.command.lower() or low in sp.help.lower()]
        if not hits:
            win.statusBar().showMessage(f"no command matches {got.strip()!r}", 6000)
            return None
        word = hits[0]
    return open_form(win, word)
