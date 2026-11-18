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

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
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
        self.save_btn = QPushButton("Save pictures…")
        self.save_btn.setToolTip("One picture of the 3D view per step, into a folder you choose")
        close_btn = QPushButton("Close")
        buttons = QHBoxLayout()
        for b in (self.play_btn, self.check_btn, self.save_btn):
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
