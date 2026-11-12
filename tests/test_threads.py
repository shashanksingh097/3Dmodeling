"""THREAD (helical ISO metric threads, outside and inside) and SPRING."""

import math
import os

import pytest

from modeler.commands import Processor
from modeler.geometry import threads as th
from modeler.gui import forms as F

TAN30 = math.tan(math.radians(30))


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


def vol(p, b):
    return p.evaluate(f"VOL({b})")


def groove_volume(major, pitch, length, outside=True, wall=None):
    """Volume a thread takes out over ``length``: the groove section turned round
    the axis (Pappus), once per pitch."""
    rmaj = major / 2
    if outside:
        r0, r1, w = rmaj - th.ROOT_EXT * pitch, rmaj, lambda r: 7 / 8 * pitch - 2 * (rmaj - r) * TAN30
    else:
        r0, r1, w = wall / 2, rmaj, lambda r: pitch / 8 + 2 * (rmaj - r) * TAN30
    n = 2000
    dr = (r1 - r0) / n
    per_turn = sum(2 * math.pi * (r0 + (i + 0.5) * dr) * w(r0 + (i + 0.5) * dr) * dr for i in range(n))
    return per_turn * length / pitch


def test_outside_thread_on_a_free_shaft(p):
    ok(p, "CYL, 0, 0, 0, 4, 30\nSEL, S, FACE, AT, 4, 0, 15")
    r = ok(p, "THREAD")
    assert "M8 outside thread (pitch 1.25, minor diameter 6.466) on face" in r.message
    assert "the whole length" in r.message
    removed = math.pi * 16 * 30 - vol(p, 1)
    assert removed == pytest.approx(groove_volume(8, 1.25, 30), rel=0.01)
    assert "OK" in p.run("CHECK, 1").message
    assert p.model.last_body == 1  # same body, same ID


def test_inside_thread_in_a_tap_drilled_hole(p):
    ok(p, "BLOCK, -10, -10, -12, 20, 20, 12\nNAME, LAST, plate\nHOLE, plate, 0, 0, 0, 6.8")
    before = vol(p, "plate")
    ok(p, "SEL, S, FACE, AT, 3.4, 0, -6")
    r = ok(p, "THREAD")
    assert "M8 inside thread (pitch 1.25" in r.message
    removed = before - vol(p, "plate")
    assert removed == pytest.approx(groove_volume(8, 1.25, 12, outside=False, wall=6.8), rel=0.02)


def test_a_thread_stops_before_a_head_and_runs_out_past_a_chamfer(p):
    ok(p, "CYL, 0, 0, 0, 8, 5\nCYL, 0, 0, -30, 4, 30\nUNION, 1, 2\n"
          "SEL, S, EDGE, AT, 0, 4, -30\nCHAMFER, 0.8\nSEL, S, FACE, AT, 4, 0, -15")
    head = math.pi * 64 * 5
    r = ok(p, "THREAD, , 20")
    assert "20 from the free end" in r.message
    b = p.model.last_body
    # the length counts from where the chamfer starts (z = -29.2): nothing above -9.2 was cut
    ok(p, "PLANE, cut, XY, -9.19")
    ok(p, f"SPLIT, {b}, cut, ABOVE")
    assert vol(p, b) == pytest.approx(head + math.pi * 16 * 9.19, rel=1e-6)


def test_a_full_length_thread_under_a_head_stays_out_of_it(p):
    ok(p, "CYL, 0, 0, 0, 8, 5\nCYL, 0, 0, -30, 4, 30\nUNION, 1, 2\nSEL, S, FACE, AT, 4, 0, -15\nTHREAD")
    b = p.model.last_body
    ok(p, f"PLANE, cut, XY, 0\nSPLIT, {b}, cut, ABOVE")
    assert vol(p, b) == pytest.approx(math.pi * 64 * 5, rel=1e-6)


def test_pitch_hand_and_sizes_that_are_not_iso(p):
    ok(p, "CYL, 0, 0, 0, 5, 20\nSEL, S, FACE, AT, 5, 0, 10")
    assert "M10x1 left-hand outside thread" in ok(p, "THREAD, 1, , LEFT").message
    ok(p, "CYL, 20, 0, 0, 3.7, 20\nSEL, S, FACE, AT, 23.7, 0, 10")
    assert "not an ISO metric size; give the pitch" in err(p, "THREAD")
    assert "M7.4x0.75 outside" in ok(p, "THREAD, 0.75").message
    ok(p, "BLOCK, 40, -10, 0, 20, 20, 10\nHOLE, LAST, 50, 0, 10, 9")
    ok(p, "SEL, S, FACE, AT, 54.5, 0, 5")
    assert "not drilled for an ISO metric size" in err(p, "THREAD")
    r = ok(p, "THREAD, 1.5")  # the hole is then the minor diameter
    assert f"M{9 + 2 * th.INT_DEPTH * 1.5:.4g}x1.5 inside" in r.message


def test_what_cannot_be_threaded(p):
    ok(p, "BLOCK, 0, 0, 0, 10, 10, 10")
    assert "select the round face" in err(p, "THREAD")
    ok(p, "SEL, S, FACE, AT, 5, 5, 10")
    assert "pick a cylindrical face" in err(p, "THREAD")
    ok(p, "CYL, 100, 0, 0, 4, 20\nSEL, S, FACE, AT, 104, 0, 10")
    assert "shorter than one pitch" in err(p, "THREAD, , 1")
    ok(p, "SEL, S, FACE, AT, 104, 0, 10")
    assert "cannot be negative" in err(p, "THREAD, -1")


def test_no_free_end(p):
    ok(p, "CYL, 0, 0, 0, 8, 5\nCYL, 0, 0, 5, 4, 10\nCYL, 0, 0, 15, 8, 5\nUNION, 1, 2, 3\nSEL, S, FACE, AT, 4, 0, 10")
    assert "neither end of the face is free" in err(p, "THREAD")


def test_pitch_function(p):
    assert p.evaluate("PITCH(8)") == 1.25
    assert p.evaluate("PITCH(12)") == 1.75
    assert not p.run("X = PITCH(7.3)").ok


def test_threaded_bolts_and_nuts_placed_8_times(p):
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "..", "scripts", "threaded_bolts.cmd"), encoding="utf-8") as fh:
        ok(p, fh.read())
    listing = p.run("LIST, PARTS").message
    assert "bolt(D=8, L=30, K=0.7*D, B=2*D+6): 8 instances" in listing
    assert "nut(D=8, M=0.8*D): 8 instances" in listing
    assert len(p.part_cache) == 2  # each part built once, then copied
    bolts = [b for b, (name, _) in p.model.instances.items() if name.upper() == "BOLT"]
    v8 = {round(vol(p, b), 6) for b in bolts}
    assert len(v8) == 1
    assert p.run('HIST, EDIT, 1, "D = 10"').ok
    bolts = [b for b, (name, _) in p.model.instances.items() if name.upper() == "BOLT"]
    assert len(bolts) == 8
    v10 = {round(vol(p, b), 6) for b in bolts}
    assert len(v10) == 1 and v10 != v8
    assert len(p.part_cache) == 4


def test_springs(p):
    r = ok(p, "SPRING, 0, 0, 0, 10, 6, 8, 1.5")
    assert "free height 49.5" in r.message
    wire = math.pi * 0.75 ** 2 * 8 * math.hypot(2 * math.pi * 10, 6)
    assert vol(p, 1) == pytest.approx(wire, rel=0.01)
    assert p.evaluate("BBOX(1).zmax") == pytest.approx(48 + 0.75, abs=0.05)
    r = ok(p, "SPRING, 40, 0, 0, 10, 5, 10, 2, , , , , 1, GROUND")
    assert "1 closed turn at each end, ends ground" in r.message
    b = p.model.last_body
    assert p.evaluate(f"BBOX({b}).zmin") == pytest.approx(1, abs=1e-3)  # half a wire ground off
    assert "OK" in p.run(f"CHECK, {b}").message
    ok(p, "SPRING, 80, 0, 0, 6, 3, 6, 1, 1, 0, 0, LEFT")
    b = p.model.last_body
    assert p.evaluate(f"BBOX({b}).xmax") == pytest.approx(80 + 18 + 0.5, abs=0.05)
    assert "clear the wire" in err(p, "SPRING, 0, 0, 0, 10, 1, 8, 1.5")
    assert "thicker than the coil" in err(p, "SPRING, 0, 0, 0, 1, 6, 8, 3")
    assert "fewer than half" in err(p, "SPRING, 0, 0, 0, 10, 6, 4, 1, , , , , 2")


def test_spring_on_the_work_plane(p):
    ok(p, "PLANE, side, YZ, 100\nWORKPLANE, side\nSPRING, 0, 0, 0, 5, 3, 4, 1")
    assert p.evaluate("BBOX(1).xmin") == pytest.approx(100 - 0.5, abs=0.05)


def test_forms(p):
    sp = F.spec("SPRING")
    vals = F.initial(p, sp)
    assert F.check(p, sp, vals) == ("SPRING, 0, 0, 0, 10, 5, 8, 1.5", {})
    vals.update(closed="1", finish="GROUND")
    text, problems = F.check(p, sp, vals)
    assert (text, problems) == ("SPRING, 0, 0, 0, 10, 5, 8, 1.5, , , , RIGHT, 1, GROUND", {})
    ok(p, text)
    sp = F.spec("THREAD")
    vals = F.initial(p, sp)
    assert F.check(p, sp, vals)[0] == "THREAD"
    vals.update(pitch="1", hand="LEFT")
    assert F.check(p, sp, vals)[0] == "THREAD, 1, , LEFT"
    assert F.parse("THREAD, 1, , LEFT")[2]["hand"] == "LEFT"
