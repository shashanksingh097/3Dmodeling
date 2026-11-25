"""PLAN item 74: the Plug-ins tab in Preferences and plug-in commands in the Commands menu."""

import os
import shutil
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings, Qt  # noqa: E402

from modeler import plugins  # noqa: E402


@pytest.fixture
def win(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from modeler.gui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    folder = tmp_path / "plugins"
    folder.mkdir()
    shutil.copy(plugins.EXAMPLE, folder / "bolt_ring.py")
    monkeypatch.setenv("MODELER_PLUGINS_HOME", str(folder))
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()
    plugins.configure([])
    plugins.unload()


def _menu_titles(menu):
    return [a.text() for a in menu.actions()]


def test_plugin_loads_at_start_and_shows_in_menu(win):
    assert "Plug-ins" in [m.replace("&", "") for m in _menu_titles(win.commands_menu)]
    r = win.execute("BLOCK, 0,0,0, 60,60,10")
    assert r.ok
    r = win.execute("BOLTRING, LAST, 3, 5, 15")
    assert r.ok, r.message


def test_preferences_tab_turns_a_plugin_off_and_on(win):
    from modeler.commands.processor import REGISTRY
    from modeler.gui import prefs

    dlg = prefs.open_dialog(win)
    try:
        assert [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())] == ["Look", "Mouse and keys", "Plug-ins"]
        item = dlg.plugin_list.item(0)
        assert item.text().startswith("bolt_ring  (adds BOLTRING)")
        item.setCheckState(Qt.Unchecked)
        assert "BOLTRING" not in REGISTRY and prefs.plugins_off(win) == ["bolt_ring"]
        assert "Plug-ins" not in [m.replace("&", "") for m in _menu_titles(win.commands_menu)]
        dlg.plugin_list.item(0).setCheckState(Qt.Checked)
        assert "BOLTRING" in REGISTRY and prefs.plugins_off(win) == []
    finally:
        dlg.close()
