"""FITSURF: smooth NURBS surfaces fitted to meshes (geometry/meshfit.py)."""

import math

import numpy as np
import pytest

from modeler.commands import Processor
from modeler.geometry import meshbody as mb
from modeler.geometry import meshfit as mf


def _grid(n=60, fold=False):
    x, y = np.meshgrid(np.linspace(-50, 50, n), np.linspace(-30, 30, n))
    z = 5 * np.sin(x / 15) * np.cos(y / 12)
    if fold:
        x = 20 * np.cos(x / 50 * 2.5)  # rolls over: not a height field any more
    pts = np.column_stack([x.ravel(), y.ravel(), z.ravel()])
    idx = np.arange(n * n).reshape(n, n)
    tris = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b, c, d = idx[i, j], idx[i, j + 1], idx[i + 1, j], idx[i + 1, j + 1]
            tris += [(a, b, d), (a, d, c)]
    return pts, np.array(tris)


def test_wavy_patch_with_a_hole_meets_the_tolerance():
    pts, tris = _grid(90)
    keep = ((pts[:, 0] / 50) ** 2 + (pts[:, 1] / 30) ** 2 < 1) & ((pts[:, 0] - 10) ** 2 + pts[:, 1] ** 2 > 64)
    pp, tt, pieces = mf.patch(pts, tris, keep)
    assert pieces == 1
    assert len(mf.boundary_loops(tt)) == 2  # the outline and the hole
    fit = mf.fit_patch(pp, tt, 0.05)
    assert fit.reached and fit.max_dev <= 0.05
    from OCP.BRepCheck import BRepCheck_Analyzer

    assert BRepCheck_Analyzer(fit.shape).IsValid()


def test_a_patch_that_folds_is_refused():
    pts, tris = _grid(40, fold=True)
    with pytest.raises(mf.FitError, match="folds"):
        mf.fit_patch(pts, tris, 0.05)


def test_closed_mesh_becomes_a_solid_close_to_its_volume():
    pts, tris = mb.sphere(20, 48)
    pts = pts * np.array([1.4, 1.0, 0.8])
    fit = mf.fit_closed(pts, tris, 0.05)
    assert fit.shape.ShapeType().name.endswith("SOLID")
    exact = 4 / 3 * math.pi * 28 * 20 * 16  # the ellipsoid the mesh was made from
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    g = GProp_GProps()
    (getattr(BRepGProp, "VolumeProperties_s", None) or BRepGProp.VolumeProperties)(fit.shape, g)
    assert g.Mass() == pytest.approx(exact, rel=0.01)


def test_a_closed_mesh_that_hides_itself_is_refused():
    p = Processor()
    for line in ["BLOCK, 0,0,0, 40, 40, 10", "BLOCK, 0,0,0, 10, 40, 40", "BLOCK, 30,0,0, 10, 40, 40",
                 "UNION, 1, 2", "UNION, LAST, 3", "TOMESH, LAST, 0.5"]:
        assert p.run(line).ok
    res = p.run("FITSURF, LAST")
    assert not res.ok and "not round enough" in res.message


def test_fitsurf_command_on_a_sphere_and_a_masked_cap():
    p = Processor()
    for line in ["SPHERE, 0,0,0, 20", "TOMESH, 1, 0.05"]:
        assert p.run(line).ok
    res = p.run("FITSURF, 1")
    assert res.ok, res.message
    assert "solid" in res.message
    assert p.evaluate("VOL(2)") == pytest.approx(4 / 3 * math.pi * 8000, rel=1e-3)
    assert p.run("CYL, 0,0,-30, 5, 60").ok
    assert p.run("SUBTRACT, 2, 3").ok  # a fitted solid takes booleans
    assert not p.run("FITSURF, 1, MASK").ok  # no mask yet
    assert p.run("MASK, 1, PAINT, 0,0,20, 12").ok
    res = p.run("FITSURF, 1, MASK, 0.01")
    assert res.ok and "face" in res.message, res.message
    assert p.model.body(1)  # the mesh stays
