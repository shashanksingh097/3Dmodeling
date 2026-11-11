"""Datums, work planes, part features (HOLE, SPLIT, SHELL, DRAFT, OFFSET) and measuring."""

import math

import pytest

from modeler.commands import Processor
from modeler.gui import feature_actions as fa


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1].message


def err(p, line):
    r = p.run(line)
    assert not r.ok, r.message
    return r.message


def val(p, expr):
    return p.evaluate(expr)


def vec(p, expr):
    return tuple(round(c, 6) + 0.0 for c in p.evaluate(expr))


BOX = "BLOCK, 0,0,0, 60,40,20\nNAME, LAST, part\n"


# ---- datums -------------------------------------------------------------------
def test_planes_every_way(p):
    ok(p, BOX + """PLANE, a, XY, 10
PLANE, b, FACE, 6
PLANE, c, FACE, 6, -5
PLANE, d, PN, (1,2,3), (0,0,2)
PLANE, e, 3P, (0,0,0), (1,0,0), (0,1,0)
PLANE, f, OFFSET, a, 5
PLANE, g, ANGLE, XY, X, 90
PLANE, h, MID, 1, 2
PLANE, i, NORMAL, 9, 0.5
PLANE, j, YZ""")
    assert vec(p, "ORIGIN('a')") == (0, 0, 10)
    assert vec(p, "ORIGIN('b')") == (30, 20, 20) and vec(p, "DIR('b')") == (0, 0, 1)
    assert vec(p, "ORIGIN('c')") == (30, 20, 15)
    assert vec(p, "ORIGIN('d')") == (1, 2, 3) and vec(p, "DIR('d')") == (0, 0, 1)
    assert vec(p, "DIR('e')") == (0, 0, 1)
    assert vec(p, "ORIGIN('f')") == (0, 0, 15)
    assert vec(p, "DIR('g')") == (0, -1, 0)
    assert vec(p, "ORIGIN('h')")[0] == 30
    assert abs(vec(p, "DIR('h')")[0]) == 1
    assert vec(p, "DIR('j')") == (1, 0, 0)
    assert "plane i" in p.run("LIST, DATUMS").message


def test_axes_and_points(p):
    ok(p, BOX + """CYL, 100, 0, 0, 5, 10
AXIS, a, Z
AXIS, b, PD, 1,2,3, 0,2,0
AXIS, c, 2P, (0,0,0), (0,0,5)
AXIS, d, FACE, 7
AXIS, e, FACE, 6
AXIS, f, PLANES, XY, YZ
POINT, p1, XYZ, 1, 2, 3
POINT, p2, VERTEX, 1
POINT, p3, CENTER, FACE, 6
POINT, p4, ON, 1, 0.5
POINT, p5, CENTER, BODY, part""")
    assert vec(p, "DIR('b')") == (0, 1, 0)
    assert vec(p, "ORIGIN('d')")[:2] == (100, 0) and vec(p, "DIR('d')") == (0, 0, 1)
    assert vec(p, "ORIGIN('e')") == (30, 20, 20)
    assert abs(vec(p, "DIR('f')")[1]) == 1
    assert vec(p, "ORIGIN('p3')") == (30, 20, 20)
    assert vec(p, "ORIGIN('p5')") == (30, 20, 10)
    # a round edge gives the axis of its circle, and its centre
    edge = int(p.run("SEL, S, EDGE, RADIUS, EQ, 5").message.split("EDGE")[1].split(",")[0])
    ok(p, f"AXIS, g, EDGE, {edge}\nPOINT, p6, CENTER, EDGE, {edge}")
    assert vec(p, "DIR('g')") == (0, 0, 1)
    assert vec(p, "ORIGIN('p6')")[:2] == (100, 0)


def test_datum_errors_and_names(p):
    ok(p, BOX + "CYL, 100,0,0, 5, 10\nPLANE, a, XY")
    assert "already a datum plane a" in err(p, "PLANE, a, YZ")
    assert "parallel" in err(p, "AXIS, x1, PLANES, XY, a")
    assert "one line" in err(p, "PLANE, x2, 3P, (0,0,0), (1,0,0), (2,0,0)")
    assert "curved" in err(p, "PLANE, x3, FACE, 7")
    assert "already used by body" in err(p, "PLANE, part, XY")
    assert "already used by datum" in err(p, "NAME, part, a")
    assert "reserved" in err(p, "PLANE, XY, XY")
    assert "too many" in err(p, "PLANE, x4, XY, 1, 2")
    ok(p, "W = 3")
    assert "parameter" in err(p, "PLANE, W, XY")
    ok(p, "DATUM, DELETE, a")
    assert "no plane or body named 'a'" in err(p, "SPLIT, part, a")


def test_datums_follow_undo_and_history_edits(p):
    ok(p, "H = 20\nBLOCK, 0,0,0, 10,10,H\nPLANE, top, FACE, 6")
    assert vec(p, "ORIGIN('top')")[2] == 20
    p.run("HIST, EDIT, 1, \"H = 35\"")
    assert vec(p, "ORIGIN('top')")[2] == 35
    p.run("UNDO")
    with pytest.raises(Exception):
        p.evaluate("ORIGIN('top')")
    p.run("REDO")
    assert vec(p, "ORIGIN('top')")[2] == 35


def test_workplane_places_new_shapes(p):
    ok(p, """PLANE, s, PN, 10,0,0, 1,0,0
WORKPLANE, s
BLOCK, 0,0,0, 2,3,4
RECT, 0,0,0, 10, 5
WORKPLANE, OFF
BLOCK, 0,0,0, 1,1,1""")
    b = val(p, "BBOX(1)")
    # local x is world Y, local y is world Z, local z (the normal) is world X
    assert tuple(round(b.get(k), 6) for k in ("xmin", "dx", "dy", "dz")) == (10, 4, 2, 3)
    assert round(val(p, "BBOX(2).xmin"), 6) == 10 and round(val(p, "BBOX(2).dx"), 6) == 0
    assert round(val(p, "BBOX(3).xmin"), 6) == 0  # back to world


# ---- HOLE ---------------------------------------------------------------------
def test_holes_simple_cbore_csink_and_tip(p):
    ok(p, BOX)
    v0 = val(p, "VOL(part)")
    ok(p, "HOLE, part, 10, 20, 20, 6")
    assert math.isclose(v0 - val(p, "VOL(part)"), math.pi * 9 * 20, rel_tol=1e-6)
    v1 = val(p, "VOL(part)")
    ok(p, "HOLE, part, 30, 20, 20, 6, 10, CBORE, 10, 4")
    assert math.isclose(v1 - val(p, "VOL(part)"), math.pi * (25 * 4 + 9 * 6), rel_tol=1e-6)
    v2 = val(p, "VOL(part)")
    msg = ok(p, "HOLE, part, 50, 20, 20, 6, 0, CSINK, 12")
    assert "countersink 12 at 90 deg" in msg
    cone = math.pi * 3 / 3 * (36 + 9 + 18)  # frustum r 6 -> 3 over 3 mm
    assert math.isclose(v2 - val(p, "VOL(part)"), cone + math.pi * 9 * 17, rel_tol=1e-6)
    v3 = val(p, "VOL(part)")
    msg = ok(p, "HOLE, part, 30, 0, 10, 4, 8, SIMPLE, , , 120")  # into the front face, drill point
    assert "into face 3" in msg
    tip = math.pi * 4 * (2 / math.tan(math.radians(60))) / 3
    assert math.isclose(v3 - val(p, "VOL(part)"), math.pi * 4 * 8 + tip, rel_tol=1e-6)
    assert p.run("CHECK, part").message.endswith(")") and "OK" in p.run("CHECK, part").message


def test_hole_errors_and_direction(p):
    ok(p, BOX)
    assert "misses" in err(p, "HOLE, part, 100, 100, 100, 5")
    assert "kind must be" in err(p, "HOLE, part, 10,10,20, 5, 5, BIG")
    assert "counterbore" in err(p, "HOLE, part, 10,10,20, 5, 5, CBORE, 4, 2")
    # an explicit direction: sideways through the whole part along -Y from the back face
    v0 = val(p, "VOL(part)")
    ok(p, "HOLE, part, 30, 40, 10, 4, 0, SIMPLE, , , , 0, -1, 0")
    assert math.isclose(v0 - val(p, "VOL(part)"), math.pi * 4 * 40, rel_tol=1e-6)


def test_hole_on_a_workplane(p):
    ok(p, BOX + "PLANE, top, FACE, 6\nWORKPLANE, top\nHOLE, part, 0, 0, 0, 8\nWORKPLANE, OFF")
    ok(p, "SEL, S, FACE, TYPE, CYLINDER")
    assert vec(p, "CENT(SELID(1), 'FACE')")[:2] == (30, 20)


def test_hole_keeps_face_ids(p):
    ok(p, BOX + "HOLE, part, 10, 20, 20, 6")
    for gid in range(1, 7):
        assert val(p, f"EXISTS({gid}, 'FACE')")
    assert vec(p, "CENT(6, 'FACE')")[2] == 20


# ---- SPLIT --------------------------------------------------------------------
def test_split_by_plane_keeps_id_name_and_unique_ids(p):
    ok(p, BOX + "PLANE, mid, YZ, 25")
    msg = ok(p, "SPLIT, part, mid")
    assert "other pieces: bodies 2" in msg
    assert p.model.body_by_name("part").id == 1
    assert round(val(p, "BBOX(part).xmin"), 6) == 25  # the piece on the normal side keeps the name
    assert math.isclose(val(p, "VOL(1)") + val(p, "VOL(2)"), 48000)
    ids = [i for b in p.model.bodies.values() for i in b.entity_ids["FACE"]]
    assert len(ids) == len(set(ids)) == 12
    assert "OK" in p.run("CHECK").message


def test_split_keep_one_side_and_errors(p):
    ok(p, BOX + "PLANE, low, XY, 5")
    ok(p, "SPLIT, part, low, BELOW")
    assert len(p.model.bodies) == 1 and math.isclose(val(p, "VOL(part)"), 60 * 40 * 5)
    assert "does not cut" in err(p, "SPLIT, part, XY, ABOVE")
    assert "keep must be" in err(p, "SPLIT, part, low, SIDEWAYS")


def test_split_by_body(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nCYL, 5,5,-1, 2, 12\nNAME, LAST, cutter\nSPLIT, 1, cutter")
    assert len(p.model.bodies) == 3 and "cutter" in [b.name for b in p.model.bodies.values()]
    assert math.isclose(val(p, "VOL(1)"), 1000 - math.pi * 40, rel_tol=1e-6)
    assert "cannot split itself" in err(p, "SPLIT, 1, 1")


# ---- SHELL, DRAFT, OFFSET -------------------------------------------------------
def test_shell_open_keeps_side_face_ids(p):
    ok(p, "BLOCK, 0,0,0, 40,30,20\nPICK, FACE, 6\nSHELL, 2")
    assert math.isclose(val(p, "VOL(1)"), 40 * 30 * 20 - 36 * 26 * 18)
    assert not val(p, "EXISTS(6, 'FACE')")  # the opened face is gone
    assert vec(p, "CENT(5, 'FACE')")[2] == 0 and vec(p, "CENT(1, 'FACE')")[0] == 0
    assert "OK" in p.run("CHECK, 1").message


def test_shell_closed_and_too_thick(p):
    ok(p, "BLOCK, 0,0,0, 40,30,20\nSEL, S, BODY, ID, 1\nSHELL, 3")
    assert math.isclose(val(p, "VOL(1)"), 24000 - 34 * 24 * 14, rel_tol=1e-6)
    ok(p, "UNDO\nUNDO\nPICK, FACE, 6")
    msg = err(p, "SHELL, 30")
    assert "thickest wall that works here is about 14" in msg
    assert "select faces" in Processor().run("SHELL, 1").message


def test_draft_tilts_side_faces_and_keeps_ids(p):
    ok(p, "BLOCK, 0,0,0, 40,30,20\nSEL, S, FACE, ID, 1, 4\nDRAFT, 5")
    t = 20 * math.tan(math.radians(5))
    top = (40 - 2 * t) * (30 - 2 * t)
    assert math.isclose(val(p, "AREA(6)"), top, rel_tol=1e-6)
    for gid in range(1, 7):
        assert val(p, f"EXISTS({gid}, 'FACE')")
    assert "OK" in p.run("CHECK").message
    ok(p, "PICK, FACE, 6")
    assert "side faces only" in err(p, "DRAFT, 5")


def test_draft_about_a_datum_plane(p):
    ok(p, "BLOCK, 0,0,0, 40,30,20\nPLANE, top, XY, 20\nSEL, S, FACE, ID, 1, 4\nDRAFT, 5, top")
    assert math.isclose(val(p, "AREA(6)"), 1200, rel_tol=1e-9)  # the top keeps its size
    assert val(p, "AREA(5)") > 1200


def test_offset(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nOFFSET, 1, 1, SHARP")
    assert math.isclose(val(p, "VOL(1)"), 12 ** 3, rel_tol=1e-6)
    ok(p, "OFFSET, 1, -2")
    assert math.isclose(val(p, "VOL(1)"), 8 ** 3, rel_tol=1e-6)
    ok(p, "OFFSET, 1, 1")  # rounded corners
    assert 8 ** 3 < val(p, "VOL(1)") < 10 ** 3
    assert "cannot be offset" in err(p, "OFFSET, 1, -20")


# ---- measuring ----------------------------------------------------------------
def test_dist_angle_and_queries(p):
    ok(p, BOX + "BLOCK, 70,0,0, 10,10,10\nPLANE, mid, XY, 10")
    msg = p.run("DIST, BODY, part, BODY, 2").message
    assert msg.startswith("distance 10 between BODY 1 and BODY 2") and "dx 10" in msg
    assert p.run("DIST, DATUM, mid, FACE, 6").message.startswith("distance 10 between mid and FACE 6")
    assert val(p, "GAP(part, 2)") == pytest.approx(10)
    assert p.run("ANGLE, FACE, 1, FACE, 3").message.startswith("angle 90 deg")
    assert p.run("ANGLE, EDGE, 1, XY").message.startswith("angle 90 deg")
    assert p.run("ANGLE, DATUM, mid, XY").message.startswith("angle 0 deg")
    ok(p, "PICK, FACE, 1\nPICK, FACE, 6, A")
    assert p.run("ANGLE").message.startswith("angle 90 deg between FACE 1 and FACE 6")
    p.run("PICK, FACE, 1")
    assert "select two" in err(p, "DIST")
    # queries are not history
    n = p.cursor
    p.run("DIST, BODY, 1, BODY, 2")
    assert p.cursor == n


def test_massprop(p):
    ok(p, "BLOCK, 0,0,0, 100,10,10")
    msg = p.run("MASSPROP, 1, 1000").message
    assert "volume 10000 mm3" in msg and "mass 0.01 kg" in msg and "centre of mass (50, 5, 5)" in msg
    # inertia about the long axis: m (b^2 + c^2) / 12 = 0.01 * 200 / 12 kg.mm2
    assert "0.166667" in msg
    assert "per unit density" in p.run("MASSPROP").message


def test_clash(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nBLOCK, 5,5,5, 10,10,10\nBLOCK, 30,0,0, 5,5,5")
    msg = p.run("CLASH").message
    assert "bodies 1 and 2 OVERLAP: 125" in msg and "1 overlap" in msg
    assert "gap 15" in p.run("CLASH, 2, 3").message


def test_section_is_a_view_setting(p):
    ok(p, BOX + "PLANE, mid, YZ, 30")
    n = p.cursor
    assert "section view at plane mid" in p.run("SECTION, mid").message
    assert p.section[0].name == "mid" and p.cursor == n
    p.run("SECTION, OFF")
    assert p.section is None


# ---- the GUI's Features toolbar builds plain commands ---------------------------
def test_feature_actions_build_commands(p):
    ok(p, BOX)
    with pytest.raises(fa.NeedInput):
        fa.plane_on_face(p)
    ok(p, "PICK, FACE, 6")
    assert fa.plane_on_face(p) == ["PLANE, P1, FACE, 6"]
    assert fa.hole_on_face(p, 6) == ["HOLE, part, 30, 20, 20, 6"]
    assert fa.workplane_on_face(p) == ["PLANE, WP1, FACE, 6", "WORKPLANE, WP1"]
    for line in fa.workplane_on_face(p):
        ok(p, line)
    ok(p, "PICK, FACE, 6")
    assert fa.hole_on_face(p, 6) == ["HOLE, part, 0, 0, 0, 6"]  # in the work plane
    assert fa.workplane_on_face(p) == ["WORKPLANE, OFF"]
    assert fa.faces_selected(p, "SHELL", 2) == ["SHELL, 2"]
    assert fa.section_toggle(p) == ["SECTION, WP1"]
    with pytest.raises(fa.NeedInput):
        fa.two_selected(p, "DIST")


def test_demo_script_rebuilds_after_an_edit(p):
    with open("scripts/bracket_features.cmd", encoding="utf-8") as f:
        ok(p, f.read())
    assert len(p.model.bodies) == 1
    v = val(p, "VOL(housing)")
    i = p.entry_for_param("WALL")
    msg = p.run(f'HIST, EDIT, {i}, "WALL = 4"').message
    assert "failed" not in msg, msg
    assert val(p, "VOL(housing)") > v
    assert "OK" in p.run("CHECK").message
