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


def test_history_and_parameter_panels_drive_commands(win, app):
    p = win.processor
    win.execute("W = 10")
    win.execute("BLOCK, 50,0,0, W, W, W")
    hp, pp = win.history_panel, win.param_panel
    assert hp.rowCount() == len(p.history) == 4
    assert hp.item(3, 1).text() == "BLOCK, 50,0,0, W, W, W"
    # typing a new value in the Parameters panel edits the defining entry
    row = [pp.item(r, 0).text() for r in range(pp.rowCount())].index("W")
    pp.item(row, 1).setText("20")
    app.processEvents()
    assert p.history[2].text == "W = 20"
    assert p.evaluate("VOL(LAST)") == pytest.approx(8000)
    assert win.output.toPlainText().splitlines()[-2].startswith('> HIST, EDIT, 3, "W = 20"')
    # the viewport shows the rebuilt bodies
    assert sorted(win.viewport._ais) == sorted(p.model.bodies)
    win.undo_action.trigger()
    assert len(p.model.bodies) == 2 and sorted(win.viewport._ais) == [1, 2]
    assert hp.item(3, 0).foreground().color().getRgb()[:3] == (140, 140, 140)  # undone: grey
    win.redo_action.trigger()
    assert len(win.viewport._ais) == 3


def test_typed_block_in_command_line(win):
    for line in ("*DO, i, 1, 3", "  SPHERE, i*10, 30, 0, 2", "*ENDDO"):
        win.cmdline.setText(line)
        win.cmdline.returnPressed.emit()
        if line != "*ENDDO":
            assert win.prompt.text() == "…"
    assert win.prompt.text() == ">"
    assert len(win.processor.model.bodies) == 5
    assert len(win.viewport._ais) == 5


def test_curves_show_and_hidden_bodies_are_not_drawn(win):
    for line in ("LINE, 0,0,0, 0,0,30", "CIRCLE, 0,0,0, 3", "SWEEP, LAST, LAST - 1"):
        assert win.execute(line).ok
    ids = sorted(win.processor.model.bodies)[-3:]
    assert all(b in win.viewport._ais for b in ids)
    assert win.execute(f"HIDE, {ids[0]}").ok
    assert ids[0] not in win.viewport._ais
    assert win.execute("SHOW").ok
    assert ids[0] in win.viewport._ais


def test_command_line_completion_and_hint(win, app):
    cl = win.cmdline
    cl.setFocus()
    cl.setText("")
    QTest.keyClicks(cl, "SWE")
    app.processEvents()
    assert cl.completer.popup().isVisible()
    QTest.keyClick(cl, Qt.Key_Tab)
    assert cl.text() == "SWEEP"
    QTest.keyClicks(cl, ", ")
    app.processEvents()
    assert "<u>profile</u>" in cl.hint.text()
    cl.setText("")


def test_autosave_and_recover(app, tmp_path):
    path = str(tmp_path / "auto.m3d")
    w = MainWindow(autosave=path)
    w.execute("BLOCK, 0,0,0, 3,3,3")
    w.autosave_now()  # the timer would do this a moment later
    assert os.path.isfile(path)
    w.close()
    w2 = MainWindow(autosave=path)  # next session: the old autosave is kept aside
    assert w2.recover_action.isVisible()
    assert w2.execute("OPEN, AUTOSAVE").ok
    assert len(w2.processor.model.bodies) == 1
    w2.close()


def test_datums_are_drawn_but_never_block_a_pick(win, app):
    vp = win.viewport
    win.execute("PLANE, front, PN, 0,-5,0, 0,1,0")  # a plane right in front of the block
    win.execute("AXIS, up, Z")
    win.execute("POINT, here, XYZ, 1, 2, 3")
    app.processEvents()
    assert len(vp._datum_ais) == 6  # three datums, each with its label
    assert vp.click(*to_px(win, *face_centre(win, 6))) == "PICK, FACE, 6"
    win.execute("DATUM, DELETE, up")
    assert len(vp._datum_ais) == 4
    win.execute("UNDO")
    assert len(vp._datum_ais) == 6


def test_section_view_adds_a_clip_plane(win):
    vp = win.viewport
    win.execute("SECTION, XY")
    assert vp._clip is not None and vp.view.ClipPlanes().Size() == 1
    win.execute("SECTION, OFF")
    assert vp._clip is None and vp.view.ClipPlanes().Size() == 0


def test_feature_toolbar_sends_commands(win):
    from modeler.gui import feature_actions as fa

    win.execute("PICK, FACE, 6")
    win.run_feature(lambda: fa.hole_on_face(win.processor, 4))
    assert win.processor.log[-1] == "HOLE, 1, 10, 5, 5, 4"
    win.run_feature(lambda: fa.two_selected(win.processor, "DIST"))  # nothing selected: no command
    assert win.processor.log[-1] == "HOLE, 1, 10, 5, 5, 4"


def test_layers_and_colours_in_the_view_and_the_layers_panel(win, app):
    from OCP.Image import Image_AlienPixMap

    vp, lp = win.viewport, win.layer_panel
    assert lp.names() == ["DEFAULT"]
    # the panel's New button runs LAYER, name; new bodies go there
    assert win.execute("LAYER, red_parts, NEW, RED").ok
    assert lp.names() == ["DEFAULT", "red_parts"]
    assert win.execute("LAYER, red_parts, ADD, 1").ok
    x, y = to_px(win, *face_centre(win, 6))  # the block's top face
    r, g, b = _pixel(vp, x, y, Image_AlienPixMap)
    assert r > g + 0.15 and r > b + 0.15, (r, g, b)  # drawn red
    # switching the layer off in the panel hides the block
    row = lp.names().index("red_parts")
    lp.table.item(row, 1).setCheckState(Qt.Unchecked)
    app.processEvents()
    assert win.processor.history[-1].text == "LAYER, red_parts, OFF"
    assert 1 not in vp._ais and 2 in vp._ais
    lp.table.item(row, 1).setCheckState(Qt.Checked)
    app.processEvents()
    assert 1 in vp._ais
    # clicking the current-layer column makes it current
    lp._clicked(row, 0)
    assert win.processor.model.current_layer == "RED_PARTS"
    assert lp.table.item(row, 0).text() == "●"
    # a body's own colour wins over its layer's
    assert win.execute("COLOR, 1, BLUE").ok
    r, g, b = _pixel(vp, x, y, Image_AlienPixMap)
    assert b > r + 0.15, (r, g, b)
    # lock from the panel: the block cannot be moved
    lp.table.item(row, 2).setCheckState(Qt.Checked)
    app.processEvents()
    assert not win.execute("MOVE, 1, 5").ok
    assert lp.table.item(row, 5).text() == "1"


def test_glass_bodies_are_see_through(win):
    win.execute("BLOCK, 0,0,0, 10,10,2")
    win.execute("BLOCK, 20,0,0, 10,10,2")
    assert win.execute("MATERIAL, 2, GLASS").ok
    ais = win.viewport._ais
    assert ais[1].Transparency() == 0
    assert 0 < ais[2].Transparency() < 1
    assert win.execute("MATERIAL, 2, STEEL").ok
    assert ais[2].Transparency() == 0


def _menu_action(menu, label):
    for act in menu.actions():
        if act.text() == label:
            return act
    raise AssertionError(f"no menu item {label!r} in {[a.text() for a in menu.actions()]}")


def test_right_click_opens_the_body_menu_and_fades_the_others(win, app):
    vp = win.viewport
    x, y = to_px(win, *face_centre(win, 7))  # the cylinder's side (body 2)
    n = len(win.processor.history)
    seen = []
    vp.body_menu.connect(lambda bid, pos: seen.append(bid))
    r = vp.devicePixelRatioF()
    QTest.mouseClick(vp, Qt.RightButton, Qt.NoModifier, QPoint(int(x / r), int(y / r)))
    app.processEvents()
    assert seen == [2]
    menu = win._body_menu
    assert menu.actions()[0].text() == "body 2"
    _menu_action(menu, "Fade all others").trigger()
    menu.close()
    app.processEvents()
    assert 0 < vp._ais[1].Transparency() < 1 and vp._ais[2].Transparency() == 0
    assert len(win.processor.history) == n  # view steps add no history
    win.show_body_menu(0, vp.mapToGlobal(vp.rect().center()))
    _menu_action(win._body_menu, "Show everything").trigger()
    win._body_menu.close()
    assert vp._ais[1].Transparency() == 0


def test_view_hide_and_history_row_menu(win, app):
    vp = win.viewport
    assert win.execute("DISPLAY, HIDE, 1").ok
    assert 1 not in vp._ais
    assert win.execute("DISPLAY, SHOW, 1").ok
    assert 1 in vp._ais
    from modeler.gui import body_menu as bm

    items = bm.entry_items(win.processor, 1)  # the CYL row made body 2
    win.run_menu_item(next(i for i in items if i.label == "Show only this"))
    assert 1 not in vp._ais and 2 in vp._ais
    win.run_menu_item(next(i for i in bm.body_items(win.processor.model, 2) if i.label.startswith("Find the step")))
    assert win.history_panel.currentRow() == 1


def test_model_tree_lists_bodies_and_follows_picks(win, app):
    tree = win.model_tree
    app.processEvents()
    assert tree.item("body:1") is not None and tree.item("body:2") is not None
    # a pick in the view selects the row
    win.execute("PICK, BODY, 2")
    assert tree.item("body:2").isSelected() and not tree.item("body:1").isSelected()
    # a click on a row picks the body (and the view highlights it in face mode too)
    tree._clicked(tree.item("body:1"), 0)
    assert win.processor.model.selection == [1] and win.processor.model.selection_kind == "BODY"
    assert win.viewport.context.NbSelected() == 1
    # the eye hides for the view only
    n = len(win.processor.history)
    tree.item("body:2").setCheckState(0, Qt.Unchecked)
    app.processEvents()
    assert 2 not in win.viewport._ais and not win.processor.model.is_shown(2)
    assert "hidden" in tree.item("body:2").text(1)
    tree.item("body:2").setCheckState(0, Qt.Checked)
    app.processEvents()
    assert 2 in win.viewport._ais
    # the right-click menu is the body menu
    labels = [i.label for i in tree.menu_items("body:2")]
    assert "Fade all others" in labels and "Zoom to" in labels
    win.run_menu_item(next(i for i in tree.menu_items("body:2") if i.label == "Fade this"))
    app.processEvents()
    assert "faded" in tree.item("body:2").text(1)
    assert len(win.processor.history) == n  # the eye and the menu are view steps
    # renaming shows in the tree
    win.execute("NAME, 1, plate")
    app.processEvents()
    assert tree.item("body:1").text(0).startswith("plate")


def test_model_tree_groups_part_instances(win, app):
    win.execute("*PART, peg, D=4\nCYL, 0,0,0, D/2, 10\n*ENDPART")
    win.execute("INST, peg, 60,0,0")
    win.execute("INST, peg, 70,0,0")
    app.processEvents()
    part = win.model_tree.node("part:PEG")
    assert part is not None and len(part.children) == 2
    assert part.children[0].label.startswith("peg")
    assert "*PART, peg" in part.children[0].tip
    items = win.model_tree.menu_items("part:PEG")
    fade = next(i for i in items if i.label == "Fade all of them")
    assert fade.commands == [f"FADE, {' '.join(map(str, part.ids))}"]
