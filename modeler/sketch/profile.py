"""From a solved sketch to faces: find the closed loops, nest them, and build
OCCT faces on the sketch plane (outer loops with their holes).

The loop finding and nesting are plain 2D work on the sketch's own numbers;
only the last step (edges, wires, faces) touches the kernel. Construction
geometry and lone points are left out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .sketch import Geo, Sketch, SketchError


@dataclass
class Piece:
    geo: Geo
    a: tuple[float, float]  # where the walk enters this piece
    b: tuple[float, float]  # where it leaves
    reverse: bool  # walked from its end to its start


@dataclass
class Loop:
    pieces: list[Piece]  # in walking order; a full circle is one piece with a == b
    poly: list[tuple[float, float]]  # points along it (arcs sampled), for area and nesting
    area: float  # signed: positive counter-clockwise

    @property
    def names(self) -> str:
        return ", ".join(str(p.geo.n) for p in self.pieces)


def _arc_points(sk: Sketch, g: Geo, reverse: bool, n: int = 24):
    c = sk.pt(g.pts["C"])
    r = sk.radius(g)
    if g.kind == "CIRCLE":
        a1, a2 = 0.0, 360.0
    else:
        a1, a2 = sk.arc_angles(g)
    steps = max(4, int(n * (a2 - a1) / 360) + 1)
    pts = [(c[0] + r * math.cos(math.radians(a1 + (a2 - a1) * i / steps)),
            c[1] + r * math.sin(math.radians(a1 + (a2 - a1) * i / steps))) for i in range(steps + 1)]
    return pts[::-1] if reverse else pts


def _area(poly) -> float:
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                     for i in range(len(poly)))


def _inside(pt, poly) -> bool:
    x, y = pt
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def loops(sk: Sketch) -> list[Loop]:
    """Every closed loop of the sketch's (non-construction) curves.

    Ends closer than a millionth of the sketch size count as joined. A curve
    end that joins nothing, or a point where three curves meet, is an error
    that names the place, since a profile there is not clear."""
    tol = 1e-6 * sk.extent()
    curves = [g for g in sk.geos.values() if not g.construction and g.kind in ("LINE", "ARC", "CIRCLE")]
    if not curves:
        raise SketchError(f"sketch {sk.name} has no lines, arcs or circles to make a profile from "
                          "(construction geometry does not count)")
    out: list[Loop] = []
    open_ones = []
    for g in curves:
        if g.kind == "CIRCLE":
            poly = _arc_points(sk, g, False, 48)[:-1]
            p = sk.pt(g.pts["C"])
            out.append(Loop([Piece(g, p, p, False)], poly, _area(poly)))
        else:
            open_ones.append(g)
    nodes: list[tuple[float, float]] = []

    def node(p) -> int:
        for i, q in enumerate(nodes):
            if abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol:
                return i
        nodes.append(p)
        return len(nodes) - 1

    ends: dict[int, tuple[int, int]] = {}
    at: dict[int, list[int]] = {}
    for g in open_ones:
        s, e = node(sk.pt(g.pts["S"])), node(sk.pt(g.pts["E"]))
        if s == e:
            raise SketchError(f"{g.kind.lower()} {g.n} starts and ends at the same point")
        ends[g.n] = (s, e)
        at.setdefault(s, []).append(g.n)
        at.setdefault(e, []).append(g.n)
    for i, gs in at.items():
        p = nodes[i]
        where = f"({p[0]:.6g}, {p[1]:.6g})"
        if len(gs) == 1:
            raise SketchError(f"the profile is not closed: {sk.geos[gs[0]].kind.lower()} {gs[0]} ends at {where} "
                              f"and nothing joins it there (draw to that point, or make {gs[0]} construction)")
        if len(gs) > 2:
            raise SketchError(f"{len(gs)} curves meet at {where} ({', '.join(map(str, gs))}), so the profile there "
                              "is not clear: keep two curves at each point, and make the others construction")
    done: set[int] = set()
    for g in open_ones:
        if g.n in done:
            continue
        pieces = []
        cur, start_node = g.n, ends[g.n][0]
        here = start_node
        while True:
            s, e = ends[cur]
            rev = here != s
            nxt_node = s if rev else e
            geo = sk.geos[cur]
            pieces.append(Piece(geo, nodes[here], nodes[nxt_node], rev))
            done.add(cur)
            here = nxt_node
            if here == start_node:
                break
            cur = next(n for n in at[here] if n != cur)
        poly: list[tuple[float, float]] = []
        for pc in pieces:
            if pc.geo.kind == "LINE":
                poly.append(pc.a)
            else:
                poly.extend(_arc_points(sk, pc.geo, pc.reverse)[:-1])
        out.append(Loop(pieces, poly, _area(poly)))
    for lp in out:
        if abs(lp.area) < 1e-12 * sk.extent() ** 2:
            raise SketchError(f"the loop through {lp.names} encloses no area")
    return out


def regions(sk: Sketch) -> list[tuple[Loop, list[Loop]]]:
    """Faces to build: (outer loop, its holes). A loop inside a hole is an
    island, a face of its own (even-odd nesting)."""
    lps = sorted(loops(sk), key=lambda lp: -abs(lp.area))
    parent: dict[int, int | None] = {}
    for i, lp in enumerate(lps):
        parent[i] = None
        for j in range(i - 1, -1, -1):  # the smallest bigger loop that holds it
            if abs(lps[j].area) > abs(lp.area) and _inside(_nudge(lp), lps[j].poly):
                parent[i] = j
                break
        if parent[i] is None:
            for j in range(i):
                if _crosses(lp, lps[j]):
                    raise SketchError(f"the loops through {lp.names} and through {lps[j].names} cross each other")

    def depth(i: int) -> int:
        d = 0
        while parent[i] is not None:
            i = parent[i]
            d += 1
        return d

    out = []
    for i, lp in enumerate(lps):
        if depth(i) % 2 == 0:
            holes = [lps[k] for k in parent if parent[k] == i]
            out.append((lp, holes))
    return out


def _nudge(lp: Loop) -> tuple[float, float]:
    """A point to test nesting with: a circle's centre, else the first outline point."""
    xs = [p[0] for p in lp.poly]
    ys = [p[1] for p in lp.poly]
    return (sum(xs) / len(xs), sum(ys) / len(ys)) if len(lp.pieces) == 1 and lp.pieces[0].geo.kind == "CIRCLE" \
        else lp.poly[0]


def _crosses(a: Loop, b: Loop) -> bool:
    ina = sum(_inside(p, b.poly) for p in a.poly)
    return 0 < ina < len(a.poly)


# =============================================================================
# kernel
# =============================================================================

def faces(sk: Sketch):
    """OCCT faces (in world space, on the sketch plane), one per region."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.ShapeFix import ShapeFix_Face

    from ..geometry import robust

    out = []
    for outer, holes in regions(sk):
        maker = BRepBuilderAPI_MakeFace(_plane(sk), _wire(sk, outer, BRepBuilderAPI_MakeWire), True)
        for h in holes:
            w = _wire(sk, h, BRepBuilderAPI_MakeWire)
            maker.Add(w)
        if not maker.IsDone():
            raise SketchError(f"the kernel could not make a face from the loop through {outer.names}")
        fix = ShapeFix_Face(maker.Face())
        fix.FixOrientation()
        fix.Perform()
        face = fix.Face()
        if not robust.is_valid(face):
            raise SketchError(f"the face from the loop through {outer.names} is not valid")
        out.append(face)
    return out


def _gp(sk: Sketch, uv):
    from OCP.gp import gp_Pnt

    return gp_Pnt(*sk.frame.point(uv[0], uv[1]))


def _plane(sk: Sketch):
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt

    f = sk.frame
    return gp_Pln(gp_Ax3(gp_Pnt(*f.origin), gp_Dir(*f.z), gp_Dir(*f.x)))


def edge(sk: Sketch, g: Geo):
    """One sketch curve as an OCCT edge in world space."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt

    f = sk.frame
    if g.kind == "LINE":
        return BRepBuilderAPI_MakeEdge(_gp(sk, sk.pt(g.pts["S"])), _gp(sk, sk.pt(g.pts["E"]))).Edge()
    c = sk.pt(g.pts["C"])
    circ = gp_Circ(gp_Ax2(gp_Pnt(*f.point(*c)), gp_Dir(*f.z), gp_Dir(*f.x)), sk.radius(g))
    if g.kind == "CIRCLE":
        return BRepBuilderAPI_MakeEdge(circ).Edge()
    a1, a2 = sk.arc_angles(g)
    arc = GC_MakeArcOfCircle(circ, math.radians(a1), math.radians(a2), True).Value()
    return BRepBuilderAPI_MakeEdge(arc).Edge()


def _wire(sk: Sketch, lp: Loop, Maker):
    from OCP.TopoDS import TopoDS

    w = Maker()
    for pc in lp.pieces:
        w.Add(edge(sk, pc.geo))
    if not w.IsDone():
        raise SketchError(f"the kernel could not join the loop through {lp.names} into one wire")
    wire = w.Wire()
    try:
        return TopoDS.Wire_s(wire)
    except AttributeError:
        return TopoDS.Wire(wire)


def curves_shape(sk: Sketch, construction: bool | None = None):
    """All sketch curves as one compound of edges (for drawing)."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    n = 0
    for g in sk.geos.values():
        if g.kind == "POINT" or (construction is not None and g.construction != construction):
            continue
        b.Add(comp, edge(sk, g))
        n += 1
    return comp if n else None
