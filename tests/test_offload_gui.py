"""Long history edits run in the rebuild helper while the window keeps running (gui/offload.py)."""

import os
import sys
import time

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

from modeler.gui import offload as off
from modeler.gui.main_window import MainWindow

SCRIPT = ["W = 40", "BLOCK, 0,0,0, W, 30, 10", "CYL, 20, 15, 0, 6, 10", "SUBTRACT, 1, 2"]


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
    for e in w.processor.history:
        e.seconds = 1.0  # pretend the steps are slow, so the edit goes to the helper
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


def test_expected_seconds_counts_from_the_edited_entry(win):
    p = win.processor
    assert off.expected_seconds(p, 'HIST, EDIT, 3, "CYL, 20, 15, 0, 8, 10"') == pytest.approx(2.0)
    assert off.expected_seconds(p, "HIST, REPLAY") == pytest.approx(4.0)
    assert off.expected_seconds(p, "HIST, MOVE, 4, 2") == pytest.approx(3.0)
    assert off.expected_seconds(p, "HIST") == 0
    assert off.expected_seconds(p, "BLOCK, 0,0,0, 1,1,1") == 0


def test_edit_runs_in_the_helper_and_the_window_keeps_going(win, app):
    ticks = []
    t = QTimer()
    t.timeout.connect(lambda: ticks.append(time.monotonic()))
    t.start(20)
    assert win.offload.wants('HIST, EDIT, 1, "W = 60"')
    res = win.execute('HIST, EDIT, 1, "W = 60"')
    t.stop()
    assert res.ok, res.message
    assert win.processor.evaluate("W") == 60
    assert win.processor.evaluate("VOL(LAST)") == pytest.approx(60 * 30 * 10 - 3.14159265 * 36 * 10, rel=1e-3)
    assert len(ticks) >= 3  # the event loop ran while the helper worked
    assert "W = 60" in win.output.toPlainText() or res.line
    assert not win.offload.busy and win.cmdline.isEnabled()
    assert win.execute("UNDO").ok  # the edit is one UNDO step, as when it runs here
    assert win.processor.evaluate("W") == 40


def test_commands_wait_while_a_rebuild_runs_and_cancel_keeps_the_model(win, app):
    vol = win.processor.evaluate("VOL(LAST)")
    refused = []

    def meanwhile():
        refused.append(win.execute("BLOCK, 0,0,0, 1,1,1"))
        win.offload.dialog.cancel()

    QTimer.singleShot(50, meanwhile)
    res = win.execute('HIST, EDIT, 1, "W = 80"')
    assert refused and not refused[0].ok
    assert not res.ok and "cancelled" in res.message
    assert win.processor.evaluate("W") == 40
    assert win.processor.evaluate("VOL(LAST)") == pytest.approx(vol)
    assert len(win.processor.history) == len(SCRIPT)
    assert win.execute('HIST, EDIT, 1, "W = 50"').ok  # a fresh helper starts for the next one
    assert win.processor.evaluate("W") == 50
