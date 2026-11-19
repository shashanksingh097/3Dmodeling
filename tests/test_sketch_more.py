"""More sketch tools: SCHAMFER, SSPLIT, SCORNER, power trim (STRIM with
several pieces), STRANSFORM, the new drawing commands (SARCT, SCIRCLE3,
SRECTC, SRECT3, SNGON, SSLOTARC), and the mouse tools that send them."""

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


def vol(p):
    return p.evaluate("VOL(LAST)")


# ---- SCHAMFER ---------------------------------------------------------------------------

def test_chamfer_equal_two_distances_and_angle_keep_the_sketch_fully_defined(p):
    ok(p, RECT + "SCHAMFER, 1.E, 4\nSCHAMFER, 3.E, 4, 6\nSCHAMFER, 4.E, 4, ANGLE, 30")
    s = sk(p)
    assert s.dof == 0 and not s.redundant
    assert close(pt(s, "1.E"), (36, 0)) and close(pt(s, "2.S"), (40, 4))
    d2 = 4 * math.sin(math.radians(30)) / math.sin(math.radians(60))  # law of sines in the cut-off corner
    ok(p, "ENDSKETCH\nEXTRUDE, s, 2")
    assert vol(p) == pytest.approx(2 * (800 - 8 - 12 - 0.5 * 4 * d2))


def test_chamfer_sizes_are_dimensions_that_edit_the_right_argument(p):
    ok(p, RECT + "SCHAMFER, 1.E, 4, 6")
    rows = st.sketch_dimensions(p, "s")
    sizes = sorted(r[3] for r in rows if r[2] == 6)  # the SCHAMFER entry
    assert sizes == ["4", "6"]
    s = sk(p)
    second = [c for c in s.cons.values() if c.kind == "DIST" and c.value == 6][0]
    line = st.edit_dimension_entry(p, second.label, "7")
    assert line.endswith('"SCHAMFER, 1.E, 4, 7"')
    ok(p, line)
    assert close(pt(sk(p), "2.S"), (40, 7))


def test_chamfer_keeps_a_length_to_the_corner(p):
    ok(p, RECT + "SCHAMFER, 1.E, 5")
    s = sk(p)
    # the 40 that was the bottom line's length is now measured to the corner point
    assert any(c.kind == "DIST" and c.value == 40 for c in s.cons.values())
    ok(p, "HIST, EDIT, 3, \"SDIM, LENGTH, 1, 50\"")
    assert close(pt(sk(p), "1.E"), (45, 0))


def test_chamfer_refusals(p):
    ok(p, RECT)
    assert "does not fit" in err(p, "SCHAMFER, 1.E, 25")
    assert "angle" in err(p, "SCHAMFER, 1.E, 4, ANGLE, 95")
    assert "give the corner" in err(p, "SCHAMFER, 4")
    ok(p, "SFILLET, 2.E, 3")
    assert "two lines" in err(p, "SCHAMFER, 2.E, 1")


# ---- SSPLIT -------------------------------------------------------------------------------

def test_split_a_line_at_points_keeps_the_pieces_on_one_line(p):
    ok(p, RECT + "SSPLIT, 1, 10, 3, 30, -2")
    s = sk(p)
    assert [s.describe(n) for n in (1, 5, 6)] == ["line 1 (0, 0) to (10, 0)", "line 5 (10, 0) to (30, 0)",
                                                  "line 6 (30, 0) to (40, 0)"]
    ok(p, "SDIM, LENGTH, 5, 25")  # a size on one piece
    s = sk(p)
    assert math.dist(pt(s, "5.S"), pt(s, "5.E")) == pytest.approx(25)
    assert all(abs(pt(s, f"{n}.{e}")[1]) < 1e-9 for n in (1, 5, 6) for e in "SE")  # still one straight line


def test_split_by_a_crossing_curve_and_a_circle_in_two(p):
    ok(p, "SKETCH, s, XY\nSCIRCLE, 0, 0, 10\nSLINE, -20, 0, 20, 0\nSSPLIT, 1, 2\nSSPLIT, 2, 1")
    s = sk(p)
    kinds = sorted(g.kind for g in s.geos.values())
    assert kinds == ["ARC", "ARC", "LINE", "LINE", "LINE"]
    assert s.dof == 7  # circle: centre, radius and two split points held on the line
    ok(p, "SDEL, 2, 5, 3\nENDSKETCH\nEXTRUDE, s, 1")  # the upper half: arc 1 and the middle piece 4
    assert vol(p) == pytest.approx(math.pi * 50, rel=1e-6)
    p2 = Processor()
    ok(p2, "SKETCH, s, XY\nSCIRCLE, 0, 0, 10")
    assert "two places" in err(p2, "SSPLIT, 1, 10, 0")


def test_split_refusals(p):
    ok(p, RECT)
    assert "end" in err(p, "SSPLIT, 1, 50, 0")
    assert "does not cross" in err(p, "SSPLIT, 1, 3")


# ---- SCORNER ------------------------------------------------------------------------------

def test_corner_extends_and_trims_to_meet(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 30,0\nSLINE, 40,5, 40,30\nSCORNER, 1, 2")
    s = sk(p)
    assert close(pt(s, "1.E"), (40, 0)) and close(pt(s, "2.S"), (40, 0))
    assert any(c.kind == "COINCIDENT" for c in s.cons.values())
    # trimming back: keep the clicked parts
    ok(p, "SLINE, 0,10, 50,10\nSCORNER, 3, 2, 5, 10, 40, 20")
    s = sk(p)
    assert close(pt(s, "3.E"), (40, 10)) and close(pt(s, "2.S"), (40, 10))
    assert "parallel" in err(p, "SCORNER, 1, 3")


def test_corner_with_an_arc(p):
    ok(p, "SKETCH, s, XY\nSARC, 0, 0, 10, 0, 60\nSLINE, 8, -5, 8, 3\nSCORNER, 1, 2")
    s = sk(p)
    assert close(pt(s, "1.E"), (8, 6)) and close(pt(s, "2.E"), (8, 6))  # the arc trimmed, the line extended
    assert close(pt(s, "1.S"), (10, 0))


# ---- power trim ----------------------------------------------------------------------------

def test_strim_with_several_pieces_follows_curves_cut_in_two(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 40,0\nSLINE, 0,10, 40,10\nSLINE, 10,-5, 10,15\nSLINE, 30,-5, 30,15")
    ok(p, "STRIM, 3, 10, -3, 3, 10, 13, 1, 20, 0, 1, 35, 0")
    s = sk(p)
    assert close(pt(s, "3.S"), (10, 0)) and close(pt(s, "3.E"), (10, 10))
    # line 1 was cut in the middle (1 and 5); the last pick was on the new piece 5, which
    # nothing else crosses, so it went
    assert sorted(s.geos) == [1, 2, 3, 4]
    assert close(pt(s, "1.E"), (10, 0))
    assert "3, u, v" in err(p, "STRIM, 1, 2")


def test_power_trim_by_mouse_drag(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 40,0\nSLINE, 10,-5, 10,15\nSLINE, 30,-5, 30,15")
    c = st.SketchController(p)
    c.set_tool("TRIM")
    c.press(5, -3, 1.0)
    for u in range(6, 36):
        c.move(u, -3 + (u - 5) * 0.2, 1.0)
    lines = c.release(35, 3, 1.0)
    assert len(lines) == 1 and lines[0].startswith("STRIM, ")
    ok(p, lines[0])
    assert len(sk(p).geos) >= 3


# ---- STRANSFORM -----------------------------------------------------------------------------

def test_transform_copy_keeps_the_constraints_among_the_copies(p):
    ok(p, RECT + "STRANSFORM, MOVE, 50, 0, 1, 2, 3, 4, COPY")
    s = sk(p)
    assert close(pt(s, "5.S"), (50, 0)) and close(pt(s, "6.E"), (90, 20))
    kinds = sorted(c.kind for c in s.cons.values() if any(r.split(".")[0] in ("5", "6", "7", "8") for r in c.refs))
    assert kinds.count("COINCIDENT") == 4 and kinds.count("LENGTH") == 2 and "HORIZONTAL" in kinds
    assert s.dof == 2  # the copy can still slide: its tie to the origin was not copied


def test_transform_rotate_swaps_level_and_upright_and_scale_scales_sizes(p):
    ok(p, RECT + "STRANSFORM, ROTATE, 90, O, 1, 2, 3, 4")
    s = sk(p)
    assert close(pt(s, "1.E"), (0, 40)) and close(pt(s, "2.E"), (-20, 40))
    assert [c.kind for c in s.cons.values() if c.refs == ("1",)][0] in ("VERTICAL", "LENGTH")
    assert any(c.kind == "VERTICAL" and c.refs == ("1",) for c in s.cons.values())
    ok(p, "STRANSFORM, SCALE, 0.5, O, 1, 2, 3, 4")
    s = sk(p)
    assert sorted(c.value for c in s.cons.values() if c.kind == "LENGTH") == [10, 20]
    assert close(pt(s, "2.E"), (-10, 20))


def test_transform_in_place_lets_go_of_ties_to_the_rest(p):
    ok(p, RECT + "SCIRCLE, 20, 10, 3\nSCON, COINCIDENT, 5.C, ORIGIN")
    r = ok(p, "STRANSFORM, MOVE, 5, 5, 5")
    assert "dropped C" in r.message
    assert close(pt(sk(p), "5.C"), (5, 5))
    assert "MOVE, ROTATE or SCALE" in err(p, "STRANSFORM, SPIN, 5, 1")


# ---- drawing --------------------------------------------------------------------------------

def test_tangent_arc_from_a_line_end(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 20,0\nSARCT, 1.E, 30, 10\nSARCT, 2.E, 20, 20")
    s = sk(p)
    assert close(pt(s, "2.C"), (20, 10)) and abs(s.radius(s.geos[2]) - 10) < 1e-9
    assert sum(c.kind == "TANGENT" for c in s.cons.values()) == 2
    assert "straight on" in err(p, "SARCT, 1.S, -10, 0")


def test_circle_through_three_points_and_centre_rectangle(p):
    ok(p, "SKETCH, s, XY\nSCIRCLE3, 0,0, 10,10, 20,0\nSRECTC, 50,0, 60,5")
    s = sk(p)
    assert close(pt(s, "1.C"), (10, 0)) and abs(s.radius(s.geos[1]) - 10) < 1e-9
    ok(p, "SDIM, LENGTH, 2, 30")
    s = sk(p)
    assert close(pt(s, "7"), (50, 0), 1e-6)  # the centre stays put as the rectangle grows
    assert close(pt(s, "2.S"), (35, -5))


def test_rectangle_at_an_angle(p):
    ok(p, "SKETCH, s, XY\nSRECT3, 0,0, 30,40, -10, 20\nENDSKETCH\nEXTRUDE, s, 1")
    w = abs((-10) * -0.8 + 20 * 0.6)  # distance of the third point from the first side
    assert vol(p) == pytest.approx(50 * w)


def test_regular_polygons_inside_and_outside(p):
    ok(p, "SKETCH, s, XY\nSNGON, 0, 0, 6, 10\nENDSKETCH\nEXTRUDE, s, 1")
    assert vol(p) == pytest.approx(1.5 * math.sqrt(3) * 100)
    p2 = Processor()
    ok(p2, "SKETCH, s, XY\nSNGON, 0, 0, 6, 10, 0, OUT\nSDIM, RADIUS, 1, 5\nENDSKETCH\nEXTRUDE, s, 1")
    assert vol(p2) == pytest.approx(2 * math.sqrt(3) * 25)  # still regular after the size changed
    p3 = Processor()
    ok(p3, "SKETCH, s, XY")
    assert "3 sides" in err(p3, "SNGON, 0, 0, 2, 5")


def test_arc_slot(p):
    ok(p, "SKETCH, s, XY\nSSLOTARC, 0, 0, 20, 0, 90, 4\nENDSKETCH\nEXTRUDE, s, 1")
    s = p.model.sketches["S"]
    assert s.dof == 6 and not s.redundant
    assert vol(p) == pytest.approx(math.pi / 4 * (24 ** 2 - 16 ** 2) + math.pi * 16)


def test_example_cover_plate():
    p = Processor()
    import pathlib

    text = (pathlib.Path(__file__).parent.parent / "scripts" / "cover_plate.cmd").read_text(encoding="utf-8")
    ok(p, text)
    assert vol(p) == pytest.approx(23951.88, rel=1e-5)


# ---- the mouse tools -------------------------------------------------------------------------

def _tool(p, name):
    c = st.SketchController(p)
    c.set_tool(name)
    return c


def test_mouse_tools_send_the_new_commands(p):
    ok(p, RECT)
    c = _tool(p, "CHAMFER")
    assert c.click(40, 0, 1.0)[0].startswith("SCHAMFER, 1.E, ")
    c = _tool(p, "SPLIT")
    assert c.click(12, 0.4, 1.0) == ["SSPLIT, 1, 12, 0"]
    c = _tool(p, "CORNER")
    assert c.click(5, 0, 1.0) == []
    assert c.click(40, 15, 1.0) == ["SCORNER, 1, 2, 5, 0, 40, 15"]
    c = _tool(p, "CENTRELINE")
    c.click(-10, -10, 0.5)
    assert c.click(-10, 30, 0.5) == ["SLINE, -10, -10, -10, 30, CONSTR, V"]
    c = _tool(p, "CRECT")
    c.click(100, 0, 0.5)
    assert c.click(110, 5, 0.5) == ["SRECTC, 100, 0, 110, 5"]
    c = _tool(p, "POLYGON")
    c.polygon_sides = 5
    c.click(100, 50, 0.5)
    assert c.click(110, 50, 0.5) == ["SNGON, 100, 50, 5, 10, 0"]
    c = _tool(p, "CIRCLE3")
    for q in ((200, 0), (210, 10)):
        assert c.click(*q, 0.5) == []
    assert c.click(220, 0, 0.5) == ["SCIRCLE3, 200, 0, 210, 10, 220, 0"]
    c = _tool(p, "TARC")
    assert c.click(150, 150, 0.5) == []  # not on the end of a line or arc: nothing starts
    assert c.click(40, 20, 0.5) == []
    assert c.click(50, 30, 0.5) == ["SARCT, 2.E, 50, 30"]
    c = _tool(p, "ARCSLOT")
    for q in ((0, 100), (20, 100), (-20, 100.1)):
        assert c.click(*q, 0.5) == []
    out = c.click(0, 123, 0.5)
    assert out and out[0].startswith("SSLOTARC, 0, 100, 20, 0, ")
    for line in out:
        ok(p, line)


def test_split_tool_on_a_circle_needs_two_clicks(p):
    ok(p, "SKETCH, s, XY\nSCIRCLE, 0, 0, 10")
    c = _tool(p, "SPLIT")
    assert c.click(10, 0.2, 1.0) == []
    (line,) = c.click(-10, 0.2, 1.0)
    assert line.startswith("SSPLIT, 1, 9.99")
    ok(p, line)
    assert [g.kind for g in sk(p).geos.values()] == ["ARC", "ARC"]


def test_transform_command_from_the_selection(p):
    ok(p, RECT + "SSEL, 1, 2")
    assert st.transform_command(p, "ROTATE", "90, O", True) == ["STRANSFORM, ROTATE, 90, O, 1, 2, COPY"]
    p.model.sketch_selection = []
    with pytest.raises(st.NeedSelection):
        st.transform_command(p, "MOVE", "1, 0")
