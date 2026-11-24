"""Features found on a body that has no history (an imported STEP part, say).

A person looking at an imported part sees holes, rounds, chamfers and rows of
holes, not faces. This module finds those from the faces alone, so they can be
listed (`FEATURES`), picked together ("select similar") and changed or removed
in bulk (`DEFEATURE`, `RESIZE`).

What counts as what:

* **HOLE**: a round hole, from `recognize.holes`, with its bottom (flat or
  pointed) and any counterbore step, so removing it removes all of it.
* **FILLET**: a part of a cylinder, torus or sphere that meets at least two of
  its neighbours smoothly (tangent). Its size is the radius.
* **CHAMFER**: a narrow flat strip between two faces that it meets at an angle
  (not smoothly), at most a quarter as wide as it is long. Its size is the
  setback on each face for a 45 degree one (`leg`), else the width across the strip.
* **PATTERN**: three or more holes of one size in a straight row with equal
  steps, or on a circle with equal angles.

Nothing here knows about IDs or commands; faces are 1-based indices into the
body's face map.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Curve2d, BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp, BRepGProp_Face
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp_Explorer

from . import recognize as rc

P3 = tuple[float, float, float]

KINDS = ("HOLE", "FILLET", "CHAMFER", "PATTERN")
_ROUND = (GeomAbs_SurfaceType.GeomAbs_Cylinder, GeomAbs_SurfaceType.GeomAbs_Torus,
          GeomAbs_SurfaceType.GeomAbs_Sphere)
TANGENT_DEG = 2.0  # faces whose normals differ by less than this along their edge meet smoothly


@dataclass
class Feature:
    kind: str  # HOLE, FILLET, CHAMFER or PATTERN
    size: float  # hole diameter, fillet radius, chamfer width, pattern: the holes' diameter
    faces: list[int] = field(default_factory=list)
    at: P3 = (0.0, 0.0, 0.0)  # a point on or in it, for showing and for finding it again
    info: dict = field(default_factory=dict)  # kind-specific: depth, through, leg, count, step ...

    def row(self, n: int) -> dict:
        out = {"n": n, "kind": self.kind, "size": round(self.size, 6), "faces": list(self.faces),
               "at": [round(c, 6) for c in self.at]}
        out.update(self.info)
        return out


def _xyz(p) -> P3:
    return (p.X(), p.Y(), p.Z())


def _face_normal(face, uv) -> P3 | None:
    g = BRepGProp_Face(face)
    p, n = gp_Pnt(), gp_Vec()
    g.Normal(uv[0], uv[1], p, n)  # BRepGProp_Face already follows the face's orientation
    ln = n.Magnitude()
    return (n.X() / ln, n.Y() / ln, n.Z() / ln) if ln > 1e-15 else None


def _edge_middle(edge):
    c = BRepAdaptor_Curve(edge)
    t = (c.FirstParameter() + c.LastParameter()) / 2
    return c, t


def normal_on_edge(face, edge) -> P3 | None:
    """The face's outward normal at the middle of one of its edges."""
    try:
        c2 = BRepAdaptor_Curve2d(edge, face)
        t = (c2.FirstParameter() + c2.LastParameter()) / 2
        uv = c2.Value(t)
    except Exception:  # noqa: BLE001 - an edge without a curve on this face
        return None
    return _face_normal(face, (uv.X(), uv.Y()))


def meets_smoothly(fa, fb, edge, deg: float = TANGENT_DEG) -> bool:
    na, nb = normal_on_edge(fa, edge), normal_on_edge(fb, edge)
    if na is None or nb is None:
        return False
    return rc._dot(na, nb) >= math.cos(math.radians(deg))


def _centre(face) -> P3:
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, g)
    return _xyz(g.CentreOfMass())


def _edges_of(face) -> list:
    out = []
    exp = TopExp_Explorer(face, TopAbs_EDGE)
    while exp.More():
        e = rc.as_edge(exp.Current())
        if not BRep_Tool.Degenerated_s(e):
            out.append(e)
        exp.Next()
    return out


def _length(edge) -> float:
    g = GProp_GProps()
    BRepGProp.LinearProperties_s(edge, g)
    return g.Mass()


class _Body:
    """Face and edge maps of one shape, worked out once."""

    def __init__(self, shape):
        self.shape = shape
        self.faces = rc.shape_map(shape, TopAbs_FACE)
        self.edges = rc.shape_map(shape, TopAbs_EDGE)
        self.em = rc.edge_faces(shape)

    def face(self, i: int):
        return rc.as_face(self.faces.FindKey(i))

    def across(self, fi: int, edge) -> int:
        """The face on the other side of an edge of face fi (0 when none)."""
        k = self.em.FindIndex(edge)
        if not k:
            return 0
        for f in rc._iter_list(self.em.FindFromIndex(k)):
            j = self.faces.FindIndex(f)
            if j and j != fi:
                return j
        return 0


def _round_radius(s: BRepAdaptor_Surface) -> float:
    t = s.GetType()
    if t == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        return s.Cylinder().Radius()
    if t == GeomAbs_SurfaceType.GeomAbs_Torus:
        return s.Torus().MinorRadius()
    return s.Sphere().Radius()


def _fillets(b: _Body, taken: set[int]) -> list[Feature]:
    out = []
    for i in range(1, b.faces.Extent() + 1):
        if i in taken:
            continue
        f = b.face(i)
        s = BRepAdaptor_Surface(f)
        if s.GetType() not in _ROUND:
            continue
        if s.GetType() == GeomAbs_SurfaceType.GeomAbs_Cylinder:
            u0, u1, _v0, _v1 = rc.BRepTools.UVBounds_s(f)
            if u1 - u0 >= 2 * math.pi - 1e-6:
                continue  # a whole cylinder: a hole, a pin or a boss, not a round
        smooth = 0
        for e in _edges_of(f):
            j = b.across(i, e)
            if j and meets_smoothly(f, b.face(j), e):
                smooth += 1
        if smooth >= 2:
            r = _round_radius(s)
            p, n = rc.face_normal_at_middle(f)
            concave = _concave(s, p, n)
            out.append(Feature("FILLET", r, [i], p, {"concave": concave,
                                                     "surface": rc.surface_type(f)}))
    return out


def _concave(s: BRepAdaptor_Surface, p: P3, n: P3) -> bool:
    """A round that fills an inside corner (its centre of curvature is outside the material)."""
    t = s.GetType()
    if t == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        ax = s.Cylinder().Axis()
        loc, d = _xyz(ax.Location()), _xyz(ax.Direction())
        foot = rc._add_scaled(loc, d, rc._dot(rc._sub(p, loc), d))
        return rc._dot(rc._sub(p, foot), n) < 0
    if t == GeomAbs_SurfaceType.GeomAbs_Sphere:
        c = _xyz(s.Sphere().Location())
        return rc._dot(rc._sub(p, c), n) < 0
    tor = s.Torus()
    ax = tor.Axis()
    loc, d = _xyz(ax.Location()), _xyz(ax.Direction())
    rel = rc._sub(p, loc)
    radial = rc._sub(rel, tuple(c * rc._dot(rel, d) for c in d))
    ln = rc._norm(radial) or 1.0
    ring = rc._add_scaled(loc, tuple(c / ln for c in radial), tor.MajorRadius())
    return rc._dot(rc._sub(p, ring), n) < 0


def _chamfers(b: _Body, taken: set[int]) -> list[Feature]:
    out = []
    for i in range(1, b.faces.Extent() + 1):
        if i in taken:
            continue
        f = b.face(i)
        if BRepAdaptor_Surface(f).GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
            continue
        edges = _edges_of(f)
        if len(edges) != 4:
            continue
        lines = [e for e in edges if BRepAdaptor_Curve(e).GetType() == rc.GeomAbs_CurveType.GeomAbs_Line]
        if len(lines) < 2:
            continue
        lens = sorted(((_length(e), e) for e in edges), key=lambda t: -t[0])
        (la, ea), (lb, eb) = lens[0], lens[1]
        if abs(la - lb) > 0.05 * la + 1e-9:
            continue  # the two long sides of a strip are about as long as each other
        ca, ta = _edge_middle(ea)
        pa = _xyz(ca.Value(ta))
        cb, tb = _edge_middle(eb)
        pb = _xyz(cb.Value(tb))
        width = _line_gap(ea, pa, pb)
        if width <= 1e-9 or width > 0.25 * la:
            continue
        nf = normal_on_edge(f, ea)
        ok = True
        angles = []
        for e in (ea, eb):
            j = b.across(i, e)
            if not j:
                ok = False
                break
            nj = normal_on_edge(b.face(j), e)
            if nf is None or nj is None:
                ok = False
                break
            ang = math.degrees(math.acos(max(-1.0, min(1.0, rc._dot(nf, nj)))))
            if not (10.0 <= ang <= 80.0):
                ok = False
                break
            angles.append(ang)
        if not ok:
            continue
        leg = width / math.sqrt(2) if all(abs(a - 45) < 1 for a in angles) else None
        info = {"length": round(la, 6), "angles": [round(a, 3) for a in angles]}
        if leg is not None:
            info["leg"] = round(leg, 6)
        info["width"] = round(width, 6)
        out.append(Feature("CHAMFER", leg if leg is not None else width, [i], _centre(f), info))
    return out


def _line_gap(edge, pa: P3, pb: P3) -> float:
    """How far pb is from the line of the straight edge through pa."""
    c = BRepAdaptor_Curve(edge)
    if c.GetType() != rc.GeomAbs_CurveType.GeomAbs_Line:
        return rc._norm(rc._sub(pa, pb))
    d = _xyz(c.Line().Direction())
    rel = rc._sub(pb, pa)
    return rc._norm(rc._sub(rel, tuple(x * rc._dot(rel, d) for x in d)))


def _hole_features(b: _Body) -> list[Feature]:
    out = []
    for h in rc.holes(b.shape):
        faces = set(h.faces)
        if not h.through:
            faces |= _bottom_faces(b, h)
        info = {"depth": round(h.depth, 6), "through": h.through,
                "axis": [round(c, 9) for c in h.axis], "mouth": [round(c, 6) for c in h.mouth]}
        if h.counterbore:
            info["counterbore"] = [round(h.counterbore[0], 6), round(h.counterbore[1], 6)]
            if h.cb_top is not None:
                info["top"] = [round(c, 6) for c in h.cb_top]
        out.append(Feature("HOLE", h.d, sorted(faces), h.centre, info))
    return out


def _bottom_faces(b: _Body, h) -> set[int]:
    """The flat or pointed bottom of a blind hole (and the step of a counterbore):
    faces next to its walls that lie inside the hole's radius, around its axis."""
    r = h.d / 2
    out: set[int] = set()
    big = (h.counterbore[0] / 2) if h.counterbore else r
    for wi in h.faces:
        w = b.face(wi)
        for e in _edges_of(w):
            j = b.across(wi, e)
            if not j or j in h.faces or j in out:
                continue
            f = b.face(j)
            t = BRepAdaptor_Surface(f).GetType()
            if t not in (GeomAbs_SurfaceType.GeomAbs_Plane, GeomAbs_SurfaceType.GeomAbs_Cone):
                continue
            if not _inside_radius(f, h, big):
                continue
            out.add(j)
    return out


def _inside_radius(face, h, r: float) -> bool:
    """Every edge of the face lies within r of the hole's axis (so the face closes the hole)."""
    for e in _edges_of(face):
        c, t = _edge_middle(e)
        for tt in (c.FirstParameter(), t, c.LastParameter()):
            p = _xyz(c.Value(tt))
            rel = rc._sub(p, h.start)
            off = rc._sub(rel, tuple(x * rc._dot(rel, h.axis) for x in h.axis))
            if rc._norm(off) > r * (1 + 1e-6) + 1e-7:
                return False
    return True


def _patterns(holes: list[tuple[int, Feature]]) -> list[Feature]:
    """Rows and rings of three or more holes of one size and direction."""
    out = []
    by_size: dict[tuple, list[tuple[int, Feature]]] = {}
    for n, h in holes:
        ax = tuple(round(abs(c), 6) for c in h.info["axis"])
        by_size.setdefault((round(h.size, 6), ax), []).append((n, h))
    for (d, _ax), group in by_size.items():
        if len(group) < 3:
            continue
        pts = [h.at for _n, h in group]
        nums = [n for n, _h in group]
        faces = sorted(f for _n, h in group for f in h.faces)
        row = _row(pts)
        if row is not None:
            step, direction = row
            out.append(Feature("PATTERN", d, faces, pts[0], {"pattern": "LINEAR", "holes": nums,
                                                             "count": len(pts), "step": round(step, 6),
                                                             "direction": [round(c, 9) for c in direction]}))
            continue
        ring = _ring(pts, group[0][1].info["axis"])
        if ring is not None:
            centre, radius, angle = ring
            out.append(Feature("PATTERN", d, faces, centre, {"pattern": "POLAR", "holes": nums,
                                                             "count": len(pts), "radius": round(radius, 6),
                                                             "angle": round(angle, 6)}))
    return out


def _row(pts: list[P3]):
    a = pts[0]
    far = max(pts, key=lambda p: rc._norm(rc._sub(p, a)))
    span = rc._norm(rc._sub(far, a))
    if span < 1e-9:
        return None
    d = tuple(c / span for c in rc._sub(far, a))
    ts = []
    for p in pts:
        rel = rc._sub(p, a)
        t = rc._dot(rel, d)
        if rc._norm(rc._sub(rel, tuple(c * t for c in d))) > 1e-6 * max(1.0, span):
            return None
        ts.append(t)
    ts.sort()
    ts = [t - ts[0] for t in ts]
    step = ts[1]
    if step < 1e-9 or any(abs(t - k * step) > 1e-6 * max(1.0, span) for k, t in enumerate(ts)):
        return None
    return step, d


def _ring(pts: list[P3], axis):
    n = len(pts)
    c = tuple(sum(p[k] for p in pts) / n for k in range(3))
    rs = [rc._norm(rc._sub(p, c)) for p in pts]
    r = sum(rs) / n
    if r < 1e-9 or any(abs(x - r) > 1e-6 * max(1.0, r) for x in rs):
        return None
    ax = tuple(axis)
    # angles round the axis, measured from the first hole
    u = rc._sub(pts[0], c)
    u = tuple(x / (rc._norm(u) or 1) for x in u)
    v = (ax[1] * u[2] - ax[2] * u[1], ax[2] * u[0] - ax[0] * u[2], ax[0] * u[1] - ax[1] * u[0])
    angs = sorted(math.degrees(math.atan2(rc._dot(rc._sub(p, c), v), rc._dot(rc._sub(p, c), u))) % 360
                  for p in pts)
    steps = [b - a for a, b in zip(angs, angs[1:])]
    step = steps[0] if steps else 0
    if step < 1e-6 or any(abs(s - step) > 1e-4 for s in steps):
        return None
    return c, r, step


def find(shape, kinds: tuple[str, ...] = KINDS) -> list[Feature]:
    """The features of a body, holes first, then fillets, chamfers and patterns."""
    b = _Body(shape)
    holes = _hole_features(b)
    taken = {f for h in holes for f in h.faces}
    out: list[Feature] = []
    if "HOLE" in kinds:
        out += holes
    fil = _fillets(b, taken)
    if "FILLET" in kinds:
        out += fil
    if "CHAMFER" in kinds:
        out += _chamfers(b, taken | {f for x in fil for f in x.faces})
    if "PATTERN" in kinds:
        numbered = [(k + 1, h) for k, h in enumerate(holes)]
        out += _patterns(numbered)
    return out


def compare(op: str, value: float, size: float, tol: float = 1e-6) -> bool:
    t = tol * max(1.0, abs(value))
    return {"ALL": True, "EQ": abs(size - value) <= t, "NE": abs(size - value) > t,
            "LT": size < value - t, "LE": size <= value + t, "GT": size > value + t,
            "GE": size >= value - t}[op]


def _sharp_edges_near(shape, points: list[P3], within: float) -> list:
    """Edges of the shape nearest to each point (used to fillet or chamfer again
    the sharp edge a removed round or chamfer left)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    edges = rc.shape_map(shape, TopAbs_EDGE)
    out, seen = [], set()
    for p in points:
        v = BRepBuilderAPI_MakeVertex(gp_Pnt(*p)).Vertex()
        best, best_d = 0, float("inf")
        for i in range(1, edges.Extent() + 1):
            d = BRepExtrema_DistShapeShape(v, edges.FindKey(i))
            if d.IsDone() and d.Value() < best_d:
                best, best_d = i, d.Value()
        if best and best_d <= within and best not in seen:
            seen.add(best)
            out.append(rc.as_edge(edges.FindKey(best)))
    return out

