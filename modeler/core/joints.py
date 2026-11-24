"""Joints that stay solved (PLAN item 69): the solver, with no kernel and no commands.

A joint ties a frame on one body (A, the fixed side) to a frame on another (B,
the moving side). A frame is (origin, z, x) in world coordinates; when a body
moves, the frames on it move with it (commands/handlers.py ``_move_frames``).
Each joint leaves some motions free:

===========  ================================================================
FIXED        nothing
REVOLUTE     the turn about A's z (the joint's value, degrees)
SLIDER       the slide along A's z (the value, a length)
CYLINDRICAL  the turn and the slide about and along A's z (value: the turn)
BALL         every turn about A's origin
PLANAR       sliding in A's xy plane and turning about z
===========  ================================================================

Couplings tie two joint values together: GEAR (q2 = -ratio * q1), BELT
(q2 = ratio * q1), RACK (slide = radius * turn in radians), SCREW (one
cylindrical joint: slide = lead * turns). Each coupling holds from the values
the joints had when it was made.

The solver moves every body that is the moving side of some joint (the other
bodies stay where they are) by the smallest change that makes every joint
true: a least-squares problem in the six motions of each such body, with the
held joint values and limits as more equations. So a chain, a closed loop (a
four-bar linkage) and gears turning each other are all solved the same way,
after any edit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

KINDS = ("FIXED", "REVOLUTE", "SLIDER", "CYLINDRICAL", "BALL", "PLANAR")
COUPLINGS = ("GEAR", "BELT", "RACK", "SCREW")
# what each kind leaves free, said in words (JOINTS lists it)
FREE = {"FIXED": "nothing", "REVOLUTE": "a turn about its axis", "SLIDER": "a slide along its axis",
        "CYLINDRICAL": "a turn about and a slide along its axis", "BALL": "every turn about its centre",
        "PLANAR": "sliding in its plane and a turn about its normal"}
TOL = 1e-6  # a joint is true when it is off by less than this (length or radians)
LIMIT_WEIGHT = 1e3
STAY_WEIGHT = 1e-4  # free motions stay as they are: the smallest change wins

Frame = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]


@dataclass
class Joint:
    name: str
    kind: str  # a KINDS word or a COUPLINGS word
    fixed: int = 0  # body IDs (0 for a coupling)
    moving: int = 0
    a: Frame | None = None
    b: Frame | None = None
    value: float | None = None  # held value (degrees for turns, length for SLIDER); None: free
    lo: float | None = None  # limits on the value
    hi: float | None = None
    # couplings: the two joints, the ratio (GEAR, BELT), radius (RACK) or lead (SCREW),
    # and the values of the joints when the coupling was made
    joints: tuple[str, ...] = ()
    ratio: float = 1.0
    start: tuple[float, ...] = ()
    step: int = 0  # the history entry that made it
    suppressed: bool = False

    def copy(self) -> "Joint":
        import copy as _c

        return _c.copy(self)


# ---- small vector help -------------------------------------------------------------
def _v(a) -> np.ndarray:
    return np.asarray(a, dtype=float)


def unit(a) -> np.ndarray:
    a = _v(a)
    n = np.linalg.norm(a)
    return a / n if n > 1e-15 else a


def across(z) -> np.ndarray:
    """A unit direction square to z, always the same one for the same z."""
    z = unit(z)
    helper = np.array([1.0, 0.0, 0.0]) if abs(z[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    x = helper - z * np.dot(helper, z)
    return unit(x)


def frame(origin, z, x=None) -> Frame:
    z = unit(z)
    x = across(z) if x is None else unit(_v(x) - z * np.dot(_v(x), z))
    return (tuple(map(float, origin)), tuple(map(float, z)), tuple(map(float, x)))


def rotation(rv) -> np.ndarray:
    """The rotation matrix of a rotation vector (axis * angle in radians)."""
    rv = _v(rv)
    th = np.linalg.norm(rv)
    if th < 1e-15:
        return np.eye(3)
    k = rv / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * (K @ K)


def matrix_rv(R) -> np.ndarray:
    """The rotation vector of a rotation matrix."""
    c = max(-1.0, min(1.0, (np.trace(R) - 1) / 2))
    th = math.acos(c)
    if th < 1e-12:
        return np.zeros(3)
    if math.pi - th < 1e-6:
        # half a turn: the axis is the column of R + I with the most length
        M = (R + np.eye(3)) / 2
        k = unit(M[:, int(np.argmax(np.diag(M)))])
        return k * th
    w = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / (2 * math.sin(th))
    return w * th


class Move:
    """A rigid move: x -> R (x - c) + c + t."""

    def __init__(self, R=None, t=None, c=None):
        self.R = np.eye(3) if R is None else R
        self.t = np.zeros(3) if t is None else _v(t)
        self.c = np.zeros(3) if c is None else _v(c)

    def point(self, p) -> np.ndarray:
        return self.R @ (_v(p) - self.c) + self.c + self.t

    def dir(self, d) -> np.ndarray:
        return self.R @ _v(d)

    def frame(self, f: Frame) -> Frame:
        return (tuple(self.point(f[0])), tuple(unit(self.dir(f[1]))), tuple(unit(self.dir(f[2]))))

    @property
    def angle(self) -> float:
        return float(np.linalg.norm(matrix_rv(self.R)))

    def axis_point_angle(self):
        """(axis, a point on it, angle in degrees, shift along the axis): the same move as a
        turn about a line then a slide along it (for ROTATE and MOVE)."""
        rv = matrix_rv(self.R)
        th = float(np.linalg.norm(rv))
        total = self.t + self.c - self.R @ self.c  # x -> R x + total
        if th < 1e-12:
            return None, None, 0.0, total
        k = rv / th
        along = np.dot(total, k)
        perp = total - along * k
        # the point on the axis: solve (I - R) p = perp in the plane square to k
        A = np.eye(3) - self.R
        p, *_ = np.linalg.lstsq(A, perp, rcond=None)
        p = p - np.dot(p, k) * k
        return k, p, math.degrees(th), along * k


# ---- one joint ---------------------------------------------------------------------
def relative(a: Frame, b: Frame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """B's origin, z and x written in A's frame."""
    oa, za, xa = _v(a[0]), unit(a[1]), unit(a[2])
    ya = np.cross(za, xa)
    M = np.vstack([xa, ya, za])  # world -> A
    return M @ (_v(b[0]) - oa), M @ unit(b[1]), M @ unit(b[2])


def measure(kind: str, a: Frame, b: Frame) -> dict[str, float]:
    """The joint's own values now: turn (degrees) and slide."""
    o, z, x = relative(a, b)
    out: dict[str, float] = {}
    if kind in ("REVOLUTE", "CYLINDRICAL", "PLANAR"):
        out["turn"] = math.degrees(math.atan2(x[1], x[0]))
    if kind in ("SLIDER", "CYLINDRICAL"):
        out["slide"] = float(o[2])
    if kind == "PLANAR":
        out["x"], out["y"] = float(o[0]), float(o[1])
    return out


def value_of(kind: str, a: Frame, b: Frame) -> float | None:
    """The single value a joint is held at: its turn, or its slide for a SLIDER."""
    m = measure(kind, a, b)
    if kind == "SLIDER":
        return m["slide"]
    return m.get("turn")


def _wrap(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


def residuals(j: Joint, a: Frame, b: Frame) -> list[float]:
    """How far the joint is from true (0s when it is): lengths and radians."""
    o, z, x = relative(a, b)
    k = j.kind
    out: list[float] = []
    if k in ("FIXED", "REVOLUTE", "BALL"):
        out += list(o)
    elif k in ("SLIDER", "CYLINDRICAL"):
        out += [o[0], o[1]]
    elif k == "PLANAR":
        out += [o[2]]
    if k != "BALL":
        out += [z[0], z[1]]  # z along z
    if k in ("FIXED", "SLIDER"):
        out += [x[1], x[2]]  # no turn about z either (x[2] is 0 once z is right)
    v = value_of(k, a, b) if k in ("REVOLUTE", "SLIDER", "CYLINDRICAL") else None
    if v is not None:
        turn = k != "SLIDER"
        if j.value is not None:
            d = _wrap(v - j.value) if turn else v - j.value
            out.append(math.radians(d) if turn else d)
        for lim, sign in ((j.lo, -1.0), (j.hi, 1.0)):
            if lim is None:
                continue
            over = sign * (v - lim)  # turns are measured in -180..180, like the limits
            out.append(LIMIT_WEIGHT * max(0.0, math.radians(over) if turn else over))
    return out


def coupling_residual(c: Joint, values: dict[str, float]) -> float:
    q1, q2 = values[c.joints[0]], values[c.joints[-1]]
    s1, s2 = c.start[0], c.start[-1]
    if c.kind == "GEAR":
        return math.radians(_wrap((q2 - s2) + c.ratio * (q1 - s1)))
    if c.kind == "BELT":
        return math.radians(_wrap((q2 - s2) - c.ratio * (q1 - s1)))
    if c.kind == "RACK":  # q1 a turn (degrees), q2 a slide: slide = radius * angle
        return (q2 - s2) - c.ratio * math.radians(q1 - s1)
    # SCREW: one cylindrical joint, slide = lead * turns
    return values["slide:" + c.joints[0]] - s2 - c.ratio * (q1 - s1) / 360.0


# ---- the whole set -------------------------------------------------------------------
@dataclass
class Solved:
    moves: dict[int, Move] = field(default_factory=dict)  # body ID -> the move that solves it
    worst: dict[str, float] = field(default_factory=dict)  # joint name -> how far off it stays
    free: int = 0  # motions left free over all moving bodies
    ok: bool = True


def _active(joints: list[Joint]) -> list[Joint]:
    return [j for j in joints if not j.suppressed]


def moving_bodies(joints: list[Joint]) -> list[int]:
    return sorted({j.moving for j in _active(joints) if j.kind in KINDS and j.moving})


def solve(joints: list[Joint], centres: dict[int, tuple] | None = None, only: set[int] | None = None,
          keep: set[int] | None = None, sizes: dict[int, float] | None = None) -> Solved:
    """The moves of the moving bodies that make every joint true.

    ``centres``: a point inside each body (the moves turn about it, for good numbers).
    ``only``: solve only the joints that reach these bodies (the group a new joint joins).
    ``keep``: bodies moved by hand; they move as little as possible and the rest follow.
    ``sizes``: about how big each body is, so a turn counts as the distance it moves the
    body's far side (a small shift then wins over a big turn)."""
    if keep:
        # first the bodies moved by hand stay exactly where they were put; only when the
        # others cannot make every joint true alone are they moved too
        got = _solve(joints, centres, only, sizes, frozen=set(keep))
        if got.ok and got.moves:
            return got
    return _solve(joints, centres, only, sizes)


def _solve(joints, centres, only, sizes, frozen: set[int] | None = None) -> Solved:
    from scipy.optimize import least_squares

    act = [j for j in _active(joints) if j.kind in KINDS and j.a and j.b]
    if only:
        group = set(only)
        grew = True
        while grew:  # every joint linked to the group, through either side
            grew = False
            for j in act:
                if (j.fixed in group or j.moving in group) and not {j.fixed, j.moving} <= group:
                    group |= {j.fixed, j.moving}
                    grew = True
        act = [j for j in act if j.fixed in group or j.moving in group]
    couplings = [c for c in _active(joints) if c.kind in COUPLINGS]
    by_name = {j.name: j for j in act}
    couplings = [c for c in couplings if all(n in by_name for n in c.joints)]
    every = sorted({j.moving for j in act})
    bodies = [b for b in every if b not in (frozen or ())]
    if not bodies:
        return Solved(ok=not frozen)
    idx = {b: i for i, b in enumerate(bodies)}
    cs = {b: _v((centres or {}).get(b, _frame_centre(act, b))) for b in bodies}

    def moves_of(x) -> dict[int, Move]:
        return {b: Move(rotation(x[6 * i:6 * i + 3]), x[6 * i + 3:6 * i + 6], cs[b]) for b, i in idx.items()}

    def placed(j: Joint, mv: dict[int, Move]) -> tuple[Frame, Frame]:
        a = mv[j.fixed].frame(j.a) if j.fixed in mv else j.a
        b = mv[j.moving].frame(j.b) if j.moving in mv else j.b
        return a, b

    def f(x, stay=STAY_WEIGHT) -> np.ndarray:
        mv = moves_of(x)
        out: list[float] = []
        vals: dict[str, float] = {}
        for j in act:
            a, b = placed(j, mv)
            out += residuals(j, a, b)
            if couplings:
                m = measure(j.kind, a, b)
                vals[j.name] = m.get("turn", m.get("slide", 0.0)) if j.kind != "SLIDER" else m["slide"]
                if "slide" in m:
                    vals["slide:" + j.name] = m["slide"]
        for c in couplings:
            out.append(coupling_residual(c, vals))
        if stay:
            out += list(stay * x * weights)
        return np.asarray(out, dtype=float)

    weights = np.ones(6 * len(bodies))
    for b, i in idx.items():
        weights[6 * i:6 * i + 3] = 100.0 * max(1.0, (sizes or {}).get(b, 1.0))  # turns cost more than shifts
    x0 = np.zeros(6 * len(bodies))
    # first the smallest change (free motions stay put), then exactly true from there
    x = least_squares(f, x0, method="lm", xtol=1e-15, ftol=1e-15, gtol=1e-15, max_nfev=4000).x
    x = least_squares(lambda y: f(y, 0.0), x, method="trf", xtol=1e-15, ftol=1e-15, gtol=1e-15,
                      max_nfev=2000).x
    mv = moves_of(x)
    out = Solved(moves=mv)
    for j in act:
        a, b = placed(j, mv)
        r = residuals(j, a, b)
        out.worst[j.name] = float(max((abs(v) for v in r), default=0.0))
    if couplings:
        vals = {}
        for j in act:
            a, b = placed(j, mv)
            m = measure(j.kind, a, b)
            vals[j.name] = m.get("turn", m.get("slide", 0.0)) if j.kind != "SLIDER" else m["slide"]
            if "slide" in m:
                vals["slide:" + j.name] = m["slide"]
        for c in couplings:
            out.worst[c.name] = abs(coupling_residual(c, vals))
    out.ok = all(v <= TOL * 10 for v in out.worst.values())
    whole = dict(mv)
    for b in every:
        if b not in whole:
            whole[b] = Move(c=_v((centres or {}).get(b, _frame_centre(act, b))))
    out.free = free_motions(act, couplings, whole, {b: whole[b].c for b in whole})
    return out


def _frame_centre(joints: list[Joint], b: int) -> tuple:
    pts = [j.b[0] for j in joints if j.moving == b] + [j.a[0] for j in joints if j.fixed == b]
    return tuple(np.mean(np.asarray(pts, dtype=float), axis=0)) if pts else (0.0, 0.0, 0.0)


def free_motions(act: list[Joint], couplings: list[Joint], mv: dict[int, Move], cs) -> int:
    """How many motions the moving bodies still have, held values and limits aside
    (the rank the joints leave of 6 per body)."""
    bodies = sorted(mv)
    if not bodies:
        return 0
    idx = {b: i for i, b in enumerate(bodies)}
    free_kinds = [j.copy() for j in act]
    for j in free_kinds:
        j.value = j.lo = j.hi = None  # what the joints allow, not where they are held

    def f(x):
        moved = {b: Move(rotation(x[6 * i:6 * i + 3]) @ mv[b].R, mv[b].t + x[6 * i + 3:6 * i + 6], cs[b])
                 for b, i in idx.items()}
        out: list[float] = []
        vals: dict[str, float] = {}
        for j in free_kinds:
            a = moved[j.fixed].frame(j.a) if j.fixed in moved else j.a
            b = moved[j.moving].frame(j.b) if j.moving in moved else j.b
            out += residuals(j, a, b)
            m = measure(j.kind, a, b)
            vals[j.name] = m.get("turn", m.get("slide", 0.0)) if j.kind != "SLIDER" else m["slide"]
            if "slide" in m:
                vals["slide:" + j.name] = m["slide"]
        for c in couplings:
            out.append(coupling_residual(c, vals))
        return np.asarray(out, dtype=float)

    n = 6 * len(bodies)
    x0 = np.zeros(n)
    f0 = f(x0)
    if not len(f0):
        return n
    h = 1e-6
    J = np.zeros((len(f0), n))
    for k in range(n):
        e = np.zeros(n)
        e[k] = h
        J[:, k] = (f(e) - f(-e)) / (2 * h)
    rank = int(np.linalg.matrix_rank(J, tol=1e-6))
    return n - rank
