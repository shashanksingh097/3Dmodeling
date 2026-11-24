"""JOINT and JOINTS: joints that stay solved (PLAN item 69).

``JOINT, kind, <fixed item>, <moving item> [, value] [, LIMITS, lo, hi] [, FLIP] [, REVERSE]``
ties the body of the second item to the body of the first. Items are written
as in ``MATE`` (``FACE, 12`` · ``EDGE, 4`` · ``VERTEX, 9`` · ``DATUM, name``),
or the two picked ones are used. The moving body is first put against the
fixed one (axes in line, faces together, points together), and that place is
the joint's zero. The value, when given, holds the joint there: degrees for
REVOLUTE, CYLINDRICAL and PLANAR, a length for SLIDER. Give it as a parameter
(``A = 30`` then ``JOINT, REVOLUTE, ..., A``) and ``DRIVE``, ``MOTION`` and the
Motion window move the mechanism. With no value the joint is free. A positive
value moves the body away from the fixed one (a lid opens, a drawer comes out);
``REVERSE`` turns that round, ``FLIP`` puts the body against the other way (as
in ``MATE``).

``JOINT, GEAR|BELT, J1, J2, ratio`` · ``JOINT, RACK, J1, J2, radius`` ·
``JOINT, SCREW, J1, lead`` tie joint values together.

After every joint, and after any ``MOVE`` or ``ROTATE`` of a body in a joint,
the solver (core/joints.py) moves the other bodies so every joint is true
again: turn the crank and the linkage follows. ``JOINTS`` lists every joint,
its value, what it leaves free and any that fight, as data.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
from OCP.gp import gp_Trsf

from ..core import joints as J
from ..lang.expr import fmt_num
from .feature_handlers import _Args
from .processor import Arg, CommandError, Processor, Raw, command

ALIASES = {"HINGE": "REVOLUTE", "REV": "REVOLUTE", "PIN": "REVOLUTE", "PRISMATIC": "SLIDER", "SLIDE": "SLIDER",
           "CYL": "CYLINDRICAL", "SPHERICAL": "BALL", "RIGID": "FIXED", "WELD": "FIXED", "PLANE": "PLANAR"}
_SOLVING = "_joint_solving"


def _unit_word(kind: str) -> str:
    return "" if kind == "SLIDER" else " deg"


# ---- frames follow their bodies ------------------------------------------------------
def _moved_frame(f: J.Frame, trsf: gp_Trsf) -> J.Frame:
    from OCP.gp import gp_Dir, gp_Pnt

    o = gp_Pnt(*f[0]).Transformed(trsf)
    z = gp_Dir(*f[1]).Transformed(trsf)
    x = gp_Dir(*f[2]).Transformed(trsf)
    return ((o.X(), o.Y(), o.Z()), (z.X(), z.Y(), z.Z()), (x.X(), x.Y(), x.Z()))


def move_joint_frames(m, bid: int, trsf: gp_Trsf) -> None:
    """The joint frames on a body go where the body goes (called by every move)."""
    out = []
    for j in m.joints:
        if j.kind in J.KINDS and bid in (j.fixed, j.moving):
            j = dataclasses.replace(
                j, a=_moved_frame(j.a, trsf) if j.fixed == bid else j.a,
                b=_moved_frame(j.b, trsf) if j.moving == bid else j.b)
        out.append(j)
    m.joints = out


def _trsf(mv: J.Move) -> gp_Trsf:
    R, t, c = mv.R, mv.t, mv.c
    tr = t + c - R @ c
    g = gp_Trsf()
    g.SetValues(R[0, 0], R[0, 1], R[0, 2], tr[0], R[1, 0], R[1, 1], R[1, 2], tr[1], R[2, 0], R[2, 1], R[2, 2], tr[2])
    return g


def _sizes(p: Processor, ids) -> dict[int, float]:
    return {b: _boxes(p, [b]).get(b, ((0, 0, 0), 1.0))[1] for b in ids}


def _centres(p: Processor, ids) -> dict[int, tuple]:
    return {b: c for b, (c, _r) in _boxes(p, ids).items()}


def _boxes(p: Processor, ids) -> dict[int, tuple]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    out = {}
    for b in ids:
        if b in p.model.bodies:
            box = Bnd_Box()
            BRepBndLib.Add_s(p.model.body(b).shape, box)
            if not box.IsVoid():
                lo, hi = box.CornerMin(), box.CornerMax()  # (Get() does not convert in OCP 8)
                c = ((lo.X() + hi.X()) / 2, (lo.Y() + hi.Y()) / 2, (lo.Z() + hi.Z()) / 2)
                out[b] = (c, lo.Distance(hi) / 2)
    return out


def solve_now(p: Processor, only: set[int] | None = None, keep: set[int] | None = None) -> J.Solved:
    """Solve the joints and move the bodies; ``keep``: bodies moved by hand, which the
    solver moves as little as it can (the rest of the linkage follows them)."""
    m = p.model
    if getattr(p, _SOLVING, False):
        return J.Solved()
    live = [j for j in m.joints if j.kind in J.COUPLINGS or (j.fixed in m.bodies and j.moving in m.bodies)]
    bodies = J.moving_bodies(live)
    if not bodies:
        return J.Solved()
    setattr(p, _SOLVING, True)
    try:
        got = J.solve(live, _centres(p, bodies), only=only, keep=keep, sizes=_sizes(p, bodies))
        from .handlers import _transform

        for b, mv in got.moves.items():
            if mv.angle < 1e-12 and float(np.linalg.norm(mv.t)) < 1e-12:
                continue
            _transform(p, b, _trsf(mv), "moved", copy=False)
    finally:
        setattr(p, _SOLVING, False)
    return got


def _fights(got: J.Solved) -> str:
    bad = [f"{n} (off by {fmt_num(round(v, 6))})" for n, v in got.worst.items() if v > J.TOL * 10]
    return ", ".join(bad)


def after_move(p: Processor, bid: int) -> str:
    """A body in a joint was moved by hand: the linkage follows (or the move is pulled back
    onto its joints)."""
    m = p.model
    if getattr(p, _SOLVING, False) or not any(bid in (j.fixed, j.moving) for j in m.joints if j.kind in J.KINDS):
        return ""
    got = solve_now(p, only={bid}, keep={bid})
    bad = _fights(got)
    if bad:
        p.warn(f"joints that cannot all be true after this move: {bad}")
    moved = sorted(b for b, mv in got.moves.items() if b != bid and (mv.angle > 1e-9 or np.linalg.norm(mv.t) > 1e-9))
    return f"; the joints moved bod{'ies' if len(moved) != 1 else 'y'} {', '.join(map(str, moved))}" if moved else ""


# ---- JOINT -----------------------------------------------------------------------------
def _new_name(m) -> str:
    used = {j.name.upper() for j in m.joints}
    n = 1
    while f"J{n}" in used:
        n += 1
    return f"J{n}"


def _snap_kind(kind: str, a, b) -> str:
    axial = ("AXIS", "CIRCLE")
    if kind in ("REVOLUTE", "CYLINDRICAL", "SLIDER") and a.what in axial and b.what in axial:
        return "COINCIDENT" if a.what == b.what == "CIRCLE" else "CONCENTRIC"
    return "COINCIDENT"


@command(
    "JOINT",
    Arg("kind", str, help="FIXED, REVOLUTE, SLIDER, CYLINDRICAL, BALL, PLANAR, or GEAR, BELT, RACK, SCREW"),
    *[Arg(f"a{i}", Raw, "") for i in range(1, 10)],
    help="A joint that stays solved: JOINT, REVOLUTE, EDGE, 12, EDGE, 40 [, A] [, LIMITS, -90, 90] hinges the "
         "body of the second item on the first; the value (degrees, or a length for SLIDER) holds it, best as a "
         "parameter so DRIVE and MOTION move it. Kinds: FIXED, REVOLUTE, SLIDER, CYLINDRICAL, BALL, PLANAR. "
         "Couplings: JOINT, GEAR, J1, J2, ratio · BELT, J1, J2, ratio · RACK, J1, J2, radius · SCREW, J1, lead. "
         "Items as in MATE, or the two picked. A positive value moves the body away from the fixed one (a lid "
         "opens); REVERSE turns that round. After any move the solver keeps every joint true; JOINTS lists them.",
)
def joint(p: Processor, kind, **raws):
    kind = ALIASES.get(kind, kind)
    words = [raws[f"a{i}"].strip() for i in range(1, 10)]
    while words and not words[-1]:
        words.pop()
    if kind in J.COUPLINGS:
        return _coupling(p, kind, words)
    if kind not in J.KINDS:
        raise CommandError(f"JOINT: the kind is one of {', '.join(J.KINDS + J.COUPLINGS)}, not {kind!r}")
    from . import mate_handlers as mh
    from .handlers import _transform

    flip = reverse = False
    while words and words[-1].upper() in ("FLIP", "REVERSE"):
        if words.pop().upper() == "FLIP":
            flip = True
        else:
            reverse = True
    lo = hi = None
    up = [w.upper() for w in words]
    if "LIMITS" in up:
        k = up.index("LIMITS")
        lim = _Args(p, "JOINT", words[k + 1:])
        lo, hi = lim.num("the lower limit"), lim.num("the upper limit")
        lim.done()
        if lo > hi:
            lo, hi = hi, lo
        words = words[:k]
    a = _Args(p, "JOINT", words)
    head = words[0].upper() if words else ""
    try:
        if not words or head not in ("FACE", "EDGE", "VERTEX", "DATUM", "XY", "YZ", "ZX"):
            ia, ib = mh._selected(p)
        else:
            ia = mh._read_item(p, a, "fixed")
            ib = mh._read_item(p, a, "moving")
    except CommandError as exc:
        raise CommandError(str(exc).replace("MATE:", "JOINT:", 1)) from None
    value = a.num("the value") if a.more() else None
    a.done()
    if kind in ("FIXED", "BALL") and value is not None:
        raise CommandError(f"JOINT: a {kind} joint takes no value")
    if ib.body is None:
        raise CommandError(f"JOINT: {ib.label} is not on a body, so nothing can move")
    fixed = ia.body if ia.body is not None else 0
    if fixed == ib.body:
        raise CommandError(f"JOINT: {ia.label} and {ib.label} are on the same body ({ib.body})")
    if kind == "BALL" and (ia.what not in ("POINT", "CIRCLE") or ib.what not in ("POINT", "CIRCLE")):
        raise CommandError("JOINT: a BALL joint needs two points or round edges (their centres meet)")
    if kind in ("SLIDER", "REVOLUTE", "CYLINDRICAL") and (ia.what == "POINT" or ib.what == "POINT"):
        raise CommandError(f"JOINT: a {kind} joint needs an axis or a flat face on each side, not a point")
    m = p.model
    # put the moving body against the fixed one; that place is the joint's zero
    t, _what = mh._solve(_snap_kind(kind, ia, ib), ia, ib, None, flip)
    setattr(p, _SOLVING, True)
    try:
        _transform(p, ib.body, t, "moved", copy=False)
    finally:
        setattr(p, _SOLVING, False)
    z = ia.dir if ia.what != "POINT" else (0.0, 0.0, 1.0)
    if kind in ("REVOLUTE", "CYLINDRICAL", "SLIDER") and fixed:
        z = _opening(p, kind, fixed, ib.body, ia.point, z)
    if reverse:
        z = tuple(-c for c in z)
    fa = J.frame(ia.point, z)
    name = _new_name(m)
    j = J.Joint(name, kind, fixed, ib.body, fa, fa, value=value, lo=lo, hi=hi, step=p.entry_index + 1)
    if fixed == 0:  # a datum or base plane: the joint holds the body to the world
        j = dataclasses.replace(j, fixed=-1)
    m.joints = [*m.joints, j]
    got = solve_now(p, only={ib.body})
    out = f"{name}: {kind.lower()} joint, body {ib.body} on " + (f"body {fixed}" if fixed else ia.label)
    now = _value_now(p, name)
    if now is not None:
        out += f", at {fmt_num(round(now, 6))}{_unit_word(kind)}" + (" (held)" if value is not None else " (free)")
    if lo is not None:
        out += f", limits {fmt_num(lo)} to {fmt_num(hi)}"
    out += f"; {got.free} motion{'s' if got.free != 1 else ''} left free"
    bad = _fights(got)
    if bad:
        p.warn(f"JOINT: these joints cannot all be true: {bad}. JOINTS lists them; a joint that repeats "
               "another (two hinges on one axis are fine) or holds a value the others do not allow fights")
    return out


def _opening(p: Processor, kind: str, fixed: int, moving: int, at, z) -> tuple:
    """The axis direction that makes a positive value move the moving body away from the
    fixed one (a lid opens, a drawer comes out); REVERSE turns it round."""
    cs = _centres(p, [fixed, moving])
    if fixed not in cs or moving not in cs:
        return tuple(z)
    cf, cm = np.asarray(cs[fixed]), np.asarray(cs[moving])
    zz, o = J.unit(z), np.asarray(at, dtype=float)

    def far(sign: float) -> float:
        if kind == "SLIDER":
            q = cm + sign * zz
        else:
            q = J.Move(J.rotation(zz * math.radians(5.0) * sign), c=o).point(cm)
        return float(np.linalg.norm(q - cf))

    return tuple(z) if far(1.0) >= far(-1.0) else tuple(-c for c in z)


def _coupling(p: Processor, kind: str, words: list[str]) -> str:
    m = p.model
    a = _Args(p, "JOINT", words)
    names = [a.word("the first joint").upper()]
    if kind != "SCREW":
        names.append(a.word("the second joint").upper())
    what = {"GEAR": "the ratio", "BELT": "the ratio", "RACK": "the pitch radius", "SCREW": "the lead"}[kind]
    ratio = a.num(what)
    a.done()
    by = {j.name.upper(): j for j in m.joints}
    js = []
    for n in names:
        if n not in by or by[n].kind not in J.KINDS:
            raise CommandError(f"JOINT: there is no joint {n} (JOINTS lists them)")
        js.append(by[n])
    need = {"GEAR": (("REVOLUTE", "CYLINDRICAL"), ("REVOLUTE", "CYLINDRICAL")),
            "BELT": (("REVOLUTE", "CYLINDRICAL"), ("REVOLUTE", "CYLINDRICAL")),
            "RACK": (("REVOLUTE", "CYLINDRICAL"), ("SLIDER",)), "SCREW": (("CYLINDRICAL",),)}[kind]
    for j, ok in zip(js, need):
        if j.kind not in ok:
            raise CommandError(f"JOINT: {kind} needs {' or '.join(ok)} joints; {j.name} is {j.kind}")
    start = []
    for j in js:
        meas = J.measure(j.kind, j.a, j.b)
        start.append(meas["slide"] if j.kind == "SLIDER" else meas["turn"])
    if kind == "SCREW":
        start = [J.measure("CYLINDRICAL", js[0].a, js[0].b)["turn"], J.measure("CYLINDRICAL", js[0].a, js[0].b)["slide"]]
    name = _new_name(m)
    c = J.Joint(name, kind, joints=tuple(j.name for j in js), ratio=ratio, start=tuple(start), step=p.entry_index + 1)
    m.joints = [*m.joints, c]
    got = solve_now(p, only={j.moving for j in js})
    bad = _fights(got)
    if bad:
        p.warn(f"JOINT: {kind} cannot hold with the other joints: {bad}")
    return f"{name}: {kind.lower()} {' and '.join(names)}, {what[4:]} {fmt_num(ratio)}; {got.free} motion" \
           f"{'s' if got.free != 1 else ''} left free"


def _value_now(p: Processor, name: str) -> float | None:
    j = next((x for x in p.model.joints if x.name == name), None)
    if j is None or j.kind not in J.KINDS:
        return None
    return J.value_of(j.kind, j.a, j.b)


# ---- JOINTS ---------------------------------------------------------------------------
def rows(p: Processor) -> tuple[list[dict], J.Solved]:
    m = p.model
    live = [j for j in m.joints if j.kind in J.COUPLINGS or (j.moving in m.bodies and (j.fixed in m.bodies or j.fixed == -1))]
    ids = J.moving_bodies(live)
    got = J.solve(live, _centres(p, ids), sizes=_sizes(p, ids)) if live else J.Solved()
    out = []
    for j in m.joints:
        r: dict = {"name": j.name, "kind": j.kind, "step": j.step}
        if j.kind in J.KINDS:
            r.update(fixed=j.fixed, moving=j.moving, free=J.FREE[j.kind], held=j.value,
                     limits=None if j.lo is None else [j.lo, j.hi])
            r["now"] = J.measure(j.kind, j.a, j.b)
            r["off"] = float(max((abs(v) for v in J.residuals(j, j.a, j.b)), default=0.0))
            r["broken"] = j.moving not in m.bodies or (j.fixed not in m.bodies and j.fixed != -1)
        else:
            r.update(joints=list(j.joints), ratio=j.ratio)
            r["off"] = got.worst.get(j.name, 0.0)
        r["fights"] = got.worst.get(j.name, 0.0) > J.TOL * 10
        out.append(r)
    return out, got


@command(
    "JOINTS",
    Arg("what", str, "", "SOLVE: solve them again now; empty: list them"),
    logged=False,
    help="List every joint: kind, bodies, value now, held value, limits, what it leaves free, and joints that "
         "fight (cannot all be true). JOINTS, SOLVE solves them again and moves the bodies.",
)
def joints_(p: Processor, what):
    if what == "SOLVE":
        got = solve_now(p)
        bad = _fights(got)
        return "joints solved" + (f"; these fight: {bad}" if bad else "") + f"; {got.free} motions left free"
    if what:
        raise CommandError("JOINTS: give SOLVE, or nothing to list them")
    data, got = rows(p)
    p.give_report("JOINTS", {"joints": data, "free": got.free, "solved": got.ok})
    if not data:
        return "no joints (JOINT, REVOLUTE, <fixed item>, <moving item> makes one)"
    lines = [f"{len(data)} joint{'s' if len(data) != 1 else ''}, {got.free} motion{'s' if got.free != 1 else ''} "
             f"left free" + ("" if got.ok else "; some fight")]
    for r in data:
        if r["kind"] in J.KINDS:
            now = ", ".join(f"{k} {fmt_num(round(v, 4))}" for k, v in r["now"].items())
            held = "" if r["held"] is None else f", held at {fmt_num(r['held'])}"
            lim = "" if not r["limits"] else f", limits {fmt_num(r['limits'][0])} to {fmt_num(r['limits'][1])}"
            line = (f"  {r['name']}: {r['kind'].lower()}, body {r['moving']} on "
                    f"{'the world' if r['fixed'] == -1 else 'body ' + str(r['fixed'])}"
                    f"{' (' + now + ')' if now else ''}{held}{lim}; free: {r['free']}")
            if r["broken"]:
                line += " - BROKEN: a body it holds is gone"
        else:
            line = f"  {r['name']}: {r['kind'].lower()} {' and '.join(r['joints'])}, {fmt_num(r['ratio'])}"
        if r["fights"]:
            line += f" - FIGHTS (off by {fmt_num(round(r['off'], 6))})"
        lines.append(line)
    return "\n".join(lines)

