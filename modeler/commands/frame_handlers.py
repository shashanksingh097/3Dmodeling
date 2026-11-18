"""Frames and weldments (geometry/frames.py): MEMBER lays structural members along a path,
CUTLIST lists what to cut."""

from __future__ import annotations

import csv
import os

import numpy as np

from ..geometry import frames as fr
from ..lang.expr import fmt_num
from .processor import Arg, CommandError, Path, Processor, Text, command


def _segments(edges, what: str) -> list[tuple]:
    """Each edge's ends, after checking that it is straight."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_CurveType

    out = []
    for e in edges:
        c = BRepAdaptor_Curve(e)
        if c.GetType() != GeomAbs_CurveType.GeomAbs_Line:
            raise CommandError(f"MEMBER: {what} has a curved piece; members run along straight lines")
        a, b = c.Value(c.FirstParameter()), c.Value(c.LastParameter())
        out.append(((a.X(), a.Y(), a.Z()), (b.X(), b.Y(), b.Z())))
    return out


def _chain(segs: list[tuple], what: str) -> tuple[list, bool]:
    """Order the segments into one path: its corner points, and whether it closes."""
    tol = 1e-6 * max(1.0, max(float(np.linalg.norm(np.subtract(a, b))) for a, b in segs))

    def same(p, q):
        return float(np.linalg.norm(np.subtract(p, q))) <= tol

    ends = [q for s in segs for q in s]
    # start at an end that only one segment has (an open path), else anywhere (a closed one)
    start = next((q for q in ends if sum(same(q, o) for o in ends) == 1), segs[0][0])
    left = list(segs)
    pts = [start]
    while left:
        for k, (a, b) in enumerate(left):
            if same(a, pts[-1]) or same(b, pts[-1]):
                pts.append(b if same(a, pts[-1]) else a)
                left.pop(k)
                break
        else:
            raise CommandError(f"MEMBER: {what}: the lines do not join into one path (draw them end to end)")
    closed = len(pts) > 2 and same(pts[0], pts[-1])
    if closed:
        pts = pts[:-1]
    return pts, closed


def _path_points(p: Processor, path: str) -> tuple[list, bool, str]:
    """The corner points of a path: a sketch's lines, or a curve body (POLYLINE ...)."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    m = p.model
    name = path.strip().strip('"')
    if name.upper() in {k.upper() for k in m.sketches}:
        from ..sketch import profile as prof

        sk = m.sketch(name)
        if m.active_sketch == sk.name.upper():
            m.set_active_sketch(None)
        edges = [prof.edge(sk, g) for g in sk.geos.values() if g.kind != "POINT" and not g.construction]
        what = f"sketch {sk.name}"
    else:
        from .processor import REGISTRY

        bid = p._body_ref(REGISTRY["MEMBER"], name)
        shape = m.body(bid).shape
        if TopExp_Explorer(shape, TopAbs_FACE).More():
            raise CommandError(f"MEMBER: body {bid} is not a path: give a POLYLINE (or other line) body or a sketch")
        as_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
        edges = []
        ex = TopExp_Explorer(shape, TopAbs_EDGE)
        while ex.More():
            edges.append(as_edge(ex.Current()))
            ex.Next()
        what = f"body {bid}"
    if not edges:
        raise CommandError(f"MEMBER: {what} has no lines")
    pts, closed = _chain(_segments(edges, what), what)
    return pts, closed, what


@command(
    "MEMBER",
    Arg("path", Text, help="the lines the members run along: a POLYLINE (or line) body, or a sketch"),
    Arg("profile", str, help=", ".join(fr.PROFILES)),
    Arg("size", Text, help="the profile's sizes, like 40x40x3: " +
        "; ".join(f"{k} {v[0]}" for k, v in fr.PROFILES.items())),
    Arg("corner", str, "MITRE", "MITRE: both cut halfway at each corner · BUTT: one runs through, the next stops "
                                "at its side"),
    Arg("name", Text, "member", "the members' name: member_1, member_2 ..."),
    Arg("turn", float, 0.0, "turn the profile about the member, degrees (90: an I-beam's web in the frame's plane)"),
    help="Structural members along the lines of a path, one per straight piece: MEMBER, frame, SQUARE, 40x3 "
         "(square tube 40 wide, 3 wall, mitred corners) · MEMBER, frame, IBEAM, 100x200x8, BUTT · MEMBER, s2, "
         "ROUND, 30x2. CUTLIST lists their lengths and end cuts",
)
def member(p: Processor, path, profile, size, corner, name, turn):
    from .handlers import _added

    if corner not in ("MITRE", "MITER", "BUTT"):
        raise CommandError("MEMBER: corner is MITRE or BUTT")
    corner = "MITRE" if corner == "MITER" else corner
    base = name.strip().strip('"') or "member"
    try:
        dims = fr.parse_size(profile, size)
    except fr.FrameError as exc:
        raise CommandError(f"MEMBER: {exc}") from None
    pts, closed, what = _path_points(p, path)
    try:
        made = fr.members(pts, closed, profile, dims, corner, turn)
    except fr.FrameError as exc:
        raise CommandError(f"MEMBER: {what}: {exc}") from None
    m = p.model
    taken = {b.name.lower() for b in m.bodies.values()}
    k = 1
    msgs = []
    for shape, rec in made:
        while f"{base}_{k}".lower() in taken:
            k += 1
        body = m.add_body(shape, name=f"{base}_{k}")
        taken.add(body.name.lower())
        m.members[body.id] = rec
        a0, a1 = rec.end_angles()
        msgs.append(_added(p, body, f"{profile} {rec.size_text()}, {fmt_num(rec.length)} long, ends {a0:g}/{a1:g}°"))
    head = (f"MEMBER along {what}: {len(made)} member{'s' if len(made) != 1 else ''} "
            f"({corner.lower()} corners)")
    return head + "\n" + "\n".join(msgs)


def cut_rows(p: Processor) -> list[dict]:
    """One row per kind of piece: same profile, size, length and end cuts, with how many."""
    rows: dict[tuple, dict] = {}
    for bid, rec in sorted(p.model.members.items()):
        if bid not in p.model.bodies:
            continue
        a0, a1 = sorted(rec.end_angles())
        key = (rec.profile, rec.size_text(), round(rec.length, 1), a0, a1)
        row = rows.setdefault(key, {"profile": rec.profile, "size": rec.size_text(), "length": rec.length,
                                    "ends": (a0, a1), "qty": 0, "bodies": []})
        row["qty"] += 1
        row["bodies"].append(p.model.bodies[bid].name)
    return sorted(rows.values(), key=lambda r: (r["profile"], r["size"], -r["length"]))


@command(
    "CUTLIST",
    Arg("file", Path, "", "a .csv file to write it to (none: just show it)"),
    logged=False,
    help="The frame's cut list: each kind of member (profile, size, length, end cut angles) with how many, and "
         "the total length per profile: CUTLIST · CUTLIST, cuts.csv",
)
def cutlist(p: Processor, file):
    rows = cut_rows(p)
    if not rows:
        return "no frame members (make them with MEMBER)"
    lines = [f"{'qty':>3}  {'profile':<8} {'size':<12} {'length':>9}  ends (from square)  bodies"]
    totals: dict[tuple, float] = {}
    for r in rows:
        lines.append(f"{r['qty']:>3}  {r['profile']:<8} {r['size']:<12} {r['length']:>9.1f}  "
                     f"{r['ends'][0]:g}° / {r['ends'][1]:g}°{'':<8} {', '.join(r['bodies'])}")
        k = (r["profile"], r["size"])
        totals[k] = totals.get(k, 0.0) + r["qty"] * r["length"]
    lines.append("total: " + "; ".join(f"{pr} {sz}: {fmt_num(round(v, 1))}" for (pr, sz), v in totals.items()))
    text = "\n".join(lines)
    if file:
        path = file if os.path.splitext(file)[1] else file + ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["qty", "profile", "size", "length", "end 1 angle", "end 2 angle", "bodies"])
                for r in rows:
                    w.writerow([r["qty"], r["profile"], r["size"], f"{r['length']:.2f}", r["ends"][0], r["ends"][1],
                                " ".join(r["bodies"])])
        except OSError as exc:
            raise CommandError(f"CUTLIST: cannot write {path} ({exc})") from None
        text += f"\nwritten to {path}"
    return text
