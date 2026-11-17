"""The last sketch tools of PLAN.md item 7: ellipses and elliptical arcs
(SELLIPSE, SEARC, MAJOR / MINOR / ARCLEN sizes, trim, split, mirror),
SCIRCLET, SOFFSET2, SINTERSECT, constraints made while drawing, and the
mouse tools that send them."""

import math

import pytest

from modeler.commands import Processor
from modeler.gui import sketch_tools as st
from modeler.sketch import ellipse as el


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


class Live:
    """The current sketch (each step stores a new copy)."""

    def __init__(self, p, name="S"):
        self.p, self.name = p, name

    def __getattr__(self, k):
        return getattr(self.p.model.sketches[self.name], k)


def volume(p, bid=1):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    g = GProp_GProps()
    try:
        BRepGProp.VolumeProperties_s(p.model.bodies[bid].shape, g)
    except AttributeError:
        BRepGProp.VolumeProperties(p.model.bodies[bid].shape, g)
    return g.Mass()


# ---- ellipses ---------------------------------------------------------------------------

def test_ellipse_extrudes_to_the_right_volume_and_has_five_freedoms(p):
    ok(p, "SKETCH, s, XY\nSELLIPSE, 0,0, 20, 10, 30")
    s = Live(p)
    assert s.dof == 5
    g = s.geos[1]
    c, ax, a, b = el.frame(s, g)
    assert (a, b) == pytest.approx((20, 10))
    assert math.degrees(math.atan2(ax[1], ax[0])) == pytest.approx(30)
    ok(p, "SDIM, MAJOR, 1, 25\nSDIM, MINOR, 1, 8\nSCON, COINCIDENT, 1.C, ORIGIN\nSCON, HORIZONTAL, 1.C, 1.A")
    assert s.dof == 0
    assert el.frame(s, g)[2:] == pytest.approx((25, 8))
    ok(p, "ENDSKETCH\nEXTRUDE, s, 4")
    assert volume(p) == pytest.approx(math.pi * 25 * 8 * 4, rel=1e-6)


def test_second_radius_bigger_than_the_first_still_builds(p):
    ok(p, "SKETCH, s, XY\nSELLIPSE, 0,0, 5, 12\nENDSKETCH\nEXTRUDE, s, 1")
    assert volume(p) == pytest.approx(math.pi * 5 * 12, rel=1e-6)


def test_half_ellipse_closed_by_its_axis(p):
    ok(p, "SKETCH, s, XY\nSEARC, 0,0, 20, 10, 0, 0, 180\nSLINE, 1.E, 1.S\nENDSKETCH\nEXTRUDE, s, 2")
    assert volume(p) == pytest.approx(math.pi * 20 * 10 / 2 * 2, rel=1e-6)
    s = Live(p)
    assert s.dof == 7  # centre 2, axis point 2, second radius 1, two ends round it


def test_arc_length_size_holds(p):
    ok(p, "SKETCH, s, XY\nSARC, 0,0, 10, 0, 90\nSDIM, ARCLEN, 1, 20")
    s = Live(p)
    g = s.geos[1]
    a1, a2 = s.arc_angles(g)
    assert s.radius(g) * math.radians(a2 - a1) == pytest.approx(20, rel=1e-7)
    ok(p, "SEARC, 50,0, 20, 10, 0, 0, 180\nSDIM, ARCLEN, 2, 40")
    from modeler.sketch.sketch import arc_length

    assert arc_length(s, s.geos[2]) == pytest.approx(40, rel=1e-6)
    assert "give an arc or elliptical arc" in err(p, "SDIM, ARCLEN, 2.C, 5")


def test_point_on_ellipse_and_line_tangent_to_it(p):
    ok(p, "SKETCH, s, XY\nSELLIPSE, 0,0, 20, 10, 30\nSPOINT, 30, 30\nSCON, ON, 2, 1")
    s = Live(p)
    q = s.pt(s.geos[2].pts["P"])
    assert abs(el.side(s, s.geos[1], q)) < 1e-7
    ok(p, "SLINE, -40,25, 40,25\nSCON, TANGENT, 3, 1")
    # the line touches: the ellipse's highest point is on it
    top = max(el.polyline(s, s.geos[1], 2000), key=lambda q: q[1] - (q[0] * 0))
    a, b = s.pt(s.geos[3].pts["S"]), s.pt(s.geos[3].pts["E"])
    dist = abs((b[0] - a[0]) * (top[1] - a[1]) - (b[1] - a[1]) * (top[0] - a[0])) / math.dist(a, b)
    assert dist < 1e-3


def test_trim_and_split_ellipses(p):
    ok(p, "SKETCH, s, XY\nSELLIPSE, 0,0, 20, 10\nSLINE, -30,0, 30,0\nSTRIM, 1, 0, -10")
    s = Live(p)
    g = s.geos[1]
    assert g.kind == "EARC"
    t1, t2 = el.arc_params(s, g)
    assert (t1 % 360, t2 - t1) == pytest.approx((0, 180), abs=1e-6)  # the top half is left
    ok(p, "SSPLIT, 1, 0, 12")
    assert len([x for x in s.geos.values() if x.kind == "EARC"]) == 2
    ok(p, "STRIM, 2, -25, 0\nSTRIM, 2, 25, 0")
    ok(p, "ENDSKETCH\nEXTRUDE, s, 1")
    assert volume(p) == pytest.approx(math.pi * 20 * 10 / 2, rel=1e-6)


def test_split_a_whole_ellipse_in_two_places(p):
    ok(p, "SKETCH, s, XY\nSELLIPSE, 0,0, 20, 10\nSSPLIT, 1, 20,0, -20,0")
    s = Live(p)
    assert sorted(g.kind for g in s.geos.values()) == ["EARC", "EARC"]
    ok(p, "SDIM, MINOR, 1, 6")  # the pieces stay one ellipse
    assert el.frame(s, s.geos[2])[3] == pytest.approx(6)
    ok(p, "ENDSKETCH\nEXTRUDE, s, 1")
    assert volume(p) == pytest.approx(math.pi * 20 * 6, rel=1e-6)


def test_mirror_pattern_and_scale_an_ellipse(p):
    ok(p, "SKETCH, s, XY\nSEARC, 10,10, 8, 4, 20, 0, 120\nSMIRROR, V, 1\nSPATTERN, LINEAR, 2, 0, 30, 1")
    s = Live(p)
    assert [g.kind for g in s.geos.values()] == ["EARC"] * 3
    m = s.geos[2]
    assert el.frame(s, m)[0] == pytest.approx((-10, 10))
    ok(p, "SDIM, MINOR, 1, 3")  # copies follow
    assert el.frame(s, m)[3] == pytest.approx(3)
    assert el.frame(s, s.geos[3])[3] == pytest.approx(3)
    before = el.frame(s, s.geos[1])[2]  # the second radius changed, so the arc settled anew
    ok(p, "STRANSFORM, SCALE, 2, 0, 0, 1")
    assert el.frame(s, s.geos[1])[2:] == pytest.approx((2 * before, 6))


def test_ellipse_errors_are_clear(p):
    ok(p, "SKETCH, s, XY\nSELLIPSE, 0,0, 20, 10")
    assert "MAJOR" in err(p, "SDIM, RADIUS, 1, 5")
    assert "1 is an ellipse, which SOFFSET does not work on" in err(p, "SOFFSET, 2, 1")
    assert "positive" in err(p, "SELLIPSE, 0,0, 0, 10")
    assert "two different angles" in err(p, "SEARC, 0,0, 5, 3, 0, 10, 10")


def test_ellipse_tool_clicks_and_size_button(p):
    ok(p, "SKETCH, s, XY")
    c = st.SketchController(p)
    c.set_tool("ELLIPSE")
    assert c.click(0, 0, 0.5) == []
    assert c.click(20, 0.2, 0.5) == []
    pv = c.move(5, 9, 0.5)
    assert pv.arcs  # the ellipse follows the mouse
    out = c.click(5, 9, 0.5)
    assert out and out[0].startswith("SELLIPSE, ORIGIN, 20, 9")
    assert out[0].endswith(", H")
    ok(p, out[0])
    c.set_tool("EARC")
    for q in ((40, 30), (50, 30), (40, 35), (50, 30.5)):
        assert c.click(*q, 0.5) == []
    out = c.click(30, 30.5, 0.5)
    assert out == ["SEARC, 40, 30, 10, 5, 0, 4.57, 175.43, H"]
    ok(p, out[0])
    assert p.model.sketches["S"].geos[2].kind == "EARC"


def test_ellipse_dimension_rows_and_labels(p):
    ok(p, "SKETCH, s, XY\nSELLIPSE, 0,0, 20, 10\nSDIM, MAJOR, 1, 20\nSDIM, MINOR, 1, 10\n"
          "SEARC, 50,0, 10, 5, 0, 0, 90\nSDIM, ARCLEN, 2, 12")
    s = Live(p)
    for c in s.cons.values():
        segs, at = st.dimension_geometry(s, c)
        assert len(at) == 2
    rows = st.sketch_dimensions(p, "S")
    assert len(rows) == 3


# ---- constraints made while drawing ------------------------------------------------------------

def _run_all(p, cmds):
    for line in cmds:
        r = p.run(line)
        assert r.ok, r.message


def test_a_click_on_a_curve_puts_the_point_on_it(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 40,0\nSCIRCLE, 60,0, 10")
    c = st.SketchController(p)
    c.set_tool("LINE")
    assert c.click(10, 0.1, 0.5) == []
    pv = c.move(52, 6.1, 0.5)
    assert [t for _, t in pv.marks] == ["On 2"]
    out = c.click(52, 6.1, 0.5)
    assert out[1:] == ["SCON, ON, 3.S, 1", "SCON, ON, 3.E, 2"]
    _run_all(p, out)
    s = sk(p)
    e = s.pt(s.geos[3].pts["E"])
    assert math.dist(e, s.pt(s.geos[2].pts["C"])) == pytest.approx(s.radius(s.geos[2]))
    ok(p, "SMOVE, 1.E, 40, 5")  # the line's start stays on line 1 as it tilts
    s = sk(p)
    a, b = s.pt(s.geos[1].pts["S"]), s.pt(s.geos[1].pts["E"])
    q = s.pt(s.geos[3].pts["S"])
    assert abs((b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])) < 1e-6


def test_shift_draws_without_them_and_the_switch_turns_them_off(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 40,0")
    c = st.SketchController(p)
    c.set_tool("POINT")
    assert c.click(10, 0.1, 0.5) == ["SPOINT, 10, 0", "SCON, ON, 2, 1"]
    c.no_auto = True
    assert c.click(10, 0.1, 0.5) == ["SPOINT, 10, 0"]
    c.no_auto, c.auto = False, False
    assert c.click(10, 0.1, 0.5) == ["SPOINT, 10, 0"]


def test_lines_on_from_an_arc_are_tangent_and_turns_are_square(p):
    ok(p, "SKETCH, s, XY\nSARC, 0,0, 10, 0, 45")
    c = st.SketchController(p)
    c.set_tool("LINE")
    e = (10 * math.cos(math.pi / 4), 10 * math.sin(math.pi / 4))
    assert c.click(*e, 0.5) == []
    q = (e[0] - 10, e[1] + 10.3)
    assert [t for _, t in c.move(*q, 0.5).marks] == ["Tangent"]
    out = c.click(*q, 0.5)
    assert out == ["SLINE, 1.E, -3, 17.4", "SCON, TANGENT, 2, 1"]
    _run_all(p, out)
    q2 = (q[0] - 10.2, q[1] - 10)
    assert "Perpendicular" in [t for _, t in c.move(*q2, 0.5).marks]
    out = c.click(*q2, 0.5)
    assert out[-1] == "SCON, PERPENDICULAR, 3, 2"
    _run_all(p, out)
    s = sk(p)
    d2 = (s.x[s.geos[2].pts["E"]] - s.x[s.geos[2].pts["S"]], s.x[s.geos[2].pts["E"] + 1] - s.x[s.geos[2].pts["S"] + 1])
    d3 = (s.x[s.geos[3].pts["E"]] - s.x[s.geos[3].pts["S"]], s.x[s.geos[3].pts["E"] + 1] - s.x[s.geos[3].pts["S"] + 1])
    assert abs(d2[0] * d3[0] + d2[1] * d3[1]) < 1e-6


def test_circle_centre_and_rect_corner_go_on_curves(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 40,-40")
    c = st.SketchController(p)
    c.set_tool("CIRCLE")
    c.click(10, -10.1, 0.5)
    assert c.click(15, -10, 0.5) == ["SCIRCLE, 10.05, -10.05, 5", "SCON, ON, 2.C, 1"]
    c.set_tool("RECT")
    c.click(20, -20.1, 0.5)
    out = c.click(30, -10, 0.5)
    assert out[1:] == ["SCON, ON, 2.S, 1"]


# ---- tangent circle, point-to-circle size, offset both sides, cut by the plane ------------------

def test_tangent_circle_to_two_lines_and_three_curves(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 30,0\nSLINE, 0,0, 0,30\nSCIRCLE, 40,40, 10\n"
          "SCIRCLET, 1, 2, R, 4, AT, 5, 6")
    s = sk(p)
    assert s.pt(s.geos[4].pts["C"]) == pytest.approx((4, 4))
    assert s.pt(s.geos[1].pts["E"]) == pytest.approx((30, 0))  # the lines did not move
    ok(p, "SCIRCLET, 1, 2, 3, AT, 15, 15")
    s = sk(p)
    g = s.geos[5]
    cc, r = s.pt(g.pts["C"]), s.radius(g)
    assert cc[0] == pytest.approx(r) and cc[1] == pytest.approx(r)
    assert math.dist(cc, (40, 40)) == pytest.approx(r + 10)
    assert "AT" in err(p, "SCIRCLET, 1, 2, R, 3")
    assert "radius" in err(p, "SCIRCLET, 1, 2, AT, 5, 5")


def test_tangent_circle_tool(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 30,0\nSLINE, 0,0, 0,30")
    c = st.SketchController(p)
    c.set_tool("CIRCLET")
    assert c.click(10, 0.1, 0.5) == []
    assert c.click(0.1, 10, 0.5) == []
    pv = c.move(5, 6, 0.5)
    assert pv.circles
    out = c.click(5, 6, 0.5)
    assert out == ["SCIRCLET, 1, 2, R, 5, AT, 5, 6"]
    ok(p, out[0])


def test_size_from_a_point_to_a_circle(p):
    ok(p, "SKETCH, s, XY\nSCIRCLE, 0,0, 10\nSCON, FIX, 1\nSPOINT, 20, 5\nSDIM, DIST, 2, 1, 3")
    s = sk(p)
    assert math.dist(s.pt(s.geos[2].pts["P"]), (0, 0)) == pytest.approx(13)
    ok(p, "SPOINT, 2, 1\nSDIM, DIST, 3, 1, 4")  # inside: 4 in from the rim
    s = sk(p)
    assert math.dist(s.pt(s.geos[3].pts["P"]), (0, 0)) == pytest.approx(6)
    rows = st.dimension_geometry(s, s.cons[max(s.cons)])
    assert rows[0]


def test_offset_both_sides_makes_a_slot_along_a_path(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 30,0\nSARC, 30,10, 10, -90, 0\nSCON, COINCIDENT, 1.E, 2.S\n"
          "SOFFSET2, 3, 1, 2\nENDSKETCH\nEXTRUDE, s, 1")
    s = sk(p)
    assert s.geos[1].construction and s.geos[2].construction
    want = 30 * 6 + math.pi * (13 ** 2 - 7 ** 2) / 4 + math.pi * 9
    assert volume(p) == pytest.approx(want, rel=1e-6)


def test_offset_both_sides_flat_and_closed(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 30,0\nSOFFSET2, 2, 1, FLAT\nENDSKETCH\nEXTRUDE, s, 1")
    assert volume(p) == pytest.approx(30 * 4)
    q = Processor()
    ok(q, "SKETCH, s, XY\nSRECT, 0,0, 20,10\nSOFFSET2, 1, 1, 2, 3, 4\nENDSKETCH\nEXTRUDE, s, 1")
    assert volume(q) == pytest.approx(22 * 12 - 18 * 8)


def test_cut_bodies_with_the_sketch_plane(p):
    ok(p, "CYL, 0,0,-10, 10, 40\nPLANE, P1, PN, 0,0,5, 0,1,1\nSKETCH, s, P1\nSINTERSECT, 1")
    s = sk(p)
    assert [g.kind for g in s.geos.values()] == ["ELLIPSE"]
    assert s.dof == 0
    assert sorted(el.frame(s, s.geos[1])[2:]) == pytest.approx([10, 10 * math.sqrt(2)])
    ok(p, "ENDSKETCH\nEXTRUDE, s, 1")
    assert volume(p, 2) == pytest.approx(math.pi * 100 * math.sqrt(2), rel=1e-6)
    q = Processor()
    ok(q, "BLOCK, 0,0,0, 20,10,10\nSKETCH, t, XY\nSINTERSECT, 1")
    s = q.model.sketches["T"]
    assert len(s.geos) == 4 and s.dof == 0
    ok(q, "ENDSKETCH\nCYL, 50,0,10, 5, 10\nSKETCH, u, XY")
    assert "does not reach the sketch plane" in err(q, "SINTERSECT, 2")
