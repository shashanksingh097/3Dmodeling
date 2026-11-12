"""Sketch editing: STRIM, SEXTEND, SFILLET, SOFFSET, SMIRROR, SPATTERN,
SPROJECT, and the Trim / Extend / Fillet mouse tools."""

import math

import pytest

from modeler.commands import Processor
from modeler.gui import sketch_tools as st

RECT = """SKETCH, s, XY
SRECT, 0,0, 40,20
SDIM, LENGTH, 1, 40
SDIM, LENGTH, 2, 20
SCON, COINCIDENT, 1.S, ORIGIN
"""


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def err(p, line):
    r = p.run(line)
    assert not r.ok
    return r.message


def sk(p, name="S"):
    return p.model.sketches[name]


def pt(s, ref):
    return s.pt(s.ref(ref).point)


def close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ---- SFILLET ----------------------------------------------------------------------------

def test_fillet_rounds_a_corner_and_keeps_the_sketch_fully_defined(p):
    ok(p, RECT + "SFILLET, 1.E, 2.E, 5")
    s = sk(p)
    assert s.dof == 0 and not s.redundant
    arcs = [g for g in s.geos.values() if g.kind == "ARC"]
    assert len(arcs) == 2 and all(abs(s.radius(a) - 5) < 1e-9 for a in arcs)
    assert close(pt(s, "1.E"), (35, 0)) and close(pt(s, "2.S"), (40, 5))
    ok(p, "ENDSKETCH\nEXTRUDE, s, 5")
    assert p.evaluate("VOL(LAST)") == pytest.approx(5 * (800 - 2 * (25 - math.pi * 25 / 4)))


def test_fillet_radius_is_a_size_to_edit(p):
    ok(p, RECT + "SFILLET, 1.E, 5\nENDSKETCH\nEXTRUDE, s, 1")
    rows = st.sketch_dimensions(p, "s")
    radius = [r for r in rows if r[1].startswith("radius")]
    assert radius and radius[0][3] == "5"
    line = st.dimension_edit(p, p.history[radius[0][2] - 1].uid, "8")
    assert line.endswith('"SFILLET, 1.E, 8"')
    ok(p, line)
    assert p.evaluate("VOL(LAST)") == pytest.approx(800 - (64 - math.pi * 64 / 4))


def test_fillet_keeps_sizes_to_the_corner(p):
    # the length of line 1 was measured to the corner: it is still 40 to the corner point
    ok(p, RECT + "SFILLET, 1.E, 5")
    ok(p, "SDEL, C9\nSDIM, LENGTH, 4, 20")  # 4 is the left side; drop the 40 and size differently
    s = sk(p)
    corner = [g for g in s.geos.values() if g.kind == "POINT" and g.construction][0]
    assert close(s.pt(corner.pts["P"]), (40, 0))


def test_fillet_errors(p):
    ok(p, RECT)
    assert "does not fit" in err(p, "SFILLET, 1.E, 30")
    assert "end of a line" in err(p, "SFILLET, 1, 3")
    ok(p, "SLINE, 100,0, 120,0")
    assert "nothing else ends" in err(p, "SFILLET, 5.E, 1")


# ---- SOFFSET ------------------------------------------------------------------------------

def test_offset_of_a_closed_chain_goes_outwards_and_meets_at_the_corners(p):
    ok(p, RECT + "SFILLET, 1.E, 2.E, 5\nSOFFSET, 3, 1, 2, 3, 4, 6, 8")
    s = sk(p)
    assert s.dof == 0 and not s.redundant
    new = [s.geos[n] for n in range(9, 15)]
    assert sorted(g.kind for g in new) == ["ARC", "ARC", "LINE", "LINE", "LINE", "LINE"]
    assert close(pt(s, "9.S"), (-3, -3))  # a sharp corner, met again
    assert {round(s.radius(g), 9) for g in new if g.kind == "ARC"} == {8.0}


def test_offset_follows_its_original(p):
    ok(p, RECT + "SOFFSET, 2, 1, 2, 3, 4")
    s = sk(p)
    assert s.dof == 0
    ok(p, "SDEL, C9\nSDIM, LENGTH, 1, 60")
    s = sk(p)
    xs = [s.pt(i)[0] for g in s.geos.values() if g.n > 4 for i in g.pts.values()]
    assert max(xs) == pytest.approx(62) and min(xs) == pytest.approx(-2)


def test_offset_of_an_open_line_and_of_a_circle(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 10,0\nSOFFSET, 2, 1\nSOFFSET, -2, 1")
    s = sk(p)
    assert close(pt(s, "2.S"), (0, 2)) and close(pt(s, "2.E"), (10, 2))  # positive: to the left
    assert close(pt(s, "3.S"), (0, -2))
    ok(p, "SCIRCLE, 50, 0, 5\nSOFFSET, 1.5, 4\nSOFFSET, -1, 4")
    s = sk(p)
    assert (s.radius(s.geos[5]), s.radius(s.geos[6])) == (pytest.approx(6.5), pytest.approx(4))
    assert "more than the radius" in err(p, "SOFFSET, -5, 4")


def test_offset_inside_a_profile_makes_a_wall(p):
    ok(p, RECT + "SOFFSET, -2, 1, 2, 3, 4\nENDSKETCH\nEXTRUDE, s, 1")
    assert p.evaluate("VOL(LAST)") == pytest.approx(800 - 36 * 16)


# ---- STRIM, SEXTEND --------------------------------------------------------------------------

CROSS = """SKETCH, t, XY
SLINE, 0,0, 50,0
SLINE, 10,-10, 10,10
SLINE, 30,-10, 30,10
SCIRCLE, 20, 0, 5
"""


def test_trim_the_middle_the_end_a_circle_and_a_lone_curve(p):
    ok(p, CROSS + "STRIM, 1, 20, 0")  # inside the circle: line 1 is cut in two
    s = sk(p, "T")
    assert close(pt(s, "1.E"), (15, 0)) and close(pt(s, "5.S"), (25, 0)) and close(pt(s, "5.E"), (50, 0))
    ok(p, "STRIM, 1, 2, 0")  # the start piece, up to line 2
    assert close(pt(sk(p, "T"), "1.S"), (10, 0))
    ok(p, "STRIM, 4, 20, 5")  # the top of the circle
    s = sk(p, "T")
    a1, a2 = s.arc_angles(s.geos[4])
    assert s.geos[4].kind == "ARC" and (a1 % 360, a2 - a1) == (pytest.approx(180), pytest.approx(180))
    ok(p, "SLINE, 0,40, 10,40\nSTRIM, 6, 5, 40")
    assert 6 not in sk(p, "T").geos


def test_trimmed_ends_stay_on_the_cutting_curve(p):
    ok(p, CROSS + "STRIM, 1, 45, 0\nSMOVE, 3.S, 36, -10")
    s = sk(p, "T")
    a, b = pt(s, "3.S"), pt(s, "3.E")
    e = pt(s, "1.E")
    assert abs((b[0] - a[0]) * (e[1] - a[1]) - (b[1] - a[1]) * (e[0] - a[0])) < 1e-6  # still on line 3


def test_extend_to_the_next_curve_or_to_a_given_one(p):
    ok(p, CROSS + "SLINE, 0,30, 20,30\nSEXTEND, 5.E, 3\nSEXTEND, 2.E")
    s = sk(p, "T")
    assert close(pt(s, "5.E"), (30, 30)) and close(pt(s, "2.E"), (10, 30))
    assert "never meets" in err(p, "SEXTEND, 3.S")
    assert "circle" in err(p, "SEXTEND, 4.E")


# ---- SMIRROR, SPATTERN ------------------------------------------------------------------------

def test_mirror_about_an_axis_and_a_line_and_follow(p):
    ok(p, "SKETCH, s, XY\nSLINE, 5,0, 20,10\nSARC, 10,0, 4, 0, 90\nSMIRROR, V, 1, 2")
    s = sk(p)
    assert close(pt(s, "3.S"), (-5, 0)) and close(pt(s, "3.E"), (-20, 10))
    assert s.geos[4].kind == "ARC" and s.arc_angles(s.geos[4]) == (pytest.approx(90), pytest.approx(180))
    ok(p, "SMOVE, 1.E, 20, 30")
    assert close(pt(sk(p), "3.E"), (-20, 30))
    ok(p, "SLINE, 0,-10, 30,-10\nSMIRROR, 5, 1")
    assert close(pt(sk(p), "6.E"), (20, -50))
    assert "lies on the mirror line" in err(p, "SMIRROR, 5, 5")


def test_pattern_in_a_row_and_round_a_point(p):
    ok(p, "SKETCH, s, XY\nSCIRCLE, 10, 0, 2\nSPATTERN, LINEAR, 4, 0, 5, 1")
    s = sk(p)
    assert [s.pt(s.geos[n].pts["C"]) for n in (2, 3, 4)] == [(10, 5), (10, 10), (10, 15)]
    ok(p, "SPATTERN, POLAR, 6, 360, O, 1")
    s = sk(p)
    centres = [s.pt(s.geos[n].pts["C"]) for n in range(5, 10)]
    assert close(centres[0], (10 * math.cos(math.pi / 3), 10 * math.sin(math.pi / 3)))
    ok(p, "SDIM, RADIUS, 1, 3")  # the copies keep the radius
    s = sk(p)
    assert all(s.radius(s.geos[n]) == pytest.approx(3) for n in range(2, 10))
    ok(p, "SPATTERN, POLAR, 3, 90, 50, 50, 1")  # a part ring round (50, 50): last one at 90 degrees
    s = sk(p)
    last = max(g.n for g in s.geos.values() if g.kind == "CIRCLE")
    assert close(s.pt(s.geos[last].pts["C"]), (100, 10))
    assert "whole number, 2 or more" in err(p, "SPATTERN, LINEAR, 1, 0, 5, 1")


def test_patterned_holes_extrude(p):
    ok(p, "SKETCH, s, XY\nSRECT, 0,0, 60,20\nSCIRCLE, 10, 10, 3\nSPATTERN, LINEAR, 3, 20, 0, 5\nENDSKETCH\nEXTRUDE, s, 2")
    assert p.evaluate("VOL(LAST)") == pytest.approx(2 * (1200 - 3 * math.pi * 9))


# ---- SPROJECT ----------------------------------------------------------------------------------

def test_project_a_face_and_edit_the_body_before_it(p):
    ok(p, "BLOCK, 0,0,0, 40,20,10\nCYL, 20,10,0, 4, 10\nSUBTRACT, 1, 2\nPLANE, top, XY, 10\nSKETCH, s, top")
    from modeler.geometry.features import face_plane

    m = p.model
    top = next(g for g in m.bodies[3].entity_ids["FACE"]
               if (fp := face_plane(m.entity_shape("FACE", g))) and abs(fp[0][2] - 10) < 1e-9)
    ok(p, f"SPROJECT, FACE, {top}")
    s = sk(p)
    assert s.dof == 0 and sorted(g.kind for g in s.geos.values()) == ["CIRCLE", "LINE", "LINE", "LINE", "LINE"]
    ok(p, "ENDSKETCH\nEXTRUDE, s, 3")
    assert p.evaluate("VOL(LAST)") == pytest.approx(3 * (800 - math.pi * 16))
    ok(p, 'HIST, EDIT, 2, "CYL, 20,10,0, 6, 10"')  # the hole grows: the projected circle follows
    assert p.evaluate("VOL(LAST)") == pytest.approx(3 * (800 - math.pi * 36))


def test_project_an_edge_that_is_square_to_the_sketch(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nSKETCH, s, XY")
    m = p.model
    from OCP.BRepAdaptor import BRepAdaptor_Curve

    from modeler.geometry.sweep import _as_edge

    upright = next(g for g in m.bodies[1].entity_ids["EDGE"]
                   if abs(BRepAdaptor_Curve(_as_edge(m.entity_shape("EDGE", g))).DN(0, 1).Z()) > 0.5)
    assert "square to the sketch" in err(p, f"SPROJECT, {upright}")


# ---- the mouse tools -----------------------------------------------------------------------------

def test_trim_extend_and_fillet_tools_send_the_commands(p):
    ok(p, CROSS + "SLINE, 0,30, 20,30")
    c = st.SketchController(p)
    c.set_tool("TRIM")
    piece = c.move(20, 0.1, 0.5).arcs
    assert piece and close(piece[0][0], (15, 0)) and close(piece[0][-1], (25, 0))
    assert c.click(20, 0.1, 0.5) == ["STRIM, 1, 20, 0.1"]
    c.set_tool("EXTEND")
    assert c.click(19, 30.2, 0.5) == ["SEXTEND, 5.E"]
    ok(p, "SEXTEND, 5.E, 3\nSEXTEND, 2.E")
    c.set_tool("FILLET")
    assert c.click(10, 30, 0.5) == []  # a T, not a corner
    ok(p, "ENDSKETCH\n" + RECT)
    assert c.click(40.1, 0.1, 0.5) == ["SFILLET, 1.E, 4"]  # a fifth of the shorter side, rounded
    ok(p, "SFILLET, 1.E, 2")
    assert any(g.kind == "ARC" for g in sk(p).geos.values())


def test_selection_buttons_build_the_commands(p):
    ok(p, RECT + "SSEL, 1, 2, 3, 4")
    assert st.offset_command(p, "2") == ["SOFFSET, 2, 1, 2, 3, 4"]
    assert st.mirror_axes(p)[:2] == ["4", "3"]
    assert st.mirror_command(p, "V") == ["SMIRROR, V, 1, 2, 3, 4"]
    assert st.pattern_command(p, "LINEAR", "3, 50, 0") == ["SPATTERN, LINEAR, 3, 50, 0, 1, 2, 3, 4"]
    ok(p, "SSEL, NONE")
    with pytest.raises(st.NeedSelection):
        st.offset_command(p, "2")
