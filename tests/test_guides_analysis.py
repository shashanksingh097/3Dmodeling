"""M5 part 3: LOFT with guide curves, SWEEP following a surface's normal, PROJECT, ANALYZE."""

import math
import sys

import pytest
from OCP.BRep import BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from modeler.commands import Processor
from modeler.geometry import sweep as sw

_as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face


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


def far(p, body, curve, n=40) -> float:
    """How far the curve body strays from the body, at worst."""
    m = p.model
    c = sw.PathSampler(sw.as_wire(m.body(curve).shape, ""))
    worst = 0.0
    for i in range(n + 1):
        q = c.at(c.length * i / n)[0]
        d = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(*q)).Vertex(), m.body(body).shape)
        d.Perform()
        worst = max(worst, d.Value())
    return worst


def normal_at(shape, q):
    best = None
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        f = _as_face(ex.Current())
        ex.Next()
        pj = GeomAPI_ProjectPointOnSurf(gp_Pnt(*q), BRep_Tool.Surface_s(f))
        if pj.NbPoints() and (best is None or pj.LowerDistance() < best[0]):
            best = (pj.LowerDistance(), f, *pj.LowerDistanceParameters())
    _, f, u, v = best
    ad = BRepAdaptor_Surface(f)
    n = BRepLProp_SLProps(ad, u, v, 1, 1e-7).Normal()
    return (n.X(), n.Y(), n.Z())


# =============================================================================
# LOFT with guides
# =============================================================================


def test_one_guide_bulges_the_loft_through_it(p):
    ok(p, """CIRCLE, 0, 0, 0, 10
CIRCLE, 0, 0, 30, 10
SPLINE, (10,0,0), (16,0,15), (10,0,30)""")
    r = ok(p, "LOFT, 1, 2, GUIDE, 3")
    assert "along 1 guide" in r.message
    b = p.model.last_body
    assert far(p, b, 3) < 0.005
    assert far(p, b, 1) < 1e-4 and far(p, b, 2) < 1e-4
    assert p.evaluate(f"VOL({b})") > 1.5 * math.pi * 100 * 30  # it swells round, not just sideways
    assert p.evaluate(f"BBOX({b}).xmax") == pytest.approx(16, abs=0.05)


def test_two_guides_through_three_sections(p):
    ok(p, """CIRCLE, 0, 0, 0, 10
ELLIPSE, 0, 0, 20, 12, 7
CIRCLE, 0, 0, 40, 8
SPLINE, (10,0,0), (15,0,10), (12,0,20), (9,0,30), (8,0,40)
SPLINE, (0,10,0), (0,6,10), (0,7,20), (0,9,30), (0,8,40)
LOFT, 1, 2, 3, GUIDES, 4, 5""")
    b = p.model.last_body
    for c in (1, 2, 3):
        assert far(p, b, c) < 1e-3
    for g in (4, 5):
        assert far(p, b, g) < 0.01
    assert p.evaluate(f"BBOX({b}).xmax") == pytest.approx(15, abs=0.1)


def test_open_sections_make_a_surface_along_the_guide(p):
    ok(p, """SPLINE, (0,0,0), (10,0,3), (20,0,0)
SPLINE, (0,20,0), (10,20,3), (20,20,0)
SPLINE, (10,0,3), (10,10,9), (10,20,3)
LOFT, 1, 2, SURFACE, GUIDE, 3""")
    b = p.model.last_body
    assert p.evaluate(f"NFACES({b})") == 1
    assert p.evaluate(f"BBOX({b}).zmax") == pytest.approx(9, abs=0.01)
    assert far(p, b, 3) < 1e-3


def test_guide_refusals(p):
    ok(p, """CIRCLE, 0, 0, 0, 10
CIRCLE, 0, 0, 20, 10
CIRCLE, 0, 0, 40, 10
SPLINE, (10,0,0), (11,0,10), (10,0,20), (11,0,30), (10,0,40)
SPLINE, (30,0,0), (30,0,40)""")
    assert "misses section 1 by 20" in err(p, "LOFT, 1, 2, 3, GUIDE, 5")
    assert "in the order" in err(p, "LOFT, 1, 3, 2, GUIDE, 4")
    assert "after GUIDE" in err(p, "LOFT, 1, 2, GUIDE")
    assert "RULED or CLOSED" in err(p, "LOFT, 1, 2, RULED, GUIDE, 4")
    assert "used twice" in err(p, "LOFT, 1, 2, GUIDE, 1")


# =============================================================================
# SWEEP along a surface's normal, and PROJECT
# =============================================================================

ON_CYLINDER = """SURFACE, PARAM, 10*cos(u), 10*sin(u), v, 0, 200, -10, 10
NAME, LAST, can
CURVE, PARAM, 10*cos(180*t), 10*sin(180*t), 4*sin(360*t), 0, 1
NAME, LAST, wave
LINE, 10, -1.5, 0, 10, 1.5, 0
NAME, LAST, strip"""


def _angles(p, body, path="wave", n=12):
    m = p.model
    c = sw.PathSampler(sw.as_wire(m.body_by_name(path).shape, ""))
    out = []
    for i in range(n + 1):
        q = c.at(c.length * (0.02 + 0.96 * i / n))[0]
        a, b = normal_at(m.body(body).shape, q), normal_at(m.body_by_name("can").shape, q)
        out.append(math.degrees(math.acos(min(1.0, abs(sum(x * y for x, y in zip(a, b)))))))
    return out


def test_sweep_normal_keeps_the_profile_square_to_the_surface(p):
    ok(p, ON_CYLINDER)
    r = ok(p, "SWEEP, strip, wave, , , NORMAL, , , , , , 0, can")
    assert "sections" in r.message  # (a path drawn on its own: the kernel's exact sweep cannot follow the can)
    on = _angles(p, p.model.last_body)
    assert max(on) - min(on) < 1.0
    # laid on the can by PROJECT, the path carries curves on the surface: the exact sweep follows it
    ok(p, "PROJECT, wave, can\nNAME, LAST, laid")
    r = ok(p, "SWEEP, strip, laid, , , NORMAL, , , , , , 0, can")
    assert "exact" in r.message
    on = _angles(p, p.model.last_body, "laid")
    assert max(on) - min(on) < 0.5
    ok(p, "SWEEP, strip, wave, , , MINTWIST, , , , , , 0")
    free = _angles(p, p.model.last_body)
    assert max(free) - min(free) > 5  # (without it the strip tips over as the wave climbs the can)
    # with a law the sections follow the same frames
    ok(p, "SWEEP, strip, wave, 0, 1 + 0.5*t, NORMAL, 1, 1, 0, 0, 40, 0, can")
    law = _angles(p, p.model.last_body)
    assert max(law) - min(law) < 1.5


def test_sweep_normal_refusals(p):
    ok(p, ON_CYLINDER)
    assert "give the surface" in err(p, "SWEEP, strip, wave, , , NORMAL")
    assert "must be NORMAL" in err(p, "SWEEP, strip, wave, , , FRENET, , , , , , 0, can")
    ok(p, "LINE, 30, 0, 0, 30, 0, 10")
    assert "must lie on the NORMAL surface" in err(p, "SWEEP, strip, LAST, , , NORMAL, , , , , , 0, can")


def test_project_lays_a_curve_on_a_surface(p):
    ok(p, """SURFACE, PARAM, u, v, 6 - 0.02*(u*u+v*v), -15, 15, -15, 15
NAME, LAST, dome
SPLINE, (-10,-6,20), (-3,2,20), (4,-2,20), (10,6,20)""")
    r = ok(p, "PROJECT, LAST, dome, 0, 0, -1")
    assert "-> curve 3 (open" in r.message
    assert far(p, 1, 3) < 1e-4
    assert p.evaluate("BBOX(3).xmin") == pytest.approx(-10, abs=1e-3)  # straight down: x and y kept
    ok(p, "CIRCLE, 0, 0, 12, 5\nPROJECT, LAST, dome")
    assert far(p, 1, p.model.last_body) < 1e-4
    assert "not a curve" in err(p, "PROJECT, dome, dome")


# =============================================================================
# ANALYZE
# =============================================================================


def test_zebra_words_tell_g2_from_g1_and_creases(p):
    sys.path.insert(0, "tests")
    from test_surface_ops import PANELS, edge_at

    for cont, want in (("G1", "2 tangent only"), ("G2", "2 smooth in curvature")):
        q = Processor()
        ok(q, PANELS)
        ok(q, f"BLEND, {cont}, {edge_at(q, 'a', 0)}, {edge_at(q, 'b', 10)}\nSEW, a, LAST, b")
        r = ok(q, "ANALYZE, LAST")
        assert want in r.message, r.message
    ok(p, "BLOCK, 0,0,0, 20,20,10\nSEL, S, EDGE, LOC, Z, 10\nFILLET, 3")
    n = len(p.history)
    r = ok(p, "ANALYZE, LAST, ZEBRA")
    assert "8 tangent only" in r.message and "12 creased" in r.message and "up to 90 degrees" in r.message
    assert len(p.history) == n  # a look, not a model change
    assert p.analysis is not None and p.analysis.mode == "ZEBRA"
    ok(p, "ANALYZE, OFF")
    assert p.analysis is None


def test_curvature_and_gauss(p):
    ok(p, "SPHERE, 0, 0, 0, 8")
    r = ok(p, "ANALYZE, 1, CURVATURE")
    assert "from 0.125 to 0.125" in r.message and "radius 8 " in r.message
    ok(p, "SURFACE, PARAM, u, v, 0.05*(u*u - v*v), -10, 10, -10, 10")
    r = ok(p, "ANALYZE, LAST, GAUSS")
    assert "100% is saddle-shaped" in r.message or "99% is saddle-shaped" in r.message, r.message
    ok(p, "CYL, 30, 0, 0, 5, 10")
    r = ok(p, "ANALYZE, LAST, GAUSS")
    assert "100% is flat or bent one way" in r.message


def test_draft(p):
    ok(p, "SPHERE, 0, 0, 0, 8")
    r = ok(p, "ANALYZE, 1, DRAFT, 0, 0, 1, 2")
    # sin(2 degrees) of the height either side of the equator is too steep: 3.5% of a sphere's area
    pct = [int(x.split("%")[0].split()[-1]) for x in r.message.split(",") if "%" in x]
    assert pct[0] == pct[1] == pytest.approx(48, abs=1) and pct[2] == pytest.approx(3, abs=1)
    ok(p, "BLOCK, 20, 0, 0, 10, 10, 10")
    r = ok(p, "ANALYZE, LAST, DRAFT")
    faces = r.message.split("(faces ")[1]
    assert faces.count(",") == 3  # the four sides


def test_analyze_refusals(p):
    ok(p, "LINE, 0,0,0, 1,0,0\nBLOCK, 0,0,0, 1,1,1")
    assert "no faces" in err(p, "ANALYZE, 1")
    assert "ZEBRA, CURVATURE" in err(p, "ANALYZE, 2, SHINY")
    assert "0 to 90" in err(p, "ANALYZE, 2, DRAFT, 0, 0, 1, 95")


def test_example_script_runs(p):
    with open("scripts/guides_analysis.cmd") as f:
        ok(p, f.read())
