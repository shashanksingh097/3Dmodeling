"""Assemblies that move: DRIVE holds a parameter at a value for a moment (what the Motion
slider does), MOTION runs a parameter through a range and checks every position for parts
running into each other.

A mechanism is written with a parameter: ``A = 30`` then ``MATE, ANGLE, ..., A`` (or a
``ROTATE`` by A, a ``MOVE`` by D ...). ``DRIVE, A, 75`` rebuilds the model with A = 75 without
touching the history: only the steps that read A run again. ``DRIVE, A`` lets go (the history's
own value again); ``DRIVE`` alone lists what is driven.

``MOTION, A, 0, 90, 18`` puts A at 0, 5, 10 ... 90 in turn and, at each, looks for shown solid
bodies that overlap. It reports the overlaps by position, the ranges where each pair runs into
the other, and the smallest gap seen, then puts A back. Nothing in the history changes.
"""

from __future__ import annotations

import re

from ..geometry import robust
from ..lang.expr import format_value
from .processor import Arg, CommandError, Processor, Text, command


def _assign_index(p: Processor, name: str) -> int:
    """The first top-level history entry that sets ``name`` (-1: none)."""
    pat = re.compile(rf"^\s*{re.escape(name)}\s*=(?!=)", re.IGNORECASE | re.MULTILINE)
    for i, e in enumerate(p.history[: p.cursor]):
        if pat.search(e.text):
            return i
    return -1


def drive_to(p: Processor, name: str, value) -> str:
    """Hold ``name`` at ``value`` (None: let go) and rebuild what depends on it."""
    key = name.upper()
    start = _assign_index(p, key)
    if start < 0:
        raise CommandError(f"{key} is not set by the history (write {key} = value in it first, then use it in "
                           "the steps that should move)")
    old = dict(p.drive)
    if value is None:
        p.drive.pop(key, None)
    else:
        p.drive[key] = value
    saved = p.history_backup()
    try:
        msg = p.rebuild(start, skip=True)
    except Exception:
        p.history_restore(saved)
        p.drive = old
        raise
    return msg


@command(
    "DRIVE",
    Arg("name", Text, "", "a parameter set in the history (none: list the driven ones)"),
    Arg("value", Text, "", "the value to hold it at (none: let go, back to the history's value)"),
    session=True,
    help="Move an assembly by a parameter without changing the history: DRIVE, A, 75 rebuilds with A = 75 "
         "(only the steps that read A run again) · DRIVE, A lets go · DRIVE lists what is driven. The Motion "
         "window's slider runs it",
)
def drive(p: Processor, name, value):
    if not name.strip():
        if not p.drive:
            return "nothing is driven"
        return "driven: " + ", ".join(f"{k} = {format_value(v)}" for k, v in p.drive.items())
    key = name.strip().upper()
    if not value.strip():
        if key not in p.drive:
            return f"{key} is not driven"
        msg = drive_to(p, key, None)
        return f"{key} back to the history's value {format_value(p.params.get(key))}: {msg}"
    try:
        v = p.evaluator.eval(value)
    except Exception as exc:  # noqa: BLE001 - an expression error, said plainly
        raise CommandError(f"DRIVE: {value.strip()}: {exc}") from None
    msg = drive_to(p, key, v)
    return f"{key} = {format_value(v)}: {msg}"


# ---- checking a range of motion -------------------------------------------------------
def solid_ids(p: Processor) -> list[int]:
    from ..geometry import meshbody

    m = p.model
    return [i for i in m.shown_ids() if robust.solids(m.bodies[i].shape)
            or (meshbody.is_mesh(m.bodies[i].shape) and meshbody.info(m.bodies[i].shape).closed)]


def overlaps(p: Processor, ids: list[int]) -> tuple[list[tuple[int, int, float]], float | None]:
    """Pairs of bodies that overlap (with the common volume), and the smallest gap between bodies
    whose boxes come within reach of each other (None: none that close)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common

    from ..geometry import features as ft
    from ..geometry import meshbody
    from .queries import bbox

    m = p.model
    boxes = {i: bbox(m.bodies[i].shape) for i in ids}
    hits, gap = [], None
    for k, x in enumerate(ids):
        for y in ids[k + 1:]:
            bx, by = boxes[x], boxes[y]
            reach = 0.05 * max(max(bx[3 + j] - bx[j], by[3 + j] - by[j]) for j in range(3))
            if any(bx[j + 3] + reach < by[j] or by[j + 3] + reach < bx[j] for j in range(3)):
                continue
            sx, sy = m.bodies[x].shape, m.bodies[y].shape
            vol = 0.0
            if meshbody.is_mesh(sx) or meshbody.is_mesh(sy):
                from .mesh_handlers import default_deflection

                vol = meshbody.overlap_volume(sx, sy, default_deflection(p, sx if not meshbody.is_mesh(sx) else sy))
            else:
                c = BRepAlgoAPI_Common(sx, sy)
                if c.IsDone() and not robust.is_empty(c.Shape()):
                    vol = robust.volume(c.Shape())
            if vol > 1e-9 * max(1.0, robust.volume(sx)):
                hits.append((x, y, vol))
                continue
            if not (meshbody.is_mesh(sx) or meshbody.is_mesh(sy)):
                try:
                    d, _, _ = ft.distance(sx, sy)
                except ft.FeatureError:
                    continue
                if d > 1e-6:  # parts that touch (a hinge, a seat) are not a gap
                    gap = d if gap is None else min(gap, d)
    return hits, gap


def _pair_hits(p: Processor, x: int, y: int) -> bool:
    m = p.model
    if x not in m.bodies or y not in m.bodies:
        return False
    return bool(overlaps(p, [x, y])[0])


def _first_contacts(p: Processor, key: str, values: list[float], pair_flags: dict) -> dict:
    """Where each overlap begins, between the last clear position and the first one that overlaps
    (halving the step 10 times: to a thousandth of the step)."""
    out = {}
    for (x, y), flags in pair_flags.items():
        for i in range(1, len(flags)):
            if flags[i] and not flags[i - 1]:
                lo, hi = values[i - 1], values[i]
                for _ in range(10):
                    mid = (lo + hi) / 2
                    drive_to(p, key, mid)
                    if _pair_hits(p, x, y):
                        hi = mid
                    else:
                        lo = mid
                out[(x, y, values[i])] = (lo + hi) / 2
    return out


def positions(a: float, b: float, steps: int) -> list[float]:
    return [a + (b - a) * i / steps for i in range(steps + 1)]


def _ranges(values: list[float], flags: list[bool]) -> list[tuple[float, float]]:
    out, start, last = [], None, None
    for v, f in zip(values, flags):
        if f and start is None:
            start = v
        if f:
            last = v
        if not f and start is not None:
            out.append((start, last))
            start = None
    if start is not None:
        out.append((start, last))
    return out


@command(
    "MOTION",
    Arg("name", Text, help="the parameter that moves the assembly"),
    Arg("start", help="its first value"),
    Arg("end", help="its last value"),
    Arg("steps", int, 10, "how many steps between them (positions: steps + 1)"),
    logged=False,
    help="Run an assembly through its range of motion and look for parts running into each other: MOTION, A, "
         "0, 90, 18 puts A at 0, 5 ... 90, checks every pair of shown solids at each position, reports where "
         "they overlap and the smallest gap, and puts A back. The history does not change",
)
def motion(p: Processor, name, start, end, steps):
    key = name.strip().upper()
    if steps < 1 or steps > 500:
        raise CommandError("MOTION: steps is 1 to 500")
    if _assign_index(p, key) < 0:
        raise CommandError(f"MOTION: {key} is not set by the history (write {key} = value in it first)")
    before = p.drive.get(key)
    values = positions(start, end, steps)
    lines = []
    pair_flags: dict[tuple[int, int], list[bool]] = {}
    worst: dict[tuple[int, int], float] = {}
    smallest = None
    u = p.model.units.lower()
    try:
        for i, v in enumerate(values):
            drive_to(p, key, v)
            if p.progress is not None and not p.progress(i, len(values), f"{key} = {format_value(v)}"):
                lines.append("(stopped)")
                values = values[: i + 1]
                break
            hits, gap = overlaps(p, solid_ids(p))
            hit_pairs = {(x, y) for x, y, _ in hits}
            for x, y, vol in hits:
                pair_flags.setdefault((x, y), [False] * i)
                worst[(x, y)] = max(worst.get((x, y), 0.0), vol)
            for pair, flags in pair_flags.items():
                flags.append(pair in hit_pairs)
            if gap is not None and (smallest is None or gap < smallest[0]):
                smallest = (gap, v)
            if hits:
                lines.append(f"  {key} = {format_value(v)}: " + "; ".join(
                    f"bodies {x} and {y} overlap {vol:.4g} {u}3" for x, y, vol in hits))
            else:
                lines.append(f"  {key} = {format_value(v)}: clear" + (f" (gap {gap:.4g})" if gap is not None else ""))
        firsts = _first_contacts(p, key, values, pair_flags)
    finally:
        drive_to(p, key, before)
    head = f"MOTION {key} from {format_value(start)} to {format_value(end)}, {len(values)} positions:"
    summary = []
    for (x, y), flags in pair_flags.items():
        for lo, hi in _ranges(values, flags):
            at = f"at {key} = {format_value(lo)}" if lo == hi else f"from {key} = {format_value(lo)} to {format_value(hi)}"
            first = firsts.get((x, y, lo))
            exact = f"; they first meet at {key} = {first:.4g}" if first is not None else ""
            summary.append(f"bodies {x} and {y} run into each other {at} (up to {worst[(x, y)]:.4g} {u}3{exact})")
    clashes = []
    for (x, y), flags in pair_flags.items():
        for lo, hi in _ranges(values, flags):
            row = {"a": x, "b": y, "from": lo, "to": hi, "worst_volume": round(worst[(x, y)], 4)}
            if firsts.get((x, y, lo)) is not None:
                row["first_meet"] = round(float(firsts[(x, y, lo)]), 6)
            clashes.append(row)
    p.give_report("MOTION", {"param": key, "start": start, "end": end, "positions": len(values),
                             "clashes": clashes,
                             "smallest_gap": None if smallest is None else
                             {"gap": round(float(smallest[0]), 4), "at": smallest[1]}})
    if not summary:
        summary.append("no parts run into each other in this range"
                       + (f"; the smallest gap is {smallest[0]:.4g} at {key} = {format_value(smallest[1])}"
                          if smallest else ""))
    return "\n".join([head, *lines, *summary])


# ---- the path of a point through a motion ---------------------------------------------
def _vertices(shape, most: int = 60):
    import numpy as np
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    as_vertex = getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex
    out = []
    ex = TopExp_Explorer(shape, TopAbs_VERTEX)
    while ex.More() and len(out) < most:
        q = BRep_Tool.Pnt_s(as_vertex(ex.Current()))
        out.append((q.X(), q.Y(), q.Z()))
        ex.Next()
    return np.array(out, float)


def rigid_fit(a, b):
    """The rotation R and shift t that best carry points a onto points b (b ~ a @ R.T + t), and the
    largest misfit."""
    import numpy as np

    ca, cb = a.mean(axis=0), b.mean(axis=0)
    h = (a - ca).T @ (b - cb)
    u, _s, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T)) or 1.0
    r = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    t = cb - ca @ r.T
    err = float(np.max(np.linalg.norm(a @ r.T + t - b, axis=1))) if len(a) else 0.0
    return r, t, err


MAX_TRACE = 31  # steps: the path is kept as a SPLINE through at most 32 points


@command(
    "TRACE",
    Arg("name", Text, help="the parameter that moves the assembly"),
    Arg("start", help="its first value"),
    Arg("end", help="its last value"),
    Arg("steps", int, 24, f"how many steps between them (1 to {MAX_TRACE})"),
    Arg("b", Text, help="the moving body that carries the point"),
    Arg("x", help="the point, where it is now"), Arg("y"), Arg("z"),
    session=True,
    help="The path a point on a moving part follows through a motion, kept as a curve: TRACE, A, 0, 360, 24, "
         "rod, 120,0,10 runs A from 0 to 360, follows the point 120,0,10 of body rod (as the model is now) and "
         "adds a SPLINE through where it goes (a history step, named trace_1). The parameter is put back.",
)
def trace(p: Processor, name, start, end, steps, b, x, y, z):
    import numpy as np

    from .processor import REGISTRY

    key = name.strip().upper()
    if not 1 <= steps <= MAX_TRACE:
        raise CommandError(f"TRACE: steps is 1 to {MAX_TRACE}")
    if _assign_index(p, key) < 0:
        raise CommandError(f"TRACE: {key} is not set by the history (write {key} = value in it first)")
    bid = p._body_ref(REGISTRY["TRACE"], b.strip())
    m = p.model
    body_name = m.body(bid).name
    ref = _vertices(m.body(bid).shape)
    if len(ref) < 3:
        raise CommandError(f"TRACE: body {bid} has too few corners to follow (it needs three)")
    point = np.array([x, y, z], float)
    before = p.drive.get(key)
    pts = []
    worst = 0.0
    try:
        for v in positions(start, end, steps):
            drive_to(p, key, v)
            now = m.body_by_name(body_name) if not body_name.startswith("body") else m.bodies.get(bid)
            if now is None:
                raise CommandError(f"TRACE: body {body_name} is gone at {key} = {format_value(v)}")
            cur = _vertices(now.shape)
            if cur.shape != ref.shape:
                raise CommandError(f"TRACE: body {body_name} changes shape as {key} moves, so a point on it "
                                   "cannot be followed")
            r, t, err = rigid_fit(ref, cur)
            worst = max(worst, err)
            pts.append(point @ r.T + t)
    finally:
        drive_to(p, key, before)
    size = max(1.0, float(np.ptp(ref, axis=0).max()))
    if worst > 1e-4 * size:
        raise CommandError(f"TRACE: body {body_name} does not just move as {key} changes (it changes shape by up "
                           f"to {worst:.3g}), so a point on it cannot be followed")
    span = max(float(np.linalg.norm(q - pts[0])) for q in pts)
    if span < 1e-9 * size:
        raise CommandError(f"TRACE: the point does not move as {key} goes from {format_value(start)} to "
                           f"{format_value(end)}")
    closed = len(pts) > 3 and float(np.linalg.norm(pts[-1] - pts[0])) < 1e-6 * size
    if closed:
        pts = pts[:-1]
    keep = [pts[0]]
    for q in pts[1:]:  # a point that stays put for a step adds nothing to the curve
        if float(np.linalg.norm(q - keep[-1])) > 1e-9 * size:
            keep.append(q)
    fmt = lambda q: "(" + ", ".join(f"{c:.6g}" for c in q) + ")"  # noqa: E731
    if len(keep) == 2:
        line = "LINE, " + ", ".join(f"{c:.6g}" for c in np.concatenate(keep))
    else:
        line = "SPLINE, " + ", ".join(fmt(q) for q in keep) + (", CLOSE" if closed else "")
    k = 1
    while m.body_by_name(f"trace_{k}") is not None:
        k += 1
    res = p.run(line)
    if not res.ok:
        raise CommandError(f"TRACE: the path could not be drawn: {res.message}")
    p.run(f"NAME, LAST, trace_{k}")
    length = sum(float(np.linalg.norm(keep[i + 1] - keep[i])) for i in range(len(keep) - 1))
    return (f"TRACE of ({x:g}, {y:g}, {z:g}) on {body_name} as {key} goes from {format_value(start)} to "
            f"{format_value(end)}: {len(pts)} points, {'a closed loop' if closed else 'an open path'} about "
            f"{length:.4g} long (through the points), kept as trace_{k}")
