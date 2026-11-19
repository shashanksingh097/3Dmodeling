"""Assembly checks (PLAN item 60): MATES finds mates that repeat or fight and names them, and lists
the ways each copy can still move; CSYS makes coordinate systems that move with a body, and
MATE, FRAME puts one on another. Also checked after saving and opening the project."""

import json

import pytest

from modeler.commands import Processor

# body 1 'base' (40 x 40 x 10, a hole r 5 at (20, 20)); body 2 'pin' (r 5, 20 long) away from it.
# faces: base top 6 (z 10, +z); pin bottom 9 (z 0, -z), pin side 7 (cylinder)
SETUP = """BLOCK, 0,0,0, 40, 40, 10
NAME, LAST, base
CYL, 100,0,0, 5, 20
NAME, LAST, pin"""


@pytest.fixture
def p():
    q = Processor()
    ok(q, SETUP)
    return q


def ok(p, text):
    res = p.run_script(text)
    bad = [r for r in res if not r.ok]
    assert not bad, f"{bad[0].line}: {bad[0].message}"
    return res[-1]


def report(p):
    return json.loads(p.run("MATES, JSON").message)


def free(d, body=2):
    return next(b for b in d["bodies"] if b["body"] == body)["free"]


def test_face_on_face_leaves_two_slides_and_a_turn(p):
    ok(p, "MATE, COINCIDENT, FACE, 6, FACE, 9")
    d = report(p)
    assert d["mates"][0]["holds"] and d["mates"][0]["fixes"] == 3
    f = free(d)
    assert sorted(x["kind"] for x in f) == ["slide", "slide", "turn"]
    turn = next(x for x in f if x["kind"] == "turn")
    assert abs(turn["about"][2]) == pytest.approx(1)
    assert all(x["along"][2] == pytest.approx(0) for x in f if x["kind"] == "slide")
    assert d["grounded"] == [1]


def test_a_pin_in_a_hole_can_only_turn(p):
    ok(p, "CYL, 20,20,-1, 5, 12\nSUBTRACT, base, LAST")
    side = [g for g in p.model.bodies[p.model.body_by_name("base").id].entity_ids["FACE"]
            if p.model.entity_shape("FACE", g) is not None]
    hole = next(g for g in side if _is_cyl(p, g))
    ok(p, f"MATE, CONCENTRIC, FACE, {hole}, FACE, 7\nMATE, COINCIDENT, FACE, 6, FACE, 9")
    f = free(report(p), p.model.body_by_name("pin").id)
    assert len(f) == 1 and f[0]["kind"] == "turn" and abs(f[0]["about"][2]) == pytest.approx(1)
    assert f[0]["through"][:2] == pytest.approx([20, 20])
    assert "1 way to move: turns about" in p.run("MATES").message


def _is_cyl(p, g):
    from modeler.core.refs import _describe

    return _describe("FACE", p.model.entity_shape("FACE", g))["type"] == "CYLINDER"


def test_a_mate_that_repeats_is_named(p):
    ok(p, "MATE, COINCIDENT, FACE, 6, FACE, 9")
    r = p.run("MATE, COINCIDENT, FACE, 6, FACE, 9")
    assert "repeats" in r.warning
    d = report(p)
    assert d["mates"][1]["repeats"] == [5] and d["mates"][1]["new"] == 0 and d["repeats"] == 1
    assert "REPEATS step 5 (fixes nothing new)" in p.run("MATES").message


def test_mates_that_fight_are_named(p):
    ok(p, "MATE, COINCIDENT, FACE, 6, FACE, 9")
    r = p.run("MATE, DISTANCE, FACE, 6, FACE, 9, 5")
    assert "undoes step 5" in r.warning
    d = report(p)
    first, second = d["mates"]
    assert not first["holds"] and first["undone_by"] == [6] and first["error"] == pytest.approx(5)
    assert second["holds"] and second["fights"] == [5] and d["fights"] == 1
    msg = p.run("MATES").message
    assert "DOES NOT HOLD (off by 5): undone by step 6" in msg and "FIGHTS step 5" in msg


def test_coordinate_systems_follow_their_body_and_mate_fully(p, tmp_path):
    ok(p, "CSYS, top, base, 20,20,10\nCSYS, foot, pin, 100,0,0, 0,0,-1")
    ok(p, "MOVE, pin, 0, 0, 5")
    assert p.model.datums["FOOT"].origin == pytest.approx((100, 0, 5))  # moved with the pin
    ok(p, "MATE, FRAME, top, foot, FLIP")
    assert p.model.datums["FOOT"].origin == pytest.approx((20, 20, 10))
    assert p.model.datums["FOOT"].z == pytest.approx((0, 0, -1))
    # the pin now stands on the top face, upwards
    from modeler.core.refs import _describe

    c = _describe("BODY", p.model.body_by_name("pin").shape)["c"]
    assert c == pytest.approx([20, 20, 20])
    d = report(p)
    assert free(d) == [] and "fully placed" in p.run("MATES").message
    assert "foot: on body 2" in p.run("CSYS").message
    path = str(tmp_path / "a.m3d")
    ok(p, f'SAVE, "{path}"')
    q = Processor()
    ok(q, f'OPEN, "{path}"')
    assert q.model.datums["FOOT"].origin == pytest.approx((20, 20, 10))
    assert report(q)["mates"][0]["holds"]


def test_csys_on_a_face_and_refusals(p):
    msg = p.run("CSYS, f6, FACE, 6, 90").message
    assert "coordinate system f6" in msg and p.model.frames["F6"] == 1
    assert p.model.datums["F6"].x == pytest.approx((0, 1, 0))
    assert "not on a body" in p.run("CSYS, world, 0, 0,0,0\nMATE, FRAME, f6, world").message
    assert "same body" in p.run("CSYS, f5, FACE, 5\nMATE, FRAME, f6, f5").message
    assert p.run("MATES").message.startswith("no mates")
