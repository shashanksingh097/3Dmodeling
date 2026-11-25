"""Preferences: the window's theme (light, dark or the system's), the 3D
view's background and how toolbar buttons show. Kept in the app's settings
and put back when the app starts.

The light and dark themes use Qt's Fusion style with a palette of their
own, so they look the same on every system; "system" leaves the style and
palette the platform gave. The toolbar icons are drawn from the palette
(gui/icons.py), so they are drawn again when the theme changes.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QVBoxLayout)

from . import icons
from ..viewport.occ_view import BACKGROUNDS

THEME_SETTING = "theme"
BACKGROUND_SETTING = "viewBackground"
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


class PreferencesDialog(QDialog):
    """Theme, 3D view background and toolbar buttons; each applies at once."""

    def __init__(self, win) -> None:
        super().__init__(win)
        from . import toolbars as tbs

        self.win = win
        self.setWindowTitle("Preferences")
        lay = QVBoxLayout(self)
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
        from . import pick_bar
        from .form_dialog import PREVIEW_SETTING, _set_setting, _setting

        self.pick_tools = QCheckBox("Show the tools that fit next to what you pick")
        self.pick_tools.setChecked(pick_bar.enabled(win))
        self.pick_tools.toggled.connect(lambda on: pick_bar.set_enabled(win, on))
        form.addRow("Tools beside a pick:", self.pick_tools)
        self.form_preview = QCheckBox("Draw what a form's step would make before OK")
        self.form_preview.setChecked(_setting(win, PREVIEW_SETTING, True))
        self.form_preview.toggled.connect(lambda on: _set_setting(win, PREVIEW_SETTING, on))
        form.addRow("Preview in forms:", self.form_preview)
        from . import sel_numbers

        self.hover_numbers = QCheckBox("Show the size of what the mouse rests on in the 3D view")
        self.hover_numbers.setChecked(sel_numbers.hover_enabled(win))
        self.hover_numbers.toggled.connect(lambda on: sel_numbers.set_hover_enabled(win, on))
        form.addRow("Numbers on hover:", self.hover_numbers)
        from . import start_page

        self.start_page = QCheckBox("Show the start page (templates, recent projects) when the app starts")
        self.start_page.setChecked(start_page.enabled(win))
        self.start_page.toggled.connect(lambda on: start_page.set_enabled(win, on))
        form.addRow("Start page:", self.start_page)
        from .main_window import set_view_cube_enabled, view_cube_enabled

        self.view_cube = QCheckBox("Show the view cube in the corner of the 3D view")
        self.view_cube.setChecked(view_cube_enabled(win))
        self.view_cube.toggled.connect(lambda on: set_view_cube_enabled(win, on))
        form.addRow("View cube:", self.view_cube)
        from . import picture_tips

        self.picture_tips = QCheckBox("Show a picture of what a button makes in its tooltip")
        self.picture_tips.setChecked(picture_tips.enabled(win))
        self.picture_tips.toggled.connect(lambda on: picture_tips.set_enabled(win, on))
        form.addRow("Tooltips:", self.picture_tips)
        lay.addLayout(form)
        note = QLabel("Changes apply at once and are kept for next time.")
        note.setEnabled(False)
        lay.addWidget(note)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.accept)
        box.accepted.connect(self.accept)
        lay.addWidget(box)


def open_dialog(win) -> PreferencesDialog:
    dlg = PreferencesDialog(win)
    dlg.show()
    return dlg
