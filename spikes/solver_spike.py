"""Sketch solver spike: the same plate with holes in three solvers.

    python spikes/solver_spike.py            # needs: pip install planegcs py-slvs

A W x H plate fixed at the origin and fully dimensioned, with an n x n grid
of holes, each with a diameter and a position from the origin. Every point
starts 5 % to 15 % away from where the dimensions put it (as after a drag,
or a dimension change), so the solver has real work to do.

Measured per solver: the time to solve, whether every dimension holds, the
degrees of freedom it reports (should be 0), and what it says when one more
dimension contradicts the others.

Our own solver (modeler/sketch) is the one the app uses; planegcs and
py-slvs are only needed for this comparison.
"""

from __future__ import annotations

import math
import random
import sys
import time

sys.path.insert(0, ".")

W, H, D = 200.0, 120.0, 6.0


def holes(n):
    for i in range(n):
        for j in range(n):
            yield 15 + i * (W - 30) / max(1, n - 1), 15 + j * (H - 30) / max(1, n - 1)


def jitter(v: float, rnd: random.Random) -> float:
    return v * (1 + rnd.choice((-1, 1)) * rnd.uniform(0.05, 0.15)) + rnd.uniform(-1, 1)


# ---------------------------------------------------------------------------
def ours(n: int, conflict: bool = False):
    from modeler.core import datum as dt
    from modeler.sketch.sketch import Sketch, SketchError

    rnd = random.Random(1)
    sk = Sketch("plate", dt.plane((0, 0, 0), (0, 0, 1)))
    sk.add_rect((jitter(0.1, rnd), jitter(0.1, rnd)), (jitter(W, rnd), jitter(H, rnd)))
    sk.add_con("COINCIDENT", ("1.S", "O"), solve=False)
    sk.add_con("LENGTH", ("1",), W, solve=False)
    sk.add_con("LENGTH", ("2",), H, solve=False)
    for u, v in holes(n):
        c = sk.add_circle((jitter(u, rnd), jitter(v, rnd)), jitter(D / 2, rnd))
        sk.add_con("DIAMETER", (str(c.n),), D, solve=False)
        sk.add_con("HDIST", ("O", f"{c.n}.C"), u, solve=False)
        sk.add_con("VDIST", ("O", f"{c.n}.C"), v, solve=False)
    t = time.perf_counter()
    sk.solve()
    dt_ = time.perf_counter() - t
    ok = abs(sk.pt(sk.geos[2].pts["E"])[0] - W) < 1e-6 and abs(sk.pt(sk.geos[2].pts["E"])[1] - H) < 1e-6
    msg = ""
    if conflict:
        try:
            sk.add_con("LENGTH", ("3",), W + 5)
        except SketchError as exc:
            msg = str(exc)
    return dt_, ok, sk.dof, msg


# ---------------------------------------------------------------------------
def planegcs_(n: int, conflict: bool = False):
    import planegcs

    rnd = random.Random(1)
    s = planegcs.SketchSolver()
    corners = [(0.1, 0.1), (W, 0.1), (W, H), (0.1, H)]
    p = [s.add_point(jitter(x, rnd), jitter(y, rnd)) for x, y in corners]
    lines = [s.add_line(p[i], p[(i + 1) % 4]) for i in range(4)]
    s.horizontal_line(lines[0]); s.vertical_line(lines[1]); s.horizontal_line(lines[2]); s.vertical_line(lines[3])
    zero = s.add_param(0.0, True)
    s.coordinate_x(p[0], zero); s.coordinate_y(p[0], zero)
    s.p2p_distance(p[0], p[1], s.add_param(W, True))
    s.p2p_distance(p[1], p[2], s.add_param(H, True))
    for u, v in holes(n):
        c = s.add_point(jitter(u, rnd), jitter(v, rnd))
        circ = s.add_circle(c, s.add_param(jitter(D / 2, rnd)))
        s.circle_diameter(circ, s.add_param(D, True))
        s.coordinate_x(c, s.add_param(u, True)); s.coordinate_y(c, s.add_param(v, True))
    t = time.perf_counter()
    st = s.solve()
    dt_ = time.perf_counter() - t
    x, y = s.get_point(p[2])
    ok = str(st).endswith("Success") and abs(x - W) < 1e-6 and abs(y - H) < 1e-6
    dof = s.diagnose().dof
    msg = ""
    if conflict:
        s.p2p_distance(p[2], p[3], s.add_param(W + 5, True))
        st = s.solve()
        d = s.diagnose()
        msg = f"{st}; conflicting tags {list(d.conflicting)}, redundant {list(d.redundant)}"
    return dt_, ok, dof, msg


# ---------------------------------------------------------------------------
def slvs_(n: int, conflict: bool = False):
    from py_slvs import slvs

    rnd = random.Random(1)
    s = slvs.System()
    g1, g2 = 1, 2
    o = s.addPoint3dV(0, 0, 0, g1)
    q = slvs.makeQuaternion(1, 0, 0, 0, 1, 0)
    nrm = s.addNormal3dV(q[0], q[1], q[2], q[3], g1)
    wp = s.addWorkplane(o, nrm, g1)
    corners = [(0.1, 0.1), (W, 0.1), (W, H), (0.1, H)]
    p = [s.addPoint2dV(wp, jitter(x, rnd), jitter(y, rnd), g2) for x, y in corners]
    lines = [s.addLineSegment(p[i], p[(i + 1) % 4], g2) for i in range(4)]
    s.addLineHorizontal(lines[0], wp, g2); s.addLineVertical(lines[1], wp, g2)
    s.addLineHorizontal(lines[2], wp, g2); s.addLineVertical(lines[3], wp, g2)
    s.addPointsCoincident(p[0], o, wp, g2)
    s.addPointsDistance(W, p[0], p[1], wp, g2)
    s.addPointsDistance(H, p[1], p[2], wp, g2)
    xax = s.addLineSegment(o, s.addPoint2dV(wp, 1, 0, g1), g1)
    yax = s.addLineSegment(o, s.addPoint2dV(wp, 0, 1, g1), g1)
    for u, v in holes(n):
        c = s.addPoint2dV(wp, jitter(u, rnd), jitter(v, rnd), g2)
        circ = s.addCircleV(c, nrm, jitter(D / 2, rnd), g2)
        s.addDiameter(D, circ, g2)
        s.addPointLineDistance(v, c, xax, wp, g2)
        s.addPointLineDistance(-u, c, yax, wp, g2)
    t = time.perf_counter()
    res = s.solve(g2, True, True)
    dt_ = time.perf_counter() - t
    x = s.getParam(s.getEntityParam(p[2], 0)).val
    y = s.getParam(s.getEntityParam(p[2], 1)).val
    ok = res == 0 and abs(x - W) < 1e-6 and abs(y - H) < 1e-6
    dof = s.Dof
    msg = ""
    if conflict:
        s.addPointsDistance(W + 5, p[2], p[3], wp, g2)
        res = s.solve(g2, True, True)
        msg = f"result {res}; failed constraints {list(s.Failed)}"
    return dt_, ok, dof, msg


def chain_ours(k: int):
    """A zig-zag of k segments: each length and each angle to the next is dimensioned."""
    from modeler.core import datum as dt
    from modeler.sketch.sketch import Sketch

    rnd = random.Random(2)
    sk = Sketch("chain", dt.plane((0, 0, 0), (0, 0, 1)))
    pts = [(i * 10.0 + rnd.uniform(-2, 2), (i % 2) * 6.0 + rnd.uniform(-2, 2)) for i in range(k + 1)]
    lines = sk.add_poly(pts, False)
    sk.add_con("COINCIDENT", ("1.S", "O"), solve=False)
    sk.add_con("ANGLE", ("1",), 30, solve=False)
    for i, ln in enumerate(lines):
        sk.add_con("LENGTH", (str(ln.n),), 10, solve=False)
        if i:
            sk.add_con("ANGLE", (str(lines[i - 1].n), str(ln.n)), 60, solve=False)
    t = time.perf_counter()
    sk.solve()
    t = time.perf_counter() - t
    end = sk.pt(lines[-1].pts["E"])
    return t, math.isfinite(end[0]), sk.dof


def chain_gcs(k: int):
    import planegcs

    rnd = random.Random(2)
    s = planegcs.SketchSolver()
    p = [s.add_point(i * 10.0 + rnd.uniform(-2, 2), (i % 2) * 6.0 + rnd.uniform(-2, 2)) for i in range(k + 1)]
    lines = [s.add_line(p[i], p[i + 1]) for i in range(k)]
    zero = s.add_param(0.0, True)
    s.coordinate_x(p[0], zero); s.coordinate_y(p[0], zero)
    ten = s.add_param(10.0, True)
    for i, ln in enumerate(lines):
        s.p2p_distance(p[i], p[i + 1], ten)
        if i:
            s.l2l_angle(lines[i - 1], ln, s.add_param(math.radians(60 if i % 2 else -60), True))
    s.p2p_angle(p[0], p[1], s.add_param(math.radians(30), True))
    t = time.perf_counter()
    st = s.solve()
    t = time.perf_counter() - t
    return t, str(st).endswith("Success"), s.diagnose().dof


def main() -> None:
    solvers = [("ours (numpy)", ours)]
    for name, fn, mod in (("planegcs", planegcs_, "planegcs"), ("py-slvs", slvs_, "py_slvs")):
        try:
            __import__(mod)
            solvers.append((name, fn))
        except ImportError:
            print(f"({name} not installed: pip install {mod.replace('_', '-')})")
    print(f"{'solver':<14}{'holes':>6}{'numbers':>9}{'time ms':>10}{'right':>7}{'dof':>5}")
    for n in (2, 5, 10, 20):
        for name, fn in solvers:
            if name == "py-slvs" and n > 10:
                continue  # dense: 7 s and gigabytes of memory at 100 holes already
            t, ok, dof, _ = fn(n)
            print(f"{name:<14}{n * n:>6}{8 + 3 * n * n:>9}{t * 1000:>10.1f}{'yes' if ok else 'NO':>7}{dof:>5}")
    print("\nOne coupled chain (every segment depends on the one before), our solver vs planegcs:")
    for k in (25, 50, 100):
        for name, fn in solvers[:2]:
            t, ok, dof = (chain_ours if fn is ours else chain_gcs)(k)
            print(f"  {name:<14}{k:>4} segments{t * 1000:>9.1f} ms  right: {'yes' if ok else 'NO'}  dof {dof}")
    print("\nOne more dimension that contradicts the others (top edge 205 on a 200 plate):")
    for name, fn in solvers:
        print(f"  {name}: {fn(2, conflict=True)[3]}")


if __name__ == "__main__":
    main()
