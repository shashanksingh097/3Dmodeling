"""GUI tests: the OCCT view inside a PySide6 window, and picking.

These need a display with OpenGL. On Linux CI they run under Xvfb. They are
skipped when no display is available (set MODELER_GUI_TESTS=0 to skip them
explicitly).
"""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from OCP.BRep import BRep_Tool  # noqa: E402
from OCP.BRepGProp import BRepGProp  # noqa: E402
from OCP.GProp import GProp_GProps  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
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
    assert w.viewport._initialized, "3D view did not initialize"
    w.execute("BLOCK, 0,0,0, 20,10,5")
    w.execute("CYL, 30,5,0, 4, 12")
    w.execute("VIEW, ISO")
    app.processEvents()
    yield w
    w.close()


def to_px(win, x, y, z):
    return win.viewport.view.Convert(x, y, z)


def face_centre(win, gid):
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(win.processor.model.entity_shape("FACE", gid), g)
    c = g.CentreOfMass()
    return c.X(), c.Y(), c.Z()


def test_click_on_faces_emits_pick_commands(win):
    vp = win.viewport
    # block top (face 6), block front (face 3), cylinder side (face 7)
    for gid in (6, 3, 7):
        text = vp.click(*to_px(win, *face_centre(win, gid)))
        assert text == f"PICK, FACE, {gid}"
        assert win.processor.model.selection == [gid]
        assert win.processor.log[-1] == f"PICK, FACE, {gid}"


def test_ctrl_click_adds_and_empty_click_clears(win):
    vp = win.viewport
    vp.click(*to_px(win, *face_centre(win, 6)))
    vp.click(*to_px(win, *face_centre(win, 7)), Qt.ControlModifier)
    assert win.processor.model.selection == [6, 7]
    assert vp.click(2, 2) == "SEL, NONE"
    assert win.processor.model.selection == []


def test_edge_and_vertex_picking(win):
    m = win.processor.model
    vp = win.viewport
    win.execute("PICKMODE, EDGE")
    assert vp.pick_mode == "EDGE"
    # top front edge of the block: from (0,0,5) to (20,0,5)
    gid = vp.click(*to_px(win, 10, 0, 5))
    assert gid and gid.startswith("PICK, EDGE, ")
    eid = int(gid.split(",")[-1])
    assert m.entity_owner("EDGE", eid)[0] == 1
    win.execute("PICKMODE, VERTEX")
    text = vp.click(*to_px(win, 20, 0, 5))
    assert text and text.startswith("PICK, VERTEX, ")
    v = m.entity_shape("VERTEX", int(text.split(",")[-1]))
    to_vertex = getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex  # name differs across OCP versions
    p = BRep_Tool.Pnt_s(to_vertex(v))
    assert (round(p.X()), round(p.Y()), round(p.Z())) == (20, 0, 5)


def test_body_picking(win):
    win.execute("PICKMODE, BODY")
    assert win.viewport.click(*to_px(win, 30, 1, 6)) == "PICK, BODY, 2"


def test_scripted_pick_highlights(win):
    win.execute("PICK, FACE, 6")
    ctx = win.viewport.context
    ctx.InitSelected()
    assert ctx.MoreSelected()
    assert ctx.SelectedShape().IsSame(win.processor.model.entity_shape("FACE", 6))


def test_scripted_pick_is_drawn_orange(win):
    """The highlight really shows: sample the rendered pixel at the face."""
    from OCP.Image import Image_AlienPixMap

    vp = win.viewport
    x, y = to_px(win, *face_centre(win, 6))
    win.execute("SEL, NONE")
    before = _pixel(vp, x, y, Image_AlienPixMap)
    win.execute("PICK, FACE, 6")
    after = _pixel(vp, x, y, Image_AlienPixMap)
    r, g, b = after
    assert r > 0.8 and b < 0.3, (before, after)  # orange
    assert before != after


def _pixel(vp, x, y, pixmap_cls):
    vp.view.Redraw()
    w, h = vp._window.Size()
    pm = pixmap_cls()
    assert vp.view.ToPixMap(pm, w, h)
    c = pm.PixelColor(x, y).GetRGB()
    return round(c.Red(), 2), round(c.Green(), 2), round(c.Blue(), 2)
