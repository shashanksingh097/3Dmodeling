"""The window side of free editing: Edit sketch in the model tree, and the question before a change
that would break later steps (PLAN items 118-119)."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from modeler.gui import edit_guard as eg  # noqa: E402
from modeler.gui.main_window import MainWindow  # noqa: E402

PLATE = ["SKETCH, s1, XY", "SRECT, 0, 0, 80, 40", "ENDSKETCH", "EXTRUDE, s1, 10", "HOLE, LAST, 30, 20, 10, 8"]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def pump(app, n=10):
    for _ in range(n):
        app.processEvents()


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    monkeypatch.setenv("MODELER_EDIT_QUESTION", "1")
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    w.resize(1000, 700)
    w.show()
    pump(app, 20)
    for line in PLATE:
        assert w.execute(line).ok, line
    pump(app, 20)
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


def test_tree_menu_edits_a_used_sketch(app, win):
    win.model_tree.refresh()
    items = win.model_tree.menu_items("sketch:S1")
    labels = [i.label for i in items]
    assert any(lb.startswith("Edit sketch") for lb in labels)
    edit = next(i for i in items if i.label.startswith("Edit sketch"))
    for c in edit.commands:
        assert win.execute(c).ok
    assert win.processor.sketch_edit is not None
    assert [i.label for i in win.model_tree.menu_items("sketch:S1")][-1] == "Close sketch"
    assert win.execute("SCIRCLE, (60, 20), 5").ok
    res = win.execute("ENDSKETCH")
    assert res.ok and "ran again" in res.message
    assert win.processor.cursor == len(PLATE) + 3
    assert all(e.ok for e in win.processor.history)


def test_a_breaking_change_asks_first(app, win, monkeypatch):
    assert win.execute("PICK, EDGE, 14").ok
    assert win.execute("FILLET, 3").ok
    asked = []
    monkeypatch.setattr(eg, "choose", lambda w, q: asked.append(q) or eg.CANCEL)
    res = win.execute('HIST, EDIT, 4, "EXTRUDE, s1, 2"')
    assert asked and not res.ok
    assert "stays as it was" in win.output.toPlainText()
    assert win.processor.history[3].text == "EXTRUDE, s1, 10"
    monkeypatch.setattr(eg, "choose", lambda w, q: eg.HISTORY)
    win.execute('HIST, EDIT, 4, "EXTRUDE, s1, 2"')
    assert win.processor.history[3].text == "EXTRUDE, s1, 2"
    assert not win.processor.history[6].ok  # the fillet is red, as asked


def test_typed_hist_edit_runs_as_typed(app, win, monkeypatch):
    assert win.execute("PICK, EDGE, 14").ok
    assert win.execute("FILLET, 3").ok
    monkeypatch.setattr(eg, "choose", lambda w, q: pytest.fail("asked"))
    win.cmdline.setText('HIST, EDIT, 4, "EXTRUDE, s1, 2"')
    win._on_enter()
    assert win.processor.history[3].text == "EXTRUDE, s1, 2"
