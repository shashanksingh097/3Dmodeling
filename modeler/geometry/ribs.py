"""Ribs, lips and wrapped sketches (RIB, LIP, WRAP: commands/rib_handlers.py).

RIB: an open sketch curve is the top edge of a thin wall (thickness t, half
on each side of the sketch plane). The wall fills the space between the curve
and the part's faces on one side of it: the curve's ends are carried on
straight along their tangents, that line is pushed far across the sketch
plane, made t thick, the part is cut away from it, and the piece that holds
the curve is the rib.

LIP: a raised band (or, for GROOVE, a cut step) along the inside edge of a
flat rim face, the way the two halves of an enclosure key into each other.

WRAP: a sketch's profiles laid onto a cylinder (sketch u runs round it, as
arc length; v runs along its axis) and made into a raised or sunk solid.
"""

from __future__ import annotations

import math

import numpy as np


class RibError(Exception):
    pass


def _api(cls, name):
    return getattr(cls, name + "_s", None) or getattr(cls, name)


def _pnt(q):
    from OCP.gp import gp_Pnt

    return gp_Pnt(*map(float, q))


def _vec(q):
    from OCP.gp import gp_Vec

    return gp_Vec(*map(float, q))


def _arr(p):
    return np.array([p.X(), p.Y(), p.Z()])


def chain(edges: list):
    """Join edges into one open wire, in order; RibError if they do not make one chain."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire

    ends = []
    for e in edges:
        c = BRepAdaptor_Curve(e)
        ends.append((_arr(c.Value(c.FirstParameter())), _arr(c.Value(c.LastParameter()))))

    def meets(p, i):
        return sum(1 for j, (a, b) in enumerate(ends) if j != i and
                   min(np.linalg.norm(p - a), np.linalg.norm(p - b)) < 1e-6)

    free = [i for i, (a, b) in enumerate(ends) if meets(a, i) == 0 or meets(b, i) == 0]
    if not free:
        raise RibError("the sketch's curves close up; a rib is drawn with an open line")
    order, left = [free[0]], set(range(len(edges))) - {free[0]}
    a, b = ends[free[0]]
    tip = a if meets(b, free[0]) else b  # walk away from the free end
    while left:
        nxt = next((j for j in left if min(np.linalg.norm(tip - ends[j][0]),
                                           np.linalg.norm(tip - ends[j][1])) < 1e-6), None)
        if nxt is None:
            raise RibError("the sketch's curves make more than one chain; a rib needs one")
        a, b = ends[nxt]
        tip = b if np.linalg.norm(tip - a) < 1e-6 else a
        order.append(nxt)
        left.discard(nxt)
    w = BRepBuilderAPI_MakeWire()
    for i in order:
        w.Add(edges[i])
    if not w.IsDone():
        raise RibError("could not join the sketch's curves into one line")
    return w.Wire()


def _ends(wire):
    """(start point, outward tangent at start, end point, outward tangent at end) of an open wire."""
    from OCP.BRepAdaptor import BRepAdaptor_CompCurve
    from OCP.gp import gp_Pnt, gp_Vec

    c = BRepAdaptor_CompCurve(wire)
    out = []
    for u, sign in ((c.FirstParameter(), -1), (c.LastParameter(), 1)):
        p, v = gp_Pnt(), gp_Vec()
        c.D1(u, p, v)
        t = _arr(v)
        n = np.linalg.norm(t)
        if n < 1e-12:
            raise RibError("the curve has no direction at one end")
        out += [_arr(p), sign * t / n]
    if np.linalg.norm(out[0] - out[2]) < 1e-7:
        raise RibError("the curve is closed; a rib is drawn with an open line")
    return out


def _edge(a, b):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge

    return BRepBuilderAPI_MakeEdge(_pnt(a), _pnt(b)).Edge()


def _centroid(shape) -> np.ndarray:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    g = GProp_GProps()
    _api(BRepGProp, "VolumeProperties")(shape, g)
    return _arr(g.CentreOfMass())


def _distance(a, b) -> float:
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    d = BRepExtrema_DistShapeShape(a, b)
    return d.Value() if d.IsDone() else math.inf


def rib_solid(wire, normal, t: float, body, flip: bool = False):
    """The rib for ``wire`` (in the sketch plane with ``normal``), filling towards ``body``."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire, BRepBuilderAPI_Transform
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Trsf
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    from . import robust

    if t <= 0:
        raise RibError("the thickness must be more than 0")
    n = np.asarray(normal, float)
    n /= np.linalg.norm(n)
    a, ta, b, tb = _ends(wire)
    size = robust.diagonal(body) + float(np.linalg.norm(b - a))
    far = 4 * size
    chord = b - a
    d = np.cross(n, chord)
    d /= np.linalg.norm(d)
    mid = (a + b) / 2
    if (_centroid(body) - mid) @ d < 0:
        d = -d
    if flip:
        d = -d
    w = BRepBuilderAPI_MakeWire()
    w.Add(_edge(a + far * ta, a))
    w.Add(wire)
    w.Add(_edge(b, b + far * tb))
    if not w.IsDone():
        raise RibError("could not carry the curve's ends on")
    sheet = BRepPrimAPI_MakePrism(w.Wire(), _vec(d * far))
    sheet.Build()
    tr = gp_Trsf()
    tr.SetTranslation(_vec(-n * t / 2))
    face = BRepBuilderAPI_Transform(sheet.Shape(), tr, True).Shape()
    slab = BRepPrimAPI_MakePrism(face, _vec(n * t))
    slab.Build()
    cut = BRepAlgoAPI_Cut(slab.Shape(), body)
    cut.Build()
    if not cut.IsDone():
        raise RibError("the kernel could not fit the rib to the part")
    keep = []
    ex = TopExp_Explorer(cut.Shape(), TopAbs_SOLID)
    while ex.More():
        s = ex.Current()
        if _distance(s, wire) < max(t, 1e-6) * 0.6:
            keep.append(s)
        ex.Next()
    if not keep:
        raise RibError("the curve lies inside the part; draw it where the rib's top edge should be")
    for s in keep:
        if robust.diagonal(s) > 1.5 * size:
            raise RibError("on that side the rib meets no part face (it would run on for ever); "
                           "move the curve, carry it to the walls, or flip the side")
    return keep[0] if len(keep) == 1 else _compound(keep)


def _compound(shapes):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    c = TopoDS_Compound()
    bb = BRep_Builder()
    bb.MakeCompound(c)
    for s in shapes:
        bb.Add(c, s)
    return c


# ---- lips and grooves -------------------------------------------------------------------
def _plane_of(face):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType
    from OCP.TopAbs import TopAbs_REVERSED

    s = BRepAdaptor_Surface(face)
    if s.GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
        raise RibError("the face is not flat; a lip runs along a flat rim")
    pl = s.Plane()
    d = pl.Axis().Direction()
    n = np.array([d.X(), d.Y(), d.Z()])
    if face.Orientation() == TopAbs_REVERSED:
        n = -n
    return pl, n  # n points out of the solid


def band(face, w: float):
    """The strip of a flat face within ``w`` of its inside edge: its holes' edges, or, for a face
    without holes, its outline."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset
    from OCP.BRepTools import BRepTools
    from OCP.GeomAbs import GeomAbs_JoinType
    from OCP.TopAbs import TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    pl, _ = _plane_of(face)
    outer = _api(BRepTools, "OuterWire")(face)
    holes = []
    ex = TopExp_Explorer(face, TopAbs_WIRE)
    while ex.More():
        wr = _api(TopoDS, "Wire")(ex.Current())
        if not wr.IsSame(outer):
            holes.append(wr)
        ex.Next()
    if holes:
        result = None
        for h in holes:
            opening = BRepBuilderAPI_MakeFace(pl, h, True).Face()
            off = BRepOffsetAPI_MakeOffset(opening, GeomAbs_JoinType.GeomAbs_Arc)
            off.Perform(w)
            if not off.IsDone():
                raise RibError("could not offset the rim's inside edge")
            grown = BRepBuilderAPI_MakeFace(pl, _api(TopoDS, "Wire")(off.Shape()), True).Face()
            piece = BRepAlgoAPI_Common(grown, face).Shape()
            result = piece if result is None else _compound([result, piece])
        return result
    whole = BRepBuilderAPI_MakeFace(pl, outer, True).Face()
    off = BRepOffsetAPI_MakeOffset(whole, GeomAbs_JoinType.GeomAbs_Arc)
    off.Perform(-w)
    if not off.IsDone():
        raise RibError("the band is wider than the face")
    inner = BRepBuilderAPI_MakeFace(pl, _api(TopoDS, "Wire")(off.Shape()), True).Face()
    return BRepAlgoAPI_Cut(face, inner).Shape()


def lip_solid(face, h: float, w: float):
    """A band along the inside edge pushed ``h`` out of the face (h < 0: into the part)."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    if w <= 0 or h == 0:
        raise RibError("the width must be more than 0 and the height not 0")
    _, n = _plane_of(face)
    strip = band(face, w)
    solids = []
    ex = TopExp_Explorer(strip, TopAbs_FACE)
    while ex.More():
        pr = BRepPrimAPI_MakePrism(ex.Current(), _vec(n * h))
        pr.Build()
        solids.append(pr.Shape())
        ex.Next()
    if not solids:
        raise RibError("the band is empty: is the width more than the rim?")
    return solids[0] if len(solids) == 1 else _compound(solids)


# ---- wrapping onto a cylinder -----------------------------------------------------------
def cylinder_of(face):
    """The cylinder or cone a face lies on: a gp_Cylinder or a gp_Cone."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType

    s = BRepAdaptor_Surface(face)
    if s.GetType() == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        return s.Cylinder()
    if s.GetType() == GeomAbs_SurfaceType.GeomAbs_Cone:
        return s.Cone()
    raise RibError("the face is not part of a cylinder or a cone")


def radius_at(surf, t: float) -> float:
    """The radius of a gp_Cylinder or gp_Cone at axial distance ``t`` from its location."""
    if hasattr(surf, "SemiAngle"):
        return surf.RefRadius() + t * math.tan(surf.SemiAngle())
    return surf.Radius()


def wrap_faces(faces: list, frame, cyl, samples: int = 40) -> list:
    """Each planar sketch face laid on ``cyl``, a gp_Cylinder or a gp_Cone: the sketch plane must be
    parallel to the axis. Its direction across the axis becomes arc length round the surface,
    measured from the line of the sketch plane nearest the axis, which lands on the surface
    where the plane faces it.

    On a cone the sketch is laid on the cone's flat development (the sector it unrolls to), so
    shapes keep their sizes and angles: the sketch's direction along the axis becomes distance
    down the cone's slope, and lines become curves on the cone."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.BRepLib import BRepLib
    from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
    from OCP.Geom import Geom_ConicalSurface, Geom_CylindricalSurface
    from OCP.Geom2d import Geom2d_Line
    from OCP.Geom2dAPI import Geom2dAPI_Interpolate
    from OCP.GeomAbs import GeomAbs_CurveType
    from OCP.gp import gp_Dir2d, gp_Pnt2d
    from OCP.ShapeFix import ShapeFix_Face
    try:  # OCP 8 renamed the array classes
        from OCP.collections import HArray1_gp_Pnt2d as TColgp_HArray1OfPnt2d
    except ImportError:
        from OCP.TColgp import TColgp_HArray1OfPnt2d
    from OCP.TopAbs import TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    ax = cyl.Position()
    o = _arr(ax.Location())
    a = _arr(ax.Direction())
    xd = _arr(ax.XDirection())
    yd = _arr(ax.YDirection())
    cone = hasattr(cyl, "SemiAngle")
    R = cyl.RefRadius() if cone else cyl.Radius()
    nz = np.asarray(frame.z, float)
    if abs(nz @ a) > 1e-6:
        raise RibError("the sketch plane must be parallel to the cylinder's axis")
    fo = np.asarray(frame.origin, float)
    side = (fo - o) @ nz  # the sketch plane's distance from the axis, along its normal
    radial = nz * (1.0 if side >= 0 else -1.0)  # towards the plane: where it faces the cylinder
    th0 = math.atan2(radial @ yd, radial @ xd)
    e = np.cross(a, radial)  # round the cylinder, in the sketch plane's direction

    if cone:
        k = math.sin(cyl.SemiAngle())
        if abs(k) < 1e-9:
            raise RibError("the cone is a cylinder")

        def uv(p):
            sv, vz = (p - o) @ e, (p - o) @ a
            d0 = (R + vz * k) / abs(k)  # distance from the apex down the slope, where the plane faces it
            if d0 <= 0:
                raise RibError("the sketch reaches past the cone's tip")
            d = math.hypot(sv, d0)
            return th0 + math.atan2(sv, d0) / abs(k), (d * abs(k) - R) / k

        surf = Geom_ConicalSurface(ax, cyl.SemiAngle(), R)
    else:
        def uv(p):
            return th0 + ((p - o) @ e) / R, (p - o) @ a

        surf = Geom_CylindricalSurface(ax, R)
    out = []
    for f in faces:
        outer = _api(BRepTools, "OuterWire")(f)
        wires = [outer]
        ex = TopExp_Explorer(f, TopAbs_WIRE)
        while ex.More():
            wr = _api(TopoDS, "Wire")(ex.Current())
            if not wr.IsSame(outer):
                wires.append(wr)
            ex.Next()
        made = []
        for wr in wires:
            mk = BRepBuilderAPI_MakeWire()
            we = BRepTools_WireExplorer(wr, f)
            while we.More():
                c = BRepAdaptor_Curve(we.Current())
                u0, u1 = c.FirstParameter(), c.LastParameter()
                rev = we.Current().Orientation() == 1  # TopAbs_REVERSED
                if c.GetType() == GeomAbs_CurveType.GeomAbs_Line and not cone:
                    p0, p1 = _arr(c.Value(u0)), _arr(c.Value(u1))
                    if rev:
                        p0, p1 = p1, p0
                    q0, q1 = uv(p0), uv(p1)
                    dv = np.subtract(q1, q0)
                    ln = float(np.linalg.norm(dv))
                    line = Geom2d_Line(gp_Pnt2d(*q0), gp_Dir2d(*(dv / ln)))
                    edge = BRepBuilderAPI_MakeEdge(line, surf, 0.0, ln).Edge()
                else:
                    us = np.linspace(u0, u1, samples + 1)
                    if rev:
                        us = us[::-1]
                    pts = [uv(_arr(c.Value(float(u)))) for u in us]
                    # a closed curve goes on in two halves: one periodic edge on the cylinder makes a
                    # face that is a little too big
                    halves = [pts[: samples // 2 + 1], pts[samples // 2:]] if (
                        np.linalg.norm(np.subtract(pts[0], pts[-1])) < 1e-9) else [pts]
                    for part in halves:
                        arr = TColgp_HArray1OfPnt2d(1, len(part))
                        for i, q in enumerate(part, 1):
                            arr.SetValue(i, gp_Pnt2d(*q))
                        ip = Geom2dAPI_Interpolate(arr, False, 1e-9)
                        ip.Perform()
                        if not ip.IsDone():
                            raise RibError("could not lay a curve of the sketch onto the cylinder")
                        mk.Add(BRepBuilderAPI_MakeEdge(ip.Curve(), surf).Edge())
                    we.Next()
                    continue
                mk.Add(edge)
                we.Next()
            if not mk.IsDone():
                raise RibError("could not join a wrapped loop")
            wire = mk.Wire()
            _api(BRepLib, "BuildCurves3d")(wire)
            made.append(wire)
        fm = BRepBuilderAPI_MakeFace(surf, made[0], True)
        for h in made[1:]:
            fm.Add(h)
        if not fm.IsDone():
            raise RibError("could not make a wrapped face")
        fix = ShapeFix_Face(fm.Face())
        fix.FixOrientation()
        fix.Perform()
        out.append(fix.Face())
    return out, R


def wrap_solid(face, h: float):
    """A wrapped face thickened ``h`` outwards (negative: inwards) into a solid."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid

    mk = BRepOffsetAPI_MakeThickSolid()
    mk.MakeThickSolidBySimple(face, float(h))
    mk.Build()
    if not mk.IsDone():
        raise RibError("could not thicken the wrapped sketch")
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    shape = mk.Shape()
    g = GProp_GProps()
    _api(BRepGProp, "VolumeProperties")(shape, g)
    return shape.Reversed() if g.Mass() < 0 else shape  # a face wound the other way comes out inside out
