"""PLAN item 83 in the window: the fill-in forms draw what the step would make in the
3D view before OK (needs a display: run under xvfb-run)."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtWidgets import QApplication  # noqa: E402

from modeler.gui.form_dialog import FormDialog  # noqa: E402
from modeler.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def pump(app, n=10):
    for _ in range(n):
        app.processEvents()


@pytest.fixture
def win(app):
    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    pump(app, 30)
    yield w
    w.close()


def run(win, text):
    for line in text.splitlines():
        res = win.execute(line)
        assert res.ok, res.message


def test_fillet_form_shows_the_result_and_cancel_leaves_nothing(app, win):
    run(win, "BLOCK, 0,0,0, 40,20,10\nNAME, LAST, plate\nSEL, S, EDGE, BODY, plate")
    p = win.processor
    steps = len(p.history)
    dlg = win.open_form("FILLET")
    assert isinstance(dlg, FormDialog)
    dlg.fields["r"].set_value("2")
    pump(app)
    pv = dlg.preview_now()
    assert pv is not None and pv.ok
    assert "changes plate" in dlg.effect.text()
    assert p.model.preview and win.viewport._step_ais
    assert p.model.preview_bodies == [1]  # the plate is drawn faint under its ghost
    assert len(p.history) == steps  # nothing ran for real
    dlg.reject()
    pump(app)
    assert not p.model.preview and not win.viewport._step_ais
    assert len(p.history) == steps


def test_a_step_that_would_fail_shows_why_and_where(app, win):
    run(win, "BLOCK, 0,0,0, 40,20,10\nSEL, S, EDGE, BODY, 1")
    dlg = win.open_form("FILLET")
    dlg.fields["r"].set_value("30")
    pump(app)
    pv = dlg.preview_now()
    assert pv is not None and not pv.ok
    assert dlg.effect.text().startswith("Would fail:") and "4.9" in dlg.effect.text()
    assert pv.fault == {"kind": "EDGE", "ids": list(range(1, 13))}
    assert all(k == "fault" for _s, k in win.processor.model.preview)
    dlg.fields["r"].set_value("3")
    pump(app)
    assert dlg.preview_now().ok
    assert dlg.submit(close=True)
    pump(app)
    assert not win.processor.model.preview  # the real step replaced the ghost
    assert win.processor.history[-1].text.startswith("FILLET")


def test_the_preview_follows_the_typing_and_new_picks(app, win):
    run(win, "BLOCK, 0,0,0, 40,20,10\nPICK, EDGE, 1")
    dlg = win.open_form("FILLET")
    dlg.fields["r"].set_value("1")
    pump(app)
    assert dlg._preview_timer.isActive()  # waits for the typing to stop
    dlg._preview_timer.timeout.emit()
    first = dlg._last_preview.changed[0]["volume"][1]
    run(win, "PICK, EDGE, 2, A")  # one more edge picked in the view
    assert dlg._preview_timer.isActive()
    dlg._preview_timer.timeout.emit()
    assert dlg._last_preview.changed[0]["volume"][1] < first
    dlg.preview_box.setChecked(False)
    assert not win.processor.model.preview
    dlg.preview_box.setChecked(True)
    dlg.preview_now()
    assert win.processor.model.preview
    dlg.close()


def test_editing_a_step_previews_the_rebuilt_model(app, win):
    run(win, "W = 40\nBLOCK, 0,0,0, W,20,10\nCYL, 10,10,10, 3, 5")
    p = win.processor
    dlg = win.open_form("BLOCK", p.history[1].text, edit_row=1) if False else None
    from modeler.gui.form_dialog import open_form

    dlg = open_form(win, "BLOCK", p.history[1].text, edit_row=1)
    dlg.fields["dx"].set_value("W, 20, 30")
    pump(app)
    pv = dlg.preview_now()
    assert pv.ok and pv.changed and pv.changed[0]["volume"][1] == pytest.approx(40 * 20 * 30)
    assert p.evaluate("VOL(1)") == pytest.approx(8000)  # the real model is untouched
    dlg.reject()


def test_slow_previews_wait_for_the_button(app, win, monkeypatch):
    from modeler.commands import preview_handlers as ph

    monkeypatch.setattr(ph, "SLOW", -1.0)  # every preview counts as slow
    run(win, "BLOCK, 0,0,0, 10,10,10")
    dlg = win.open_form("MOVE")
    dlg.fields["b"].set_value("1")
    dlg.fields["dx"].set_value("5")
    pump(app)
    dlg.preview_now()
    assert dlg._manual and not dlg.update_button.isHidden()
    dlg.fields["dx"].set_value("7")
    pump(app)
    assert not dlg._preview_timer.isActive() and "Update preview" in dlg.effect.text()
    pv = dlg.preview_now()
    assert pv.ok and "changes body 1" in pv.text(), pv.text()
    dlg.reject()


def test_preview_command_and_off(app, win):
    run(win, "BLOCK, 0,0,0, 10,10,10")
    n = len(win.processor.history)
    res = win.execute('PREVIEW, "HOLE, 1, 5,5,10, 4"')
    assert res.ok and "changes body 1 (becomes body 2)" in res.message
    assert win.viewport._step_ais and len(win.processor.history) == n
    assert win.execute("PREVIEW, OFF").ok
    assert not win.viewport._step_ais
