"""PLAN item 108: UPTO moves a body, or pulls picked faces, up to another face, edge or vertex."""

import pytest

from modeler.commands import Processor
from modeler.commands.upto_handlers import _extent
from modeler.geometry import recognize as rc


def ok(p, text):
    r = None
    for line in text.strip().splitlines():
        r = p.run(line.strip())
        assert r.ok, (line, r.message)
    return r


def face_at(p, bid, z):
    m = p.model
    for g in m.bodies[bid].entity_ids["FACE"]:
        q, n = rc.face_normal_at_middle(m.entity_shape("FACE", g))
        if abs(q[2] - z) < 1e-6 and abs(n[2]) > 0.99:
            return g
    raise AssertionError("no such face")


def setup():
    p = Processor()
    ok(p, """BLOCK, 0, 0, 0, 10, 10, 10
NAME, LAST, box
BLOCK, 0, 0, 50, 40, 40, 5
NAME, LAST, shelf
CYL, 100, 0, 0, 5, 10
NAME, LAST, peg""")
    return p, face_at(p, 2, 50)


def test_body_up_to_a_face_along_its_normal_and_an_axis():
    p, under = setup()
    r = ok(p, f"UPTO, box, FACE, {under}")  # the face's normal points down: the box goes up to it
    assert r.message.startswith("moved by (0, 0, 40) up to face")
    assert _extent(p.model.body(1).shape, (0, 0, 1)) == pytest.approx((40, 50))
    peg = p.model.body_by_name("peg").id
    ok(p, f"UPTO, peg, FACE, {under}, Z, 1")  # stops 1 short; round sides count exactly
    assert _extent(p.model.body(peg).shape, (0, 0, 1)) == pytest.approx((39, 49))
    ok(p, "UPTO, peg, VERTEX, 1, X")  # back along X: its low side to the vertex
    assert _extent(p.model.body(peg).shape, (1, 0, 0))[0] == pytest.approx(0)


def test_picked_faces_pull_up_to_a_face():
    p, under = setup()
    ok(p, f"PICK, FACE, {face_at(p, 1, 10)}")
    r = ok(p, f"UPTO, SEL, FACE, {under}, , 2")
    assert "pulled 38" in r.message
    assert _extent(p.model.body(1).shape, (0, 0, 1)) == pytest.approx((0, 48))
    ok(p, "UNDO")
    ok(p, f"UPTO, FACES {face_at(p, 1, 10)}, FACE, {under}")  # named instead of picked
    assert _extent(p.model.body(1).shape, (0, 0, 1)) == pytest.approx((0, 50))


def test_errors():
    p, under = setup()
    for bad, says in [("UPTO, box, FACE, 99999", "no face"), ("UPTO, box, EDGE, 1", "give the axis"),
                      ("UPTO, box, FACE, 1, W", "axis"), ("UPTO, nobody, FACE, 1", "not a body"),
                      ("UPTO, box, CORNER, 1", "FACE, EDGE or VERTEX")]:
        r = p.run(bad)
        assert not r.ok and says in r.message, (bad, r.message)
    ok(p, f"UPTO, box, FACE, {under}")
    r = p.run(f"UPTO, box, FACE, {under}")
    assert not r.ok and "level with" in r.message
