"""ARRAY: copies of a body in a row or grid, around an axis, or along a path.
PATTERN: repeat what the last steps did to a body (a feature pattern): in a row or grid, round an
axis, along a curve, at points, filling a face, or mirrored (PLAN item 97), leaving out the copies
named after SKIP.

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


PATTERN_KINDS = ("LINEAR", "POLAR", "CURVE", "POINTS", "FILL", "MIRROR")
MAX_FILL = 5000  # copies FILL may make


def _bbox(shapes) -> tuple[tuple, tuple] | None:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    for s in shapes:
        if s is not None and not s.IsNull():
            BRepBndLib.Add_s(s, box)
    if box.IsVoid():
        return None
    lo, hi = box.CornerMin(), box.CornerMax()
    return (lo.X(), lo.Y(), lo.Z()), (hi.X(), hi.Y(), hi.Z())


def _take_skip(p: Processor, raws: list[str]) -> tuple[list[str], set[int]]:
    """Take ``SKIP, k, k ...`` (or SKIP, "3 5 7") off the end of the arguments: copy numbers to leave out
    (the original is copy 1)."""
    up = [r.strip().upper() for r in raws]
    if "SKIP" not in up:
        return raws, set()
    k = up.index("SKIP")
    out: set[int] = set()
    for r in raws[k + 1:]:
        t = r.strip().strip("\"'")
        for w in t.replace(";", " ").replace(",", " ").split():
            try:
                v = p.evaluate(w)
            except ExprError as exc:
                raise CommandError(f"PATTERN: SKIP: {exc}") from None
            if not isinstance(v, (int, float)) or not float(v).is_integer() or v < 2:
                raise CommandError(f"PATTERN: SKIP takes copy numbers from 2 up (1 is the original), got {w}")
            out.add(int(v))
    if not out:
        raise CommandError("PATTERN: SKIP needs the copy numbers to leave out: ..., SKIP, 3, 5")
    return raws[:k], out


def _translation(d) -> gp_Trsf:
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(*d))
    return t


def _curve_trsfs(p: Processor, rest: list[str], ref) -> tuple[list[gp_Trsf], str]:
    """CURVE, curve, n [, TURN]: n copies spread along a curve body, moved (or also turned) with it."""
    from .curve_handlers import _wire

    words = {r.strip().upper() for r in rest if is_ident(r.strip())}
    turn = "TURN" in words
    rest = [r for r in rest if r.strip() and r.strip().upper() != "TURN"]
    if len(rest) < 2:
        raise CommandError("PATTERN: CURVE needs a curve and a count: PATTERN, CURVE, b, steps, curve, n [, TURN]")
    cid = p._body_arg(REGISTRY["PATTERN"], rest[0])
    n = _count(p._number(rest[1], "PATTERN count"))
    ps = sw.PathSampler(_wire(p, cid, "the PATTERN curve"))
    stations = n if ps.closed else max(n - 1, 1)
    trsfs = []
    if turn:
        try:
            fs = sw.frames(ps, stations, "MINTWIST")
        except cv.CurveError as exc:
            raise CommandError(f"PATTERN: {exc}") from None
        for i in range(1, n):
            M, off = sw._station_matrix(fs[0], fs[i], 0.0, 1.0, 1.0, 0.0, 0.0, 1.0)
            t = gp_Trsf()
            t.SetValues(M[0][0], M[0][1], M[0][2], off[0], M[1][0], M[1][1], M[1][2], off[1],
                        M[2][0], M[2][1], M[2][2], off[2])
            trsfs.append(t)
    else:
        p0 = ps.at(0.0)[0]
        for i in range(1, n):
            q = ps.at(ps.length * i / stations)[0]
            trsfs.append(_translation(tuple(q[k] - p0[k] for k in range(3))))
    return trsfs, f"PATTERN CURVE {n}" + (" turned" if turn else "")


def _points_trsfs(p: Processor, rest: list[str], ref) -> tuple[list[gp_Trsf], str]:
    """POINTS, sketch | (x,y,z), (x,y,z) ...: a copy at each point. A sketch's points (SPOINT, or its
    circles' centres) move the feature in the sketch's plane from where it is; with a list, the first
    point is where the feature is now and the others are where the copies go."""
    rest = [r for r in rest if r.strip()]
    if not rest:
        raise CommandError("PATTERN: POINTS needs a sketch with points, or points: PATTERN, POINTS, b, steps, "
                           "(10,10,5), (30,10,5) (the first is where the feature is now)")
    sk = p.model.sketches.get(rest[0].strip().upper()) if len(rest) == 1 and is_ident(rest[0].strip()) else None
    moves: list[tuple] = []
    if sk is not None:
        geos = list(sk.geos.values())
        chosen = ([g for g in geos if g.kind == "POINT" and not g.construction]
                  or [g for g in geos if g.kind == "POINT"] or [g for g in geos if g.kind == "CIRCLE"])
        if not chosen:
            raise CommandError(f"PATTERN: sketch {sk.name} has no points (SPOINT) or circles to place copies at")
        u0, v0, _w = sk.frame.local(ref)
        for g in chosen:
            u, v = sk.pt(g.pts["P"] if g.kind == "POINT" else g.pts["C"])
            moves.append(sk.frame.direction((u - u0, v - v0, 0.0)))
    else:
        from .curve_handlers import _points

        pts, _closed = _points(p, rest, "PATTERN POINTS", allow_close=False)
        if len(pts) < 2:
            raise CommandError("PATTERN: POINTS needs the feature's own point first, then where the copies go")
        moves = [tuple(q[k] - pts[0][k] for k in range(3)) for q in pts[1:]]
    trsfs = [_translation(d) for d in moves if math.sqrt(sum(c * c for c in d)) > 1e-9]  # not onto itself
    return trsfs, f"PATTERN POINTS {len(trsfs) + 1}"


def _fill_trsfs(p: Processor, rest: list[str], ref, feat_box) -> tuple[list[gp_Trsf], str]:
    """FILL, face, spacing [, margin [, HEX]]: copies on a grid (or staggered rows) at the spacing, over
    a flat face, kept where the whole feature stays inside the face by the margin."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.GeomAbs import GeomAbs_SurfaceType
    from OCP.gp import gp_Pnt2d
    from OCP.TopAbs import TopAbs_IN, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    from ..geometry.recognize import _static

    words = {r.strip().upper() for r in rest if is_ident(r.strip())}
    hexa = "HEX" in words
    rest = [r for r in rest if r.strip() and r.strip().upper() not in ("HEX", "GRID")]
    if len(rest) < 2:
        raise CommandError("PATTERN: FILL needs a face and a spacing: PATTERN, FILL, b, steps, face, spacing "
                           "[, margin [, HEX]]")
    fid = int(p._number(rest[0], "PATTERN face"))
    gap = p._number(rest[1], "PATTERN spacing")
    if gap <= 0:
        raise CommandError("PATTERN: the spacing must be more than 0")
    try:
        face = _static(TopoDS, "Face")(p.model.entity_shape("FACE", fid))
    except Exception:
        raise CommandError(f"PATTERN: there is no face {fid}") from None
    ad = BRepAdaptor_Surface(face)
    if ad.GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
        raise CommandError(f"PATTERN: FILL needs a flat face (face {fid} is curved)")
    pl = ad.Plane()
    o, xd, yd = pl.Location(), pl.XAxis().Direction(), pl.YAxis().Direction()
    org = (o.X(), o.Y(), o.Z())
    ax = (xd.X(), xd.Y(), xd.Z())
    ay = (yd.X(), yd.Y(), yd.Z())

    def uv(q):
        d = (q[0] - org[0], q[1] - org[1], q[2] - org[2])
        return (sum(d[k] * ax[k] for k in range(3)), sum(d[k] * ay[k] for k in range(3)))

    lo, hi = feat_box
    corners = [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    r0 = uv(ref)
    reach = max(math.hypot(*(a - b for a, b in zip(uv(c), r0))) for c in corners) / math.sqrt(2)
    margin = p._number(rest[2], "PATTERN margin") if len(rest) > 2 else 0.0
    keep_off = reach + margin  # a copy's middle must be this far inside the edge
    box = _bbox([face])
    fcorners = [(x, y, z) for x in (box[0][0], box[1][0]) for y in (box[0][1], box[1][1]) for z in (box[0][2], box[1][2])]
    us = [uv(c)[0] for c in fcorners]
    vs = [uv(c)[1] for c in fcorners]
    pitch = gap * (math.sqrt(3) / 2 if hexa else 1.0)
    j0, j1 = math.floor((min(vs) - r0[1]) / pitch) - 1, math.ceil((max(vs) - r0[1]) / pitch) + 1
    i0, i1 = math.floor((min(us) - r0[0]) / gap) - 1, math.ceil((max(us) - r0[0]) / gap) + 1
    if (i1 - i0 + 1) * (j1 - j0 + 1) > 50 * MAX_FILL:
        raise CommandError(f"PATTERN: a spacing of {gap:g} gives too many copies on face {fid}; use a bigger one")
    wires = []  # the outline and any holes: a copy keeps off all of them
    ex = TopExp_Explorer(face, TopAbs_WIRE)
    while ex.More():
        wires.append(ex.Current())
        ex.Next()
    trsfs = []
    for j in range(j0, j1 + 1):
        shift = gap / 2 if hexa and j % 2 else 0.0
        for i in range(i0, i1 + 1):
            du, dv = i * gap + shift, j * pitch
            if abs(du) < 1e-12 and abs(dv) < 1e-12:
                continue  # the original
            q = tuple(ref[k] + du * ax[k] + dv * ay[k] for k in range(3))
            # the plane's parameters are its own x and y
            if BRepClass_FaceClassifier(face, gp_Pnt2d(*uv(q)), 1e-7).State() != TopAbs_IN:
                continue
            if keep_off > 0:  # measured in the face's plane (the feature's middle may sit below it)
                u, v = uv(q)
                on = tuple(org[k] + u * ax[k] + v * ay[k] for k in range(3))
                vx = BRepBuilderAPI_MakeVertex(gp_Pnt(*on)).Vertex()
                if any((dd := BRepExtrema_DistShapeShape(vx, w)).IsDone() and dd.Value() < keep_off - 1e-9
                       for w in wires):
                    continue
            trsfs.append(_translation(tuple(du * ax[k] + dv * ay[k] for k in range(3))))
            if len(trsfs) >= MAX_FILL:
                raise CommandError(f"PATTERN: more than {MAX_FILL} copies; use a bigger spacing")
    return trsfs, f"PATTERN FILL {len(trsfs) + 1}" + (" staggered" if hexa else "")


def _mirror_trsfs(p: Processor, rest: list[str]) -> tuple[list[gp_Trsf], str]:
    from OCP.gp import gp_Ax2

    from .feature_handlers import plane_ref

    rest = [r for r in rest if r.strip()]
    if len(rest) != 1:
        raise CommandError("PATTERN: MIRROR needs a plane: PATTERN, MIRROR, b, steps, plane (XY, YZ, ZX or a datum)")
    d = plane_ref(p, rest[0], "PATTERN")
    t = gp_Trsf()
    t.SetMirror(gp_Ax2(gp_Pnt(*d.origin), gp_Dir(*d.z)))
    return [t], f"PATTERN MIRROR in {d.name}"


def _apply(t: gp_Trsf, q) -> tuple:
    pt = gp_Pnt(*q)
    pt.Transform(t)
    return (pt.X(), pt.Y(), pt.Z())


@command(
    "PATTERN",
    Arg("kind", str, help="LINEAR, POLAR, CURVE, POINTS, FILL or MIRROR"),
    Arg("b", Raw, help="the body the feature was made on"),
    Arg("steps", Raw, help="how many of the last steps made the feature (1 for one HOLE, 2 for SEL then THREAD ...)"),
    *[Arg(f"v{i}", Raw, "") for i in range(1, 25)],
    help="Repeat what the last steps did to a body: PATTERN, LINEAR, plate, 1, n, dx,dy,dz [, n2, dx2,dy2,dz2] · "
         "POLAR, flange, 1, n [, angle [, x,y,z [, dx,dy,dz]]] · CURVE, b, 1, curve, n [, TURN] (spread along a "
         "curve, turned with it after TURN) · POINTS, b, 1, sketch or (x,y,z), (x,y,z) ... (at a sketch's points; in a list "
         "the first point is where the feature is now) · FILL, b, 1, face, spacing [, margin [, HEX]] (over a flat "
         "face, for vents and perforations) · MIRROR, b, 1, plane. "
         "Add SKIP, 3, 5 to leave copies out (the original is copy 1). The material those steps added or took "
         "away is copied, and all copies go in at once, so 100 holes cost about as much as one: "
         "HOLE, plate, 5,5,10, 3 then PATTERN, LINEAR, plate, 1, 10, 8,0,0.",
)
def pattern(p: Processor, kind, b, steps, **raws):
    from .handlers import _added, combine

    m = p.model
    if kind not in PATTERN_KINDS:
        raise CommandError(f"PATTERN: kind must be one of {', '.join(PATTERN_KINDS)}"
                           + ("; along a curve it is CURVE" if kind == "PATH" else ""))
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
    rest, skip = _take_skip(p, list(raws.values()))
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
    changed = [s for s, v in ((added.Shape(), vol_add), (removed.Shape(), vol_rem)) if v >= 1e-9 * size]
    feat_box = _bbox(changed)
    ref = tuple((feat_box[0][i] + feat_box[1][i]) / 2 for i in range(3))  # the feature's middle
    if kind in ("LINEAR", "POLAR"):
        vals, words = _values(p, rest, "PATTERN")
        if words:
            raise CommandError(f"PATTERN: unexpected {', '.join(sorted(words))}")
        trsfs, what = _trsfs(kind, vals, "PATTERN")
    elif kind == "CURVE":
        trsfs, what = _curve_trsfs(p, rest, ref)
    elif kind == "POINTS":
        trsfs, what = _points_trsfs(p, rest, ref)
    elif kind == "FILL":
        trsfs, what = _fill_trsfs(p, rest, ref, feat_box)
    else:
        trsfs, what = _mirror_trsfs(p, rest)
    numbered = list(enumerate(trsfs, 2))  # copy 1 is the original
    bad = sorted(n for n in skip if n > len(trsfs) + 1)
    if bad:
        raise CommandError(f"PATTERN: SKIP {', '.join(map(str, bad))}: there are only {len(trsfs) + 1} copies")
    kept = [(n, t) for n, t in numbered if n not in skip]
    p.give_report("PATTERN", {"body": bid, "kind": kind, "copies": [{"n": 1, "at": [round(c, 6) for c in ref]}] + [
        {"n": n, "at": [round(c, 6) for c in _apply(t, ref)], **({"skipped": True} if n in skip else {})}
        for n, t in numbered], "skipped": sorted(skip), "size": round(max(
            feat_box[1][i] - feat_box[0][i] for i in range(3)), 6)})
    copies_of = getattr(p, "pattern_copies", None)
    if copies_of is not None:
        copies_of[bid] = (p.entry_uid, [(n, _apply(t, ref)) for n, t in numbered],
                          max(feat_box[1][i] - feat_box[0][i] for i in range(3)), sorted(skip))
    trsfs = [t for _n, t in kept]
    if not trsfs:
        return "PATTERN: nothing to repeat (count 1" + (", the rest skipped)" if skip else ")")
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
    if skip:
        what += f" (skipped {', '.join(map(str, sorted(skip)))})"
    return _added(p, body, f"{what}: {len(trsfs) + 1} copies of the {' and '.join(notes)} of the last "
                           f"{int(k)} step{'s' if k > 1 else ''} on body {bid}")


def skip_command(p: Processor, bid: int, faces: list[int]) -> tuple[int, str] | None:
    """(copy number, the HIST, EDIT line) that leaves out the copy of the body's last PATTERN the picked
    faces are on, or None when they are on no copy (a right click on a copy, PLAN item 97)."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    from ..ai.describe import entry_number
    from ..lang.script import split_args

    got = getattr(p, "pattern_copies", {}).get(bid)
    if not got or not faces:
        return None
    uid, copies, size, skipped = got
    n_entry = entry_number(p, uid)
    if n_entry is None or n_entry > p.cursor:
        return None
    props = GProp_GProps()
    try:
        for f in faces:
            BRepGProp.SurfaceProperties_s(p.model.entity_shape("FACE", f), props)
    except Exception:  # noqa: BLE001 - a face that is gone
        return None
    c = props.CentreOfMass()
    at = (c.X(), c.Y(), c.Z())
    best = min(copies, key=lambda nc: math.dist(nc[1], at))
    if math.dist(best[1], at) > max(size, 1e-6) or best[0] in skipped:
        return None
    text = p.history[n_entry - 1].text
    args = split_args(text)
    up = [a.strip().upper() for a in args]
    if "SKIP" in up:
        k = up.index("SKIP")
        have = sorted({*skipped, best[0]})
        args = args[:k] + ["SKIP", *map(str, have)]
    else:
        args = args + ["SKIP", str(best[0])]
    line = ", ".join(a.strip() for a in args)
    return best[0], f'HIST, EDIT, {n_entry}, "{line}"'
