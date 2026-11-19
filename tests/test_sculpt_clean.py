"""Sculpting that stays clean (PLAN item 54): fine and coarse areas meet gently, sharp edges,
masks and symmetry survive remeshing, every stroke is checked for cracks, folds and slivers, and
a long session of 2,000 strokes on a growing mesh stays clean (with timings)."""

import json
import time

import numpy as np
import pytest

from modeler.commands import Processor
from modeler.geometry import meshbody as mb
from modeler.geometry import meshcheck as mc
from modeler.geometry import sculpt as sc


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    res = p.run_script(text)
    bad = [r for r in res if not r.ok]
    assert not bad, f"{bad[0].line}: {bad[0].message}"
    return res[-1]


def sphere_mesh(p, deflection=0.2):
    ok(p, f"SPHERE, 0,0,0, 10\nTOMESH, 1, {deflection}")
    pts, t = mb.arrays(p.model.bodies[1].shape)
    return np.array(pts, dtype=float), np.array(t, dtype=np.int64)


def cube_mesh(n=6, size=10.0):
    """A closed cube of n x n squares per side (each cut in two), its points on the faces."""
    pts, index, tris = [], {}, []

    def pid(x):
        k = tuple(np.round(x, 9))
        if k not in index:
            index[k] = len(pts)
            pts.append(x)
        return index[k]

    g = np.linspace(-size / 2, size / 2, n + 1)
    for axis in range(3):
        for side in (-1, 1):
            u, v = [a for a in range(3) if a != axis]
            for i in range(n):
                for j in range(n):
                    q = []
                    for di, dj in ((0, 0), (1, 0), (1, 1), (0, 1)):
                        x = np.zeros(3)
                        x[axis], x[u], x[v] = side * size / 2, g[i + di], g[j + dj]
                        q.append(pid(x))
                    a, b, c, d = q
                    tris += [[a, b, c], [a, c, d]]
    p_, t_ = np.array(pts), np.array(tris)
    # turn every triangle outward
    cen = p_[t_].mean(axis=1)
    nrm = np.cross(p_[t_[:, 1]] - p_[t_[:, 0]], p_[t_[:, 2]] - p_[t_[:, 0]])
    flip = np.einsum("ij,ij->i", nrm, cen) < 0
    t_[flip] = t_[flip][:, [0, 2, 1]]
    return p_, t_


def longest(pts, t):
    return np.linalg.norm(pts[t] - pts[t[:, [1, 2, 0]]], axis=2).max(axis=1)


# ---- fine and coarse meet gently ------------------------------------------------------------------

def test_detail_grows_gently_away_from_the_stroke(p):
    pts, t = sphere_mesh(p)
    c = np.array([[10.0, 0, 0]])
    sizes = {}
    for grade in (0.0, sc.GRADE):
        P, T, _m, _n = sc.refine_near(pts, t, 0.15, c, 3.0, grade=grade)
        d = np.linalg.norm(P[T].mean(axis=1) - c[0], axis=1)
        L = longest(P, T)
        # the largest triangle just outside the brush (3 to 4.5 from it)
        sizes[grade] = L[(d > 3) & (d < 4.5)].max()
        assert mc.check(P, T).count == 0
        if grade:
            # outside, no edge is longer than the grading allows (plus one split's slack)
            far = d > 3
            assert (L[far] <= 2 * (0.15 + grade * (d[far] - 3)) + 0.3).all()
    assert sizes[sc.GRADE] < 0.5 * sizes[0.0]  # no jump from fine to coarse at the brush's rim


# ---- sharp edges, masks and symmetry kept while remeshing ------------------------------------------

def on_cube(P, half=5.0):
    """Each point's distance to the cube's surface."""
    a = np.abs(P)
    return np.abs(a.max(axis=1) - half)


def test_sharp_edges_stay_sharp_through_detail_and_joins():
    pts, t = cube_mesh()
    centre = np.array([[5.0, 5.0, 0.0]])  # on an edge of the cube
    P, T, _m, added = sc.refine_near(pts, t, 0.2, centre, 3.0)
    assert added > 100
    assert on_cube(P).max() < 1e-9  # the evening-out moved no point off the cube or off its edge
    keys, sharp = sc.sharp_edges(P, T)
    edge_pts = P[sharp]
    # every sharp point lies on a cube edge: two of its coordinates are at +-5
    assert ((np.abs(np.abs(edge_pts) - 5) < 1e-9).sum(axis=1) >= 2).all()
    # joins (as after a brush that squeezed points together) keep the corners and edges too
    Q, T2, _m, joined = sc.collapse_near(P, T, 0.25, centre, 3.0)
    assert joined > 0
    assert on_cube(Q).max() < 1e-9
    assert np.allclose(Q.min(axis=0), -5) and np.allclose(Q.max(axis=0), 5)
    assert mc.check(Q, T2).broken == 0


def test_mask_holds_through_detail_strokes(p):
    pts, t = sphere_mesh(p)
    # everything frozen but a soft hole round (10, 0, 0): the stroke reaches past the hole's rim
    ok(p, "MASK, 1, ALL\nMASK, 1, ERASE, 10, 0, 0, 2.5")
    frozen = p.model.masks[1] >= 0.999
    reach = np.linalg.norm(pts - [10, 0, 0], axis=1) < 5
    assert (frozen & reach).sum() > 5
    held = pts[frozen].copy()
    r = ok(p, 'SCULPT, 1, DRAW, 3, 0.8, "10,0,-3, 10,0,3", , 0.3')
    assert "points added for detail" in r.message
    q, _t = mb.arrays(p.model.bodies[1].shape)
    q = np.asarray(q)
    m = p.model.masks[1]
    assert len(m) == len(q)
    # every fully frozen point is still there, where it was
    from scipy.spatial import cKDTree

    d, _i = cKDTree(q).query(held)
    assert d.max() < 1e-9


def test_symmetric_strokes_stay_symmetric_with_detail(p):
    pts, t = sphere_mesh(p)
    r = sc.sculpt_step(pts, t, "DRAW", 3.0, 0.6, np.array([[6, 6, 5.0], [6, 6, -5.0]]) / 1.0, "X", None, 0.3)
    P, T = r.pts, r.tris
    # the bumps on both sides match: each side's highest point mirrors the other's
    right, left = P[P[:, 0] > 0], P[P[:, 0] < 0]
    rad_r, rad_l = np.linalg.norm(right, axis=1).max(), np.linalg.norm(left, axis=1).max()
    assert rad_r > 10.3 and rad_r == pytest.approx(rad_l, rel=0.01)
    assert r.added and not r.worse


# ---- every stroke is checked --------------------------------------------------------------------

def grid(n=8):
    xs = np.linspace(0, 1, n + 1)
    pts = np.array([[x, y, 0.0] for y in xs for x in xs])
    tris = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            tris += [[a, a + 1, a + n + 2], [a, a + n + 2, a + n + 1]]
    return pts, np.array(tris)


def test_check_finds_cracks_folds_and_slivers():
    pts, t = grid()
    assert mc.check(pts, t, open_ok=True).count == 0
    # a crack: a triangle taken out of the middle
    assert mc.check(pts, np.delete(t, 40, axis=0), open_ok=True).open_edges == 0  # open_ok: rims are fine
    cracked = mc.check(pts, np.delete(t, 40, axis=0))
    assert cracked.open_edges > mc.check(pts, t).open_edges
    # a fold: one point pushed through its neighbours
    q = pts.copy()
    q[40] = q[40] + [0.4, 0.4, 0.0]
    f = mc.check(q, t, open_ok=True)
    assert f.folded > 0 and f.where["folded"]
    # a sliver: a point moved almost onto the line of its neighbours
    s = pts.copy()
    s[40, 1] += 0.124
    assert mc.check(s, t, open_ok=True).thin > 0
    # inside out: one triangle turned
    t2 = t.copy()
    t2[40] = t2[40][[0, 2, 1]]
    assert mc.check(pts, t2, open_ok=True).misturned == 3


def test_untangle_smooths_a_fold_flat():
    pts, t = grid()
    q = pts.copy()
    q[40] = q[40] + [0.2, 0.2, 0.0]
    assert mc.check(q, t, open_ok=True).folded > 0
    fixed, left = mc.untangle(q, t)
    assert left == 0 and mc.check(fixed, t, open_ok=True).folded == 0
    # a frozen fold point is not moved (the ring round it is)
    frozen = np.zeros(len(q), dtype=bool)
    frozen[40] = True
    fixed2, _ = mc.untangle(q, t, frozen=frozen)
    assert np.allclose(fixed2[40], q[40])


def test_sculpt_reports_or_clears_what_a_stroke_breaks(p):
    sphere_mesh(p, 0.3)
    # a hard pinch with no detail squeezes triangles over each other: smoothed flat, or reported
    res = p.run_script('SCULPT, 1, PINCH, 4, 1, "10,0,-4, 10,0,4"\nSCULPT, 1, PINCH, 4, 1, "10,0,-4, 10,0,4"')
    assert all(r.ok for r in res)
    pts, t = mb.arrays(p.model.bodies[1].shape)
    left = mc.check(np.asarray(pts), np.asarray(t))
    said = " ".join(r.message + " " + r.warning for r in res)
    assert left.folded == 0 or "fold" in said
    assert left.broken == 0
    row = json.loads(p.run("CHECK, 1, FLAWS, 0, JSON").message)
    assert row["mesh"] and row["open_edges"] == 0


# ---- a long session --------------------------------------------------------------------------------

def test_two_thousand_strokes_on_a_growing_mesh(p):
    """2,000 strokes with every brush, some mirrored, all with detail, on a sphere that grows from
    about 900 triangles. After each one the mesh near it is checked; at the end the whole mesh.
    Prints the timings (pytest -s shows them)."""
    pts, t = sphere_mesh(p)
    rng = np.random.default_rng(7)
    brushes = [b for b in sc.BRUSHES if b != "GRAB"]
    start, n0 = time.perf_counter(), len(t)
    slowest = 0.0
    sizes = []
    for k in range(2000):
        d = rng.normal(size=3)
        d /= np.linalg.norm(d)
        a = d * np.linalg.norm(pts, axis=1).mean()
        b = a + np.cross(d, rng.normal(size=3)) * 0.3
        brush = brushes[k % len(brushes)]
        strength = float(rng.uniform(0.1, 0.5)) * (1 if k % 5 else -1)
        t0 = time.perf_counter()
        r = sc.sculpt_step(pts, t, brush, 1.5, strength, np.vstack([a, b]), "X" if k % 4 == 0 else "", None, 0.5)
        slowest = max(slowest, time.perf_counter() - t0)
        pts, t = r.pts, r.tris
        assert not r.worse or set(r.worse) <= {"thin", "folded", "flat"}, f"stroke {k}: {r.worse}"
        sizes.append(len(t))
    took = time.perf_counter() - start
    final = mc.check(pts, t)
    print(f"\n2,000 strokes: {took:.1f} s ({took / 2:.1f} ms a stroke, slowest {slowest * 1000:.0f} ms); "
          f"{n0:,} -> {len(t):,} triangles; left {final.as_dict()}")
    assert final.broken == 0  # no cracks, three-way edges or inside-out triangles, ever
    assert final.folded <= 0.001 * len(t) and final.thin <= 0.002 * len(t)
    assert len(t) > 3 * n0  # it grew
    assert took < 600  # loose: CI machines are slow; about 60 s here
