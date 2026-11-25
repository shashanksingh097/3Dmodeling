"""PLAN items 89-91 in the window: the error bar (faults in red, "Use ...", Find
fixes, Why?), tinted failed history rows, Enter on an empty line and right
click > Repeat, the pin on forms, and the Properties panel (needs a display:
run under xvfb-run)."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from modeler.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    monkeypatch.setenv("MODELER_TEMPLATES", str(tmp_path / "templates"))
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    w = MainWindow(autosave="off", settings=settings)
    w.resize(1300, 850)
    w.show()
    for _ in range(40):
        app.processEvents()
        if w.viewport._initialized:
            break
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


def run(win, text):
    for line in text.strip().splitlines():
        res = win.execute(line)
        assert res.ok, f"{line}: {res.message}"


def wait(ms=150):
    QTest.qWait(ms)


def wait_for(cond, ms=3000):
    for _ in range(ms // 20):
        if cond():
            return True
        QTest.qWait(20)
    return cond()


# ---- 89: the error bar -----------------------------------------------------------------------
def test_error_bar_hidden_at_start_and_after_success(win):
    assert not win.error_bar.isVisible()
    run(win, "BLOCK, 0,0,0, 10,10,10")
    assert not win.error_bar.isVisible()


def test_misspelt_command_offers_the_fixed_line(win):
    win.execute("blok, 1,1,1, 2,2,2")
    eb = win.error_bar
    assert eb.isVisible() and "did you mean BLOCK" in eb.label.text()
    assert [b.text() for b in eb.near_buttons] == ["Use BLOCK"]
    assert eb.fault is None
    eb.near_buttons[0].click()
    assert win.cmdline.text() == "BLOCK, 1,1,1, 2,2,2"
    QTest.keyClick(win.cmdline, Qt.Key_Return)
    wait()
    assert win.processor.history[-1].text == "BLOCK, 1,1,1, 2,2,2"
    assert not eb.isVisible()  # a line that works hides the bar


def test_a_failure_lights_up_the_picked_edge(win):
    run(win, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1")
    win.execute("FILLET, 50")
    eb = win.error_bar
    assert eb.isVisible() and "too large" in eb.label.text()
    assert eb.fault == {"kind": "EDGE", "ids": [1], "from": "the pick it used"}
    assert "edge 1, red in the view" in eb.label.text()
    m = win.processor.model
    assert len(m.preview) == 1 and m.preview[0][1] == "fault"
    eb.dismiss()
    assert not eb.isVisible() and m.preview == []


def test_find_fixes_offers_buttons_that_work(win):
    run(win, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1")
    win.execute("FILLET, 50")
    eb = win.error_bar
    fixes = eb.find_fixes()
    assert fixes and len(eb.fix_buttons) == len(fixes) <= 3
    assert not eb.find_button.isEnabled() and eb.find_button.text() == "Fixes below"
    assert fixes[0]["run"] in eb.fix_buttons[0].toolTip()
    n = len(win.processor.history)
    eb.fix_buttons[0].click()
    wait()
    assert len(win.processor.history) == n + 1 and win.processor.history[-1].text == fixes[0]["run"]
    assert not eb.isVisible()


def test_find_fixes_with_nothing_that_works(win):
    win.execute("SUBTRACT, nothing, at_all")
    eb = win.error_bar
    assert eb.find_fixes() == []
    assert eb.find_button.text() == "No usual fix works"


def test_why_button_opens_the_why_window(win):
    run(win, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1")
    win.execute("FILLET, 50")
    dlg = win.error_bar.open_why()
    assert "FILLET, 50" in dlg.text.toPlainText()
    dlg.close()


def test_esc_in_the_command_line_hides_the_bar(win):
    win.execute("BLOK")
    assert win.error_bar.isVisible()
    win.cmdline.setFocus()
    QTest.keyClick(win.cmdline, Qt.Key_Escape)
    assert not win.error_bar.isVisible()


def test_looking_at_a_failure_keeps_the_bar(win):
    run(win, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1")
    win.execute("FILLET, 50")
    win.execute("WHY")
    assert win.error_bar.isVisible()


def test_the_bar_fits_a_narrow_view(win):
    run(win, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1")
    win.execute("FILLET, 50")
    win.error_bar.find_fixes()
    wait()
    eb = win.error_bar
    assert eb.width() <= win.centralWidget().width()
    for b in eb.fix_buttons + [eb.find_button, eb.why_button, eb.close_button]:
        assert b.isVisible() and b.width() > 20
        assert b.geometry().right() <= eb.width()


# ---- 89: failed history rows -----------------------------------------------------------------
def _failed_step(win):
    run(win, 'BLOCK, 0,0,0, 20, 20, 20\nPICK, EDGE, 1\nFILLET, 5\nHIST, EDIT, 1, "BLOCK, 0,0,0, 4, 4, 4"')
    assert not win.processor.history[2].ok


def test_failed_rows_are_tinted_with_a_tip(win):
    _failed_step(win)
    hp = win.history_panel
    item = hp.item(2, 2)
    assert item.background().color() == QColor(253, 236, 236)
    assert "too large" in item.toolTip() and "error bar" in item.toolTip()
    assert hp.item(0, 2).background().style() == Qt.NoBrush


def test_clicking_a_failed_row_shows_it_in_the_bar(win):
    _failed_step(win)
    win.history_panel._clicked(2)
    eb = win.error_bar
    assert eb.isVisible() and eb.step == 3 and eb.label.text().startswith("Step 3:")
    assert eb.fault["kind"] == "EDGE" and eb.fault["ids"] == [1]
    d = eb.find_fixes()
    assert d and d[0]["run"].startswith("HIST, EDIT, 3")
    win.history_panel._clicked(0)  # a good row does not change the bar
    assert eb.isVisible() and eb.step == 3


# ---- 90: repeat ------------------------------------------------------------------------------
def test_enter_on_an_empty_line_repeats(win):
    run(win, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1\nFILLET, 2\nPICK, EDGE, 3")
    assert "Enter repeats FILLET, 2" in win.cmdline.placeholderText()
    win.cmdline.setFocus()
    win.cmdline.clear()
    QTest.keyClick(win.cmdline, Qt.Key_Return)
    wait()
    assert [e.text for e in win.processor.history][-2:] == ["PICK, EDGE, 3", "FILLET, 2"]
    assert "Repeated FILLET, 2" in win.statusBar().currentMessage()


def test_enter_on_an_empty_line_with_nothing_to_repeat(win):
    win.cmdline.setFocus()
    QTest.keyClick(win.cmdline, Qt.Key_Return)
    wait()
    assert win.processor.history == [] and not win.error_bar.isVisible()


def test_right_click_menu_has_repeat(win):
    run(win, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1\nFILLET, 2\nPICK, EDGE, 3")
    win.show_body_menu(max(win.processor.model.bodies), win.mapToGlobal(win.rect().center()))
    acts = win._body_menu.actions()
    rep = [a for a in acts if a.objectName() == "repeat"]
    assert len(rep) == 1 and rep[0].text() == "Repeat FILLET, 2"
    assert acts.index(rep[0]) > 0 and acts[0].text().startswith("The picked")  # after the tools for the pick
    win._body_menu.close()
    rep[0].trigger()
    wait()
    assert win.processor.history[-1].text == "FILLET, 2"


def test_repeat_is_first_without_a_pick(win):
    run(win, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1\nFILLET, 2")
    win.processor.model.selection = []
    win.show_body_menu(0, win.mapToGlobal(win.rect().center()))
    acts = win._body_menu.actions()
    assert acts[0].objectName() == "repeat" and acts[1].isSeparator()
    win._body_menu.close()


def test_no_repeat_in_the_menu_before_any_step(win):
    win.show_body_menu(0, win.mapToGlobal(win.rect().center()))
    assert all(a.objectName() != "repeat" for a in win._body_menu.actions())
    win._body_menu.close()


def test_pinned_form_stays_open_pick_after_pick(win):
    run(win, "BLOCK, 0,0,0, 20,20,20")
    dlg = win.open_form("CHAMFER", "CHAMFER, 1")
    assert not dlg.pin_box.isChecked()
    dlg.pin_box.setChecked(True)
    for e in (1, 3, 5):
        run(win, f"PICK, EDGE, {e}")
        assert dlg.submit(close=True) and dlg.isVisible()
    texts = [e.text for e in win.processor.history]
    assert texts.count("CHAMFER, 1") == 3
    assert "Pick the next ones" in win.statusBar().currentMessage()
    QTest.keyClick(dlg, Qt.Key_Escape)
    wait()
    # the pin is remembered for this command
    dlg2 = win.open_form("CHAMFER", "CHAMFER, 1")
    assert dlg2.pin_box.isChecked()
    dlg2.pin_box.setChecked(False)
    run(win, "PICK, EDGE, 7")
    assert dlg2.submit(close=True)
    wait()
    assert not win.findChildren(type(dlg2))


def test_pinned_form_takes_the_new_pick(win):
    run(win, "BLOCK, 0,0,0, 10,10,10\nBLOCK, 20,0,0, 10,10,10\nBLOCK, 40,0,0, 10,10,10")
    dlg = win.open_form("UNION", "")
    dlg.pin_box.setChecked(True)
    fields = [w for w in dlg.fields.values() if w.f.kind == "bodies"]
    if not fields:
        pytest.skip("UNION's form has no list of bodies")
    run(win, "PICK, BODY, 1 2")
    wait()
    assert "1" in fields[0].value() and "2" in fields[0].value()
    dlg.close()


def test_editing_a_step_has_no_pin(win):
    run(win, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1\nFILLET, 2")
    dlg = win.open_form("", "FILLET, 2", 2)
    assert not dlg.pinned and not dlg.pin_box.isVisible()
    dlg.close()


# ---- 91: the Properties panel ----------------------------------------------------------------
def _props_rows(pp):
    out = {}
    for i in range(pp.table.rowCount()):
        k, v = pp.table.item(i, 0), pp.table.item(i, 1)
        if k is not None and v is not None and k.data(Qt.UserRole):
            out[k.data(Qt.UserRole)] = v
    return out


def test_props_panel_follows_the_pick(win):
    pp = win.props_panel
    assert "Pick a body" in pp.title.text() and pp.table.rowCount() == 0
    run(win, "BLOCK, 0,0,0, 40,20,10\nNAME, LAST, bracket\nPICK, FACE, 2")
    wait()
    assert "Body 1" in pp.title.text() and "bracket" in pp.title.text()
    rows = _props_rows(pp)
    assert rows["name"].text() == "bracket" and rows["x"].text() == "20"
    assert bool(rows["x"].flags() & Qt.ItemIsEditable) and not bool(rows["volume"].flags() & Qt.ItemIsEditable)


def test_props_panel_edit_writes_the_step(win):
    pp = win.props_panel
    run(win, "BLOCK, 0,0,0, 40,20,10\nNAME, LAST, bracket\nPICK, BODY, 1")
    wait()
    _props_rows(pp)["x"].setText("50")
    wait()
    assert win.processor.history[-1].text == "MOVE, bracket, 30, 0, 0"
    _props_rows(pp)["1.dz"].setText("15")
    wait(400)
    assert win.processor.history[0].text == "BLOCK, 0, 0, 0, 40, 20, 15"
    assert wait_for(lambda: _props_rows(pp)["z"].text() == "7.5")
    _props_rows(pp)["colour"].setText("blue")
    wait()
    assert win.processor.history[-1].text == "COLOR, bracket, blue"


def test_props_panel_bad_value_shows_the_reason(win):
    pp = win.props_panel
    run(win, "BLOCK, 0,0,0, 40,20,10\nPICK, BODY, 1")
    wait()
    n = len(win.processor.history)
    _props_rows(pp)["turn"].setText("ninety")
    wait()
    assert "axis and an angle" in pp.note.text() and len(win.processor.history) == n
    assert _props_rows(pp)["turn"].text() == ""  # the table shows the model again


def test_props_panel_shows_a_clicked_step(win):
    pp = win.props_panel
    run(win, "BLOCK, 0,0,0, 40,20,10\nCYL, 0,0,0, 3, 20\nSUBTRACT, 1, 2")
    win.history_panel._clicked(0)
    assert "Step 1" in pp.title.text()
    rows = _props_rows(pp)
    assert rows["1.dx"].text() == "40"
    rows["1.dx"].setText("60")
    wait()
    assert win.processor.history[0].text == "BLOCK, 0, 0, 0, 60, 20, 10"
    assert "Step 1" in pp.title.text()  # still on the step
    run(win, "PICK, BODY, 3")
    wait()
    assert "Body 3" in pp.title.text()  # a new pick takes over


def test_props_dock_is_beside_parameters(win):
    tabs = win.tabifiedDockWidgets(win.props_dock)
    assert any(d.windowTitle() == "Parameters" for d in tabs)
