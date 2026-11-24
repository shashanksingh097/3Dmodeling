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

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..lang.script import ScriptError, split_args
from .forms import replace_code_line as _replace_code_line
from . import forms as F

if TYPE_CHECKING:
    from .main_window import MainWindow

_BAD = "border: 1px solid #c62828;"
PREVIEW_SETTING = "forms/preview3d"  # Show in 3D on the fill-in forms (on unless turned off)
PREVIEW_DELAY_MS = 300  # wait this long after the last key before working out the preview


def _setting(win, key: str, default: bool) -> bool:
    shell = getattr(win, "shell", None)
    if shell is None:
        return default
    v = shell.settings.value(key, default)
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")


def _set_setting(win, key: str, value: bool) -> None:
    shell = getattr(win, "shell", None)
    if shell is not None:
        shell.settings.setValue(key, value)


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
        self.values: dict[str, QLineEdit] = {}  # params: one box per part parameter
        self.values_form: QFormLayout | None = None
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
        elif f.kind == "part":
            self.combo = QComboBox()
            self.combo.addItems(F.options(p, f))
            self.combo.currentTextChanged.connect(dlg.part_changed)
            lay.addWidget(self.combo, 1)
        elif f.kind == "params":
            box = QWidget()
            self.values_form = QFormLayout(box)
            self.values_form.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(box, 1)
        elif f.kind in ("body", "datum", "sketch", "layer"):
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

    def show_part(self, name: str) -> None:
        """params: one box per parameter of this part, its default shown greyed."""
        assert self.values_form is not None
        while self.values_form.rowCount():
            self.values_form.removeRow(0)
        self.values = {}
        params = F.part_params(self.dlg.win.processor, name)
        for pname, default in params:
            e = QLineEdit()
            e.setPlaceholderText(default or "(needed)")
            e.textChanged.connect(self.dlg.update_preview)
            self.values[pname] = e
            self.values_form.addRow(pname, e)
        if not params:
            self.values_form.addRow(QLabel("this part has no parameters" if name else "no part chosen"))
        self.values_form.parentWidget().updateGeometry()
        self.updateGeometry()

    def value(self) -> str:
        if self.f.kind == "params":
            return ", ".join(f"{k}={e.text().strip()}" for k, e in self.values.items() if e.text().strip())
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
        if self.f.kind == "params":
            for e in self.values.values():
                e.setText("")
            try:
                items = split_args(v) if v.strip() else []
            except ScriptError:
                items = []
            for item in items:
                k, _eq, val = item.partition("=")
                if k.strip().upper() in self.values:
                    self.values[k.strip().upper()].setText(val.strip())
            return
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
        targets = self.parts or list(self.values.values()) or [
            w for w in (self.combo, self.line, self.box) if w is not None]
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
        save = self.dlg.spec.command in ("EXPORT", "DRAWING")
        filt = "All files (*)"
        if save:
            first = "drawing.dxf" if self.dlg.spec.command == "DRAWING" else "part.step"
            path, _ = QFileDialog.getSaveFileName(self, "Export to", first, filt)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Choose a file", "", filt)
        if path:
            self.set_value(path)


class FormDialog(QDialog):
    def __init__(self, win: "MainWindow", spec: F.FormSpec, variant: str = "",
                 values: dict[str, str] | None = None, edit_row: int | None = None,
                 edit_line: int | None = None) -> None:
        super().__init__(win)
        self.win, self.spec = win, spec
        self.edit_row = edit_row  # 0-based history row being edited, or None
        self.edit_line = edit_line  # with edit_row: the line inside that entry (a *PART or loop), or None
        where = "" if edit_row is None else f" (history entry {edit_row + 1}" + (
            f", line {edit_line + 1})" if edit_line is not None else ")")
        self.setWindowTitle(f"{spec.title}{where}")
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMinimumWidth(520)
        self.fields: dict[str, _FieldWidget] = {}
        self._hidden: list[_FieldWidget] = []
        self._filling = False

        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetMinimumSize)  # grows when a part with more values is chosen
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

        # PLAN item 83: what the step would make, drawn see-through in the 3D view
        prow = QHBoxLayout()
        self.preview_box = QCheckBox("Show in 3D")
        self.preview_box.setToolTip("Draw what this step would make, see-through, before you press OK "
                                    "(worked out on a copy of the model; nothing is added until OK)")
        self.preview_box.setChecked(_setting(win, PREVIEW_SETTING, True))
        self.preview_box.toggled.connect(self._preview_toggled)
        prow.addWidget(self.preview_box)
        prow.addStretch(1)
        self.effect = QLabel()
        self.effect.setObjectName("form_effect")
        self.effect.setWordWrap(True)
        self.effect.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.update_button = QPushButton("Update preview")
        self.update_button.setToolTip("This step is slow to work out, so the preview waits for this button")
        self.update_button.clicked.connect(self.preview_now)
        self.update_button.setVisible(False)
        prow.addWidget(self.update_button)
        lay.addLayout(prow)
        lay.addWidget(self.effect)  # its own full-width row: a reason can be long
        self._manual = False  # True once a preview took longer than SLOW seconds
        self._last_preview = None  # the last preview_handlers.Preview
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(PREVIEW_DELAY_MS)
        self._preview_timer.timeout.connect(self.preview_now)
        # a new pick while the form is open (FILLET on other edges, say) changes what it would make
        self._listener = self._on_result
        win.processor.listeners.append(self._listener)

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
        self._filling = True
        for f in v.fields:
            w = _FieldWidget(self, f)
            self.fields[f.key] = w
            if f.kind == "params":
                w.show_part(vals.get("part", ""))
            w.set_value(vals.get(f.key, ""))
            label = "" if f.kind == "flag" else (f.label + ("" if f.required else " (optional)") if f.label else "")
            if f.kind == "choice" and len(f.choices) == 1:
                w.setParent(self.body)
                w.setVisible(False)  # a fixed word of this variant
                self._hidden.append(w)
                continue
            self.form.addRow(label, w)
        self._filling = False
        self.variant_help.setText(v.help)
        self.variant_help.setVisible(bool(v.help))
        self.update_preview()

    def part_changed(self, name: str) -> None:
        """INST: a different part has other parameters."""
        if self._filling:
            return
        for w in self.fields.values():
            if w.f.kind == "params":
                w.show_part(name)
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
        if self._filling:
            return
        text, problems = F.check(self.win.processor, self.spec, self.values(), self.variant)
        if self.edit_line is not None:
            # a line inside a *PART or loop uses its own names (D, B, i) and the
            # part's own bodies: they cannot be checked here; the rebuild checks them
            problems = {k: m for k, m in problems.items() if k == ""}
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
        self._schedule_preview(text if (text and ok) else "")

    # ---- the 3D preview (PLAN item 83) -----------------------------------------------
    def _schedule_preview(self, text: str) -> None:
        if not hasattr(self, "preview_box"):
            return
        self._pending_text = text
        if not text or not self.preview_box.isChecked():
            self._preview_timer.stop()
            self.clear_3d_preview()
            if not text:
                self.effect.setText("")
            return
        if self._manual:
            self.effect.setText("Changed: press Update preview to see it")
            self.effect.setStyleSheet("color: #555;")
            return
        self._preview_timer.start()

    def _step_text(self, text: str) -> str:
        """The text the preview runs: the new entry when this form edits one."""
        if self.edit_row is None:
            return text
        old = self.win.processor.history[self.edit_row].text
        return F.replace_line(old, self.edit_line, text) if self.edit_line is not None else _replace_code_line(old, text)

    def preview_now(self):
        """Work out the step on a copy and show it; returns the Preview (or None)."""
        from ..commands import preview_handlers as ph

        self._preview_timer.stop()
        text = getattr(self, "_pending_text", "")
        if not text or not self.preview_box.isChecked():
            self.clear_3d_preview()
            return None
        p = self.win.processor
        try:
            pv = ph.preview_step(p, self._step_text(text), self.edit_row)
        except Exception as exc:  # noqa: BLE001 - a preview must never break the form
            self.clear_3d_preview()
            self.effect.setText(f"No preview: {exc}")
            self.effect.setStyleSheet("color: #555;")
            return None
        self._last_preview = pv
        ph.show(p, pv)
        if pv.seconds > ph.SLOW and not self._manual:
            self._manual = True
            self.update_button.setVisible(True)
        note = f"  ({pv.seconds:.1f} s: the preview now waits for Update preview)" if self._manual else ""
        self.effect.setText(pv.text() + note)
        colour = "#555" if pv.skipped else ("#2e7d32" if pv.ok else "#c62828")
        self.effect.setStyleSheet(f"color: {colour};")
        self._fit()
        return pv

    def _fit(self) -> None:
        """Grow (never shrink) to show a long reason in full."""
        want = self.sizeHint()
        if want.height() > self.height() or want.width() > self.width():
            self.resize(max(want.width(), self.width()), max(want.height(), self.height()))

    def clear_3d_preview(self) -> None:
        from ..commands import preview_handlers as ph

        self._last_preview = None
        ph.show(self.win.processor, None)

    def _preview_toggled(self, on: bool) -> None:
        _set_setting(self.win, PREVIEW_SETTING, on)
        if on:
            self.update_preview()
        else:
            self._preview_timer.stop()
            self.clear_3d_preview()
            self.effect.setText("")

    def _on_result(self, res) -> None:
        if not res.ok or not res.line or not self.preview_box.isChecked():
            return
        word = res.line.split(",", 1)[0].strip().upper()
        if word in ("PICK", "SEL", "CMSEL") and getattr(self, "_pending_text", ""):
            self._schedule_preview(self._pending_text)

    def _unlisten(self) -> None:
        try:
            self.win.processor.listeners.remove(self._listener)
        except (ValueError, AttributeError):
            pass

    def done(self, r: int) -> None:  # OK, Cancel, Esc and the close button all end here
        self._unlisten()
        self._preview_timer.stop()
        self.clear_3d_preview()
        super().done(r)

    def closeEvent(self, e) -> None:
        self._unlisten()
        self._preview_timer.stop()
        self.clear_3d_preview()
        super().closeEvent(e)

    def show_error(self, msg: str) -> None:
        self.error.setText(msg)

    def submit(self, close: bool) -> bool:
        self._preview_timer.stop()
        self.clear_3d_preview()  # the real step replaces the ghost
        try:
            text = self.command_text()
        except F.FormError as exc:
            self.show_error(str(exc))
            return False
        if self.edit_row is not None:
            old = self.win.processor.history[self.edit_row].text
            new = (F.replace_line(old, self.edit_line, text) if self.edit_line is not None
                   else _replace_code_line(old, text))
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


def open_form(win: "MainWindow", name: str, text: str = "", edit_row: int | None = None,
              edit_line: int | None = None) -> FormDialog | None:
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
    dlg = FormDialog(win, sp, variant, values, edit_row, edit_line)
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
