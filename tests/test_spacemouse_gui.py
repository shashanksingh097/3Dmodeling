"""PLAN item 111: the 3D mouse moves the window's view and its buttons run commands."""

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
from modeler.viewport import spacemouse as sm


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_motion_turns_the_view_and_buttons_run_commands(app, tmp_path):
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    w.show()
    app.processEvents()
    w.execute("BLOCK, 0, 0, 0, 10, 10, 10")
    w.execute("VIEW, FRONT")
    d0 = w.viewport.view.Camera().Direction()
    assert w.spacemouse.apply((0, 0, 0, 0, 1, 0), 0.5)
    d1 = w.viewport.view.Camera().Direction()
    assert abs(d0.Dot(d1)) < 0.9  # turned about 45 degrees
    w.spacemouse.feed(("button", 2, True))  # VIEW, ISO by default
    assert w.viewport.view_name() in ("ISO", "TOP FRONT RIGHT")
    assert w.processor.run("SPACEMOUSE, SPEED, 3").ok
    w2 = QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat)
    assert '"speed": 3.0' in w2.value("spaceMouse")
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()
    sm.settings = sm.Settings()
