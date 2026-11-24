"""PLAN items 86-88 without a window: the numbers of the pick (SELINFO, the status
line, the hover text, the assistant's user_context and selection_numbers), typed
values while sketching (the sketcher's boxes, what they fix, the sizes they leave),
and project templates (NEW, template; TEMPLATE LIST/SHOW/SAVE/DELETE; the
templates tool; the drawing sheet a template sets)."""

import json
import math

import pytest

from modeler.ai.tools import Toolbox, ToolError
from modeler.commands import Processor
from modeler.commands import selinfo as si
from modeler.commands import template_handlers as th
from modeler.gui import sketch_typed as st
from modeler.gui.sketch_tools import SketchController


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def fails(p, text):
    r = p.run_script(text)[-1]
    assert not r.ok
    return r.message


def two_bodies():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nCYL, 60,0,0, 5, 10")
    return p


# ---- item 86: the numbers of the pick ---------------------------------------------------
def test_one_flat_face_gives_type_and_area():
    p = two_bodies()
    ok(p, "PICK, FACE, 6")
    info = si.selection_info(p)
    (row,) = info["items"]
    assert row["type"] == "plane" and row["area"] == pytest.approx(800)
    assert si.line(info) == "face 6: plane, area 800 mm²"
    assert "total" not in info and "pair" not in info


def test_round_face_gives_radius_and_diameter():
    p = two_bodies()
    side = p.model.bodies[2].entity_ids["FACE"][0]
    info = si.selection_info(p, "FACE", [side])
    row = info["items"][0]
    assert row["type"] == "cylinder" and row["r"] == 5 and row["d"] == 10
    assert row["area"] == pytest.approx(2 * math.pi * 5 * 10, rel=1e-6)
    assert "r 5 (d 10)" in si.line(info)


def test_edges_give_length_and_circle_or_arc():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nCYL, 60,0,0, 5, 10\nSEL, S, EDGE, BODY, 1\nFILLET, 3")
    m = p.model
    plate = next(b for b in m.bodies if b != 2)  # the filleted block (a new body)
    rows = [si.edge_numbers(p, g) for g in m.bodies[plate].entity_ids["EDGE"]]
    arcs = [r for r in rows if "r" in r and not r["closed"]]
    assert arcs and all(r["r"] == pytest.approx(3) and r["arc_deg"] == pytest.approx(90) for r in arcs)
    assert "arc r 3 (d 6), 90°" in si.row_text("EDGE", arcs[0], "mm")
    circ = [si.edge_numbers(p, g) for g in m.bodies[2].entity_ids["EDGE"]]
    full = [r for r in circ if r.get("closed")]
    assert full and full[0]["length"] == pytest.approx(2 * math.pi * 5, rel=1e-6)
    assert si.row_text("EDGE", full[0], "mm").startswith(f"edge {full[0]['id']}: circle r 5 (d 10)")


def test_body_gives_volume_area_size_and_mass_from_material():
    p = two_bodies()
    ok(p, "MATERIAL, 1, STEEL")
    info = si.selection_info(p, "BODY", [1])
    row = info["items"][0]
    assert row["volume"] == pytest.approx(8000) and row["area"] == pytest.approx(2800)
    assert row["size"] == [40, 20, 10]
    assert row["mass_kg"] == pytest.approx(8000e-9 * 7850)
    assert row["name"] == ""  # the default name body1 is not repeated
    text = si.line(info)
    assert "volume 8000 mm³" in text and "mass 0.0628 kg (steel)" in text and "size 40 x 20 x 10 mm" in text


def test_named_body_shows_its_name():
    p = two_bodies()
    ok(p, "NAME, 1, plate")
    assert si.line(si.selection_info(p, "BODY", [1])).startswith("body 1 (plate):")


def test_several_faces_give_a_total_area():
    p = two_bodies()
    ok(p, "PICK, FACE, 1 3 5")
    info = si.selection_info(p)
    assert info["count"] == 3 and info["total"]["area"] == pytest.approx(200 + 400 + 800)
    assert si.line(info) == "3 faces, total area 1400 mm²"


def test_two_faces_give_distance_and_parallel():
    p = two_bodies()
    ok(p, "PICK, FACE, 1 2")
    info = si.selection_info(p)
    pr = info["pair"]
    assert pr["distance"] == pytest.approx(40) and pr["parallel"] == "facing away"
    assert pr["dx"] == pytest.approx(40) and pr["dy"] == 0 and pr["dz"] == 0
    assert si.line(info) == "2 faces, distance 40 mm (dx 40), parallel, facing away, total area 400 mm²"


def test_two_faces_at_right_angles_give_the_angle():
    p = two_bodies()
    ok(p, "PICK, FACE, 1 6")
    pr = si.selection_info(p)["pair"]
    assert pr["angle"] == pytest.approx(90) and not pr.get("parallel")
    assert pr["distance"] == pytest.approx(0)
    assert "distance 0 mm (touching), angle 90°" in si.line(si.selection_info(p))


def test_two_straight_edges_give_angle_between_lines():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 20,10,10")
    es = p.model.bodies[1].entity_ids["EDGE"]
    rows = {g: si.edge_numbers(p, g) for g in es}
    along_x = [g for g, r in rows.items() if r.get("dir") and abs(abs(r["dir"][0]) - 1) < 1e-9]
    along_z = [g for g, r in rows.items() if r.get("dir") and abs(abs(r["dir"][2]) - 1) < 1e-9]
    info = si.selection_info(p, "EDGE", [along_x[0], along_z[0]])
    assert info["pair"]["angle"] == pytest.approx(90) and info["pair"]["angle_between"] == "lines"
    assert info["total"]["length"] == pytest.approx(30)
    par = si.selection_info(p, "EDGE", along_x[:2])
    assert par["pair"]["parallel"] == "parallel"


def test_two_cylinders_angle_between_axes():
    p = Processor()
    ok(p, "CYL, 0,0,0, 5, 10\nCYL, 30,0,0, 3, 10")
    a = p.model.bodies[1].entity_ids["FACE"][0]
    b = p.model.bodies[2].entity_ids["FACE"][0]
    info = si.selection_info(p, "FACE", [a, b])
    assert info["pair"]["angle_between"] == "axes" and info["pair"]["parallel"] == "parallel"
    assert info["pair"]["distance"] == pytest.approx(22) and info["pair"]["centres"] == pytest.approx(30)
    assert si.line(info) == ("2 faces, distance 22 mm (dx 22), centres 30 mm apart (dx 30), axes parallel, "
                             "total area 502.655 mm²")


def test_two_holes_give_the_distance_between_centres():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 80,50,12\nHOLE, 1, 20,25,12, 8\nHOLE, LAST, 60,45,12, 8")
    b = max(p.model.bodies)
    holes = [g for g in p.model.bodies[b].entity_ids["FACE"] if si.face_numbers(p, g)["type"] == "cylinder"]
    pr = si.selection_info(p, "FACE", holes)["pair"]
    assert pr["centres"] == pytest.approx(math.hypot(40, 20))
    assert abs(pr["cdx"]) == pytest.approx(40) and abs(pr["cdy"]) == pytest.approx(20) and pr["cdz"] == 0
    assert pr["distance"] == pytest.approx(math.hypot(40, 20) - 8)


def test_two_round_edges_give_the_distance_between_centres():
    p = Processor()
    ok(p, "CYL, 0,0,0, 5, 10\nCYL, 0,30,0, 3, 10")
    e1 = next(g for g in p.model.bodies[1].entity_ids["EDGE"] if si.edge_numbers(p, g).get("closed"))
    e2 = next(g for g in p.model.bodies[2].entity_ids["EDGE"] if si.edge_numbers(p, g).get("closed"))
    pr = si.selection_info(p, "EDGE", [e1, e2])["pair"]
    assert pr["centres"] == pytest.approx(30) and pr["cdy"] == pytest.approx(30)


def test_two_vertices_give_distance_and_each_axis():
    p = two_bodies()
    vs = p.model.bodies[1].entity_ids["VERTEX"]
    rows = {g: si.vertex_numbers(p, g)["at"] for g in vs}
    a = next(g for g, at in rows.items() if at == [0, 0, 0])
    b = next(g for g, at in rows.items() if at == [40, 20, 10])
    info = si.selection_info(p, "VERTEX", [a, b])
    assert info["pair"]["distance"] == pytest.approx(math.sqrt(40 ** 2 + 20 ** 2 + 10 ** 2))
    assert "(dx 40, dy 20, dz 10)" in si.line(info)
    assert si.line(info).startswith("2 vertices")


def test_two_bodies_total_volume_and_mass_note():
    p = two_bodies()
    ok(p, "MATERIAL, 1, STEEL")
    info = si.selection_info(p, "BODY", [1, 2])
    t = info["total"]
    assert t["volume"] == pytest.approx(8000 + math.pi * 25 * 10, rel=1e-6)
    assert t["mass_note"] == "1 of 2 have no material"
    assert info["pair"]["distance"] == pytest.approx(15)


def test_mesh_body_numbers():
    p = Processor()
    ok(p, "SPHERE, 0,0,0, 10\nTOMESH, 1")
    row = si.body_numbers(p, 1)
    assert row["kind"] == "mesh" and row["triangles"] > 100
    assert row["volume"] == pytest.approx(4 / 3 * math.pi * 1000, rel=0.03)
    assert "mesh of" in si.row_text("BODY", row, "mm")


def test_inches_are_shown_in_the_models_unit():
    p = Processor()
    ok(p, "/UNITS, IN\nBLOCK, 0,0,0, 2,1,1\nPICK, FACE, 6")
    assert si.line(si.selection_info(p)) == "face 6: plane, area 2 in²"


def test_nothing_picked():
    p = two_bodies()
    assert si.line(si.selection_info(p)) == ""
    assert "nothing is picked" in ok(p, "SELINFO").message


def test_selinfo_command_text_and_report():
    p = two_bodies()
    ok(p, "PICK, FACE, 1 2")
    steps = len(p.history)
    r = ok(p, "SELINFO")
    lines = r.message.splitlines()
    assert lines[0] == "face 1: plane, area 200 mm2" and lines[1] == "face 2: plane, area 200 mm2"
    assert "distance 40 mm (dx 40), parallel, facing away" in r.message
    assert "from (0, 0, 10) to (40, 0, 10)" in r.message
    assert r.report["pair"]["distance"] == 40
    assert len(p.history) == steps  # a query, not a step


def test_selinfo_with_kind_and_ids_and_json():
    p = two_bodies()
    data = json.loads(ok(p, 'SELINFO, FACE, "1 2", JSON').message)
    assert data["count"] == 2 and data["total"]["area"] == 400
    data = json.loads(ok(p, "SELINFO, BODY, 2, JSON").message)
    assert data["items"][0]["volume"] == pytest.approx(math.pi * 250, rel=1e-6)
    ok(p, "PICK, FACE, 6")
    assert json.loads(ok(p, "SELINFO, JSON").message)["items"][0]["id"] == 6
    assert ok(p, "SELINFO, EDGE").message.startswith("nothing is picked")  # faces are picked, not edges


def test_selinfo_by_body_name():
    p = two_bodies()
    ok(p, "NAME, 2, pin")
    assert "body 2 (pin)" in ok(p, "SELINFO, BODY, pin").message


def test_selinfo_errors():
    p = two_bodies()
    assert "kind" in fails(p, "SELINFO, SHAPE, 3")
    assert "whole numbers" in fails(p, 'SELINFO, FACE, "1 x"')
    assert "999" in fails(p, "SELINFO, FACE, 999")
    assert "say the kind" in fails(p, 'SELINFO, , "1 2"')
    assert "TEXT or JSON" in fails(p, "SELINFO, FACE, 1, XML")


def test_hover_text_names_the_body():
    p = two_bodies()
    ok(p, "NAME, 2, pin")
    side = p.model.bodies[2].entity_ids["FACE"][0]
    txt = si.hover_text(p, "FACE", side)
    assert txt.splitlines()[0].startswith(f"face {side}: cylinder r 5 (d 10)")
    assert txt.splitlines()[1] == "on body 2 (pin)"
    assert si.hover_text(p, "FACE", 1).splitlines()[1] == "on body 1"
    assert si.hover_text(p, "FACE", 999) == ""


def test_many_picks_are_counted_but_rows_capped():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 10,10,10\n*DO, i, 1, 12\nBLOCK, 20*i,0,0, 10,10,10\n*ENDDO")
    faces = [g for b in p.model.bodies.values() for g in b.entity_ids["FACE"]]
    info = si.selection_info(p, "FACE", faces, limit=10)
    assert info["count"] == 78 and len(info["items"]) == 10 and info["more"] == 68
    assert info["total"]["area"] == pytest.approx(78 * 100)
    assert "... and 68 more" in si.report_text(info)


def test_short_numbers():
    assert si._n(12.5) == "12.5" and si._n(800.0) == "800" and si._n(0.00031) == "0.00031"
    assert si._n(1234567.0) == "1.235e+06" and si._n(12345.6789) == "12345.7" and si._n(0) == "0"


def test_assistant_user_context_has_the_numbers():
    p = two_bodies()
    tb = Toolbox(p)
    ok(p, "PICK, FACE, 1 2")
    nums = tb.user_context()["selection"]["numbers"]
    assert nums["pair"]["distance"] == 40 and nums["total"]["area"] == 400
    assert nums["status_line"].startswith("2 faces, distance 40 mm")
    ok(p, "PICK, FACE, 6")
    assert tb.user_context()["selection"]["numbers"]["status_line"] == "face 6: plane, area 800 mm2"


def test_assistant_selection_numbers_tool():
    p = two_bodies()
    tb = Toolbox(p)
    data = tb.call("selection_numbers", {"kind": "BODY", "ids": [1, 2]})
    assert data["pair"]["distance"] == 15 and data["status_line"].startswith("2 bodies")
    with pytest.raises(ToolError):
        tb.selection_numbers("SHAPE", [1])
    with pytest.raises(ToolError):
        tb.selection_numbers(None, [1])
    ok(p, "PICK, FACE, 6")
    assert tb.selection_numbers()["items"][0]["id"] == 6
    assert tb.selection_numbers("EDGE")["count"] == 0
    assert "selection_numbers" in tb.tools and "templates" in tb.tools
    assert "error" in tb.call("selection_numbers", {"kind": "SHAPE", "ids": [1]})


# ---- item 87: typed values while sketching ----------------------------------------------
@pytest.fixture
def sk():
    p = Processor()
    ok(p, "SKETCH, s1, XY")
    return p, SketchController(p)


def run(p, cmds):
    for c in cmds:
        r = p.run(c)
        assert r.ok, (c, r.message)


def sketch(p):
    return p.model.sketches[p.model.active_sketch]


def typed(c, text):
    for ch in text:
        assert c.type_key(ch), ch


def test_boxes_follow_the_mouse_until_a_value_is_typed(sk):
    p, c = sk
    c.set_tool("LINE")
    assert c.typing_fields() == ()  # nothing placed yet: no boxes
    run(p, c.click(5, 5, 0.5))
    c.move(15, 5, 0.5)
    assert [(f.key, f.label, round(f.value, 6), f.fixed) for f in c.fields] == [("L", "length", 10, False),
                                                                                ("A", "angle", 0, False)]
    c.move(5, 25, 0.5)
    assert c.fields[0].value == pytest.approx(20) and c.fields[1].value == pytest.approx(90)


def test_line_typed_length_and_angle_become_sizes(sk):
    p, c = sk
    c.set_tool("LINE")
    run(p, c.click(5, 5, 0.5))
    c.move(20, 8, 0.5)
    typed(c, "40")
    assert c.fields[0].editing and c.fields[0].shown() == "40"
    c.type_tab()
    assert c.fields[0].fixed and c.fields[0].text == "40" and c.typed.focus == 1
    assert c.last_at[0] == pytest.approx(5 + 40 * math.cos(math.atan2(3, 15)))  # the mouse still sets the angle
    typed(c, "30")
    cmds = c.enter(0.5)
    assert cmds[0].startswith("SLINE, 5, 5, 39.641, 25")
    assert cmds[1:] == ["SDIM, LENGTH, 1, 40", "SDIM, ANGLE, 1, 30"]
    run(p, cmds)
    s = sketch(p)
    end = s.pt(s.ref("1.E").point)
    assert end[0] == pytest.approx(5 + 40 * math.cos(math.radians(30)), abs=1e-3)
    assert end[1] == pytest.approx(5 + 20, abs=1e-3)
    assert {k.kind for k in s.cons.values()} >= {"LENGTH", "ANGLE"}
    assert c.typed.values == {} and c.stage() == 1  # the chain goes on from the line's end, boxes clear


def test_line_chain_each_segment_its_own_values(sk):
    p, c = sk
    c.set_tool("LINE")
    run(p, c.click(0, 0, 0.5))
    c.move(10, 0.1, 0.5)
    c.type_value("L", "30")
    run(p, c.enter(0.5))  # level: H, no angle size
    c.move(30, 10, 0.5)
    c.type_value("L", "15")
    c.type_value("A", "90")
    cmds = c.enter(0.5)
    assert cmds[0] == "SLINE, 1.E, 30, 15, V"
    assert cmds[1:] == ["SDIM, LENGTH, 2, 15"]  # upright: V already says the angle
    run(p, cmds)
    s = sketch(p)
    assert s.pt(s.ref("2.E").point) == pytest.approx((30, 15), abs=1e-6)


def test_angle_only_projects_the_mouse(sk):
    p, c = sk
    c.set_tool("LINE")
    run(p, c.click(0, 0, 0.5))
    c.type_value("A", "45")
    c.move(10, 0, 0.5)  # the mouse 10 along: projected onto the 45 degree ray
    assert c.last_at == pytest.approx((5, 5))
    assert c.fields[0].value == pytest.approx(math.hypot(5, 5)) and c.fields[1].fixed


def test_typed_angle_over_180_is_written_as_a_line_angle(sk):
    p, c = sk
    c.set_tool("LINE")
    run(p, c.click(0, 0, 0.5))
    c.move(-5, -5, 0.5)
    c.type_value("L", "10")
    c.type_value("A", "225")
    cmds = c.enter(0.5)
    assert cmds[-1] == "SDIM, ANGLE, 1, 135"  # as the sketch measures a line: 0 to 180 either way round
    run(p, cmds)
    s = sketch(p)
    assert s.pt(s.ref("1.E").point) == pytest.approx((-10 / math.sqrt(2), -10 / math.sqrt(2)), abs=1e-3)


def test_rect_width_and_height(sk):
    p, c = sk
    c.set_tool("RECT")
    run(p, c.click(10, 10, 0.5))
    c.move(2, 3, 0.5)  # down and to the left
    assert [f.key for f in c.fields] == ["W", "H"] and c.fields[0].value == pytest.approx(8)
    c.type_value("W", "25")
    c.type_value("H", "12")
    cmds = c.enter(0.5)
    assert cmds[0] == "SRECT, 10, 10, -15, -2"
    assert cmds[-2:] == ["SDIM, LENGTH, 1, 25", "SDIM, LENGTH, 2, 12"]
    run(p, cmds)
    s = sketch(p)
    assert s.measure("LENGTH", ("1",)) == pytest.approx(25) and s.measure("LENGTH", ("2",)) == pytest.approx(12)


def test_centre_rect_full_width(sk):
    p, c = sk
    c.set_tool("CRECT")
    run(p, c.click(0, 0, 0.5))
    c.move(4, 4, 0.5)
    assert c.fields[0].value == pytest.approx(8)  # the whole width, not half
    c.type_value("W", "30")
    c.type_value("H", "10")
    cmds = c.enter(0.5)
    assert cmds[0] == "SRECTC, ORIGIN, 15, 5"
    run(p, cmds)
    s = sketch(p)
    assert s.measure("LENGTH", ("1",)) == pytest.approx(30) and s.measure("LENGTH", ("2",)) == pytest.approx(10)


def test_circle_radius_as_a_parameter_keeps_the_link(sk):
    p, c = sk
    ok(p, "D = 7")
    c.set_tool("CIRCLE")
    run(p, c.click(0, 50, 0.5))
    c.move(3, 52, 0.5)
    c.type_tab()  # Tab opens the first box, so a name can be typed
    typed(c, "D*2")
    cmds = c.enter(0.5)
    assert cmds[0].startswith("SCIRCLE, 0, 50, D*2") and cmds[-1] == "SDIM, RADIUS, 1, D*2"
    run(p, cmds)
    s = sketch(p)
    assert s.measure("RADIUS", ("1",)) == pytest.approx(14)
    n = next(i for i, e in enumerate(p.history, 1) if e.text.strip() == "D = 7")
    ok(p, f'HIST, EDIT, {n}, "D = 4"')  # the size follows the parameter
    assert p.model.sketches["S1"].measure("RADIUS", ("1",)) == pytest.approx(8)


def test_arc_chord_then_radius(sk):
    p, c = sk
    c.set_tool("ARC")
    run(p, c.click(0, 0, 0.5))
    c.move(20, 1, 0.5)
    c.type_value("L", "20")
    c.type_value("A", "0")
    assert c.enter(0.5) == []  # the end is placed; the arc needs its bulge
    assert c.stage() == 2 and [f.key for f in c.fields] == []  # until the mouse moves
    c.move(10, 4, 0.5)
    assert [f.key for f in c.fields] == ["R"]
    c.type_value("R", "15")
    cmds = c.enter(0.5)
    assert cmds[0].startswith("SARC3, ORIGIN,")
    assert cmds[1:] == ["SDIM, DIST, 1.S, 1.E, 20", "SDIM, RADIUS, 1, 15"]
    run(p, cmds)
    s = sketch(p)
    assert s.measure("RADIUS", ("1",)) == pytest.approx(15, abs=1e-6)
    assert s.measure("DIST", ("1.S", "1.E")) == pytest.approx(20, abs=1e-6)


def test_arc_middle_short_and_long_way():
    m = st.arc_middle((0, 0), (20, 0), 15, (10, 3))
    assert m[1] == pytest.approx(15 - math.sqrt(15 ** 2 - 10 ** 2))
    far = st.arc_middle((0, 0), (20, 0), 15, (10, 40))
    assert far[1] == pytest.approx(15 + math.sqrt(15 ** 2 - 10 ** 2))
    below = st.arc_middle((0, 0), (20, 0), 15, (10, -3))
    assert below[1] < 0
    assert st.circle_radius((0, 0), (20, 0), m) == pytest.approx(15)


def test_slot_length_and_radius(sk):
    p, c = sk
    c.set_tool("SLOT")
    run(p, c.click(0, 0, 0.5))
    c.move(30, 0.2, 0.5)
    c.type_value("L", "30")
    run(p, c.enter(0.5))
    c.move(10, 4.3, 0.5)
    c.type_value("R", "4.5")
    cmds = c.enter(0.5)
    assert cmds[0] == "SSLOT, ORIGIN, 30, 0, 4.5"
    assert cmds[1:] == ["SDIM, DIST, 1.C, 2.C, 30", "SDIM, RADIUS, 1, 4.5"]
    run(p, cmds)


def test_polygon_values_go_into_the_step(sk):
    p, c = sk
    c.set_tool("POLYGON")
    run(p, c.click(0, 0, 0.5))
    c.move(5, 5, 0.5)
    c.type_value("R", "10")
    c.type_value("A", "90")
    assert c.enter(0.5) == ["SNGON, ORIGIN, 6, 10, 90"]


def test_click_with_fixed_values_uses_them(sk):
    p, c = sk
    c.set_tool("CIRCLE")
    run(p, c.click(0, 0, 0.5))
    c.type_value("R", "6")
    cmds = c.click(17, 3, 0.5)  # clicking anywhere places it with the fixed radius
    assert cmds[0] == "SCIRCLE, ORIGIN, 6" and cmds[-1] == "SDIM, RADIUS, 1, 6"


def test_bad_values_are_refused_and_said(sk):
    p, c = sk
    c.set_tool("LINE")
    run(p, c.click(0, 0, 0.5))
    c.move(5, 0, 0.5)
    with pytest.raises(st.TypedError, match="more than 0"):
        c.type_value("L", "-3")
    with pytest.raises(st.TypedError):
        c.type_value("L", "nosuchname")
    typed(c, "-2")
    assert c.enter(0.5) == [] and "more than 0" in c.typed_error
    c.typed.focus, c.typed.buffer = 0, "nosuch"
    c.type_tab()
    assert "nosuch" in c.typed_error and "L" not in c.typed.values


def test_backspace_and_escape(sk):
    p, c = sk
    c.set_tool("LINE")
    run(p, c.click(0, 0, 0.5))
    c.move(5, 0, 0.5)
    typed(c, "123")
    assert c.type_key("\b") and c.fields[0].buffer == "12"
    assert c.type_escape()  # first Esc: the typed values go, the line goes on
    assert not c.typed.active and c.stage() == 1
    assert not c.type_escape()  # nothing typed: the next Esc ends the line (the view's job)


def test_letters_do_not_start_a_value(sk):
    p, c = sk
    c.set_tool("LINE")
    run(p, c.click(0, 0, 0.5))
    c.move(5, 0, 0.5)
    assert not c.type_key("L")  # a shortcut, not a value
    assert c.type_key("5") and c.type_key("W")  # once typing, names are fine (5W is caught on use)


def test_tab_cycles_round_the_boxes(sk):
    p, c = sk
    c.set_tool("RECT")
    run(p, c.click(0, 0, 0.5))
    c.move(5, 5, 0.5)
    c.type_tab()
    assert c.typed.focus == 0
    c.type_tab()
    assert c.typed.focus == 1
    c.type_tab()
    assert c.typed.focus == 0


def test_tools_without_boxes_ignore_keys(sk):
    p, c = sk
    c.set_tool("CIRCLE3")
    run(p, c.click(0, 0, 0.5))
    assert not c.type_key("5") and c.enter(0.5) == []
    c.set_tool("SELECT")
    assert not c.type_key("5")


def test_changing_tool_clears_typed_values(sk):
    p, c = sk
    c.set_tool("RECT")
    run(p, c.click(0, 0, 0.5))
    c.type_value("W", "5")
    c.set_tool("CIRCLE")
    assert c.typed.values == {} and c.fields == []


def test_field_shown_text():
    f = st.Field("L", "length", 12.34567)
    assert f.shown() == "12.346"
    f.fixed, f.text = True, "W/2"
    assert f.shown() == "W/2"
    f.editing, f.buffer = True, "3"
    assert f.shown() == "3"


# ---- item 88: templates ------------------------------------------------------------------
@pytest.fixture
def tdir(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELER_TEMPLATES", str(tmp_path / "tpl"))
    return tmp_path / "tpl"


def test_builtin_templates_are_there_in_order(tdir):
    ts = th.all_templates()
    assert [t.name for t in ts][:4] == ["part", "assembly", "sheet_metal", "drawing"]
    assert [t.title for t in ts][:4] == ["New part", "New assembly", "New sheet metal part", "New drawing"]
    assert all(t.source == "built-in" and t.about for t in ts[:4])


def test_every_builtin_template_runs_cleanly(tdir):
    for t in th.all_templates():
        p = Processor()
        results = th.start_from(p, t)
        assert results and all(r.ok for r in results), t.name


def test_new_from_a_template_makes_editable_first_steps(tdir):
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 1,1,1")
    r = ok(p, "NEW, part")
    assert r.message.startswith("new part from the template part:")
    assert not p.model.bodies
    texts = [e.text for e in p.history]
    assert any("W = 60" in t for t in texts) and any("LAYER, construction" in t for t in texts)
    assert p.model.properties["TITLE"] == "New part" and p.model.units == "MM"
    n = next(i for i, e in enumerate(p.history, 1) if "W = 60" in e.text)
    ok(p, f'HIST, EDIT, {n}, "W = 80"')
    assert p.evaluate("W") == 80


def test_sheet_metal_template_leaves_its_sketch_open(tdir):
    p = Processor()
    ok(p, "NEW, sheet_metal")
    assert p.model.active_sketch == "BASE"
    ok(p, "SRECT, 0, 0, 60, 40\nENDSKETCH\nSHEET, base, T, R, K")
    assert len(p.model.bodies) == 1


def test_new_by_title_and_unknown(tdir):
    p = Processor()
    assert ok(p, 'NEW, "New assembly"').message.startswith("new assembly")
    msg = fails(p, "NEW, rocket")
    assert "no template called 'rocket'" in msg and "part, assembly" in msg
    assert ok(p, "NEW").message == "new session" and p.cursor == 0


def test_template_list_and_show(tdir):
    p = Processor()
    txt = ok(p, "TEMPLATE").message
    assert "part: New part - units mm; layers construction; parameters W = 60, D = 40, T = 5" in txt
    data = json.loads(ok(p, "TEMPLATE, JSON").message)
    sm = next(t for t in data["templates"] if t["name"] == "sheet_metal")
    assert sm["sets"]["parameters"] == {"T": "2", "R": "2", "K": "0.44"} and sm["sets"]["sketches"] == ["base"]
    assert data["user_folder"] == str(tdir)
    show = ok(p, "TEMPLATE, SHOW, drawing").message
    assert "PROPERTY, SHEET, A3" in show and show.startswith("New drawing (built-in,")


def test_save_your_own_template_and_start_from_it(tdir):
    p = Processor()
    ok(p, 'NEW, part\nLAYER, welds, NEW, RED\nBLOCK, 0,0,0, W, D, T\nNAME, LAST, base')
    r = ok(p, 'TEMPLATE, SAVE, my_base, "My base plate", "A plate to start brackets from"')
    path = tdir / "my_base.cmd"
    assert path.is_file() and "NEW, my_base" in r.message
    head = path.read_text(encoding="utf-8").splitlines()[:3]
    assert head == ["! template: my_base", "! title: My base plate", "! about: A plate to start brackets from"]
    t = th.find("my_base")
    assert t.source == "user" and "welds" in t.sets()["layers"]
    q = Processor()
    ok(q, "NEW, my_base")
    assert len(q.model.bodies) == 1 and q.model.bodies[1].name == "base"
    assert q.model.bodies[1].shape is not None


def test_saved_template_default_title_and_about(tdir):
    p = Processor()
    ok(p, "/UNITS, CM\nW = 3")
    ok(p, "TEMPLATE, SAVE, metric_cm")
    t = th.find("metric_cm")
    assert t.title == "New metric cm" and "units cm; parameters W = 3" in t.about


def test_your_template_replaces_a_builtin_one_and_delete_brings_it_back(tdir):
    p = Processor()
    ok(p, "/UNITS, IN\nW = 2\nTEMPLATE, SAVE, part")
    assert th.find("part").source == "user"
    q = Processor()
    ok(q, "NEW, part")
    assert q.model.units == "IN"
    msg = ok(p, "TEMPLATE, DELETE, part").message
    assert "the built-in one is used again" in msg and th.find("part").source == "built-in"


def test_template_errors(tdir):
    p = Processor()
    assert "history is empty" in fails(p, "TEMPLATE, SAVE, empty")
    ok(p, "W = 1")
    assert "name is a word" in fails(p, 'TEMPLATE, SAVE, "two words"')
    assert "name is a word" in fails(p, "TEMPLATE, SAVE, 9lives")
    assert "built in" in fails(p, "TEMPLATE, DELETE, drawing")
    assert "give the template's name" in fails(p, "TEMPLATE, SHOW")
    assert "LIST, SHOW, SAVE or DELETE" in fails(p, "TEMPLATE, BURN, x")


def test_template_commands_are_not_history(tdir):
    p = Processor()
    ok(p, "W = 1\nTEMPLATE\nTEMPLATE, SAVE, w1")
    assert len(p.history) == 1


def test_a_broken_user_template_says_where_it_stopped(tdir):
    tdir.mkdir(parents=True)
    (tdir / "bad.cmd").write_text("! template: bad\nW = 1\nNOSUCHCOMMAND, 3\n", encoding="utf-8")
    p = Processor()
    msg = fails(p, "NEW, bad")
    assert "stopped at 'NOSUCHCOMMAND, 3'" in msg


def test_summarize_reads_the_steps():
    s = th.summarize(["/UNITS, CM", "LAYER, a, NEW, RED", "LAYER, a", "LAYER, DEFAULT", "W = 3 ! width",
                      'PROPERTY, TITLE, "Big, red"', "MATERIAL, ALL, STEEL", "SKETCH, s1, XY", "BLOCK, 0,0,0, 1,1,1",
                      "! just a note"])
    assert s == {"units": "CM", "layers": ["a"], "materials": ["STEEL"], "parameters": {"W": "3"},
                 "properties": {"TITLE": "Big, red"}, "sketches": ["s1"], "other": 1}


def test_drawing_uses_the_templates_paper(tdir, tmp_path):
    p = Processor()
    ok(p, "NEW, drawing\nBLOCK, 0,0,0, 40,20,10")
    r = ok(p, f'DRAWING, "{(tmp_path / "a.pdf").as_posix()}"')
    assert "A3 at" in r.message
    r = ok(p, f'DRAWING, "{(tmp_path / "a.dxf").as_posix()}"')  # a DXF stays at true size
    assert "A3" not in r.message
    r = ok(p, f'DRAWING, "{(tmp_path / "b.pdf").as_posix()}", , , , A4')
    assert "A4 at" in r.message


def test_assistant_templates_tool(tdir):
    p = Processor()
    data = Toolbox(p).templates()
    assert [t["name"] for t in data["templates"]][:4] == ["part", "assembly", "sheet_metal", "drawing"]
    assert data["start"].startswith("NEW, name") and data["save_own"].startswith("TEMPLATE, SAVE")
