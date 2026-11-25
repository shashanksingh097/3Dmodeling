"""PLAN item 78: WRAPSKIN, one closed skin around messy meshes or an assembly."""

import numpy as np

from modeler.commands import Processor
from modeler.geometry import meshbody as mb
from modeler.geometry import shrinkwrap as sw


def ok(p, line):
    r = p.run(line)
    assert r.ok, r.message
    return r


def test_skin_lies_on_the_outside_and_closes_small_holes():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40, 30, 20")
    ok(p, "CYL, 20, 15, -1, 1.5, 22")
    ok(p, "SUBTRACT, 1, 2")
    r = ok(p, "WRAPSKIN, LAST, 2, 1")
    skin = p.model.bodies[max(p.model.bodies)].shape
    pts, t = mb.arrays(skin)
    assert mb.closed(t)
    assert abs(mb.volume(pts, t) - 24000) < 0.01 * 24000  # the 3 mm hole is closed over
    m = (abs(pts[:, 0] - 10) < 3) & (abs(pts[:, 1] - 10) < 3)
    assert abs(pts[m, 2].max() - 20) < 0.05 and abs(pts[m, 2].min()) < 0.05
    assert "one piece" in r.message


def test_wide_holes_stay_and_far_parts_stay_apart():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40, 30, 20")
    ok(p, "CYL, 20, 15, -1, 6, 22")
    ok(p, "SUBTRACT, 1, 2")
    ok(p, "SPHERE, 70, 15, 10, 5")
    r = ok(p, "WRAPSKIN, ALL, 1, 1")
    d = p.reports["WRAPSKIN"]
    assert d["pieces"] == 2 and d["closed"] and "2 separate pieces" in r.message
    assert d["volume"] < 24000 - 0.8 * np.pi * 36 * 20 + 4 / 3 * np.pi * 125 * 1.1


def test_overlapping_and_touching_parts_become_one():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 20, 20, 20")
    ok(p, "BLOCK, 15,0,0, 20, 20, 20")
    ok(p, "BLOCK, 35.5,0,0, 10, 20, 20")  # 0.5 apart: joined with a gap of 1
    ok(p, "WRAPSKIN, ALL, 1, 0.5")
    d = p.reports["WRAPSKIN"]
    assert d["pieces"] == 1
    assert abs(d["volume"] - 45.5 * 400) < 0.02 * 45.5 * 400


def test_open_mesh_is_closed():
    pts, t = mb.sphere(10, 48)
    keep = np.ones(len(t), bool)
    keep[:40] = False  # a hole in the skin
    skin = sw.wrap([mb.make_shape(pts, t[keep])], 3.0, 0.75)
    assert mb.closed(skin.tris) and mb.pieces(skin.points, skin.tris) == 1


def test_refusals():
    p = Processor()
    assert "no bodies" in p.run("WRAPSKIN").message
    ok(p, "BLOCK, 0,0,0, 10, 10, 10")
    assert "positive" in p.run("WRAPSKIN, ALL, 0").message
    assert "SEL needs" in p.run("WRAPSKIN, SEL, 1").message
    assert "cell of at least" in p.run("WRAPSKIN, ALL, 1, 0.001").message
