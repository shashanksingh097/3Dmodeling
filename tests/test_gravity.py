"""GRAVITY: does the assembly stand up? (geometry/gravity.py)"""

import numpy as np

from modeler.commands import Processor
from modeler.geometry import gravity as gv


def run(p, *lines):
    for line in lines:
        r = p.run(line)
        assert r.ok, (line, r.message)
    return r


def line_of(msg, name):
    return next(x for x in msg.splitlines() if x.strip().startswith(name))


def test_outline_and_margin():
    h = gv.hull(np.array([[0, 0], [10, 0], [10, 4], [0, 4], [5, 2]], float))
    assert len(h) == 4
    assert np.isclose(gv.margin(np.array([5.0, 2.0]), h), 2.0)
    assert np.isclose(gv.margin(np.array([13.0, 2.0]), h), -3.0)
    line = gv.hull(np.array([[0, 0], [5, 0], [10, 0]], float))
    assert len(line) == 2 and gv.margin(np.array([5.0, 0.0]), line) == 0.0


def _stack(p):
    run(p, "BLOCK, 0,0,0, 100,60,10", "NAME, LAST, base", "BLOCK, 10,10,10, 20,20,40", "NAME, LAST, post",
        "BLOCK, 0,10,50, 80,20,8", "NAME, LAST, arm", "BLOCK, 60,10,30, 10,10,10", "NAME, LAST, floater",
        "BLOCK, 100,20,0, 10,10,30", "NAME, LAST, side", "BLOCK, 10,40,10.2, 10,10,10", "NAME, LAST, near")


def test_floating_tipping_resting_and_gaps():
    p = Processor()
    _stack(p)
    msg = run(p, "GRAVITY").message
    assert "rests on the floor, its centre of mass 30 inside" in line_of(msg, "base")
    assert "rests on base (1), its centre of mass 10 inside" in line_of(msg, "post")
    assert "TIPS off post (2): its centre of mass is 10 past" in line_of(msg, "arm")  # 0..80 on 10..30
    assert "FLOATS" in line_of(msg, "floater") and "FLOATS" in line_of(msg, "near")
    assert "rests on the floor" in line_of(msg, "side")  # touching base's side is no support
    assert "gap: base (1) and near (6) are 0.2 apart" in msg
    assert "on the floor: it stands" in msg and "3 parts to look at" in msg


def test_named_ground_fastened_parts_and_side_hangers():
    p = Processor()
    _stack(p)
    run(p, "BLOCK, 100, 5, 4, 10, 10, 4", "NAME, LAST, hanger")  # touches only base's side face
    msg = run(p, "GRAVITY, base").message
    assert "standing on base (1)" in msg and "on the floor" not in msg
    assert "held only at its sides by base (1)" in line_of(msg, "hanger")
    assert "held only at its sides" in line_of(msg, "side")  # the floor is not there now, only base's side
    msg = run(p, "GRAVITY, base, \"hanger side\"").message
    assert "held (fastened)" in line_of(msg, "hanger")


def test_whole_assembly_tips_and_overlaps_hold():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 10,10,10", "NAME, LAST, foot", "BLOCK, 0,0,10, 60,10,4", "NAME, LAST, beam",
        "BLOCK, 50,0,14, 10,10,40", "NAME, LAST, weight", "MATERIAL, weight, STEEL",
        "BLOCK, 2,2,8, 6,6,6", "NAME, LAST, pin")
    msg = run(p, "GRAVITY, FLOOR, beam weight").message
    assert "held (pressed into" in line_of(msg, "pin") and "overlap: foot (1) and pin (4)" in msg
    assert "on the floor: it TIPS over" in msg
    assert run(p, "GRAVITY, OFF").message == "gravity marks cleared"


def test_errors():
    p = Processor()
    assert not p.run("GRAVITY").ok  # no parts
    run(p, "BLOCK, 0,0,0, 1,1,1")
    assert not p.run("GRAVITY, FLOOR, , 0, 0, 0").ok
    assert not p.run("GRAVITY, FLOOR, , 0, 0, -1, -2").ok
