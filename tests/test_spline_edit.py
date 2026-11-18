"""Splines in the sketch editing tools: trim, extend, split, fillet with a
line or arc, ON and TANGENT constraints with a spline, and SJOIN (join
curves into one spline, or turn one curve into a spline)."""

import math

import pytest

from modeler.commands import Processor
from modeler.gui import sketch_tools as st
from modeler.sketch import spline as sp

WAVE = "SSPLINE, 0,0, 10,8, 20,0, 30,-8, 40,0"


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


def ends(s, n):
    g = s.geos[n]
    return s.pt(g.pts["S"]), s.pt(g.pts["E"])


def on_spline(s, n, q, tol=1e-6):
    return sp.distance(s, s.geos[n], q) < tol


def area(p, bid=1):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    g = GProp_GProps()
    try:
        BRepGProp.VolumeProperties_s(p.model.bodies[bid].shape, g)
    except AttributeError:
        BRepGProp.VolumeProperties(p.model.bodies[bid].shape, g)
    return g.Mass()


# ---- trim ---------------------------------------------------------------------------------

def test_trim_a_spline_end_back_to_a_line(p):
    ok(p, f"SKETCH, s, XY\n{WAVE}\nSLINE, 20,-20, 20,20")
    r = ok(p, "STRIM, 1, 35,-5")
    assert "trimmed spline 1 back to 2" in r.message
    s = sk(p)
    a, b = ends(s, 1)
    assert a == pytest.approx((0, 0)) and b == pytest.approx((20, 0), abs=1e-6)
    assert [c.kind for c in s.cons.values()] == ["ON"]
    # the kept part still runs through (10, 8), the point it ran through before
    assert any(math.dist(q, (10, 8)) < 1e-9 for q in s.spline_points(s.geos[1]))
    ok(p, "SMOVE, 2.S, 25,-20")  # the line tilts: the trimmed end stays on it
    s = sk(p)
    a2, b2 = ends(s, 2)
    e = ends(s, 1)[1]
    assert abs((b2[0] - a2[0]) * (e[1] - a2[1]) - (b2[1] - a2[1]) * (e[0] - a2[0])) < 1e-6


def test_trim_the_middle_of_a_spline_leaves_two(p):
    ok(p, f"SKETCH, s, XY\n{WAVE}\nSLINE, 8,-20, 8,20\nSLINE, 32,-20, 32,20")
    r = ok(p, "STRIM, 1, 20,0")
    assert "cut spline 1 between 2 and 3: 1 and 4 are left" in r.message
    s = sk(p)
    assert ends(s, 1)[1][0] == pytest.approx(8, abs=1e-6)
    assert ends(s, 4)[0][0] == pytest.approx(32, abs=1e-6)
    assert ends(s, 4)[1] == pytest.approx((40, 0))


def test_trim_a_closed_spline_opens_it(p):
    ok(p, "SKETCH, s, XY\nSSPLINE, 0,0, 10,10, 20,0, 10,-10, CLOSE\nSLINE, 5,-20, 5,20")
    ok(p, "STRIM, 1, 0,0")
    s = sk(p)
    g = s.geos[1]
    assert not g.closed and "E" in g.pts
    a, b = ends(s, 1)
    assert a[0] == pytest.approx(5, abs=1e-6) and b[0] == pytest.approx(5, abs=1e-6)
    assert a[1] * b[1] < 0  # one end above, one below


def test_a_line_trimmed_by_a_spline_stays_on_it(p):
    ok(p, f"SKETCH, s, XY\n{WAVE}\nSLINE, 5,-20, 5,20")
    ok(p, "STRIM, 2, 5,15")
    s = sk(p)
    e = ends(s, 2)[1]
    assert on_spline(s, 1, e)
    ok(p, "SMOVE, 1.K1, 10,12")  # the spline bulges higher: the line end follows
    s = sk(p)
    e2 = ends(s, 2)[1]
    assert e2[1] > e[1] + 0.5
    assert on_spline(s, 1, e2)


# ---- split --------------------------------------------------------------------------------

def test_split_a_spline_keeps_its_points_and_their_constraints(p):
    ok(p, f"SKETCH, s, XY\n{WAVE}\nSPOINT, 30,-8\nSCON, COINCIDENT, 1.K3, 2")
    r = ok(p, "SSPLIT, 1, 20,0")  # right at a point it runs through
    assert "split spline 1 into 2: 1, 3" in r.message
    s = sk(p)
    assert ends(s, 1)[1] == pytest.approx((20, 0)) and ends(s, 3)[0] == pytest.approx((20, 0))
    refs = [c.refs for c in s.cons.values()]
    assert ("1.E", "3.S") in refs
    # the point (30, -8) went to the second piece, and its constraint with it
    assert any(r[1] == "2" and r[0].startswith("3.K") for r in refs)
    ok(p, "SMOVE, 2, 30,-12")
    s = sk(p)
    assert any(math.dist(q, (30, -12)) < 1e-6 for q in s.spline_points(s.geos[3]))


def test_split_a_spline_by_a_curve_and_a_closed_one_at_one_point(p):
    ok(p, f"SKETCH, s, XY\n{WAVE}\nSCIRCLE, 20,0, 12")
    r = ok(p, "SSPLIT, 1, 2")
    assert "into 3" in r.message
    s = sk(p)
    c = s.pt(s.geos[2].pts["C"])
    for n in (3, 4):
        assert math.dist(ends(s, n)[0], c) == pytest.approx(12, abs=1e-6)
    ok(p, "SSPLINE, 0,30, 10,40, 20,30, CLOSE")
    r = ok(p, "SSPLIT, 5, 10,40")
    assert "opened closed spline 5" in r.message
    g = sk(p).geos[5]
    assert not g.closed
    a, b = ends(sk(p), 5)
    assert a == pytest.approx(b, abs=1e-9)


# ---- extend -------------------------------------------------------------------------------

def test_extend_a_spline_to_a_line(p):
    ok(p, f"SKETCH, s, XY\n{WAVE}\nSLINE, 50,-40, 50,40")
    r = ok(p, "SEXTEND, 1.E")
    assert "extended spline 1 at E to 2" in r.message
    s = sk(p)
    e = ends(s, 1)[1]
    assert e[0] == pytest.approx(50, abs=1e-6)
    pts = s.spline_points(s.geos[1])
    assert len(pts) == 6 and pts[4] == pytest.approx((40, 0))  # the old end is a point it runs through
    assert "never meets" in err(p, "SEXTEND, 1.S, 2")


# ---- constraints with a spline ---------------------------------------------------------------

def test_tangent_line_and_spline_at_its_end(p):
    ok(p, f"SKETCH, s, XY\n{WAVE}\nSLINE, -20,-5, 0,0\nSCON, COINCIDENT, 2.E, 1.S\nSCON, TANGENT, 1, 2")
    s = sk(p)
    a, b = ends(s, 2)
    d = sp.tangent(s, s.geos[1], 0.0)
    ln = ((b[0] - a[0]) / math.dist(a, b), (b[1] - a[1]) / math.dist(a, b))
    assert abs(d[0] * ln[1] - d[1] * ln[0]) < 1e-6
    ok(p, "SSPLINE, 0,30, 10,40, 20,30, CLOSE")
    assert "closed" in err(p, "SCON, TANGENT, 3, 2")


def test_tangent_arc_and_spline(p):
    ok(p, f"SKETCH, s, XY\n{WAVE}\nSARC, 40,10, 10, 200, 300\nSCON, COINCIDENT, 1.E, 2.S\nSCON, TANGENT, 1, 2")
    s = sk(p)
    e = ends(s, 1)[1]
    c = s.pt(s.geos[2].pts["C"])
    d = sp.tangent(s, s.geos[1], 1.0)
    rr = ((e[0] - c[0]) / math.dist(e, c), (e[1] - c[1]) / math.dist(e, c))
    assert abs(d[0] * rr[0] + d[1] * rr[1]) < 1e-6


# ---- fillet -------------------------------------------------------------------------------

def test_fillet_a_line_and_a_spline_and_extrude(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,-20, 0,0\nSSPLINE, 0,0, 15,10, 30,5, 40,-20\nSLINE, 40,-20, 0,-20\n"
          "SCON, COINCIDENT, 1.E, 2.S\nSCON, COINCIDENT, 2.E, 3.S\nSCON, COINCIDENT, 3.E, 1.S")
    r = ok(p, "SFILLET, 1.E, 4")
    assert "rounded the corner of line 1 and spline 2 with arc" in r.message
    s = sk(p)
    arc = next(g for g in s.geos.values() if g.kind == "ARC")
    assert s.radius(arc) == pytest.approx(4)
    c = s.pt(arc.pts["C"])
    a1, b1 = ends(s, 1)
    gap = abs((b1[0] - a1[0]) * (c[1] - a1[1]) - (b1[1] - a1[1]) * (c[0] - a1[0])) / math.dist(a1, b1)
    assert gap == pytest.approx(4, abs=1e-6)  # tangent to the line
    q = ends(s, 2)[0]
    assert math.dist(q, c) == pytest.approx(4, abs=1e-6)  # the spline starts on the arc ...
    d = sp.tangent(s, s.geos[2], 0.0)
    assert abs(d[0] * (q[0] - c[0]) + d[1] * (q[1] - c[1])) < 1e-5  # ... and leaves it smoothly
    ok(p, "ENDSKETCH\nEXTRUDE, S, 5")
    assert area(p) > 0


def test_fillet_errors(p):
    ok(p, "SKETCH, s, XY\nSSPLINE, 0,0, 10,10, 20,0\nSSPLINE, 20,0, 30,10, 40,0")
    assert "two splines meet" in err(p, "SFILLET, 1.E, 2")


# ---- join -----------------------------------------------------------------------------------

def test_join_a_chain_into_one_spline(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 20,0\nSARC, 20,10, 10, 270, 360\nSLINE, 30,10, 30,30\n"
          "SCON, COINCIDENT, 1.E, 2.S\nSCON, COINCIDENT, 2.E, 3.S\nSCON, FIX, 1.S\nSDIM, LENGTH, 3, 20")
    r = ok(p, "SJOIN, 3, 1, 2")
    assert "joined line 3, line 1, arc 2 into spline 4" in r.message
    assert "dropped C4 (length)" in r.message
    s = sk(p)
    assert list(s.geos) == [4]
    a, b = ends(s, 4)
    assert a == pytest.approx((0, 0)) and b == pytest.approx((30, 30))
    assert [c.refs for c in s.cons.values()] == [("4.S",)]  # the FIX moved to the spline's start
    # it follows the old curves closely: the middle of the arc is on it
    m = (20 + 10 * math.cos(math.radians(315)), 10 + 10 * math.sin(math.radians(315)))
    assert sp.distance(s, s.geos[4], m) < 0.05


def test_join_a_closed_chain_and_convert_one_curve(p):
    ok(p, "SKETCH, s, XY\nSRECT, 0,0, 20,10")
    r = ok(p, "SJOIN, 1, 2, 3, 4")
    assert "closed" in r.message
    g = sk(p).geos[5]
    assert g.closed and g.kind == "SPLINE"
    ok(p, "SCIRCLE, 50,0, 10\nSJOIN, 6")
    g = sk(p).geos[7]
    assert g.closed and len(g.pts) == 12
    assert sp.distance(sk(p), g, (60, 0)) < 1e-9
    ok(p, "SLINE, 0,40, 10,40\nSJOIN, 8")
    assert len(sk(p).geos[9].pts) == 2
    assert "a spline already" in err(p, "SJOIN, 9")
    ok(p, "SLINE, 0,50, 10,50\nSLINE, 30,50, 40,50")
    assert "do not join end to end" in err(p, "SJOIN, 10, 11")


# ---- the mouse tools ------------------------------------------------------------------------

def test_tools_work_on_splines(p):
    ok(p, f"SKETCH, s, XY\n{WAVE}\nSLINE, 20,-20, 20,20")
    c = st.SketchController(p)
    c.set_tool("SPLIT")
    q = sp.foot(sk(p), sk(p).geos[1], (10, 8.3))
    out = c.click(*q, 0.5)
    assert out and out[0].startswith("SSPLIT, 1, ")
    c.set_tool("TRIM")
    q = sp.foot(sk(p), sk(p).geos[1], (35, -7))
    assert c.trim_preview(*q, 0.5)
    out = c.click(*q, 0.5)
    assert out and out[0].startswith("STRIM, 1, ")
    c.set_tool("EXTEND")
    assert c.click(39.5, -0.3, 0.5) == ["SEXTEND, 1.E"]
    p.model.sketch_selection = ["1", "2"]
    assert st.join_command(p) == ["SJOIN, 1, 2"]
