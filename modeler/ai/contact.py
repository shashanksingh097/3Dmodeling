"""Do parts touch? As short answers with IDs: one pair, a whole assembly, shafts in holes.

The layer over geometry/contact.py, like probe.py is over geometry/probe.py:
body and face IDs instead of kernel shapes, rounded numbers, the unit and the
model revision. Used by the CONTACT and CLEARANCE commands, the TOUCH, OVERLAP,
CONTACTAREA, GROUPS and CLEARANCE queries, and the assistant's ``contact``,
``assembly_check`` and ``fit_check`` tools.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..core import datum as dt
from ..geometry import contact as ct
from ..geometry import robust
from .describe import DescribeError, find_body, num, vec

if TYPE_CHECKING:
    from ..commands.processor import Processor

LIMIT = 100  # rows of each list in one answer


def _face_ids(p: "Processor", bid: int, idx: list[int]) -> list[int]:
    ids = p.model.bodies[bid].entity_ids["FACE"]
    return [ids[i - 1] for i in idx if 0 < i <= len(ids)]


def _solid(p: "Processor", bid: int):
    shape = p.model.bodies[bid].shape
    if not robust.solids(shape):
        raise DescribeError(f"body {bid} is not a solid (contact needs closed solids)")
    return shape


def _tol(p: "Processor", shapes, tol: float) -> float:
    return float(tol) if tol and tol > 0 else ct.default_tol(*shapes, extra=p.model.tolerance)


def _label(p: "Processor", bid: int) -> dict[str, Any]:
    name = p.model.bodies[bid].name
    return {"id": bid, "name": name} if name else {"id": bid}


def pair_row(p: "Processor", a: int, b: int, c: ct.Contact) -> dict[str, Any]:
    row: dict[str, Any] = {"a": _label(p, a), "b": _label(p, b), "state": c.state}
    if c.state == "apart":
        delta = dt.sub(c.at_b, c.at_a)
        row.update({"gap": num(c.distance), "from": vec(c.at_a), "to": vec(c.at_b), "delta": vec(delta),
                    "faces_a": _face_ids(p, a, c.near_a), "faces_b": _face_ids(p, b, c.near_b)})
    elif c.state == "touch":
        row["touch"] = c.kind
        if c.kind == "face":
            row["area"] = num(c.area)
        elif c.kind == "line":
            row["length"] = num(c.length)
        row["at"] = vec(c.at_a)
        row.update({"faces_a": _face_ids(p, a, c.faces_a), "faces_b": _face_ids(p, b, c.faces_b)})
    else:
        bx = c.overlap_box
        row.update({"volume": num(c.volume), "fraction_of_smaller": num(c.fraction, 4),
                    "overlap_box": {"min": vec(bx[:3]), "max": vec(bx[3:]),
                                    "size": vec([bx[3] - bx[0], bx[4] - bx[1], bx[5] - bx[2]])},
                    "faces_a": _face_ids(p, a, c.faces_a), "faces_b": _face_ids(p, b, c.faces_b)})
    return row


def contact(p: "Processor", a, b, tol: float = 0.0) -> dict[str, Any]:
    """How two bodies meet: apart (gap, nearest points and faces), touching (on faces with the
    area, along a line with its length, or at a point) or overlapping (volume in common)."""
    ia, ib = find_body(p, a), find_body(p, b)
    if ia == ib:
        raise DescribeError("give two different bodies")
    sa, sb = _solid(p, ia), _solid(p, ib)
    t = _tol(p, (sa, sb), tol)
    out = {"rev": p.model.revision, "unit": p.model.units.lower(), "tol": _tnum(t)}
    out.update(pair_row(p, ia, ib, ct.contact(sa, sb, t)))
    return out


def pair_state(p: "Processor", a, b, tol: float = 0.0) -> ct.Contact:
    """The raw contact of two bodies (for the queries)."""
    ia, ib = find_body(p, a), find_body(p, b)
    if ia == ib:
        raise DescribeError("give two different bodies")
    sa, sb = _solid(p, ia), _solid(p, ib)
    return ct.contact(sa, sb, _tol(p, (sa, sb), tol))


def _ids(p: "Processor", bodies) -> list[int]:
    if bodies in (None, "", "ALL", []):
        return [i for i in sorted(p.model.bodies) if p.model.is_shown(i)]
    if not isinstance(bodies, list):
        bodies = [bodies]
    return sorted({find_body(p, x) for x in bodies})


def assembly(p: "Processor", bodies=None, against=None, tol: float = 0.0, near: float = 0.0,
             limit: int = LIMIT, budget: float = 60.0) -> dict[str, Any]:
    """Every pair of solid bodies: which overlap (a clash), which touch and how, which are
    nearly touching (gap below ``near``), the groups of bodies that hold together through
    contacts, and the bodies that touch nothing (floating). Stops after ``budget`` seconds
    and says how far it got."""
    import time

    end = time.monotonic() + budget if budget and budget > 0 else None
    ids = _ids(p, bodies)
    skipped = [i for i in ids if not robust.solids(p.model.bodies[i].shape)]
    ids = [i for i in ids if i not in skipped]
    if against not in (None, ""):
        others = [find_body(p, x) for x in (against if isinstance(against, list) else [against])]
        for o in others:
            _solid(p, o)
        pairs = [(o, i) for o in others for i in ids if i != o]
        ids = sorted(set(ids) | set(others))
    else:
        pairs = [(x, y) for k, x in enumerate(ids) for y in ids[k + 1:]]
    if len(ids) > 400:
        raise DescribeError(f"{len(ids)} bodies is too many to check every pair; name the bodies")
    shapes = {i: p.model.bodies[i].shape for i in ids}
    boxes = {i: ct.box_of(s) for i, s in shapes.items()}
    t = float(tol) if tol and tol > 0 else (max(1e-6, 1e-6 * ct.size_of(*boxes.values())) + p.model.tolerance
                                           if boxes else 1e-6)
    near = max(0.0, float(near or 0.0))
    reach = max(t, near)
    overlaps, touching, close = [], [], []
    links: dict[int, set[int]] = {i: set() for i in ids}
    checked, stopped = 0, 0
    todo = [(x, y) for x, y in pairs if not ct.boxes_apart(boxes[x], boxes[y], reach)]
    for k, (x, y) in enumerate(todo):
        if end is not None and time.monotonic() > end:
            stopped = len(todo) - k
            break
        checked += 1
        c = ct.contact(shapes[x], shapes[y], t)
        if c.state == "apart":
            if near and c.distance <= near:
                close.append(pair_row(p, x, y, c))
            continue
        links[x].add(y)
        links[y].add(x)
        (overlaps if c.state == "overlap" else touching).append(pair_row(p, x, y, c))
    groups = _groups(ids, links)
    floating = [g[0] for g in groups if len(g) == 1] if len(ids) > 1 else []
    out: dict[str, Any] = {"rev": p.model.revision, "unit": p.model.units.lower(), "tol": _tnum(t),
                           "bodies": len(ids), "pairs": len(pairs), "pairs_measured": checked,
                           "overlaps": overlaps[:limit], "touching": touching[:limit]}
    if near:
        out["near"] = sorted(close, key=lambda r: r["gap"])[:limit]
    if against in (None, ""):
        out["groups"] = groups[:limit]
        out["floating"] = floating[:limit]
    for key, rows in (("overlaps", overlaps), ("touching", touching)):
        if len(rows) > limit:
            out[f"more_{key}"] = len(rows) - limit
    if skipped:
        out["not_solid"] = skipped[:limit]
    if stopped:
        out["stopped"] = (f"the time limit ({budget:g} s) ran out with {stopped} close pairs not measured; "
                          "the groups and floating bodies are incomplete. Check fewer bodies, or one body "
                          "against the rest")
    out["summary"] = _summary(out, against not in (None, ""))
    return out


def _groups(ids: list[int], links: dict[int, set[int]]) -> list[list[int]]:
    seen: set[int] = set()
    out = []
    for i in ids:
        if i in seen:
            continue
        stack, g = [i], []
        seen.add(i)
        while stack:
            k = stack.pop()
            g.append(k)
            for n in links[k]:
                if n not in seen:
                    seen.add(n)
                    stack.append(n)
        out.append(sorted(g))
    out.sort(key=lambda g: (-len(g), g[0]))
    return out


def _summary(out: dict[str, Any], one_against: bool) -> str:
    parts = [f"{len(out['overlaps']) + out.get('more_overlaps', 0)} overlapping",
             f"{len(out['touching']) + out.get('more_touching', 0)} touching"]
    if "near" in out:
        parts.append(f"{len(out['near'])} nearly touching")
    text = "pairs: " + ", ".join(parts)
    if not one_against:
        n = len(out["groups"])
        text += f"; {n} group{'s' if n != 1 else ''} of connected bodies"
        if out["floating"]:
            text += f"; touching nothing: {', '.join(map(str, out['floating'][:10]))}"
    return text


def group_count(p: "Processor", tol: float = 0.0) -> int:
    """How many separate groups the shown solid bodies make (1: everything holds together)."""
    out = assembly(p, None, None, tol, budget=0)
    return len(out["groups"])


def fit(p: "Processor", a, b, tol: float = 0.0) -> dict[str, Any]:
    """Every round shaft of one body inside a round hole of the other: both diameters, the
    clearance (negative: interference), how far the axes are apart, and the engaged length."""
    ia, ib = find_body(p, a), find_body(p, b)
    if ia == ib:
        raise DescribeError("give two different bodies")
    sa, sb = _solid(p, ia), _solid(p, ib)
    t = _tol(p, (sa, sb), tol)
    rows = []
    for f in ct.fits(sa, sb, t):
        sid, hid = (ia, ib) if f.shaft_in == "a" else (ib, ia)
        row: dict[str, Any] = {
            "shaft": {"body": sid, "d": num(2 * f.shaft.r), "faces": _face_ids(p, sid, f.shaft.faces)},
            "hole": {"body": hid, "d": num(2 * f.hole.r), "faces": _face_ids(p, hid, f.hole.faces)},
            "state": f.state, "clearance": num(2 * f.clearance), "per_side": num(f.clearance),
            "axis_offset": num(f.offset), "tightest_gap": num(f.min_gap), "engaged": num(f.engaged),
            "axis": vec(f.hole.d)}
        if f.tilt > 1e-6:
            row["tilt_deg"] = num(f.tilt)
        if f.state == "thread":
            row["note"] = ("screw thread: the diameters are the thread's crests (major of the shaft, minor of "
                           "the hole); use CONTACT for whether the threads clash")
        rows.append(row)
    out: dict[str, Any] = {"rev": p.model.revision, "unit": p.model.units.lower(), "a": _label(p, ia),
                           "b": _label(p, ib), "tol": _tnum(t), "fits": rows[:LIMIT]}
    if not rows:
        out["note"] = ("no round shaft of one sits in a round hole of the other (threads and partial "
                       "cylinders are not counted)")
    return out


def tightest_fit(p: "Processor", a, b) -> float:
    """The smallest radial gap of the plain (not threaded) fits between two bodies (negative: interference)."""
    rows = [r for r in fit(p, a, b)["fits"] if r["state"] != "thread"]
    if not rows:
        raise DescribeError("no shaft of one body sits in a hole of the other")
    return min(r["tightest_gap"] for r in rows)


def _tnum(t: float) -> float:
    return float(f"{t:.3g}")
