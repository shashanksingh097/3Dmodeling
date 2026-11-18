"""Scan to CAD for machined parts: SEGMENT and RECONSTRUCT (geometry/scanfit.py)."""

import numpy as np
import pytest

from modeler.commands import Processor
from modeler.geometry import meshbody as mb
from modeler.geometry import robust
from modeler.geometry import scanfit as sf

PART = ["BLOCK, 0,0,0, 60,40,20", "NAME, LAST, part", "CYL, 35, 20, -1, 5, 30", "SUBTRACT, part, LAST",
        "CYL, 45, 20, 20, 6, 10", "UNION, part, LAST", "SPHERE, 15, 20, 20, 5", "UNION, part, LAST"]


def _scan(noise=0.0):
    p = Processor()
    for line in PART:
        assert p.run(line).ok, line
    v0 = robust.volume(p.model.body(max(p.model.bodies)).shape)
    assert p.run("TOMESH, part").ok
    b = max(p.model.bodies)
    pts, t = mb.arrays(p.model.body(b).shape)
    if noise:
        pts = pts + np.random.default_rng(1).normal(scale=noise, size=pts.shape)
    return p, b, pts, t, v0


def test_regions_are_recognised():
    _p, _b, pts, t, _v = _scan(0.01)
    regs = sf.recognise(pts, t, sf.segment(pts, t, 25), 0.1)
    kinds = sorted(r.shape.kind for r in regs)
    assert kinds == ["CYLINDER", "CYLINDER"] + ["PLANE"] * 7 + ["SPHERE"]
    cyl = sorted((r.shape for r in regs if r.shape.kind == "CYLINDER"), key=lambda s: s.radius)
    assert cyl[0].radius == pytest.approx(5, abs=0.05) and cyl[0].inside  # the bore
    assert cyl[1].radius == pytest.approx(6, abs=0.05) and not cyl[1].inside  # the boss
    sph = next(r.shape for r in regs if r.shape.kind == "SPHERE")
    assert np.allclose(sph.centre, (15, 20, 20), atol=0.05) and sph.radius == pytest.approx(5, abs=0.05)


@pytest.mark.parametrize("noise", [0.0, 0.01])
def test_reconstruct_gives_the_part_back(noise):
    _p, _b, pts, t, v0 = _scan(noise)
    regs = sf.recognise(pts, t, sf.segment(pts, t, 25), 0.1)
    shape, _cells, _kept = sf.reconstruct(pts, t, regs)
    assert robust.checked_ok(shape, True)
    assert robust.volume(shape) == pytest.approx(v0, rel=1e-3)


def test_snap_makes_near_axes_exact():
    _p, _b, pts, t, _v = _scan(0.01)
    regs = sf.snap(sf.recognise(pts, t, sf.segment(pts, t, 25), 0.1))
    for r in regs:
        if r.shape.kind in ("PLANE", "CYLINDER"):
            assert max(abs(x) for x in r.shape.axis) == 1.0


def test_commands():
    p, b, *_ = _scan()
    r = p.run(f"SEGMENT, {b}")
    assert r.ok and "10 regions" in r.message and "bore radius" in r.message
    r = p.run(f"RECONSTRUCT, {b}")
    assert r.ok, r.message
    assert "2 cylinders, 1 sphere" in r.message
    new = max(p.model.bodies)
    assert new != b and not mb.is_mesh(p.model.body(new).shape)
    assert p.run(f"CHECK, {new}").ok


def test_freeform_is_refused():
    p = Processor()
    pts, t = mb.sphere(10, 32)
    pts = pts * np.array([1.0, 1.0, 0.5])  # an ellipsoid: no plane, cylinder or sphere fits
    p.model.add_body(mb.make_shape(pts, t))
    b = max(p.model.bodies)
    r = p.run(f"RECONSTRUCT, {b}")
    assert not r.ok and "FITSURF" in r.message


def test_needs_a_mesh():
    p = Processor()
    assert p.run("BLOCK, 0,0,0, 1,1,1").ok
    r = p.run("SEGMENT, 1")
    assert not r.ok
