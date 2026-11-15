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
from PySide6.QtWidgets import QApplication  # noqa: E402

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
