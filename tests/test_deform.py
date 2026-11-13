"""M5 deformers: BEND, TWIST, TAPER, STRETCH, FLOW, and SWEEPVOL."""

import math

import pytest

from modeler.commands import Processor


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


BAR = "BLOCK, 0,0,0, 100,10,4\nNAME, LAST, bar"


def test_bend_keeps_length_volume_and_ids(p):
    ok(p, BAR)
    faces = sorted(p.model.body(1).entity_ids["FACE"])
    r = ok(p, "BEND, bar, 90")
    assert "along X towards +Z" in r.message
    assert p.evaluate("VOL(bar)") == pytest.approx(4000, rel=1e-4)
    R = 100 / (math.pi / 2)  # the centre line (z = 2) keeps its length
    assert p.evaluate("BBOX(bar).zmax") == pytest.approx(2 + R, abs=0.01)
    assert p.evaluate("BBOX(bar).xmax") == pytest.approx(R + 2, abs=0.01)
    assert sorted(p.model.body(1).entity_ids["FACE"]) == faces
    assert p.evaluate("VALID(bar)") == 1


def test_bend_down_and_with_a_law(p):
    ok(p, BAR + "\nBEND, bar, 90, X, -Z")
    assert p.evaluate("BBOX(bar).zmin") == pytest.approx(2 - 100 / (math.pi / 2), abs=0.01)
    q = Processor()
    ok(q, BAR + "\nBEND, bar, 90, X, Z, t**2")  # the bend gathers towards the far end
    assert q.evaluate("VOL(bar)") == pytest.approx(4000, rel=1e-3)
    assert q.evaluate("BBOX(bar).xmax") > p.evaluate("BBOX(bar).xmax")


def test_twist_and_its_law(p):
    ok(p, "BLOCK, 0,0,0, 10,10,60\nNAME, LAST, col\nTWIST, col, 45")
    assert p.evaluate("VOL(col)") == pytest.approx(6000, rel=1e-4)
    assert p.evaluate("BBOX(col).xmax - BBOX(col).xmin") == pytest.approx(10 * math.sqrt(2), abs=0.01)
    q = Processor()
    ok(q, "BLOCK, 0,0,0, 10,10,60\nTWIST, 1, 45, Z, sin(180*t)")  # out and back: both ends square again
    top = next(f for f in q.model.body(1).entity_ids["FACE"] if q.evaluate(f'CENT({f}, "FACE").z') > 59)
    assert q.evaluate(f'AREA({top})') == pytest.approx(100, rel=1e-6)
    assert q.evaluate("BBOX(1).xmax - BBOX(1).xmin") > 10.5  # (the middle turned)


def test_taper_and_stretch(p):
    ok(p, "BLOCK, 0,0,0, 10,10,60\nTAPER, 1, 0.5")
    # cross-section 100 * (1 - t/2)^2 along 60
    assert p.evaluate("VOL(1)") == pytest.approx(6000 * (1 - 0.5 + 0.25 / 3), rel=1e-4)
    ok(p, "BLOCK, 20,0,0, 40,10,10\nSTRETCH, LAST, 2")
    b = p.model.last_body
    assert p.evaluate(f"VOL({b})") == pytest.approx(4000, rel=1e-6)
    assert p.evaluate(f"BBOX({b}).xmax - BBOX({b}).xmin") == pytest.approx(80, abs=1e-6)
    ok(p, "BLOCK, 0,30,0, 40,10,10\nSTRETCH, LAST, 2, X, FREE")
    assert p.evaluate(f"VOL({p.model.last_body})") == pytest.approx(8000, rel=1e-6)


def test_curved_bodies_deform_too(p):
    ok(p, "CYL, 0, 0, 0, 5, 60, 1, 0, 0\nBEND, 1, 60")
    assert p.evaluate("VOL(1)") == pytest.approx(math.pi * 25 * 60, rel=1e-3)
    ok(p, "SPHERE, 50, 0, 0, 8\nTWIST, LAST, 90, X")
    assert p.evaluate(f"VOL({p.model.last_body})") == pytest.approx(4 / 3 * math.pi * 512, rel=1e-3)


def test_flow_lays_text_along_a_curve(p):
    ok(p, """TEXT, "FLOW", 0, 0, 0, 10, 2
NAME, LAST, label
ARC, 0,0,20, 40,30,20, 80,0,20
NAME, LAST, arc""")
    v0 = p.evaluate("VOL(label)")
    long0 = p.evaluate("BBOX(label).xmax - BBOX(label).xmin")
    r = ok(p, "FLOW, label, arc, FIT")
    assert "fitted to its length" in r.message
    assert p.evaluate("VALID(label)") == 1
    R = 125 / 3  # the arc's circle: centre (40, -35/3), through all three points
    arc_len = R * 2 * math.asin(40 / R)
    # FIT stretches the word to the arc's length, so the volume grows by about as much
    assert p.evaluate("VOL(label)") == pytest.approx(v0 * arc_len / long0, rel=0.05)
    # the letters now follow the arc, standing on it up to its top, and lie centred on the arc's plane
    assert 30 < p.evaluate("BBOX(label).ymax") < 30 + 7.7
    assert p.evaluate("BBOX(label).zmin") == pytest.approx(19, abs=1e-3)
    assert p.evaluate("BBOX(label).zmax") == pytest.approx(21, abs=1e-3)


def test_flow_too_long_without_fit(p):
    ok(p, BAR + "\nLINE, 0, 50, 0, 40, 50, 0")
    assert "add FIT" in err(p, "FLOW, bar, LAST")
    assert "follow itself" in err(p, "FLOW, bar, bar")


def test_sweepvol_slot_exact_and_cut(p):
    ok(p, """BLOCK, -10, -10, -5, 60, 30, 10
NAME, LAST, plate
CYL, 0, 0, 0, 3, 10
NAME, LAST, cutter
LINE, 0, 0, 0, 30, 0, 0
NAME, LAST, track""")
    r = ok(p, "SWEEPVOL, cutter, track")
    assert "exact" in r.message
    assert p.evaluate(f"VOL({p.model.last_body})") == pytest.approx(math.pi * 9 * 10 + 6 * 10 * 30, rel=1e-6)
    v = p.evaluate("VOL(plate)")
    ok(p, "SUBTRACT, plate, LAST")
    # the plate is 10 thick from z = -5: the cutter (z 0..10) takes half its height through it
    assert p.evaluate("VOL(plate)") == pytest.approx(v - (math.pi * 9 + 6 * 30) * 5, rel=1e-6)


def test_sweepvol_ball_and_other_tools(p):
    ok(p, "SPHERE, 0,0,0, 3\nSPLINE, (0,0,0), (20,10,0), (40,0,5)")
    r = ok(p, "SWEEPVOL, 1, 2")
    assert "round pipe" in r.message and p.evaluate(f"VALID({p.model.last_body})") == 1
    ok(p, "CONE, 0,30,0, 3, 1, 6\nLINE, 0,30,0, 30,30,0")
    r = ok(p, f"SWEEPVOL, {p.model.last_body - 1}, LAST")
    assert "copies along the path" in r.message and "ridges" in r.message
    ok(p, "LINE, 0,0,0, 1,0,0")
    assert "not a solid" in err(p, "SWEEPVOL, LAST, 2")


def test_a_mesh_body_bends_by_its_points(p, tmp_path):
    ok(p, f'SPHERE, 0,0,0, 10\nEXPORT, STL, "{tmp_path}/s.stl"')
    q = Processor()
    ok(q, f'IMPORT, STL, "{tmp_path}/s.stl"')
    r = ok(q, "STRETCH, 1, 2, Z")
    assert "as a mesh" in r.message
    assert q.evaluate("BBOX(1).zmax - BBOX(1).zmin") == pytest.approx(40, rel=1e-3)


def test_refusals(p):
    ok(p, BAR)
    assert "less than 360" in err(p, "BEND, bar, 400")
    assert "above 0" in err(p, "TAPER, bar, -1")
    assert "greater than 0" in err(p, "STRETCH, bar, 0")
    assert "X, Y or Z" in err(p, "TWIST, bar, 10, W")
    assert "another axis" in err(p, "BEND, bar, 30, X, X")


def test_example_script_runs(p):
    with open("scripts/deformers.cmd") as f:
        ok(p, f.read())


def test_greville_points_stay_inside_the_knots():
    # the mean of three 0.35 knots rounds below 0.35, where every basis function is 0 (a singular fit)
    from modeler.geometry import deform as dfm
    from modeler.geometry import nurbs as nb
    import numpy as np

    k = np.array([0.35] * 4 + [1.1675, 1.985, 2.8025, 3.62, 4.4375, 5.255, 6.07251] + [6.89001] * 4)
    g = dfm._greville(k, 3, 11)
    assert g[0] == 0.35 and g[-1] == 6.89001
    N = nb.basis(k, 3, g)
    assert np.linalg.matrix_rank(N) == 11
