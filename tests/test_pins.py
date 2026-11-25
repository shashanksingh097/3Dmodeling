"""PLAN item 115: pinned measurements (PIN) follow the model."""

import os
import sys

import pytest

from modeler.commands import Processor


def ok(p, line):
    r = p.run(line)
    assert r.ok, f"{line}: {r.message}"
    return r


def test_pin_follows_an_edit_and_checks_its_limits():
    p = Processor()
    ok(p, "W = 10")
    ok(p, "BLOCK, 0,0,0, W, 10, 10")
    ok(p, "NAME, LAST, base")
    ok(p, "BLOCK, 30,0,0, 10, 10, 10")
    ok(p, "NAME, LAST, lid")
    r = ok(p, "PIN, gap, DIST, BODY, base, BODY, lid, 15")
    assert "gap" in r.message and "20" in r.message and "in range" in r.message
    rep = p.reports["pins"]["pins"][0]
    assert rep["value"] == pytest.approx(20.0) and rep["ok"] is True
    ok(p, 'HIST, EDIT, 1, "W = 25"')  # the base grows: the gap shrinks to 5
    r = ok(p, "PIN")
    assert "gap" in r.message and ": 5" in r.message and "OUT of range" in r.message
    assert p.reports["pins"]["pins"][0]["ok"] is False


def test_angle_pin_delete_clear_and_undo():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 10,10,10")
    r = ok(p, "PIN, square, ANGLE, FACE, 1, FACE, 3, 89.9, 90.1")
    assert "90 deg" in r.message
    ok(p, "PIN, again, DIST, FACE, 1, FACE, 2")
    assert len(p.model.measure_pins) == 2
    ok(p, "PIN, DELETE, square")
    assert [x["name"] for x in p.model.measure_pins] == ["again"]
    ok(p, "UNDO")
    assert len(p.model.measure_pins) == 2
    ok(p, "PIN, CLEAR")
    assert not p.model.measure_pins
    assert not p.run("PIN, 9bad, DIST, FACE, 1, FACE, 2").ok
    assert not p.run("PIN, x, AREA, FACE, 1, FACE, 2").ok
    assert not p.run("PIN, x, DIST, FACE, 1, FACE, 2, 5, 1").ok


def test_pins_saved_with_the_project(tmp_path):
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 10,10,10")
    ok(p, "BLOCK, 20,0,0, 10,10,10")
    ok(p, "PIN, gap, DIST, BODY, 1, BODY, 2")
    f = str(tmp_path / "a.m3d")
    ok(p, f'SAVE, "{f}"')
    q = Processor()
    ok(q, f'OPEN, "{f}"')
    assert [x["name"] for x in q.model.measure_pins] == ["gap"]


@pytest.mark.skipif(os.environ.get("MODELER_GUI_TESTS") == "0" or
                    (sys.platform.startswith("linux") and not os.environ.get("DISPLAY")), reason="no display")
def test_pin_is_drawn_in_the_view(tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from modeler.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    w.show()
    app.processEvents()
    w.execute("BLOCK, 0,0,0, 10,10,10")
    w.execute("BLOCK, 20,0,0, 10,10,10")
    n0 = len(w.viewport._note_ais)
    assert w.execute("PIN, gap, DIST, BODY, 1, BODY, 2").ok
    app.processEvents()
    assert len(w.viewport._note_ais) >= n0 + 2  # the line and its value
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()
