"""The model tree: a left dock listing parts, bodies, sketches, datums and sets.

It draws what gui/tree_model.py says and, like every panel, only sends
commands: a click picks (``PICK, BODY, b``), the eye hides or shows for the
view (``DISPLAY``), a double click zooms (``FIT, b``) and a right click opens
the same menu as a body in the 3D view (gui/body_menu.py). Picks made in the
3D view select the matching rows.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
)

from . import body_menu as bm
from . import tree_model as tm

# model events after which the tree is rebuilt (selection only re-syncs)
_REBUILD_ON = {"body_added", "body_removed", "cleared", "restored", "visibility", "style", "layers",
               "renamed", "sketch", "datums"}
KEY = Qt.UserRole


def _swatch(color) -> QIcon:
    pm = QPixmap(12, 12)
    r, g, b = color if color else (0.62, 0.66, 0.72)
    pm.fill(QColor.fromRgbF(r, g, b))
    return QIcon(pm)


class ModelTree(QTreeWidget):
    def __init__(self, window) -> None:
        super().__init__()
        self.win = window
        self.setColumnCount(2)
        self.setHeaderHidden(True)  # the dock title says "Model"
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemClicked.connect(self._clicked)
        self.itemDoubleClicked.connect(self._double_clicked)
        self.itemChanged.connect(self._changed)
        self._filling = False
        self._collapsed: set[str] = set()  # keys the user folded
        self.itemCollapsed.connect(lambda it: self._collapsed.add(it.data(0, KEY)))
        self.itemExpanded.connect(lambda it: self._collapsed.discard(it.data(0, KEY)))
        self._items: dict[str, QTreeWidgetItem] = {}
        self._nodes: list[tm.Node] = []
        self._pending = False
        window.processor.model.subscribe(self._on_model)
        window.processor.history_listeners.append(self.schedule)
        self.refresh()

    # ---- keeping in step with the model ------------------------------------
    def _on_model(self, ev) -> None:
        if ev.kind in _REBUILD_ON:
            self.schedule()
        elif ev.kind == "selection":
            self.sync_selection()

    def schedule(self) -> None:
        """Rebuild once the current command is done (a script sends many events)."""
        if not self._pending:
            self._pending = True
            QTimer.singleShot(0, self.refresh)

    def node(self, key: str) -> tm.Node | None:
        return tm.find(self._nodes, key)

    def item(self, key: str) -> QTreeWidgetItem | None:
        return self._items.get(key)

    def refresh(self) -> None:
        self._pending = False
        p = self.win.processor
        self._nodes = tm.tree_nodes(p)
        top = self.verticalScrollBar().value()
        self._filling = True
        try:
            self.clear()
            self._items = {}
            for n in self._nodes:
                self._add(n, None)
        finally:
            self._filling = False
        self.sync_selection()
        self.verticalScrollBar().setValue(top)

    def _add(self, n: tm.Node, parent: QTreeWidgetItem | None) -> None:
        it = QTreeWidgetItem([n.label, n.state + ("  ⚠" if n.badge else "")])
        it.setData(0, KEY, n.key)
        if n.tip:
            it.setToolTip(0, n.tip)
            it.setToolTip(1, n.tip)
        flags = Qt.ItemIsEnabled | (Qt.ItemIsSelectable if n.kind == "body" else Qt.NoItemFlags)
        if n.shown is not None:
            flags |= Qt.ItemIsUserCheckable
        it.setFlags(flags)
        if n.shown is not None:
            it.setCheckState(0, Qt.Checked if n.shown else Qt.Unchecked)
        if n.kind == "body":
            it.setIcon(0, _swatch(n.color))
            if not n.shown or "faded" in n.state:
                it.setForeground(0, QBrush(QColor(130, 130, 130)))
        if n.badge:
            it.setForeground(1, QBrush(QColor(176, 108, 0)))
        if n.kind in ("group", "part"):
            f = it.font(0)
            f.setBold(n.kind == "group")
            it.setFont(0, f)
        if parent is None:
            self.addTopLevelItem(it)
        else:
            parent.addChild(it)
        self._items[n.key] = it
        for c in n.children:
            self._add(c, it)
        # parts with many instances start folded; what the user folded stays folded
        it.setExpanded(n.key not in self._collapsed and not (n.kind == "part" and len(n.children) > 12))

    def sync_selection(self) -> None:
        """Select the rows of the bodies the model has selected."""
        m = self.win.processor.model
        want = {f"body:{b}" for b in bm.selected_bodies(m)}
        self._filling = True
        try:
            for key, it in self._items.items():
                if key.startswith("body:"):
                    it.setSelected(key in want)
            first = next((self._items[k] for k in sorted(want) if k in self._items), None)
            if first is not None:
                self.scrollToItem(first)
        finally:
            self._filling = False

    # ---- what clicks send ----------------------------------------------------
    def _clicked(self, it: QTreeWidgetItem, col: int) -> None:
        n = self.node(it.data(0, KEY))
        if n is None or n.kind != "body":
            self.sync_selection()
            return
        mods = QApplication.keyboardModifiers()
        add = bool(mods & (Qt.ControlModifier | Qt.ShiftModifier))
        self.win.execute(tm.pick_command(self.win.processor.model, n.ids[0], add))
        self.sync_selection()

    def _double_clicked(self, it: QTreeWidgetItem, col: int) -> None:
        n = self.node(it.data(0, KEY))
        if n is not None and n.ids:
            self.win.execute(f"FIT, {bm.target_text(n.ids)}")

    def _changed(self, it: QTreeWidgetItem, col: int) -> None:
        if self._filling or col != 0:
            return
        n = self.node(it.data(0, KEY))
        if n is None or n.shown is None or not n.ids:
            return
        show = it.checkState(0) == Qt.Checked
        if show != n.shown:
            self.win.execute(tm.eye_command(n, show))

    def menu_items(self, key: str) -> list:
        """The right-click menu of a row (also used by the tests)."""
        n = self.node(key)
        m = self.win.processor.model
        if n is None:
            return []
        if n.kind == "body":
            return bm.body_items(m, n.ids[0])
        if n.ids:
            head = [bm.MenuItem(n.label, enabled=False, title=True)]
            return (head + bm.view_items(m, n.ids, "these" if n.kind == "group" else "all of them")
                    + bm.everything_items(m) + [bm.SEPARATOR, bm.MenuItem("Zoom to", [f"FIT, {bm.target_text(n.ids)}"])])
        return bm.everything_items(m)

    def _menu(self, pos) -> None:
        it = self.itemAt(pos)
        items = self.menu_items(it.data(0, KEY)) if it is not None else bm.everything_items(self.win.processor.model)
        if not items:
            return
        menu = QMenu(self)
        self.win.fill_menu(menu, items)
        self._last_menu = menu
        menu.popup(self.viewport().mapToGlobal(pos))
