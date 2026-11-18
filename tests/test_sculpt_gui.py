"""The Sculpt tab: strokes dragged in the 3D view become SCULPT / MASK history steps."""

import os
import sys

import numpy as np
import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QPoint, QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from modeler.geometry import meshbody as mb  # noqa: E402
from modeler.gui import sculpt_tool as st  # noqa: E402
from modeler.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path):
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    w.resize(1000, 700)
    w.show()
    for _ in range(20):
        app.processEvents()
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


def _ball(win):
    for c in ("SPHERE, 0,0,0, 20", "TOMESH, 1", "REMESH, 1, 1.5"):
        assert win.execute(c).ok, c
    win.execute("VIEW, FRONT")


def _logical(win, q):
    x, y = win.viewport.view.Convert(*q)
    r = win.viewport.devicePixelRatioF()
    return QPoint(int(round(x / r)), int(round(y / r)))


def _drag(win, app, a, b, mods=Qt.NoModifier, release=True):
    vp = win.viewport
    pa, pb = _logical(win, a), _logical(win, b)
    QTest.mousePress(vp, Qt.LeftButton, mods, pa)
    for k in range(1, 9):
        QTest.mouseMove(vp, pa + (pb - pa) * k / 8)
        app.processEvents()
    if release:
        QTest.mouseRelease(vp, Qt.LeftButton, mods, pb)
        app.processEvents()
    return pb


def test_ray_hit_and_thin():
    pts = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], float)
    t = np.array([[0, 1, 2]])
    assert st.ray_hit(pts, t, (2, 2, 5), (0, 0, -1)) == pytest.approx([2, 2, 0])
    assert st.ray_hit(pts, t, (9, 9, 5), (0, 0, -1)) is None
    line = [(x, 0, 0) for x in np.linspace(0, 10, 101)]
    th = st.thin(line, 1.0)
    assert len(th) == 11 and th[-1] == pytest.approx([10, 0, 0])
    assert len(st.thin(line, 0.0, limit=20)) == 20


def test_drag_sculpts_and_undo_takes_it_back(win, app):
    _ball(win)
    p = win.processor
    before, _ = mb.arrays(p.model.bodies[1].shape)
    win.sculpt_action.setChecked(True)
    assert win.viewport.sculpt_on and win.radius_box.value() == pytest.approx(3.46, abs=0.01)
    _drag(win, app, (-10, -30, 5), (10, -30, 5))
    last = p.history[-1].text
    assert last.startswith("SCULPT, 1, DRAW,") and last.endswith("S1"), last
    after, _ = mb.arrays(p.model.bodies[1].shape)
    assert np.abs(after - before).max() > 0.05
    assert "STROKE, S1," in p.script(standalone=True)
    # Ctrl digs in
    _drag(win, app, (-10, -30, -5), (10, -30, -5), Qt.ControlModifier)
    assert ", -0.5, S2" in p.history[-1].text
    win.execute("UNDO")
    win.execute("UNDO")
    assert np.abs(mb.arrays(p.model.bodies[1].shape)[0] - before).max() < 1e-9


def test_mask_brush_and_symmetry(win, app):
    _ball(win)
    p = win.processor
    win.brush_actions["MASK"].trigger()
    assert win.viewport.sculpt_on
    _drag(win, app, (-10, -30, 0), (10, -30, 0))
    assert p.history[-1].text.startswith("MASK, 1, PAINT,")
    assert int((p.model.masks[1] > 0.5).sum()) > 0
    win.brush_actions["INFLATE"].trigger()
    win.sym_actions["X"].setChecked(True)
    _drag(win, app, (5, -30, 10), (12, -30, 10))
    assert p.history[-1].text.startswith("SCULPT, 1, INFLATE,") and p.history[-1].text.endswith(", X")


def test_missing_the_body_runs_nothing_and_esc_ends(win, app):
    _ball(win)
    p = win.processor
    n = len(p.history)
    win.sculpt_action.setChecked(True)
    _drag(win, app, (60, -30, 60), (70, -30, 60))
    assert len(p.history) == n and not p.strokes
    QTest.keyClick(win.viewport, Qt.Key_Escape)
    assert not win.viewport.sculpt_on and not win.sculpt_action.isChecked()


def test_knife_and_sculpt_exclude_each_other(win):
    win.sculpt_action.setChecked(True)
    win.knife_action.setChecked(True)
    assert win.viewport.knife and not win.viewport.sculpt_on and not win.sculpt_action.isChecked()


def test_make_sculptable(win):
    win.execute("BLOCK, 0,0,0, 30,20,10")
    win.execute("PICK, BODY, 1")
    st.make_sculptable(win)
    shape = win.processor.model.bodies[1].shape
    assert mb.is_mesh(shape)
    assert len(mb.arrays(shape)[1]) > 5000


def test_live_stroke_and_mask_overlay():
    from modeler.commands import Processor

    p = Processor()
    for c in ("SPHERE, 0,0,0, 20", "TOMESH, 1", "REMESH, 1, 1.5"):
        assert p.run(c).ok
    shape = p.model.bodies[1].shape
    s = st.Settings(brush="DRAW", radius=3, strength=0.5)
    live = st.LiveStroke(1, shape, s)
    moved = [live.add((x, -20, 0)) for x in np.linspace(-5, 5, 11)]
    assert moved[0] is False and any(moved) and live.changed
    assert np.abs(live.work - live.pts0).max() > 0.05
    assert np.abs(mb.arrays(shape)[0] - live.pts0).max() == 0  # the body itself is untouched
    assert st.LiveStroke(1, shape, st.Settings(brush="MASK", radius=3)).add((0, -20, 0)) is False
    pts, tris = mb.arrays(shape)
    assert st.mask_overlay(pts, tris, None) is None
    mask = np.zeros(len(pts))
    assert st.mask_overlay(pts, tris, mask) is None
    mask[pts[:, 1] < -15] = 1
    q, t = st.mask_overlay(pts, tris, mask)
    assert len(t) and q[:, 1].max() < -14 and t.max() < len(q)


def test_the_surface_moves_while_dragging(win, app):
    _ball(win)
    p = win.processor
    vp = win.viewport
    win.sculpt_action.setChecked(True)
    shape = p.model.bodies[1].shape
    pb = _drag(win, app, (-10, -30, 5), (10, -30, 5), release=False)
    shown = vp._ais[1].Shape()
    assert not shown.IsSame(shape)  # the preview
    assert np.abs(mb.arrays(shown)[0] - mb.arrays(shape)[0]).max() > 0.05
    assert vp._brush_ais is not None
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, pb)
    app.processEvents()
    assert p.history[-1].text.startswith("SCULPT, 1, DRAW,")
    assert vp._ais[1].Shape().IsSame(p.model.bodies[1].shape)
    # Esc in the middle of a drag puts the body back
    n = len(p.history)
    _drag(win, app, (-10, -30, -5), (10, -30, -5), release=False)
    QTest.keyClick(vp, Qt.Key_Escape)
    assert len(p.history) == n and vp._ais[1].Shape().IsSame(p.model.bodies[1].shape)


def test_brush_circle_follows_the_mouse(win, app):
    _ball(win)
    vp = win.viewport
    win.sculpt_action.setChecked(True)
    vp._hover_at = 0.0
    QTest.mouseMove(vp, _logical(win, (0, -30, 0)))
    app.processEvents()
    assert vp._brush_ais is not None
    vp._hover_at = 0.0
    QTest.mouseMove(vp, _logical(win, (60, -30, 60)))
    app.processEvents()
    assert vp._brush_ais is None


def test_frozen_areas_are_shown(win, app):
    _ball(win)
    vp = win.viewport
    win.brush_actions["MASK"].trigger()
    assert vp._mask_ais is None
    _drag(win, app, (-10, -30, 0), (10, -30, 0))
    assert vp._mask_ais is not None
    win.execute("UNDO")
    assert vp._mask_ais is None
    win.execute("MASK, 1, ALL")
    assert vp._mask_ais is not None
    win.execute("MASK, 1, CLEAR")
    assert vp._mask_ais is None
    win.execute("MASK, 1, ALL")
    win.sculpt_action.setChecked(False)
    assert vp._mask_ais is None  # only while sculpting


def test_detail_box_adds_detail_to_the_command(win, app):
    _ball(win)
    p = win.processor
    before = len(mb.arrays(p.model.bodies[1].shape)[1])
    win.sculpt_action.setChecked(True)
    win.detail_box.setValue(0.5)
    _drag(win, app, (-10, -30, 5), (10, -30, 5))
    last = p.history[-1].text
    assert last.endswith(", , 0.5"), last
    win.sym_actions["X"].setChecked(True)
    _drag(win, app, (-10, -30, -5), (10, -30, -5))
    assert p.history[-1].text.endswith(", X, 0.5")
    assert len(mb.arrays(p.model.bodies[1].shape)[1]) > before  # finer triangles where it went
