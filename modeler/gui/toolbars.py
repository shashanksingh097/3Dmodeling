"""Toolbars in labelled groups, each button with its icon and its name.

A group is one QToolBar whose first item is its name in small grey text
(Shapes, Booleans, Features ...), so the window reads like a ribbon without
being one: groups can still be moved, wrapped or hidden like any toolbar.
How buttons show (icons with names under or beside them, icons only, names
only) is one setting for every group, kept between sessions.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QLabel, QToolBar

from . import icons

SETTING = "toolbarButtons"
DEFAULT_STYLE = "under"


def group(win, title: str, name: str, area=Qt.TopToolBarArea) -> QToolBar:
    """A new labelled toolbar group."""
    tb = QToolBar(title, win)
    tb.setObjectName(name)
    tb.setProperty("group", True)
    label = QLabel(title)
    label.setObjectName("groupLabel")
    label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
    f = label.font()
    f.setPointSizeF(max(6.5, f.pointSizeF() * 0.8))
    label.setFont(f)
    label.setEnabled(False)  # drawn in the theme's quiet colour
    label.setContentsMargins(4, 0, 6, 0)
    tb.addWidget(label)
    tb.setToolButtonStyle(icons.STYLES[current_style(win)])
    tb.setIconSize(QSize(22, 22))
    win.addToolBar(area, tb)
    groups(win).append(tb)
    return tb


def groups(win) -> list[QToolBar]:
    if not hasattr(win, "_toolbar_groups"):
        win._toolbar_groups = []
    return win._toolbar_groups


def action(win, tb: QToolBar, label: str, icon: str, tip: str, slot=None, shortcut=None,
           checkable: bool = False) -> QAction:
    """A button with an icon and its name; the tooltip says what it runs."""
    a = QAction(icons.icon(icon), label, win)
    a.setIconText(label.rstrip("…"))
    a.setToolTip(tip)
    a.setProperty("icon_name", icon)
    if shortcut:
        a.setShortcut(QKeySequence(shortcut))
    a.setCheckable(checkable)
    if slot is not None:
        a.triggered.connect(slot)
    tb.addAction(a)
    return a


def current_style(win) -> str:
    shell = getattr(win, "shell", None)
    settings = getattr(shell, "settings", None)
    value = settings.value(SETTING, DEFAULT_STYLE) if settings is not None else DEFAULT_STYLE
    return value if value in icons.STYLES else DEFAULT_STYLE


def set_style(win, key: str) -> None:
    """Show every group's buttons as ``key`` (see icons.STYLES) and remember it."""
    if key not in icons.STYLES:
        raise ValueError(key)
    for tb in groups(win):
        tb.setToolButtonStyle(icons.STYLES[key])
    shell = getattr(win, "shell", None)
    if getattr(shell, "settings", None) is not None:
        shell.settings.setValue(SETTING, key)
    acts = getattr(win, "_style_actions", {})
    if key in acts:
        acts[key].setChecked(True)


def style_menu(win, menu) -> None:
    """Toolbar buttons: icons and names / icons only / names only."""
    sub = menu.addMenu("Toolbar &buttons")
    grp = QActionGroup(win)
    grp.setExclusive(True)
    win._style_actions = {}
    now = current_style(win)
    for key, text in icons.STYLE_LABELS.items():
        a = sub.addAction(text)
        a.setCheckable(True)
        a.setChecked(key == now)
        a.triggered.connect(lambda _=False, k=key: set_style(win, k))
        grp.addAction(a)
        win._style_actions[key] = a
    for tb in groups(win):
        tb.setToolButtonStyle(icons.STYLES[now])


def bars_menu(win, menu) -> None:
    """Show or hide each toolbar group (the sketch groups come and go with sketch mode)."""
    sub = menu.addMenu("&Toolbars")
    for tb in groups(win):
        if tb.property("sketch"):
            continue
        sub.addAction(tb.toggleViewAction())
