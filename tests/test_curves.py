"""Shapes on curves: paths, profiles, LOFT, SWEEP with laws, MORPH, PIPE, HELIX, CURVE."""

import math
from pathlib import Path

import pytest
from OCP.BRepCheck import BRepCheck_Analyzer

from modeler.commands import Processor

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def err(p, line):
    r = p.run(line)
    assert not r.ok
    return r.message


def length(p, b="LAST"):
    from modeler.geometry.sweep import PathSampler, as_wire

    bid = p.evaluate(b) if isinstance(b, str) else b
    return PathSampler(as_wire(p.model.body(bid).shape, "curve")).length


def bbox(p, b="LAST"):
    from types import SimpleNamespace

    rec = p.evaluate(f"BBOX({b})")
    return SimpleNamespace(**{k: rec.get(k) for k in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")})


def vol(p, b="LAST"):
    return p.evaluate(f"VOL({b})")


def valid(p, b="LAST"):
    return BRepCheck_Analyzer(p.model.body(p.evaluate(b)).shape).IsValid()


# ---- curves and profiles --------------------------------------------------------
def test_paths(p):
    ok(p, "LINE, 0,0,0, 30,40,0")
    assert length(p) == pytest.approx(50)
    ok(p, "ARC, 10,0,0, 0,10,0, -10,0,0")
    assert length(p) == pytest.approx(10 * math.pi)
    ok(p, "POLYLINE, (0,0,0), (10,0,0), (10,10,0), CLOSE")
    assert length(p) == pytest.approx(20 + math.sqrt(200))
    assert p.model.body(p.evaluate("LAST")).shape.Closed()
    ok(p, "SPLINE, (0,0,0), (10,5,0), (20,0,3)")
    assert not p.model.body(p.evaluate("LAST")).shape.Closed()


def test_profiles(p):
    ok(p, "CIRCLE, 0,0,0, 5")
    assert length(p) == pytest.approx(10 * math.pi)
    ok(p, "RECT, 0,0,0, 20, 10")
    assert length(p) == pytest.approx(60)
    ok(p, "RECT, 0,0,0, 20, 10, 2")
    assert length(p) == pytest.approx(60 - 16 + 4 * math.pi)
    ok(p, "POLYGON, 0,0,0, 10, 6")
    assert length(p) == pytest.approx(60)
    ok(p, "SLOT, 0,0,0, 20, 6, 1,0,0")
    assert length(p) == pytest.approx(28 + 6 * math.pi)
    ok(p, "STAR, 0,0,0, 10, 4, 5")
    ok(p, "ELLIPSE, 0,0,0, 6, 3, 0,1,0, 30")
    ok(p, "AIRFOIL, 0,0,0, 100, 2412, 1,0,0")
    assert length(p) == pytest.approx(204, rel=0.01)  # a thin airfoil is a little over twice its chord


def test_profile_plane_rule(p):
    """Normal +X: profile X is world Y, profile Y is world Z."""
    ok(p, "RECT, 0,0,0, 20, 4, 0, 1,0,0")
    box = bbox(p, "LAST")
    assert (box.xmax - box.xmin, box.ymax - box.ymin, box.zmax - box.zmin) == pytest.approx((0, 20, 4), abs=1e-6)


def test_bad_curve_input_is_reported(p):
    assert "same point" in err(p, "LINE, 1,1,1, 1,1,1")
    assert "one line" in err(p, "ARC, 0,0,0, 1,0,0, 2,0,0")
    assert "point" in err(p, "SPLINE, (0,0,0), 5")
    assert "NACA" in err(p, "AIRFOIL, 0,0,0, 10, 24x2")


def test_helix_and_variable_pitch(p):
    ok(p, "HELIX, 0,0,0, 10, 5, 4")
    assert length(p) == pytest.approx(4 * math.hypot(2 * math.pi * 10, 5), rel=1e-3)
    assert p.evaluate("BBOX(LAST).zmax") == pytest.approx(20, abs=1e-6)
    ok(p, "HELIX, 0,0,0, 10, 5, 4, 0,0,1, 0, LEFT, 2*t")  # average pitch factor 1
    assert p.evaluate("BBOX(LAST).zmax") == pytest.approx(20, abs=0.01)


def test_equation_curve_closes_itself(p):
    ok(p, "CURVE, PARAM, 10*cos(t), 10*sin(t), 0, 0, 360, 72")
    assert p.model.body(p.evaluate("LAST")).shape.Closed()
    assert length(p) == pytest.approx(20 * math.pi, rel=1e-4)


# ---- loft ------------------------------------------------------------------------
def test_loft_two_circles_is_a_cylinder(p):
    ok(p, "CIRCLE, 0,0,0, 5\nCIRCLE, 0,0,10, 5\nLOFT, 1, 2")
    assert vol(p) == pytest.approx(math.pi * 25 * 10, rel=1e-3)
    assert valid(p)


def test_ruled_loft_is_a_frustum(p):
    ok(p, "CIRCLE, 0,0,0, 6\nCIRCLE, 0,0,10, 3\nLOFT, 1, 2, RULED")
    assert vol(p) == pytest.approx(math.pi * 10 / 3 * (36 + 18 + 9), rel=1e-3)


def test_loft_through_different_shapes_and_surface(p):
    ok(p, "CIRCLE, 0,0,0, 10\nRECT, 0,0,15, 20, 20, 4\nCIRCLE, 0,0,30, 6\nLOFT, 1, 2, 3")
    assert valid(p) and vol(p) > 0
    ok(p, "LOFT, 1, 2, 3, SURFACE")
    assert p.model.body(p.evaluate("LAST")).entity_ids["FACE"]
    assert "at least 2" in err(p, "LOFT, 1")


# ---- sweep -----------------------------------------------------------------------
def test_plain_sweep_is_exact(p):
    r = ok(p, "LINE, 0,0,0, 0,0,40\nCIRCLE, 0,0,0, 3\nSWEEP, 2, 1")
    assert "exact" in r.message
    assert vol(p) == pytest.approx(math.pi * 9 * 40, rel=1e-4)


def test_scale_law_makes_a_frustum(p):
    ok(p, "LINE, 0,0,0, 0,0,40\nCIRCLE, 0,0,0, 4\nSWEEP, 2, 1, 0, 1 - 0.5*t")
    assert vol(p) == pytest.approx(math.pi * 40 / 3 * (16 + 8 + 4), rel=2e-3)


def test_twist_keeps_volume_and_turns_the_end(p):
    ok(p, "LINE, 0,0,0, 0,0,50\nRECT, 0,0,0, 20, 4\nSWEEP, 2, 1, 90*t")
    assert vol(p) == pytest.approx(20 * 4 * 50, rel=2e-3)
    assert valid(p)
    # the top face has turned a quarter turn: long side now along Y
    top = [f for f in p.model.body(p.evaluate("LAST")).entity_ids["FACE"]
           if p.evaluate(f"CENT({f}, 'FACE').z") > 49.9]
    assert len(top) == 1


def test_laws_use_parameters_and_macro_arguments(p):
    ok(p, """
TW = 45
LINE, 0,0,0, 0,0,30
NAME, LAST, axis
CIRCLE, 0,0,0, 2
NAME, LAST, c
*MACRO, horn, k
  SWEEP, c, axis, TW*t, 1 + k*t
*END
horn, 1
""")
    assert vol(p) == pytest.approx(math.pi * 30 / 3 * (4 + 8 + 16), rel=2e-3)


def test_stretch_and_offset_laws(p):
    ok(p, "LINE, 0,0,0, 0,0,30\nCIRCLE, 0,0,0, 2\nSWEEP, 2, 1, 0, 1, , 1 + t, 1, 0, 10*t")
    box = bbox(p, "LAST")
    # side direction for a +Z path is world X (start frame): stretched to 2x, offset 10 along up (world Y)
    assert box.xmax == pytest.approx(4, abs=0.05)
    assert box.ymax == pytest.approx(12, abs=0.05)


def test_quoted_law_and_law_errors(p):
    ok(p, 'LINE, 0,0,0, 0,0,30\nCIRCLE, 0,0,0, 2\nSWEEP, 2, 1, "30*t"')
    assert "above 0" in err(p, "SWEEP, 2, 1, 0, 1 - 2*t")
    assert "number" in err(p, 'SWEEP, 2, 1, "a" + STR(t)')
    assert "mode" in err(p, "SWEEP, 2, 1, 0, 1, SIDEWAYS")


def test_sweep_along_closed_path(p):
    ok(p, "CIRCLE, 0,0,0, 30\nRECT, 30,0,0, 4, 8, 0, 0,1,0\nSWEEP, 2, 1, 360*t")
    assert vol(p) == pytest.approx(4 * 8 * 2 * math.pi * 30, rel=3e-3)
    assert valid(p)


def test_morph_between_profiles(p):
    r = ok(p, """
LINE, 0,0,0, 60,0,0
CIRCLE, 0,0,0, 6, 1,0,0
RECT, 0,0,0, 10, 10, 2, 1,0,0
STAR, 0,0,0, 7, 3, 5, 1,0,0
MORPH, 1, 45*t, 1, MINTWIST, 2, 3, 4
""")
    assert "sections" in r.message
    assert valid(p)
    assert p.evaluate("BBOX(LAST).xmax") == pytest.approx(60, abs=1e-6)
    assert "at least 2" in err(p, "MORPH, 1, 0, 1, MINTWIST, 2")


# ---- pipe ------------------------------------------------------------------------
def test_pipe_hollow_and_radius_law(p):
    ok(p, "LINE, 0,0,0, 50,0,0\nPIPE, 1, 5, 3")
    assert vol(p) == pytest.approx(math.pi * (25 - 9) * 50, rel=1e-3)
    ok(p, "PIPE, 1, 4, 0, 1 + t")
    assert vol(p) == pytest.approx(math.pi * 50 / 3 * (16 + 32 + 64), rel=3e-3)


def test_spring(p):
    ok(p, "HELIX, 0,0,0, 20, 8, 3\nPIPE, 1, 2")
    assert vol(p) == pytest.approx(math.pi * 4 * length(p, 1), rel=5e-3)


def test_curves_stay_after_use_and_can_be_hidden(p):
    ok(p, "LINE, 0,0,0, 0,0,10\nCIRCLE, 0,0,0, 1\nSWEEP, 2, 1\nHIDE, 1")
    assert sorted(p.model.bodies) == [1, 2, 3]
    assert p.model.hidden == {1}
    ok(p, "UNDO")
    assert p.model.hidden == set()
    ok(p, "REDO\nSHOW")
    assert p.model.hidden == set()


def test_history_edit_reshapes_the_sweep(p):
    ok(p, "TW = 0\nLINE, 0,0,0, 0,0,30\nRECT, 0,0,0, 10, 2\nSWEEP, 2, 1, TW*t")
    box0 = bbox(p, "3")
    ok(p, 'HIST, EDIT, 1, "TW = 90"')
    box1 = bbox(p, "3")
    assert box0.ymax == pytest.approx(1, abs=1e-6)
    assert box1.ymax > 4.9  # the far end turned a quarter turn


def test_smooth_blade_script(p):
    rs = p.run_script((ROOT / "scripts" / "blade_smooth.cmd").read_text())
    assert all(r.ok for r in rs), [r.message for r in rs if not r.ok]
    assert p.evaluate("BBOX(rotor).xmax") == pytest.approx(134, abs=0.5)
    assert valid(p, "rotor")


def test_gallery_script(p):
    rs = p.run_script((ROOT / "scripts" / "sweep_gallery.cmd").read_text())
    assert all(r.ok for r in rs), [r.message for r in rs if not r.ok]
