"""View > Preferences: theme, 3D view background and toolbar buttons, kept
in the settings; File > Export drawing."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QAction, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from modeler.gui import prefs  # noqa: E402
from modeler.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def pump(app, n=10):
    for _ in range(n):
        app.processEvents()


def make(app, path):
    settings = QSettings(str(path), QSettings.IniFormat)
    w = MainWindow(autosave="off", settings=settings)
    w.resize(1000, 700)
    w.show()
    pump(app, 20)
    return w


def close(w):
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


def test_theme_background_and_buttons_are_kept(app, tmp_path):
    ini = tmp_path / "settings.ini"
    w = make(app, ini)
    try:
        start = app.palette().color(QPalette.Window).lightness()
        dlg = w.open_preferences()
        dlg.theme.setCurrentIndex(list(prefs.THEMES).index("dark"))
        pump(app)
        assert app.palette().color(QPalette.Window).lightness() < 128
        acts = [a for a in w.findChildren(QAction) if a.property("icon_name")]
        assert acts and all(not a.icon().isNull() for a in acts)
        dlg.background.setCurrentIndex(list(prefs.BACKGROUND_LABELS).index("white"))
        assert w.viewport.background == "white"
        dlg.buttons.setCurrentIndex(2)  # icons only
        dlg.close()
    finally:
        close(w)
    w2 = make(app, ini)  # a new session puts them back
    try:
        assert app.palette().color(QPalette.Window).lightness() < 128
        assert w2.viewport.background == "white"
        prefs.apply_theme(w2, "system")
        assert app.palette().color(QPalette.Window).lightness() == start
        prefs.apply_background(w2, "grey")
    finally:
        close(w2)


def test_export_drawing_menu(app, tmp_path):
    w = make(app, tmp_path / "s.ini")
    try:
        assert w.preferences_action.shortcut().toString() == "Ctrl+,"
        assert "Export drawing…" in [a.text().replace("&", "") for a in w.shell.file_menu.actions()]
        w.execute("BLOCK, 0,0,0, 10,10,10")
        f = tmp_path / "out.svg"
        w.shell.export_drawing(str(f))
        assert f.exists() and "<svg" in f.read_text()
    finally:
        close(w)
