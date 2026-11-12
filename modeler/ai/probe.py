"""Where material is, as compact data: rays, points, cross-sections, wall thickness.

The formatting layer over geometry/probe.py: IDs instead of kernel faces,
rounded numbers, the unit and the model revision, like describe.py.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from ..core import datum as dt
from ..geometry import probe as pr
from ..geometry import robust
from .describe import DescribeError, find_body, num, on_circle, vec

if TYPE_CHECKING:
    from ..commands.processor import Processor


def _face_id(p: "Processor", bid: int, face) -> int | None:
    body = p.model.bodies[bid]
    k = body.maps["FACE"].FindIndex(face)
    return body.entity_ids["FACE"][k - 1] if k else None


def _bodies(p: "Processor", bodies) -> list[int]:
    if bodies in (None, "", "ALL", []):
        return [i for i in sorted(p.model.bodies) if p.model.is_shown(i)]
    if not isinstance(bodies, list):
        bodies = [bodies]
    return [find_body(p, b) for b in bodies]


# ---- rays ---------------------------------------------------------------------------------


def probe_ray(p: "Processor", origin, direction, bodies=None, limit: int = 50) -> dict[str, Any]:
    """Every face the ray crosses (body, face, point, distance, entering or
    leaving) and the stretches of the ray inside each body's material."""
    try:
        d = pr._unit(tuple(float(c) for c in direction))
    except ValueError as exc:
        raise DescribeError(str(exc)) from None
    o = tuple(float(c) for c in origin)
    hits, spans = [], []
    for bid in _bodies(p, bodies):
        shape = p.model.bodies[bid].shape
        if not robust.solids(shape):
            continue
        found = pr.Rays(shape).hits(o, d)
        inside = pr.classify(shape, o) == "inside"
        for h in found:
            row = {"t": num(h["t"]), "body": bid, "face": _face_id(p, bid, h["face"]), "at": vec(h["point"]),
                   "enters" if h["state"] == "in" else "leaves": True}
            if h.get("grazing"):
                row["grazing"] = True
            hits.append(row)
        for a, b in pr.material_spans(found, inside):
            spans.append({"body": bid, "from": num(a), "to": num(b), "length": num(b - a)})
    hits.sort(key=lambda h: (h["t"], h["body"]))
    spans.sort(key=lambda s: (s["from"], s["body"]))
    out: dict[str, Any] = {"rev": p.model.revision, "unit": p.model.units.lower(), "from": vec(o), "dir": vec(d),
                           "hits": hits[:limit], "material": spans[:limit]}
    if len(hits) > limit:
        out["more"] = len(hits) - limit
    if not hits:
        out["note"] = "the ray meets nothing"
    return out


# ---- points --------------------------------------------------------------------------------


def probe_point(p: "Processor", points: list, bodies=None) -> dict[str, Any]:
    """For each point: which body it is inside or on, else the nearest body,
    with the nearest face and the distance to it."""
    ids = _bodies(p, bodies)
    rows = []
    for pt in points:
        q = tuple(float(c) for c in pt)
        best = None
        state_row = None
        for bid in ids:
            shape = p.model.bodies[bid].shape
            dist, at, face = pr.nearest(shape, q)
            state = pr.classify(shape, q) if robust.solids(shape) else ("on" if dist < 1e-6 else "outside")
            if dist < 1e-6 and state != "inside":
                state = "on"
            cand = {"body": bid, "state": state, "distance": num(dist), "nearest": vec(at)}
            fid = _face_id(p, bid, face) if face is not None else None
            if fid is not None:
                cand["face"] = fid
            if state in ("inside", "on") and state_row is None:
                state_row = cand
            if best is None or dist < best["distance"]:
                best = cand
        row: dict[str, Any] = {"at": vec(q)}
        chosen = state_row or best
        if chosen is None:
            row["state"] = "empty model"
        else:
            row.update(chosen)
        rows.append(row)
    return {"rev": p.model.revision, "unit": p.model.units.lower(), "points": rows}


# ---- cross-sections --------------------------------------------------------------------------


def plane_at(base: dt.Datum, offset: float) -> dt.Datum:
    if not offset:
        return base
    return dataclasses.replace(base, origin=dt.add(base.origin, dt.mul(base.z, offset)))


def section_profile(p: "Processor", body, plane: dt.Datum, offsets: list[float] | None = None,
                    plane_name: str = "") -> dict[str, Any]:
    """The cut through a body at one or more parallel planes, as loops in the
    plane's own coordinates (u along its x axis, v along its y axis)."""
    bid = find_body(p, body)
    shape = p.model.bodies[bid].shape
    if not robust.solids(shape):
        raise DescribeError("a section needs a solid body")
    diag = robust.diagonal(shape)
    size = diag + 10
    from ..commands.queries import bbox

    x0, y0, z0, x1, y1, z1 = bbox(shape)
    mid = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    cuts = []
    for off in offsets or [0.0]:
        pl = plane_at(plane, off)
        try:
            s = pr.section(shape, pl, mid, size)
            note = ""
            if _on_flat_face(shape, pl):
                # a cut exactly on a flat face shows both sides of it: take the
                # cut a hair to either side that has material
                nudge = 1e-6 * max(1.0, diag)
                below = pr.section(shape, plane_at(pl, -nudge), mid, size)
                above = pr.section(shape, plane_at(pl, nudge), mid, size)
                s, side = (above, "above") if above.area >= below.area else (below, "below")
                note = f"the plane lies on a flat face; this is the cut just {side} it"
        except ValueError as exc:
            raise DescribeError(str(exc)) from None
        cut: dict[str, Any] = {"offset": num(off)} if offsets else {}
        if note:
            cut["note"] = note
        cut["area"] = num(s.area)
        if s.area <= 0:
            cut["note"] = "the plane misses the body"
        else:
            cut["centre"] = vec(s.centre)
            cut["loops"] = _loops(s.loops)
        cuts.append(cut)
    out: dict[str, Any] = {"rev": p.model.revision, "unit": p.model.units.lower(), "body": bid,
                           "plane": {"name": plane_name or plane.name, "at": vec(plane.origin),
                                     "normal": vec(plane.z), "u": vec(plane.x), "v": vec(plane.y)}}
    if offsets:
        out["cuts"] = cuts
    else:
        out.update(cuts[0])
    return out


def _on_flat_face(shape, pl: dt.Datum) -> bool:
    """True if a flat face of the shape lies in the plane."""
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    from ..geometry import features as ft

    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        got = ft.face_plane(exp.Current())
        exp.Next()
        if got is None:
            continue
        c, n = got
        if abs(abs(dt.dot(n, pl.z)) - 1) < 1e-9 and abs(dt.dot(dt.sub(c, pl.origin), pl.z)) < 1e-7:
            return True
    return False


def _seg(s: dict) -> dict:
    if "line" in s:
        return {"line": [vec(s["line"][0]), vec(s["line"][1])]}
    if "circle" in s:
        return {"circle": {"c": vec(s["circle"]["c"]), "r": num(s["circle"]["r"])}}
    if "arc" in s:
        a = s["arc"]
        return {"arc": {"c": vec(a["c"]), "r": num(a["r"]), "from": vec(a["from"]), "to": vec(a["to"]),
                        "deg": num(a["deg"], 2)}}
    c = s["curve"]
    return {"curve": {"through": [vec(q) for q in c["points"]], "length": num(c["length"])}}


def _loops(loops: list[pr.Loop]) -> list[dict]:
    """Loops, outer ones first; equal round holes become one row with a count."""
    rows: list[dict] = []
    circles: dict[tuple, list] = {}
    for lp in sorted(loops, key=lambda lp: not lp.outer):
        segs = [_seg(s) for s in lp.segments]
        if len(segs) == 1 and "circle" in segs[0] and not lp.outer:
            circles.setdefault(("hole", segs[0]["circle"]["r"]), []).append(segs[0]["circle"]["c"])
            continue
        row: dict[str, Any] = {"outer": lp.outer}
        rect = _rect(segs)
        if len(segs) == 1 and "circle" in segs[0]:
            row["circle"] = segs[0]["circle"]
        elif rect:
            row["rect"] = rect
        else:
            row["segments"] = segs
        rows.append(row)
    for (_, r), centres in circles.items():
        if len(centres) == 1:
            rows.append({"outer": False, "circle": {"c": centres[0], "r": r}})
            continue
        row = {"outer": False, "circles": {"n": len(centres), "r": r, "c": sorted(centres)}}
        ring = on_circle([[c[0], c[1], 0.0] for c in centres], [0.0, 0.0, 1.0])
        if ring:
            row["circles"]["on"] = {"c": ring["circle"][:2], "r": ring["r"],
                                    **({"step_deg": ring["step_deg"]} if "step_deg" in ring else {})}
            del row["circles"]["c"]
        rows.append(row)
    return rows


def _rect(segs: list[dict]) -> dict | None:
    """Four lines along u and v: a rectangle, given by its corners."""
    if len(segs) != 4 or not all("line" in s for s in segs):
        return None
    for s in segs:
        (a, b) = s["line"]
        if a[0] != b[0] and a[1] != b[1]:
            return None
    us = [q[0] for s in segs for q in s["line"]]
    vs = [q[1] for s in segs for q in s["line"]]
    return {"min": [min(us), min(vs)], "max": [max(us), max(vs)], "size": [num(max(us) - min(us)),
                                                                          num(max(vs) - min(vs))]}


# ---- wall thickness -------------------------------------------------------------------------


def wall_thickness(p: "Processor", body, below: float = 0.0, limit: int = 5, per_face: int = 5) -> dict[str, Any]:
    """The thinnest walls of a body: where, between which faces, how thick.
    With ``below``, every face whose wall is thinner than that."""
    bid = find_body(p, body)
    shape = p.model.bodies[bid].shape
    if not robust.solids(shape):
        raise DescribeError("wall thickness needs a solid body")
    spots = pr.wall_thickness(shape, per_face)
    if below > 0:
        spots = [s for s in spots if s.thickness < below]
    rows = []
    for s in spots[: limit if below <= 0 else 200]:
        rows.append({"t": num(s.thickness), "face": _face_id(p, bid, s.face), "at": vec(s.point),
                     "to_face": _face_id(p, bid, s.other) if s.other is not None else None,
                     "to": vec(s.other_point)})
    out: dict[str, Any] = {"rev": p.model.revision, "unit": p.model.units.lower(), "body": bid,
                           "min": rows[0]["t"] if rows else None, "thinnest": rows}
    if below > 0:
        out["below"] = below
    return out


def min_wall(shape) -> float:
    spots = pr.wall_thickness(shape)
    return spots[0].thickness if spots else 0.0
