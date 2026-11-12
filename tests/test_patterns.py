"""ARRAY ... CUT, PATTERN (feature patterns), and cancelling a long rebuild."""

import math
import time

import pytest

from modeler.commands import Processor
from modeler.gui import forms as F

PLATE = "BLOCK, 0,0,0, 100,60,10\nNAME, LAST, plate\n"


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


def hole_vol(r, h=10):
    return math.pi * r * r * h


# ---- ARRAY ... CUT ------------------------------------------------------------------

def test_array_cut_makes_a_grid_of_holes_in_one_step(p):
    ok(p, PLATE + "CYL, 10,10,-1, 2, 12\nNAME, LAST, pin")
    r = ok(p, "ARRAY, LINEAR, pin, 9, 10,0,0, 5, 0,10,0, CUT, plate")
    assert "45 copies" in r.message and "one step" in r.message
    assert p.evaluate("VOL(plate)") == pytest.approx(60000 - 45 * hole_vol(2), rel=1e-9)
    assert p.evaluate("COUNT()") == 1  # the tool is used up, as with SUBTRACT


def test_array_cut_polar_and_path_and_keep(p):
    ok(p, "CYL, 0,0,0, 40, 8\nNAME, LAST, disc\nCYL, 30,0,-1, 3, 10\nKEEP, ON")
    ok(p, "ARRAY, POLAR, LAST, 8, CUT, disc")
    assert p.evaluate("VOL(disc)") == pytest.approx(math.pi * 1600 * 8 - 8 * hole_vol(3, 8), rel=1e-9)
    assert p.evaluate("COUNT()") == 2  # with KEEP, ON the tool stays, hidden
    ok(p, "KEEP, OFF\n" + PLATE + "LINE, 10,30,0, 90,30,0\nCYL, 10,30,-1, 1, 12\n"
          "ARRAY, PATH, LAST, LAST-1, 5, CUT, plate")
    assert p.evaluate("VOL(plate)") == pytest.approx(60000 - 5 * hole_vol(1), rel=1e-9)


def test_array_cut_errors(p):
    ok(p, PLATE + "CYL, 10,10,-1, 2, 12")
    assert "CUT needs" in err(p, "ARRAY, LINEAR, LAST, 3, 10,0,0, CUT")
    assert "not both" in err(p, "ARRAY, LINEAR, LAST, 3, 10,0,0, FUSE, CUT, plate")
    assert "cannot be the body" in err(p, "ARRAY, LINEAR, plate, 3, 10,0,0, CUT, plate")


# ---- PATTERN --------------------------------------------------------------------------

def test_pattern_repeats_a_hole_in_a_grid(p):
    ok(p, PLATE + "HOLE, plate, 10,10,10, 4")
    r = ok(p, "PATTERN, LINEAR, plate, 1, 9, 10,0,0, 5, 0,10,0")
    assert "45 copies" in r.message and "removed material" in r.message
    assert p.evaluate("VOL(plate)") == pytest.approx(60000 - 45 * hole_vol(2), rel=1e-9)


def test_pattern_follows_an_edit_of_the_feature(p):
    ok(p, PLATE + "HOLE, plate, 10,10,10, 4\nPATTERN, LINEAR, plate, 1, 9, 10,0,0")
    t = time.time()
    p.run('HIST, EDIT, 3, "HOLE, plate, 10,10,10, 6"')
    assert time.time() - t < 5
    assert p.evaluate("VOL(plate)") == pytest.approx(60000 - 9 * hole_vol(3), rel=1e-9)


def test_pattern_of_several_steps_adds_and_removes(p):
    # a boss with a hole through it, repeated round a flange
    ok(p, "CYL, 0,0,0, 40, 5\nNAME, LAST, fl\nCYL, 30,0,5, 3, 4\nUNION, fl, LAST\nHOLE, fl, 30,0,9, 2")
    v1 = p.evaluate("VOL(fl)") - math.pi * 1600 * 5  # what one boss with its hole adds
    r = ok(p, "PATTERN, POLAR, fl, 3, 6")
    assert "added material and removed material" in r.message
    assert p.evaluate("VOL(fl)") == pytest.approx(math.pi * 1600 * 5 + 6 * v1, rel=1e-9)


def test_pattern_keeps_face_ids_of_the_body(p):
    ok(p, PLATE + "HOLE, plate, 10,10,10, 4")
    bid = p.evaluate("BODY('plate')")
    before = set(p.model.body(bid).entity_ids["FACE"])
    ok(p, "PATTERN, LINEAR, plate, 1, 3, 20,0,0")
    after = set(p.model.body(p.evaluate("BODY('plate')")).entity_ids["FACE"])
    assert before <= after and len(after - before) == 2  # two new hole walls


def test_pattern_errors(p):
    ok(p, PLATE)
    assert "only 2 steps" in err(p, "PATTERN, LINEAR, plate, 5, 3, 10,0,0")
    assert "did not change" in err(p, "SEL, NONE\nPATTERN, LINEAR, plate, 1, 3, 10,0,0")
    assert "did not exist" in err(p, "CYL, 0,0,0, 1, 1\nPATTERN, LINEAR, LAST, 1, 3, 10,0,0")
    assert "LINEAR or POLAR" in err(p, "PATTERN, PATH, plate, 1, 3")
    assert "whole number" in err(p, "PATTERN, LINEAR, plate, 0, 3, 10,0,0")


# ---- cancelling a rebuild ---------------------------------------------------------------

def test_cancelled_rebuild_leaves_everything_as_it_was(p):
    ok(p, "W = 10\nBLOCK, 0,0,0, W,W,W\nCYL, 0,0,0, 1, 20\nSUBTRACT, LAST-1, LAST")
    v = p.evaluate("VOL(LAST)")
    texts = [e.text for e in p.history]
    seen = []

    def stop_at_third(done, total, label):
        seen.append((done, total, label))
        return done < 2

    p.progress = stop_at_third
    r = p.run('HIST, EDIT, 1, "W = 20"')
    p.progress = None
    assert not r.ok and "cancelled" in r.message
    assert [s[0] for s in seen] == [0, 1, 2] and seen[0][1] == 4
    assert [e.text for e in p.history] == texts
    assert p.evaluate("W") == 10 and p.evaluate("VOL(LAST)") == pytest.approx(v)
    ok(p, "SPHERE, 50,0,0, 2")  # still usable
    assert p.cursor == 5


def test_progress_is_called_for_each_step_and_can_let_it_finish(p):
    ok(p, "W = 10\nBLOCK, 0,0,0, W,W,W\nMOVE, LAST, 1,0,0")
    calls = []
    p.progress = lambda d, t, label: calls.append(label) or True
    ok(p, 'HIST, EDIT, 1, "W = 20"')
    assert calls == ["W = 20", "BLOCK, 0,0,0, W,W,W", "MOVE, LAST, 1,0,0"]
    assert p.evaluate("VOL(LAST)") == pytest.approx(8000)


# ---- forms -------------------------------------------------------------------------

def test_forms_for_array_cut_and_pattern(p):
    sp = F.spec("ARRAY")
    text = F.build(sp, {"b": "pin", "n": "9", "d": "10, 0, 0", "cut": "plate"}, "LINEAR")
    assert text == "ARRAY, LINEAR, pin, 9, 10, 0, 0, CUT, plate"
    assert F.parse(text)[2]["cut"] == "plate"
    sp = F.spec("PATTERN")
    text = F.build(sp, {"b": "plate", "steps": "1", "n": "4", "d": "20, 0, 0"}, "LINEAR")
    assert text == "PATTERN, LINEAR, plate, 1, 4, 20, 0, 0"
    ok(p, PLATE + "HOLE, plate, 10,10,10, 4\n" + text)
