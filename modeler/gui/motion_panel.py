"""The Motion window: move an assembly by one of its parameters with a slider, play it, check the
whole range for parts running into each other, and save it as pictures.

Each slider position runs ``DRIVE, name, value`` (only the steps that read the parameter run
again; the history does not change). **Check range** runs ``MOTION``. **Save pictures…** saves
one PNG per position from the 3D view. Closing the window lets the parameter go
(``DRIVE, name``), so the model is as the history makes it.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QComboBox,
    QLineEdit,
    QWidget,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from .main_window import MainWindow


def driveable(p) -> list[str]:
    """Parameters set by a top-level history line, in the order they are first set."""
    out = []
    pat = re.compile(r"^\s*([A-Za-z_]\w*)\s*=(?!=)", re.MULTILINE)
    for e in p.history[: p.cursor]:
        for m in pat.finditer(e.text):
            name = m.group(1).upper()
            if name not in out and isinstance(p.params.get(name), (int, float)):
                out.append(name)
    return out


class Plot(QWidget):
    """Small line charts of a motion study, one panel per series (name, x, y, unit)."""

    COLOURS = ("#2a6fdb", "#d9534f", "#2e9e5b", "#b26fd1", "#e08a1e", "#3aa6b9")

    def __init__(self) -> None:
        super().__init__()
        self.series: list[tuple[str, list[float], list[float], str]] = []
        self.marker: float | None = None  # the slider's value, drawn as a line
        self.setMinimumHeight(0)

    def set_series(self, series) -> None:
        self.series = list(series)
        self.setMinimumHeight(110 * len(self.series))
        self.update()

    def set_marker(self, x: float | None) -> None:
        self.marker = x
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt's name
        if not self.series:
            return
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        text = pal.color(pal.ColorRole.WindowText)
        n = len(self.series)
        h = self.height() / n
        left, right = 62, 8
        for i, (name, xs, ys, unit) in enumerate(self.series):
            top, bot = i * h + 16, (i + 1) * h - 16
            x0, x1 = min(xs), max(xs) if max(xs) > min(xs) else min(xs) + 1
            from ..geometry.kinematics import _yrange

            y0, y1 = _yrange(ys)
            if y1 - y0 < 1e-12:
                y0, y1 = y0 - 1, y1 + 1
            w = self.width() - left - right

            def px(x, x0=x0, x1=x1, w=w):
                return left + (x - x0) / (x1 - x0) * w

            def py(y, y0=y0, y1=y1, top=top, bot=bot):
                return bot - (y - y0) / (y1 - y0) * (bot - top)

            qp.setPen(QPen(QColor(150, 150, 150)))
            qp.drawRect(int(left), int(top), int(w), int(bot - top))
            qp.setPen(text)
            qp.drawText(int(left + 4), int(top - 3), f"{name} ({unit})")
            qp.drawText(2, int(top + 10), f"{y1:.4g}")
            qp.drawText(2, int(bot), f"{y0:.4g}")
            qp.setPen(QPen(QColor(self.COLOURS[i % len(self.COLOURS)]), 1.6))
            qp.drawPolyline(QPolygonF([QPointF(px(x), py(y)) for x, y in zip(xs, ys)]))
            if self.marker is not None and x0 <= self.marker <= x1:
                qp.setPen(QPen(QColor(120, 120, 120), 1, Qt.DashLine))
                qp.drawLine(int(px(self.marker)), int(top), int(px(self.marker)), int(bot))
        qp.end()


class MotionDialog(QDialog):
    def __init__(self, win: MainWindow) -> None:
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Motion")
        self.setWindowModality(Qt.NonModal)
        self.setMinimumWidth(460)
        self.driven: str | None = None
        p = win.processor

        self.param = QComboBox()
        self.param.addItems(driveable(p))
        self.param.setToolTip("The parameter that moves the assembly (set in the history, e.g. A = 30, and used "
                              "in a MATE, ROTATE or MOVE)")
        self.start = QDoubleSpinBox()
        self.end = QDoubleSpinBox()
        for box in (self.start, self.end):
            box.setRange(-1e6, 1e6)
            box.setDecimals(3)
        self.end.setValue(90)
        self.steps = QSpinBox()
        self.steps.setRange(1, 500)
        self.steps.setValue(18)
        form = QFormLayout()
        form.addRow("Parameter", self.param)
        form.addRow("From", self.start)
        form.addRow("To", self.end)
        form.addRow("Steps", self.steps)
        self.points = QLineEdit()
        self.points.setPlaceholderText("rod 120,0,10; crank 40,0,0")
        self.points.setToolTip("Points to follow for Study: a body and a point on it as it is now; ; between them")
        self.time = QDoubleSpinBox()
        self.time.setRange(0.001, 1e5)
        self.time.setDecimals(3)
        self.time.setValue(1.0)
        self.time.setSuffix(" s")
        self.time.setToolTip("How long the motion takes: speeds, accelerations and the drive torque follow from it")
        form.addRow("Points", self.points)
        form.addRow("Time", self.time)

        self.slider = QSlider(Qt.Horizontal)
        self.value_label = QLabel()
        self.value_label.setMinimumWidth(110)
        row = QHBoxLayout()
        row.addWidget(self.slider, 1)
        row.addWidget(self.value_label)

        self.play_btn = QPushButton("Play")
        self.play_btn.setCheckable(True)
        self.play_btn.setToolTip("Run through the range and back")
        self.check_btn = QPushButton("Check range")
        self.check_btn.setToolTip("Look for parts running into each other at every step (MOTION)")
        self.study_btn = QPushButton("Study")
        self.study_btn.setToolTip("Position, speed and acceleration of the points, and the drive torque or force, "
                                  "at every step, as plots (MOTION with points)")
        self.table_btn = QPushButton("Save table…")
        self.table_btn.setToolTip("Write the study as a table (.csv) or as plots (.svg)")
        self.save_btn = QPushButton("Save pictures…")
        self.save_btn.setToolTip("One picture of the 3D view per step, into a folder you choose")
        close_btn = QPushButton("Close")
        buttons = QHBoxLayout()
        for b in (self.play_btn, self.check_btn, self.study_btn, self.table_btn, self.save_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(close_btn)

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setMaximumBlockCount(500)
        self.report.setPlaceholderText("Check range lists the positions where parts overlap.")

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addLayout(row)
        lay.addLayout(buttons)
        lay.addWidget(self.report, 1)
        self.plot = Plot()
        lay.addWidget(self.plot, 2)

        self._pending: int | None = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(40)
        self._debounce.timeout.connect(self._drive_pending)
        self._play = QTimer(self)
        self._play.setInterval(120)
        self._play.timeout.connect(self._tick)
        self._dir = 1

        self.param.currentTextChanged.connect(self._param_changed)
        for w in (self.start, self.end):
            w.valueChanged.connect(self._range_changed)
        self.steps.valueChanged.connect(self._range_changed)
        self.slider.valueChanged.connect(self._slid)
        self.play_btn.toggled.connect(self._toggle_play)
        self.check_btn.clicked.connect(self.check)
        self.study_btn.clicked.connect(lambda: self.study())
        self.table_btn.clicked.connect(lambda: self.save_table())
        self.save_btn.clicked.connect(self.save_pictures)
        close_btn.clicked.connect(self.close)
        self._param_changed(self.param.currentText())

    # ---- values ------------------------------------------------------------------------
    def values(self) -> list[float]:
        a, b, n = self.start.value(), self.end.value(), self.steps.value()
        return [a + (b - a) * i / n for i in range(n + 1)]

    def _param_changed(self, name: str) -> None:
        self.let_go()
        ok = bool(name)
        for w in (self.slider, self.play_btn, self.check_btn, self.save_btn):
            w.setEnabled(ok)
        if not ok:
            self.value_label.setText("no parameter")
            self.report.setPlainText("Set a parameter in the history (A = 0) and use it in the steps that move "
                                     "(MATE, ANGLE, ..., A or ROTATE, lid, A, ...), then open Motion again.")
            return
        self._range_changed()

    def _range_changed(self) -> None:
        self.slider.blockSignals(True)
        self.slider.setRange(0, self.steps.value())
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self._show_value(0)

    def _show_value(self, i: int) -> None:
        vals = self.values()
        self.value_label.setText(f"{self.param.currentText()} = {vals[min(i, len(vals) - 1)]:.6g}")
        if hasattr(self, "plot"):
            self.plot.set_marker(vals[min(i, len(vals) - 1)])

    # ---- driving -----------------------------------------------------------------------
    def _slid(self, i: int) -> None:
        self._show_value(i)
        self._pending = i
        self._debounce.start()

    def _drive_pending(self) -> None:
        if self._pending is not None:
            self.drive_to(self._pending)

    def drive_to(self, i: int) -> bool:
        name = self.param.currentText()
        if not name:
            return False
        v = self.values()[i]
        r = self.win.execute(f"DRIVE, {name}, {v:.10g}")
        if r.ok:
            self.driven = name
        else:
            self.report.setPlainText(r.message)
        return r.ok

    def let_go(self) -> None:
        if self.driven and self.driven in self.win.processor.drive:
            self.win.execute(f"DRIVE, {self.driven}")
        self.driven = None

    def _toggle_play(self, on: bool) -> None:
        self.play_btn.setText("Stop" if on else "Play")
        if on:
            self._play.start()
        else:
            self._play.stop()

    def _tick(self) -> None:
        i = self.slider.value() + self._dir
        if i > self.slider.maximum() or i < 0:
            self._dir = -self._dir
            i = self.slider.value() + self._dir
        self.slider.setValue(i)

    # ---- checking and pictures ---------------------------------------------------------
    def check(self) -> str:
        self.play_btn.setChecked(False)
        name = self.param.currentText()
        self.let_go()
        r = self.win.execute(f"MOTION, {name}, {self.start.value():.10g}, {self.end.value():.10g}, "
                             f"{self.steps.value()}")
        self.report.setPlainText(r.message)
        self.slider.blockSignals(True)
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self._show_value(0)
        return r.message

    def _study_line(self, file: str = "") -> str:
        name = self.param.currentText()
        pts = self.points.text().strip().replace('"', "")
        line = (f"MOTION, {name}, {self.start.value():.10g}, {self.end.value():.10g}, {self.steps.value()}, "
                f"\"{pts}\", {self.time.value():.10g}")
        if file:
            line += f', , "{file}"'
        return line

    def study(self, file: str = "") -> str:
        """Run the motion study and plot it."""
        self.play_btn.setChecked(False)
        self.let_go()
        r = self.win.execute(self._study_line(file))
        self.report.setPlainText(r.message)
        rep = (self.win.processor.reports.get("MOTION") or {}).get("study") if r.ok else None
        series = []
        if rep:
            xs = rep["values"]
            u = rep["unit"]
            for label, d in rep["points"].items():
                series.append((f"{label} speed", xs, d["speed"], f"{u}/s"))
                series.append((f"{label} acceleration", xs, d["accel"], f"{u}/s²"))
            if rep.get("drive"):
                series.append(("drive " + ("torque" if rep["kind"] == "ANGLE" else "force"), xs,
                               rep["drive"]["values"], rep["drive"]["unit"]))
        self.plot.set_series(series)
        self.slider.blockSignals(True)
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self._show_value(0)
        return r.message

    def save_table(self, path: str = "") -> str:
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save the motion study", "motion.csv",
                                                  "Table (*.csv);;Plots (*.svg)")
            if not path:
                return ""
        return self.study(path)

    def save_pictures(self, folder: str = "") -> list[str]:
        from OCP.Image import Image_AlienPixMap
        from OCP.TCollection import TCollection_AsciiString
        from PySide6.QtWidgets import QApplication

        self.play_btn.setChecked(False)
        if not folder:
            folder = QFileDialog.getExistingDirectory(self, "Folder for the pictures")
            if not folder:
                return []
        name = self.param.currentText()
        vp = self.win.viewport
        w, h = max(vp.width(), 320), max(vp.height(), 200)
        saved = []
        for i in range(len(self.values())):
            self.slider.blockSignals(True)
            self.slider.setValue(i)
            self.slider.blockSignals(False)
            self._show_value(i)
            if not self.drive_to(i):
                break
            QApplication.processEvents()
            vp.view.Redraw()
            path = os.path.join(folder, f"{name.lower()}_{i:03d}.png")
            pix = Image_AlienPixMap()
            if vp.view.ToPixMap(pix, w, h) and pix.Save(TCollection_AsciiString(path)):
                saved.append(path)
        self.report.setPlainText(f"saved {len(saved)} pictures to {folder}" if saved else "no pictures saved")
        return saved

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt's name
        self.play_btn.setChecked(False)
        self.let_go()
        super().closeEvent(event)


def open_motion(win: MainWindow) -> MotionDialog:
    dlg = getattr(win, "_motion_dialog", None)
    if dlg is None or not dlg.isVisible():
        dlg = MotionDialog(win)
        win._motion_dialog = dlg
    dlg.show()
    dlg.raise_()
    return dlg
