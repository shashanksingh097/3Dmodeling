"""Kernel work for datums and part features: holes, split, shell, draft, offset.

Commands call these with plain numbers and shapes; nothing here knows about
the command language or the model's IDs.
"""

from __future__ import annotations

import math

from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon,
    BRepBuilderAPI_MakeVertex,
    BRepBuilderAPI_Transform,
)
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepOffset import BRepOffset_Mode
from OCP.BRepOffsetAPI import BRepOffsetAPI_DraftAngle, BRepOffsetAPI_MakeOffsetShape, BRepOffsetAPI_MakeThickSolid
from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_JoinType, GeomAbs_SurfaceType
from OCP.gp import gp_Ax1, gp_Ax3, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf
from OCP.TopAbs import TopAbs_REVERSED
from OCP.TopoDS import TopoDS, TopoDS_Shape

from ..core import datum as dt
from . import robust

try:  # OCP 7.x
    from OCP.TopTools import TopTools_ListOfShape
except ImportError:  # OCP 8.x
    from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape  # type: ignore[no-redef]


def _static(cls, name):
    return getattr(cls, name + "_s", None) or getattr(cls, name)


as_face = _static(TopoDS, "Face")
as_edge = _static(TopoDS, "Edge")
as_vertex = _static(TopoDS, "Vertex")

_S = GeomAbs_SurfaceType
_C = GeomAbs_CurveType


class FeatureError(Exception):
    pass


def _xyz(p) -> dt.P3:
    return (p.X(), p.Y(), p.Z())


def _pnt(p) -> gp_Pnt:
    return gp_Pnt(*p)


# =============================================================================
# Placing shapes in a datum's frame (work planes)
# =============================================================================


def to_world(shape: TopoDS_Shape, frame: dt.Datum | None) -> TopoDS_Shape:
    """A shape built in the frame's local coordinates, moved to where the frame is."""
    if frame is None:
        return shape
    t = gp_Trsf()
    t.SetTransformation(gp_Ax3(_pnt(frame.origin), gp_Dir(*frame.z), gp_Dir(*frame.x)), gp_Ax3())
    moved = BRepBuilderAPI_Transform(shape, t, True).Shape()
    return _same_type(moved, shape)


def _same_type(shape: TopoDS_Shape, like: TopoDS_Shape) -> TopoDS_Shape:
    """Give a transformed shape back its own class (a wire stays a TopoDS_Wire)."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_WIRE

    cast = {TopAbs_WIRE: _static(TopoDS, "Wire"), TopAbs_EDGE: as_edge, TopAbs_FACE: as_face}.get(like.ShapeType())
    return cast(shape) if cast else shape


# =============================================================================
# Reading geometry off faces and edges
# =============================================================================


def face_plane(face) -> tuple[dt.P3, dt.P3] | None:
    """(centre, outward normal) of a planar face, or None when it is curved."""
    face = as_face(face)
    s = BRepAdaptor_Surface(face)
    if s.GetType() != _S.GeomAbs_Plane:
        return None
    d = s.Plane().Axis().Direction()
    n = (d.X(), d.Y(), d.Z())
    if face.Orientation() == TopAbs_REVERSED:
        n = (-n[0], -n[1], -n[2])
    from ..commands.queries import centre

    return tuple(centre("FACE", face)), n  # type: ignore[return-value]


def face_axis(face) -> tuple[dt.P3, dt.P3] | None:
    """Axis (point, direction) of a cylinder, cone, sphere-free revolved face."""
    s = BRepAdaptor_Surface(as_face(face))
    t = s.GetType()
    ax = {_S.GeomAbs_Cylinder: lambda: s.Cylinder().Axis(), _S.GeomAbs_Cone: lambda: s.Cone().Axis(),
          _S.GeomAbs_Torus: lambda: s.Torus().Axis()}.get(t)
    if ax is None:
        return None
    a = ax()
    return _xyz(a.Location()), _xyz(a.Direction())


def edge_line(edge) -> tuple[dt.P3, dt.P3] | None:
    """(start point, direction) of a straight edge."""
    c = BRepAdaptor_Curve(as_edge(edge))
    if c.GetType() != _C.GeomAbs_Line:
        return None
    p0, p1 = c.Value(c.FirstParameter()), c.Value(c.LastParameter())
    return _xyz(p0), dt.unit(dt.sub(_xyz(p1), _xyz(p0)))


def edge_circle(edge) -> tuple[dt.P3, dt.P3, float] | None:
    """(centre, axis direction, radius) of a circular edge."""
    c = BRepAdaptor_Curve(as_edge(edge))
    if c.GetType() != _C.GeomAbs_Circle:
        return None
    circ = c.Circle()
    return _xyz(circ.Location()), _xyz(circ.Axis().Direction()), circ.Radius()


def edge_frame(edge, t: float) -> tuple[dt.P3, dt.P3]:
    """Point and unit tangent at fraction t (0..1) along an edge."""
    from OCP.gp import gp_Vec

    c = BRepAdaptor_Curve(as_edge(edge))
    u = c.FirstParameter() + t * (c.LastParameter() - c.FirstParameter())
    p, v = gp_Pnt(), gp_Vec()
    c.D1(u, p, v)
    tangent = (v.X(), v.Y(), v.Z())
    if as_edge(edge).Orientation() == TopAbs_REVERSED:
        tangent = dt.mul(tangent, -1)
    return _xyz(p), dt.unit(tangent, "edge tangent")


def vertex_point(v) -> dt.P3:
    from OCP.BRep import BRep_Tool

    return _xyz(BRep_Tool.Pnt_s(as_vertex(v)))


def datum_shape(d: dt.Datum, size: float = 1e5) -> TopoDS_Shape:
    """A finite stand-in for a datum, for distance measurements."""
    if d.kind == "POINT":
        return BRepBuilderAPI_MakeVertex(_pnt(d.origin)).Vertex()
    if d.kind == "AXIS":
        return BRepBuilderAPI_MakeEdge(_pnt(dt.add(d.origin, dt.mul(d.z, -size))),
                                       _pnt(dt.add(d.origin, dt.mul(d.z, size)))).Edge()
    return plane_face(d, d.origin, size)


def plane_face(d: dt.Datum, around: dt.P3, half: float) -> TopoDS_Shape:
    """A square piece of the plane, centred where ``around`` projects onto it."""
    u, v, _ = d.local(around)
    pln = gp_Pln(gp_Ax3(_pnt(d.origin), gp_Dir(*d.z), gp_Dir(*d.x)))
    return BRepBuilderAPI_MakeFace(pln, u - half, u + half, v - half, v + half).Face()


def distance(a: TopoDS_Shape, b: TopoDS_Shape) -> tuple[float, dt.P3, dt.P3]:
    d = BRepExtrema_DistShapeShape(a, b)
    if not d.IsDone() or d.NbSolution() == 0:
        raise FeatureError("the kernel could not measure that distance")
    return d.Value(), _xyz(d.PointOnShape1(1)), _xyz(d.PointOnShape2(1))


# =============================================================================
# History adapters: each maker reports what became of the old faces in its own
# way; these answer in the Modified/IsDeleted terms the model understands.
# =============================================================================


class Renamed:
    """History where ``new_of(old)`` lists what an old entity became, and
    entities in ``gone`` were removed on purpose."""

    def __init__(self, new_of, gone=()) -> None:
        self.new_of = new_of
        self.gone = list(gone)

    def _is_gone(self, old) -> bool:
        return any(old.IsSame(g) for g in self.gone)

    def IsDeleted(self, old) -> bool:
        return self._is_gone(old)

    def Modified(self, old):
        if self._is_gone(old):
            return []
        try:
            return [s for s in self.new_of(old) if not s.IsNull()]
        except Exception:
            return []


# =============================================================================
# HOLE
# =============================================================================

HOLE_KINDS = ("SIMPLE", "CBORE", "CSINK")


def hole_tool(origin: dt.P3, drill: dt.P3, d: float, depth: float, kind: str = "SIMPLE",
              d2: float = 0.0, h2: float = 0.0, tip: float = 0.0) -> TopoDS_Shape:
    """The solid a hole removes: drilled from ``origin`` along ``drill``.

    It starts a little above the surface, so the cut never leaves a skin.
    CBORE: a wider step of diameter d2 and depth h2. CSINK: a cone of
    diameter d2 at the surface with an included angle h2 (degrees).
    tip: included angle of a drill point at the bottom (0 = flat).
    """
    r = d / 2
    lift = max(1.0, d)
    prof: list[tuple[float, float]] = []
    if kind == "SIMPLE":
        prof = [(0, -lift), (r, -lift)]
    elif kind == "CBORE":
        if not d2 > d or not 0 < h2 < depth:
            raise FeatureError("a counterbore needs d2 larger than d and a step depth between 0 and the hole depth")
        prof = [(0, -lift), (d2 / 2, -lift), (d2 / 2, h2), (r, h2)]
    elif kind == "CSINK":
        angle = h2 or 90.0
        if not d2 > d or not 0 < angle < 180:
            raise FeatureError("a countersink needs d2 larger than d and an angle between 0 and 180 degrees")
        hc = (d2 / 2 - r) / math.tan(math.radians(angle / 2))
        if hc >= depth:
            raise FeatureError("the countersink is deeper than the hole")
        prof = [(0, -lift), (d2 / 2 + lift * math.tan(math.radians(angle / 2)), -lift), (r, hc)]
    else:
        raise FeatureError(f"kind must be one of {', '.join(HOLE_KINDS)}")
    if tip:
        if not 0 < tip < 180:
            raise FeatureError("the drill point angle must be between 0 and 180 degrees")
        prof += [(r, depth), (0, depth + r / math.tan(math.radians(tip / 2)))]
    else:
        prof += [(r, depth), (0, depth)]
    z = dt.unit(drill, "drill direction")
    x, _, _ = dt.plane_axes(z)
    poly = BRepBuilderAPI_MakePolygon()
    for u, w in prof:
        poly.Add(_pnt(dt.add(origin, dt.add(dt.mul(x, u), dt.mul(z, w)))))
    poly.Close()
    face = BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()
    rev = BRepPrimAPI_MakeRevol(face, gp_Ax1(_pnt(origin), gp_Dir(*z)), 2 * math.pi)
    rev.Build()
    if not rev.IsDone():
        raise FeatureError("could not make the hole's shape")
    return rev.Shape()


# =============================================================================
# SPLIT
# =============================================================================


def split(shape: TopoDS_Shape, tools: list[TopoDS_Shape]):
    """Cut a body into pieces with faces or bodies. Returns (solids, maker)."""
    sp = BRepAlgoAPI_Splitter()
    a, t = TopTools_ListOfShape(), TopTools_ListOfShape()
    a.Append(shape)
    for s in tools:
        t.Append(s)
    sp.SetArguments(a)
    sp.SetTools(t)
    sp.Build()
    if not sp.IsDone():
        raise FeatureError("the kernel could not split the body")
    return robust.solids(sp.Shape()), sp


# =============================================================================
# SHELL, OFFSET, DRAFT
# =============================================================================


def thick_solid(shape: TopoDS_Shape, open_faces: list, offset: float):
    """Hollow a solid, removing ``open_faces``; offset < 0 puts the wall inside."""
    lst = TopTools_ListOfShape()
    for f in open_faces:
        lst.Append(f)
    mk = BRepOffsetAPI_MakeThickSolid()
    mk.MakeThickSolidByJoin(shape, lst, offset, 1e-6)
    mk.Build()
    if not mk.IsDone():
        return None, None
    return mk.Shape(), Renamed(lambda old: [], gone=open_faces)


def offset_shape(shape: TopoDS_Shape, d: float, sharp: bool = False):
    mo = BRepOffsetAPI_MakeOffsetShape()
    join = GeomAbs_JoinType.GeomAbs_Intersection if sharp else GeomAbs_JoinType.GeomAbs_Arc
    mo.PerformByJoin(shape, d, 1e-6, BRepOffset_Mode.BRepOffset_Skin, False, False, join)
    if not mo.IsDone():
        return None, None
    return mo.Shape(), Renamed(lambda old: list(mo.Generated(old)))


def draft(shape: TopoDS_Shape, faces: list, pull: dt.P3, angle_deg: float, neutral: dt.Datum):
    """Tilt faces by an angle about where they meet the neutral plane.

    Returns (shape, maker, bad) where bad is the index of the first face the
    kernel refused (then shape is None)."""
    dr = BRepOffsetAPI_DraftAngle(shape)
    pln = gp_Pln(_pnt(neutral.origin), gp_Dir(*neutral.z))
    for i, f in enumerate(faces):
        dr.Add(as_face(f), gp_Dir(*pull), math.radians(angle_deg), pln)
        if not dr.AddDone():
            return None, None, i
    dr.Build()
    if not dr.IsDone():
        return None, None, -1
    return dr.Shape(), Renamed(lambda old: [dr.ModifiedShape(old)]), None
