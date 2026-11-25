"""The Properties panel (PLAN item 91): one table for the picked body, or for the
history step clicked in the History panel.

It shows PROPS as a table (commands/props_handlers.py). Values that can change
are white and editable; typing a new value runs ``PROPS, b, key, value``, which
writes the ordinary step (MOVE, COLOR, HIST, EDIT ...), so Undo takes it back.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..commands import props_handlers as ph
from ..commands.processor import CommandError


def _text(v) -> str:
    if isinstance(v, (list, tuple)):
        return ", ".join(ph._num(x) for x in v)
    if isinstance(v, float):
        return ph._num(v)
    return str(v)


class PropsPanel(QWidget):
    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setContentsMargins(4, 2, 4, 2)
        lay.addWidget(self.title)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Property", "Value"])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(22)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                   | QAbstractItemView.AnyKeyPressed)
        self.table.itemChanged.connect(self._changed)
        lay.addWidget(self.table, 1)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #c62828;")
        lay.addWidget(self.note)
        self.target = ""  # what PROPS is given: a body ID, or "#n" for a history step
        self.data: dict | None = None
        self._filling = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self.refresh)
        win.processor.listeners.append(self._on_result)
        win.processor.history_listeners.append(self._timer.start)
        self.refresh()

    # ---- following the window --------------------------------------------------------------
    def _on_result(self, res) -> None:
        if res.pending or not res.line:
            return
        word = res.line.split(",", 1)[0].strip().upper()
        if word in ("PICK", "SEL", "CMSEL", "CLEAR"):
            self.target = ""  # a new pick: show it
        self._timer.start()

    def show_step(self, n: int) -> None:
        self.target = f"#{n}"
        self.refresh()

    def _resolve(self) -> dict | None:
        p = self.win.processor
        if self.target.startswith("#"):
            try:
                n = int(self.target[1:])
                if 1 <= n <= p.cursor:
                    return ph.step_properties(p, n)
            except (ValueError, CommandError):
                pass
            self.target = ""
        m = p.model
        bid = None
        if self.target:
            bid = int(self.target) if self.target.isdigit() and int(self.target) in m.bodies else None
        if bid is None and m.selection:
            try:
                bid = ph.body_of(p, "SEL")
            except Exception:  # noqa: BLE001 - a pick that is gone
                bid = None
        if bid is None or bid not in m.bodies:
            return None
        self.target = str(bid)
        return ph.properties(p, bid)

    def refresh(self) -> None:
        try:
            d = self._resolve()
        except Exception as exc:  # noqa: BLE001 - never let the panel break the window
            d = None
            self.note.setText(str(exc))
        self.data = d
        self._filling = True
        self.table.setRowCount(0)
        if d is None:
            self.title.setText("Pick a body (or a face of it) to see its properties here, or click a step in "
                               "History. Values in white can be changed.")
            self._filling = False
            return
        if "body" in d:
            label = d["label"] if d["label"] != str(d["body"]) else ""
            self.title.setText(f"<b>Body {d['body']}</b> {label}  <span style='color:#666'>({d['units']}; "
                               f"white values can be changed, Undo takes a change back)</span>")
        else:
            self.title.setText(f"<b>Step {d['step']}</b>: {d['label'][:80]}"
                               + (" <span style='color:#c62828'>(failed)</span>" if not d.get("ok", True) else ""))
        grey = QBrush(QColor(110, 110, 110))
        head = QBrush(QColor(232, 236, 242))
        bold = QFont()
        bold.setBold(True)
        group = None
        for r in d["rows"]:
            if r["group"] != group:
                group = r["group"]
                i = self.table.rowCount()
                self.table.insertRow(i)
                it = QTableWidgetItem(group)
                it.setFlags(Qt.ItemIsEnabled)
                it.setFont(bold)
                it.setBackground(head)
                self.table.setItem(i, 0, it)
                self.table.setSpan(i, 0, 1, 2)
            i = self.table.rowCount()
            self.table.insertRow(i)
            key = r["key"]
            shown = key.split(".", 1)[1] if r.get("step") and "." in key else key
            k = QTableWidgetItem("  " + shown)
            k.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            k.setData(Qt.UserRole, key)
            v = QTableWidgetItem(_text(r["value"]))
            v.setData(Qt.UserRole, key)
            tip = r.get("about") or ""
            if r["edit"]:
                v.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                v.setToolTip((tip + "\n" if tip else "") + f"Double-click to change it (writes {r['edit']})")
            else:
                v.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                v.setForeground(grey)
                k.setForeground(grey)
                v.setToolTip(tip or "worked out from the shape")
            self.table.setItem(i, 0, k)
            self.table.setItem(i, 1, v)
        self._filling = False

    # ---- changing a value ------------------------------------------------------------------
    def command_for(self, key: str, value: str) -> str:
        from ..lang.expr import format_value

        v = value.strip()
        quoted = format_value(v) if ("," in v or not v) else v
        return f"PROPS, {self.target}, {key}, {quoted}"

    def set_value(self, key: str, value: str):
        line = self.command_for(key, value)
        res = self.win.execute(line)
        self.note.setText("" if res.ok else res.message)
        if not res.ok:
            self.refresh()
        return res

    def _changed(self, item: QTableWidgetItem) -> None:
        if self._filling or item.column() != 1:
            return
        key = item.data(Qt.UserRole)
        if not key:
            return
        old = next((r for r in (self.data or {}).get("rows", []) if r["key"] == key), None)
        if old is not None and _text(old["value"]) == item.text().strip():
            return
        text = item.text()
        QTimer.singleShot(0, lambda: self.set_value(key, text))
