"""The section tests behind the LOFT/SWEEP/PIPE checks (geometry/overlap.py)."""

import math

import numpy as np

from modeler.commands import Processor
from modeler.geometry import overlap


def square(z=0.0, size=1.0, normal="z", at=(0.0, 0.0, 0.0)):
    h = size / 2
    pts = [(-h, -h), (h, -h), (h, h), (-h, h)]
    if normal == "z":
        return [(at[0] + x, at[1] + y, at[2] + z) for x, y in pts]
    return [(at[0] + z, at[1] + x, at[2] + y) for x, y in pts]  # in a plane x = const


def circle(r, z=0.0, n=48):
    return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), z) for i in range(n)]


def test_parallel_sections_apart_do_not_touch():
    assert overlap.clashes([square(0), square(1), square(2)]) == []


def test_crossing_sections_touch():
    found = overlap.clashes([square(0, 2), square(0, 2, normal="x")])
    assert found and (found[0].i, found[0].j) == (0, 1)


def test_sections_side_by_side_do_not_touch():
    # planes meet, but the squares are far apart along that line
    a = square(0, 1)
    b = square(0, 1, normal="x", at=(0.0, 5.0, 0.0))
    assert overlap.clashes([a, b]) == []


def test_same_plane_one_inside_the_other():
    assert overlap.clashes([circle(5), circle(8)])
    assert overlap.clashes([circle(5), circle(5)])  # the same section twice
    assert overlap.clashes([circle(1), [(x + 10, y, z) for x, y, z in circle(1)]]) == []


def test_skip_lets_a_closed_loop_meet_itself():
    a = square(0)
    assert overlap.clashes([a, square(1), a], skip=lambda i, j: (i, j) == (0, 2)) == []


def test_figure_of_eight_and_simple_loops():
    bow = [(0, 0, 0), (10, 10, 0), (10, 0, 0), (0, 10, 0)]
    hit = overlap.self_crossing(bow)
    assert hit is not None and np.allclose(hit, (5, 5, 0))
    assert overlap.self_crossing(circle(3)) is None
    assert overlap.self_crossing(square(0, 4)) is None


def test_sections_out_of_order_fold_back():
    assert overlap.folds_back([circle(5, 0), circle(5, 20), circle(5, 10)]) == 1
    assert overlap.folds_back([circle(5, 0), circle(5, 10), circle(5, 20)]) is None


def test_check_self_finds_a_bad_body_the_quick_checks_pass():
    p = Processor()
    # a pipe too fat for its bend, built before the checks existed: forge it
    # through the kernel directly, then ask CHECK
    from modeler.geometry import curves as cv
    from modeler.geometry import sweep as sw
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell

    p.run("ARC, 0,0,0, 5,5,0, 10,0,0")
    path = sw.as_wire(p.model.body(1).shape, "path")
    o, tan = sw.PathSampler(path).at(0)
    mk = BRepOffsetAPI_MakePipeShell(path)
    mk.Add(cv.circle(o, 8, tan), False, False)
    mk.Build()
    mk.MakeSolid()
    p.model.add_body(mk.Shape())
    assert "OK" in p.run("CHECK, 2").message
    msg = p.run("CHECK, 2, SELF").message
    assert "faces cut through each other" in msg
    assert "curve" in p.run("CHECK, 1, SELF").message  # a curve: nothing to test
