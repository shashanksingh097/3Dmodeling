"""Reading a body the way a person would describe it: face types, holes, symmetry.

Plain kernel work on shapes, used by DESCRIBE and by the HOLES, PIECES,
VALID and SYMMETRIC queries. Nothing here knows about IDs or commands;
faces are given back as 1-based indices into the body's face map.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepGProp import BRepGProp_Face
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.gp import gp_Ax2, gp_Dir, gp_Lin, gp_Pnt, gp_Trsf, gp_Vec
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS, TopoDS_Shape

from . import robust

try:  # OCP 7.x
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape as _AncestorMap
    from OCP.TopTools import TopTools_IndexedMapOfShape as _ShapeMap
except ImportError:  # OCP 8.x
    from OCP.collections import (  # type: ignore[no-redef]
        IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as _AncestorMap,
    )
    from OCP.collections import (  # type: ignore[no-redef]
        IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as _ShapeMap,
    )


def _static(cls, name):
    return getattr(cls, name + "_s", None) or getattr(cls, name)


as_face = _static(TopoDS, "Face")
as_edge = _static(TopoDS, "Edge")

SURFACE_NAMES = {
    GeomAbs_SurfaceType.GeomAbs_Plane: "plane",
    GeomAbs_SurfaceType.GeomAbs_Cylinder: "cylinder",
    GeomAbs_SurfaceType.GeomAbs_Cone: "cone",
    GeomAbs_SurfaceType.GeomAbs_Sphere: "sphere",
    GeomAbs_SurfaceType.GeomAbs_Torus: "torus",
    GeomAbs_SurfaceType.GeomAbs_BezierSurface: "bezier",
    GeomAbs_SurfaceType.GeomAbs_BSplineSurface: "bspline",
    GeomAbs_SurfaceType.GeomAbs_SurfaceOfRevolution: "revolved",
    GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion: "extruded",
    GeomAbs_SurfaceType.GeomAbs_OffsetSurface: "offset",
}
CURVE_NAMES = {
    GeomAbs_CurveType.GeomAbs_Line: "line",
    GeomAbs_CurveType.GeomAbs_Circle: "circle",
    GeomAbs_CurveType.GeomAbs_Ellipse: "ellipse",
    GeomAbs_CurveType.GeomAbs_Hyperbola: "hyperbola",
    GeomAbs_CurveType.GeomAbs_Parabola: "parabola",
    GeomAbs_CurveType.GeomAbs_BezierCurve: "bezier",
    GeomAbs_CurveType.GeomAbs_BSplineCurve: "bspline",
    GeomAbs_CurveType.GeomAbs_OffsetCurve: "offset",
}

P3 = tuple[float, float, float]


def _xyz(p) -> P3:
    return (p.X(), p.Y(), p.Z())


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b) -> P3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add_scaled(a, d, t) -> P3:
    return (a[0] + d[0] * t, a[1] + d[1] * t, a[2] + d[2] * t)


def _norm(a) -> float:
    return math.sqrt(_dot(a, a))


def shape_map(shape: TopoDS_Shape, kind) -> _ShapeMap:
    m = _ShapeMap()
    TopExp.MapShapes_s(shape, kind, m)
    return m


def edge_faces(shape: TopoDS_Shape) -> _AncestorMap:
    """Each edge of the shape with the faces that use it."""
    m = _AncestorMap()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, m)
    return m


def _iter_list(lst):
    out = []
    try:
        for s in lst:
            out.append(s)
        return out
    except TypeError:  # OCP 7 lists are not iterable
        from OCP.TopTools import TopTools_ListIteratorOfListOfShape

        i = TopTools_ListIteratorOfListOfShape(lst)
        while i.More():
            out.append(i.Value())
            i.Next()
        return out


def neighbours(shape: TopoDS_Shape, faces: _ShapeMap | None = None) -> dict[int, set[int]]:
    """Face index -> indices of the faces that share an edge with it."""
    faces = faces or shape_map(shape, TopAbs_FACE)
    out: dict[int, set[int]] = {i: set() for i in range(1, faces.Extent() + 1)}
    em = edge_faces(shape)
    for i in range(1, em.Extent() + 1):
        idx = {faces.FindIndex(f) for f in _iter_list(em.FindFromIndex(i))}
        idx.discard(0)
        for a in idx:
            out[a] |= idx - {a}
    return out


def surface_type(face) -> str:
    return SURFACE_NAMES.get(BRepAdaptor_Surface(as_face(face)).GetType(), "other")


def curve_type(edge) -> str:
    return CURVE_NAMES.get(BRepAdaptor_Curve(as_edge(edge)).GetType(), "other")


def face_normal_at_middle(face) -> tuple[P3, P3]:
    """(point, outward normal) at the middle of the face's parameter range."""
    face = as_face(face)
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    g = BRepGProp_Face(face)
    p, n = gp_Pnt(), gp_Vec()
    g.Normal((u0 + u1) / 2, (v0 + v1) / 2, p, n)
    ln = n.Magnitude()
    nn = (n.X() / ln, n.Y() / ln, n.Z() / ln) if ln > 1e-15 else (0.0, 0.0, 0.0)
    return _xyz(p), nn


# ---- holes ----------------------------------------------------------------------


@dataclass
class Hole:
    """A round hole: one or more concave cylinder faces on the same axis and radius
    that together go all the way round."""

    d: float
    axis: P3  # unit direction, pointing out of the hole's first end
    start: P3  # where the hole's cylinder starts and ends on its axis
    end: P3
    faces: list[int] = field(default_factory=list)  # 1-based face indices
    through: bool = False  # the axis leaves the body at both ends without meeting material
    mouth: P3 = (0.0, 0.0, 0.0)  # the open end (the start of a through hole's axis)
    # a wider hole on the same axis that starts where this one ends: (diameter, depth)
    counterbore: tuple[float, float] | None = None

    @property
    def depth(self) -> float:
        return _norm(_sub(self.end, self.start))

    @property
    def centre(self) -> P3:
        return tuple((a + b) / 2 for a, b in zip(self.start, self.end))  # type: ignore[return-value]


def _cylinder_info(face):
    """(axis point, axis dir, radius, angle span, axial extent v0..v1, concave) or None."""
    s = BRepAdaptor_Surface(face)
    if s.GetType() != GeomAbs_SurfaceType.GeomAbs_Cylinder:
        return None
    cyl = s.Cylinder()
    ax = cyl.Axis()
    loc, d = _xyz(ax.Location()), _xyz(ax.Direction())
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    p, n = face_normal_at_middle(face)
    foot = _add_scaled(loc, d, _dot(_sub(p, loc), d))
    radial = _sub(p, foot)
    concave = _dot(radial, n) < 0
    return loc, d, cyl.Radius(), u1 - u0, (v0, v1), concave


def holes(shape: TopoDS_Shape, tol: float = 1e-6) -> list[Hole]:
    """Every round hole in a body, sorted by diameter then position."""
    faces = shape_map(shape, TopAbs_FACE)
    groups: list[dict] = []
    for i in range(1, faces.Extent() + 1):
        info = _cylinder_info(as_face(faces.FindKey(i)))
        if info is None or not info[5]:
            continue
        loc, d, r, span, (v0, v1), _ = info
        rtol = tol + 1e-7 * max(1.0, r)
        for g in groups:
            if abs(g["r"] - r) > rtol or abs(abs(_dot(g["d"], d)) - 1) > 1e-9:
                continue
            off = _sub(loc, g["loc"])
            off_perp = _sub(off, tuple(c * _dot(off, g["d"]) for c in g["d"]))
            if _norm(off_perp) > rtol * 10:
                continue
            g["faces"].append(i)
            g["span"] += span
            sign = 1.0 if _dot(g["d"], d) > 0 else -1.0
            base = _dot(off, g["d"])
            for v in (v0, v1):
                g["t"].append(base + sign * v)
            break
        else:
            groups.append({"loc": loc, "d": d, "r": r, "span": span, "faces": [i], "t": [v0, v1]})
    out = []
    for g in groups:
        if g["span"] < 2 * math.pi - 1e-6:
            continue  # a part of a cylinder: a fillet or a rounded slot end, not a hole
        t0, t1 = min(g["t"]), max(g["t"])
        a, b = _add_scaled(g["loc"], g["d"], t0), _add_scaled(g["loc"], g["d"], t1)
        h = Hole(2 * g["r"], g["d"], a, b, sorted(g["faces"]))
        open_b, open_a = _escapes(shape, b, g["d"]), _escapes(shape, a, tuple(-c for c in g["d"]))
        h.through = open_a and open_b
        h.mouth = a if open_a and not open_b else b
        out.append(h)
    out = _join_counterbores(out, tol)
    out.sort(key=lambda h: (round(h.d, 6), tuple(round(c, 6) for c in h.centre)))
    return out


def _join_counterbores(found: list[Hole], tol: float) -> list[Hole]:
    """A wide short hole that continues a narrower one on the same axis is its
    counterbore, not a hole of its own."""
    found = sorted(found, key=lambda h: h.d)
    gone: set[int] = set()
    close = 1e-6 + tol
    for i, small in enumerate(found):
        for j in range(i + 1, len(found)):
            big = found[j]
            if j in gone or big.d <= small.d + close or abs(abs(_dot(big.axis, small.axis)) - 1) > 1e-9:
                continue
            ends = [(a, b) for a in (small.start, small.end) for b in (big.start, big.end)]
            if not any(_norm(_sub(a, b)) <= close * 10 for a, b in ends):
                continue
            off = _sub(big.centre, small.centre)
            if _norm(_sub(off, tuple(c * _dot(off, small.axis) for c in small.axis))) > close * 10:
                continue
            small.counterbore = (big.d, big.depth)
            small.faces = sorted(small.faces + big.faces)
            gone.add(j)
            break
    return [h for k, h in enumerate(found) if k not in gone]


def _escapes(shape, start: P3, d: P3) -> bool:
    """True if the half-line from the end of a hole meets no face at all.

    A chamfer, countersink or counterbore lies round the axis and is not
    met; a floor, or the point of a drill tip, is."""
    return not any(hit["t"] > 1e-6 for hit in ray_hits(shape, start, d, 1e-6))


def ray_hits(shape: TopoDS_Shape, origin: P3, d: P3, tol: float = 1e-7, length: float = 1e9) -> list[dict]:
    """Where a half-line crosses the faces of a shape, nearest first.

    Each hit: t (distance along the ray), point, face (the face itself) and
    state "in" (entering material) or "out" (leaving it), from the face's
    outward normal."""
    ln = _norm(d)
    d = (d[0] / ln, d[1] / ln, d[2] / ln)
    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(shape, tol)
    inter.Perform(gp_Lin(gp_Pnt(*origin), gp_Dir(*d)), -tol, length)
    out = []
    if not inter.IsDone():
        return out
    for i in range(1, inter.NbPnt() + 1):
        face = inter.Face(i)
        p = _xyz(inter.Pnt(i))
        g = BRepGProp_Face(face)
        pp, n = gp_Pnt(), gp_Vec()
        g.Normal(inter.UParameter(i), inter.VParameter(i), pp, n)
        state = "in" if _dot(_xyz(n), d) < 0 else "out"
        out.append({"t": inter.WParameter(i), "point": p, "face": face, "state": state})
    out.sort(key=lambda h: h["t"])
    return out


# ---- symmetry -------------------------------------------------------------------


def mirror_matches(shape: TopoDS_Shape, origin: P3, normal: P3, rel: float = 1e-6) -> bool:
    """True if the solid is its own mirror image in the plane (origin, normal).

    The mirror image and the body must overlap in their whole volume."""
    vol = robust.volume(shape)
    if vol <= 0:
        raise ValueError("symmetry needs a solid with a volume")
    t = gp_Trsf()
    t.SetMirror(gp_Ax2(gp_Pnt(*origin), gp_Dir(*normal)))
    mirrored = BRepBuilderAPI_Transform(shape, t, True).Shape()
    common = BRepAlgoAPI_Common(shape, mirrored)
    if not common.IsDone():
        return False
    return abs(robust.volume(common.Shape()) - vol) <= max(rel, 1e-9) * vol * 10
