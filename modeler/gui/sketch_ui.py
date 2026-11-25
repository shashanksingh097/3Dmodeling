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
    QCheckBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
)

from ..lang.expr import fmt_num
from . import feature_actions as fa
from . import sketch_tools as st

_TOOL_LABELS = {"SELECT": "Select", "LINE": "Line", "CENTRELINE": "Centreline", "RECT": "Rectangle",
                "CRECT": "Centre rect", "RECT3": "Angled rect", "CIRCLE": "Circle",
                "CIRCLE3": "3-point circle", "ARC": "Arc", "TARC": "Tangent arc", "SLOT": "Slot", "ARCSLOT": "Arc slot",
                "POLYGON": "Polygon", "ELLIPSE": "Ellipse", "EARC": "Elliptical arc", "CIRCLET": "Tangent circle",
                "POINT": "Point", "FREEHAND": "Freehand", "TRIM": "Trim", "EXTEND": "Extend",
                "FILLET": "Fillet", "CHAMFER": "Chamfer", "SPLIT": "Split", "CORNER": "Corner"}
_TOOL_KEYS = {"SELECT": "S", "LINE": "L", "RECT": "R", "CIRCLE": "C", "ARC": "A", "POINT": "P", "FREEHAND": "D",
              "TRIM": "T", "EXTEND": "E", "FILLET": "F", "CHAMFER": "K", "SPLIT": "B", "CORNER": "O",
              "POLYGON": "G", "TARC": "N", "ELLIPSE": "I"}
_TOOL_RUNS = {"SELECT": "SSEL / SMOVE", "LINE": "SLINE", "CENTRELINE": "SLINE, ..., CONSTR", "RECT": "SRECT",
              "CRECT": "SRECTC", "RECT3": "SRECT3", "CIRCLE": "SCIRCLE", "CIRCLE3": "SCIRCLE3", "ARC": "SARC3",
              "TARC": "SARCT", "SLOT": "SSLOT", "ARCSLOT": "SSLOTARC", "POLYGON": "SNGON", "ELLIPSE": "SELLIPSE", "EARC": "SEARC", "CIRCLET": "SCIRCLET", "POINT": "SPOINT",
              "FREEHAND": "SSPLINE", "TRIM": "STRIM", "EXTEND": "SEXTEND", "FILLET": "SFILLET", "CHAMFER": "SCHAMFER",
              "SPLIT": "SSPLIT", "CORNER": "SCORNER"}
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
        self._show_bars(False)
        self.p.model.subscribe(self._on_model)

    # ---- toolbars ---------------------------------------------------------
    def _build_toolbar(self) -> QToolBar:
        """Sketch draw, Sketch edit, Constraints and Sizes: shown while a
        sketch is open. Returns the first; all four are in self.toolbars."""
        from . import toolbars as tbs

        win = self.win
        group = QActionGroup(win)
        group.setExclusive(True)
        self.tool_actions: dict[str, QAction] = {}
        self.toolbars: list[QToolBar] = []

        def bar(title: str, name: str, tab: str) -> QToolBar:
            tb = tbs.group(win, title, name, tab, sketch=True)
            self.toolbars.append(tb)
            return tb

        def tool(tb: QToolBar, t: str) -> None:
            key = _TOOL_KEYS.get(t, "")
            a = tbs.action(win, tb, _TOOL_LABELS[t], "s_" + t.lower(),
                           st.HINTS[t] + (f"\nKey: {key}" if key else "") + f"\nRuns: {_TOOL_RUNS[t]}",
                           lambda _=False, t=t: self.set_tool(t), key or None, checkable=True)
            group.addAction(a)
            self.tool_actions[t] = a

        tb = bar("Sketch draw", "sketch", "Sketch")
        for t in ("SELECT",) + st.DRAW_TOOLS:
            tool(tb, t)
        self.sides = QSpinBox()
        self.sides.setRange(3, 64)
        self.sides.setValue(self.controller.polygon_sides)
        self.sides.setPrefix("Sides ")
        self.sides.setToolTip("How many sides the Polygon tool draws")
        self.sides.valueChanged.connect(lambda n: setattr(self.controller, "polygon_sides", n))
        tb.addWidget(self.sides)
        a = tbs.action(win, tb, "Auto constraints", "s_auto",
                       "While drawing, a click on a curve puts the point on it, and a line drawn on from an arc's end "
                       "along it is tangent (or square to the line before it). The marks by the cursor show what a "
                       "click will add. Hold Shift to draw without them.\nAdds: SCON, ON / TANGENT / PERPENDICULAR",
                       checkable=True)
        a.setChecked(True)
        a.toggled.connect(lambda on: setattr(self.controller, "auto", on))
        self.auto_action = a
        self.tool_actions["SELECT"].setChecked(True)

        tb = bar("Sketch edit", "sketch_edit", "Sketch edit")
        for t in st.EDIT_TOOLS:
            tool(tb, t)
        a = tbs.action(win, tb, "Axes cut", "s_axes",
                       "Let the sketch's H and V axes cut too when trimming (handy for half a profile to revolve)\n"
                       "Runs: STRIM, n, u, v, AXES", checkable=True)
        a.toggled.connect(lambda on: setattr(self.controller, "trim_axes", on))
        self.axes_action = a
        self.edit_actions: dict[str, QAction] = {}
        for label, icon, slot, tip in (
                ("Offset…", "s_offset", self.offset, "Offset the selected curves (a chain is offset as one)\n"
                                                     "Runs: SOFFSET, d, ..."),
                ("Mirror…", "s_mirror", self.mirror, "Mirror the selected geometry about a line (select it too) or "
                                                     "H / V\nRuns: SMIRROR, axis, ..."),
                ("Pattern…", "s_pattern", self.pattern, "Copies of the selected geometry in a row or round a point\n"
                                                        "Runs: SPATTERN, LINEAR/POLAR, ..."),
                ("Move/Copy…", "s_move", self.transform, "Move, turn or scale the selected geometry, or copies of it; "
                                                         "constraints among it go along\nRuns: STRANSFORM, ..."),
                ("Offset both…", "s_offset2", self.offset2, "Offset the selected curves to both sides with round (or "
                                                            "flat) ends: a slot along a path\nRuns: SOFFSET2, d, ..."),
                ("Join to spline", "s_join", self.join, "Join the selected curves (end to end) into one smooth "
                                                        "spline, or turn one curve into a spline\nRuns: SJOIN, ..."),
                ("Project…", "s_project", self.project, "Bring body edges into the sketch (the edges or faces picked "
                                                        "before the sketch, or IDs)\nRuns: SPROJECT, ..."),
                ("Cut bodies…", "s_intersect", self.intersect, "Bring in the curves where bodies cut the sketch plane "
                                                               "(a section)\nRuns: SINTERSECT, body, ...")):
            a = tbs.action(win, tb, label, icon, tip, lambda _=False, f=slot: f())
            self.edit_actions[label.rstrip("…")] = a
        for label, icon, cmd, tip in (
                ("From DXF…", "s_dxf", "SDXF", "Bring a 2D DXF drawing's lines, arcs, circles, polylines and splines "
                                               "into this sketch, joined where they meet\nRuns: SDXF, file [, scale, "
                                               "du, dv, layer]"),
                ("Trace picture…", "s_trace", "STRACE", "Trace the outlines of the dark shapes in a picture into this "
                                                        "sketch, as smooth curves or straight pieces\n"
                                                        "Runs: STRACE, file, width [, threshold, du, dv]"),
                ("Picture…", "image", "IMAGE", "Show a picture on a plane behind the model, to draw over (it is "
                                              "not part of the model)\nRuns: IMAGE, file, plane, width")):
            a = tbs.action(win, tb, label, icon, tip, lambda _=False, c=cmd: self.win.open_form(c))
            self.edit_actions[label.rstrip("…")] = a

        tb = bar("Constraints", "sketch_constraints", "Constrain")
        for label, kind, tip in _CONSTRAINTS:
            tbs.action(win, tb, label, "c_" + kind.lower(), tip,
                       lambda _=False, k=kind: self.run(lambda: st.constraint_command(self.p, k)))

        tb = bar("Sizes", "sketch_sizes", "Constrain")
        for label, icon, which, tip in (
                ("Size…", "d_size", "AUTO", "Length of a line, diameter of a circle, radius of an arc, distance between "
                                             "two points or from a point to a line, angle between two lines\nRuns: SDIM, ..."),
                ("Across…", "d_across", "HDIST", "Horizontal distance between two points (or a point and the origin)\n"
                                                  "Runs: SDIM, HDIST, ..."),
                ("Up…", "d_up", "VDIST", "Vertical distance between two points (or a point and the origin)\n"
                                          "Runs: SDIM, VDIST, ..."),
                ("Arc length…", "d_arclen", "ARCLEN", "Length along an arc or elliptical arc\nRuns: SDIM, ARCLEN, n, ...")):
            tbs.action(win, tb, label, icon, tip, lambda _=False, w=which: self.add_dimension(w))
        tbs.action(win, tb, "Construction", "s_construction",
                   "Make the selected curves construction geometry (or back)\nRuns: SCONSTRUCT, n, ON/OFF",
                   lambda: self.run(lambda: st.construction_command(self.p)))
        tbs.action(win, tb, "Delete", "s_delete", "Delete the selected geometry or sizes\nRuns: SDEL, ...",
                   lambda: self.run(lambda: st.delete_command(self.p)), QKeySequence.Delete)
        tbs.action(win, tb, "Finish sketch", "s_finish", "Leave sketch mode\nRuns: ENDSKETCH",
                   lambda: self.win.execute("ENDSKETCH"))
        tbs.action(win, tb, "Extrude…", "extrude", "Finish and extrude this sketch\n"
                                                    "Runs: EXTRUDE, sketch, d [, mode, body]", self.extrude)
        return self.toolbars[0]

    SKETCH_TABS = ("Sketch", "Sketch edit", "Constrain")

    def _show_bars(self, on: bool) -> None:
        """The sketch tabs come with sketch mode; opening a sketch shows its
        drawing tab, and closing it goes back to the tab used before."""
        rb = self.win.ribbon
        self.shown = on
        if on:
            if rb.current_title() not in self.SKETCH_TABS:
                self._tab_before = rb.current_title()
            for t in self.SKETCH_TABS:
                rb.show_tab(t, True)
            rb.select("Sketch")
        else:
            back = getattr(self, "_tab_before", "")
            for t in self.SKETCH_TABS:
                rb.show_tab(t, False)
            if back:
                rb.select(back)

    def set_tool(self, tool: str) -> None:
        self.controller.set_tool(tool)
        self.tool_actions[tool].setChecked(True)
        self.win.viewport.set_preview(None)
        from . import sketch_typed

        hint = st.HINTS[tool]
        if tool in sketch_typed.TOOLS:
            hint += " · Type a size after the first click (Tab: next box, Enter: place it)"
        self.win.statusBar().showMessage(hint)

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
            if on != self.shown:
                self._show_bars(on)
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

    def offset2(self) -> None:
        try:
            st.offset2_command(self.p, "1")
        except st.NeedSelection as exc:
            self.win.statusBar().showMessage(str(exc), 6000)
            return
        d = self._ask("Offset both sides", "Distance to each side (add FLAT for straight ends):", "2")
        if d:
            flat = d.strip().upper().endswith("FLAT")
            d = d.strip()[:-4].rstrip(", ") if flat else d
            self.run(lambda: st.offset2_command(self.p, d, flat))

    def join(self) -> None:
        self.run(lambda: st.join_command(self.p))

    def intersect(self) -> None:
        ids = self._ask("Cut bodies with the sketch plane", "Body IDs:", st.intersect_default(self.p))
        if ids:
            self.win.execute(f"SINTERSECT, {ids}")

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

    def transform(self) -> None:
        try:
            st.transform_command(self.p, "MOVE", "0, 0")
        except st.NeedSelection as exc:
            self.win.statusBar().showMessage(str(exc), 6000)
            return
        dlg = TransformForm(self.win, self.p)
        if dlg.exec() == QDialog.Accepted:
            self.run(dlg.lines)

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
                "ANGLE": "Angle (degrees)", "HDIST": "Horizontal distance", "VDIST": "Vertical distance",
                "MAJOR": "First radius", "MINOR": "Second radius", "ARCLEN": "Arc length"}[kind]
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
                c = self.p.model.sketch(name).cons.get(int(label[1:]))
                line = st.dimension_edit(self.p, self._uid_of(n), new, c.data.get("arg", -1) if c else -1)
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
        bodies = [b for b in p.model.bodies.values() if p.model.is_shown(b.id) and b.entity_ids["FACE"]]
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


class TransformForm(QDialog):
    """Move, turn or scale the selected sketch geometry, or copies of it."""

    _HOW = {"MOVE": ("Move by du, dv:", "10, 0"),
            "ROTATE": ("Angle (degrees), then the centre (a point like O or 3.C, or u, v):", "90, O"),
            "SCALE": ("Factor, then the centre (a point like O or 3.C, or u, v):", "2, O")}

    def __init__(self, parent, p) -> None:
        super().__init__(parent)
        self.setWindowTitle("Move / copy sketch geometry")
        self.p = p
        form = QFormLayout()
        self.kind = QComboBox()
        self.kind.addItems(["Move", "Rotate", "Scale"])
        form.addRow("Do:", self.kind)
        self.how = QLabel()
        self.values = QLineEdit()
        form.addRow(self.how)
        form.addRow("", self.values)
        self.copy = QCheckBox("Make a copy (the selected geometry stays where it is)")
        form.addRow(self.copy)
        self.preview = QLineEdit()
        self.preview.setReadOnly(True)
        form.addRow("Runs:", self.preview)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.kind.currentTextChanged.connect(self._kind)
        self.values.textChanged.connect(self._show)
        self.copy.toggled.connect(self._show)
        self._kind(self.kind.currentText())
        self.resize(480, 0)

    def _kind(self, text: str) -> None:
        label, start = self._HOW[text.upper()]
        self.how.setText(label)
        self.values.setText(start)
        self._show()

    def lines(self) -> list[str]:
        return st.transform_command(self.p, self.kind.currentText().upper(), self.values.text(), self.copy.isChecked())

    def _show(self, *_) -> None:
        try:
            self.preview.setText(self.lines()[0])
        except st.NeedSelection as exc:
            self.preview.setText(str(exc))


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
