"""The ribbon: toolbar groups on tabs, each button with its icon and its name.

All the buttons sit in one row of tabs at the top of the window (Home,
Model, Features, Freeform, Inspect, and the sketch tabs while a sketch is
open), so they take the height of one toolbar instead of several rows.
Each tab holds a few groups side by side; a group is one QToolBar with its
name in small grey text under it (File, Edit, Shapes, Booleans ...).

A small quick-access bar at the right of the tabs keeps Undo, Redo, the pick
modes and Fit in reach whichever tab is open. Double-click a tab (or use
View > Collapse ribbon) to fold the ribbon to its tab names; click a tab to
use it and it folds away again.

How buttons show (icons with names under or beside them, icons only, names
only) is one setting for every group, kept between sessions, and so is the
tab that was open last.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QTabWidget, QToolBar, QVBoxLayout,
                               QWidget)

from . import icons

SETTING = "toolbarButtons"
TAB_SETTING = "ribbonTab"
COLLAPSED_SETTING = "ribbonCollapsed"
DEFAULT_STYLE = "under"


# ---- the ribbon -----------------------------------------------------------------------------
class Ribbon(QTabWidget):
    """Tabs of toolbar groups. ``page(title)`` makes or finds a tab."""

    def __init__(self, win) -> None:
        super().__init__(win)
        self.win = win
        self.setObjectName("ribbon")
        self.setDocumentMode(True)
        self.setUsesScrollButtons(True)
        self.pages: dict[str, QWidget] = {}
        self.collapsed = False
        self._peek = False  # unfolded for one use while collapsed
        self.tabBarDoubleClicked.connect(lambda _i: self.set_collapsed(not self.collapsed))
        self.tabBarClicked.connect(self._clicked)
        self.currentChanged.connect(self._remember)

    def page(self, title: str) -> QWidget:
        if title not in self.pages:
            w = QWidget()
            w.setObjectName("ribbon_" + title.lower().replace(" ", "_"))
            lay = QHBoxLayout(w)
            lay.setContentsMargins(2, 2, 2, 0)
            lay.setSpacing(2)
            lay.addStretch(1)
            self.pages[title] = w
            self.addTab(w, title)
        return self.pages[title]

    def add_group(self, title: str, tb: QToolBar) -> QWidget:
        """A group on tab ``title``: the toolbar, its name under it, a thin line after it."""
        page = self.page(title)
        lay: QHBoxLayout = page.layout()
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(tb, 1)
        v.addWidget(tb.property("label_widget"), 0, Qt.AlignHCenter)
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        at = lay.count() - 1  # before the stretch
        lay.insertWidget(at, box)
        lay.insertWidget(at + 1, line)
        tb._ribbon_box = box
        return box

    def tab_index(self, title: str) -> int:
        page = self.pages.get(title)
        return self.indexOf(page) if page is not None else -1

    def show_tab(self, title: str, on: bool, select: bool = False) -> None:
        i = self.tab_index(title)
        if i < 0:
            return
        self.setTabVisible(i, on)
        if on and select:
            self.setCurrentIndex(i)

    def select(self, title: str) -> None:
        i = self.tab_index(title)
        if i >= 0 and self.isTabVisible(i):
            self.setCurrentIndex(i)

    def current_title(self) -> str:
        return self.tabText(self.currentIndex())

    def visible_titles(self) -> list[str]:
        return [self.tabText(i) for i in range(self.count()) if self.isTabVisible(i)]

    # folding the ribbon to its tab names
    def set_collapsed(self, on: bool) -> None:
        self.collapsed = bool(on)
        self._peek = False
        self._fold(self.collapsed)
        settings = _settings(self.win)
        if settings is not None:
            settings.setValue(COLLAPSED_SETTING, self.collapsed)
        act = getattr(self.win, "collapse_ribbon_action", None)
        if act is not None and act.isChecked() != self.collapsed:
            act.setChecked(self.collapsed)

    def _fold(self, fold: bool) -> None:
        for i in range(self.count()):
            self.widget(i).setVisible(not fold)
        self.setMaximumHeight(self.tabBar().sizeHint().height() + 2 if fold else 16777215)

    def _clicked(self, _i: int) -> None:
        if self.collapsed:  # unfold for this one use; folds again after a button is pressed
            self._peek = True
            self._fold(False)

    def fold_after_use(self) -> None:
        if self.collapsed and self._peek:
            self._peek = False
            self._fold(True)

    def _remember(self, i: int) -> None:
        settings = _settings(self.win)
        if settings is not None and i >= 0 and self.tabText(i) and not self.widget(i).property("sketch"):
            settings.setValue(TAB_SETTING, self.tabText(i))


def ribbon(win) -> Ribbon:
    """The window's ribbon, made the first time (in a fixed toolbar at the top)."""
    rb = getattr(win, "ribbon", None)
    if rb is None:
        holder = QToolBar("Ribbon", win)
        holder.setObjectName("ribbon_bar")
        holder.setMovable(False)
        holder.setFloatable(False)
        holder.toggleViewAction().setVisible(False)
        rb = Ribbon(win)
        holder.addWidget(rb)
        win.addToolBar(Qt.TopToolBarArea, holder)
        win.ribbon = rb
        win.ribbon_bar = holder
    return rb


def quick_access(win, actions: list) -> QToolBar:
    """Icons that stay in reach on every tab, at the right of the tab names."""
    rb = ribbon(win)
    tb = QToolBar("Quick access", rb)
    tb.setObjectName("quick_access")
    tb.setIconSize(QSize(18, 18))
    tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
    for a in actions:
        if a is None:
            tb.addSeparator()
        else:
            tb.addAction(a)
    rb.setCornerWidget(tb, Qt.TopRightCorner)
    win.quick_access = tb
    return tb


def group(win, title: str, name: str, tab: str = "Home", sketch: bool = False) -> QToolBar:
    """A new labelled toolbar group on ribbon tab ``tab``."""
    rb = ribbon(win)
    tb = QToolBar(title, win)
    tb.setObjectName(name)
    tb.setProperty("group", True)
    tb.setProperty("tab", tab)
    if sketch:
        tb.setProperty("sketch", True)
    label = QLabel(title)
    label.setObjectName("groupLabel")
    f = label.font()
    f.setPointSizeF(max(6.5, f.pointSizeF() * 0.8))
    label.setFont(f)
    label.setEnabled(False)  # drawn in the theme's quiet colour
    tb.setProperty("label_widget", label)
    tb.setToolButtonStyle(icons.STYLES[current_style(win)])
    tb.setIconSize(QSize(22, 22))
    rb.add_group(tab, tb)
    if sketch:
        rb.pages[tab].setProperty("sketch", True)
    tb.actionTriggered.connect(lambda _a: rb.fold_after_use())
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


def _settings(win):
    return getattr(getattr(win, "shell", None), "settings", None)


def current_style(win) -> str:
    settings = _settings(win)
    value = settings.value(SETTING, DEFAULT_STYLE) if settings is not None else DEFAULT_STYLE
    return value if value in icons.STYLES else DEFAULT_STYLE


def set_style(win, key: str) -> None:
    """Show every group's buttons as ``key`` (see icons.STYLES) and remember it."""
    if key not in icons.STYLES:
        raise ValueError(key)
    for tb in groups(win):
        tb.setToolButtonStyle(icons.STYLES[key])
    settings = _settings(win)
    if settings is not None:
        settings.setValue(SETTING, key)
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


def ribbon_menu(win, menu) -> None:
    """View > Collapse ribbon, and View > Ribbon tab > (each tab) to jump to one."""
    rb = ribbon(win)
    a = menu.addAction("&Collapse ribbon")
    a.setCheckable(True)
    a.setToolTip("Fold the ribbon to its tab names (double-click a tab does the same)")
    a.toggled.connect(lambda on: rb.set_collapsed(on) if rb.collapsed != on else None)
    win.collapse_ribbon_action = a
    sub = menu.addMenu("Ribbon &tab")
    sub.aboutToShow.connect(lambda: _fill_tabs(sub, rb))


def _fill_tabs(sub, rb: Ribbon) -> None:
    sub.clear()
    for t in rb.visible_titles():
        act = sub.addAction(t, lambda t=t: rb.select(t))
        act.setCheckable(True)
        act.setChecked(t == rb.current_title())


def restore(win) -> None:
    """Open the tab used last, and fold the ribbon if it was folded."""
    rb = ribbon(win)
    settings = _settings(win)
    if settings is None:
        return
    t = settings.value(TAB_SETTING, "")
    if t:
        rb.select(str(t))
    if str(settings.value(COLLAPSED_SETTING, False)).lower() in ("true", "1"):
        rb.set_collapsed(True)
