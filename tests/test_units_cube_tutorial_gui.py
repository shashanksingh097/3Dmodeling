"""PLAN items 92-94 in the window: unit labels on form fields, the view cube
(clicks, arrows, home, the setting), the Tutorial panel (Help > Tutorials,
checks turning green as the model changes, Show me, Next, Back, Stop, the
unsaved-work question), layouts (View > Layout, saved ones kept in the
settings) and pictures in the ribbon's tooltips (needs a display: run under
xvfb-run)."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QEvent, QPointF, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox  # noqa: E402

from modeler.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _make(app, tmp_path, monkeypatch, name="settings.ini"):
    monkeypatch.setenv("MODELER_TEMPLATES", str(tmp_path / "templates"))
    monkeypatch.setenv("MODELER_TUTORIALS", str(tmp_path / "tutorials"))
    settings = QSettings(str(tmp_path / name), QSettings.IniFormat)
    w = MainWindow(autosave="off", settings=settings)
    w.resize(1400, 900)
    w.show()
    for _ in range(60):
        app.processEvents()
        if w.viewport._initialized:
            break
    return w


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    w = _make(app, tmp_path, monkeypatch)
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    w.shell.confirm_discard = lambda *_: True
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


def last_output(win):
    return [line for line in win.output.toPlainText().splitlines() if line.startswith("> ")][-1][2:]


# ---- item 92: units beside form fields ----------------------------------------------------------
def test_form_fields_show_their_unit(win):
    dlg = win.open_form("BLOCK")
    wait()
    units = {lab.text() for lab in dlg.findChildren(QLabel, "unit") if lab.isVisibleTo(dlg)}
    assert units == {"mm"}
    dlg.close()
    run(win, "/UNITS, IN")
    dlg = win.open_form("ROTATE")
    wait()
    units = {lab.text() for lab in dlg.findChildren(QLabel, "unit") if lab.isVisibleTo(dlg)}
    assert "deg" in units and "in" in units
    dlg.close()


def test_a_unit_typed_in_a_form_field(win):
    dlg = win.open_form("BLOCK", "BLOCK, 0, 0, 0, 1 in, 20 mm, 1 cm")
    wait()
    assert dlg.ok_button.isEnabled()
    dlg.ok_button.click()
    wait(300)
    assert win.processor.history[-1].text.startswith("BLOCK")
    from modeler.ai import expect

    assert expect.check(win.processor, "BBOX(LAST).dx, EQ, 25.4, 1e-6").passed


def test_status_bar_numbers_follow_shown_units(win):
    run(win, "BLOCK, 0,0,0, 25.4, 50.8, 10\nPICK, BODY, 1")
    assert wait_for(lambda: "mm" in win.sel_numbers.text())
    run(win, "/UNITS, IN, SHOW")
    assert wait_for(lambda: "size 1 x 2 x 0.3937 in" in win.sel_numbers.text()), win.sel_numbers.text()
    run(win, "/UNITS, MM, SHOW")
    assert wait_for(lambda: "in³" not in win.sel_numbers.text() and "mm" in win.sel_numbers.text())


# ---- item 93: the view cube ---------------------------------------------------------------------------
def _click(vp, x, y):
    for t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        buttons = Qt.LeftButton if t == QEvent.MouseButtonPress else Qt.NoButton
        ev = QMouseEvent(t, QPointF(x, y), vp.mapToGlobal(QPointF(x, y)), Qt.LeftButton, buttons, Qt.NoModifier)
        (vp.mousePressEvent if t == QEvent.MouseButtonPress else vp.mouseReleaseEvent)(ev)
    wait(60)


def test_view_cube_clicks_write_view_lines(win):
    from modeler.viewport.view_cube import CORNER

    run(win, "BLOCK, 0,0,0, 40,20,10\nFIT")
    vp = win.viewport
    assert vp.cube is not None and vp.cube.visible
    cx, cy = vp.width() - CORNER, CORNER
    _click(vp, cx, cy)  # the face towards the eye in the iso view
    first = last_output(win)
    assert first.startswith("VIEW, ")
    name = first.split(",", 1)[1].strip()
    assert vp.view_name() == name
    seen = {name}
    for dx, dy in ((0, -22), (22, 12), (-22, 12), (26, -26), (-26, -26)):
        _click(vp, cx + dx, cy + dy)
        seen.add(last_output(win).split(",", 1)[1].strip())
    assert len(seen) >= 3  # faces, edges and corners give different views
    n = len(win.processor.history)
    assert n == 1  # VIEW is not a history step


def test_view_cube_arrows_and_home(win):
    run(win, "BLOCK, 0,0,0, 40,20,10\nVIEW, FRONT")
    vp = win.viewport
    vp.cube.buttons["LEFT"].click()
    wait()
    assert last_output(win) == "VIEW, TURN, LEFT" and vp.view_name() in ("LEFT", "RIGHT")
    vp.cube.buttons["RIGHT"].click()
    wait()
    assert vp.view_name() == "FRONT"
    vp.cube.buttons["UP"].click()
    wait()
    assert vp.view_name() == "TOP"
    vp.cube.buttons["HOME"].click()
    wait()
    assert last_output(win) == "VIEW, HOME" and vp.view_name() == "TOP FRONT RIGHT"
    state = vp.view_state()
    assert state["name"] == "TOP FRONT RIGHT" and state["view_cube"] is True
    assert 1 in state["in_sight"]


def test_view_cube_stays_after_new_undo_and_replay(win):
    vp = win.viewport
    ctx = vp.context
    assert ctx.IsDisplayed(vp.cube.cube)
    run(win, "BLOCK, 0,0,0, 4,4,4\nUNDO")
    assert ctx.IsDisplayed(vp.cube.cube)
    run(win, "BLOCK, 0,0,0, 4,4,4\nNEW")
    assert ctx.IsDisplayed(vp.cube.cube)
    run(win, "TUTORIAL, fix_a_step")  # a new project and a history edit
    assert ctx.IsDisplayed(vp.cube.cube) and vp.cube.visible


def test_view_state_tool_sees_the_window(win):
    from modeler.ai.tools import Toolbox

    run(win, "BLOCK, 0,0,0, 40,20,10\nVIEW, TOP FRONT")
    out = Toolbox(win.processor).call("view_state", {})
    assert out["name"] == "TOP FRONT" and out["looking_from"][2] > 0


def test_view_cube_setting(win):
    vp = win.viewport
    from modeler.gui.main_window import set_view_cube_enabled, view_cube_enabled

    set_view_cube_enabled(win, False)
    wait()
    assert not vp.cube.visible and not view_cube_enabled(win)
    assert all(not b.isVisible() for b in vp.cube.buttons.values())
    set_view_cube_enabled(win, True)
    wait()
    assert vp.cube.visible and all(b.isVisible() for b in vp.cube.buttons.values())


# ---- item 94: the Tutorial panel -------------------------------------------------------------------
def test_help_menu_opens_the_tutorial_list(win):
    assert not win.tutorial_dock.isVisible()
    act = next(a for a in win.shell.help_menu.actions() if a.text().replace("&", "") == "Tutorials")
    act.trigger()
    wait()
    tp = win.tutorial_panel
    assert win.tutorial_dock.isVisible()
    html = tp.body.toHtml()
    assert "Your first part" in html and "Fixing a step that failed" in html
    assert not tp.next.isVisible()


def test_tutorial_panel_follows_the_model(win):
    tp = win.tutorial_panel
    tp.start("first_part")
    wait()
    assert win.tutorial_dock.isVisible()
    assert win.tutorial_dock.height() > win.tree_dock.height()  # room to read the step
    assert not win.props_dock.visibleRegion().isEmpty()  # the panel the lesson uses is in front
    assert "step 1 of 6" in tp.heading.text() and not tp.next.isEnabled() and not tp.back.isEnabled()
    assert "○ a body in the model" in tp.checks.text()
    # the user does the step by typing (any way works): the panel notices
    run(win, "BLOCK, 0,0,0, 60,40,10")
    assert wait_for(lambda: tp.next.isEnabled())
    assert "✓ a body in the model" in tp.checks.text() and "Done!" in tp.checks.text()
    tp.next.click()
    wait()
    assert "step 2 of 6" in tp.heading.text() and tp.back.isEnabled()
    assert "nothing is called plate" in tp.checks.text()
    # the Properties panel's name row, as the step says
    win.execute("PICK, BODY, 1")
    assert wait_for(lambda: win.props_panel.target == "1" and "name" in _props_rows(win.props_panel))
    wait()
    _props_rows(win.props_panel)["name"].setText("plate")
    wait()
    assert win.processor.history[-1].text.startswith("NAME"), win.output.toPlainText()[-500:]
    assert wait_for(lambda: tp.next.isEnabled())
    tp.next.click()
    wait()
    # Show me does step 3
    tp.show_me.click()
    assert wait_for(lambda: tp.next.isEnabled())
    assert "✓ 80 long" in tp.checks.text()
    tp.back.click()
    wait()
    assert "step 2 of 6" in tp.heading.text() and tp.next.isEnabled()
    tp.stop.click()
    wait()
    assert win.processor.tutorial is None and "Tutorials" in tp.heading.text()
    assert win.processor.model.bodies  # the model stays
    assert not win.item_panel.isVisible()
    win.tutorial_dock.close()
    wait()
    assert win.item_panel.isVisible()  # back under the model tree


def test_tutorial_to_the_end_and_finish(win):
    tp = win.tutorial_panel
    tp.start("sketch_to_solid")
    wait()
    for _ in range(5):
        tp.show_me.click()
        assert wait_for(lambda: tp.next.isEnabled()), tp.checks.text()
        tp.next.click()
        wait()
    assert tp.next.text() == "Finish" and not tp.show_me.isEnabled() and tp.next.isEnabled()
    tp.next.click()
    wait()
    assert win.processor.tutorial is None and "finished" in win.output.toPlainText()


def test_starting_asks_before_losing_unsaved_work(win, monkeypatch):
    tp = win.tutorial_panel
    run(win, "BLOCK, 0,0,0, 5,5,5")
    answers = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: answers.append(a[2]) or QMessageBox.Cancel)
    assert tp.start("first_part") is None
    assert win.processor.tutorial is None and len(win.processor.history) == 1
    assert "not saved" in answers[0]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    assert tp.start("first_part").ok
    assert win.processor.tutorial is not None and win.processor.history == []


def test_tutorial_starts_from_the_list_link(win):
    from PySide6.QtCore import QUrl

    win.show_tutorials()
    win.tutorial_panel.body.anchorClicked.emit(QUrl("start:fix_a_step"))
    wait(300)
    lesson = win.processor.tutorial
    assert lesson is not None and lesson.tut.name == "fix_a_step"
    # its own start steps: the fillet is red in History
    hp = win.history_panel
    assert any(not e.ok for e in win.processor.history)
    assert hp.rowCount() == len(win.processor.history) == 6


def _props_rows(pp):
    out = {}
    for i in range(pp.table.rowCount()):
        k, v = pp.table.item(i, 0), pp.table.item(i, 1)
        if k is not None and v is not None and k.data(Qt.UserRole):
            out[k.data(Qt.UserRole)] = v
    return out


# ---- item 94: layouts ---------------------------------------------------------------------------------
def _visible(win):
    return {n for n, d in win.layouts.docks().items() if d.isVisible()}


def test_built_in_layouts(win):
    run(win, "LAYOUT, sculpt")
    assert _visible(win) == set() and win.ribbon.current_title() == "Sculpt"
    run(win, "LAYOUT, sketch")
    assert _visible(win) == {"model", "properties"}
    assert win.ribbon.current_title() == "Features"  # no sketch open
    run(win, "SKETCH, s, XY\nLAYOUT, sketch")
    assert win.ribbon.current_title() == "Sketch"
    run(win, "ENDSKETCH\nLAYOUT, drawing")
    assert _visible(win) == {"output", "history", "parameters"} and win.ribbon.current_title() == "Inspect"
    run(win, "LAYOUT, modelling")
    assert {"model", "properties", "parameters"} == _visible(win)
    assert win.layouts.current == "modelling"
    run(win, "LAYOUT, RESET")
    assert {"model", "properties", "parameters"} == _visible(win)
    assert "tutorial" not in _visible(win)


def test_saved_layouts_last_between_sessions(app, tmp_path, monkeypatch):
    w = _make(app, tmp_path, monkeypatch, "keep.ini")
    try:
        run(w, "LAYOUT, drawing")
        w.layouts.docks()["model"].show()
        run(w, "LAYOUT, SAVE, Review")
        run(w, "LAYOUT, RESET")
        assert _visible(w) == {"model", "properties", "parameters"}  # History, Layers ... open on demand
    finally:
        w.shell.confirm_discard = lambda *_: True
        w.close()
    w2 = _make(app, tmp_path, monkeypatch, "keep.ini")
    try:
        assert w2.layouts.saved_names() == ["Review"]
        run(w2, "LAYOUT, review")  # any case
        assert _visible(w2) == {"output", "history", "parameters", "model"}
        assert w2.ribbon.current_title() == "Inspect"
        menu = w2.layouts.menu
        w2.layouts._fill(__import__("modeler.commands.layout_handlers", fromlist=["x"]).BUILT_IN)
        texts = [a.text() for a in menu.actions() if a.text()]
        assert texts[:5] == ["Modelling", "Sketch", "Assembly", "Drawing", "Sculpt"]
        assert "Review" in texts and "Save this layout…" in texts and "Reset" in texts
        review = next(a for a in menu.actions() if a.text() == "Review")
        assert review.isChecked()
        run(w2, "LAYOUT, DELETE, review")
        assert w2.layouts.saved_names() == []
    finally:
        w2.shell.confirm_discard = lambda *_: True
        w2.close()


def test_layout_menu_runs_the_command(win):
    menu = win.layouts.menu
    act = next(a for a in menu.actions() if a.text() == "Sculpt")
    act.trigger()
    wait()
    assert last_output(win) == "LAYOUT, sculpt" and _visible(win) == set()


# ---- item 94: pictures in tooltips -----------------------------------------------------------------
def test_ribbon_tooltips_have_pictures(win):
    from modeler.gui import picture_tips as pt
    from modeler.gui import toolbars

    acts = {a.text(): a for tb in toolbars.groups(win) for a in tb.actions() if a.text()}
    assert "<img" in acts["Block…"].toolTip() and "block.png" in acts["Block…"].toolTip()
    assert "Runs: BLOCK" in acts["Block…"].toolTip()
    assert "<img" in acts["Fillet…"].toolTip()
    assert "<img" not in win.undo_action.toolTip()  # nothing to show for undo (a quick-access icon)
    with_pictures = sum("<img" in a.toolTip() for a in acts.values())
    assert with_pictures >= 100
    pt.set_enabled(win, False)
    assert "<img" not in acts["Block…"].toolTip() and acts["Block…"].toolTip().startswith("Add a block")
    assert not pt.enabled(win)
    pt.set_enabled(win, True)
    assert "<img" in acts["Block…"].toolTip()


def test_picture_tooltips_survive_a_language_switch(win):
    from modeler import i18n
    from modeler.gui import picture_tips as pt
    from modeler.gui import prefs, toolbars

    def block():
        return next(a for tb in toolbars.groups(win) for a in tb.actions() if "Runs: BLOCK" in (a.property(pt.PLAIN) or ""))

    try:
        prefs.apply_language(win, "de", remember=False)
        a = block()
        assert "<img" in a.toolTip() and "block.png" in a.toolTip()
        assert a.toolTip().count("<img") == 1  # not wrapped twice
        assert win.tutorial_panel.next.text() == "Weiter"
        win.execute("TUTORIAL, first_part, NEW")
        assert win.tutorial_panel.next.text() == "Weiter"  # still German after the panel refreshes
        win.execute("TUTORIAL, STOP")
        pt.set_enabled(win, False)
        assert "<img" not in a.toolTip()
        pt.set_enabled(win, True)
        prefs.apply_language(win, "en", remember=False)
        assert a.toolTip().count("<img") == 1 and "Runs: BLOCK" in a.toolTip()
    finally:
        i18n.set_language("en")
        pt.set_enabled(win, True)


def test_preferences_has_the_new_settings(win):
    from modeler.gui import prefs

    dlg = prefs.open_dialog(win)
    wait()
    try:
        assert dlg.picture_tips.isChecked() and dlg.view_cube.isChecked()
        dlg.picture_tips.setChecked(False)
        from modeler.gui import toolbars

        acts = {a.text(): a for tb in toolbars.groups(win) for a in tb.actions() if a.text()}
        assert "<img" not in acts["Block…"].toolTip()
    finally:
        dlg.picture_tips.setChecked(True)
        dlg.close()
