"""ARRAY: copies of a body in a row or grid, around an axis, or along a path.
PATTERN: repeat what the last steps did to a body (a feature pattern).

The original counts as the first copy and stays where it is; the new copies
are separate bodies (add FUSE to fuse them all into the original, or
CUT, target to cut them all from another body in one kernel call).
"""

from __future__ import annotations

import math

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from ..geometry import curves as cv
from ..geometry import robust
from ..geometry import sweep as sw
from ..lang.expr import ExprError, Vec, format_value
from ..lang.script import is_ident
from .processor import REGISTRY, Arg, CommandError, Processor, Raw, command

_N_ARGS = 16


def _values(p: Processor, raws: list[str], what: str = "ARRAY") -> tuple[list, set[str]]:
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
            raise CommandError(f"{what}: {exc}") from None
        if isinstance(v, Vec):
            vals.extend(list(v) + [0.0] * (3 - len(v)))
        elif isinstance(v, bool) or not isinstance(v, (int, float)):
            raise CommandError(f"{what}: expected a number or a point, got {format_value(v)}")
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


def _copies(shape, trsfs: list[gp_Trsf], what: str = "ARRAY") -> list:
    out = []
    for t in trsfs:
        mk = BRepBuilderAPI_Transform(shape, t, True)
        if not mk.IsDone():
            raise CommandError(f"{what}: kernel failed placing a copy")
        out.append(mk.Shape())
    return out


def _place(p: Processor, bid: int, trsfs: list[gp_Trsf], fuse: bool, what: str, cut: int | None = None) -> str:
    m = p.model
    shape = m.body(bid).shape
    copies = _copies(shape, trsfs)
    if cut is not None:
        from .handlers import _added, combine

        if cut == bid:
            raise CommandError("ARRAY: the body to cut from cannot be the body that is copied")
        if fuse:
            raise CommandError("ARRAY: give FUSE or CUT, not both")
        keep = (shape, m.body(bid).name, m.body(bid)) if m.keep else None
        cut_shape, maker = combine(p, "SUBTRACT", BRepAlgoAPI_Cut, m.body(cut).shape, [shape] + copies, cut)
        body = m.replace([cut, bid], cut_shape, maker)
        msg = _added(p, body, f"{what}: {len(copies) + 1} copies of body {bid} cut from body {cut} in one step")
        if keep:
            b = m.add_body(keep[0], "" if keep[1].startswith("body") else keep[1], like=keep[2])
            m.set_hidden(b.id, True)
            m.last_body = body.id
            msg += f"; kept the tool as hidden body {b.id}"
        return msg
    if not copies:
        return "ARRAY: nothing to add (count 1)"
    if fuse:
        from .handlers import combine

        fused, maker = combine(p, "UNION", BRepAlgoAPI_Fuse, shape, copies, bid, merge=True)
        body = m.replace([bid], fused, maker)
        return f"{what}: {len(copies) + 1} copies fused into body {body.id}"
    like = m.body(bid)
    ids = [m.add_body(c, like=like).id for c in copies]
    shown = f"{ids[0]}..{ids[-1]}" if len(ids) > 3 else ", ".join(map(str, ids))
    return f"{what}: body {bid} plus {len(ids)} cop{'y' if len(ids) == 1 else 'ies'} (bodies {shown})"


@command(
    "ARRAY",
    Arg("kind", str, help="LINEAR, POLAR or PATH"),
    Arg("b", Raw, help="the body to copy"),
    *[Arg(f"v{i}", Raw, "") for i in range(1, _N_ARGS + 1)],
    help="Copies of a body. LINEAR, b, n, dx,dy,dz [, n2, dx2,dy2,dz2] · "
         "POLAR, b, n [, angle [, x,y,z [, dx,dy,dz]]] · "
         "PATH, b, path, n [, twist_law [, scale_law [, MINTWIST/FRENET/FIXED]]]. Add FUSE to fuse them into one body, "
         "or CUT, target to cut all of them (the original too) from another body in one step: "
         "ARRAY, LINEAR, hole, 20, 5,0,0, 15, 0,5,0, CUT, plate.",
)
def array(p: Processor, kind, b, **raws):
    bid = p._body_arg(REGISTRY["ARRAY"], b)
    rest, cut = _cut_target(p, list(raws.values()))
    if kind == "PATH":
        return _path_array(p, bid, rest, cut)
    vals, words = _values(p, rest)
    fuse = "FUSE" in words
    if kind in ("LINEAR", "POLAR"):
        trsfs, what = _trsfs(kind, vals, "ARRAY")
        return _place(p, bid, trsfs, fuse, what, cut)
    raise CommandError("ARRAY: kind must be LINEAR, POLAR or PATH")


def _trsfs(kind: str, vals: list, what: str) -> tuple[list[gp_Trsf], str]:
    """The moves for the copies after the first, and a label, for LINEAR and POLAR."""
    if kind == "LINEAR":
        n = _count(_get(vals, 0, None, "the count"))
        d = [_get(vals, i, 0.0, "step") for i in (1, 2, 3)]
        n2 = _count(_get(vals, 4, 1.0, "second count"), "second count")
        d2 = [_get(vals, i, 0.0, "second step") for i in (5, 6, 7)]
        if n > 1 and d == [0, 0, 0]:
            raise CommandError(f"{what}: LINEAR needs a step (dx,dy,dz)")
        if n2 > 1 and d2 == [0, 0, 0]:
            raise CommandError(f"{what}: the second direction needs a step")
        trsfs = []
        for j in range(n2):
            for i in range(n):
                if i == j == 0:
                    continue
                t = gp_Trsf()
                t.SetTranslation(gp_Vec(*(i * d[k] + j * d2[k] for k in range(3))))
                trsfs.append(t)
        return trsfs, f"{what} LINEAR {n}" + (f" x {n2}" if n2 > 1 else "")
    n = _count(_get(vals, 0, None, "the count"))
    total = _get(vals, 1, 360.0, "angle")
    c = [_get(vals, i, 0.0, "centre") for i in (2, 3, 4)]
    ax = [_get(vals, i, dflt, "axis") for i, dflt in ((5, 0.0), (6, 0.0), (7, 1.0))]
    if ax == [0, 0, 0]:
        raise CommandError(f"{what}: the axis cannot be (0, 0, 0)")
    full = abs(abs(total) - 360) < 1e-9
    step = total / n if full else (total / (n - 1) if n > 1 else 0.0)
    axis = gp_Ax1(gp_Pnt(*c), gp_Dir(*ax))
    trsfs = []
    for i in range(1, n):
        t = gp_Trsf()
        t.SetRotation(axis, math.radians(i * step))
        trsfs.append(t)
    return trsfs, f"{what} POLAR {n}"


def _cut_target(p: Processor, raws: list[str]) -> tuple[list[str], int | None]:
    """Take ``CUT, target`` out of the arguments."""
    for i, r in enumerate(raws):
        if is_ident(r.strip()) and r.strip().upper() == "CUT":
            if i + 1 >= len(raws) or not raws[i + 1].strip():
                raise CommandError("ARRAY: CUT needs the body to cut from: ..., CUT, plate")
            return raws[:i] + raws[i + 2:], p._body_arg(REGISTRY["ARRAY"], raws[i + 1])
    return raws, None


def _path_array(p: Processor, bid: int, rest: list[str], cut: int | None = None) -> str:
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
    return _place(p, bid, trsfs, "FUSE" in words, f"ARRAY PATH {n}", cut)


# =============================================================================
# PATTERN: repeat a feature
# =============================================================================
# What the last steps did to a body is read off as two shapes: the material
# they added (after minus before) and the material they took away (before
# minus after). Copies of both are placed by the pattern and applied in two
# kernel calls, one fuse and one cut, however many copies there are. So any
# feature can be repeated (a hole, a pocket, a boss, a thread, engraved text),
# and 100 holes cost about as much as one.


def _body_before(p: Processor, bid: int, steps: int):
    """The shape body ``bid`` had before the last ``steps`` entries."""
    m = p.model
    before = p.state_before(steps)["model"]["bodies"]
    if bid in before:
        return before[bid].shape
    name = m.body(bid).name
    if not name.startswith("body"):
        for b in before.values():
            if b.name == name:
                return b.shape
    return None


@command(
    "PATTERN",
    Arg("kind", str, help="LINEAR or POLAR"),
    Arg("b", Raw, help="the body the feature was made on"),
    Arg("steps", Raw, help="how many of the last steps made the feature (1 for one HOLE, 2 for SEL then THREAD ...)"),
    *[Arg(f"v{i}", Raw, "") for i in range(1, 9)],
    help="Repeat what the last steps did to a body: PATTERN, LINEAR, plate, 1, n, dx,dy,dz [, n2, dx2,dy2,dz2] · "
         "PATTERN, POLAR, flange, 1, n [, angle [, x,y,z [, dx,dy,dz]]]. The material those steps added or took "
         "away is copied, and all copies go in at once, so 100 holes cost about as much as one: "
         "HOLE, plate, 5,5,10, 3 then PATTERN, LINEAR, plate, 1, 10, 8,0,0.",
)
def pattern(p: Processor, kind, b, steps, **raws):
    from .handlers import _added, combine

    m = p.model
    if kind not in ("LINEAR", "POLAR"):
        raise CommandError("PATTERN: kind must be LINEAR or POLAR")
    bid = p._body_arg(REGISTRY["PATTERN"], b)
    k = p._number(steps, "PATTERN steps")
    if not float(k).is_integer() or k < 1:
        raise CommandError("PATTERN: steps must be a whole number of at least 1")
    try:
        before = _body_before(p, bid, int(k))
    except CommandError as exc:
        raise CommandError(f"PATTERN: {exc}") from None
    if before is None:
        raise CommandError(f"PATTERN: body {bid} did not exist {int(k)} step{'s' if k > 1 else ''} ago; "
                           "pattern a feature made on a body, not a new body (use ARRAY for that)")
    vals, words = _values(p, list(raws.values()), "PATTERN")
    if words:
        raise CommandError(f"PATTERN: unexpected {', '.join(sorted(words))}")
    trsfs, what = _trsfs(kind, vals, "PATTERN")
    after = m.body(bid).shape
    added = BRepAlgoAPI_Cut(after, before)
    removed = BRepAlgoAPI_Cut(before, after)
    for op in (added, removed):
        op.SetRunParallel(True)
        op.Build()
        if not op.IsDone():
            raise CommandError("PATTERN: the kernel could not work out what those steps changed")
    vol_add, vol_rem = robust.volume(added.Shape()), robust.volume(removed.Shape())
    size = max(robust.volume(after), 1.0)
    if vol_add < 1e-9 * size and vol_rem < 1e-9 * size:
        raise CommandError(f"PATTERN: the last {int(k)} step{'s' if k > 1 else ''} did not change body {bid}")
    if not trsfs:
        return f"PATTERN: nothing to repeat (count 1)"
    shape = after
    maker = None
    notes = []
    if vol_add >= 1e-9 * size:
        shape, maker = combine(p, "UNION", BRepAlgoAPI_Fuse, shape, _copies(added.Shape(), trsfs, "PATTERN"), bid,
                               merge=True)
        notes.append("added material")
    if vol_rem >= 1e-9 * size:
        cut_shape, cut_maker = combine(p, "SUBTRACT", BRepAlgoAPI_Cut, shape, _copies(removed.Shape(), trsfs, "PATTERN"),
                                       bid)
        if maker is not None:  # two steps: replace twice so IDs carry through both
            m.replace([bid], shape, maker, same_id=True)
        shape, maker = cut_shape, cut_maker
        notes.append("removed material")
    body = m.replace([bid], shape, maker, same_id=True)
    return _added(p, body, f"{what}: {len(trsfs) + 1} copies of the {' and '.join(notes)} of the last "
                           f"{int(k)} step{'s' if k > 1 else ''} on body {bid}")
