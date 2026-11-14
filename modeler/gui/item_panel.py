"""The item panel under the model tree: the steps that made the picked body.

Each line opens in its fill-in form (a line inside a ``*PART`` recipe or a
loop too); OK writes ``HIST, EDIT`` for that history entry, so the model
rebuilds. The parameters those steps use can be changed in place. What is
listed comes from gui/item_model.py.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import body_menu as bm
from . import item_model as im


class ItemPanel(QWidget):
    def __init__(self, window) -> None:
        super().__init__()
        self.win = window
        self.info: im.ItemInfo | None = None
        self.title = QLabel("Pick a body in the tree or the view to see the steps that made it.")
        self.title.setWordWrap(True)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #555;")
        self.steps = QTableWidget(0, 2)
        self.steps.setHorizontalHeaderLabels(["#", "Step"])
        self.steps.verticalHeader().hide()
        self.steps.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.steps.setSelectionMode(QAbstractItemView.SingleSelection)
        self.steps.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.steps.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.steps.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.steps.verticalHeader().setDefaultSectionSize(20)
        self.steps.cellDoubleClicked.connect(lambda r, _c: self.edit(r))
        self.edit_button = QPushButton("Edit step…")
        self.edit_button.setToolTip("Change the picked step in its form; the model rebuilds (HIST, EDIT)")
        self.edit_button.clicked.connect(lambda: self.edit(self.steps.currentRow()))
        self.show_button = QPushButton("Show in History")
        self.show_button.clicked.connect(self._show_in_history)
        self.params = QTableWidget(0, 2)
        self.params.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.params.verticalHeader().hide()
        self.params.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.params.verticalHeader().setDefaultSectionSize(20)
        self.params.itemChanged.connect(self._param_changed)
        self._filling = False

        buttons = QHBoxLayout()
        buttons.addWidget(self.edit_button)
        buttons.addWidget(self.show_button)
        buttons.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.title)
        lay.addWidget(self.note)
        lay.addWidget(self.steps, 3)
        lay.addLayout(buttons)
        lay.addWidget(QLabel("Parameters these steps use"))
        lay.addWidget(self.params, 1)

        self._pending = False
        window.processor.model.subscribe(self._on_model)
        window.processor.history_listeners.append(self.schedule)
        self.refresh()

    def _on_model(self, ev) -> None:
        if ev.kind in ("selection", "restored", "cleared", "body_removed", "renamed"):
            self.schedule()

    def schedule(self) -> None:
        if not self._pending:
            self._pending = True
            QTimer.singleShot(0, self.refresh)

    def current_body(self) -> int | None:
        sel = bm.selected_bodies(self.win.processor.model)
        return sel[0] if len(sel) == 1 else None

    def refresh(self) -> None:
        self._pending = False
        p = self.win.processor
        bid = self.current_body()
        self.info = im.item_info(p, bid) if bid is not None else None
        self._filling = True
        try:
            if self.info is None:
                self.title.setText("Pick one body in the tree or the view to see the steps that made it.")
                self.note.setText("")
                self.steps.setRowCount(0)
                self.params.setRowCount(0)
                self.edit_button.setEnabled(False)
                self.show_button.setEnabled(False)
                return
            info = self.info
            self.title.setText(f"<b>{info.title}</b>")
            if info.part:
                self.note.setText(f"Placed from part {info.part} ({info.copies} cop{'y' if info.copies == 1 else 'ies'}). "
                                  "Lines of the part's recipe change every copy; the INST line places it.")
            else:
                self.note.setText("Double-click a step to change it; the model rebuilds.")
            self.steps.setRowCount(len(info.lines))
            for r, ln in enumerate(info.lines):
                num = QTableWidgetItem(str(ln.row + 1) if ln.depth == 0 else "")
                text = QTableWidgetItem(("      " if ln.depth else "") + ln.text)
                tip = im.line_note(p, info, ln)
                text.setToolTip(tip + ("\nopens in its form" if ln.form else "\nopens as text"))
                if ln.warning:
                    text.setForeground(QBrush(QColor(176, 108, 0)))
                    text.setToolTip(text.toolTip() + "\nneeds a look: " + ln.warning.splitlines()[0])
                elif not ln.form and ln.depth == 0 and ln.line is not None:
                    text.setForeground(QBrush(QColor(110, 110, 110)))
                self.steps.setItem(r, 0, num)
                self.steps.setItem(r, 1, text)
            self.params.setRowCount(len(info.params))
            for r, (name, value) in enumerate(info.params):
                key = QTableWidgetItem(name)
                key.setFlags(key.flags() & ~Qt.ItemIsEditable)
                val = QTableWidgetItem(value)
                val.setToolTip("Type a new value or expression; the model rebuilds")
                self.params.setItem(r, 0, key)
                self.params.setItem(r, 1, val)
            self.edit_button.setEnabled(bool(info.lines))
            self.show_button.setEnabled(bool(info.lines))
        finally:
            self._filling = False

    # ---- actions -------------------------------------------------------------
    def edit(self, r: int):
        """Open step ``r`` of the list: its form, the sweep editor, or the entry as text."""
        if self.info is None or not 0 <= r < len(self.info.lines):
            return None
        ln = self.info.lines[r]
        if ln.form and ln.line is not None:
            return self.win.open_form("", ln.text, ln.row, ln.line)
        if ln.sweep and ln.line is None:
            return self.win.open_sweep_editor(ln.row)
        if ln.form:
            return self.win.open_form("", self.win.processor.history[ln.row].text, ln.row)
        return self.win.history_panel.edit_row(ln.row)

    def _show_in_history(self) -> None:
        r = self.steps.currentRow()
        if self.info is not None and 0 <= r < len(self.info.lines):
            row = self.info.lines[r].row
            self.win.history_panel.selectRow(row)
            self.win.history_panel.scrollToItem(self.win.history_panel.item(row, 0))

    def _param_changed(self, item: QTableWidgetItem) -> None:
        if self._filling or item.column() != 1:
            return
        name = self.params.item(item.row(), 0).text()
        cmd = im.param_edit(self.win.processor, name, item.text())
        if cmd is None or not self.win.execute(cmd).ok:
            self.schedule()
