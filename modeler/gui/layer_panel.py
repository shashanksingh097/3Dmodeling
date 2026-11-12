"""The Layers panel: one row per layer, every click sends a LAYER command.

Columns: current (click to draw new bodies there), shown, locked, name
(double-click to rename), colour (click to choose), number of bodies.
The buttons below make a layer, move the selected bodies onto the chosen
layer, show only that layer, and delete it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..commands.layer_handlers import color_text
from ..core.model import DEFAULT_LAYER

if TYPE_CHECKING:
    from .main_window import MainWindow

CUR, SHOW, LOCK, NAME, COLOR, COUNT = range(6)
_REFRESH_ON = {"layers", "style", "body_added", "body_removed", "restored", "cleared", "selection"}


class LayerPanel(QWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.win = window
        self._filling = False
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "Show", "Lock", "Layer", "Colour", "Bodies"])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        h = self.table.horizontalHeader()
        for col in (CUR, SHOW, LOCK, COLOR, COUNT):
            h.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(NAME, QHeaderView.Stretch)
        self.table.horizontalHeaderItem(CUR).setToolTip("Current layer: new bodies go here")
        self.table.itemChanged.connect(self._changed)
        self.table.cellClicked.connect(self._clicked)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        self.new_button = QPushButton("New…")
        self.new_button.setToolTip("Make a layer and draw new bodies on it\nRuns: LAYER, name")
        self.new_button.clicked.connect(self._new)
        self.move_button = QPushButton("Move selected here")
        self.move_button.setToolTip("Put the selected bodies (or the bodies of the selected faces) on this layer\n"
                                    "Runs: LAYER, name, ADD, SEL")
        self.move_button.clicked.connect(lambda: self._run_on_row("LAYER, {n}, ADD, SEL"))
        self.isolate_button = QPushButton("Only this")
        self.isolate_button.setToolTip("Show only this layer's bodies (SHOW, ALL brings the rest back)\n"
                                       "Runs: ISOLATE, name")
        self.isolate_button.clicked.connect(lambda: self._run_on_row("ISOLATE, {n}"))
        self.delete_button = QPushButton("Delete")
        self.delete_button.setToolTip("Delete the layer; its bodies move to DEFAULT\nRuns: LAYER, name, DELETE")
        self.delete_button.clicked.connect(lambda: self._run_on_row("LAYER, {n}, DELETE"))
        for b in (self.new_button, self.move_button, self.isolate_button, self.delete_button):
            buttons.addWidget(b)
        buttons.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.table, 1)
        lay.addLayout(buttons)

        window.processor.model.subscribe(self._on_model)
        self.refresh()

    # ---- showing ------------------------------------------------------------
    def _on_model(self, ev) -> None:
        if ev.kind in _REFRESH_ON:
            self.refresh()

    def names(self) -> list[str]:
        return [lay.name for lay in self.win.processor.model.layers.values()]

    def refresh(self) -> None:
        m = self.win.processor.model
        keep = self.current_row_name()
        counts: dict[str, int] = {}
        for b in m.bodies.values():
            counts[b.layer.upper()] = counts.get(b.layer.upper(), 0) + 1
        selected_layers = set()
        if m.selection:
            for gid in m.selection:
                try:
                    bid = gid if m.selection_kind == "BODY" else m.entity_owner(m.selection_kind, gid)[0]
                    selected_layers.add(m.bodies[bid].layer.upper())
                except Exception:
                    pass
        self._filling = True
        try:
            layers = list(m.layers.values())
            self.table.setRowCount(len(layers))
            for row, lay in enumerate(layers):
                key = lay.name.upper()
                cur = QTableWidgetItem("●" if key == m.current_layer else "")
                cur.setFlags(Qt.ItemIsEnabled)
                cur.setTextAlignment(Qt.AlignCenter)
                cur.setToolTip("New bodies go on this layer" if key == m.current_layer
                               else f"Click to draw new bodies on {lay.name}\nRuns: LAYER, {lay.name}")
                show = QTableWidgetItem()
                show.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                show.setCheckState(Qt.Checked if lay.visible else Qt.Unchecked)
                show.setToolTip(f"Runs: LAYER, {lay.name}, {'OFF' if lay.visible else 'ON'}")
                lock = QTableWidgetItem()
                lock.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                lock.setCheckState(Qt.Checked if lay.locked else Qt.Unchecked)
                lock.setToolTip("Locked: its bodies cannot be changed, used up or deleted\n"
                                f"Runs: LAYER, {lay.name}, {'UNLOCK' if lay.locked else 'LOCK'}")
                name = QTableWidgetItem(lay.name)
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
                if key != DEFAULT_LAYER:
                    flags |= Qt.ItemIsEditable
                name.setFlags(flags)
                if key in selected_layers:
                    f = name.font()
                    f.setBold(True)
                    name.setFont(f)
                    name.setToolTip("The selection is on this layer")
                col = QTableWidgetItem(color_text(lay.color) if lay.color else "")
                col.setFlags(Qt.ItemIsEnabled)
                if lay.color:
                    col.setBackground(QBrush(QColor.fromRgbF(*lay.color)))
                    col.setForeground(QBrush(QColor(0, 0, 0) if sum(lay.color) > 1.5 else QColor(255, 255, 255)))
                col.setToolTip(f"Click to choose a colour\nRuns: LAYER, {lay.name}, COLOR, #rrggbb")
                n = QTableWidgetItem(str(counts.get(key, 0)))
                n.setFlags(Qt.ItemIsEnabled)
                n.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if not lay.visible:
                    for it in (name, n):
                        it.setForeground(QBrush(QColor(150, 150, 150)))
                for c, it in ((CUR, cur), (SHOW, show), (LOCK, lock), (NAME, name), (COLOR, col), (COUNT, n)):
                    self.table.setItem(row, c, it)
            names = [lay.name for lay in layers]
            row = names.index(keep) if keep in names else next(
                (i for i, lay in enumerate(layers) if lay.name.upper() == m.current_layer), 0)
            self.table.selectRow(row)
        finally:
            self._filling = False

    def current_row_name(self) -> str | None:
        row = self.table.currentRow()
        it = self.table.item(row, NAME) if row >= 0 else None
        return it.text() if it is not None else None

    # ---- sending commands -----------------------------------------------------
    def _run(self, text: str) -> None:
        self.win.execute(text)

    def _run_on_row(self, template: str) -> None:
        n = self.current_row_name()
        if n:
            self._run(template.format(n=n))

    def _changed(self, item: QTableWidgetItem) -> None:
        if self._filling:
            return
        names = self.names()
        if item.row() >= len(names):
            return
        n = names[item.row()]
        if item.column() == SHOW:
            self._run(f"LAYER, {n}, {'ON' if item.checkState() == Qt.Checked else 'OFF'}")
        elif item.column() == LOCK:
            self._run(f"LAYER, {n}, {'LOCK' if item.checkState() == Qt.Checked else 'UNLOCK'}")
        elif item.column() == NAME:
            new = item.text().strip()
            if new and new != n:
                if not self.win.execute(f"LAYER, {n}, RENAME, {new}").ok:
                    self.refresh()
            else:
                self.refresh()

    def _clicked(self, row: int, col: int) -> None:
        names = self.names()
        if row >= len(names):
            return
        n = names[row]
        if col == CUR and n.upper() != self.win.processor.model.current_layer:
            self._run(f"LAYER, {n}")
        elif col == COLOR:
            lay = self.win.processor.model.layers[n.upper()]
            start = QColor.fromRgbF(*lay.color) if lay.color else QColor(160, 168, 180)
            c = QColorDialog.getColor(start, self, f"Colour of layer {n}")
            if c.isValid():
                self._run(f"LAYER, {n}, COLOR, {c.name()}")

    def _new(self) -> None:
        name, ok = QInputDialog.getText(self, "New layer", "Name (letters, digits, _):")
        if ok and name.strip():
            self._run(f"LAYER, {name.strip()}")
