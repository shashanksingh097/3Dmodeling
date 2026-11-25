"""PLAN item 106: the Python console (gui/console.py)."""

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


def test_off_until_opened_and_commands_go_to_history(win):
    assert getattr(win, "console_dock", None) is None  # off by default
    win.console_action.setChecked(True)
    con = win.console
    assert win.console_dock.isVisible()
    out = con.push("c.BLOCK(0, 0, 0, 20, 10, 5)")
    assert "BLOCK -> body 1" in out
    con.push('run("NAME, LAST, plate")')
    assert [e.text for e in win.processor.history] == ["BLOCK, 0, 0, 0, 20, 10, 5", "NAME, LAST, plate"]
    assert "1000" in con.push("round(value('VOL(plate)'))")
    con.push("c.MASSPROP('plate')")
    assert "1000" in con.push("round(report('MASSPROP')['volume'])")
    assert "plate" in con.push("bodies()")
    # loops work, a line at a time
    con.push("for i in range(2):")
    con.push("    c.CYL(30 + 10 * i, 0, 0, 2, 5)")
    con.push("")
    assert len(win.processor.model.bodies) == 3


def test_direct_changes_are_undone(win):
    win.toggle_console(True)
    con = win.console
    con.push("c.BLOCK(0, 0, 0, 20, 10, 5)")
    out = con.push("model.bodies.pop(1)")
    assert "not kept" in out and 1 in win.processor.model.bodies
    out = con.push("1 / 0")
    assert "ZeroDivisionError" in out
    out = con.push("raise SystemExit")
    assert win.isVisible()
    win.toggle_console(False)
    assert not win.console_dock.isVisible()


def test_command_text():
    from modeler.gui.console import _arg

    assert _arg(2.5) == "2.5" and _arg(True) == "YES" and _arg((1, 2, 3)) == "(1, 2, 3)"
    assert _arg("a, b") == '"a, b"' and _arg("SEL") == "SEL"
