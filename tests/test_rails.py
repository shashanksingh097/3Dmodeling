"""RAILSWEEP: sweeps steered by one or two rails."""

import math
import os

import pytest

from modeler.commands import Processor
from modeler.gui import forms as F


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


def box(p, b, k):
    return p.evaluate(f"BBOX({b}).{k}")


def tip(p, b, y):
    """The size of a thin slice of the body at y (square to Y): its section there."""
    ok(p, f"PLANE, lo, ZX, {y}\nPLANE, hi, ZX, {y + 0.01}\nSPLIT, {b}, lo, ABOVE\nSPLIT, {b}, hi, BELOW")
    return [box(p, b, k) for k in ("xmin", "xmax", "zmin", "zmax")]


def test_two_rails_set_chord_position_and_rise(p):
    # straight rails: the chord goes from 40 at the root to 16 at the tip, swept back 28, rising 8
    ok(p, "RECT, 20, 0, 0, 40, 4, 0, 0, -1, 0\nNAME, LAST, prof\n"
          "LINE, 0, 0, 0, 0, 100, 0\nNAME, LAST, spine\n"
          "LINE, 0, 0, 0, 28, 100, 8\nNAME, LAST, le\nLINE, 40, 0, 0, 44, 100, 8\nNAME, LAST, te")
    assert box(p, "prof", "xmin") == pytest.approx(0) and box(p, "prof", "xmax") == pytest.approx(40)
    r = ok(p, "RAILSWEEP, prof, le, te, spine")
    assert "RAILSWEEP (two rails," in r.message
    b = p.model.last_body
    assert "OK" in p.run(f"CHECK, {b}").message
    # a section halfway: chord 28 from x=14, thickness scaled with it (4 * 28/40), raised 4
    x0, x1, z0, z1 = tip(p, b, 50)
    assert (x0, x1) == (pytest.approx(14, abs=0.01), pytest.approx(42, abs=0.01))
    assert z1 - z0 == pytest.approx(4 * 28 / 40, abs=0.02)
    assert (z0 + z1) / 2 == pytest.approx(4, abs=0.02)


def test_volume_of_a_tapered_two_rail_sweep(p):
    ok(p, "RECT, 20, 0, 0, 40, 4, 0, 0, -1, 0\nLINE, 0, 0, 0, 0, 100, 0\n"
          "LINE, 0, 0, 0, 10, 100, 0\nLINE, 40, 0, 0, 30, 100, 0")
    ok(p, "RAILSWEEP, 1, 3, 4, 2")
    b = p.model.last_body
    # chord c(y) = 40 - 0.2 y, thickness 0.1 c: area 0.1 c^2
    expected = sum(0.1 * (40 - 0.2 * (i + 0.5) / 10) ** 2 / 10 for i in range(1000))
    assert p.evaluate(f"VOL({b})") == pytest.approx(expected, rel=1e-3)


def test_thickness_law_thins_square_to_the_rails(p):
    ok(p, "RECT, 20, 0, 0, 40, 4, 0, 0, -1, 0\nLINE, 0, 0, 0, 0, 100, 0\n"
          "LINE, 0, 0, 0, 0, 100, 0\nLINE, 40, 0, 0, 40, 100, 0")
    ok(p, "RAILSWEEP, 1, 3, 4, 2, 1 - 0.5*t")
    b = p.model.last_body
    assert p.evaluate(f"VOL({b})") == pytest.approx(40 * 4 * 100 * 0.75, rel=1e-3)
    assert box(p, b, "xmax") == pytest.approx(40, abs=1e-3)  # the chord is kept
    assert "needs two rails" in err(p, "RAILSWEEP, 1, 3, 0, 2, 1 - 0.5*t")


def test_one_rail_turns_the_profile(p):
    # a strip round a post: the rail is a helix of radius 15, the strip reaches from 5 to 15
    ok(p, "RECT, 10, 0, 0, 10, 2, 0, 0, 0, 1\nHELIX, 0, 0, 0, 15, 60, 100/60\nLINE, 0,0,0, 0,0,100")
    r = ok(p, "RAILSWEEP, 1, 2, 0, 3")
    assert "one rail" in r.message
    b = p.model.last_body
    assert p.evaluate(f"VOL({b})") == pytest.approx(10 * 2 * 100, rel=1e-3)
    assert box(p, b, "xmin") == pytest.approx(-15, abs=0.1)  # it turned right round
    assert "OK" in p.run(f"CHECK, {b}").message


def test_one_rail_scales_to_reach_the_rail_or_only_turns(p):
    # a rail that moves out from radius 10 to 20: SCALE grows the profile, TURN keeps its size
    ok(p, "CIRCLE, 8, 0, 0, 2\nLINE, 10, 0, 0, 20, 0, 50\nLINE, 0, 0, 0, 0, 0, 50")
    ok(p, "RAILSWEEP, 1, 2, 0, 3")
    grown = p.model.last_body
    assert box(p, grown, "xmax") == pytest.approx(20, abs=0.01)
    ok(p, "RAILSWEEP, 1, 2, 0, 3, , TURN")
    kept = p.model.last_body
    assert p.evaluate(f"VOL({kept})") == pytest.approx(math.pi * 4 * 50, rel=1e-3)
    assert "leave fit out" in err(p, "LINE, 0, 5, 0, 0, 5, 50\nRAILSWEEP, 1, 2, LAST, 3, , TURN")


def test_rails_that_do_not_fit(p):
    ok(p, "RECT, 20, 0, 0, 40, 4, 0, 0, -1, 0\nLINE, 0, 0, 0, 0, 100, 0\n"
          "LINE, 0, 0, 0, 0, 50, 0\nLINE, 40, 0, 0, 40, 100, 0")
    assert "rail 1 does not reach the section" in err(p, "RAILSWEEP, 1, 3, 4, 2")
    ok(p, "LINE, 0, 0, 0, 20, 100, 0\nLINE, 40, 0, 0, 20, 100, 0")
    assert "meet" in err(p, "RAILSWEEP, 1, LAST-1, LAST, 2")
    assert "fit must be" in err(p, "RAILSWEEP, 1, 3, 0, 2, , BEND")


def test_the_wing_example(p):
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "..", "scripts", "wing_rails.cmd"), encoding="utf-8") as fh:
        ok(p, fh.read())
    assert "OK" in p.run("CHECK, wing").message
    assert box(p, "wing", "ymax") == pytest.approx(120, abs=1e-6)
    x0, x1, z0, _ = tip(p, "wing", 119.98)
    assert x0 == pytest.approx(28, abs=0.05) and x1 == pytest.approx(44, abs=0.05)
    assert z0 > 7
    assert p.run('HIST, EDIT, 3, "TIP = 20"').ok


def test_form(p):
    ok(p, "RECT, 20, 0, 0, 40, 4, 0, 0, -1, 0\nNAME, LAST, foil\nLINE, 0, 0, 0, 0, 100, 0\nNAME, LAST, spine\n"
          "LINE, 0, 0, 0, 10, 100, 0\nNAME, LAST, le\nLINE, 40, 0, 0, 30, 100, 0\nNAME, LAST, te")
    sp = F.spec("RAILSWEEP")
    vals = F.initial(p, sp)
    vals.update(profile="foil", rail1="le", rail2="te", path="spine", thick="1 - 0.3*t")
    text, problems = F.check(p, sp, vals)
    assert (text, problems) == ("RAILSWEEP, foil, le, te, spine, 1 - 0.3*t", {})
    ok(p, text)
    assert F.parse(text)[2]["rail2"] == "te"
