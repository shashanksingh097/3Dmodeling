"""Dragging a control point in the view writes MOVEPT (needs a display; see test_viewport.py)."""

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


@pytest.fixture
def win(app):
    w = MainWindow()
    w.show()
    for _ in range(20):
        app.processEvents()
        if w.viewport._initialized:
            break
    assert w.viewport._initialized
    yield w
    w.close()


def _logical(win, q):
    x, y = win.viewport.view.Convert(*q)
    r = win.viewport.devicePixelRatioF()
    return QPoint(int(round(x / r)), int(round(y / r)))


def test_drag_a_control_point_runs_movept(win, app):
    win.execute("NURBS, 3, (0,0,0), (10,8,0), (20,-8,0), (30,0,0)")
    win.execute("VIEW, TOP")
    assert win.execute("CPOINTS, 1").ok
    vp = win.viewport
    assert vp.control_points is not None and len(vp.control_points.points()) == 4
    app.processEvents()
    a = _logical(win, (10, 8, 0))
    b = _logical(win, (10, 14, 0))
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)
    for k in range(1, 6):
        QTest.mouseMove(vp, a + (b - a) * k / 5)
        app.processEvents()
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, b)
    app.processEvents()
    p = win.processor
    last = p.history[-1].text
    assert last.startswith("MOVEPT, 1, 2,"), last
    y = p.evaluate("POLE(1, 2)")[1]
    assert y == pytest.approx(14, abs=0.6)
    # the view shows the moved point after the edit
    assert vp.control_points.points()[1][1][1] == pytest.approx(y)
    assert win.execute("CPOINTS, OFF").ok and vp.control_points is None


def test_control_points_button_needs_a_pick(win):
    from modeler.gui import feature_actions as fa

    win.execute("NURBS, 2, (0,0,0), (10,10,0), (20,0,0)")
    with pytest.raises(fa.NeedInput):
        fa.control_points_toggle(win.processor)
    win.execute("PICK, BODY, 1")
    assert fa.control_points_toggle(win.processor) == ["CPOINTS, 1"]
