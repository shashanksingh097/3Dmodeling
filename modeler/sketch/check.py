"""SCHECK: what is wrong with a sketch, or still loose, named entity by entity.

The solver already knows the degrees of freedom left, which numbers can still move and which
constraints repeat others. This turns that into words a user can act on:

* constraints that cannot all hold (and the ones each fights);
* constraints that only repeat others (and which ones they repeat);
* geometry that can still move, with how (an end of a line, a circle's radius);
* curves drawn twice, curves too small to keep, ends left open in the profile.

Each finding names the geometry (3, 3.E) and constraints (C4) involved, so the window can
select them in the view.
"""

from __future__ import annotations

import math
from typing import Any

from .sketch import Sketch, SketchError, kname

# how a point role reads in words
_ROLE = {"S": "start", "E": "end", "C": "centre", "P": "point", "A": "axis end"}


def _role(r: str) -> str:
    return _ROLE.get(r, f"point {r}")


def check(sk: Sketch) -> dict[str, Any]:
    """Findings for one sketch (a copy is solved; the sketch itself is not changed)."""
    work = sk.copy()
    out: dict[str, Any] = {"sketch": sk.name, "dof": None, "conflicts": [], "repeats": [], "free": [],
                           "duplicates": [], "tiny": [], "profile": "", "select": []}
    try:
        rep = work.solve()
        out["dof"] = rep.dof
    except SketchError as exc:
        out["conflicts"].append({"text": str(exc)})
        return out
    # constraints that only repeat others, and which ones
    for n in work.redundant:
        others = [k for k in work._fights(n) if k != n]
        c = work.cons[n]
        mine = [k for k in others if k in work.cons and not work.cons[k].auto]
        out["repeats"].append({"con": n, "kind": c.kind.lower(), "refs": list(c.refs), "repeats": mine,
                               "with_drawing": len(mine) < len(others)})
        out["select"].append(f"C{n}")
    # geometry that can still move
    for g in work.geos.values():
        if g.kind == "POINT" and not g.pts:
            continue
        loose = []
        for role, i in g.pts.items():
            u, v = i in work.free, i + 1 in work.free
            if u and v:
                loose.append(f"{_role(role)} moves freely")
            elif u or v:
                loose.append(f"{_role(role)} slides along {'u' if u else 'v'}")
        if len(loose) == len(g.pts) and all(t.endswith("moves freely") for t in loose):
            loose = ["not held in place (all of it can move)"]
        if g.r is not None and g.r in work.free:
            loose.append("size is free" if g.kind in ("ELLIPSE", "EARC") else "radius is free")
        if loose:
            out["free"].append({"geo": g.n, "kind": kname(g.kind), "construction": g.construction, "how": loose})
            out["select"].append(str(g.n))
    # the same curve drawn twice
    seen: dict[tuple, int] = {}
    size = max(work.extent(), 1.0)

    def key(g):
        pts = sorted((round(work.pt(i)[0] / size, 7), round(work.pt(i)[1] / size, 7)) for i in g.pts.values())
        r = round(work.x[g.r] / size, 7) if g.r is not None else None
        return (g.kind, tuple(pts), r, g.construction)

    for g in work.geos.values():
        k = key(g)
        if k in seen:
            out["duplicates"].append({"geo": g.n, "same_as": seen[k], "kind": kname(g.kind)})
            out["select"].append(str(g.n))
        else:
            seen[k] = g.n
    # curves too small to see or keep
    for g in work.geos.values():
        if g.kind == "LINE":
            length = math.dist(work.pt(g.pts["S"]), work.pt(g.pts["E"]))
            if length < 1e-4 * size:
                out["tiny"].append({"geo": g.n, "kind": "line", "size": length})
        elif g.kind in ("ARC", "CIRCLE") and work.radius(g) < 1e-4 * size:
            out["tiny"].append({"geo": g.n, "kind": kname(g.kind), "size": work.radius(g)})
    # the profile: closed, open ends, crossings
    from . import profile as pf

    try:
        faces = pf.faces(work)
        out["profile"] = f"{len(faces)} profile{'s' if len(faces) != 1 else ''} ready" if faces else "no profile"
    except SketchError as exc:
        out["profile"] = str(exc)
    out["select"] = list(dict.fromkeys(out["select"]))
    return out


def as_text(res: dict[str, Any]) -> str:
    lines = []
    dof = res["dof"]
    if res["conflicts"]:
        lines.append(f"sketch {res['sketch']}: the constraints cannot all hold")
        lines += [f"  {c['text']}" for c in res["conflicts"]]
        return "\n".join(lines)
    state = "fully defined" if dof == 0 else f"{dof} degree{'s' if dof != 1 else ''} of freedom left"
    problems = len(res["repeats"]) + len(res["duplicates"]) + len(res["tiny"])
    lines.append(f"sketch {res['sketch']}: {state}; " + (f"{problems} problem{'s' if problems != 1 else ''}"
                                                       if problems else "no problems"))
    for r in res["repeats"]:
        rep = ", ".join(f"C{k}" for k in r["repeats"])
        if r.get("with_drawing"):
            rep = (rep + " with " if rep else "") + "the constraints the drawing tools added"
        rep = rep or "the others"
        lines.append(f"  C{r['con']} ({r['kind']} {', '.join(r['refs'])}) only repeats {rep}: delete one (SDEL)")
    for d in res["duplicates"]:
        lines.append(f"  {d['kind']} {d['geo']} is drawn twice (the same as {d['same_as']}): delete one")
    for t in res["tiny"]:
        lines.append(f"  {t['kind']} {t['geo']} is tiny ({t['size']:.3g}): delete it or give it a size")
    if res["free"]:
        lines.append("  can still move:")
        for f in res["free"]:
            what = f"{f['kind']} {f['geo']}" + (" (construction)" if f["construction"] else "")
            lines.append(f"    {what}: {'; '.join(f['how'])}")
    lines.append(f"  profile: {res['profile']}")
    return "\n".join(lines)
