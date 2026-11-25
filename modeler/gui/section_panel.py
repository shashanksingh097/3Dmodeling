"""The Section window: cut the view open along a plane and move the plane with a slider.

Each change runs ``SECTION, plane, side, offset`` (a view setting: the history does not change),
and the window shows the area and centre of each cut. **Add plane** keeps the planes so far and
adds this one (``SECTION, plane, side, offset, ADD``). **Off** and closing the window end the section view.
**Edit in the cut** (PLAN item 96) runs ``SECTIONEDIT, plane, offset`` instead: the cut lines show in
orange, a click on one picks the face behind it and its arrow pulls it; **Draw on the cut** starts a
sketch on the plane to add or remove material with EXTRUDE.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from .main_window import MainWindow

STEPS = 200  # slider positions across the model


def plane_names(p) -> list[str]:
    return ["XY", "YZ", "ZX"] + [d.name for d in p.model.datums.values() if d.kind == "PLANE"]


def offset_range(p, plane: str) -> tuple[float, float]:
    """How far the plane can move along its normal and still cut what is shown."""
    from ..commands.feature_handlers import plane_ref
    from ..core import datum as dt
    from ..geometry import robust

    try:
        d = plane_ref(p, plane, "SECTION")
    except Exception:
        return -50.0, 50.0
    lo, hi = None, None
    for bid in p.model.shown_ids():
        shape = p.model.bodies[bid].shape
        if robust.is_empty(shape):
            continue
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        box = Bnd_Box()
        BRepBndLib.Add_s(shape, box)
        lo_c, hi_c = box.CornerMin(), box.CornerMax()  # (Get() does not convert in OCP 8)
        x0, y0, z0, x1, y1, z1 = lo_c.X(), lo_c.Y(), lo_c.Z(), hi_c.X(), hi_c.Y(), hi_c.Z()
        for x in (x0, x1):
            for y in (y0, y1):
                for z in (z0, z1):
                    t = dt.dot(dt.sub((x, y, z), d.origin), d.z)
                    lo = t if lo is None else min(lo, t)
                    hi = t if hi is None else max(hi, t)
    if lo is None or hi - lo < 1e-9:
        return -50.0, 50.0
    return lo, hi


class SectionDialog(QDialog):
    def __init__(self, win: MainWindow) -> None:
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Section")
        self.setWindowModality(Qt.NonModal)
        self.setMinimumWidth(420)
        p = win.processor

        self.plane = QComboBox()
        self.plane.addItems(plane_names(p))
        self.plane.setToolTip("The plane to cut along: a base plane or one of your datum planes")
        self.side = QComboBox()
        self.side.addItems(["BELOW", "ABOVE"])
        self.side.setToolTip("Which half stays in view: below the plane (against its normal) or above it")
        form = QFormLayout()
        form.addRow("Plane", self.plane)
        form.addRow("Keep", self.side)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, STEPS)
        self.slider.setToolTip("Move the plane along its normal through the model")
        self.value_label = QLabel()
        self.value_label.setMinimumWidth(110)
        row = QHBoxLayout()
        row.addWidget(self.slider, 1)
        row.addWidget(self.value_label)

        self.edit = QCheckBox("Edit in the cut")
        self.edit.setToolTip("Show the lines of the cut: click one to pick the face behind it, then drag its arrow "
                             "(or type a value) to move that face\nRuns: SECTIONEDIT, plane, offset")
        self.draw_btn = QPushButton("Draw on the cut")
        self.draw_btn.setToolTip("Start a sketch on the section plane; finish it and EXTRUDE it with ADD or CUT "
                                 "to add or remove material\nRuns: SKETCH (and PLANE when the plane is moved)")
        self.draw_btn.setEnabled(False)
        edit_row = QHBoxLayout()
        edit_row.addWidget(self.edit)
        edit_row.addWidget(self.draw_btn)
        edit_row.addStretch(1)

        self.add_btn = QPushButton("Add plane")
        self.add_btn.setToolTip("Keep the planes so far and cut along this one too (up to three)")
        off_btn = QPushButton("Off")
        off_btn.setToolTip("End the section view")
        close_btn = QPushButton("Close")
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_btn)
        buttons.addWidget(off_btn)
        buttons.addStretch(1)
        buttons.addWidget(close_btn)

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setPlaceholderText("The area and centre of each cut show here.")

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addLayout(row)
        lay.addLayout(edit_row)
        lay.addLayout(buttons)
        lay.addWidget(self.report, 1)

        self.kept: list[str] = []  # "plane, side, offset" of the planes kept before the one the slider moves
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(40)
        self._debounce.timeout.connect(self.apply)

        self.plane.currentTextChanged.connect(self._plane_changed)
        self.side.currentTextChanged.connect(lambda _t: self._debounce.start())
        self.slider.valueChanged.connect(self._slid)
        self.add_btn.clicked.connect(self.add_plane)
        self.edit.toggled.connect(self._edit_toggled)
        self.draw_btn.clicked.connect(self.draw)
        off_btn.clicked.connect(self.off)
        close_btn.clicked.connect(self.close)
        self._plane_changed(self.plane.currentText())

    def offset(self) -> float:
        lo, hi = self.range
        return lo + (hi - lo) * self.slider.value() / STEPS

    def _plane_changed(self, name: str) -> None:
        self.range = offset_range(self.win.processor, name)
        self.slider.blockSignals(True)
        self.slider.setValue(STEPS // 2)
        self.slider.blockSignals(False)
        self._slid(self.slider.value())

    def _slid(self, _i: int) -> None:
        self.value_label.setText(f"offset {self.offset():.4g}")
        self._debounce.start()

    def current(self) -> str:
        return f"{self.plane.currentText()}, {self.side.currentText()}, {self.offset():.10g}"

    def _edit_toggled(self, on: bool) -> None:
        self._edit_toggled_view(on)
        if on:
            self.kept = []
            self.apply()
        else:
            r = self.win.execute("SECTIONEDIT, OFF")
            self.report.setPlainText(r.message)
            self._debounce.start()

    def draw(self) -> list[str]:
        """Start a sketch on the section plane (the steps SECTIONEDIT lists under "draw")."""
        data = self.win.processor.reports.get("SECTIONEDIT") or {}
        lines = list(data.get("draw") or [])
        for line in lines:
            r = self.win.execute(line)
            if not r.ok:
                self.report.setPlainText(r.message)
                break
        return lines

    def apply(self) -> str:
        """Show the section for the current plane, side and offset (after any planes kept)."""
        if self.edit.isChecked():
            r = self.win.execute(f"SECTIONEDIT, {self.plane.currentText()}, {self.offset():.10g}")
            self.report.setPlainText(r.message)
            return r.message
        lines = [*self.kept, self.current()]
        r = None
        for i, line in enumerate(lines):
            r = self.win.execute(f"SECTION, {line}" + (", ADD" if i else ""))
            if not r.ok:
                break
        self.report.setPlainText(r.message)
        return r.message

    def add_plane(self) -> None:
        if len(self.kept) >= 2:
            self.report.setPlainText("at most three planes at once: Off starts again")
            return
        self.kept.append(self.current())
        self._slid(self.slider.value())

    def off(self) -> None:
        self._debounce.stop()
        self.kept = []
        r = self.win.execute("SECTIONEDIT, OFF" if self.edit.isChecked() else "SECTION, OFF")
        self.edit.blockSignals(True)
        self.edit.setChecked(False)
        self.edit.blockSignals(False)
        self._edit_toggled_view(False)
        self.report.setPlainText(r.message)

    def _edit_toggled_view(self, on: bool) -> None:
        self.add_btn.setEnabled(not on)
        self.side.setEnabled(not on)
        self.draw_btn.setEnabled(on)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt's name
        self._debounce.stop()
        if getattr(self.win.processor, "section_edit", None) is not None:
            self.win.execute("SECTIONEDIT, OFF")
        elif self.win.processor.section is not None:
            self.win.execute("SECTION, OFF")
        super().closeEvent(event)


def open_section(win: MainWindow) -> SectionDialog:
    dlg = getattr(win, "_section_dialog", None)
    if dlg is None or not dlg.isVisible():
        dlg = SectionDialog(win)
        win._section_dialog = dlg
    dlg.show()
    dlg.raise_()
    return dlg
