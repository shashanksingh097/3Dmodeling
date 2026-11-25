"""PLAN item 110: the live drawing-sheet window (gui/sheet_window.py)."""

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


def test_window_shows_sheet_drags_views_and_adds_sizes(win, app, tmp_path):
    for line in ("BLOCK, 0, 0, 0, 40, 20, 10", "DRAWSHEET, front, STANDARD, 0, NONE, A4"):
        assert win.execute(line).ok
    sw = win.open_sheets()
    app.processEvents()
    assert sw.sheet_box.currentText() == "front"
    assert {"FRONT", "TOP", "RIGHT", "ISO"} <= set(sw.boxes)
    # a drag of 10 mm of paper to the right and 5 up is one SHEETVIEW step
    assert sw.moved("TOP", 10.0, 5.0)
    k = sw.page.scale
    assert win.processor.history[-1].text.startswith("SHEETVIEW, front, TOP")
    mv = win.processor.model.drawsheets["FRONT"]["moves"]["TOP"]
    assert mv == pytest.approx([10 / k, 5 / k], abs=1e-3)
    sw.refresh()
    assert "moved: top" in sw.status.text()
    # sizes of picked edges
    m = win.processor.model
    m.selection_kind, m.selection = "EDGE", list(m.entity_ids("EDGE"))[:2]
    assert sw.size_of_pick()
    assert len(m.drawsheets["FRONT"]["notes"]) == 2
    assert sw.centres()
    assert sw.reset_views()
    assert not m.drawsheets["FRONT"].get("moves")
    pdf = tmp_path / "d.pdf"
    assert sw.save_pdf(str(pdf)) and pdf.stat().st_size > 1000


def test_no_sheet_says_how_to_make_one(win, app):
    sw = win.open_sheets()
    assert "New sheet" in sw.status.text()
    assert not sw.size_button.isEnabled()
