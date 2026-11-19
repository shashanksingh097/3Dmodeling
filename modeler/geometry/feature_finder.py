"""Finding features in a solid from its faces alone (so it works on imported bodies too):
fillets and rounds, chamfers, bosses and pins, pockets and slots. Holes are in
recognize.py. Face numbers are 1-based indices of the body's face map.

The rules are simple and say what they found, not what was meant:

* **fillet / round**: a part of a cylinder or torus (less than half way round) that
  meets its neighbours smoothly; concave (in a corner) is a fillet, convex (on an
  edge) a round;
* **chamfer**: a narrow flat strip between two faces, tilted to both;
* **boss / pin**: a convex cylinder that goes all the way round, with a flat end;
* **pocket / slot**: a flat floor whose every neighbour rises above it (the walls of a
  recess open on the other side); a slot when the floor is long and narrow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp_Explorer

from . import recognize as rc

P3 = tuple[float, float, float]


@dataclass
class Feature:
    kind: str  # fillet, round, chamfer, boss, pocket, slot
    faces: list[int]
    size: float = 0.0  # radius, chamfer width, boss diameter, pocket depth
    axis: P3 | None = None
    at: P3 | None = None
    extra: dict = field(default_factory=dict)


def _area(face) -> float:
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, g)
    return g.Mass()


def _edges(face) -> list:
    out = []
    ex = TopExp_Explorer(face, TopAbs_EDGE)
    while ex.More():
        out.append(rc.as_edge(ex.Current()))
        ex.Next()
    return out


def _perimeter_of_edge(edge) -> float:
    g = GProp_GProps()
    BRepGProp.LinearProperties_s(edge, g)
    return g.Mass()


def _strip_width(face) -> float:
    """How far the face reaches from its longest straight edge (a strip's width)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_CurveType

    edges = [e for e in _edges(face) if BRepAdaptor_Curve(e).GetType() == GeomAbs_CurveType.GeomAbs_Line]
    if not edges:
        return 0.0
    e = max(edges, key=_perimeter_of_edge)
    c = BRepAdaptor_Curve(e)
    a, b = rc._xyz(c.Value(c.FirstParameter())), rc._xyz(c.Value(c.LastParameter()))
    d = rc._sub(b, a)
    ln = rc._norm(d)
    if ln <= 0:
        return 0.0
    d = tuple(k / ln for k in d)
    far = 0.0
    for o in _edges(face):
        oc = BRepAdaptor_Curve(o)
        for t in (oc.FirstParameter(), oc.LastParameter()):
            v = rc._sub(rc._xyz(oc.Value(t)), a)
            perp = rc._sub(v, tuple(k * rc._dot(v, d) for k in d))
            far = max(far, rc._norm(perp))
    return far


def _normal_at(face, pt: P3) -> P3 | None:
    """The face's outward normal at the point of it nearest to pt."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt, gp_Vec

    try:
        proj = GeomAPI_ProjectPointOnSurf(gp_Pnt(*pt), BRep_Tool.Surface_s(face))
        if proj.NbPoints() < 1:
            return None
        u, v = proj.LowerDistanceParameters()
        q, n = gp_Pnt(), gp_Vec()
        BRepGProp_Face(face).Normal(u, v, q, n)
        ln = n.Magnitude()
        return (n.X() / ln, n.Y() / ln, n.Z() / ln) if ln > 1e-15 else None
    except Exception:  # noqa: BLE001
        return None


def _blends_in(face, neighbours: list, axis: P3) -> bool:
    """A blend meets the faces beside it smoothly along its straight edges (those along its axis);
    an arc of a cam or a gear tooth meets them at a corner."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_CurveType

    sides = 0
    for e in _edges(face):
        c = BRepAdaptor_Curve(e)
        if c.GetType() != GeomAbs_CurveType.GeomAbs_Line:
            continue
        if abs(abs(rc._dot(rc._xyz(c.Line().Direction()), axis)) - 1) > 1e-6:
            continue
        mid = rc._xyz(c.Value((c.FirstParameter() + c.LastParameter()) / 2))
        mine = _normal_at(face, mid)
        if mine is None:
            return False
        other = None
        for f in neighbours:
            if _edge_in(e, f):
                other = _normal_at(f, mid)
                break
        if other is None or rc._dot(mine, other) < 0.996:  # within about 5 degrees
            return False
        sides += 1
    return sides >= 1


def _edge_in(edge, face) -> bool:
    ex = TopExp_Explorer(face, TopAbs_EDGE)
    while ex.More():
        if ex.Current().IsSame(edge):
            return True
        ex.Next()
    return False


def _angle(a: P3, b: P3) -> float:
    c = max(-1.0, min(1.0, rc._dot(a, b)))
    return math.degrees(math.acos(c))


def _face_box(face) -> tuple[P3, P3]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    bb = Bnd_Box()
    BRepBndLib.AddOptimal_s(face, bb, False, False)
    lo, hi = bb.CornerMin(), bb.CornerMax()
    return (lo.X(), lo.Y(), lo.Z()), (hi.X(), hi.Y(), hi.Z())


def _extent_along(face, d: P3) -> tuple[float, float]:
    """The face's lowest and highest point along d (from its edges' sample points)."""
    lo, hi = math.inf, -math.inf
    from OCP.BRepAdaptor import BRepAdaptor_Curve

    ex = TopExp_Explorer(face, TopAbs_EDGE)
    while ex.More():
        c = BRepAdaptor_Curve(rc.as_edge(ex.Current()))
        t0, t1 = c.FirstParameter(), c.LastParameter()
        for k in range(9):
            pt = rc._xyz(c.Value(t0 + (t1 - t0) * k / 8))
            v = rc._dot(pt, d)
            lo, hi = min(lo, v), max(hi, v)
        ex.Next()
    return lo, hi


def find(shape, size_hint: float | None = None) -> list[Feature]:
    """Every feature found, by kind then size."""
    faces = rc.shape_map(shape, TopAbs_FACE)
    nb = rc.neighbours(shape, faces)
    n = faces.Extent()
    if n > 3000:
        return []  # a mesh or a sculpted body: nothing to name
    info: dict[int, dict] = {}
    for i in range(1, n + 1):
        f = rc.as_face(faces.FindKey(i))
        s = BRepAdaptor_Surface(f)
        t = s.GetType()
        p, nrm = rc.face_normal_at_middle(f)
        row = {"face": f, "type": t, "p": p, "n": nrm}
        if t == GeomAbs_SurfaceType.GeomAbs_Cylinder:
            ci = rc._cylinder_info(f)
            if ci:
                row["cyl"] = ci
        elif t == GeomAbs_SurfaceType.GeomAbs_Torus:
            tor = s.Torus()
            u0, u1, v0, v1 = BRepTools.UVBounds_s(f)
            row["torus"] = (tor.MinorRadius(), tor.MajorRadius(), u1 - u0, v1 - v0)
        info[i] = row
    out: list[Feature] = []
    used: set[int] = set()
    lo, hi = _face_box(shape)
    big = max(hi[k] - lo[k] for k in range(3))  # a blend is small next to the body

    # fillets and rounds
    for i, row in info.items():
        if "cyl" in row:
            loc, d, r, span, _v, concave = row["cyl"]
            if (span < math.pi - 1e-6 and r <= 0.2 * big
                    and _blends_in(row["face"], [info[j]["face"] for j in nb[i]], d)):
                out.append(Feature("fillet" if concave else "round", [i], r, d))
                used.add(i)
        elif "torus" in row:
            rmin, _R, su, sv = row["torus"]
            if min(su, sv) < math.pi - 1e-6 and rmin <= 0.2 * big:
                # concave when the normal points towards the tube's centre line
                s = BRepAdaptor_Surface(row["face"]).Torus()
                ax = s.Position()
                c, d = rc._xyz(ax.Location()), rc._xyz(ax.Direction())
                rel = rc._sub(row["p"], c)
                radial = rc._sub(rel, tuple(k * rc._dot(rel, d) for k in d))
                ln = rc._norm(radial) or 1.0
                ring = rc._add_scaled(c, tuple(k / ln for k in radial), s.MajorRadius())
                concave = rc._dot(rc._sub(row["p"], ring), row["n"]) < 0
                out.append(Feature("fillet" if concave else "round", [i], rmin, d, extra={"corner": True}))
                used.add(i)

    # chamfers: a narrow flat strip tilted to the two big faces it joins
    for i, row in info.items():
        if row["type"] != GeomAbs_SurfaceType.GeomAbs_Plane or i in used:
            continue
        f = row["face"]
        width = _strip_width(f)
        if width <= 0:
            continue
        planes = [j for j in nb[i] if info[j]["type"] == GeomAbs_SurfaceType.GeomAbs_Plane]
        big = sorted(planes, key=lambda j: -_area(info[j]["face"]))[:2]
        if len(big) < 2:
            continue
        a1 = _angle(row["n"], info[big[0]]["n"])
        a2 = _angle(row["n"], info[big[1]]["n"])
        longest = max(rc._norm(rc._sub(*_face_box(f))), 1e-9)
        if 15 < a1 < 75 and 15 < a2 < 75 and width < 0.25 * longest:
            # the distances along the two faces (equal for a 45 degree chamfer)
            d1, d2 = width * math.cos(math.radians(a1)), width * math.cos(math.radians(a2))
            out.append(Feature("chamfer", [i], d1, extra={"d2": d2, "angles": (round(a1, 1), round(a2, 1))}))
            used.add(i)

    # bosses and pins: convex full cylinders (several faces on one axis count as one)
    groups: list[dict] = []
    for i, row in info.items():
        if "cyl" not in row or i in used:
            continue
        loc, d, r, span, (v0, v1), concave = row["cyl"]
        if concave:
            continue
        for g in groups:
            if abs(g["r"] - r) < 1e-6 * max(1, r) and abs(abs(rc._dot(g["d"], d)) - 1) < 1e-9:
                off = rc._sub(loc, g["loc"])
                perp = rc._sub(off, tuple(c * rc._dot(off, g["d"]) for c in g["d"]))
                if rc._norm(perp) < 1e-6 * max(1, r):
                    g["faces"].append(i)
                    g["span"] += span
                    break
        else:
            groups.append({"loc": loc, "d": d, "r": r, "span": span, "faces": [i]})
    for g in groups:
        if g["span"] < 2 * math.pi - 1e-6:
            continue
        lo, hi = math.inf, -math.inf
        for i in g["faces"]:
            a, b = _extent_along(info[i]["face"], g["d"])
            lo, hi = min(lo, a), max(hi, b)
        ends = [j for i in g["faces"] for j in nb[i]
                if info[j]["type"] == GeomAbs_SurfaceType.GeomAbs_Plane and abs(abs(rc._dot(info[j]["n"], g["d"])) - 1) < 1e-6]
        # it stands on a bigger face (its base, with the boss as a loop inside it); a cylinder with
        # no such face is the outside of the body itself (a disc, a shaft), not a boss
        base = [j for j in ends if _area(info[j]["face"]) > math.pi * g["r"] ** 2 * 1.05]
        if not base:
            continue
        level = rc._dot(info[base[0]]["p"], g["d"])
        if abs(level - hi) < abs(level - lo):  # standing the other way: up is -d
            g["d"] = tuple(-c for c in g["d"])
            lo, hi = -hi, -lo
        foot = rc._add_scaled(g["loc"], g["d"], lo - rc._dot(g["loc"], g["d"]))
        out.append(Feature("boss", sorted(g["faces"]), 2 * g["r"], g["d"], foot, {"height": hi - lo}))
        used.update(g["faces"])

    # pockets and slots: a flat floor with every neighbour above it
    for i, row in info.items():
        if row["type"] != GeomAbs_SurfaceType.GeomAbs_Plane or i in used:
            continue
        walls = nb[i]
        if len(walls) < 2:
            continue
        nrm = row["n"]
        level = rc._dot(row["p"], nrm)
        tops = []
        ok = True
        for j in walls:
            lo, hi = _extent_along(info[j]["face"], nrm)
            if lo < level - 1e-6 or hi < level + 1e-6:
                ok = False
                break
            tops.append(hi)
        if not ok:
            continue
        depth = min(tops) - level
        if depth <= 1e-6:
            continue
        a, b = _face_box(row["face"])
        dims = sorted((abs(b[k] - a[k]) for k in range(3)), reverse=True)[:2]
        kind = "slot" if dims[1] > 0 and dims[0] / dims[1] >= 3 else "pocket"
        out.append(Feature(kind, [i] + sorted(walls), depth, nrm, row["p"],
                           {"floor": i, "size": (dims[0], dims[1])}))
    order = {"fillet": 0, "round": 1, "chamfer": 2, "boss": 3, "pocket": 4, "slot": 5}
    out.sort(key=lambda f: (order[f.kind], round(f.size, 6)))
    return out
