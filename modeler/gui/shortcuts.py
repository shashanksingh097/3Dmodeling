"""Keyboard shortcuts of one's own (PLAN item 75): any menu item or toolbar button, and the
fill-in form of any command, can get a key; kept in the settings and put back at start.

Every action in the window is found by its place and text ("File / Save", "View toolbar / Fit"), so a
shortcut survives a new version of the app as long as the button keeps its name. Forms get an
action of their own ("Form / BLOCK") the first time a key is given to one.
"""

from __future__ import annotations

import json

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
                               QKeySequenceEdit, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

SETTING = "shortcuts"  # JSON: action id -> key sequence text ("" takes the key away)
FORM_PREFIX = "Form / "


def _clean(text: str) -> str:
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&").replace("…", "").strip()


def _place(a: QAction) -> str:
    """Where an action lives: its menu ('File'), else its toolbar ('File toolbar'), else 'Window'."""
    from PySide6.QtWidgets import QMenu, QToolBar

    objs = a.associatedObjects()
    for w in objs:
        if isinstance(w, QMenu) and _clean(w.title()):
            return _clean(w.title())
    for w in objs:
        if isinstance(w, QToolBar) and _clean(w.windowTitle()):
            return _clean(w.windowTitle()) + " toolbar"
    return "Window"


def actions(win) -> dict[str, QAction]:
    """Every action a shortcut can go on, by id ('Place / Text'), in a stable order."""
    out: dict[str, QAction] = {}
    for a in win.findChildren(QAction):
        if a.isSeparator() or a.menu() is not None or not _clean(a.text()):
            continue
        key = a.property("shortcut_id") or f"{_place(a)} / {_clean(a.text())}"
        if key not in out:
            out[str(key)] = a
            if a.property("default_shortcut") is None:  # remember the app's own key once
                a.setProperty("default_shortcut", a.shortcut().toString())
    return dict(sorted(out.items(), key=lambda kv: kv[0].lower()))


def form_actions(win) -> dict[str, str]:
    """'Form / NAME' -> the command, for every command that has a form."""
    from . import forms as F

    return {f"{FORM_PREFIX}{n}": n for n in sorted(F.specs())}


def _form_action(win, cmd: str) -> QAction:
    key = f"{FORM_PREFIX}{cmd}"
    for a in win.findChildren(QAction):
        if a.property("shortcut_id") == key:
            return a
    from . import form_dialog as fd

    a = QAction(f"{cmd} form", win)
    a.setProperty("shortcut_id", key)
    a.setProperty("default_shortcut", "")
    a.triggered.connect(lambda _=False, c=cmd: fd.open_form(win, c))
    win.addAction(a)  # a window action: its key works wherever the focus is
    return a


def saved(win) -> dict[str, str]:
    s = getattr(getattr(win, "shell", None), "settings", None)
    raw = s.value(SETTING, "") if s is not None else ""
    try:
        got = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}
    return {str(k): str(v) for k, v in got.items()} if isinstance(got, dict) else {}


def save(win, mapping: dict[str, str]) -> None:
    s = getattr(getattr(win, "shell", None), "settings", None)
    if s is not None:
        s.setValue(SETTING, json.dumps(mapping, sort_keys=True))


def apply(win, mapping: dict[str, str] | None = None) -> list[str]:
    """Put the user's keys on the actions (the saved ones by default). Returns the ids not found."""
    mapping = saved(win) if mapping is None else mapping
    acts = actions(win)
    missing = []
    for key, seq in mapping.items():
        a = acts.get(key)
        if a is None and key.startswith(FORM_PREFIX):
            cmd = key[len(FORM_PREFIX):]
            if seq and cmd in form_actions(win).values():
                a = _form_action(win, cmd)
        if a is None:
            missing.append(key)
            continue
        a.setShortcut(QKeySequence(seq))
    return missing


def current(win) -> dict[str, str]:
    """Every action's key as it is now: id -> key text ('' for none)."""
    out = {k: a.shortcut().toString() for k, a in actions(win).items()}
    for k in form_actions(win):
        out.setdefault(k, "")
    return out


def _context(action_id: str) -> str:
    """Sketch tools have keys of their own while a sketch is open, so they only clash with each other."""
    return "sketch" if action_id.startswith("Sketch ") else "window"


def conflicts(mapping: dict[str, str]) -> dict[str, list[str]]:
    """Keys given to more than one action at the same time: key -> the ids."""
    by_key: dict[tuple[str, str], list[str]] = {}
    for k, seq in mapping.items():
        if seq:
            by_key.setdefault((_context(k), seq), []).append(k)
    return {seq: ids for (_ctx, seq), ids in by_key.items() if len(ids) > 1}


def set_key(win, action_id: str, seq: str) -> None:
    """Give one action a key (or '' for none) and keep it."""
    mapping = saved(win)
    a = actions(win).get(action_id)
    default = str(a.property("default_shortcut") or "") if a is not None else ""
    if seq == default:
        mapping.pop(action_id, None)  # the app's own key: nothing to keep
    else:
        mapping[action_id] = seq
    save(win, mapping)
    apply(win, {action_id: seq})


def reset(win) -> None:
    """Every action back to the app's own key."""
    for a in actions(win).values():
        a.setShortcut(QKeySequence(str(a.property("default_shortcut") or "")))
    save(win, {})


class ShortcutDialog(QDialog):
    """A table of every action and form with its key; pick a row, press the new key."""

    def __init__(self, win) -> None:
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Keyboard shortcuts")
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Find an action or command…")
        self.filter.textChanged.connect(self._filter)
        lay.addWidget(self.filter)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Action", "Shortcut"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._picked)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("New shortcut:"))
        self.keys = QKeySequenceEdit()
        self.keys.editingFinished.connect(self._set)
        row.addWidget(self.keys, 1)
        clear = QPushButton("None")
        clear.setToolTip("Take the key off the picked action")
        clear.clicked.connect(lambda: self._set(""))
        row.addWidget(clear)
        default = QPushButton("App's own")
        default.setToolTip("Put back the key the app gives the picked action")
        default.clicked.connect(self._default)
        row.addWidget(default)
        lay.addLayout(row)
        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        lay.addWidget(self.warning)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        reset_all = box.addButton("Reset all", QDialogButtonBox.ResetRole)
        reset_all.clicked.connect(self._reset)
        box.rejected.connect(self.accept)
        lay.addWidget(box)
        self._fill()

    def _fill(self) -> None:
        keys = current(self.win)
        self.table.setRowCount(len(keys))
        for r, (k, seq) in enumerate(keys.items()):
            self.table.setItem(r, 0, QTableWidgetItem(k))
            self.table.setItem(r, 1, QTableWidgetItem(QKeySequence(seq).toString(QKeySequence.NativeText)))
        self._filter(self.filter.text())
        clash = conflicts(keys)
        self.warning.setText("" if not clash else "Used twice: " + "; ".join(
            f"{QKeySequence(s).toString(QKeySequence.NativeText)} ({', '.join(ids)})" for s, ids in clash.items()))

    def _filter(self, text: str) -> None:
        t = text.strip().lower()
        for r in range(self.table.rowCount()):
            self.table.setRowHidden(r, bool(t) and t not in self.table.item(r, 0).text().lower())

    def _row_id(self) -> str:
        rows = self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(), 0).text() if rows else ""

    def _picked(self) -> None:
        key = self._row_id()
        self.keys.setKeySequence(QKeySequence(current(self.win).get(key, "")))

    def _set(self, seq: str | None = None) -> None:
        key = self._row_id()
        if not key:
            return
        text = self.keys.keySequence().toString() if seq is None else seq
        set_key(self.win, key, text)
        self._refresh(key)

    def _default(self) -> None:
        key = self._row_id()
        a = actions(self.win).get(key)
        self._set(str(a.property("default_shortcut") or "") if a is not None else "")

    def _reset(self) -> None:
        reset(self.win)
        self._fill()

    def _refresh(self, key: str) -> None:
        self._fill()
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).text() == key:
                self.table.selectRow(r)
                break


def open_dialog(win) -> ShortcutDialog:
    dlg = ShortcutDialog(win)
    dlg.show()
    return dlg
