"""PLAN items 86-88 in the window: the numbers of the pick in the status bar and on
hover, the typed-value boxes while sketching, and the start page with its
templates, recent projects (with pictures) and examples (needs a display: run
under xvfb-run)."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QPoint, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from modeler.gui import sel_numbers, start_page  # noqa: E402
from modeler.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def pump(app, n=10):
    for _ in range(n):
        app.processEvents()


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    monkeypatch.setenv("MODELER_TEMPLATES", str(tmp_path / "data" / "templates"))
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    w = MainWindow(autosave="off", settings=settings)
    w.resize(1300, 850)
    w.show()
    for _ in range(40):
        app.processEvents()
        if w.viewport._initialized:
            break
    assert w.viewport._initialized
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    page = getattr(w.shell, "start_page", None)
    if page is not None:
        page.close()
    w.close()


def run(win, text):
    for line in text.splitlines():
        res = win.execute(line)
        assert res.ok, res.message


def move(vp, pt):
    """A mouse move with no button held, delivered at once (QTest.mouseMove waits on the X server)."""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent

    ev = QMouseEvent(QEvent.MouseMove, QPointF(pt), QPointF(vp.mapToGlobal(pt)), Qt.NoButton, Qt.NoButton,
                     Qt.NoModifier)
    QApplication.sendEvent(vp, ev)


def settle(app, ms=150):
    QTest.qWait(ms)
    pump(app)


# ---- item 86 ------------------------------------------------------------------------------
def test_status_bar_shows_the_numbers_of_the_pick(app, win):
    label = win.sel_numbers
    assert label.parent() is not None and label.isVisible()
    run(win, "BLOCK, 0,0,0, 20,10,5\nCYL, 40,0,0, 5, 5\nMATERIAL, 1, STEEL")
    assert label.text() == ""
    run(win, "PICK, FACE, 6")
    settle(app)
    assert label.text() == "face 6: plane, area 200 mm²"
    run(win, "PICK, FACE, 5 6")
    settle(app)
    assert label.text() == "2 faces, distance 5 mm (dz 5), parallel, facing away, total area 400 mm²"
    assert "face 5: plane, area 200 mm2" in label.toolTip()
    run(win, "PICK, BODY, 1")
    settle(app)
    assert label.text().startswith("body 1: volume 1000 mm³, area 700 mm², mass 0.00785 kg (steel)")
    run(win, "SEL, NONE")
    settle(app)
    assert label.text() == "" and "Pick a face" in label.toolTip()


def test_click_copies_the_numbers(app, win):
    run(win, "BLOCK, 0,0,0, 20,10,5\nPICK, FACE, 1 2")
    settle(app)
    QTest.mouseClick(win.sel_numbers, Qt.LeftButton)
    clip = QGuiApplication.clipboard().text()
    assert clip.startswith("2 faces, distance 20 mm") and "face 1: plane, area 50 mm2" in clip
    assert "Copied" in win.statusBar().currentMessage()


def test_the_numbers_follow_an_edit_of_the_model(app, win):
    run(win, "W = 20\nBLOCK, 0,0,0, W,10,5\nPICK, FACE, 6")
    settle(app)
    assert "area 200" in win.sel_numbers.text()
    run(win, 'HIST, EDIT, 1, "W = 30"')
    settle(app)
    assert "area 300" in win.sel_numbers.text()


def test_hover_tooltip_shows_what_the_mouse_rests_on(app, win, monkeypatch):
    run(win, "BLOCK, 0,0,0, 20,10,5\nNAME, LAST, plate\nVIEW, ISO")
    pump(app)
    vp = win.viewport
    x, y = vp.view.Convert(10, 5, 5)  # the middle of the top face
    vp._hover_px = (x, y)
    monkeypatch.setattr(vp, "underMouse", lambda: True)
    got = []
    vp.hovered.connect(lambda k, g, at: got.append((k, g)))
    vp._rested()
    pump(app)
    assert got == [("FACE", 6)]
    assert win.hover_numbers.text == "face 6: plane, area 200 mm²\non body 1 (plate)"
    vp._hover_gone()  # the mouse moves on
    assert win.hover_numbers.text == "" and win.hover_numbers.last is None
    # Preferences > Numbers on hover: off
    sel_numbers.set_hover_enabled(win, False)
    vp._rested()
    assert win.hover_numbers.text == ""
    sel_numbers.set_hover_enabled(win, True)
    assert sel_numbers.hover_enabled(win)


def test_hover_waits_for_the_mouse_to_rest(app, win, monkeypatch):
    run(win, "BLOCK, 0,0,0, 20,10,5\nVIEW, ISO")
    pump(app)
    vp = win.viewport
    monkeypatch.setattr(vp, "underMouse", lambda: True)
    got = []
    vp.hovered.connect(lambda k, g, at: got.append(k))
    r = vp.devicePixelRatioF()
    x, y = vp.view.Convert(10, 5, 5)
    move(vp, QPoint(int(x / r), int(y / r)))
    pump(app)
    assert got == [] and vp._rest.isActive()  # not at once
    QTest.qWait(vp._rest.interval() + 200)
    pump(app)
    assert got[:1] == ["FACE"]


def test_no_hover_numbers_while_sketching(app, win, monkeypatch):
    run(win, "BLOCK, 0,0,0, 20,10,5\nSKETCH, s, XY")
    vp = win.viewport
    vp._hover_px = vp.view.Convert(10, 5, 5)
    monkeypatch.setattr(vp, "underMouse", lambda: True)
    got = []
    vp.hovered.connect(lambda *a: got.append(a))
    vp._rested()
    assert got == []


# ---- item 87 ------------------------------------------------------------------------------
def sketch_at(win, app):
    vp = win.viewport
    run(win, "SKETCH, s, XY")
    pump(app, 20)
    vp.view.SetSize(120)
    vp.view.Redraw()
    pump(app)

    def at(u, v):
        x, y = vp.pixel_of(u, v)
        r = vp.devicePixelRatioF()
        return QPoint(int(round(x / r)), int(round(y / r)))

    return vp, at


def test_typed_values_draw_a_line_with_sizes(app, win):
    vp, at = sketch_at(win, app)
    win.sketch_ui.tool_actions["LINE"].trigger()
    move(vp, at(0, 0))
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at(0, 0))
    pump(app, 3)
    move(vp, at(20, 7))
    pump(app, 3)
    boxes = win.value_boxes
    assert boxes.isVisible() and [b.text().split(" ")[0] for b in boxes.boxes if b.isVisible()] == ["length", "angle"]
    vp.setFocus()
    QTest.keyClicks(vp, "40")
    pump(app)
    assert boxes.boxes[0].text() == "length 40▏"
    QTest.keyClick(vp, Qt.Key_Tab)
    pump(app)
    assert boxes.boxes[0].text() == "length = 40" and "angle" in boxes.boxes[1].text()
    QTest.keyClicks(vp, "30")
    QTest.keyClick(vp, Qt.Key_Return)
    pump(app, 5)
    texts = [e.text for e in win.processor.history]
    assert "SDIM, LENGTH, 1, 40" in texts and "SDIM, ANGLE, 1, 30" in texts
    sk = win.processor.model.sketches["S"]
    assert sk.measure("LENGTH", ("1",)) == pytest.approx(40) and sk.measure("ANGLE", ("1",)) == pytest.approx(30)
    QTest.keyClick(vp, Qt.Key_Escape)  # end the chain: the boxes go
    move(vp, at(5, 5))
    pump(app)
    assert not boxes.isVisible()


def test_letters_type_a_parameter_not_a_tool_shortcut(app, win):
    run(win, "R1 = 6")
    vp, at = sketch_at(win, app)
    win.sketch_ui.tool_actions["CIRCLE"].trigger()
    move(vp, at(0, 0))
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at(0, 0))
    move(vp, at(4, 1))
    pump(app, 3)
    vp.setFocus()
    QTest.keyClick(vp, Qt.Key_Tab)  # open the radius box, so a name can be typed
    QTest.keyClicks(vp, "R1")  # R is the Rectangle shortcut, but not while typing
    pump(app)
    assert win.sketch_ui.controller.tool == "CIRCLE"
    QTest.keyClick(vp, Qt.Key_Return)
    pump(app, 5)
    texts = [e.text for e in win.processor.history]
    assert any(t.startswith("SCIRCLE, ORIGIN, R1") for t in texts) and "SDIM, RADIUS, 1, R1" in texts


def test_clicking_a_box_starts_typing_into_it(app, win):
    vp, at = sketch_at(win, app)
    win.sketch_ui.tool_actions["RECT"].trigger()
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at(0, 0))
    move(vp, at(10, 6))
    pump(app, 3)
    boxes = win.value_boxes
    QTest.mouseClick(boxes.boxes[1], Qt.LeftButton)  # the height box
    pump(app)
    assert win.sketch_ui.controller.typed.focus == 1
    QTest.keyClicks(vp, "8")
    QTest.keyClick(vp, Qt.Key_Return)
    pump(app, 5)
    sk = win.processor.model.sketches["S"]
    assert sk.measure("LENGTH", ("2",)) == pytest.approx(8)
    assert "SDIM, LENGTH, 2, 8" in [e.text for e in win.processor.history]


def test_a_bad_value_is_said_in_the_boxes(app, win):
    vp, at = sketch_at(win, app)
    win.sketch_ui.tool_actions["LINE"].trigger()
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at(0, 0))
    move(vp, at(10, 3))
    pump(app, 3)
    vp.setFocus()
    QTest.keyClicks(vp, "-4")
    QTest.keyClick(vp, Qt.Key_Return)
    pump(app)
    assert win.value_boxes.note.isVisible() and "more than 0" in win.value_boxes.note.text()
    assert not any(e.text.startswith("SLINE") for e in win.processor.history)


def test_closing_the_sketch_hides_the_boxes(app, win):
    vp, at = sketch_at(win, app)
    win.sketch_ui.tool_actions["LINE"].trigger()
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at(0, 0))
    move(vp, at(10, 3))
    pump(app, 3)
    assert win.value_boxes.isVisible()
    run(win, "ENDSKETCH")
    pump(app, 10)
    assert not win.value_boxes.isVisible()


# ---- item 88 ------------------------------------------------------------------------------
def test_file_new_opens_the_start_page_with_the_templates(app, win):
    win.shell.new_action.trigger()
    pump(app)
    page = win.shell.start_page
    assert page.isVisible()
    titles = [c.title_label.text() for c in page.cards.values()]
    assert titles[:4] == ["<b>New part</b>", "<b>New assembly</b>", "<b>New sheet metal part</b>",
                          "<b>New drawing</b>"] and titles[-1] == "<b>Empty project</b>"
    assert "Runs: NEW, sheet_metal" in page.cards["sheet_metal"].toolTip()
    page.cards["sheet_metal"].click()
    pump(app, 10)
    assert not page.isVisible()
    m = win.processor.model
    assert m.active_sketch == "BASE" and win.processor.evaluate("T") == 2
    assert not win.isWindowModified()  # a fresh project is not unsaved work
    assert win.sketch_ui.toolbar.isVisible()


def test_start_page_asks_before_dropping_work(app, win):
    run(win, "BLOCK, 0,0,0, 1,1,1")
    page = win.shell.show_start_page()
    win.shell.ask_unsaved = lambda *_: "cancel"
    page.cards["part"].click()
    pump(app)
    assert len(win.processor.model.bodies) == 1 and page.isVisible()
    win.shell.ask_unsaved = lambda *_: "discard"
    page.cards[""].click()
    pump(app)
    assert not win.processor.model.bodies and win.processor.cursor == 0


def test_recent_projects_have_pictures(app, win, tmp_path):
    path = str(tmp_path / "plate.m3d").replace("\\", "/")
    run(win, "BLOCK, 0,0,0, 30,20,5\nVIEW, ISO\nFIT")
    pump(app)
    run(win, f'SAVE, "{path}"')
    thumb = start_page.thumb_path(path)
    assert os.path.isfile(thumb) and os.path.getsize(thumb) > 500
    assert thumb.startswith(str(tmp_path / "data"))
    page = win.shell.show_start_page()
    item = page.recent.item(0)
    assert item.text() == "plate" and not item.icon().isNull()
    win.shell.ask_unsaved = lambda *_: "discard"
    win.shell.new()
    page._open_recent(item)
    pump(app)
    assert len(win.processor.model.bodies) == 1 and win.processor.project_path


def test_examples_open_from_the_start_page(app, win):
    page = win.shell.show_start_page()
    assert page.examples.count() > 10
    names = [page.examples.item(i).text() for i in range(page.examples.count())]
    i = names.index("plate")
    win.shell.ask_unsaved = lambda *_: "discard"
    page._open_example(page.examples.item(i))
    pump(app, 5)
    assert win.processor.model.bodies


def test_save_a_template_from_the_start_page(app, win, monkeypatch):
    run(win, "NEW, part\nLAYER, welds, NEW, RED")
    page = win.shell.show_start_page()
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("welded_part", True))
    page.save_template()
    pump(app)
    page = win.shell.start_page  # it opens again with the new card
    assert "welded_part" in page.cards and "(yours)" in page.cards["welded_part"].title_label.text()


def test_start_page_setting(app, win):
    assert start_page.enabled(win)
    page = win.shell.show_start_page()
    page.show_at_start.setChecked(False)
    assert not start_page.enabled(win)
    page.show_at_start.setChecked(True)
    assert start_page.enabled(win)


def test_preferences_have_the_new_switches(app, win):
    from modeler.gui.prefs import PreferencesDialog

    dlg = PreferencesDialog(win)
    assert dlg.hover_numbers.isChecked() and dlg.start_page.isChecked()
    dlg.hover_numbers.setChecked(False)
    assert not sel_numbers.hover_enabled(win)
    dlg.start_page.setChecked(False)
    assert not start_page.enabled(win)
    dlg.close()
