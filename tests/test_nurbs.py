"""M5 part 1: NURBS curves and surfaces, editing control points, NETWORK, FILL, SEW."""

import math

import pytest

from modeler.commands import Processor
from modeler.geometry import nurbs as nb
from modeler.gui import forms as F
from modeler.gui.point_edit import PointEditor


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def err(p, text):
    rs = p.run_script(text)
    assert not rs[-1].ok, rs[-1].message
    return rs[-1].message


WAVE = "NURBS, 3, (0,0,0), (10,8,0), (20,-8,0), (30,0,0)\nNAME, LAST, c"


# ---- curves ---------------------------------------------------------------------

def test_nurbs_curve_starts_and_ends_on_its_end_points(p):
    ok(p, WAVE)
    assert p.evaluate("NPOLES(c)") == 4
    assert p.evaluate("POLE(c, 2)") == (10, 8, 0)
    g = nb.curve_of(p.model.body_by_name("c").shape)
    assert nb._xyz(g.Value(g.FirstParameter())) == pytest.approx((0, 0, 0))
    assert nb._xyz(g.Value(g.LastParameter())) == pytest.approx((30, 0, 0))


def test_weights_make_an_exact_quarter_circle(p):
    ok(p, "NURBS, 2, (10,0,0), (10,10,0,0.70710678), (0,10,0)")
    assert p.evaluate("LENGTH(1)") == pytest.approx(math.pi * 5, rel=1e-6)


def test_closed_curve_and_too_high_degree(p):
    ok(p, "NURBS, 3, (10,0,0), (0,10,0), (-10,0,0), (0,-10,0), CLOSE")
    assert p.model.body(1).shape.Closed()
    r = ok(p, "NURBS, 3, (0,0,0), (10,5,0), (20,0,0)")
    assert "at most degree 2" in r.warning
    assert "at least 3" in err(p, "NURBS, 3, (0,0,0), (5,0,0), CLOSE")


def test_movept_keeps_ids_and_moves_the_point(p):
    ok(p, WAVE)
    edges = list(p.model.body(1).entity_ids["EDGE"])
    ok(p, "MOVEPT, c, 2, 0, 5, 0")
    assert p.evaluate("POLE(c, 2)") == (10, 13, 0)
    ok(p, "MOVEPT, c, 2, 1, 2, 3, TO")
    assert p.evaluate("POLE(c, 2)") == (1, 2, 3)
    assert p.model.body(1).entity_ids["EDGE"] == edges
    assert "control points 1 to 4" in err(p, "MOVEPT, c, 9, 0, 0, 1")
    assert "(i, j)" not in err(p, "MOVEPT, c, (1, 2), 0, 0, 1")


def test_knot_and_degree_keep_the_shape(p):
    ok(p, WAVE)
    before = nb.curve_of(p.model.body(1).shape)
    ok(p, "KNOT, c, 0.3\nDEGREE, c, 5")
    after = nb.curve_of(p.model.body(1).shape)
    assert after.Degree() == 5 and after.NbPoles() > 4
    for t in (0.1, 0.5, 0.9):
        a = nb._xyz(before.Value(t))
        b = nb._xyz(after.Value(t))
        assert a == pytest.approx(b, abs=1e-7)
    assert "only go up" in err(p, "DEGREE, c, 2")
    assert "between 0 and 1" in err(p, "KNOT, c, 1.5")


def test_weight_pulls_the_curve(p):
    ok(p, WAVE)
    d0 = p.evaluate("BBOX(c).ymax")
    ok(p, "WEIGHT, c, 2, 4")
    assert p.evaluate("BBOX(c).ymax") > d0 + 1
    assert "greater than 0" in err(p, "WEIGHT, c, 2, 0")


def test_rebuild_turns_a_polyline_into_one_curve(p):
    ok(p, "POLYLINE, (0,0,0), (10,0,0), (10,10,0), (20,10,0)")
    assert "pieces" in err(p, "MOVEPT, 1, 2, 0, 0, 1")
    r = ok(p, "REBUILD, 1, 12")
    assert p.evaluate("NPOLES(1)") == 12
    assert "away from the old one" in r.warning  # sharp corners round off
    ok(p, "MOVEPT, 1, 2, 0, 0, 1")


def test_rebuild_closed_curve_stays_closed(p):
    ok(p, "CIRCLE, 0,0,0, 10\nREBUILD, 1, 10")
    assert p.model.body(1).shape.Closed()
    assert p.evaluate("LENGTH(1)") == pytest.approx(2 * math.pi * 10, rel=1e-3)


def test_lines_and_arcs_become_nurbs(p):
    ok(p, "LINE, 0,0,0, 10,0,0\nMOVEPT, 1, 2, 0, 5, 0")
    assert p.evaluate("POLE(1, 2)") == (10, 5, 0)


# ---- surfaces --------------------------------------------------------------------

ROWS = """NURBS, 3, (0,0,0), (10,0,4), (20,0,4), (30,0,0)
NURBS, 3, (0,10,2), (10,10,6), (20,10,6), (30,10,2)
NURBS, 2, (0,20,0), (15,20,8), (30,20,0)
NSURF, 2, 1, 2, 3
NAME, LAST, s"""


def test_nsurf_matches_rows_and_edits(p):
    ok(p, ROWS)
    assert p.evaluate("NPOLES(s, \"U\")") == 3
    nv = p.evaluate("NPOLES(s, \"V\")")
    assert nv >= 4
    assert p.evaluate("POLE(s, 1, 1)") == (0, 0, 0)
    faces = list(p.model.body_by_name("s").entity_ids["FACE"])
    z0 = p.evaluate("BBOX(s).zmax")
    ok(p, "MOVEPT, s, (2, 2), 0, 0, 5")
    assert p.evaluate("BBOX(s).zmax") > z0 + 0.5
    assert p.model.body_by_name("s").entity_ids["FACE"] == faces
    ok(p, "KNOT, s, 0.5, V")
    assert p.evaluate("NPOLES(s, \"V\")") > nv
    r = ok(p, "REBUILD, s, 6, 3, 6")
    assert p.evaluate("NPOLES(s, \"U\")") == 6
    assert "POLES" not in r.message
    assert "(1, 1)" in ok(p, "POLES, s").message


def _net(p):
    ok(p, """SPLINE, (0,0,0), (10,0,2), (20,0,0)
SPLINE, (0,10,0), (10,10,3), (20,10,0)
SPLINE, (0,20,0), (10,20,4), (20,20,0)
SPLINE, (0,0,0), (0,10,0), (0,20,0)
SPLINE, (10,0,2), (10,10,3), (10,20,4)
SPLINE, (20,0,0), (20,10,0), (20,20,0)""")


def test_network_passes_through_every_curve(p):
    _net(p)
    ok(p, "NETWORK, 1, 2, 3, ACROSS, 4, 5, 6")
    g = nb.surface_of(p.model.body(7).shape)[0]
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt

    for q in ((10, 10, 3), (5, 0, 1.4), (10, 5, 2.4)):
        if q == (5, 0, 1.4):  # a point of curve 1
            c = nb.curve_of(p.model.body(1).shape)
            q = nb._xyz(c.Value(0.25 * c.LastParameter()))
        if q == (10, 5, 2.4):
            c = nb.curve_of(p.model.body(5).shape)
            q = nb._xyz(c.Value(0.25 * c.LastParameter()))
        assert GeomAPI_ProjectPointOnSurf(gp_Pnt(*q), g).LowerDistance() < 0.02
    # given backwards, the curves are turned round
    ok(p, "NETWORK, 1, 2, 3, ACROSS, 6, 5, 4")


def test_network_needs_curves_that_meet(p):
    _net(p)
    ok(p, "SPLINE, (0,30,5), (20,30,5)")
    assert "do not meet" in err(p, "NETWORK, 1, 2, 7, ACROSS, 4, 5, 6")
    assert "ACROSS" in err(p, "NETWORK, 1, 2, 3")
    assert "in the order" in err(p, "NETWORK, 1, 3, 2, ACROSS, 4, 5, 6")


def test_fill_and_sew_a_cube(p):
    faces = [[(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
             [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], [(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)],
             [(0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)], [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]]
    lines, n, fills = [], 0, []
    for f in faces:
        ids = []
        for a, b in zip(f, f[1:] + f[:1]):
            lines.append("LINE, " + ", ".join(str(10 * v) for v in a + b))
            n += 1
            ids.append(n)
        lines.append("FILL, G0, " + ", ".join(map(str, ids)))
        n += 1
        fills.append(n)
    ok(p, "\n".join(lines))
    r = ok(p, "SEW, " + ", ".join(map(str, fills)))
    assert "closed solid" in r.message
    assert p.evaluate("VOL(LAST)") == pytest.approx(1000, rel=1e-4)
    assert len(p.model.bodies) == n - 6 + 1  # the patches were used up


def test_fill_refuses_an_open_loop(p):
    ok(p, "LINE, 0,0,0, 10,0,0\nLINE, 10,0,0, 10,10,0")
    assert "do not close" in err(p, "FILL, G0, 1, 2")


def test_fill_g1_meets_a_surface_smoothly(p):
    ok(p, """NURBS, 3, (0,0,0), (0,4,4), (0,8,4), (0,12,0)
NURBS, 3, (-10,0,0), (-10,4,4), (-10,8,4), (-10,12,0)
NSURF, 1, 1, 2
NAME, LAST, wing
NURBS, 3, (10,0,0), (10,4,2), (10,8,2), (10,12,0)
LINE, 0,0,0, 10,0,0
LINE, 0,12,0, 10,12,0""")
    from modeler.commands.queries import centre

    wing = p.model.body_by_name("wing")
    edge = next(g for g in wing.entity_ids["EDGE"]
                if abs(centre("EDGE", p.model.entity_shape("EDGE", g))[0]) < 1e-6)
    r = ok(p, f"PICK, EDGE, {edge}\nFILL, G1, SEL, 4, 5, 6")
    deg = float(r.message.split("within ")[1].split(" degrees")[0])
    assert deg < 0.1
    assert "do not close" in err(p, "FILL, G0, 4, 5, 6")  # without the wing's edge the loop is open


def test_sew_open_surfaces_reports_free_edges(p):
    ok(p, ROWS)
    r = ok(p, "SEW, s")
    assert "free edges" in r.message


# ---- forms and the point editor ------------------------------------------------------

def test_every_new_command_has_a_form():
    assert F.missing_forms() == []
    for t in ("NURBS, 3, (0, 0, 0), (10, 8, 0, 2), (20, 0, 0), CLOSE", "NETWORK, 1, 2, ACROSS, 3, 4",
              "FILL, G2, SEL", "MOVEPT, c, (2, 3), 0, 0, 4", "SEW, 1, 2, 3", "NSURF, 2, a, b, c",
              "KNOT, s, 0.5, V", "REBUILD, c, 8"):
        sp, v, vals = F.parse(t)
        assert F.build(sp, vals, v) == t


def test_point_editor_drag_writes_movept(p):
    ok(p, WAVE)
    ed = PointEditor(p.model, 1)
    assert len(ed.points()) == 4 and len(ed.lines()) == 3

    def top(q):  # a view from above, 10 pixels a unit
        return q[0] * 10, -q[1] * 10

    assert ed.hit(1000, 1000, top) is None
    assert ed.press(100, -80, top)
    ed.move(((10, 13, 50), (0, 0, -1)))  # mouse ray straight down
    assert ed.preview() is not None
    text = ed.release()
    assert text == "MOVEPT, c, 2, 0, 5, 0"
    ok(p, text)
    assert ed.refresh() and dict(ed.points())[(2,)] == pytest.approx((10, 13, 0))


def test_example_script_runs(p):
    with open("scripts/nurbs_freeform.cmd") as f:
        ok(p, f.read())
    assert p.evaluate("VOL(pebble)") > 10000
