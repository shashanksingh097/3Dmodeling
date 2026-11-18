"""GUI test of sketch mode: real mouse clicks in the 3D view turn into
sketch commands, and the Sketch toolbar shows only while a sketch is open."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolBar  # noqa: E402

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
    w.resize(1000, 700)
    w.show()
    for _ in range(40):
        app.processEvents()
        if w.viewport._initialized:
            break
    assert w.viewport._initialized, "3D view did not initialize"
    yield w
    w.close()


def test_draw_a_rectangle_by_mouse_and_extrude(app, win):
    vp = win.viewport
    assert not win.sketch_ui.toolbar.isVisible()
    win.execute("SKETCH, s, XY")
    pump(app, 20)
    assert win.sketch_ui.toolbar.isVisible()
    vp.view.SetSize(120)
    vp.view.Redraw()
    pump(app)

    def at(u, v):
        x, y = vp.pixel_of(u, v)
        r = vp.devicePixelRatioF()
        return QPoint(int(x / r), int(y / r))

    win.sketch_ui.tool_actions["RECT"].trigger()
    for u, v in [(-20, -10), (20, 10)]:
        p = at(u, v)
        QTest.mouseMove(vp, p)
        pump(app, 2)
        QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, p)
        pump(app, 3)
    sk = win.processor.model.sketches["S"]
    assert len(sk.geos) == 4
    lo, hi = sk.pt(sk.geos[1].pts["S"]), sk.pt(sk.geos[2].pts["E"])
    assert abs(hi[0] - lo[0] - 40) < 3 and abs(hi[1] - lo[1] - 20) < 3
    assert any(e.text.startswith("SRECT") for e in win.processor.history)
    win.execute("EXTRUDE, s, 5")
    pump(app, 20)
    assert not win.sketch_ui.toolbar.isVisible()  # using the sketch closed it
    assert win.processor.model.active_sketch is None
    assert len(win.processor.model.bodies) == 1


def test_fillet_and_trim_by_mouse_and_offset_from_the_toolbar(app, win, monkeypatch):
    vp = win.viewport
    win.execute("SKETCH, s, XY")
    win.execute("SRECT, -20,-10, 20,10")
    win.execute("SLINE, 0,-20, 0,20")
    pump(app, 20)
    vp.view.SetSize(120)
    vp.view.Redraw()
    pump(app)

    def at(u, v):
        x, y = vp.pixel_of(u, v)
        r = vp.devicePixelRatioF()
        return QPoint(int(x / r), int(y / r))

    def click(u, v):
        q = at(u, v)
        QTest.mouseMove(vp, q)
        pump(app, 2)
        QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, q)
        pump(app, 3)

    win.sketch_ui.tool_actions["FILLET"].trigger()
    click(20, 10)  # the top right corner
    sk = win.processor.model.sketches["S"]
    assert any(g.kind == "ARC" for g in sk.geos.values())
    assert win.processor.history[win.processor.cursor - 1].text.startswith("SFILLET, 2.E")
    win.sketch_ui.tool_actions["TRIM"].trigger()
    click(0, 16)  # the part of the upright line above the rectangle
    sk = win.processor.model.sketches["S"]
    assert abs(sk.pt(sk.geos[5].pts["E"])[1] - 10) < 1e-6
    win.execute("SSEL, 1, 2, 3, 4, 7")
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("2", True))
    win.sketch_ui.edit_actions["Offset"].trigger()
    pump(app, 5)
    assert win.processor.history[win.processor.cursor - 1].text == "SOFFSET, 2, 1, 2, 3, 4, 7"


def _drag(app, vp, pts):
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, pts[0])
    pump(app, 2)
    for p in pts[1:]:
        QTest.mouseMove(vp, p)
        pump(app, 1)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, pts[-1])
    pump(app, 5)


def test_freehand_stroke_becomes_a_closed_spline_to_extrude(app, win):
    import math

    vp = win.viewport
    win.execute("SKETCH, s, XY")
    pump(app, 20)
    vp.view.SetSize(120)
    vp.view.Redraw()
    pump(app)

    def at(u, v):
        x, y = vp.pixel_of(u, v)
        r = vp.devicePixelRatioF()
        return QPoint(int(x / r), int(y / r))

    win.sketch_ui.tool_actions["FREEHAND"].trigger()
    loop = [at(20 * math.cos(a / 40 * 2 * math.pi), 12 * math.sin(a / 40 * 2 * math.pi)) for a in range(41)]
    _drag(app, vp, loop)
    sk = win.processor.model.sketches["S"]
    assert [g.kind for g in sk.geos.values()] == ["SPLINE"] and sk.geos[1].closed
    assert win.processor.history[-1].text.startswith("SSPLINE") and win.processor.history[-1].text.endswith("CLOSE")
    win.execute("EXTRUDE, s, 5")
    pump(app, 20)
    from modeler.geometry import robust

    (body,) = win.processor.model.bodies.values()
    assert abs(robust.volume(body.shape) - math.pi * 20 * 12 * 5) < 0.05 * math.pi * 20 * 12 * 5


def test_knife_stroke_cuts_a_block_along_the_view(app, win):
    vp = win.viewport
    win.execute("BLOCK, -20, -10, 0, 40, 20, 10")
    win.execute("VIEW, TOP")
    win.execute("FIT")
    pump(app, 20)
    win.knife_action.trigger()
    assert vp.knife
    r = vp.devicePixelRatioF()

    def at(x, y, z=5.0):
        px, py = vp.view.Convert(x, y, z)
        return QPoint(int(px / r), int(py / r))

    _drag(app, vp, [at(-5 + i * 0.5, -16 + i * 1.6) for i in range(21)])
    texts = [e.text for e in win.processor.history]
    assert texts[-1].startswith("KNIFE, 1, LAST, 0"), texts[-2:]
    m = win.processor.model
    assert texts[-2].startswith(("SPLINE", "LINE")) and m.last_body in m.bodies
    assert len(m.hidden) == 1  # the stroke
    assert len([b for b in m.bodies.values() if robust_solid(b.shape)]) == 2
    vp.set_knife(False)
    assert not win.knife_action.isChecked()


def robust_solid(shape):
    from modeler.geometry import robust

    return bool(robust.solids(shape))


def test_toolbar_groups_have_icons_and_names_and_one_style_setting(app, win):
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QImage

    from modeler.gui import icons
    from modeler.gui import toolbars as tbs

    for name in icons.NAMES:  # every icon draws something
        img = icons.pixmap(name).toImage().convertToFormat(QImage.Format_ARGB32)
        assert any(img.pixelColor(x, y).alpha() > 0 for x in range(0, img.width(), 2)
                   for y in range(0, img.height(), 2)), name
    titles = [tb.windowTitle() for tb in tbs.groups(win)]
    for t in ("File", "Edit", "Shapes", "Booleans", "Patterns", "Pick", "View", "Sketch", "Features", "Measure",
              "Sketch draw", "Sketch edit", "Constraints", "Sizes"):
        assert t in titles, t
    for tb in tbs.groups(win):
        for a in tb.actions():
            if a.text():
                assert not a.icon().isNull(), a.text()
                assert a.property("icon_name") in icons.NAMES
    tbs.set_style(win, "icons")
    assert all(tb.toolButtonStyle() == _Qt.ToolButtonIconOnly for tb in tbs.groups(win))
    assert win.shell.settings.value(tbs.SETTING) == "icons"
    win._style_actions["under"].trigger()
    assert all(tb.toolButtonStyle() == _Qt.ToolButtonTextUnderIcon for tb in tbs.groups(win))
    # every group is on a ribbon tab: one row of tabs, not rows of toolbars
    rb = win.ribbon
    assert rb.visible_titles() == ["Home", "Model", "Features", "Freeform", "Sculpt", "Inspect"]
    assert all(tb.property("tab") for tb in tbs.groups(win))
    for area in (_Qt.LeftToolBarArea, _Qt.RightToolBarArea, _Qt.BottomToolBarArea):
        assert not [t for t in win.findChildren(QToolBar) if t.isVisible() and win.toolBarArea(t) == area]
    rows = {win.toolBarArea(t) for t in win.findChildren(QToolBar) if t.parent() is win and t.isVisible()
            and not t.property("group")}
    assert rows == {_Qt.TopToolBarArea}
    rb.select("Model")
    pump(app, 5)
    assert rb.current_title() == "Model"
    assert win.shell.settings.value(tbs.TAB_SETTING) == "Model"
    # the quick-access icons stay in reach on every tab
    assert win.undo_action in win.quick_access.actions()
    assert win._mode_actions["EDGE"] in win.quick_access.actions()
    # the sketch tabs come and go together with sketch mode
    sketch_bars = win.sketch_ui.toolbars
    assert len(sketch_bars) == 4 and not any(tb.isVisible() for tb in sketch_bars)
    win.execute("SKETCH, s, XY")
    pump(app, 10)
    assert rb.visible_titles()[-3:] == ["Sketch", "Sketch edit", "Constrain"]
    assert rb.current_title() == "Sketch" and sketch_bars[0].isVisible()
    rb.select("Constrain")
    pump(app, 5)
    assert sketch_bars[2].isVisible() and sketch_bars[3].isVisible()
    win.execute("ENDSKETCH")
    pump(app, 10)
    assert not any(tb.isVisible() for tb in sketch_bars)
    assert rb.current_title() == "Model"  # back to the tab used before the sketch
    # folding the ribbon to its tab names
    full = rb.sizeHint().height()
    win.collapse_ribbon_action.trigger()
    pump(app, 5)
    assert rb.collapsed and rb.maximumHeight() < full
    rb.tabBarDoubleClicked.emit(0)
    pump(app, 5)
    assert not rb.collapsed and not win.collapse_ribbon_action.isChecked()


def test_power_trim_by_dragging_across_curves(app, win):
    vp = win.viewport
    win.execute("SKETCH, s, XY")
    win.execute("SLINE, -30,0, 30,0")
    win.execute("SLINE, -10,-10, -10,10")
    win.execute("SLINE, 10,-10, 10,10")
    pump(app, 20)
    vp.view.SetSize(120)
    vp.view.Redraw()
    pump(app)

    def at(u, v):
        x, y = vp.pixel_of(u, v)
        r = vp.devicePixelRatioF()
        return QPoint(int(x / r), int(y / r))

    win.sketch_ui.tool_actions["TRIM"].trigger()
    # across the two upright lines above the long one, and across the long one's middle
    _drag(app, vp, [at(-15, 6), at(-10, 6), at(-5, 6), at(0, 4), at(0, 0), at(0, -2), at(5, 6), at(10, 6), at(15, 6)])
    last = win.processor.history[win.processor.cursor - 1].text
    assert last.startswith("STRIM, ") and last.count(",") >= 8, last
    sk = win.processor.model.sketches["S"]
    tops = [sk.pt(sk.geos[n].pts["E"])[1] for n in (2, 3)]
    assert all(abs(t) < 1e-6 for t in tops)  # both upright lines cut back to the long one


def test_move_copy_button_runs_stransform(app, win, monkeypatch):
    from modeler.gui import sketch_ui

    win.execute("SKETCH, s, XY")
    win.execute("SRECT, 0,0, 20,10")
    win.execute("SSEL, 1, 2, 3, 4")
    pump(app, 5)

    def fake_exec(self):
        self.kind.setCurrentText("Rotate")
        self.values.setText("90, O")
        self.copy.setChecked(True)
        return sketch_ui.QDialog.Accepted

    monkeypatch.setattr(sketch_ui.TransformForm, "exec", fake_exec)
    win.sketch_ui.edit_actions["Move/Copy"].trigger()
    pump(app, 5)
    assert win.processor.history[win.processor.cursor - 1].text == "STRANSFORM, ROTATE, 90, O, 1, 2, 3, 4, COPY"
    assert len(win.processor.model.sketches["S"].geos) == 8
