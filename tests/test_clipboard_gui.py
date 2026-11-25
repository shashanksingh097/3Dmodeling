"""PLAN item 107: Edit > Copy, Paste and Duplicate in the window (gui/clipboard.py)."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from modeler.gui import clipboard as cb
from modeler.gui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _win(tmp_path, name):
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / f"{name}.ini"), QSettings.IniFormat))
    w.show()
    return w


def _close(w):
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


def test_copy_paste_duplicate_and_between_windows(app, tmp_path):
    a = _win(tmp_path, "a")
    b = _win(tmp_path, "b")
    try:
        assert a.shell.copy_action.shortcut().toString() == "Ctrl+C"
        assert a.shell.duplicate_action.shortcut().toString() == "Ctrl+D"
        a.execute("BLOCK, 0, 0, 0, 10, 10, 10")
        a.execute("NAME, LAST, cube")
        # nothing picked: told so, nothing copied
        a.execute("PICKMODE, BODY")
        assert cb.copy(a) is None
        a.execute("PICK, BODY, 1")
        assert cb.copy(a)["items"][0]["name"] == "cube"
        assert "cube" in QApplication.clipboard().text()
        a.viewport.paste_point = lambda: None  # the mouse is not over the view
        assert cb.paste(a)
        assert a.processor.history[-1].text == "COPY, 1, 11, 0, 0"
        a.execute("PICK, BODY, 1")
        assert cb.duplicate(a) and len(a.processor.model.bodies) == 3
        # into another window: the geometry comes along and is kept there
        b.viewport.paste_point = lambda: (50.0, 0.0, 0.0)
        assert cb.paste(b)
        assert b.processor.history[-1].text == "PASTE, CLIP1, 45, -5, 0"
        assert b.processor.model.body(1).name == "cube"
    finally:
        _close(a)
        _close(b)
