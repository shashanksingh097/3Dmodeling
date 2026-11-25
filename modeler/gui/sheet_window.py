"""View > Drawing sheets…: a live drawing-sheet window (PLAN item 110).

The window shows one sheet (DRAWSHEET) as it would print, made from the model as it is now, and
draws it again a moment after every change. Each view has a box around it: drag the box to move
the view, which writes one SHEETVIEW step (so undo puts it back and the history shows it). The
buttons add the usual drawing details through commands as well:

* Size of picked edge: SHEETNOTE, sheet, SIZE, EDGE n for each edge picked in the 3D view
* Note on pick…: the SHEETNOTE form for a leader note on the picked face, edge or vertex
* Centre marks: SHEETNOTE, sheet, CENTRES
* Parts list…: the SHEETTABLE form (parts list with balloons, hole table ...)
* Views back: SHEETVIEW, sheet, view, RESET for every moved view
* Save PDF…: DRAWINGS, "file.pdf"

Nothing is kept in the window itself: the sheet, its moves and its details are all in the model,
so the assistant and the command line see the same sheet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QByteArray, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from .main_window import MainWindow


class ViewBox(QGraphicsRectItem):
    """The box around one view on the sheet; dragging it moves the view (SHEETVIEW on release)."""

    def __init__(self, win: SheetWindow, title: str, rect: QRectF) -> None:
        super().__init__(rect)
        self.win, self.title = win, title
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setCursor(Qt.SizeAllCursor)
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"{title.lower()}: drag to move it on the sheet")
        self._idle()

    def _idle(self) -> None:
        self.setPen(QPen(QColor(30, 110, 220, 90), 0.4, Qt.DashLine))
        self.setBrush(QBrush(Qt.NoBrush))

    def hoverEnterEvent(self, ev) -> None:  # noqa: N802 - Qt name
        self.setPen(QPen(QColor(30, 110, 220), 0.6))
        self.setBrush(QBrush(QColor(30, 110, 220, 25)))
        super().hoverEnterEvent(ev)

    def hoverLeaveEvent(self, ev) -> None:  # noqa: N802
        self._idle()
        super().hoverLeaveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        super().mouseReleaseEvent(ev)
        d = self.pos()
        if abs(d.x()) > 0.2 or abs(d.y()) > 0.2:
            self.win.moved(self.title, d.x(), -d.y())  # the scene's y goes down, the paper's goes up


class SheetWindow(QDialog):
    def __init__(self, win: MainWindow) -> None:
        super().__init__(win)
        self.main = win
        self.setWindowTitle("Drawing sheets")
        self.resize(900, 700)
        self.page = None
        self.boxes: dict[str, ViewBox] = {}
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Sheet:"))
        self.sheet_box = QComboBox()
        self.sheet_box.setToolTip("The sheet shown (DRAWSHEET makes them)")
        self.sheet_box.currentIndexChanged.connect(lambda _i: self.redraw())
        top.addWidget(self.sheet_box, 1)
        self.new_button = self._button(top, "New sheet…", "A new sheet: the DRAWSHEET form", self.new_sheet)
        lay.addLayout(top)

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing, True)
        self.view.setBackgroundBrush(QColor(110, 110, 115))
        self.view.setDragMode(QGraphicsView.NoDrag)
        lay.addWidget(self.view, 1)

        row = QHBoxLayout()
        self.size_button = self._button(row, "Size of picked edge",
                                        "Put the length of the picked straight edge (or the diameter of a round "
                                        "one) on the sheet: SHEETNOTE, SIZE", self.size_of_pick)
        self.note_button = self._button(row, "Note on pick…", "A leader note on the picked face, edge or vertex: "
                                        "the SHEETNOTE form", self.note_on_pick)
        self.centre_button = self._button(row, "Centre marks", "Centre marks on every round hole: SHEETNOTE, "
                                          "CENTRES", self.centres)
        self.table_button = self._button(row, "Parts list…", "A parts list with balloons, a hole table or "
                                         "revisions: the SHEETTABLE form", self.tables)
        self.reset_button = self._button(row, "Views back", "Put every moved view back in its own place "
                                         "(SHEETVIEW, RESET)", self.reset_views)
        row.addStretch(1)
        self.pdf_button = self._button(row, "Save PDF…", "Write every sheet to a PDF: DRAWINGS", self.save_pdf)
        lay.addLayout(row)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.refresh)
        win.processor.history_listeners.append(self.schedule)

    def _button(self, row, text, tip, fn) -> QPushButton:
        b = QPushButton(text)
        b.setToolTip(tip)
        b.clicked.connect(fn)
        row.addWidget(b)
        return b

    # ---- what is shown -----------------------------------------------------------------------------
    @property
    def p(self):
        return self.main.processor

    def sheet(self) -> dict | None:
        key = (self.sheet_box.currentData() or "").upper()
        return self.p.model.drawsheets.get(key)

    def schedule(self) -> None:
        if self.isVisible():
            self._timer.start()

    def refresh(self) -> None:
        """The list of sheets and the shown sheet, again from the model."""
        sheets = self.p.model.drawsheets
        want = self.sheet_box.currentData()
        self.sheet_box.blockSignals(True)
        self.sheet_box.clear()
        for key, s in sheets.items():
            self.sheet_box.addItem(s["name"], key)
        k = self.sheet_box.findData(want) if want else 0
        self.sheet_box.setCurrentIndex(max(k, 0) if sheets else -1)
        self.sheet_box.blockSignals(False)
        self.redraw()

    def redraw(self) -> None:
        from ..commands.drawsheet_handlers import render
        from ..commands.processor import CommandError
        from ..geometry import sheets as sh

        self.scene.clear()
        self.boxes = {}
        self.page = None
        s = self.sheet()
        has = s is not None
        for b in (self.size_button, self.note_button, self.centre_button, self.table_button, self.reset_button,
                  self.pdf_button):
            b.setEnabled(has)
        if not has:
            self.status.setText("No sheets yet: New sheet… makes one (DRAWSHEET).")
            return
        try:
            _views, page, placed, nsizes = render(self.p, s)
        except (CommandError, sh.SheetError, ValueError) as exc:
            self.status.setText(f"The sheet can't be drawn: {exc}")
            return
        self.page = page
        rend = QSvgRenderer(QByteArray(sh.svg(page).encode("utf-8")), self)
        item = QGraphicsSvgItem()
        item.setSharedRenderer(rend)
        self._renderer = rend  # kept alive with the item
        size = rend.defaultSize()
        item.setScale(page.width / max(size.width(), 1))  # one scene unit is one mm of paper
        self.scene.addItem(item)
        H = page.height
        for title, x0, y0, x1, y1 in page.boxes:
            pad = 1.5
            box = ViewBox(self, title, QRectF(x0 - pad, H - y1 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad))
            self.scene.addItem(box)
            self.boxes[title.upper()] = box
        self.scene.setSceneRect(QRectF(-10, -10, page.width + 20, page.height + 20))
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        bits = [f"{page.paper} at {sh.scale_text(page.scale)}", f"{nsizes} size{'s' if nsizes != 1 else ''}"]
        if placed:
            bits.append(f"{len(placed)} detail{'s' if len(placed) != 1 else ''}")
        moved = s.get("moves") or {}
        if moved:
            bits.append("moved: " + ", ".join(k.lower() for k in moved))
        text = "; ".join(bits) + ". Drag a view's box to move it."
        if page.warnings:
            text += "\n" + "\n".join(page.warnings[:3])
        self.status.setText(text)

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        if self.page is not None:
            self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def showEvent(self, ev) -> None:  # noqa: N802
        super().showEvent(ev)
        self.refresh()

    # ---- actions: every one a command ------------------------------------------------------------
    def _run(self, line: str) -> bool:
        res = self.main.execute(line)
        if not res.ok:
            self.status.setText(res.message)
        return res.ok

    def moved(self, title: str, dx_mm: float, dy_mm: float) -> bool:
        """A view's box was dragged by (dx, dy) mm of paper: SHEETVIEW with its new place."""
        from ..commands.drawsheet_handlers import fmt

        s = self.sheet()
        if s is None or self.page is None:
            return False
        k = self.page.scale or 1.0
        old = (s.get("moves") or {}).get(title.upper(), [0.0, 0.0])
        x, y = old[0] + dx_mm / k, old[1] + dy_mm / k
        ok = self._run(f"SHEETVIEW, {s['name']}, {title}, {fmt(x)}, {fmt(y)}")
        if not ok:
            self.redraw()
        return ok

    def _picked(self) -> tuple[str, list[int]]:
        m = self.p.model
        return m.selection_kind, [g for g in m.selection]

    def size_of_pick(self) -> bool:
        s = self.sheet()
        kind, ids = self._picked()
        if s is None:
            return False
        if kind != "EDGE" or not ids:
            self.status.setText("Pick one or more edges in the 3D view first (straight or round ones).")
            return False
        return self._run("\n".join(f"SHEETNOTE, {s['name']}, SIZE, EDGE {g}" for g in ids))

    def note_on_pick(self) -> None:
        s = self.sheet()
        if s is None:
            return
        kind, ids = self._picked()
        on = f"{kind} {ids[0]}" if kind in ("FACE", "EDGE", "VERTEX") and ids else ""
        self.main.open_form("SHEETNOTE", f"SHEETNOTE, {s['name']}, LEADER, {on}, ")

    def centres(self) -> bool:
        s = self.sheet()
        return s is not None and self._run(f"SHEETNOTE, {s['name']}, CENTRES")

    def tables(self) -> None:
        s = self.sheet()
        if s is not None:
            self.main.open_form("SHEETTABLE", f"SHEETTABLE, {s['name']}, PARTS")

    def reset_views(self) -> bool:
        s = self.sheet()
        if s is None or not s.get("moves"):
            return False
        return self._run("\n".join(f"SHEETVIEW, {s['name']}, {v}, RESET" for v in s["moves"]))

    def new_sheet(self) -> None:
        n = len(self.p.model.drawsheets) + 1
        self.main.open_form("DRAWSHEET", f"DRAWSHEET, sheet{n}, STANDARD")

    def save_pdf(self, path: str | None = None) -> bool:
        if path is None:
            path, _f = QFileDialog.getSaveFileName(self, "Save the drawing sheets", "drawings.pdf",
                                                   "PDF (*.pdf)")
            if not path:
                return False
        return self._run(f'DRAWINGS, "{path}"')


def open_window(win: MainWindow) -> SheetWindow:
    w = getattr(win, "sheet_window", None)
    if w is None:
        w = SheetWindow(win)
        win.sheet_window = w
    w.show()
    w.raise_()
    w.refresh()
    return w
