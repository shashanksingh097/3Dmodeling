"""The Motion window (gui/motion_panel.py): slider, check, pictures, letting go on close."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from modeler.commands.queries import bbox
from modeler.gui.main_window import MainWindow
from modeler.gui.motion_panel import driveable

SCRIPT = ["A = 0", "W = 40", "BLOCK, 0, 0, 0, W, 30, 5", "BLOCK, 0, 0, 5, W, 30, 2", "NAME, LAST, lid",
          "ROTATE, lid, -A, 0, 0, 5, 0, 1, 0", "CYL, -20, 15, 0, 3, 30"]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path):
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    w.resize(1000, 700)
    w.show()
    for _ in range(20):
        app.processEvents()
    for line in SCRIPT:
        assert w.execute(line).ok
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


def test_slider_drives_and_close_lets_go(app, win, tmp_path):
    assert driveable(win.processor) == ["A", "W"]
    dlg = win.open_motion()
    assert dlg.param.currentText() == "A"
    dlg.end.setValue(180)
    dlg.steps.setValue(4)
    dlg.slider.setValue(2)
    dlg._debounce.timeout.emit()  # what the timer does a moment after the slider stops
    assert win.processor.params["A"] == 90
    assert bbox(win.processor.model.body(2).shape)[5] == pytest.approx(45)
    n = len(win.processor.history)
    text = dlg.check()
    assert "run into each other" in text and len(win.processor.history) == n
    saved = dlg.save_pictures(str(tmp_path))
    assert len(saved) == 5 and all(os.path.getsize(f) > 1000 for f in saved)
    dlg.close()
    assert not win.processor.drive and win.processor.params["A"] == 0


def test_study_plots_and_table(win, app, tmp_path):
    from modeler.gui.motion_panel import open_motion

    assert win.execute("MATERIAL, lid, ALUMINIUM").ok
    dlg = open_motion(win)
    dlg.param.setCurrentText("A")
    dlg.start.setValue(0)
    dlg.end.setValue(60)
    dlg.steps.setValue(6)
    dlg.points.setText("lid 40,30,7")
    msg = dlg.study()
    assert "motion study" in msg and "drive torque" in msg
    assert [s[0] for s in dlg.plot.series] == ["lid speed", "lid acceleration", "drive torque"]
    dlg.plot.grab()  # it paints
    f = tmp_path / "study.csv"
    dlg.save_table(str(f))
    assert f.read_text().startswith("A,time_s")
    dlg.close()
