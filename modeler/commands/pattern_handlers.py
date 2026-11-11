"""ARRAY: copies of a body in a row or grid, around an axis, or along a path.

The original counts as the first copy and stays where it is; the new copies
are separate bodies (add FUSE to fuse them all into the original).
"""

from __future__ import annotations

import math

from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from ..geometry import curves as cv
from ..geometry import sweep as sw
from ..lang.expr import ExprError, Vec, format_value
from ..lang.script import is_ident
from .processor import REGISTRY, Arg, CommandError, Processor, Raw, command

_N_ARGS = 16


def _values(p: Processor, raws: list[str]) -> tuple[list, set[str]]:
    """Evaluate the arguments: numbers and points (spread into numbers), empty
    arguments as None, and keywords (bare words such as FUSE) collected apart."""
    vals: list = []
    words: set[str] = set()
    raws = list(raws)
    while raws and not raws[-1].strip():
        raws.pop()
    for raw in raws:
        s = raw.strip()
        if not s:
            vals.append(None)
            continue
        if is_ident(s) and s.upper() in ("FUSE", "MINTWIST", "FRENET", "FIXED"):
            words.add(s.upper())
            continue
        try:
            v = p.evaluate(s)
        except ExprError as exc:
            raise CommandError(f"ARRAY: {exc}") from None
        if isinstance(v, Vec):
            vals.extend(list(v) + [0.0] * (3 - len(v)))
        elif isinstance(v, bool) or not isinstance(v, (int, float)):
            raise CommandError(f"ARRAY: expected a number or a point, got {format_value(v)}")
        else:
            vals.append(float(v))
    return vals, words


def _get(vals, i, default, what):
    v = vals[i] if i < len(vals) else None
    if v is None:
        if default is None:
            raise CommandError(f"ARRAY: {what} is required")
        return default
    return v


def _count(v, what="count") -> int:
    if not float(v).is_integer() or v < 1:
        raise CommandError(f"ARRAY: the {what} must be a whole number of at least 1")
    if v > 10000:
        raise CommandError("ARRAY: at most 10000 copies")
    return int(v)


def _place(p: Processor, bid: int, trsfs: list[gp_Trsf], fuse: bool, what: str) -> str:
    m = p.model
    shape = m.body(bid).shape
    copies = []
    for t in trsfs:
        mk = BRepBuilderAPI_Transform(shape, t, True)
        if not mk.IsDone():
            raise CommandError("ARRAY: kernel failed placing a copy")
        copies.append(mk.Shape())
    if not copies:
        return "ARRAY: nothing to add (count 1)"
    if fuse:
        from .handlers import _shape_list

        algo = BRepAlgoAPI_Fuse()
        algo.SetArguments(_shape_list([shape]))
        algo.SetTools(_shape_list(copies))
        if m.tolerance > 0:
            algo.SetFuzzyValue(m.tolerance)
        algo.Build()
        if not algo.IsDone():
            raise CommandError("ARRAY: the kernel could not fuse the copies")
        body = m.replace([bid], algo.Shape(), algo)
        return f"{what}: {len(copies) + 1} copies fused into body {body.id}"
    ids = [m.add_body(c).id for c in copies]
    shown = f"{ids[0]}..{ids[-1]}" if len(ids) > 3 else ", ".join(map(str, ids))
    return f"{what}: body {bid} plus {len(ids)} cop{'y' if len(ids) == 1 else 'ies'} (bodies {shown})"


@command(
    "ARRAY",
    Arg("kind", str, help="LINEAR, POLAR or PATH"),
    Arg("b", Raw, help="the body to copy"),
    *[Arg(f"v{i}", Raw, "") for i in range(1, _N_ARGS + 1)],
    help="Copies of a body. LINEAR, b, n, dx,dy,dz [, n2, dx2,dy2,dz2] · "
         "POLAR, b, n [, angle [, x,y,z [, dx,dy,dz]]] · "
         "PATH, b, path, n [, twist_law [, scale_law [, MINTWIST/FRENET/FIXED]]]. Add FUSE to fuse them into one body.",
)
def array(p: Processor, kind, b, **raws):
    bid = p._body_arg(REGISTRY["ARRAY"], b)
    rest = list(raws.values())
    if kind == "PATH":
        return _path_array(p, bid, rest)
    vals, words = _values(p, rest)
    fuse = "FUSE" in words
    if kind == "LINEAR":
        n = _count(_get(vals, 0, None, "the count"))
        d = [_get(vals, i, 0.0, "step") for i in (1, 2, 3)]
        n2 = _count(_get(vals, 4, 1.0, "second count"), "second count")
        d2 = [_get(vals, i, 0.0, "second step") for i in (5, 6, 7)]
        if n > 1 and d == [0, 0, 0]:
            raise CommandError("ARRAY: LINEAR needs a step (dx,dy,dz)")
        if n2 > 1 and d2 == [0, 0, 0]:
            raise CommandError("ARRAY: the second direction needs a step")
        trsfs = []
        for j in range(n2):
            for i in range(n):
                if i == j == 0:
                    continue
                t = gp_Trsf()
                t.SetTranslation(gp_Vec(*(i * d[k] + j * d2[k] for k in range(3))))
                trsfs.append(t)
        return _place(p, bid, trsfs, fuse, f"ARRAY LINEAR {n}" + (f" x {n2}" if n2 > 1 else ""))
    if kind == "POLAR":
        n = _count(_get(vals, 0, None, "the count"))
        total = _get(vals, 1, 360.0, "angle")
        c = [_get(vals, i, 0.0, "centre") for i in (2, 3, 4)]
        ax = [_get(vals, i, dflt, "axis") for i, dflt in ((5, 0.0), (6, 0.0), (7, 1.0))]
        if ax == [0, 0, 0]:
            raise CommandError("ARRAY: the axis cannot be (0, 0, 0)")
        full = abs(abs(total) - 360) < 1e-9
        step = total / n if full else (total / (n - 1) if n > 1 else 0.0)
        axis = gp_Ax1(gp_Pnt(*c), gp_Dir(*ax))
        trsfs = []
        for i in range(1, n):
            t = gp_Trsf()
            t.SetRotation(axis, math.radians(i * step))
            trsfs.append(t)
        return _place(p, bid, trsfs, fuse, f"ARRAY POLAR {n}")
    raise CommandError("ARRAY: kind must be LINEAR, POLAR or PATH")


def _path_array(p: Processor, bid: int, rest: list[str]) -> str:
    from .curve_handlers import _Law, _wire

    rest = [r for r in rest]
    while rest and not rest[-1].strip():
        rest.pop()
    words = {r.strip().upper() for r in rest if is_ident(r.strip()) and r.strip().upper() in ("FUSE", "MINTWIST", "FRENET", "FIXED")}
    rest = [r for r in rest if r.strip().upper() not in words or not is_ident(r.strip())]
    if len(rest) < 2:
        raise CommandError("ARRAY: PATH needs a path and a count: ARRAY, PATH, b, path, n")
    path = p._body_arg(REGISTRY["ARRAY"], rest[0])
    n = _count(p._number(rest[1], "ARRAY count"))
    twist = _Law(p, rest[2] if len(rest) > 2 else "", "ARRAY twist", 0.0)
    scale = _Law(p, rest[3] if len(rest) > 3 else "", "ARRAY scale", 1.0)
    mode = next((w for w in ("FRENET", "FIXED", "MINTWIST") if w in words), "MINTWIST")
    pw = _wire(p, path, "the ARRAY path")
    ps = sw.PathSampler(pw)
    closed = ps.closed
    stations = n if closed else max(n - 1, 1)
    try:
        fs = sw.frames(ps, stations, mode)
    except cv.CurveError as exc:
        raise CommandError(f"ARRAY: {exc}") from None
    f0 = fs[0]
    trsfs = []
    for i in range(1, n):
        t_ = i / stations
        s = scale(t_)
        if s <= 0:
            raise CommandError(f"ARRAY: the scale must stay above 0 (it is {s:g} at t = {t_:g})")
        M, off = sw._station_matrix(f0, fs[i], twist(t_), s, s, 0.0, 0.0, s)
        k = s
        R = [[v / k for v in row] for row in M]
        rot = gp_Trsf()
        rot.SetValues(R[0][0], R[0][1], R[0][2], off[0], R[1][0], R[1][1], R[1][2], off[1],
                      R[2][0], R[2][1], R[2][2], off[2])
        if abs(k - 1) > 1e-12:
            sc = gp_Trsf()
            sc.SetScale(gp_Pnt(0, 0, 0), k)
            rot = rot.Multiplied(sc)
        trsfs.append(rot)
    return _place(p, bid, trsfs, "FUSE" in words, f"ARRAY PATH {n}")
