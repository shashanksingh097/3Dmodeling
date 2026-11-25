"""View > Materials…: the material library every project shares (core/matlib.py).

A table of every material the model knows: density, stiffness, strength, heat values, how it
renders and its colour, and where it comes from (built in, the library, this project). Editing a
cell writes it to the library with MATLIB, SET, so the change counts for every project from now
on; New adds a material, Delete takes a library one out again, and Give to selection runs
MATERIAL on the selected bodies. Everything goes through commands, so the command line shows
what each click did.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import matlib
from ..core.model import MATERIALS

# column: (heading, JSON field, Material attribute, tooltip)
COLUMNS = (
    ("Name", "", "name", "the material's name, as MATERIAL takes it"),
    ("Density\nkg/m³", "density", "density", "mass per volume: MASSPROP's mass"),
    ("Stiffness E\nMPa", "E_MPa", "E", "Young's modulus: how much it bends (STRESS)"),
    ("Poisson\nν", "poisson", "nu", "how much it narrows as it stretches (STRESS)"),
    ("Yield\nMPa", "yield_MPa", "yield_", "the stress where it starts to bend for good (STRESS's safety factor)"),
    ("Conduction\nW/(m·K)", "conductivity", "k", "how well it carries heat"),
    ("Expansion\nµm/(m·K)", "expansion", "cte", "how much it grows per degree"),
    ("Specific heat\nJ/(kg·K)", "specific_heat", "cp", "the heat it takes to warm a kilogram by a degree"),
    ("Up to\n°C", "max_temp_C", "tmax", "the highest temperature it is used at"),
    ("Render look", "look", "look", "how RENDER draws it (metal, plastic, glass ...)"),
    ("Colour", "color", "color", "the colour bodies of this material are drawn in"),
    ("From", "", "", "built in, the material library (every project), or this project only"),
    ("Note", "note", "note", "a grade or supplier"),
)
_NUM = {i for i, c in enumerate(COLUMNS) if c[1] in dict(matlib.FIELDS)}
LOOK_COL = 9
COLOR_COL = 10
FROM_COL = 11
NOTE_COL = 12


def _num(v) -> str:
    if v is None:
        return ""
    return f"{v:g}"


class MaterialsDialog(QDialog):
    def __init__(self, win: QWidget) -> None:
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Materials")
        self.resize(1180, 560)
        self._filling = False
        lay = QVBoxLayout(self)
        intro = QLabel(
            "The material library is shared by every project on this computer. Change a value and it is "
            "kept in the library (MATLIB, SET): MASSPROP, STRESS and RENDER use it from then on. A saved "
            "project keeps a copy of the library materials it uses, so it opens the same elsewhere.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in COLUMNS])
        for i, c in enumerate(COLUMNS):
            self.table.horizontalHeaderItem(i).setToolTip(c[3])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._edited)
        self.table.cellDoubleClicked.connect(self._double)
        lay.addWidget(self.table, 1)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        self.new_button = QPushButton("New material…")
        self.new_button.setToolTip("Add a material to the library: its name and density, then fill in the rest")
        self.new_button.clicked.connect(self.new_material)
        self.delete_button = QPushButton("Delete from library")
        self.delete_button.setToolTip("Take the material out of the library (a built-in one goes back to "
                                      "its built-in values)")
        self.delete_button.clicked.connect(self.delete_material)
        self.keep_button = QPushButton("Keep in library")
        self.keep_button.setToolTip("Copy a material this project made (MATERIAL, NEW) into the library")
        self.keep_button.clicked.connect(self.keep_material)
        self.give_button = QPushButton("Give to selection")
        self.give_button.setToolTip("MATERIAL, SEL, name: the selected bodies are made of this material")
        self.give_button.clicked.connect(self.give)
        self.folder_button = QPushButton("Open library folder")
        self.folder_button.setToolTip(matlib.path())
        self.folder_button.clicked.connect(self.open_folder)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        for b in (self.new_button, self.delete_button, self.keep_button, self.give_button, self.folder_button):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        self.table.itemSelectionChanged.connect(self._buttons)
        self.fill()

    # ---- the table ----------------------------------------------------------------------------
    def _p(self):
        return self.win.processor

    def fill(self, keep: str = "") -> None:
        from ..commands.matlib_handlers import source

        p = self._p()
        self._filling = True
        try:
            mats = sorted(p.model.materials.items(), key=lambda kv: (kv[0] not in MATERIALS, kv[0]))
            self.table.setRowCount(len(mats))
            for r, (key, mat) in enumerate(mats):
                for c, (_, field, attr, _tip) in enumerate(COLUMNS):
                    if c == LOOK_COL:
                        combo = QComboBox()
                        combo.addItems(["(from colour)", *[x.lower().replace("_", " ") for x in matlib.LOOKS]])
                        combo.setCurrentIndex(matlib.LOOKS.index(mat.look) + 1 if mat.look in matlib.LOOKS else 0)
                        combo.currentIndexChanged.connect(lambda i, k=key: self._look(k, i))
                        self.table.setCellWidget(r, c, combo)
                        continue
                    if c == COLOR_COL:
                        it = QTableWidgetItem("")
                        if mat.color is not None:
                            it.setBackground(QColor.fromRgbF(*mat.color))
                        it.setToolTip("double-click to pick a colour")
                        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    elif c == FROM_COL:
                        it = QTableWidgetItem(source(p, key))
                        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    elif c == 0:
                        it = QTableWidgetItem(key)
                        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    elif c == NOTE_COL:
                        it = QTableWidgetItem(mat.note)
                    else:
                        it = QTableWidgetItem(_num(getattr(mat, attr)))
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    it.setData(Qt.UserRole, key)
                    self.table.setItem(r, c, it)
                if key == keep:
                    self.table.selectRow(r)
            self.table.resizeColumnsToContents()
            self.table.setColumnWidth(COLOR_COL, 60)
            self.table.setColumnWidth(FROM_COL, min(self.table.columnWidth(FROM_COL), 230))
            err = matlib.problem()
            self.status.setText(f"Library file: {matlib.path()}" + (f" — {err}" if err else ""))
        finally:
            self._filling = False
        self._buttons()

    def _key(self) -> str:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return ""
        it = self.table.item(rows[0].row(), 0)
        return it.text() if it else ""

    def _buttons(self) -> None:
        from ..commands.matlib_handlers import source

        key = self._key()
        src = source(self._p(), key) if key else ""
        self.delete_button.setEnabled(src.startswith("library"))
        self.keep_button.setEnabled(src.startswith("this project") or src.startswith("kept"))
        self.give_button.setEnabled(bool(key))

    def _run(self, text: str) -> bool:
        res = self.win.execute(text)
        ok = bool(getattr(res, "ok", False))
        msg = getattr(res, "message", "") or ""
        self.status.setText(msg.splitlines()[0] if msg else "")
        return ok

    def _set(self, key: str, words: str) -> None:
        self._run(f"MATLIB, SET, {key}, {words}")
        self.fill(keep=key)

    # ---- edits --------------------------------------------------------------------------------
    def _edited(self, it: QTableWidgetItem) -> None:
        if self._filling:
            return
        c = it.column()
        key = it.data(Qt.UserRole)
        field = COLUMNS[c][1]
        if not key or not field:
            return
        text = it.text().strip()
        if c == NOTE_COL:
            safe = text.replace('"', "'")
            self._set(key, f'note="{safe}"')
            return
        if c in _NUM:
            if text:
                try:
                    float(text)
                except ValueError:
                    self.status.setText(f"{COLUMNS[c][0].splitlines()[0]}: {text!r} is not a number")
                    self.fill(keep=key)
                    return
            self._set(key, f"{field}={text or 'NONE'}")

    def _look(self, key: str, i: int) -> None:
        if self._filling:
            return
        look = matlib.LOOKS[i - 1] if i > 0 else ""
        self._set(key, f"look={look}" if look else 'look=""')

    def _double(self, r: int, c: int) -> None:
        if c != COLOR_COL:
            return
        key = self.table.item(r, 0).text()
        mat = self._p().model.materials.get(key)
        start = QColor.fromRgbF(*mat.color) if mat is not None and mat.color is not None else QColor(200, 200, 200)
        col = QColorDialog.getColor(start, self, f"Colour of {key}")
        if col.isValid():
            self._set(key, f"color={col.name()}")

    # ---- buttons ------------------------------------------------------------------------------
    def new_material(self) -> None:
        name, ok = QInputDialog.getText(self, "New material", "Name (letters, digits, _):")
        if not ok or not name.strip():
            return
        key = name.strip().upper()
        dens, ok = QInputDialog.getDouble(self, "New material", f"Density of {key} (kg/m³):", 1000, 0.001, 100000, 1)
        if not ok:
            return
        self._set(key, f"density={dens:g}")

    def delete_material(self) -> None:
        key = self._key()
        if key:
            self._run(f"MATLIB, DELETE, {key}")
            self.fill(keep=key)

    def keep_material(self) -> None:
        key = self._key()
        if key:
            self._run(f"MATLIB, KEEP, {key}")
            self.fill(keep=key)

    def give(self) -> None:
        key = self._key()
        if key:
            self._run(f"MATERIAL, SEL, {key}")
            self.fill(keep=key)

    def open_folder(self) -> None:
        folder = os.path.dirname(matlib.path())
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))


def open_dialog(win) -> MaterialsDialog:
    dlg = getattr(win, "materials_dialog", None)
    if dlg is None:
        dlg = MaterialsDialog(win)
        win.materials_dialog = dlg
    else:
        dlg.fill()
    dlg.show()
    dlg.raise_()
    return dlg
