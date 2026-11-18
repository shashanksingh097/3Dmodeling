"""STRESS: the first strength check (geometry/fea.py, commands/stress_handlers.py)."""

import math

import numpy as np
import pytest

pytest.importorskip("scipy")

from modeler.commands import Processor  # noqa: E402
from modeler.geometry import fea  # noqa: E402


def run(p, *lines):
    for line in lines:
        r = p.run(line)
        assert r.ok, (line, r.message)
    return r


def face(p, nx, ny, nz):
    run(p, f"SEL, S, FACE, NORMAL, {nx}, {ny}, {nz}")
    return p.model.selection[0]


def test_element_is_symmetric_and_free_to_move_rigidly():
    k = fea.element(200_000, 0.3, np.array([1.0, 2.0, 0.5]))
    assert np.allclose(k, k.T, atol=1e-6 * abs(k).max())
    c = (fea._CORNERS + 1) / 2 * np.array([1.0, 2.0, 0.5])
    for t in np.eye(3):  # translations
        assert np.allclose(k @ np.tile(t, 8), 0, atol=1e-6 * abs(k).max())
    rot = np.cross([0, 0, 1.0], c).ravel()  # a small rotation about z
    assert np.allclose(k @ rot, 0, atol=1e-6 * abs(k).max())
    assert np.linalg.eigvalsh(k).min() > -1e-6 * abs(k).max()


def test_voxels_fill_a_sphere():
    p = Processor()
    run(p, "SPHERE, 0, 0, 0, 10")
    g = fea.voxelize(p.model.body(1).shape, 1.0)
    vol = len(g.cells) * float(np.prod(g.h))
    assert vol == pytest.approx(4 / 3 * math.pi * 1000, rel=0.02)


def test_cantilever_matches_beam_theory():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 100,10,10")
    fixed, end = face(p, -1, 0, 0), face(p, 1, 0, 0)
    msg = run(p, f'STRESS, 1, "{fixed}", "{end}", FORCE, 0, 0, -100').message
    res = p.analysis.field
    d, _ = res.deflection()
    assert d == pytest.approx(100 * 100 ** 3 / (3 * 200_000 * 10 ** 4 / 12), rel=0.01)  # F L^3 / 3 E I = 0.2
    assert np.allclose(res.reaction, (0, 0, 100), atol=1e-6)  # the support takes the load
    # bending stress M c / I = 60 MPa at the root's surface; cell centres sit half a cell inside
    peak, _ = res.peak()
    assert 45 < peak < 65
    assert "safety factor" in msg and "holds" in msg
    assert p.analysis.mode == "STRESS" and p.analysis.scale > 0


def test_pressure_gives_area_times_pressure():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 100,10,10", "MATERIAL, 1, ALUMINIUM")
    fixed, top = face(p, -1, 0, 0), face(p, 0, 0, 1)
    msg = run(p, f'STRESS, 1, "{fixed}", "{top}", PRESSURE, 0.2').message
    assert np.allclose(p.analysis.field.force, (0, 0, -0.2 * 1000), atol=1e-6)
    assert "aluminium" in msg
    # aluminium is about three times softer than steel
    d, _ = p.analysis.field.deflection()
    assert d == pytest.approx(200 * 100 ** 3 / (8 * 69_000 * 10 ** 4 / 12), rel=0.03)  # w L^3 / 8 E I


def test_errors():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 10,10,10", "BLOCK, 20,0,0, 10,10,10")
    a = face(p, -1, 0, 0)
    run(p, "SEL, S, FACE, NORMAL, 1, 0, 0")
    other = max(p.model.selection)
    r = p.run(f'STRESS, 1, "{a}", "{other}", FORCE, 1, 0, 0')
    assert not r.ok and "not on body 1" in r.message
    r = p.run(f'STRESS, 1, "{a}", "{a + 1}", FORCE, 0, 0, 0')
    assert not r.ok and "zero" in r.message
    run(p, "MATERIAL, 1, RUBBER")
    r = p.run(f'STRESS, 1, "{a}", "{a + 1}", FORCE, 1, 0, 0')
    assert not r.ok and "RUBBER" in r.message
