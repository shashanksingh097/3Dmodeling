"""M5 part 2: BLEND, EXTEND, TRIM, MOVEFACE, REPLACEFACE."""

import pytest

from modeler.commands import Processor
from modeler.commands.queries import centre
from modeler.geometry import nurbs as nb
from modeler.geometry import surface_ops as so


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


PANELS = """NURBS, 3, (0,0,0), (0,4,3), (0,8,3), (0,12,0)
NURBS, 3, (-10,0,0), (-10,4,4), (-10,8,4), (-10,12,0)
NSURF, 1, 1, 2
NAME, LAST, a
NURBS, 3, (10,0,2), (10,4,6), (10,8,6), (10,12,2)
NURBS, 3, (20,0,1), (20,4,4), (20,8,4), (20,12,1)
NSURF, 1, 4, 5
NAME, LAST, b"""


def edge_at(p, name, x):
    m = p.model
    return next(g for g in m.body_by_name(name).entity_ids["EDGE"]
                if abs(centre("EDGE", m.entity_shape("EDGE", g))[0] - x) < 1e-6)


def _angle(r) -> float:
    return float(r.message.split("meets within ")[1].split(" degrees")[0])


@pytest.mark.parametrize("cont", ["G1", "G2"])
def test_blend_meets_both_surfaces_smoothly(p, cont):
    ok(p, PANELS)
    r = ok(p, f"BLEND, {cont}, {edge_at(p, 'a', 0)}, {edge_at(p, 'b', 10)}")
    assert _angle(r) < 0.1
    blend = p.model.body(p.model.last_body)
    assert p.evaluate(f"BBOX({blend.id}).xmin") == pytest.approx(0, abs=1e-3)
    assert p.evaluate(f"BBOX({blend.id}).xmax") == pytest.approx(10, abs=1e-3)
    # it sews to both panels into one skin with no gaps along the joins
    r = ok(p, f"SEW, a, {blend.id}, b")
    assert "8 free edges" in r.message


def test_blend_g2_matches_curvature_better_than_g1(p):
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt

    from modeler.commands.nurbs_handlers import _edge_with_face

    ok(p, """NURBS, 3, (-10,0,-4), (-10,4,0), (-10,8,0), (-10,12,-4)
NURBS, 3, (-5,0,0), (-5,4,4), (-5,8,4), (-5,12,0)
NURBS, 3, (0,0,1), (0,4,5), (0,8,5), (0,12,1)
NSURF, 2, 1, 2, 3
NAME, LAST, a
NURBS, 3, (10,0,2), (10,4,6), (10,8,6), (10,12,2)
NURBS, 3, (20,0,1), (20,4,4), (20,8,4), (20,12,1)
NSURF, 1, 5, 6
NAME, LAST, b""")
    sa = _edge_with_face(p, edge_at(p, "a", 0), "t")
    sb = _edge_with_face(p, edge_at(p, "b", 10), "t")
    q = so.edge_points(sa[0], 21)[10]  # the middle of panel a's edge

    def mean_curvature(face):
        srf = BRep_Tool.Surface_s(face)
        u, v = GeomAPI_ProjectPointOnSurf(gp_Pnt(*q), srf).LowerDistanceParameters()
        ad = BRepAdaptor_Surface(face)  # kept alive: the props only point at it
        props = BRepLProp_SLProps(ad, u, v, 2, 1e-7)
        assert props.IsCurvatureDefined()  # (this is also what computes the curvatures)
        return abs(props.MeanCurvature())

    panel = mean_curvature(sa[1])
    miss = {cont: abs(mean_curvature(so.blend(sa, sb, cont)[0]) - panel) for cont in ("G1", "G2")}
    assert miss["G2"] < 0.2 * miss["G1"]


def test_blend_needs_two_surface_edges(p):
    ok(p, PANELS)
    assert "two edges" in err(p, f"BLEND, G1, {edge_at(p, 'a', 0)}")
    ok(p, "LINE, 0,0,0, 5,0,0")
    line_edge = p.model.body(p.model.last_body).entity_ids["EDGE"][0]
    assert "not on a surface" in err(p, f"BLEND, G1, {edge_at(p, 'a', 0)}, {line_edge}")
    assert "no edges are picked" in err(p, "SEL, NONE\nBLEND, G2")


def test_extend_by_side_and_by_picked_edge(p):
    ok(p, PANELS)
    ok(p, f"PICK, EDGE, {edge_at(p, 'a', 0)}\nEXTEND, a, 3")
    assert p.evaluate("BBOX(a).xmax") == pytest.approx(3, abs=0.05)
    assert p.evaluate("BBOX(a).xmin") == pytest.approx(-10, abs=1e-6)
    ok(p, "EXTEND, b, 2, ALL")
    assert p.evaluate("BBOX(b).xmin") == pytest.approx(8, abs=0.05)
    assert p.evaluate("BBOX(b).ymin") == pytest.approx(-2, abs=0.6)
    assert "U0, U1" in err(p, "EXTEND, b, 2, TOP")


def test_trim_with_a_line_and_a_hole(p):
    ok(p, """NURBS, 3, (0,0,0), (10,0,4), (20,0,4), (30,0,0)
NURBS, 3, (0,20,0), (10,20,4), (20,20,4), (30,20,0)
NSURF, 1, 1, 2
NAME, LAST, s""")
    face = p.model.body_by_name("s").entity_ids["FACE"][0]
    a0 = p.evaluate(f"AREA({face})")
    ok(p, "LINE, 15, -5, 10, 15, 25, 10\nTRIM, s, LAST, 25, 10, 3")
    assert p.evaluate("BBOX(s).xmax") == pytest.approx(15, abs=1e-3)
    ok(p, "CIRCLE, 8, 10, 10, 4\nTRIM, s, LAST, 8, 10, 3")
    assert p.evaluate(f"AREA({face})") < a0 / 2
    ok(p, "LINE, 0, 0, 30, 1, 0, 30")
    assert "pieces" in err(p, "TRIM, s, LAST, 5, 5, 0")


def test_moveface_keeps_ids_and_moves_faces(p):
    ok(p, "BLOCK, 0,0,0, 20,20,10\nNAME, LAST, b")
    ids = sorted(p.model.body(1).entity_ids["FACE"])
    ok(p, "PICK, FACE, 6\nMOVEFACE, 0, 0, 5")
    assert p.evaluate("VOL(b)") == pytest.approx(6000)
    assert sorted(p.model.body(1).entity_ids["FACE"]) == ids
    assert p.evaluate("CENT(6, \"FACE\").z") == pytest.approx(15)
    ok(p, "PICK, FACE, 2\nMOVEFACE, -4, 0, 0")
    assert p.evaluate("VOL(b)") == pytest.approx(4800)
    assert p.evaluate("CENT(2, \"FACE\").x") == pytest.approx(16)
    assert "(0, 0, 0)" in err(p, "PICK, FACE, 2\nMOVEFACE, 0, 0, 0")


def test_replaceface_takes_a_wavy_surface(p):
    ok(p, """BLOCK, 0,0,0, 20,20,10
NAME, LAST, b
SURFACE, PARAM, u, v, 13 + 2*sin(18*u)*sin(18*v), -10, 30, -10, 30
NAME, LAST, wave
PICK, FACE, 6
REPLACEFACE, wave""")
    assert p.evaluate("VOL(b)") == pytest.approx(20 * 20 * 13, rel=0.02)
    assert 6 in p.model.body(1).entity_ids["FACE"]
    assert p.evaluate("NFACES(b)") == 6
    # cutting down to a surface inside the block
    ok(p, "SURFACE, PARAM, u, v, 4 + 0.02*u, -10, 30, -10, 30\nPICK, FACE, 6\nREPLACEFACE, LAST")
    assert p.evaluate("BBOX(b).zmax") < 5


def test_replaceface_refuses_a_surface_that_misses(p):
    ok(p, """BLOCK, 0,0,0, 20,20,10
NURBS, 3, (100,100,50), (105,100,52), (110,100,50)
NURBS, 3, (100,105,50), (105,105,52), (110,105,50)
NSURF, 1, 2, 3""")
    assert "REPLACEFACE" in err(p, "PICK, FACE, 6\nREPLACEFACE, LAST")
    assert p.evaluate("VOL(1)") == pytest.approx(4000)


def test_example_script_runs(p):
    with open("scripts/surface_ops.cmd") as f:
        ok(p, f.read())
    assert p.evaluate("VOL(base)") == pytest.approx(30 * 30 * 13 - 6 * 30 * 13, rel=0.02)
