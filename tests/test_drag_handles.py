"""PLAN item 68: drag handles. The handle logic is headless (gui/drag_handles.py); the
last tests drive the real 3D view and need a display (run under xvfb-run)."""

import math
import os
import sys

import pytest

from modeler.commands import Processor
from modeler.gui import drag_handles as dh


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def _ortho_top(scale=10.0):
    """A pretend top view: x right, y up, looking down -Z, `scale` pixels a unit."""
    def to_pixel(q):
        return (q[0] * scale, -q[1] * scale)

    def ray(x, y):
        return ((x / scale, -y / scale, 100.0), (0.0, 0.0, -1.0))
    return to_pixel, ray


def test_body_handles_write_move_and_rotate():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nNAME, LAST, plate\nPICK, BODY, 1")
    hs = dh.Handles.for_model(p.model)
    assert hs.mode == "BODY" and hs.centre == pytest.approx((20, 10, 5))
    assert [h.kind for h in hs.items] == ["MOVE"] * 3 + ["TURN"] * 3
    to_pixel, ray = _ortho_top()
    xh = next(h for h in hs.items if h.name == "X" and h.kind == "MOVE")
    mid = tuple((a + b) / 2 for a, b in zip(xh.origin, xh.tip))
    assert hs.press(*to_pixel(mid), to_pixel, ray)
    assert hs.drag.handle is xh
    end = (mid[0] + 7.3, mid[1] + 2, mid[2])
    hs.move(ray(*to_pixel(end)))
    assert hs.amount == pytest.approx(7)  # snapped to the 1 mm grid
    hs.move(ray(*to_pixel(end)), free=True)
    assert hs.amount == pytest.approx(7.3)
    assert "move X 7.3" in hs.readout()
    text = hs.release()
    assert text == "MOVE, plate, 7.3, 0, 0"
    ok(p, text)
    assert p.evaluate("BBOX(plate)").get("xmin") == pytest.approx(7.3)


def test_ring_turns_about_the_middle_in_snapped_steps():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nPICK, BODY, 1")
    hs = dh.Handles.for_model(p.model)
    to_pixel, ray = _ortho_top()
    ring = next(h for h in hs.items if h.name == "Z" and h.kind == "TURN")
    r, c = ring.size, ring.origin
    s0 = math.radians(45)  # off the arrows, which run through the ring at 0 and 90 degrees
    start = (c[0] + r * math.cos(s0), c[1] + r * math.sin(s0), c[2])
    assert hs.press(*to_pixel(start), to_pixel, ray)
    assert hs.drag.handle is ring
    a = math.radians(45 + 32)
    hs.move(ray(*to_pixel((c[0] + r * math.cos(a), c[1] + r * math.sin(a), c[2]))))
    assert hs.amount == pytest.approx(30)  # 5 degree steps
    assert hs.release() == "ROTATE, 1, 30, 20, 10, 5, 0, 0, 1"


def test_typed_value_wins_and_escape_cancels():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nPICK, BODY, 1")
    hs = dh.Handles.for_model(p.model)
    to_pixel, ray = _ortho_top()
    yh = next(h for h in hs.items if h.name == "Y" and h.kind == "MOVE")
    assert hs.press(*to_pixel(yh.tip), to_pixel, ray)
    for ch in "12.5":
        assert hs.type_key(ch)
    assert hs.type_key("\b") and hs.type_key("5")
    assert hs.amount == 12.5 and "(typed)" in hs.readout()
    assert hs.release() == "MOVE, 1, 0, 12.5, 0"
    assert hs.press(*to_pixel(yh.tip), to_pixel, ray)
    hs.cancel()
    assert hs.release() is None


def test_face_pull_arrow_writes_pushpull():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nSEL, S, FACE, LOC, X, 40")
    hs = dh.Handles.for_model(p.model)
    assert hs.mode == "FACES"
    pull = hs.items[0]
    assert pull.kind == "PULL" and pull.direction == pytest.approx((1, 0, 0))
    to_pixel, ray = _ortho_top()
    assert hs.press(*to_pixel(pull.tip), to_pixel, ray)
    hs.move(ray(*to_pixel((pull.tip[0] + 4.2, pull.tip[1], 0))))
    text = hs.release()
    assert text == "PUSHPULL, 4"
    ok(p, text)
    assert p.evaluate("BBOX(1)").get("dx") == pytest.approx(44)


def test_handles_command_lists_them_as_data():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nNAME, LAST, plate")
    assert "no handles" in ok(p, "HANDLES").message
    ok(p, "PICK, BODY, 1")
    r = ok(p, "HANDLES")
    rows = r.report["handles"]
    assert r.report["mode"] == "BODY" and len(rows) == 6
    assert rows[0]["writes"] == "MOVE, plate, 1, 0, 0"
    ok(p, "PICK, FACE, 6")
    rows = ok(p, "HANDLES").report["handles"]
    assert rows[0]["kind"] == "PULL" and rows[0]["writes"] == "PUSHPULL, 1"


def test_a_jointed_body_drag_moves_the_linkage():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,30,5\nBLOCK, 0,0,5, 40,30,2\nJOINT, REVOLUTE, EDGE, 2, EDGE, 16\nPICK, BODY, 2")
    r = ok(p, "HANDLES")
    assert r.report["jointed"] and "joint solver" in r.message
    ok(p, "MOVE, 2, 0, 0, 15")  # a drag up: pulled back onto the hinge
    assert p.evaluate("BBOX(2)").get("zmin") == pytest.approx(5, abs=1e-6)


# ---- in the real view --------------------------------------------------------------------
gui = pytest.mark.skipif(os.environ.get("MODELER_GUI_TESTS") == "0"
                         or (sys.platform.startswith("linux") and not os.environ.get("DISPLAY")),
                         reason="needs a display (run under xvfb-run)")


@pytest.fixture
def win():
    from PySide6.QtWidgets import QApplication

    from modeler.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    for _ in range(30):
        app.processEvents()
        if w.viewport._initialized:
            break
    assert w.viewport._initialized
    yield w, app
    w.close()


def _logical(win, q):
    from PySide6.QtCore import QPoint

    x, y = win.viewport.view.Convert(*q)
    r = win.viewport.devicePixelRatioF()
    return QPoint(int(round(x / r)), int(round(y / r)))


@gui
def test_drag_an_arrow_in_the_view_runs_move(win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    w, app = win
    w.execute("BLOCK, 0,0,0, 40,20,10")
    w.execute("VIEW, TOP")
    w.execute("FIT")
    w.execute("PICKMODE, BODY")
    w.execute("PICK, BODY, 1")
    w.handles_action.setChecked(True)
    app.processEvents()
    vp = w.viewport
    hd = vp.handles
    assert hd is not None and hd.mode == "BODY" and len(vp._hd_ais) == 6
    xh = next(h for h in hd.items if h.name == "X" and h.kind == "MOVE")
    a = _logical(w, tuple((p + q) / 2 for p, q in zip(xh.origin, xh.tip)))
    b = _logical(w, tuple((p + q) / 2 + (8 if k == 0 else 0) for k, (p, q) in enumerate(zip(xh.origin, xh.tip))))
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)
    for k in range(1, 6):
        QTest.mouseMove(vp, a + (b - a) * k / 5)
        app.processEvents()
    assert vp._hd_label is not None and vp._hd_label.isVisible()
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, b)
    app.processEvents()
    last = w.processor.history[-1].text
    assert last.startswith("MOVE, 1, "), last
    dx = float(last.split(",")[2])
    assert dx == pytest.approx(8, abs=1.01) and dx == round(dx)  # snapped to whole mm
    assert vp.handles is not None and vp.handles.centre[0] == pytest.approx(20 + dx)


@gui
def test_typed_value_and_escape_in_the_view(win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    w, app = win
    w.execute("BLOCK, 0,0,0, 40,20,10")
    w.execute("VIEW, TOP")
    w.execute("FIT")
    w.execute("SEL, S, FACE, LOC, X, 40")
    w.handles_action.setChecked(True)
    app.processEvents()
    vp = w.viewport
    pull = vp.handles.items[0]
    a = _logical(w, pull.tip)
    n = len(w.processor.history)
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)
    QTest.keyClicks(vp, "2.5")
    QTest.keyClick(vp, Qt.Key_Return)
    app.processEvents()
    assert w.processor.history[-1].text == "PUSHPULL, 2.5"
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, a)
    # Esc leaves the model as it was
    w.execute("SEL, S, FACE, LOC, X, 42.5")
    app.processEvents()
    pull = vp.handles.items[0]
    a = _logical(w, pull.tip)
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)
    QTest.mouseMove(vp, a + (a - a) + type(a)(30, 0))
    QTest.keyClick(vp, Qt.Key_Escape)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, a)
    app.processEvents()
    assert len(w.processor.history) == n + 2  # the PUSHPULL and the SEL; nothing from the cancelled drag
