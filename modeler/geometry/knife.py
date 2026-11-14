"""Knife cuts (M6c): cut a body along a stroke seen from a direction.

The stroke (a curve body, usually drawn on screen) is laid flat on a plane
across the direction, its open ends are carried on straight past the body,
and the result is pushed through the body along the direction:

- as a sheet, to split a solid into pieces (the kernel's splitter, so the
  pieces keep the faces' history);
- as a kerf, a slot ``width`` wide around the stroke, to cut a groove or a
  gap (a boolean, on solids and on mesh bodies alike).

A closed stroke is a cookie cutter: the piece inside it and the piece
outside it.
"""

from __future__ import annotations

import math

from OCP.BRep import BRep_Tool
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
)
from OCP.BRepLib import BRepLib_FindSurface
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.GeomAbs import GeomAbs_Arc, GeomAbs_Plane
from OCP.GeomProjLib import GeomProjLib
from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_EDGE, TopAbs_REVERSED, TopAbs_WIRE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape


class KnifeError(Exception):
    pass


def _cast(shape, kind: str):
    fn = getattr(TopoDS, f"{kind}_s", None) or getattr(TopoDS, kind)
    return fn(shape)


def stroke_wire(shape: TopoDS_Shape):
    """The stroke's one wire (a curve body made by LINE, POLYLINE, SPLINE ...)."""
    ex = TopExp_Explorer(shape, TopAbs_WIRE)
    wires = []
    while ex.More():
        wires.append(_cast(ex.Current(), "Wire"))
        ex.Next()
    if len(wires) > 1:
        raise KnifeError("the stroke has more than one curve; draw it as one curve")
    if wires:
        return wires[0]
    ex = TopExp_Explorer(shape, TopAbs_EDGE)
    mk = BRepBuilderAPI_MakeWire()
    n = 0
    while ex.More():
        mk.Add(_cast(ex.Current(), "Edge"))
        ex.Next()
        n += 1
    if not n:
        raise KnifeError("the stroke is not a curve")
    if not mk.IsDone():
        raise KnifeError("the stroke's pieces do not join end to end")
    return mk.Wire()


def stroke_normal(wire) -> tuple[float, float, float] | None:
    """The normal of the plane the stroke lies in, or None (a straight or 3D stroke)."""
    fs = BRepLib_FindSurface(wire, 1e-6, True)
    if not fs.Found():
        return None
    from OCP.GeomAdaptor import GeomAdaptor_Surface

    ad = GeomAdaptor_Surface(fs.Surface())
    if ad.GetType() != GeomAbs_Plane:
        return None
    d = ad.Plane().Axis().Direction()
    return (d.X(), d.Y(), d.Z())


def _edges(wire) -> list:
    out = []
    ex = BRepTools_WireExplorer(wire)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def flat_wire(wire, plane: gp_Pln):
    """The stroke laid flat on ``plane`` (projected along its normal), edge by edge."""
    from OCP.Geom import Geom_Plane, Geom_TrimmedCurve

    gpl = Geom_Plane(plane)
    mk = BRepBuilderAPI_MakeWire()
    for e in _edges(wire):
        got = BRep_Tool.Curve_s(e, 0.0, 0.0)
        crv = got[0] if isinstance(got, tuple) else got
        try:
            t0, t1 = BRep_Tool.Range_s(e)
        except TypeError:  # older bindings return the range through the call above
            t0, t1 = got[1], got[2]
        if crv is None:
            continue
        trimmed = Geom_TrimmedCurve(crv, t0, t1)
        flat = GeomProjLib.ProjectOnPlane_s(trimmed, gpl, plane.Axis().Direction(), True)
        a, b = flat.Value(flat.FirstParameter()), flat.Value(flat.LastParameter())
        if a.Distance(b) < 1e-9 and not BRep_Tool.IsClosed_s(e):
            continue  # an edge along the direction: nothing left of it
        fe = BRepBuilderAPI_MakeEdge(flat).Edge()
        if e.Orientation() == TopAbs_REVERSED:
            fe = _cast(fe.Reversed(), "Edge")
        mk.Add(fe)
        if not mk.IsDone():
            raise KnifeError("the stroke, seen from the direction, does not join end to end")
    if not mk.IsDone():
        raise KnifeError("the stroke, seen from the direction, is a single point")
    return mk.Wire()


def _ends(wire):
    """(start point, direction out of the start), (end point, direction out of the end)."""
    from OCP.BRepAdaptor import BRepAdaptor_CompCurve

    c = BRepAdaptor_CompCurve(wire)
    t0, t1 = c.FirstParameter(), c.LastParameter()
    p0, v0 = gp_Pnt(), gp_Vec()
    p1, v1 = gp_Pnt(), gp_Vec()
    c.D1(t0, p0, v0)
    c.D1(t1, p1, v1)
    return (p0, v0.Reversed()), (p1, v1)


def _straight(wire) -> bool:
    from OCP.BRepAdaptor import BRepAdaptor_CompCurve

    c = BRepAdaptor_CompCurve(wire)
    t0, t1 = c.FirstParameter(), c.LastParameter()
    a, b = c.Value(t0), c.Value(t1)
    ab = gp_Vec(a, b)
    L = ab.Magnitude()
    if L < 1e-12:
        return False
    for i in range(1, 16):
        q = c.Value(t0 + (t1 - t0) * i / 16)
        if ab.Crossed(gp_Vec(a, q)).Magnitude() / L > 1e-7 * L:
            return False
    return True


def _closed(wire) -> bool:
    (p0, _), (p1, _) = _ends(wire)
    return p0.Distance(p1) < 1e-7


def extended(wire, reach: float):
    """An open stroke with straight lines added at both ends, ``reach`` long,
    so it runs right through the body."""
    (p0, v0), (p1, v1) = _ends(wire)
    mk = BRepBuilderAPI_MakeWire()
    for p, v in ((p0, v0),):
        if v.Magnitude() > 1e-12:
            q = p.Translated(v.Normalized() * reach)
            mk.Add(BRepBuilderAPI_MakeEdge(q, p).Edge())
    for e in _edges(wire):
        mk.Add(e)
    if v1.Magnitude() > 1e-12:
        mk.Add(BRepBuilderAPI_MakeEdge(p1, p1.Translated(v1.Normalized() * reach)).Edge())
    if not mk.IsDone():
        raise KnifeError("could not carry the stroke past the body")
    return mk.Wire()


class Cut:
    """The cutting tools for one stroke, one body and one direction."""

    def __init__(self, body: TopoDS_Shape, stroke: TopoDS_Shape, direction=None) -> None:
        wire = stroke_wire(stroke)
        if direction is None:
            direction = stroke_normal(wire)
            if direction is None:
                raise KnifeError("the stroke is straight (or not flat), so the direction to cut along is not clear: "
                                 "give it (dx, dy, dz), e.g. the view direction")
        n = math.sqrt(sum(c * c for c in direction))
        if n < 1e-12:
            raise KnifeError("the direction is zero")
        self.d = gp_Dir(*(c / n for c in direction))
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        box = Bnd_Box()
        for s in (body, stroke):
            BRepBndLib.Add_s(s, box, False)
            if box.IsVoid():
                BRepBndLib.Add_s(s, box, True)
        lo, hi = box.CornerMin(), box.CornerMax()
        x0, y0, z0, x1, y1, z1 = lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()
        self.centre = gp_Pnt((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
        self.reach = 1.5 * math.dist((x0, y0, z0), (x1, y1, z1)) + 1.0
        self.plane = gp_Pln(gp_Ax3(self.centre.Translated(gp_Vec(self.d) * -self.reach), self.d))
        self.closed = _closed(wire)
        flat = flat_wire(wire, self.plane)
        self.closed = self.closed or _closed(flat)
        self.flat = flat if self.closed else extended(flat, self.reach)

    def _push(self, shape):
        """Sweep a flat shape along the direction right through the body."""
        mk = BRepPrimAPI_MakePrism(shape, gp_Vec(self.d) * (2 * self.reach))
        mk.Build()
        if not mk.IsDone():
            raise KnifeError("the kernel could not push the stroke through the body")
        return mk.Shape()

    def sheet(self):
        """The surface the knife moves through (a closed stroke: a tube)."""
        return self._push(self.flat)

    def inside(self):
        """A closed stroke: the solid inside it, right through the body."""
        face = BRepBuilderAPI_MakeFace(self.flat, True)
        if not face.IsDone():
            raise KnifeError("the closed stroke does not make a flat face (does it cross itself?)")
        return self._push(face.Face())

    def kerf(self, width: float):
        """A slot ``width`` wide around the stroke, right through the body."""
        h = width / 2
        if self.closed:
            outer, inner = _offset(self.flat, h), _offset(self.flat, -h)
            if robust_area(outer) < robust_area(inner):
                outer, inner = inner, outer
            mk = BRepBuilderAPI_MakeFace(outer, True)
            inner.Reverse()
            mk.Add(_cast(inner, "Wire"))
            if not mk.IsDone():
                raise KnifeError("could not make the slot around the closed stroke")
            from OCP.ShapeFix import ShapeFix_Face

            fix = ShapeFix_Face(mk.Face())
            fix.FixOrientation()
            fix.Perform()
            return self._push(fix.Face())
        if _straight(self.flat):  # the offset could not tell which plane a straight stroke is in
            return self._push(self._band(h))
        outline = _offset(self.flat, h)
        face = BRepBuilderAPI_MakeFace(outline, True)
        if not face.IsDone():
            raise KnifeError("could not make the slot around the stroke")
        return self._push(face.Face())

    def _band(self, h: float):
        """The slot around a straight stroke: a rectangle 2h wide on the plane."""
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon

        (p0, _), (p1, _) = _ends(self.flat)
        along = gp_Vec(p0, p1)
        side = gp_Vec(self.d).Crossed(along)
        if side.Magnitude() < 1e-12:
            raise KnifeError("the stroke runs along the direction, so seen from it there is nothing to cut")
        side = side.Normalized() * h
        poly = BRepBuilderAPI_MakePolygon(p0.Translated(side), p1.Translated(side), p1.Translated(side.Reversed()),
                                          p0.Translated(side.Reversed()), True)
        return BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()


def _offset(wire, d: float):
    mk = BRepOffsetAPI_MakeOffset(wire, GeomAbs_Arc, False)
    mk.Perform(d)
    if not mk.IsDone():
        raise KnifeError("the kernel could not make the slot outline (try a narrower width, or a smoother stroke)")
    ex = TopExp_Explorer(mk.Shape(), TopAbs_WIRE)
    best, area = None, -1.0
    while ex.More():
        w = _cast(ex.Current(), "Wire")
        a = robust_area(w)
        if a > area:
            best, area = w, a
        ex.Next()
    if best is None:
        raise KnifeError("the slot outline came out empty (the width may be too big for the stroke's bends)")
    return best


def robust_area(wire) -> float:
    face = BRepBuilderAPI_MakeFace(wire, True)
    if not face.IsDone():
        return 0.0
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face.Face(), g)
    return abs(g.Mass())
