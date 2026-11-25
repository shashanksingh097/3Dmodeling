"""PLAN items 84 and 85 in the window: picking whatever is nearest, Tab to the one
behind, box and lasso picks, double-click loops and chains, and the tools beside a
pick (needs a display: run under xvfb-run)."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from OCP.BRepGProp import BRepGProp  # noqa: E402
from OCP.GProp import GProp_GProps  # noqa: E402
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
    w.resize(1300, 850)
    w.show()
    for _ in range(30):
        app.processEvents()
        if w.viewport._initialized:
            break
    assert w.viewport._initialized
    run(w, "BLOCK, 0,0,0, 20,10,5\nVIEW, ISO")
    pump(app)
    yield w
    w.close()


def run(win, text):
    for line in text.splitlines():
        res = win.execute(line)
        assert res.ok, res.message


def px(win, x, y, z):
    return win.viewport.view.Convert(x, y, z)


def logical(win, x, y):
    r = win.viewport.devicePixelRatioF()
    return QPoint(int(x / r), int(y / r))


def centre(win, kind, gid):
    g = GProp_GProps()
    shape = win.processor.model.entity_shape(kind, gid)
    (BRepGProp.SurfaceProperties_s if kind == "FACE" else BRepGProp.LinearProperties_s)(shape, g)
    c = g.CentreOfMass()
    return c.X(), c.Y(), c.Z()


def test_auto_is_the_default_and_picks_faces_and_edges_by_nearness(app, win):
    vp, m = win.viewport, win.processor.model
    assert vp.pick_mode == "AUTO" and win._mode_actions["AUTO"].isChecked()
    text = vp.click(*px(win, *centre(win, "FACE", 6)))  # the middle of the top face
    assert text == "PICK, FACE, 6"
    # right on the front top edge: the edge wins
    hit = vp.pick_at(*px(win, 10, 0, 5))
    assert hit is not None and hit[0] == "EDGE" and m.entity_owner("EDGE", hit[1])[0] == 1
    # a corner: the vertex wins
    hit = vp.pick_at(*px(win, 20, 0, 5))
    assert hit is not None and hit[0] == "VERTEX"
    run(win, "PICKMODE, FACE")
    assert vp.pick_at(*px(win, 10, 0, 5))[0] == "FACE"  # a face-only pick ignores the edge
    run(win, "PICKMODE, AUTO")
    assert win._mode_actions["AUTO"].isChecked()


def test_tab_steps_to_the_face_behind(app, win):
    vp, m = win.viewport, win.processor.model
    x, y = px(win, *centre(win, "FACE", 6))
    vp._hover_px = (x, y)
    cands = vp.candidates_at(x, y)
    faces = [g for k, g in cands if k == "FACE"]
    assert faces[:1] == [6] and 5 in faces  # the top, then the bottom behind it
    first = vp.pick_behind()
    assert first is not None and first != "PICK, FACE, 6"
    seen = {first}
    for _ in range(len(cands)):
        seen.add(vp.pick_behind())
    assert "PICK, FACE, 5" in seen and "PICK, FACE, 6" in seen  # it goes round
    assert m.selection_kind in ("FACE", "EDGE", "VERTEX")
    # the Tab key in the view does it too
    vp.setFocus()
    before = len(win.processor.history)
    QTest.keyClick(vp, Qt.Key_Tab)
    pump(app)
    assert len(win.processor.history) == before + 1 and win.processor.history[-1].text.startswith("PICK, ")


def test_box_tool_and_ctrl_drag_pick_regions(app, win):
    vp, m = win.viewport, win.processor.model
    run(win, "BLOCK, 40,0,0, 10,10,10\nFIT")
    pump(app)
    lo = px(win, -2, -2, 0)
    hi = px(win, 22, 12, 5)
    xs = [lo[0], hi[0], px(win, -2, 12, 5)[0], px(win, 22, -2, 0)[0]]
    ys = [lo[1], hi[1], px(win, -2, 12, 5)[1], px(win, 22, -2, 0)[1]]
    a, b = (min(xs) - 5, min(ys) - 5), (max(xs) + 5, max(ys) + 5)
    run(win, "PICKMODE, BODY")
    assert vp.region_text([a, b]) == "PICK, BODY, 1"
    run(win, "PICKMODE, FACE")
    text = vp.region_text([a, b])
    assert text == "PICK, FACE, " + " ".join(map(str, m.bodies[1].entity_ids["FACE"]))
    # right to left: what it touches; Ctrl adds
    t2 = vp.region_text([b, a], Qt.ControlModifier)
    assert t2.endswith(", A")
    # the toolbar button and PICKREGION drive the same tool, Esc ends it
    win._region_actions["BOX"].trigger()
    assert vp.region_tool == "BOX" and win._region_actions["BOX"].isChecked()
    run(win, "PICKREGION, LASSO")
    assert win._region_actions["LASSO"].isChecked() and not win._region_actions["BOX"].isChecked()
    vp.setFocus()
    QTest.keyClick(vp, Qt.Key_Escape)
    assert vp.region_tool == "" and not win._region_actions["LASSO"].isChecked()
    # a real Ctrl+drag with the mouse: one PICK step for the box
    run(win, "PICKMODE, BODY\nSEL, NONE")
    n = len(win.processor.history)
    QTest.mousePress(vp, Qt.LeftButton, Qt.ControlModifier, logical(win, *a))
    for t in (0.3, 0.6, 1.0):
        QTest.mouseMove(vp, logical(win, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        pump(app, 2)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.ControlModifier, logical(win, *b))
    pump(app)
    assert win.processor.history[-1].text == "PICK, BODY, 1, A" and len(win.processor.history) == n + 1
    assert m.selection == [1]


def test_double_click_picks_the_loop_then_the_chain_and_smooth_faces(app, win):
    vp, m = win.viewport, win.processor.model
    run(win, "SEL, S, EDGE, BODY, 1\nSEL, R, EDGE, SIZE, EQ, 5\nFILLET, 2\nVIEW, ISO\nFIT")
    pump(app)
    b = max(m.bodies)
    run(win, f"SEL, S, FACE, BODY, {b}\nSEL, R, FACE, NORMAL, 0,0,1")
    top = m.selection[0]
    run(win, "SEL, S, EDGE, OF, FACE\nSEL, R, EDGE, TYPE, LINE")
    line = m.selection[0]
    text = vp.loop_text("EDGE", line)
    assert text == f"SEL, S, EDGE, LOOP, {line}, {top}"  # the top faces the viewer in the iso view
    run(win, text)
    assert len(m.selection) == 8
    assert vp.loop_text("EDGE", line) == f"SEL, S, EDGE, CHAIN, {line}"  # again: the tangent chain
    assert vp.loop_text("FACE", top) == f"SEL, S, FACE, TANGENT, {top}"
    # a real double click on the middle of the top face
    x, y = px(win, *centre(win, "FACE", top))
    QTest.mouseDClick(vp, Qt.LeftButton, Qt.NoModifier, logical(win, x, y))
    pump(app)
    assert win.processor.history[-1].text == f"SEL, S, FACE, TANGENT, {top}"


def test_tools_appear_beside_a_pick_and_run(app, win):
    vp, m = win.viewport, win.processor.model
    bar = win.pick_bar
    x, y = px(win, *centre(win, "FACE", 6))
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, logical(win, x, y))
    pump(app)
    assert m.selection == [6]
    assert bar.isVisible()
    labels = [i.label for i in bar.items]
    assert labels[:3] == ["Sketch on this face", "Pull…", "Hole…"] and len(bar.buttons) == len(labels) + 1
    bar._watch.stop()
    bar.buttons[labels.index("Hole…")].click()  # opens the Hole form, filled in from the pick
    pump(app)
    from modeler.gui.form_dialog import FormDialog

    dlg = [d for d in win.findChildren(FormDialog) if d.isVisible()][-1]
    assert dlg.spec.command == "HOLE" and dlg.fields["x"].value() == "10, 5, 5"
    assert not bar.isVisible()
    dlg.reject()
    # something else picked: it goes
    bar.show_for_pick(vp.mapToGlobal(QPoint(50, 50)))
    run(win, "PICK, FACE, 5")
    bar._check()
    assert not bar.isVisible()
    # a press in the view sends it away; the setting turns it off
    bar.show_for_pick(vp.mapToGlobal(QPoint(50, 50)))
    vp.pressed.emit()
    assert not bar.isVisible()
    from modeler.gui import pick_bar

    pick_bar.set_enabled(win, False)
    assert not bar.show_for_pick(vp.mapToGlobal(QPoint(50, 50)))
    pick_bar.set_enabled(win, True)


def test_right_click_menu_starts_with_the_pick_tools(app, win):
    vp = win.viewport
    run(win, "PICK, EDGE, 1")
    win.show_body_menu(1, vp.mapToGlobal(vp.rect().center()))
    acts = [a.text() for a in win._body_menu.actions() if a.text()]
    assert acts[0] == "The picked edge" and acts[1:5] == ["Fillet…", "Chamfer…", "Loop round its face",
                                                          "Tangent chain"]
    loop = next(a for a in win._body_menu.actions() if a.text() == "Loop round its face")
    win._body_menu.close()
    loop.trigger()
    assert len(win.processor.model.selection) == 4 and win.processor.model.selection_kind == "EDGE"
