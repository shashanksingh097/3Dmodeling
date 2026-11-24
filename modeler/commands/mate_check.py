"""Assembly checks: mates that repeat or fight, what each copy can still do, and coordinate
systems that move with a body.

Every MATE step is kept (``model.mates``) with what it joined. ``MATES`` measures each one again on
the finished assembly and says:

* **holds** or **does not hold** (a later mate on the same copy moved it away: they *fight*, and
  the later step is named);
* **repeats**: it fixes nothing an earlier mate on that copy had not fixed already (the earlier
  one is named), or only part of what it fixes is new;
* for each copy that was mated, the ways it can still move: slides along a direction, turns about
  an axis.

The freedoms come from the mates as small motions: a copy moving by a twist (v, w) moves a point x
by v + w x x. A face against a face fixes the motion along the normal and the two tilts; two axes
in line fix the two sideways motions and the two tilts; and so on. The motions no mate fixes (the
null space of those rows) are what is left.

``CSYS, name, body, x,y,z [, nx,ny,nz [, angle]]`` or ``CSYS, name, FACE, id [, angle]`` makes a
coordinate system (a datum plane with its X axis) that moves with the body; ``MATE, FRAME, a, b``
puts one on another, which fixes everything.
"""

from __future__ import annotations

import math

import numpy as np

from ..core import datum as dt
from ..core.model import ModelError
from .processor import Arg, CommandError, Processor, Raw, Text, command

TOL_ANG = 1e-6  # radians
ROWS_TOL = 1e-9


# ---- items again --------------------------------------------------------------------------------

def item(p: Processor, ref: tuple):
    """The Item a mate record points at, measured now (None when it is gone)."""
    from .feature_handlers import plane_ref
    from .mate_handlers import _item_of_datum, _item_of_entity

    try:
        if ref[0] == "DATUM":
            return _item_of_datum(plane_ref(p, ref[1], "MATES") if ref[1].upper() in dt.BASE_PLANES
                                  else p.model.datum(ref[1]), f"datum {ref[1]}", p.model.frames)
        return _item_of_entity(p, ref[0], int(ref[1]))
    except (CommandError, ModelError):
        return None


def _datum(p: Processor, ref: tuple):
    if ref[0] != "DATUM":
        return None
    from .feature_handlers import plane_ref

    try:
        return plane_ref(p, ref[1], "MATES") if ref[1].upper() in dt.BASE_PLANES else p.model.datum(ref[1])
    except (CommandError, ModelError):
        return None


def _scale(p: Processor) -> float:
    from ..geometry import robust

    sizes = [robust.diagonal(b.shape) for b in p.model.bodies.values()]
    return max([1.0, *sizes])


def error(p: Processor, rec: dict) -> float | None:
    """How far the mate is from holding (a length; angles count as angle x size). None: an item is gone."""
    a, b = item(p, rec["a"]), item(p, rec["b"])
    if a is None or b is None:
        return None
    size = _scale(p)
    gap = rec.get("value") or 0.0
    kind = rec["kind"]
    if kind == "FRAME":
        da, db = _datum(p, rec["a"]), _datum(p, rec["b"])
        if da is None or db is None:
            return None
        z = dt.mul(da.z, -1.0) if rec.get("flip") else da.z
        return (dt.norm(dt.sub(da.origin, db.origin)) + size * (dt.norm(dt.sub(z, db.z)) + dt.norm(dt.sub(da.x, db.x))))
    if kind == "ANGLE":
        c = dt.dot(a.dir, b.dir)
        if a.what in ("AXIS", "CIRCLE") or b.what in ("AXIS", "CIRCLE"):
            c = abs(c)
        now = math.degrees(math.acos(max(-1.0, min(1.0, c))))
        want = gap
        return size * math.radians(min(abs(now - want), abs(180 - now - want)))
    par = size * math.sqrt(max(0.0, 1 - min(1.0, abs(dt.dot(a.dir, b.dir))) ** 2))
    pair = (a.what, b.what)
    if pair == ("PLANE", "PLANE"):
        return par + abs(abs(dt.dot(dt.sub(b.point, a.point), a.dir)) - gap)
    if a.what == "PLANE":
        return abs(abs(dt.dot(dt.sub(b.point, a.point), a.dir)) - gap)
    if b.what == "PLANE":
        return abs(abs(dt.dot(dt.sub(a.point, b.point), b.dir)) - gap)
    if "POINT" in pair:
        return abs(dt.norm(dt.sub(a.point, b.point)) - gap)
    off = dt.norm(_perp(dt.sub(b.point, a.point), a.dir))
    if pair == ("CIRCLE", "CIRCLE") and kind == "COINCIDENT":
        return par + dt.norm(dt.sub(a.point, b.point))
    return par + abs(off - (gap if kind == "DISTANCE" else 0.0))


def _perp(v, d):
    return dt.sub(v, dt.mul(d, dt.dot(v, d)))


# ---- what a mate fixes, as rows on the twist (v, w) ---------------------------------------------------

def _two_across(d) -> tuple:
    x, y, _ = dt.plane_axes(dt.unit(d))
    return x, y


def _trans(n, at) -> list[float]:
    """Row fixing the motion of point ``at`` along ``n``: n.(v + w x at) = n.v + (at x n).w"""
    return [*n, *dt.cross(at, n)]


def _turn(n) -> list[float]:
    return [0.0, 0.0, 0.0, *n]


def rows(p: Processor, rec: dict) -> np.ndarray:
    """The motions of the moving copy that this mate fixes (one row each)."""
    a, b = item(p, rec["a"]), item(p, rec["b"])
    if rec["kind"] == "FRAME":
        o = _datum(p, rec["b"])
        at = o.origin if o is not None else (0.0, 0.0, 0.0)
        return np.array([_trans(e, at) for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
                        + [_turn(e) for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))], float)
    if a is None or b is None:
        return np.zeros((0, 6))
    out: list[list[float]] = []
    kind, pair = rec["kind"], (a.what, b.what)
    if kind == "ANGLE":
        ax = dt.cross(a.dir, b.dir)
        if dt.norm(ax) < 1e-12:
            ax = _two_across(a.dir)[0]
        out.append(_turn(dt.unit(ax)))
    elif pair == ("PLANE", "PLANE"):
        n = a.dir
        out.append(_trans(n, b.point))
        out += [_turn(t) for t in _two_across(n)]
    elif a.what == "PLANE" or b.what == "PLANE":
        pl, pt = (a, b) if a.what == "PLANE" else (b, a)
        out.append(_trans(pl.dir, pt.point if pt is b else b.point))
    elif "POINT" in pair:
        out += [_trans(e, b.point) for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    else:  # two axes (or round edges)
        d = a.dir
        across = _two_across(d)
        if kind == "DISTANCE":
            way = _perp(dt.sub(b.point, a.point), d)
            if dt.norm(way) > 1e-12:
                out.append(_trans(dt.unit(way), b.point))
        else:
            out += [_trans(t, b.point) for t in across]
        out += [_turn(t) for t in across]
        if pair == ("CIRCLE", "CIRCLE") and kind == "COINCIDENT":
            out.append(_trans(d, b.point))  # the centres meet too
    return np.array(out, float).reshape(-1, 6)


def _rank(m: np.ndarray) -> int:
    if not len(m):
        return 0
    s = np.linalg.svd(m, compute_uv=False)
    return int((s > ROWS_TOL * max(1.0, s[0])).sum())


def _null(m: np.ndarray) -> np.ndarray:
    """Basis of the motions no row fixes (6 x k)."""
    if not len(m):
        return np.eye(6)
    _u, s, vt = np.linalg.svd(m)
    r = int((s > ROWS_TOL * max(1.0, s[0])).sum())
    return vt[r:].T


def _clean(v, nd=6):
    v = np.asarray(v, float)
    v = np.where(np.abs(v) < 1e-9, 0.0, v)
    return [round(float(x), nd) + 0.0 for x in v]


def freedoms(m: np.ndarray, size: float, centre=(0.0, 0.0, 0.0)) -> list[dict]:
    """The motions left: slides (a direction) and turns (an axis through a point; where the copy can
    also slide, the axis is put through the point nearest ``centre``)."""
    # scale the turn columns so lengths and angles weigh alike
    s = np.diag([1, 1, 1, size, size, size]).astype(float)
    n = _null(m @ np.linalg.inv(s)) if len(m) else np.eye(6)
    n = np.linalg.inv(s) @ n  # back to (v, w)
    if n.shape[1] == 0:
        return []
    w = n[3:, :]
    out = []
    # pure slides: combinations with no turn
    _u, sv, vt = np.linalg.svd(w) if w.size else (None, np.zeros(0), np.eye(n.shape[1]))
    r = int((sv > 1e-9 * max(1.0, sv[0] if len(sv) else 1.0)).sum())
    slide = vt[r:].T  # k x r'
    turn = vt[:r].T
    dirs = []
    for c in slide.T:
        v = n[:3, :] @ c
        if np.linalg.norm(v) > 1e-12:
            v = v / np.linalg.norm(v)
            big = np.flatnonzero(np.abs(v) > 1e-9)
            if len(big) and v[big[0]] < 0:
                v = -v  # a slide goes both ways: show it pointing the plus way
            dirs.append(v)
            out.append({"kind": "slide", "along": _clean(dirs[-1])})
    ctr = np.asarray(centre, float)
    for c in turn.T:
        v, om = n[:3, :] @ c, n[3:, :] @ c
        k = float(om @ om)
        if k < 1e-24:
            continue
        axis = om / math.sqrt(k)
        big = np.flatnonzero(np.abs(axis) > 1e-9)
        if len(big) and axis[big[0]] < 0:
            axis, om, v = -axis, -om, -v
        at = np.cross(om, v) / k
        for d in dirs:
            at = at + float((ctr - at) @ d) * d
        pitch = float(om @ v) / k
        row = {"kind": "turn", "about": _clean(axis), "through": _clean(at, 4)}
        if abs(pitch) > 1e-9 * size:
            row["pitch"] = round(pitch, 6)
        out.append(row)
    return out


# ---- the whole assembly ------------------------------------------------------------------------------

def _centre(shape):
    from ..core.refs import _describe

    return _describe("BODY", shape)["c"]


def _tol(p: Processor) -> float:
    return 1e-6 * _scale(p)


def check(p: Processor) -> dict:
    m = p.model
    recs = list(m.mates)
    size = _scale(p)
    tol = _tol(p)
    out_m, bodies = [], {}
    for i, rec in enumerate(recs):
        err = error(p, rec)
        rw = rows(p, rec)
        body = rec["body"]
        prev = [r for r in recs[:i] if r["body"] == body]
        before = np.vstack([rows(p, r) for r in prev] or [np.zeros((0, 6))])
        new = _rank(np.vstack([before, rw])) - _rank(before) if len(rw) else 0
        row = {"step": rec["step"], "kind": rec["kind"].lower(), "body": body,
               "a": " ".join(map(str, rec["a"])).lower(), "b": " ".join(map(str, rec["b"])).lower(),
               "holds": err is not None and err <= tol, "error": None if err is None else round(err, 9),
               "fixes": int(_rank(rw)), "new": int(new)}
        if err is None:
            row["gone"] = True
        if len(rw) and new < _rank(rw):
            # the earlier mates on this copy that fix some of the same: still holding, it repeats them;
            # undone by this one, they fight
            over = [r for r in prev if _rank(np.vstack([rows(p, r), rw])) < _rank(rows(p, r)) + _rank(rw)]
            undid = set(rec.get("undoes", ()))
            rep = [r["step"] for r in over if r["step"] not in undid]
            if rep:
                row["repeats"] = rep
            if undid:
                row["fights"] = sorted(undid)
        elif rec.get("undoes"):
            row["fights"] = sorted(rec["undoes"])
        if not row["holds"] and err is not None:
            row["undone_by"] = [r["step"] for r in recs[i + 1:] if rec["step"] in r.get("undoes", ())]
        out_m.append(row)
        bodies.setdefault(body, []).append(rw)
    out_b = []
    for body, rws in sorted(bodies.items()):
        stack = np.vstack(rws)
        b = m.bodies.get(body)
        fr = freedoms(stack, size, _centre(b.shape) if b else (0.0, 0.0, 0.0))
        out_b.append({"body": body, "name": b.name if b else "", "fixed": _rank(stack), "free": fr})
    grounded = sorted({r["fixed"] for r in recs if r.get("fixed") is not None} - set(bodies))
    return {"mates": out_m, "bodies": out_b, "grounded": grounded,
            "fights": sum(1 for r in out_m if r.get("fights")),
            "repeats": sum(1 for r in out_m if r.get("repeats"))}


def _vec(v) -> str:
    from ..lang.expr import format_value

    return "(" + ", ".join(format_value(x) for x in v) + ")"


def freedom_words(f: dict) -> str:
    if f["kind"] == "slide":
        return f"slides along {_vec(f['along'])}"
    s = f"turns about {_vec(f['about'])} through {_vec(f['through'])}"
    return s + (f" (screws {f['pitch']:g} per radian)" if "pitch" in f else "")


def check_text(d: dict) -> str:
    if not d["mates"]:
        return "no mates (MATE places a copy against another)"
    lines = ["mates:"]
    for r in d["mates"]:
        head = f"  step {r['step']}: {r['kind']} {r['a']} - {r['b']} (body {r['body']})"
        if r.get("gone"):
            state = "an item is gone (the face or datum no longer exists)"
        elif r["holds"]:
            state = "holds"
        else:
            later = ", ".join(map(str, r.get("undone_by", [])))
            state = f"DOES NOT HOLD (off by {r['error']:.6g})" + (f": undone by step {later}" if later else "")
        if r.get("fights"):
            state += f"; FIGHTS step {', '.join(map(str, r['fights']))} (moved the copy off it)"
        if r.get("repeats"):
            prev = ", ".join(map(str, r["repeats"]))
            state += (f"; REPEATS step {prev} (fixes nothing new)" if r["new"] == 0
                      else f"; partly repeats step {prev} ({r['new']} of {r['fixes']} new)")
        lines.append(f"{head}: {state}")
    lines.append("copies:")
    for b in d["bodies"]:
        name = f" '{b['name']}'" if b["name"] and b["name"] != f"body{b['body']}" else ""
        if not b["free"]:
            lines.append(f"  body {b['body']}{name}: fully placed")
        else:
            lines.append(f"  body {b['body']}{name}: {6 - b['fixed']} way{'s' if 6 - b['fixed'] != 1 else ''} "
                         "to move: " + "; ".join(freedom_words(f) for f in b["free"]))
    if d["grounded"]:
        lines.append("held in place (only mated to): bodies " + ", ".join(map(str, d["grounded"])))
    lines.append(f"{d['fights']} fight{'s' if d['fights'] != 1 else ''}, {d['repeats']} "
                 f"repeat{'s' if d['repeats'] != 1 else ''}")
    return "\n".join(lines)


def after_mate(p: Processor, rec: dict) -> None:
    """Right after a MATE: does it undo an earlier mate on the same copy, or fix nothing new?"""
    tol = _tol(p)
    prev = [r for r in p.model.mates[:-1] if r["body"] == rec["body"]]
    if not prev:
        return
    broken = [r["step"] for r in prev if (e := error(p, r)) is not None and e > tol
              and r.get("holding", True)]
    rec["undoes"] = broken
    rec["holding"] = True
    for r in prev:  # what holds now, so a later mate is blamed only for what it undoes itself
        e = error(p, r)
        r["holding"] = e is not None and e <= tol
    if broken:
        p.warn(f"MATE: this undoes step {', '.join(map(str, broken))} (the mates fight; MATES shows them)")
    rw = rows(p, rec)
    before = np.vstack([rows(p, r) for r in prev])
    if not broken and len(rw) and _rank(np.vstack([before, rw])) == _rank(before):
        p.warn("MATE: this fixes nothing the earlier mates on this copy had not fixed (it repeats them)")


@command(
    "MATES",
    Arg("fmt", str, "TEXT", "TEXT or JSON"),
    logged=False,
    help="Check the assembly's mates: each one holds or not (a later mate that undid it is named), mates that "
         "repeat earlier ones, and for every mated copy the ways it can still move (slides and turns).",
)
def mates_cmd(p: Processor, fmt):
    d = check(p)
    p.give_report("mates", d)
    if fmt == "JSON":
        import json

        return json.dumps(d)
    return check_text(d)


# ---- coordinate systems on bodies ---------------------------------------------------------------------

@command(
    "CSYS",
    Arg("name", Text, "", "the coordinate system's name (none: list them)"),
    Arg("on", Raw, "", "the body it moves with (0: none), or FACE"),
    *[Arg(f"a{i}", Raw, "") for i in range(1, 8)],
    help="A coordinate system that moves with a body: CSYS, name, body, x,y,z [, nx,ny,nz [, angle]] (origin, "
         "Z direction, X turned by angle about Z) or CSYS, name, FACE, id [, angle] (on a flat face, Z out of "
         "the body). It is a datum plane with an X axis, so WORKPLANE and MATE use it; MATE, FRAME, a, b puts b "
         "on a. CSYS alone lists them.",
)
def csys(p: Processor, name, on, **raws):
    from .feature_handlers import _add, _Args, _check_name, _face_plane

    m = p.model
    if not name:
        if not m.frames:
            return "no coordinate systems (CSYS, name, body, x,y,z makes one)"
        lines = []
        for key, bid in m.frames.items():
            d = m.datums.get(key)
            if d is None:
                continue
            on_b = f"on body {bid}" if bid else "fixed"
            lines.append(f"  {d.name}: {on_b}, origin {_vec(_clean(d.origin, 6))}, x {_vec(_clean(d.x))}, "
                         f"z {_vec(_clean(d.z))}")
        return "coordinate systems:\n" + "\n".join(lines)
    _check_name(p, name, "CSYS")
    vals = [raws[f"a{i}"] for i in range(1, 8)]
    if on.strip().upper() == "FACE":
        a = _Args(p, "CSYS", vals)
        gid = a.entity("FACE", "the face")
        ang = a.num("angle", 0.0)
        a.done()
        c, n = _face_plane(p, gid, "CSYS")
        bid = m.entity_owner("FACE", gid)[0]
        d = dt.plane(c, n, ang, name)
        how = f"on face {gid}"
    else:
        try:
            bid = p._body_ref(_csys_cmd(), on) if on.strip() not in ("", "0") else 0
        except CommandError:
            raise CommandError(f"CSYS: {on.strip()!r} is not a body (or FACE)") from None
        a = _Args(p, "CSYS", vals)
        o = a.point("the origin")
        nrm = a.point("the Z direction") if a.more() else (0.0, 0.0, 1.0)
        ang = a.num("angle", 0.0)
        a.done()
        try:
            d = dt.plane(o, nrm, ang, name)
        except dt.DatumError as exc:
            raise CommandError(f"CSYS: {exc}") from None
        how = f"on body {bid}" if bid else "fixed in space"
    msg = _add(p, d, how)
    m.frames = {**m.frames, name.upper(): bid}
    m.datums_changed()  # drawn as a coordinate system now, not a plane
    return msg.replace("plane ", "coordinate system ", 1) + f", x {_vec(_clean(d.x))}"


def _csys_cmd():
    from .processor import REGISTRY

    return REGISTRY["CSYS"]
