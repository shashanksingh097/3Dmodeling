"""ROUTE (pipes, tubes and cables along a path, geometry/routing.py) and ROUTES (the pipe list)."""

from __future__ import annotations

import csv
import dataclasses
import os

from ..geometry import robust
from ..geometry import routing as rt
from ..lang.expr import fmt_num
from .processor import Arg, CommandError, Path, Processor, Text, command


def _n(v: float) -> str:
    return fmt_num(round(v, 2) + 0.0)


@command(
    "ROUTE",
    Arg("path", Text, help="the lines the route runs along: a POLYLINE (or line) body, or a sketch"),
    Arg("kind", str, "PIPE", "PIPE (a tube; also TUBE) or CABLE (a round bundle of wires)"),
    Arg("size", Text, "", "PIPE: outside diameter x wall, like 22x1.5 (one number: solid) · CABLE: wires x wire "
                          "diameter, like 7x2.5 (one number: the bundle's diameter)"),
    Arg("radius", float, 0.0, "the bend radius on the centreline (0: 1.5 diameters for a pipe, 6 for a cable)"),
    Arg("name", Text, "", "the route's name (default pipe_1, cable_1 ...)"),
    help="A pipe or cable along the straight lines of a path, bent at the corners: ROUTE, p1, PIPE, 22x1.5 "
         "(bends of 1.5 x 22) · ROUTE, p1, PIPE, 22x1.5, 40 · ROUTE, s1, CABLE, 7x2.5 (a bundle of seven 2.5 "
         "wires). A route that starts or ends on another route's centreline joins it as a tee. ROUTES lists "
         "the lengths and bends.",
)
def route(p: Processor, path, kind, size, radius, name):
    from .frame_handlers import _path_points
    from .handlers import _added

    kind = "PIPE" if kind == "TUBE" else kind
    if kind not in ("PIPE", "CABLE"):
        raise CommandError("ROUTE: the kind is PIPE (or TUBE) or CABLE")
    if not size.strip():
        raise CommandError("ROUTE: give the size: ROUTE, p1, PIPE, 22x1.5 or ROUTE, p1, CABLE, 7x2.5")
    try:
        od, wall, wires = rt.parse_size(kind, size.strip().strip('"'))
    except rt.RouteError as exc:
        raise CommandError(f"ROUTE: {exc}") from None
    if radius < 0:
        raise CommandError("ROUTE: the bend radius cannot be negative")
    radius = radius or od * (1.5 if kind == "PIPE" else 6.0)
    pts, closed, what = _path_points(p, path, "ROUTE")
    if closed:
        raise CommandError(f"ROUTE: {what} closes on itself; a route has two ends")
    try:
        shape, wire, straights, bends = rt.build(pts, kind, od, wall, radius)
    except rt.RouteError as exc:
        raise CommandError(f"ROUTE: {what}: {exc}") from None
    m = p.model
    rec = rt.Route(kind, od, wall, radius, straights, bends, wires, [wire])
    # a tee: an end of this route on the centreline of another route of the same size
    tol = 1e-6 * max(1.0, robust.diagonal(shape))
    host = None
    for bid, other in sorted(m.routes.items()):
        if bid not in m.bodies or other.kind != kind:
            continue
        if any(rt.on_line(w, q, tol) for w in other.centrelines for q in (pts[0], pts[-1])):
            host = bid
            break
    if host is not None:
        other = m.routes[host]
        if abs(other.od - od) > 1e-9 or abs(other.wall - wall) > 1e-9:
            p.warn(f"ROUTE: joining a {rec.size_text()} branch to route {m.bodies[host].name} "
                   f"({other.size_text()})")
        try:
            bores = []
            if kind == "PIPE" and wall:
                bores = [rt.bore(wire, od, wall)] + [rt.bore(w, other.od, other.wall) for w in other.centrelines]
            joined = rt.tee(m.bodies[host].shape, shape, bores)
        except rt.RouteError as exc:
            raise CommandError(f"ROUTE: the tee with route {m.bodies[host].name} failed: {exc}") from None
        merged = dataclasses.replace(other, straights=other.straights + straights, bends=other.bends + bends,
                                     centrelines=other.centrelines + [wire], tees=other.tees + 1)
        body = m.replace([host], joined, "ROUTE", same_id=True)
        m.routes[body.id] = merged
        return _added(p, body, f"ROUTE tee: {rec.size_text()} branch, {_n(rec.length)} long, joined to "
                               f"{body.name}")
    base = name.strip().strip('"') or kind.lower()
    k = 1
    taken = {b.name.lower() for b in m.bodies.values()}
    full = base if name.strip() and base.lower() not in taken else None
    while full is None:
        if f"{base}_{k}".lower() not in taken:
            full = f"{base}_{k}"
        k += 1
    body = m.add_body(shape, name=full)
    m.routes[body.id] = rec
    bends_txt = (f", {len(bends)} bend{'s' if len(bends) != 1 else ''} of radius {_n(radius)}" if bends else "")
    return _added(p, body, f"ROUTE {kind.lower()} {rec.size_text()} along {what}: {_n(rec.length)} long"
                           + bends_txt)


def route_rows(p: Processor) -> list[dict]:
    m = p.model
    rows = []
    for bid, r in sorted(m.routes.items()):
        if bid not in m.bodies:
            continue
        rows.append({"name": m.bodies[bid].name, "kind": r.kind, "size": r.size_text(), "length": r.length,
                     "straights": r.straights, "bends": r.bends, "radius": r.radius, "tees": r.tees})
    return rows


@command(
    "ROUTES",
    Arg("file", Path, "", "a .csv file to write it to (none: just show it)"),
    logged=False,
    help="The pipe and cable list: each route's size, length along the centreline, straight pieces and bends "
         "(angle and radius), tees, and the total per size: ROUTES · ROUTES, pipes.csv",
)
def routes(p: Processor, file):
    rows = route_rows(p)
    if not rows:
        return "no routes (make them with ROUTE)"
    lines = []
    totals: dict[tuple, float] = {}
    for r in rows:
        bends = ", ".join(f"{a:.0f}°" for a in r["bends"])
        lines.append(f"{r['name']}: {r['kind'].lower()} {r['size']}, {_n(r['length'])} long; straights "
                     + ", ".join(_n(s) for s in r["straights"])
                     + (f"; bends {bends} at radius {_n(r['radius'])}" if r["bends"] else "; no bends")
                     + (f"; {r['tees']} tee{'s' if r['tees'] != 1 else ''}" if r["tees"] else ""))
        key = (r["kind"], r["size"])
        totals[key] = totals.get(key, 0.0) + r["length"]
    lines.append("total: " + "; ".join(f"{k.lower()} {s}: {_n(v)}" for (k, s), v in totals.items()))
    text = "\n".join(lines)
    if file:
        path = file if os.path.splitext(file)[1] else file + ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["name", "kind", "size", "length", "straights", "bends (degrees)", "bend radius", "tees"])
                for r in rows:
                    w.writerow([r["name"], r["kind"], r["size"], f"{r['length']:.2f}",
                                " ".join(f"{s:.2f}" for s in r["straights"]),
                                " ".join(f"{a:.1f}" for a in r["bends"]), f"{r['radius']:g}", r["tees"]])
        except OSError as exc:
            raise CommandError(f"ROUTES: cannot write {path}: {exc}") from None
        text += f"\nwritten to {path}"
    return text
