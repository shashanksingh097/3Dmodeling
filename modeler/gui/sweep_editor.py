"""The sweep editor: a graph of each law with handles to drag, a slider that
moves a ghost section along the path, and a live preview in the 3D view.

Nothing changes the model until Apply, which sends ``HIST, EDIT`` with the
new ``SWEEP`` line (laws written as ``TABLE(t, ...)``), so the history stays
the one source of truth and Undo works as for any edit.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import sweep_edit as se
from .main_window import hist_command

_HANDLE = 6  # handle radius in pixels


class LawGraph(QWidget):
    """One law over t: the curve, its stations as handles, the slider's t."""

    changed = Signal(bool)  # True when a drag ends (time to rebuild the preview)

    def __init__(self, edit: se.SweepEdit, key: str, parent=None) -> None:
        super().__init__(parent)
        self.edit, self.key = edit, key
        self.t = 0.0
        self.drag: int | None = None
        self.setMinimumSize(420, 150)
        self.setMouseTracking(True)
        self.setToolTip("Drag a handle to change the law there (left/right moves it along the path).\n"
                        "Double-click to add a handle, right-click a handle to remove it.")
        self._fit()

    # ---- coordinates --------------------------------------------------------------
    def _fit(self) -> None:
        vals = [self.edit.value(self.key, i / 60) for i in range(61)]
        if self.key in self.edit.stations:
            vals += [v for _, v in self.edit.stations[self.key]]
        lo, hi = min(vals), max(vals)
        if self.key == "scale":
            lo = min(lo, 0.0)
        pad = max((hi - lo) * 0.15, 1.0 if self.key == "twist" else 0.1)
        self.lo, self.hi = lo - pad, hi + pad

    def _box(self) -> QRectF:
        return QRectF(46, 22, max(10, self.width() - 60), max(10, self.height() - 44))

    def to_px(self, t: float, v: float) -> QPointF:
        b = self._box()
        return QPointF(b.left() + t * b.width(), b.bottom() - (v - self.lo) / (self.hi - self.lo) * b.height())

    def from_px(self, x: float, y: float) -> tuple[float, float]:
        b = self._box()
        t = (x - b.left()) / b.width()
        v = self.lo + (b.bottom() - y) / b.height() * (self.hi - self.lo)
        return min(max(t, 0.0), 1.0), v

    def _stations(self):
        return self.edit.stations.get(self.key)

    def _hit(self, pos) -> int | None:
        st = self.edit.law_stations(self.key) if self._stations() is None else self._stations()
        for i, (t, v) in enumerate(st):
            q = self.to_px(t, v)
            if (q.x() - pos.x()) ** 2 + (q.y() - pos.y()) ** 2 <= (_HANDLE + 4) ** 2:
                return i
        return None

    # ---- drawing ----------------------------------------------------------------
    def paintEvent(self, _ev) -> None:
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.fillRect(self.rect(), QColor(250, 250, 252))
        b = self._box()
        qp.setPen(QPen(QColor(200, 200, 205), 1))
        qp.drawRect(b)
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1))
        qp.setFont(f)
        qp.setPen(QColor(90, 90, 100))
        qp.drawText(QRectF(4, 2, self.width() - 8, 18), Qt.AlignLeft | Qt.AlignVCenter, se.LABELS[self.key])
        for k in range(5):  # value grid
            v = self.lo + (self.hi - self.lo) * k / 4
            y = self.to_px(0, v).y()
            qp.setPen(QPen(QColor(232, 232, 236), 1))
            qp.drawLine(QPointF(b.left(), y), QPointF(b.right(), y))
            qp.setPen(QColor(120, 120, 130))
            qp.drawText(QRectF(0, y - 8, 42, 16), Qt.AlignRight | Qt.AlignVCenter, f"{v:.3g}")
        for k in range(5):
            x = b.left() + b.width() * k / 4
            qp.drawText(QRectF(x - 20, b.bottom() + 2, 40, 16), Qt.AlignCenter, f"t {k / 4:g}")
        path = QPainterPath()
        for i in range(121):
            t = i / 120
            q = self.to_px(t, self.edit.value(self.key, t))
            path.moveTo(q) if i == 0 else path.lineTo(q)
        qp.setPen(QPen(QColor(30, 110, 200), 2.2))
        qp.drawPath(path)
        x = self.to_px(self.t, 0).x()
        qp.setPen(QPen(QColor(220, 60, 190), 1.5, Qt.DashLine))
        qp.drawLine(QPointF(x, b.top()), QPointF(x, b.bottom()))
        st = self._stations()
        if st is not None:
            for i, (t, v) in enumerate(st):
                q = self.to_px(t, v)
                qp.setPen(QPen(QColor(20, 70, 140), 1.5))
                qp.setBrush(QColor(255, 200, 40) if i == self.drag else QColor(255, 255, 255))
                qp.drawEllipse(q, _HANDLE, _HANDLE)
        else:
            qp.setPen(QColor(120, 120, 130))
            qp.drawText(QRectF(b.left() + 6, b.top() + 2, b.width() - 12, 16), Qt.AlignLeft,
                        f"formula: {self.edit.formula.get(self.key, '')}  (drag to turn it into handles)")
        qp.end()

    # ---- mouse --------------------------------------------------------------------
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.RightButton:
            i = self._hit(e.position()) if self._stations() is not None else None
            if i is not None:
                try:
                    self.edit.remove_station(self.key, i)
                except se.SweepEditError:
                    return
                self.changed.emit(True)
                self.update()
            return
        if e.button() == Qt.LeftButton:
            if self._stations() is None:
                self.edit.law_stations(self.key)  # a formula becomes handles
                self._fit()
            self.drag = self._hit(e.position())
            self.update()

    def mouseMoveEvent(self, e) -> None:
        if self.drag is None:
            i = self._hit(e.position()) if self._stations() is not None else None
            self.setCursor(Qt.SizeAllCursor if i is not None else Qt.ArrowCursor)
            return
        t, v = self.from_px(e.position().x(), e.position().y())
        self.edit.set_station(self.key, self.drag, t, v)
        span = self.hi - self.lo
        if v > self.hi - 0.05 * span:  # grow the range, never shrink it, while dragging
            self.hi = v + 0.1 * span
        if v < self.lo + 0.05 * span:
            self.lo = v - 0.1 * span
        self.changed.emit(False)
        self.update()

    def mouseReleaseEvent(self, _e) -> None:
        if self.drag is not None:
            self.drag = None
            self._fit()
            self.changed.emit(True)
            self.update()

    def mouseDoubleClickEvent(self, e) -> None:
        t, _ = self.from_px(e.position().x(), e.position().y())
        try:
            self.edit.add_station(self.key, t)
        except se.SweepEditError:
            return
        self.changed.emit(True)
        self.update()


class SweepEditor(QDialog):
    """Edits one SWEEP step of the history; Apply sends HIST, EDIT."""

    def __init__(self, win, row: int) -> None:
        super().__init__(win)
        self.win = win
        self.edit = se.SweepEdit(win.processor, row)
        self.setWindowTitle(f"Sweep editor: step {row + 1}")
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose)
        lay = QVBoxLayout(self)
        intro = QLabel("Drag the handles to shape the twist and the scale along the path. "
                       "The slider moves a ghost section along the path; the see-through shape shows the sweep "
                       "as it will be. Nothing changes until Apply.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.graphs = [LawGraph(self.edit, k, self) for k in se.LAWS]
        for g in self.graphs:
            g.changed.connect(self._changed)
            lay.addWidget(g, 1)
        row_t = QHBoxLayout()
        row_t.addWidget(QLabel("Section at t"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setValue(500)
        self.slider.valueChanged.connect(lambda _v: self._ghost())
        row_t.addWidget(self.slider, 1)
        self.readout = QLabel()
        self.readout.setMinimumWidth(240)
        row_t.addWidget(self.readout)
        lay.addLayout(row_t)
        self.command_label = QLabel()
        self.command_label.setWordWrap(True)
        self.command_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.command_label.setStyleSheet("font-family: monospace; color: #1a3d7a; background: #f3f5fa; padding: 4px;")
        lay.addWidget(self.command_label)
        self.status = QLabel()
        lay.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(close)
        lay.addLayout(buttons)
        self._solid = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._rebuild_preview)
        self.resize(560, 560)
        self._rebuild_preview()

    @property
    def t(self) -> float:
        return self.slider.value() / 1000

    def _changed(self, final: bool) -> None:
        self._ghost()
        if final:
            self._timer.start(60)

    def _ghost(self) -> None:
        t = self.t
        for g in self.graphs:
            g.t = t
            g.update()
        try:
            section = self.edit.section(t)
            self.status.setText("")
        except se.SweepEditError as exc:
            section = None
            self.status.setText(str(exc))
        self.readout.setText(f"t = {t:.2f}   twist {self.edit.value('twist', t):.1f}°   "
                             f"scale {self.edit.value('scale', t):.3f}")
        self.command_label.setText(self.edit.command())
        self.win.viewport.set_ghosts([(self._solid, "solid"), (section, "curve")])

    def _rebuild_preview(self) -> None:
        try:
            self._solid = self.edit.preview()
            self.apply_button.setEnabled(True)
        except se.SweepEditError as exc:
            self._solid = None
            self.status.setText(str(exc))
            self.apply_button.setEnabled(False)
        self._ghost()

    def apply(self) -> None:
        text = self.edit.entry_text()
        res = self.win.execute(hist_command("EDIT", self.edit.row + 1, text))
        if res.ok:
            self.close()
        else:
            self.status.setText(res.message.splitlines()[-1] if res.message else "the edit failed")

    def closeEvent(self, e) -> None:
        self.win.viewport.set_ghosts([])
        super().closeEvent(e)


def open_editor(win, row: int | None = None) -> SweepEditor | None:
    """Open the sweep editor on a SWEEP step: the given row, else the History
    panel's selected row, else the last SWEEP in the history."""
    p = win.processor
    if row is None:
        rows = sorted({i.row() for i in win.history_panel.selectedIndexes()})
        cand = [r for r in rows if r < p.cursor and _is_sweep(p.history[r].text)]
        if cand:
            row = cand[0]
        else:
            row = next((i for i in range(p.cursor - 1, -1, -1) if _is_sweep(p.history[i].text)), None)
    if row is None:
        win.statusBar().showMessage("No SWEEP step to edit: make one first (Commands → Shapes from curves)", 6000)
        return None
    try:
        dlg = SweepEditor(win, row)
    except se.SweepEditError as exc:
        win.statusBar().showMessage(f"Sweep editor: {exc}", 8000)
        return None
    dlg.show()
    return dlg


def _is_sweep(text: str) -> bool:
    from ..lang.script import first_code_line, strip_comment

    return strip_comment(first_code_line(text)).strip().upper().startswith("SWEEP")
