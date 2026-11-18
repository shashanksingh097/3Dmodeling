"""Big-mesh sculpting: boxes for ray tests, a point grid for brush strokes, cheap mesh stats."""

import numpy as np
import pytest

from modeler.geometry import meshbody as mb
from modeler.geometry import sculpt as sc

st = pytest.importorskip("modeler.gui.sculpt_tool")


@pytest.fixture(scope="module")
def ball():
    pts, tris = mb.sphere(20, 64)
    pts, tris = mb.refine(pts, tris, 0.35)
    assert len(tris) >= st.INDEX_FROM
    return pts, tris


def _rays(n=40, seed=0):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        o = rng.normal(size=3) * 60
        yield o, -o + rng.normal(size=3) * 12


def test_boxed_ray_test_finds_the_same_points(ball):
    pts, tris = ball
    hits = 0
    for o, d in _rays():
        a, b = st.ray_hit(pts, tris, o, d), st._ray_hit_all(pts, tris, o, d)
        assert (a is None) == (b is None)
        if a is not None:
            hits += 1
            assert np.allclose(a, b)
    assert hits > 10


def test_grown_boxes_still_hold_moved_points(ball):
    pts, tris = ball
    moved = pts * 1.08  # every point moves outwards up to 1.6
    grow = float(np.linalg.norm(moved - pts, axis=1).max())
    for o, d in _rays(seed=1):
        a = st.ray_hit(moved, tris, o, d, base=pts, grow=grow)
        b = st._ray_hit_all(moved, tris, o, d)
        assert (a is None) == (b is None)
        if a is not None:
            assert np.allclose(a, b)


def test_point_grid_finds_every_point_in_a_box(ball):
    pts, _ = ball
    grid = sc.PointGrid(pts, 3.0)
    lo, hi = np.array([-5.0, -21, -4]), np.array([6.0, -12, 7])
    want = set(np.flatnonzero(np.all((pts >= lo) & (pts <= hi), axis=1)).tolist())
    got = set(grid.inside(lo, hi).tolist())
    assert want <= got
    assert len(got) < len(pts) / 4  # and it did not just give everything


@pytest.mark.parametrize("brush", ["DRAW", "CLAY", "SMOOTH", "INFLATE"])
def test_stroke_with_candidates_matches_the_full_search(ball, brush):
    pts, tris = ball
    topo = sc.Topology.of(tris, len(pts))
    path = np.array([[-6.0, -19.5, 0.0], [6.0, -19.5, 2.0]])
    full, rep = sc.stroke(pts, tris, brush, 3.0, 0.7, path, "X", topo=topo)
    grid = sc.PointGrid(pts, 6.0)
    cand = np.unique(np.concatenate([grid.inside(np.minimum(path[0] * s, path[1] * s) - 3.01,
                                                 np.maximum(path[0] * s, path[1] * s) + 3.01)
                                     for s in sc._mirrors("X")]))
    fast, rep2 = sc.stroke(pts, tris, brush, 3.0, 0.7, path, "X", topo=topo, candidates=cand)
    assert rep.moved and rep.moved == rep2.moved
    assert np.allclose(full, fast)


def test_live_drag_on_a_big_mesh_moves_the_surface(ball):
    pts, tris = ball
    shape = mb.make_shape(pts, tris)
    s = st.Settings()
    s.radius, s.brush = 2.5, "DRAW"
    live = st.LiveStroke(1, shape, s)
    live.BIG = 1  # use the big-mesh path here
    moved = 0
    for k in range(25):
        h = live.hit(np.array([-8 + k * 0.6, -100.0, 1.0]), np.array([0, 1.0, 0]))
        assert h is not None
        moved += live.add(h)
    assert moved > 5 and live._grow > 0
    assert live.patch() is not None


def test_mesh_description_does_not_need_volume(ball):
    pts, tris = ball
    shape = mb.make_shape(pts, tris)
    from modeler.commands.mesh_handlers import describe

    assert describe(shape) == f"(mesh, {len(tris):,} triangles)"
    t = mb.arrays(shape)[1]
    assert mb.closed(t) is True and mb.closed(t) is True  # the second answer is remembered
    i = mb.info(shape)
    assert i.volume == pytest.approx(mb.volume(pts, tris)) and i.area == pytest.approx(mb.area(pts, tris))
