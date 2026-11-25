"""More kinds of pattern (PLAN item 97): CURVE, POINTS, FILL, MIRROR, SKIP, the report, the form
and leaving a copy out from the right-click menu."""

import math

import pytest

from modeler.commands.processor import Processor
from modeler.core.model import Model
from modeler.geometry import robust


def run(p, text):
    for line in text.strip().splitlines():
        r = p.run(line.strip())
        assert r.ok, (line, r.message)
    return r


def err(p, line):
    r = p.run(line)
    assert not r.ok, r.message
    return r.message


@pytest.fixture
def p():
    return Processor(Model())


HOLE = math.pi * 1 * 5  # a hole 2 across through a plate 5 thick


def vol(p):
    return robust.volume(p.model.body_by_name("plate").shape)


def plate(p, w=100, h=60):
    run(p, f"BLOCK, 0,0,0, {w},{h},5\nNAME, LAST, plate\nHOLE, plate, 10,10,5, 2")


def test_fill_grid_and_staggered(p):
    plate(p)
    top = p.model.body_by_name("plate")
    run(p, "SEL, S, FACE, NORMAL, 0,0,1")
    face = p.model.selection[0]
    run(p, "SEL, NONE")  # (the plate's own steps: HOLE, then two picks: PATTERN, ..., 3)
    run(p, f"PATTERN, FILL, plate, 3, {face}, 8, 2")
    d = p.reports["PATTERN"]
    # middles 10, 18 ... 90 across (11) and 10 ... 50 up (6), at least 2 + 2 (radius) from every edge
    assert len(d["copies"]) == 66 and d["kind"] == "FILL"
    assert all(3 - 1e-9 <= c["at"][0] <= 97 and 3 - 1e-9 <= c["at"][1] <= 57 for c in d["copies"])
    assert vol(p) == pytest.approx(100 * 60 * 5 - 66 * HOLE, rel=1e-6)
    run(p, "UNDO")
    run(p, f"PATTERN, FILL, plate, 3, {face}, 8, 2, HEX")
    rows = sorted({round(c["at"][1], 6) for c in p.reports["PATTERN"]["copies"]})
    assert rows[1] - rows[0] == pytest.approx(8 * math.sqrt(3) / 2)
    assert top is not None


def test_fill_keeps_off_holes_in_the_face(p):
    run(p, "BLOCK, 0,0,0, 60,60,5\nNAME, LAST, plate\nCYL, 30,30,0, 10, 5\nSUBTRACT, plate, LAST\nNAME, LAST, plate"
           "\nHOLE, plate, 5,5,5, 1")
    run(p, "SEL, S, FACE, NORMAL, 0,0,1")
    face = p.model.selection[0]
    run(p, f"PATTERN, FILL, plate, 2, {face}, 5, 1")
    assert len(p.reports["PATTERN"]["copies"]) > 50
    for c in p.reports["PATTERN"]["copies"]:
        assert math.dist(c["at"][:2], (30, 30)) >= 10 + 1 + 0.5 - 1e-6  # big hole + margin + small radius
    run(p, "UNDO")
    assert "spacing" in err(p, f"PATTERN, FILL, plate, 2, {face}, 0")


def test_curve_points_mirror(p):
    run(p, "SPLINE, (10,10,5), (40,40,5), (90,20,5)\nNAME, LAST, path\nPLANE, mid, YZ, 50")
    plate(p)
    run(p, "PATTERN, CURVE, plate, 1, path, 6")
    at = [c["at"] for c in p.reports["PATTERN"]["copies"]]
    assert at[-1][:2] == pytest.approx([90, 20]) and len(at) == 6
    assert vol(p) == pytest.approx(100 * 60 * 5 - 6 * HOLE, rel=1e-6)
    run(p, "UNDO\nPATTERN, CURVE, plate, 1, path, 6, TURN")
    assert vol(p) == pytest.approx(100 * 60 * 5 - 6 * HOLE, rel=1e-4)
    run(p, "UNDO\nPATTERN, POINTS, plate, 1, (10,10,5), (30,10,5), (50,40,5)")
    assert [c["at"][:2] for c in p.reports["PATTERN"]["copies"]] == [[10, 10], [30, 10], [50, 40]]
    assert vol(p) == pytest.approx(100 * 60 * 5 - 3 * HOLE, rel=1e-6)
    run(p, "UNDO\nPATTERN, MIRROR, plate, 1, mid")
    assert p.reports["PATTERN"]["copies"][1]["at"][:2] == pytest.approx([90, 10])
    assert vol(p) == pytest.approx(100 * 60 * 5 - 2 * HOLE, rel=1e-6)


def test_points_from_a_sketch(p):
    run(p, "SKETCH, s, XY\nSPOINT, 10, 10\nSPOINT, 50, 30\nSPOINT, 80, 30\nENDSKETCH")
    plate(p)
    run(p, "PATTERN, POINTS, plate, 1, s")  # the point under the hole is the hole itself
    assert len(p.reports["PATTERN"]["copies"]) == 3
    assert vol(p) == pytest.approx(100 * 60 * 5 - 3 * HOLE, rel=1e-6)


def test_skip(p):
    plate(p)
    run(p, "PATTERN, LINEAR, plate, 1, 5, 15,0,0, SKIP, 2, 4")
    d = p.reports["PATTERN"]
    assert d["skipped"] == [2, 4] and [c.get("skipped", False) for c in d["copies"]] == [False, True, False, True, False]
    assert vol(p) == pytest.approx(100 * 60 * 5 - 3 * HOLE, rel=1e-6)
    assert "SKIP" in err(p, "PATTERN, LINEAR, plate, 1, 3, 15,0,0, SKIP")
    assert "only 3 copies" in err(p, "PATTERN, LINEAR, plate, 2, 3, 0,15,0, SKIP, 7")
    assert "1 is the original" in err(p, "PATTERN, LINEAR, plate, 2, 3, 0,15,0, SKIP, 1")


def test_right_click_leaves_a_copy_out(p):
    from modeler.gui import body_menu as bm

    plate(p)
    run(p, "PATTERN, LINEAR, plate, 1, 4, 20,0,0")
    b = p.model.body_by_name("plate").id
    # pick the wall of the third hole (at x = 50)
    walls = [f for f in p.model.body(b).entity_ids["FACE"]
             if abs(p.evaluate(f"AREA({f})") - 2 * math.pi * 1 * 5) < 1e-6]
    third = next(f for f in walls if abs(_centre_x(p, f) - 50) < 1e-6)
    run(p, f"PICK, FACE, {third}")
    items = bm.body_items(p.model, b, {}, p)
    item = next(i for i in items if i.label.startswith("Leave out copy"))
    assert item.label == "Leave out copy 3 of the pattern"
    assert item.commands == ['HIST, EDIT, 4, "PATTERN, LINEAR, plate, 1, 4, 20, 0, 0, SKIP, 3"']
    run(p, item.commands[0])
    assert vol(p) == pytest.approx(100 * 60 * 5 - 3 * HOLE, rel=1e-6)
    assert p.reports["PATTERN"]["skipped"] == [3]


def _centre_x(p, f):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(p.model.entity_shape("FACE", f), g)
    return g.CentreOfMass().X()


def test_form_round_trip():
    from modeler.gui import forms

    for line in ("PATTERN, FILL, plate, 1, 6, 8, 2, HEX, SKIP, 3, 5",
                 "PATTERN, CURVE, plate, 1, path, 6, TURN",
                 "PATTERN, POINTS, plate, 1, (10, 10, 5), (30, 10, 5)",
                 "PATTERN, MIRROR, plate, 1, mid",
                 "PATTERN, LINEAR, plate, 1, 4, 20, 0, 0, SKIP, 2"):
        sp, variant, values = forms.parse(line)
        again = forms.build(sp, values, variant)
        assert again.replace(" ", "") == line.replace(" ", ""), (line, again)
