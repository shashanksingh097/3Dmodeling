"""PLAN item 109: several projects open at once, in tabs (gui/project_tabs.py)."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from modeler.gui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path):
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    w.show()
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


def test_tabs_keep_their_own_history_and_undo(win, tmp_path):
    tabs = win.project_tabs
    assert tabs.count() == 1 and not tabs.bar.isVisible()  # one project: no tab bar
    win.execute("BLOCK, 0, 0, 0, 10, 10, 10")
    win.execute("NAME, LAST, first")
    f = tmp_path / "one.m3d"
    win.execute(f'SAVE, "{f}"')
    win.shell.mark_saved()
    assert tabs.new_tab() == 1 and tabs.bar.isVisible()
    p = win.processor
    assert not p.model.bodies and not p.history and win.windowTitle().startswith("Untitled")
    win.execute("CYL, 0, 0, 0, 5, 20")
    win.execute("CYL, 20, 0, 0, 5, 20")
    win.execute("UNDO")
    assert len(p.model.bodies) == 1
    tabs.switch(0)
    assert [b.name for b in p.model.bodies.values()] == ["first"]
    assert win.windowTitle().startswith("one.m3d") and win.history_panel.rowCount() == 2
    assert tabs.labels() == ["one.m3d", "Untitled"] and tabs.tabs[1].modified
    tabs.switch(1)
    assert len(p.model.bodies) == 1 and p.can_redo  # its undo came back with it
    win.execute("REDO")
    assert len(p.model.bodies) == 2
    # a body to the other tab, where it stands
    tabs.copy_to([1], 0)
    assert tabs.current == 0 and len(p.model.bodies) == 2
    assert p.history[-1].text.startswith("PASTE, CLIP1, 0, 0, 0")
    # closing a tab with changes asks; the last tab stays
    asked = []
    win.shell.ask_unsaved = lambda *a: asked.append(a) or "discard"
    assert tabs.close_tab(1)
    assert tabs.count() == 1 and asked and not tabs.bar.isVisible()
    assert not tabs.close_tab(0)


def test_the_file_menu_has_the_tab_actions(win):
    sh = win.shell
    assert sh.new_tab_action.shortcut().toString() == "Ctrl+T"
    assert sh.close_tab_action.shortcut().toString() == "Ctrl+W"
    sh.new_tab_action.trigger()
    assert win.project_tabs.count() == 2
    sh.prev_tab_action.trigger()
    assert win.project_tabs.current == 0


def test_the_assistant_hears_which_project(win):
    from modeler.ai.tools import Toolbox

    tb = Toolbox(win.processor)
    assert "open_tabs" not in tb.user_context()["project"]
    win.project_tabs.new_tab()
    ctx = tb.user_context()["project"]
    assert ctx["open_tabs"] == ["Untitled", "Untitled"] and ctx["shown_tab"] == 2
