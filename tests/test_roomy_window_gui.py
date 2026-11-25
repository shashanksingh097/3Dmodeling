"""A roomier window (PLAN items 120-122): History and Output closed at first with buttons in the
status bar, Properties and Parameters under the model tree, fewer repeated buttons."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolBar  # noqa: E402

from modeler.gui import toolbars as tbs  # noqa: E402
from modeler.gui.app_shell import ROOMY_KEY  # noqa: E402
from modeler.gui.main_window import MainWindow  # noqa: E402
from modeler.gui.panel_buttons import history_text  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def pump(app, n=10):
    for _ in range(n):
        app.processEvents()


def make(app, path):
    w = MainWindow(autosave="off", settings=QSettings(str(path), QSettings.IniFormat))
    w.resize(1600, 960)
    w.show()
    pump(app, 20)
    return w


@pytest.fixture
def win(app, tmp_path):
    w = make(app, tmp_path / "s.ini")
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


def test_the_3d_view_gets_the_room(app, win):
    assert not win.history_dock.isVisible() and not win.output_dock.isVisible()
    assert not win.assistant_dock.isVisible() and not win.layers_dock.isVisible()
    assert win.tree_dock.isVisible() and win.props_dock.isVisible()
    for d in (win.tree_dock, win.props_dock, win.params_dock):
        assert win.dockWidgetArea(d) == Qt.LeftDockWidgetArea
    vp = win.viewport
    share = vp.width() * vp.height() / (win.width() * win.height())
    assert share > 0.55, share


def test_history_button_and_ctrl_h(app, win):
    b = win.panel_buttons.buttons["history"]
    assert b.text() == "History: 0 steps"
    win.execute("BLOCK, 0,0,0, 10, 10, 10")
    assert b.text() == "History: 1 step"
    b.click()
    pump(app)
    assert win.history_dock.isVisible()
    win.panel_buttons.shortcut.activated.emit()  # Ctrl+H
    pump(app)
    assert not win.history_dock.isVisible() and not b.isChecked()
    win.history_dock.show()
    pump(app)
    assert b.isChecked()


def test_history_button_says_when_a_step_failed(app, win):
    p = win.processor
    for line in ("BLOCK, 0,0,0, 10, 10, 10", "PICK, EDGE, 1", "FILLET, 1"):
        assert win.execute(line).ok
    win.execute('HIST, EDIT, 3, "FILLET, 50"')
    text, failed = history_text(p)
    assert failed == 1 and text.endswith("1 failed")
    assert "c62828" in win.panel_buttons.buttons["history"].styleSheet()


def test_a_typed_question_opens_the_output(app, win):
    win.execute("BLOCK, 0,0,0, 10, 10, 10")
    assert not win.output_dock.isVisible()
    win.cmdline.setText("BLOCK, 0,0,0, 5, 5, 5")
    win._on_enter()
    pump(app)
    assert not win.output_dock.isVisible()  # a new step: the view shows it
    win.cmdline.setText("DESCRIBE, 1")
    win._on_enter()
    pump(app)
    assert win.output_dock.isVisible()


def test_parameters_list_only_what_the_user_set(app, win):
    win.execute("W = 40")
    win.execute("*DO, i, 1, 3\nBLOCK, i*20, 0, 0, 5, 5, 5\n*ENDDO")
    pp = win.param_panel
    pp.refresh()
    names = [pp.item(r, 0).text() for r in range(pp.rowCount())]
    assert names == ["W"] and pp.hidden_count == 1


def test_home_tab_without_repeats(app, win):
    home = [tb for tb in tbs.groups(win) if tb.property("tab") == "Home"]
    labels = [a.text() for tb in home for a in tb.actions()]
    for gone in ("Undo", "Redo", "Iso", "Top", "Front", "Right", "Save log…", "Run script…", "Clear", "Body"):
        assert gone not in labels, gone
    assert win.undo_action in win.quick_access.actions()  # still in reach, on every tab
    pick = next(tb for tb in home if tb.windowTitle() == "Pick")
    menu = pick.widgetForAction(win._mode_actions["AUTO"]).menu()
    assert [a.text() for a in menu.actions()] == ["Body", "Face", "Edge", "Vertex"]
    win._mode_actions["FACE"].trigger()
    assert win.viewport.pick_mode == "FACE"
    view = next(a.menu() for a in win.menuBar().actions() if a.text() == "&View")
    titles = [a.text() for a in view.actions()]
    assert "&Look from" in titles and "&Panels" in titles


def test_item_panel_folds_with_nothing_picked(app, win):
    win.item_panel.refresh()
    assert not win.item_panel.steps.isVisibleTo(win.item_panel)
    win.execute("BLOCK, 0,0,0, 10, 10, 10")
    win.execute("PICK, BODY, 1")
    win.item_panel.refresh()
    assert win.item_panel.steps.isVisibleTo(win.item_panel)


def test_an_old_saved_layout_gives_way_once(app, tmp_path):
    path = tmp_path / "old.ini"
    w = make(app, path)
    w.history_dock.show()
    w.output_dock.show()
    pump(app)
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()
    s = QSettings(str(path), QSettings.IniFormat)
    s.remove(ROOMY_KEY)  # as a window from before the change left it
    s.sync()
    w2 = make(app, path)
    assert not w2.history_dock.isVisible()  # the new arrangement, once
    w2.history_dock.show()
    pump(app)
    w2.shell.ask_unsaved = lambda *_: "discard"
    w2.close()
    w3 = make(app, path)
    assert w3.history_dock.isVisible()  # from then on, what the user left
    w3.shell.ask_unsaved = lambda *_: "discard"
    w3.close()


def test_no_side_toolbars(app, win):
    for area in (Qt.LeftToolBarArea, Qt.RightToolBarArea, Qt.BottomToolBarArea):
        assert not [t for t in win.findChildren(QToolBar) if t.isVisible() and win.toolBarArea(t) == area]
