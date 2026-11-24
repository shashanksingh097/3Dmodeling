"""PLAN item 69: joints that stay solved (core/joints.py, commands/joint_handlers.py)."""

import math

import pytest

from modeler.commands import Processor
from modeler.core import joints as J


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def err(p, line):
    r = p.run(line)
    assert not r.ok, r.message
    return r.message


def face_at(p, x, y, z):
    ok(p, f"SEL, S, FACE, AT, {x}, {y}, {z}")
    return p.model.selection[0]


def bbox(p, b):
    return p.evaluate(f"BBOX({b})")


HINGE = """A = 30
BLOCK, 0,0,0, 40,30,5
NAME, LAST, base
BLOCK, 0,0,5, 40,30,2
NAME, LAST, lid
"""


def _hinge(p, extra=""):
    ok(p, HINGE)
    ok(p, "SEL, S, EDGE, LOC, Z, 5\nSEL, R, EDGE, LOC, X, 0\nSEL, R, EDGE, BODY, 1\nCM, e1, EDGE\n"
          "SEL, S, EDGE, LOC, Z, 5\nSEL, R, EDGE, LOC, X, 0\nSEL, R, EDGE, BODY, 2\nCM, e2, EDGE")
    a, b = p.model.named_set("e1")[1][0], p.model.named_set("e2")[1][0]
    return ok(p, f"JOINT, REVOLUTE, EDGE, {a}, EDGE, {b}, A{extra}")


def _lid_angle(p):
    j = p.model.joints[0]
    return J.value_of("REVOLUTE", j.a, j.b)


def test_hinge_holds_its_value_and_drives():
    p = Processor()
    r = _hinge(p, ", LIMITS, 0, 110")
    assert "J1: revolute joint" in r.message and "at 30 deg (held)" in r.message
    assert _lid_angle(p) == pytest.approx(30, abs=1e-6)
    top = bbox(p, 2)
    assert top.get('dz') > 2  # the lid stands up from the base
    ok(p, "DRIVE, A, 90")
    assert _lid_angle(p) == pytest.approx(90, abs=1e-6)
    ok(p, "DRIVE, A")
    assert _lid_angle(p) == pytest.approx(30, abs=1e-6)
    rep = ok(p, "JOINTS").report
    row = rep["joints"][0]
    assert row["kind"] == "REVOLUTE" and row["held"] == 30 and row["limits"] == [0, 110]
    assert row["free"] == "a turn about its axis" and not row["fights"]


def test_limits_are_reported_when_held_outside():
    p = Processor()
    ok(p, HINGE.replace("A = 30", "A = 150"))
    ok(p, "SEL, S, EDGE, LOC, Z, 5\nSEL, R, EDGE, LOC, X, 0\nSEL, R, EDGE, BODY, 1\nCM, e1, EDGE\n"
          "SEL, S, EDGE, LOC, Z, 5\nSEL, R, EDGE, LOC, X, 0\nSEL, R, EDGE, BODY, 2\nCM, e2, EDGE")
    a, b = p.model.named_set("e1")[1][0], p.model.named_set("e2")[1][0]
    r = ok(p, f"JOINT, REVOLUTE, EDGE, {a}, EDGE, {b}, A, LIMITS, 0, 110")
    assert "cannot all be true" in r.warning
    assert ok(p, "JOINTS").report["joints"][0]["fights"]


def test_free_hinge_follows_a_rotate_but_stays_on_its_axis():
    p = Processor()
    ok(p, HINGE)
    ok(p, "SEL, S, EDGE, LOC, Z, 5\nSEL, R, EDGE, LOC, X, 0\nSEL, R, EDGE, BODY, 1\nCM, e1, EDGE\n"
          "SEL, S, EDGE, LOC, Z, 5\nSEL, R, EDGE, LOC, X, 0\nSEL, R, EDGE, BODY, 2\nCM, e2, EDGE")
    a, b = p.model.named_set("e1")[1][0], p.model.named_set("e2")[1][0]
    ok(p, f"JOINT, REVOLUTE, EDGE, {a}, EDGE, {b}")
    ok(p, "ROTATE, lid, -40, 0,0,5, 0,1,0")  # a turn about the hinge: allowed, kept
    assert abs(_lid_angle(p)) == pytest.approx(40, abs=1e-5)
    ok(p, "MOVE, lid, 0, 0, 20")  # a lift off the hinge: pulled back
    j = p.model.joints[0]
    assert max(abs(v) for v in J.residuals(j, j.a, j.b)) < 1e-6
    assert abs(_lid_angle(p)) == pytest.approx(40, abs=0.05)  # the turn about the hinge stays


FOURBAR = """CYL, 0,0,0, 1, 1
CYL, 30,0,0, 1, 1
UNION, LAST, LAST-1
NAME, LAST, ground
CYL, 0,0,1, 1, 1
CYL, 0,10,1, 1, 1
UNION, LAST, LAST-1
NAME, LAST, crank
CYL, 0,10,2, 1, 1
CYL, 30,20,2, 1, 1
UNION, LAST, LAST-1
NAME, LAST, coupler
CYL, 30,0,3, 1, 1
CYL, 30,20,3, 1, 1
UNION, LAST, LAST-1
NAME, LAST, rocker
"""


def _fourbar(p, crank_value=""):
    ok(p, FOURBAR)
    g0, g1 = face_at(p, 1, 0, 0.5), face_at(p, 31, 0, 0.5)
    c0, c1 = face_at(p, 1, 0, 1.5), face_at(p, 1, 10, 1.5)
    k0, k1 = face_at(p, 1, 10, 2.5), face_at(p, 31, 20, 2.5)
    r0, r1 = face_at(p, 31, 0, 3.5), face_at(p, 31, 20, 3.5)
    ok(p, f"JOINT, REVOLUTE, FACE, {g0}, FACE, {c0}{crank_value}\n"
          f"JOINT, REVOLUTE, FACE, {c1}, FACE, {k0}\n"
          f"JOINT, REVOLUTE, FACE, {g1}, FACE, {r0}")
    return ok(p, f"JOINT, REVOLUTE, FACE, {r1}, FACE, {k1}")


def _pin(p, name, x, y, z):
    """Where a pin centre of a body is now (the body's nearest round face's axis point)."""
    from modeler.geometry import features as ft

    b = next(bd for bd in p.model.bodies.values() if bd.name == name)
    best = None
    for gid in b.entity_ids["FACE"]:
        ax = ft.face_axis(p.model.entity_shape("FACE", gid))
        if ax:
            d = math.dist(ax[0][:2], (x, y))
            if best is None or d < best[0]:
                best = (d, ax[0])
    return best[1]


def test_four_bar_loop_has_one_motion_and_follows_the_crank():
    p = Processor()
    r = _fourbar(p)
    assert "1 motion left free" in r.message and not r.warning
    ok(p, "ROTATE, crank, 20, 0,0,0, 0,0,1")
    rep = ok(p, "JOINTS").report
    assert rep["free"] == 1 and rep["solved"]
    assert all(not row["fights"] for row in rep["joints"])
    # the crank's far pin turned 20 degrees about the ground pin
    tip = _pin(p, "crank", -3.4, 9.4, 0)
    assert math.degrees(math.atan2(tip[1], tip[0])) == pytest.approx(110, abs=1e-3)
    # the coupler still joins the crank tip and the rocker tip (bar lengths kept)
    rk = _pin(p, "rocker", 30, 20, 0)
    assert math.dist(rk[:2], (30, 0)) == pytest.approx(20, abs=1e-4)


def test_four_bar_driven_by_a_parameter_rebuilds_after_an_edit():
    p = Processor()
    ok(p, "T = 0")
    _fourbar(p, ", T")
    ok(p, "DRIVE, T, 15")
    rep = ok(p, "JOINTS").report
    assert rep["solved"] and rep["joints"][0]["now"]["turn"] == pytest.approx(15, abs=1e-5)
    ok(p, "DRIVE, T")
    p.rebuild()
    assert all(e.ok for e in p.history)
    assert ok(p, "JOINTS").report["solved"]


def test_gear_coupling_turns_the_second_wheel():
    p = Processor()
    ok(p, "CYL, 0,0,0, 1, 1\nCYL, 30,0,0, 1, 1\nUNION, LAST, LAST-1\nNAME, LAST, frame\n"
          "CYL, 0,0,1, 10, 1\nNAME, LAST, w1\nCYL, 30,0,1, 20, 1\nNAME, LAST, w2")
    f0, f1 = face_at(p, 1, 0, 0.5), face_at(p, 31, 0, 0.5)
    a, b = face_at(p, 10, 0, 1.5), face_at(p, 50, 0, 1.5)
    ok(p, f"JOINT, REVOLUTE, FACE, {f0}, FACE, {a}\nJOINT, REVOLUTE, FACE, {f1}, FACE, {b}")
    r = ok(p, "JOINT, GEAR, J1, J2, 0.5")
    assert "J3: gear J1 and J2" in r.message
    ok(p, "ROTATE, w1, 40, 0,0,0, 0,0,1")
    rows = {r["name"]: r for r in ok(p, "JOINTS").report["joints"]}
    q1, q2 = rows["J1"]["now"]["turn"], rows["J2"]["now"]["turn"]
    assert abs(q1) == pytest.approx(40, abs=1e-3) and q2 == pytest.approx(-0.5 * q1, abs=1e-3)


def test_slider_and_rack():
    p = Processor()
    ok(p, "BLOCK, -50,-2,-2, 100, 4, 1\nNAME, LAST, rail\nBLOCK, -5,-2,0, 10, 4, 3\nNAME, LAST, car")
    rail_top, car_bottom = face_at(p, 30, 0, -1), face_at(p, 0, 0, 0)
    r = ok(p, f"JOINT, SLIDER, FACE, {rail_top}, FACE, {car_bottom}, 12")
    assert "at 12 (held)" in r.message
    x0 = bbox(p, "car").get("xmin")
    assert abs(x0 - (-5)) == pytest.approx(12, abs=1e-6) or abs(x0 + 5) < 1e-6
    rows = ok(p, "JOINTS").report["joints"]
    assert rows[0]["now"]["slide"] == pytest.approx(12, abs=1e-6)


def test_errors_say_what_is_wrong():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 10,10,10\nBLOCK, 20,0,0, 10,10,10")
    assert "same body" in err(p, "JOINT, REVOLUTE, FACE, 1, FACE, 2")
    assert "kind is one of" in err(p, "JOINT, WOBBLY, FACE, 1, FACE, 7")
    assert "no joint J9" in err(p, "JOINT, GEAR, J9, J8, 2")
    assert "takes no value" in err(p, "JOINT, FIXED, FACE, 1, FACE, 7, 5")
    assert ok(p, "JOINTS").message.startswith("no joints")


def test_solver_alone_on_frames():
    a = J.frame((0, 0, 0), (0, 0, 1), (1, 0, 0))
    j = J.Joint("J1", "CYLINDRICAL", 1, 2, a, a, value=45)
    got = J.solve([j])
    assert got.ok and got.free == 2
    b = got.moves[2].frame(a)
    assert J.measure("CYLINDRICAL", a, b)["turn"] == pytest.approx(45)
    ball = J.Joint("J1", "BALL", 1, 2, a, J.frame((1, 1, 1), (0, 0, 1)))
    got = J.solve([ball])
    assert got.ok and got.free == 3


def test_positive_opens_the_lid_and_motion_is_clear():
    p = Processor()
    rs = p.run_script("A = 60\nBLOCK, 0,0,0, 40,30,10\nBLOCK, 0,0,10, 40,30,2\n"
                      "JOINT, REVOLUTE, EDGE, 2, EDGE, 16, A, LIMITS, 0, 110\nMOTION, A, 0, 110, 11")
    assert all(r.ok for r in rs), [r.message for r in rs if not r.ok]
    assert "no parts run into each other" in rs[-1].message
    assert bbox(p, 2).get("zmin") == pytest.approx(10, abs=1e-6)  # up, not into the box
