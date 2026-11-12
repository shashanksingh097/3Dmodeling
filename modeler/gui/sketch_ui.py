"""Sketch mode in the window: the Sketch toolbar, and the forms for new
sketches, EXTRUDE, REVOLVE and sketch sizes.

Every button and form only builds command text and runs it through the
main window, the same way as typing it (see sketch_tools.py for the mouse).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
)

from ..lang.expr import fmt_num
from . import feature_actions as fa
from . import sketch_tools as st

_TOOL_LABELS = {"SELECT": "Select", "LINE": "Line", "RECT": "Rectangle", "CIRCLE": "Circle", "ARC": "Arc",
                "SLOT": "Slot", "POINT": "Point", "TRIM": "Trim", "EXTEND": "Extend", "FILLET": "Fillet"}
_TOOL_KEYS = {"SELECT": "S", "LINE": "L", "RECT": "R", "CIRCLE": "C", "ARC": "A", "SLOT": "", "POINT": "P",
              "TRIM": "T", "EXTEND": "E", "FILLET": "F"}
_CONSTRAINTS = [
    ("Coincident", "COINCIDENT", "Join two points, or put a point on a curve\nRuns: SCON, COINCIDENT/ON, ..."),
    ("Horizontal", "HORIZONTAL", "Make lines level (or two points level with each other)\nRuns: SCON, HORIZONTAL, ..."),
    ("Vertical", "VERTICAL", "Make lines upright\nRuns: SCON, VERTICAL, ..."),
    ("Parallel", "PARALLEL", "Runs: SCON, PARALLEL, a, b"),
    ("Perpendicular", "PERPENDICULAR", "Runs: SCON, PERPENDICULAR, a, b"),
    ("Tangent", "TANGENT", "A line and an arc/circle, or two arcs/circles, touching smoothly\nRuns: SCON, TANGENT, a, b"),
    ("Equal", "EQUAL", "Same length (lines) or same radius (arcs, circles)\nRuns: SCON, EQUAL, a, b"),
    ("Midpoint", "MIDPOINT", "A point at the middle of a line\nRuns: SCON, MIDPOINT, p, line"),
    ("Symmetric", "SYMMETRIC", "Two points mirrored about a line\nRuns: SCON, SYMMETRIC, p, q, line"),
    ("Concentric", "CONCENTRIC", "Runs: SCON, CONCENTRIC, a, b"),
    ("Fix", "FIX", "Pin points or geometry where they are\nRuns: SCON, FIX, ..."),
]


class SketchUI:
    def __init__(self, win) -> None:
        self.win = win
        self.p = win.processor
        self.controller = st.SketchController(self.p)
        win.viewport.sketcher = self.controller
        win.viewport.edit_dimension.connect(self.edit_dimension)
        win.viewport.sketch_hover.connect(self._hover)
        self.toolbar = self._build_toolbar()
        self.toolbar.setVisible(False)
        self.p.model.subscribe(self._on_model)

    # ---- toolbar ----------------------------------------------------------
    def _build_toolbar(self) -> QToolBar:
        win = self.win
        win.addToolBarBreak()
        tb = QToolBar("Sketch", win)
        tb.setObjectName("sketch")
        win.addToolBar(tb)
        group = QActionGroup(win)
        group.setExclusive(True)
        self.tool_actions: dict[str, QAction] = {}
        for tool in st.TOOLS:
            if tool == "TRIM":
                tb.addSeparator()
            a = QAction(_TOOL_LABELS[tool], win)
            a.setCheckable(True)
            a.setToolTip(st.HINTS[tool] + (f"\nKey: {_TOOL_KEYS[tool]}" if _TOOL_KEYS[tool] else ""))
            if _TOOL_KEYS[tool]:
                a.setShortcut(QKeySequence(_TOOL_KEYS[tool]))
            a.triggered.connect(lambda _=False, t=tool: self.set_tool(t))
            group.addAction(a)
            tb.addAction(a)
            self.tool_actions[tool] = a
        self.tool_actions["SELECT"].setChecked(True)
        self.edit_actions: dict[str, QAction] = {}
        for label, slot, tip in (
                ("Offset…", self.offset, "Offset the selected curves (a chain is offset as one)\nRuns: SOFFSET, d, ..."),
                ("Mirror…", self.mirror, "Mirror the selected geometry about a line (select it too) or H / V\n"
                                         "Runs: SMIRROR, axis, ..."),
                ("Pattern…", self.pattern, "Copies of the selected geometry in a row or round a point\n"
                                           "Runs: SPATTERN, LINEAR/POLAR, ..."),
                ("Project…", self.project, "Bring body edges into the sketch (the edges or faces picked before "
                                           "the sketch, or IDs)\nRuns: SPROJECT, ...")):
            a = QAction(label, win)
            a.setToolTip(tip)
            a.triggered.connect(slot)
            tb.addAction(a)
            self.edit_actions[label.rstrip("…")] = a
        tb.addSeparator()
        for label, kind, tip in _CONSTRAINTS:
            a = QAction(label, win)
            a.setToolTip(tip)
            a.triggered.connect(lambda _=False, k=kind: self.run(lambda: st.constraint_command(self.p, k)))
            tb.addAction(a)
        tb.addSeparator()
        for label, which, tip in (
                ("Size…", "AUTO", "Length of a line, diameter of a circle, radius of an arc, distance between two "
                                   "points or from a point to a line, angle between two lines\nRuns: SDIM, ..."),
                ("Across…", "HDIST", "Horizontal distance between two points (or a point and the origin)\nRuns: SDIM, HDIST, ..."),
                ("Up…", "VDIST", "Vertical distance between two points (or a point and the origin)\nRuns: SDIM, VDIST, ...")):
            a = QAction(label, win)
            a.setToolTip(tip)
            a.triggered.connect(lambda _=False, w=which: self.add_dimension(w))
            tb.addAction(a)
        tb.addSeparator()
        a = QAction("Construction", win)
        a.setToolTip("Make the selected curves construction geometry (or back)\nRuns: SCONSTRUCT, n, ON/OFF")
        a.triggered.connect(lambda: self.run(lambda: st.construction_command(self.p)))
        tb.addAction(a)
        a = QAction("Delete", win)
        a.setToolTip("Delete the selected geometry or sizes\nRuns: SDEL, ...")
        a.setShortcut(QKeySequence.Delete)
        a.triggered.connect(lambda: self.run(lambda: st.delete_command(self.p)))
        tb.addAction(a)
        tb.addSeparator()
        a = QAction("Finish sketch", win)
        a.setToolTip("Leave sketch mode\nRuns: ENDSKETCH")
        a.triggered.connect(lambda: self.win.execute("ENDSKETCH"))
        tb.addAction(a)
        a = QAction("Extrude…", win)
        a.setToolTip("Finish and extrude this sketch\nRuns: EXTRUDE, sketch, d [, mode, body]")
        a.triggered.connect(self.extrude)
        tb.addAction(a)
        return tb

    def set_tool(self, tool: str) -> None:
        self.controller.set_tool(tool)
        self.tool_actions[tool].setChecked(True)
        self.win.viewport.set_preview(None)
        self.win.statusBar().showMessage(st.HINTS[tool])

    def run(self, build) -> None:
        try:
            lines = build()
        except st.NeedSelection as exc:
            self.win.statusBar().showMessage(str(exc), 6000)
            return
        for line in lines:
            if not self.win.execute(line).ok:
                break

    def _on_model(self, ev) -> None:
        if ev.kind in ("sketch", "restored", "cleared"):
            on = bool(self.p.model.active_sketch)
            sk = self.controller.sketch
            if sk is not None:
                self.win.statusBar().showMessage(f"{sk.status()}    ·    {st.HINTS[self.controller.tool]}")
            if on != self.toolbar.isVisible():
                self.toolbar.setVisible(on)
                if on:
                    self.set_tool("SELECT")
                else:
                    self.controller.reset()
                    self.win.statusBar().showMessage("Sketch closed: Extrude… or Revolve… makes a solid from it", 6000)

    def _hover(self, text: str) -> None:
        sk = self.controller.sketch
        if sk is not None:
            self.win.statusBar().showMessage(f"{text}    ·    {sk.status()}    ·    {st.HINTS[self.controller.tool]}")

    # ---- offset, mirror, pattern, project -----------------------------------------
    def _ask(self, title: str, label: str, text: str = "") -> str | None:
        got, ok = QInputDialog.getText(self.win, title, label, QLineEdit.Normal, text)
        return got.strip() if ok and got.strip() else None

    def offset(self) -> None:
        try:
            st.offset_command(self.p, "1")
        except st.NeedSelection as exc:
            self.win.statusBar().showMessage(str(exc), 6000)
            return
        d = self._ask("Offset", "Distance (positive: outwards for a closed chain or a circle):", "2")
        if d:
            self.run(lambda: st.offset_command(self.p, d))

    def mirror(self) -> None:
        axes = st.mirror_axes(self.p)
        axis, ok = QInputDialog.getItem(self.win, "Mirror", "Mirror about (a selected line, or the axes):", axes, 0, False)
        if ok:
            self.run(lambda: st.mirror_command(self.p, axis))

    def pattern(self) -> None:
        kind, ok = QInputDialog.getItem(self.win, "Pattern", "Copies:", ["In a row (LINEAR)", "Round a point (POLAR)"],
                                        0, False)
        if not ok:
            return
        if "LINEAR" in kind:
            vals = self._ask("Pattern in a row", "How many in all, then the step u, v:", "3, 10, 0")
            if vals:
                self.run(lambda: st.pattern_command(self.p, "LINEAR", vals))
        else:
            vals = self._ask("Pattern round a point", "How many in all, the angle (360: a full ring), the centre "
                             "(a point like O or 3.C, or u, v):", "6, 360, O")
            if vals:
                self.run(lambda: st.pattern_command(self.p, "POLAR", vals))

    def project(self) -> None:
        ids = self._ask("Project edges", "Edge IDs (or FACE, then face IDs; pick them before opening the sketch, "
                        "or type them):", st.project_default(self.p))
        if ids:
            self.win.execute(f"SPROJECT, {ids}")

    # ---- sizes --------------------------------------------------------------
    def add_dimension(self, which: str) -> None:
        try:
            kind, names, now = st.dimension_for(self.p, which)
        except st.NeedSelection as exc:
            self.win.statusBar().showMessage(str(exc), 6000)
            return
        what = {"LENGTH": "Length", "DIAMETER": "Diameter", "RADIUS": "Radius", "DIST": "Distance",
                "ANGLE": "Angle (degrees)", "HDIST": "Horizontal distance", "VDIST": "Vertical distance"}[kind]
        text, ok = QInputDialog.getText(self.win, "Size", f"{what} of {', '.join(names)} (a number, or an "
                                        "expression with parameters):", QLineEdit.Normal, fmt_num(round(now, 4) + 0.0))
        if ok and text.strip():
            self.win.execute(st.dimension_command(kind, names, text))

    def edit_dimension(self, label: str) -> None:
        sk = self.controller.sketch
        if sk is None:
            return
        c = sk.cons.get(int(label[1:]))
        if c is None:
            return
        rows = {r[0]: r for r in st.sketch_dimensions(self.p, sk.name)}
        now = rows[label][3] if label in rows else fmt_num(c.value)
        text, ok = QInputDialog.getText(self.win, "Change size", f"{c.kind.title()} {', '.join(c.refs)}:",
                                        QLineEdit.Normal, now)
        if ok and text.strip() and text.strip() != now:
            line = st.edit_dimension_entry(self.p, label, text)
            if line:
                self.win.execute(line)

    # ---- features toolbar: sketch, extrude, revolve ------------------------------
    def new_sketch(self) -> None:
        p = self.p
        if p.model.active_sketch:
            self.win.statusBar().showMessage("A sketch is open: finish it first", 5000)
            return
        name = fa.free_name(p, "S")
        m = p.model
        if m.selection_kind == "FACE" and len(m.selection) == 1:
            from ..geometry.features import face_plane

            gid = m.selection[0]
            if face_plane(m.entity_shape("FACE", gid)) is not None:
                self.win.execute(f"SKETCH, {name}, FACE, {gid}")
                return
        planes = ["XY", "YZ", "ZX"] + [d.name for d in m.datums.values() if d.kind == "PLANE"]
        if m.workplane is not None and m.workplane.name not in planes:
            planes.insert(0, m.workplane.name)
        plane, ok = QInputDialog.getItem(self.win, "New sketch", "Sketch on (or pick a flat face first):", planes, 0, False)
        if ok:
            self.win.execute(f"SKETCH, {name}, {plane}")

    def _sketch_names(self) -> list[str]:
        m = self.p.model
        names = [s.name for s in m.sketches.values() if not s.used_by]
        if m.active_sketch:
            act = m.sketches[m.active_sketch].name
            names = [act] + [n for n in names if n != act]
        return names or [s.name for s in m.sketches.values()][::-1]

    def extrude(self) -> None:
        names = self._sketch_names()
        if not names:
            self.win.statusBar().showMessage("Extrude: make a sketch first (Sketch button)", 5000)
            return
        dlg = FeatureForm(self.win, "Extrude", self.p, names, revolve=False)
        if dlg.exec() == QDialog.Accepted:
            self.win.execute(dlg.command())

    def revolve(self) -> None:
        names = self._sketch_names()
        if not names:
            self.win.statusBar().showMessage("Revolve: make a sketch first (Sketch button)", 5000)
            return
        dlg = FeatureForm(self.win, "Revolve", self.p, names, revolve=True)
        if dlg.exec() == QDialog.Accepted:
            self.win.execute(dlg.command())

    def edit_sizes(self, name: str) -> None:
        rows = st.sketch_dimensions(self.p, name)
        if not rows:
            self.win.statusBar().showMessage(f"Sketch {name} has no sizes yet", 5000)
            return
        dlg = SizesForm(self.win, name, rows)
        if dlg.exec() != QDialog.Accepted:
            return
        for (label, _what, n, old), new in zip(rows, dlg.values()):
            if new.strip() and new.strip() != old:
                line = st.dimension_edit(self.p, self._uid_of(n), new)
                if line and not self.win.execute(line).ok:
                    break

    def _uid_of(self, n: int) -> int:
        return self.p.history[n - 1].uid


class FeatureForm(QDialog):
    """EXTRUDE or REVOLVE: pick the sketch, the size, and new body / add / cut."""

    def __init__(self, parent, title: str, p, sketches: list[str], revolve: bool) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.p, self.revolve = p, revolve
        form = QFormLayout()
        self.sketch = QComboBox()
        self.sketch.addItems(sketches)
        form.addRow("Sketch:", self.sketch)
        if revolve:
            self.axis = QComboBox()
            self.axis.setEditable(True)
            form.addRow("Axis:", self.axis)
            self.size = QLineEdit("360")
            form.addRow("Angle (degrees):", self.size)
            self.sketch.currentTextChanged.connect(self._axes)
            self._axes(self.sketch.currentText())
        else:
            self.size = QLineEdit("10")
            form.addRow("Distance (negative: other way):", self.size)
            self.back = QLineEdit("0")
            form.addRow("Also the other way:", self.back)
        self.mode = QComboBox()
        self.mode.addItems(["New body", "Add to body", "Cut from body"])
        form.addRow("Result:", self.mode)
        self.body = QComboBox()
        bodies = [b for b in p.model.bodies.values() if b.id not in p.model.hidden and b.entity_ids["FACE"]]
        self.body.addItems([b.name if not b.name.startswith("body") else str(b.id) for b in bodies][::-1])
        form.addRow("Body:", self.body)
        self.mode.currentIndexChanged.connect(lambda i: self.body.setEnabled(i > 0))
        self.body.setEnabled(False)
        sk = p.model.sketches.get(sketches[0].upper()) if sketches else None
        if sk is not None and sk.base_body and sk.base_body in p.model.bodies:
            self.mode.setCurrentIndex(1)
            b = p.model.bodies[sk.base_body]
            self.body.setCurrentText(b.name if not b.name.startswith("body") else str(b.id))
        self.preview = QLineEdit()
        self.preview.setReadOnly(True)
        form.addRow("Runs:", self.preview)
        for w in (self.size, self.mode, self.body, self.sketch) + ((self.axis,) if revolve else (self.back,)):
            sig = getattr(w, "textChanged", None) or getattr(w, "currentTextChanged")
            sig.connect(lambda *_: self.preview.setText(self.command()))
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.resize(460, 0)
        self.preview.setText(self.command())

    def _axes(self, name: str) -> None:
        self.axis.clear()
        items = ["V", "H"]
        sk = self.p.model.sketches.get(name.upper())
        if sk is not None:
            lines = [g for g in sk.geos.values() if g.kind == "LINE"]
            lines.sort(key=lambda g: not g.construction)
            items = [str(g.n) for g in lines if g.construction] + items + [str(g.n) for g in lines if not g.construction]
        items += [d.name for d in self.p.model.datums.values() if d.kind == "AXIS"] + ["X", "Y", "Z"]
        self.axis.addItems(items)

    def command(self) -> str:
        mode = ["NEW", "ADD", "CUT"][self.mode.currentIndex()]
        body = self.body.currentText() if mode != "NEW" else ""
        size = self.size.text().strip() or ("360" if self.revolve else "10")
        if self.revolve:
            parts = ["REVOLVE", self.sketch.currentText(), self.axis.currentText().strip() or "V", size]
            if mode != "NEW":
                parts += [mode, body]
            return ", ".join(parts)
        parts = ["EXTRUDE", self.sketch.currentText(), size]
        back = self.back.text().strip()
        if mode != "NEW" or (back and back != "0"):
            parts += [mode, body]
        if back and back != "0":
            parts.append(back)
        return ", ".join(parts)


class SizesForm(QDialog):
    """Every size of a sketch in a table; changed ones are written back with HIST, EDIT."""

    def __init__(self, parent, name: str, rows) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Sizes of sketch {name}")
        self.table = QTableWidget(len(rows), 3)
        self.table.setHorizontalHeaderLabels(["", "Measures", "Size"])
        for i, (label, what, n, value) in enumerate(rows):
            for c, text in enumerate((label, what, value)):
                item = QTableWidgetItem(text)
                if c < 2:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setToolTip(f"history entry {n}")
                self.table.setItem(i, c, item)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        lay = QVBoxLayout(self)
        lay.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.resize(460, 320)

    def values(self) -> list[str]:
        return [self.table.item(i, 2).text() for i in range(self.table.rowCount())]
