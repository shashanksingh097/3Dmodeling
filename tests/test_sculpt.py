"""Sculpting mesh bodies (M7): the brushes, symmetry, masks, the commands, strokes in projects."""

import time

import numpy as np
import pytest

from modeler.commands import Processor
from modeler.geometry import meshbody as mb
from modeler.geometry import sculpt as sc


@pytest.fixture(scope="module")
def ball():
    pts, t = mb.sphere(20, 96)
    return pts, t, sc.Topology.of(t, len(pts))


TOP = np.array([[0, -6, 19.0], [0, 0, 20.0], [0, 6, 19.0]])


def test_neighbours_of_a_tetrahedron():
    t = np.array([[0, 1, 2], [0, 3, 1], [0, 2, 3], [1, 3, 2]])
    topo = sc.Topology.of(t, 4)
    assert list(topo.degree) == [3, 3, 3, 3]
    for i in range(4):
        assert sorted(topo.indices[topo.indptr[i]:topo.indptr[i + 1]]) == [j for j in range(4) if j != i]


def test_resample_keeps_the_ends_and_spacing():
    s = sc.resample(np.array([[0, 0, 0], [10, 0, 0]]), 1.0)
    assert len(s) == 11 and np.allclose(s[0], 0) and np.allclose(s[-1], [10, 0, 0])
    assert np.allclose(np.diff(s[:, 0]), 1.0)


@pytest.mark.parametrize("brush,sign", [("DRAW", 1), ("CLAY", 1), ("INFLATE", 1), ("CREASE", -1), ("PINCH", -1)])
def test_brushes_change_the_volume_the_right_way(ball, brush, sign):
    pts, t, topo = ball
    v0 = mb.volume(pts, t)
    out, rep = sc.stroke(pts, t, brush, 5, 0.6, TOP, topo=topo)
    assert rep.moved > 0 and rep.dabs >= 4
    assert np.sign(mb.volume(out, t) - v0) == sign
    far = np.linalg.norm(pts - [0, 0, 20], axis=1) > 15
    assert np.allclose(out[far], pts[far])  # only near the stroke
    assert np.array_equal(pts, ball[0])  # the input is not changed


def test_negative_strength_digs(ball):
    pts, t, topo = ball
    up, _ = sc.stroke(pts, t, "DRAW", 5, 0.5, TOP, topo=topo)
    down, _ = sc.stroke(pts, t, "DRAW", 5, -0.5, TOP, topo=topo)
    v0 = mb.volume(pts, t)
    assert mb.volume(up, t) > v0 > mb.volume(down, t)


def test_smooth_and_flatten_take_a_bump_away(ball):
    pts, t, topo = ball
    bumped, _ = sc.stroke(pts, t, "DRAW", 4, 1.0, [[0, 0, 20]], topo=topo)
    r = lambda p: np.linalg.norm(p, axis=1)  # noqa: E731
    near = np.linalg.norm(pts - [0, 0, 20], axis=1) < 6
    bump = (r(bumped) - 20)[near].max()
    smoothed, _ = sc.stroke(bumped, t, "SMOOTH", 6, 1.0, [[0, 0, 21]] * 1, topo=topo)
    for _ in range(5):
        smoothed, _ = sc.stroke(smoothed, t, "SMOOTH", 6, 1.0, [[0, 0, 21]], topo=topo)
    assert (r(smoothed) - 20)[near].max() < 0.7 * bump
    flat, _ = sc.stroke(bumped, t, "FLATTEN", 6, 1.0, [[0, 0, 21]], topo=topo)
    assert np.ptp(flat[near][:, 2]) < np.ptp(bumped[near][:, 2])


def test_grab_moves_what_is_under_the_first_point(ball):
    pts, t, _ = ball
    top = int(np.argmax(pts[:, 2]))
    out, rep = sc.stroke(pts, t, "GRAB", 4, 1.0, [pts[top], pts[top] + [0, 0, 5]])
    assert np.allclose(out[top] - pts[top], [0, 0, 5], atol=0.05)
    assert rep.dabs == 1


def test_symmetry_mirrors_the_stroke(ball):
    pts, t, topo = ball
    out, rep = sc.stroke(pts, t, "DRAW", 5, 0.5, [[12, 0, 16]], sym="X", topo=topo)
    moved = np.linalg.norm(out - pts, axis=1) > 1e-9
    assert np.any(moved & (pts[:, 0] > 5)) and np.any(moved & (pts[:, 0] < -5))
    assert rep.dabs == 2
    one, _ = sc.stroke(pts, t, "DRAW", 5, 0.5, [[12, 0, 16]], topo=topo)
    assert not np.any((np.linalg.norm(one - pts, axis=1) > 1e-9) & (pts[:, 0] < -5))


def test_mask_freezes(ball):
    pts, t, topo = ball
    mask = sc.sphere_mask(pts, (0, 0, 20), 3)
    frozen = mask >= 1 - 1e-12
    assert frozen.any()
    out, _ = sc.stroke(pts, t, "DRAW", 5, 0.8, TOP, mask=mask, topo=topo)
    assert np.allclose(out[frozen], pts[frozen])
    erased = sc.sphere_mask(pts, (0, 0, 20), 3, old=mask, mode="ERASE")
    assert erased.max() < 1e-12


@pytest.mark.parametrize("args,match", [(("BRUSHY", 5, 0.5), "unknown brush"), (("DRAW", 0, 0.5), "radius"),
                                        (("DRAW", 5, 2), "strength"), (("DRAW", 5, 0), "strength")])
def test_bad_strokes(ball, args, match):
    pts, t, _ = ball
    with pytest.raises(sc.SculptError, match=match):
        sc.stroke(pts, t, *args, TOP)
    with pytest.raises(sc.SculptError, match="symmetry"):
        sc.stroke(pts, t, "DRAW", 5, 0.5, TOP, sym="Q")


def test_big_mesh_is_fast():
    pts, t = mb.sphere(20, 720)  # about 260,000 triangles
    topo = sc.Topology.of(t, len(pts))
    path = np.array([[0, -10, 17.3], [0, 0, 20], [0, 10, 17.3]])
    for brush in ("DRAW", "SMOOTH", "INFLATE"):
        t0 = time.perf_counter()
        sc.stroke(pts, t, brush, 3, 0.5, path, topo=topo)
        assert time.perf_counter() - t0 < 2.0, brush  # about 0.05 s here


# ---- commands --------------------------------------------------------------------------------
@pytest.fixture
def head():
    p = Processor()
    for line in ("SPHERE, 0,0,0, 20", "NAME, LAST, head", "TOMESH, head", "REMESH, head, 2"):
        assert p.run(line).ok, line
    return p


def test_sculpt_command_and_undo(head):
    vol = head.evaluate("VOL(head)")
    r = head.run('STROKE, S1, "0,-6,19  0,0,20  0,6,19"')
    assert r.ok and "3 points" in r.message
    r = head.run("SCULPT, head, DRAW, 5, 0.5, S1, X")
    assert r.ok and "points moved" in r.message, r.message
    assert head.evaluate("VOL(head)") > vol
    assert head.run("UNDO").ok
    assert head.evaluate("VOL(head)") == pytest.approx(vol)
    assert not head.run("SCULPT, head, DRAW, 5, 0.5, S9").ok  # no such stroke
    assert "not near" in head.run('SCULPT, head, DRAW, 5, 0.5, "100,100,100"').message
    assert "not a mesh body" in Processor().run("BLOCK, 0,0,0, 1,1,1\nSCULPT, 1, DRAW, 1, 0.5, \"0,0,1\"").message


def test_mask_command(head):
    assert "frozen" in head.run("MASK, head, PAINT, 0,0,20, 8").message
    vol = head.evaluate("VOL(head)")
    r = head.run('SCULPT, head, DRAW, 4, 0.8, "0,0,20"')
    assert r.ok
    assert head.evaluate("VOL(head)") == pytest.approx(vol, rel=1e-4)  # frozen there: barely moved
    assert head.run("MASK, head, INVERT").ok
    assert head.run('SCULPT, head, DRAW, 4, 0.8, "0,0,20"').ok
    assert head.evaluate("VOL(head)") > vol + 1
    assert head.run("MASK, head, CLEAR").ok and not head.model.masks
    assert head.run("UNDO").ok and head.model.masks  # the mask is undone too
    assert not head.run("MASK, head, PAINT, 0,0,0").ok  # no radius
    assert not head.run("MASK, head, SPLAT").ok


def test_strokes_are_saved_with_the_project(head, tmp_path):
    head.strokes["S1"] = np.array([[0, -6, 19], [0, 0, 20], [0, 6, 19.0]])
    assert head.run("SCULPT, head, CLAY, 5, 0.5, S1, X").ok
    vol = head.evaluate("VOL(head)")
    path = str(tmp_path / "head.m3d")
    assert head.run(f'SAVE, "{path}"').ok
    q = Processor()
    r = q.run(f'OPEN, "{path}"')
    assert r.ok, r.message
    assert q.evaluate("VOL(head)") == pytest.approx(vol, rel=1e-6)
    assert list(q.strokes) == ["S1"]
    # a log saved on its own carries the strokes as STROKE lines
    text = head.script(standalone=True)
    assert text.startswith("! the sculpt strokes") and 'STROKE, S1, "0,-6,19' in text
    s = Processor()
    assert all(r.ok for r in s.run_script(text))
    assert s.evaluate("VOL(head)") == pytest.approx(vol, rel=1e-4)
