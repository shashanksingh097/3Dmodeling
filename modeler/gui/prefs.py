"""Preferences: the window's theme (light, dark or the system's), the 3D
view's background and how toolbar buttons show, and which plug-ins are on
(modeler/plugins.py). Kept in the app's settings and put back when the app
starts.

The light and dark themes use Qt's Fusion style with a palette of their
own, so they look the same on every system; "system" leaves the style and
palette the platform gave. The toolbar icons are drawn from the palette
(gui/icons.py), so they are drawn again when the theme changes.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from . import icons
from ..viewport.occ_view import BACKGROUNDS

THEME_SETTING = "theme"
BACKGROUND_SETTING = "viewBackground"
PLUGINS_OFF_SETTING = "pluginsOff"
THEMES = {"system": "The system's", "light": "Light", "dark": "Dark"}
BACKGROUND_LABELS = {"grey": "Grey (default)", "dark": "Dark", "light": "Light", "white": "White"}

_system: dict = {}  # the style and palette the app started with


def _palette(dark: bool) -> QPalette:
    pal = QPalette()
    if dark:
        base, window, text, mid = QColor(32, 34, 38), QColor(45, 48, 53), QColor(225, 228, 232), QColor(70, 74, 80)
        hl, link = QColor(42, 110, 200), QColor(106, 168, 255)
    else:
        base, window, text, mid = QColor(255, 255, 255), QColor(240, 241, 243), QColor(25, 27, 30), QColor(200, 203, 208)
        hl, link = QColor(31, 111, 209), QColor(31, 111, 209)
    for group in (QPalette.Active, QPalette.Inactive):
        pal.setColor(group, QPalette.Window, window)
        pal.setColor(group, QPalette.WindowText, text)
        pal.setColor(group, QPalette.Base, base)
        pal.setColor(group, QPalette.AlternateBase, window)
        pal.setColor(group, QPalette.Text, text)
        pal.setColor(group, QPalette.Button, window)
        pal.setColor(group, QPalette.ButtonText, text)
        pal.setColor(group, QPalette.ToolTipBase, base)
        pal.setColor(group, QPalette.ToolTipText, text)
        pal.setColor(group, QPalette.PlaceholderText, mid.darker(130) if not dark else mid.lighter(150))
        pal.setColor(group, QPalette.Highlight, hl)
        pal.setColor(group, QPalette.HighlightedText, QColor(255, 255, 255))
        pal.setColor(group, QPalette.Link, link)
        pal.setColor(group, QPalette.Mid, mid)
        pal.setColor(group, QPalette.Light, window.lighter(130))
        pal.setColor(group, QPalette.Dark, window.darker(160))
    grey = QColor(120, 124, 130) if dark else QColor(150, 152, 156)
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, grey)
    pal.setColor(QPalette.Disabled, QPalette.Window, window)
    pal.setColor(QPalette.Disabled, QPalette.Base, base)
    pal.setColor(QPalette.Disabled, QPalette.Button, window)
    return pal


def _settings(win):
    return getattr(getattr(win, "shell", None), "settings", None)


def current(win, key: str, default: str) -> str:
    s = _settings(win)
    return str(s.value(key, default)) if s is not None else default


def apply_theme(win, name: str, remember: bool = True) -> None:
    """Switch the whole app to theme ``name`` (one of THEMES)."""
    if name not in THEMES:
        raise ValueError(name)
    app = QApplication.instance()
    if not _system:
        _system["style"] = app.style().name()
        _system["palette"] = QPalette(app.palette())
    if name == "system":
        app.setStyle(_system["style"])
        app.setPalette(_system["palette"])
    else:
        app.setStyle("Fusion")
        app.setPalette(_palette(name == "dark"))
    refresh_icons(win)
    if remember and _settings(win) is not None:
        _settings(win).setValue(THEME_SETTING, name)


def refresh_icons(win) -> None:
    """Draw every toolbar icon again in the current palette."""
    from PySide6.QtGui import QAction

    for a in win.findChildren(QAction):
        name = a.property("icon_name")
        if name:
            a.setIcon(icons.icon(str(name)))


def apply_background(win, name: str, remember: bool = True) -> None:
    win.viewport.set_background(name)
    if remember and _settings(win) is not None:
        _settings(win).setValue(BACKGROUND_SETTING, name)


def restore(win) -> None:
    """Put back the theme and background from the settings (at start)."""
    theme = current(win, THEME_SETTING, "system")
    if theme in THEMES and theme != "system":
        apply_theme(win, theme, remember=False)
    bg = current(win, BACKGROUND_SETTING, "grey")
    if bg in BACKGROUNDS:
        win.viewport.set_background(bg)


def plugins_off(win) -> list[str]:
    s = _settings(win)
    raw = s.value(PLUGINS_OFF_SETTING, []) if s is not None else []
    if isinstance(raw, str):
        raw = [raw] if raw else []
    return [str(x) for x in (raw or [])]


def load_plugins(win) -> None:
    """Read the turned-on plug-ins (at start, and after a change in Preferences) and put their
    commands in the Commands menu. A plug-in that does not load is named in the status bar."""
    from .. import plugins
    from . import form_dialog as fd

    plugins.configure(plugins_off(win))
    found = plugins.load_all()
    menu = getattr(win, "commands_menu", None)
    if menu is not None:
        fd.command_menu(win, menu)
    bad = [pl.name for pl in found if pl.problem]
    if bad:
        win.statusBar().showMessage(f"Plug-in{'s' if len(bad) != 1 else ''} not loaded: {', '.join(bad)} "
                                    "(Preferences > Plug-ins says why)", 10000)


class PreferencesDialog(QDialog):
    """Theme, 3D view background and toolbar buttons; each applies at once. Plug-ins on a tab
    of their own."""

    def __init__(self, win) -> None:
        super().__init__(win)
        from . import toolbars as tbs

        self.win = win
        self.setWindowTitle("Preferences")
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)
        look = QWidget()
        lay = QVBoxLayout(look)
        form = QFormLayout()
        self.theme = QComboBox()
        for key, text in THEMES.items():
            self.theme.addItem(text, key)
        self.theme.setCurrentIndex(list(THEMES).index(current(win, THEME_SETTING, "system")
                                                      if current(win, THEME_SETTING, "system") in THEMES
                                                      else "system"))
        self.theme.currentIndexChanged.connect(lambda _: apply_theme(win, self.theme.currentData()))
        form.addRow("Theme:", self.theme)
        self.background = QComboBox()
        for key, text in BACKGROUND_LABELS.items():
            self.background.addItem(text, key)
        self.background.setCurrentIndex(list(BACKGROUND_LABELS).index(win.viewport.background
                                                                      if win.viewport.background in BACKGROUND_LABELS
                                                                      else "grey"))
        self.background.currentIndexChanged.connect(lambda _: apply_background(win, self.background.currentData()))
        form.addRow("3D view background:", self.background)
        self.buttons = QComboBox()
        for key, text in icons.STYLE_LABELS.items():
            self.buttons.addItem(text, key)
        self.buttons.setCurrentIndex(list(icons.STYLE_LABELS).index(tbs.current_style(win)))
        self.buttons.currentIndexChanged.connect(lambda _: tbs.set_style(win, self.buttons.currentData()))
        form.addRow("Toolbar buttons:", self.buttons)
        lay.addLayout(form)
        note = QLabel("Changes apply at once and are kept for next time.")
        note.setEnabled(False)
        lay.addWidget(note)
        lay.addStretch(1)
        self.tabs.addTab(look, "Look")
        self.tabs.addTab(self._plugins_tab(), "Plug-ins")
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.accept)
        box.accepted.connect(self.accept)
        outer.addWidget(box)

    # ---- plug-ins ----
    def _plugins_tab(self) -> QWidget:
        from .. import plugins

        page = QWidget()
        lay = QVBoxLayout(page)
        intro = QLabel("Plug-ins are your own commands, written in Python, one file each in the plug-in folder. "
                       "Each command gets a form, a help page and a guide for the assistant. Tick to turn one on. "
                       "Only add files you trust: a plug-in runs with the app's rights.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.plugin_list = QListWidget()
        self.plugin_list.itemChanged.connect(self._plugin_toggled)
        lay.addWidget(self.plugin_list, 1)
        self.plugin_folder = QLabel(plugins.folder())
        self.plugin_folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.plugin_folder.setWordWrap(True)
        lay.addWidget(self.plugin_folder)
        row = QHBoxLayout()
        for text, slot in (("Open the folder", self._open_folder), ("Add the example", self._add_example),
                           ("Reload", self._reload)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self._fill_plugins()
        return page

    def _fill_plugins(self) -> None:
        from .. import plugins

        self._filling = True
        self.plugin_list.clear()
        found = plugins.plugins()
        for pl in found:
            if not pl.enabled:
                what = "off"
            elif pl.problem:
                what = f"not loaded: {pl.problem}"
            else:
                what = "adds " + ", ".join(pl.commands)
            item = QListWidgetItem(f"{pl.name}  ({what})" + (f"\n    {pl.about}" if pl.about else ""))
            item.setData(Qt.UserRole, pl.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if pl.enabled else Qt.Unchecked)
            if pl.problem:
                item.setToolTip(pl.problem)
            self.plugin_list.addItem(item)
        if not found:
            empty = QListWidgetItem("No plug-ins yet: press Add the example, then change it to make your own.")
            empty.setFlags(Qt.NoItemFlags)
            self.plugin_list.addItem(empty)
        self._filling = False

    def _plugin_toggled(self, item: QListWidgetItem) -> None:
        if getattr(self, "_filling", False) or item.data(Qt.UserRole) is None:
            return
        off = set(plugins_off(self.win))
        name = str(item.data(Qt.UserRole))
        if item.checkState() == Qt.Checked:
            off.discard(name)
        else:
            off.add(name)
        if _settings(self.win) is not None:
            _settings(self.win).setValue(PLUGINS_OFF_SETTING, sorted(off))
        self._reload()

    def _reload(self) -> None:
        load_plugins(self.win)
        self._fill_plugins()

    def _add_example(self) -> None:
        from .. import plugins

        path = plugins.add_example()
        self.win.statusBar().showMessage(f"Example plug-in added: {path}", 8000)
        self._reload()

    def _open_folder(self) -> None:
        import os

        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from .. import plugins

        os.makedirs(plugins.folder(), exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(plugins.folder()))


def open_dialog(win) -> PreferencesDialog:
    dlg = PreferencesDialog(win)
    dlg.show()
    return dlg
