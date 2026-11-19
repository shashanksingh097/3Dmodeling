"""Surface inspection (PLAN item 57): CONTINUITY judges every join (open, sharp, kink, G1, G2) with
the worst gap and angle; COMB draws curvature combs; INSPECT lists the places worth a second look."""

import json

import pytest

import flawed_files as ff
from modeler.commands import Processor


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    res = p.run_script(text)
    bad = [r for r in res if not r.ok]
    assert not bad, f"{bad[0].line}: {bad[0].message}"
    return res[-1]


def joins(p, b, tol=0):
    return json.loads(p.run(f"CONTINUITY, {b}, {tol}, JSON").message)


def test_a_box_has_sharp_joins_only(p):
    ok(p, "BLOCK, 0,0,0, 40, 20, 10")
    d = joins(p, 1)
    assert d["counts"] == {"open": 0, "sharp": 12, "kink": 0, "G1": 0, "G2": 0} and d["open_edges"] == 0
    assert all(j["angle"] == pytest.approx(90) for j in d["joins"])


def test_a_fillet_is_tangent_but_not_curvature_smooth(p):
    ok(p, "BLOCK, 0,0,0, 40, 20, 10\nPICK, EDGE, 1\nFILLET, 3")
    b = max(p.model.bodies)
    d = joins(p, b)
    assert d["counts"]["G1"] == 2  # where the round meets the flat faces the curvature jumps 0 -> 1/3
    g1 = [j for j in d["joins"] if j["kind"] == "G1"]
    assert all(j["angle"] < 0.25 for j in g1)
    assert sorted(abs(k) for k in g1[0]["curvature"]) == pytest.approx([0, 1 / 3], abs=1e-6)
    msg = p.run(f"CONTINUITY, {b}").message
    assert "2 G1 (tangent)" in msg and "G1 (the curvature jumps" in msg


def test_a_nearly_straight_corner_is_a_kink(p):
    # a polygon with one corner bent by 2 degrees: the faces there are nearly in line
    ok(p, "SKETCH, s, XY\nSPOLY, 0,0, 20,0, 40,0.7, 40,20, 0,20, 0,0\nENDSKETCH\nEXTRUDE, s, 5")
    b = max(p.model.bodies)
    d = joins(p, b)
    kinks = [j for j in d["joins"] if j["kind"] == "kink"]
    assert len(kinks) == 1 and kinks[0]["angle"] == pytest.approx(2.0, abs=0.05)
    msg = p.run(f"INSPECT, {b}").message
    assert f"kink: edge {kinks[0]['edge']}" in msg and "meant to be smooth" in msg


def test_faces_that_do_not_quite_meet_are_open(p, tmp_path):
    path = ff.gaps(str(tmp_path), gap=0.02)
    ok(p, f'IMPORT, STEP, "{path}"\nHEAL, 1, 0.05')
    d = joins(p, 1, 0.005)  # a tolerance below the gap the sewing bridged
    assert d["counts"]["open"] == 4
    assert max(j["gap"] for j in d["joins"]) == pytest.approx(0.02, abs=0.002)
    assert joins(p, 1, 0.05)["counts"]["open"] == 0


def test_combs_on_curved_edges(p):
    ok(p, "BLOCK, 0,0,0, 40, 20, 10\nCYL, 60,0,0, 5, 10")
    shown = []

    class View:
        def show_toolpath(self, shape):
            shown.append(shape)

    p.view = View()
    assert "every edge is straight" in p.run("COMB, 1").message
    msg = p.run("COMB, 2").message
    assert "tightest bend radius 5" in msg and shown and shown[-1] is not None
    e = p.model.bodies[2].entity_ids["EDGE"][0]
    assert "edge" in p.run(f"COMB, EDGE, {e}").message
    assert p.run("COMB, OFF").message == "combs hidden" and shown[-1] is None


def test_a_comb_shows_where_a_flat_curve_changes_side():
    import numpy as np
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge

    from modeler.geometry import inspect_surf as ins
    from modeler.geometry import nurbs

    x = np.linspace(0, 40, 50)
    s_curve = nurbs.fit_curve(np.stack([x, 5 * np.sin(x / 40 * 2 * np.pi), 0 * x], 1), 8, 3)
    edge = BRepBuilderAPI_MakeEdge(s_curve).Edge()
    c = ins.comb(edge, 1, n=60, size=40)
    assert c.inflections >= 1 and len(c.tips) == 61


def test_inspect_lists_the_tightest_bend_and_thinnest_wall(p):
    ok(p, "BLOCK, 0,0,0, 40, 20, 10\nCYL, 20,10,-1, 9.5, 12\nSUBTRACT, 1, 2")
    b = max(p.model.bodies)
    d = json.loads(p.run(f"INSPECT, {b}, 0, JSON").message)
    assert d["smallest_radius"]["radius"] == pytest.approx(9.5, rel=1e-3)
    assert d["thinnest_wall"]["t"] == pytest.approx(0.5, abs=0.05)
    assert not d["kinks"] and not d["gaps"]
    msg = p.run(f"INSPECT, {b}").message
    assert "tightest bend: radius 9.5" in msg and "thinnest wall: 0.5" in msg


def test_inspection_refuses_meshes(p):
    ok(p, "SPHERE, 0,0,0, 5\nTOMESH, 1")
    assert "mesh body" in p.run("CONTINUITY, 1").message
    assert "mesh body" in p.run("INSPECT, 1").message
