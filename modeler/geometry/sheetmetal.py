"""Sheet metal: a plate of one thickness, flanges bent up or down along its edges, and the
flat pattern (the plate as it is cut from the sheet before bending).

Coordinates: a sheet is made in a plane (origin, x, y, normal n). The plate
fills 0 <= height <= t above that plane. A flange is bent along a straight
edge of the plate: from an edge on the top face it goes up (towards n), from
an edge on the bottom face it goes down. The bend starts at the edge, its
inside radius is r, and a flat wall of the given length follows it, so the
part grows beyond the edge (by r + t + length for a 90 degree flange).

The flat pattern unrolls each bend: the bend takes ``angle * (r + k * t)``
of flat length (the bend allowance: the length of the neutral line, which
sits ``k * t`` from the inside face; ``k`` is the K-factor, 0.44 by default)
and the wall its own length. The plate's bottom face, with any holes cut
through it, is the middle of the pattern.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

K_FACTOR = 0.44


class SheetError(Exception):
    pass


@dataclass(frozen=True)
class Flange:
    a: tuple  # the bend edge on the base plane (bottom), start and end
    b: tuple
    out: tuple  # unit vector in the base plane, away from the plate
    up: bool
    angle: float  # degrees
    length: float
    radius: float


@dataclass(frozen=True)
class Sheet:
    origin: tuple
    x: tuple
    y: tuple
    n: tuple
    t: float
    r: float
    k: float = K_FACTOR
    flanges: tuple = field(default_factory=tuple)

    def allowance(self, angle: float, radius: float) -> float:
        return math.radians(angle) * (radius + self.k * self.t)

    def local(self, p) -> np.ndarray:
        d = np.asarray(p, float) - np.asarray(self.origin, float)
        return np.array([d @ np.asarray(self.x), d @ np.asarray(self.y), d @ np.asarray(self.n)])

    def world(self, u: float, v: float, h: float = 0.0) -> tuple:
        o, x, y, n = (np.asarray(a, float) for a in (self.origin, self.x, self.y, self.n))
        return tuple(o + u * x + v * y + h * n)


def _pnt(q):
    from OCP.gp import gp_Pnt

    return gp_Pnt(*map(float, q))


def _vec(q):
    from OCP.gp import gp_Vec

    return gp_Vec(*map(float, q))


def flange_solid(sh: Sheet, a, b, up: bool, angle: float, length: float, radius: float):
    """The bend and wall of one flange, as a solid to join to the plate. ``a``-``b`` is the edge on
    the face it starts from (the top face for up, the bottom face for down)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.GC import GC_MakeArcOfCircle

    if not 0 < angle <= 180:
        raise SheetError("the bend angle is more than 0 and at most 180 degrees")
    if length < 0 or radius < 0:
        raise SheetError("the length and the radius cannot be negative")
    a, b = np.asarray(a, float), np.asarray(b, float)
    along = b - a
    if np.linalg.norm(along) < 1e-9:
        raise SheetError("the edge has no length")
    n = np.asarray(sh.n, float) * (1 if up else -1)
    out = _outward(sh, a, b)
    t, r = sh.t, radius
    th = math.radians(angle)

    def P(u, v):  # local (u along out, v along n) at the edge start
        return a + u * out + v * n

    c = np.array([0.0, r])
    def arc_pt(rad, phi):
        return c + rad * np.array([math.cos(phi), math.sin(phi)])

    p0, q0 = -math.pi / 2, -math.pi / 2 + th
    in0, in1 = arc_pt(r, p0), arc_pt(r, q0)
    out0, out1 = arc_pt(r + t, p0), arc_pt(r + t, q0)
    d = np.array([-math.sin(q0), math.cos(q0)])  # along the wall
    in2, out2 = in1 + length * d, out1 + length * d
    edges = []
    if r > 1e-12:
        mid = arc_pt(r, (p0 + q0) / 2)
        edges.append(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(_pnt(P(*in0)), _pnt(P(*mid)),
                                                                _pnt(P(*in1))).Value()).Edge())
    mid = arc_pt(r + t, (p0 + q0) / 2)
    pts = [in1, in2, out2, out1] if length > 1e-12 else [in1, out1]
    for s, e in zip(pts, pts[1:]):
        edges.append(BRepBuilderAPI_MakeEdge(_pnt(P(*s)), _pnt(P(*e))).Edge())
    edges.append(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(_pnt(P(*out1)), _pnt(P(*mid)),
                                                            _pnt(P(*out0))).Value()).Edge())
    edges.append(BRepBuilderAPI_MakeEdge(_pnt(P(*out0)), _pnt(P(*in0))).Edge())
    wire = BRepBuilderAPI_MakeWire()
    for e in edges:
        wire.Add(e)
    if not wire.IsDone():
        raise SheetError("could not draw the bend's section")
    face = BRepBuilderAPI_MakeFace(wire.Wire(), True).Face()
    prism = BRepPrimAPI_MakePrism(face, _vec(along))
    prism.Build()
    return prism.Shape()


def _outward(sh: Sheet, a, b) -> np.ndarray:
    """In-plane unit vector square to the edge, pointing away from the plate's middle
    (worked out by the caller's plate; here: from the edge towards nowhere in particular)."""
    along = (np.asarray(b, float) - np.asarray(a, float))
    along /= np.linalg.norm(along)
    out = np.cross(along, np.asarray(sh.n, float))
    return out / np.linalg.norm(out)


def edge_side(sh: Sheet, a, b, plate_centre) -> tuple[tuple, tuple, bool]:
    """Order the edge so that _outward points away from the plate, and say whether it lies on
    the top face (True) or the bottom face (False)."""
    la, lb = sh.local(a), sh.local(b)
    if abs(la[2] - lb[2]) > 1e-6 * max(1.0, sh.t) + 1e-7:
        raise SheetError("the edge is not flat in the sheet's plane: pick an edge of the top or bottom face")
    h = la[2]
    if abs(h - sh.t) < 1e-6 * max(1.0, sh.t) + 1e-7:
        top = True
    elif abs(h) < 1e-6 * max(1.0, sh.t) + 1e-7:
        top = False
    else:
        raise SheetError("the edge is not on the plate's top or bottom face")
    out = _outward(sh, a, b)
    mid = (np.asarray(a, float) + np.asarray(b, float)) / 2
    if (np.asarray(plate_centre, float) - mid) @ out > 0:
        a, b = b, a
    return tuple(a), tuple(b), top


# ---- the flat pattern ---------------------------------------------------------------------
@dataclass
class Flat:
    face: object  # the flat outline as one face in the base plane
    bends: list  # [(p, q, text)] bend centre lines, world points in the base plane
    size: tuple  # (width, height) of its box in the sheet's x, y


def flat_pattern(sh: Sheet, body_shape) -> Flat:
    """The base plate's bottom face (with whatever holes it has) and a strip for each flange."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

    base = _bottom_faces(sh, body_shape)
    if not base:
        raise SheetError("the plate's bottom face is gone (was the body cut through its base?)")
    shape = base[0]
    for f in base[1:]:
        shape = BRepAlgoAPI_Fuse(shape, f).Shape()
    bends = []
    for fl in sh.flanges:
        a, b = np.asarray(fl.a, float), np.asarray(fl.b, float)
        out = np.asarray(fl.out, float)
        ba = sh.allowance(fl.angle, fl.radius)
        wall = _wall_faces(sh, fl, body_shape, ba) if fl.length > 1e-9 else []
        depth = ba if wall else ba + fl.length  # the wall as it really is (with its holes), else a strip
        if depth > 1e-9:
            poly = BRepBuilderAPI_MakePolygon(_pnt(a), _pnt(b), _pnt(b + depth * out), _pnt(a + depth * out), True)
            strip = BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()
            shape = BRepAlgoAPI_Fuse(shape, strip).Shape()
        for wf in wall:
            shape = BRepAlgoAPI_Fuse(shape, wf).Shape()
        word = "UP" if fl.up else "DOWN"
        bends.append((tuple(a + ba / 2 * out), tuple(b + ba / 2 * out),
                      f"{word} {fl.angle:g}° R{fl.radius:g}"))
    u = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
    u.Build()
    shape = u.Shape()
    lo, hi = _box(sh, shape)
    return Flat(shape, bends, (hi[0] - lo[0], hi[1] - lo[1]))


def _wall_faces(sh: Sheet, fl: Flange, shape, ba: float) -> list:
    """A flange wall's faces on the sheet's bottom side, laid flat where the wall goes in the
    flat pattern: so holes and cuts made in the wall after bending show in the blank."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepGProp import BRepGProp
    from OCP.GeomAbs import GeomAbs_SurfaceType
    from OCP.GProp import GProp_GProps
    from OCP.gp import gp_Ax3, gp_Dir, gp_Trsf
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
    surface_props = getattr(BRepGProp, "SurfaceProperties_s", None) or BRepGProp.SurfaceProperties
    n = np.asarray(sh.n, float)
    a = np.asarray(fl.a, float)
    b = np.asarray(fl.b, float)
    out = np.asarray(fl.out, float)
    span = float(np.linalg.norm(b - a))
    al = (b - a) / span
    t, r = sh.t, fl.radius
    if fl.up:  # the bottom side is the outside of an up bend
        edge0, nn, rad = a + t * n, n, r + t
    else:
        edge0, nn, rad = a, -n, r
    q0 = -math.pi / 2 + math.radians(fl.angle)
    w0 = edge0 + (rad * math.cos(q0)) * out + (r + rad * math.sin(q0)) * nn
    d3 = -math.sin(q0) * out + math.cos(q0) * nn
    nw = np.cross(d3, al)
    tol = 1e-6 * max(1.0, t) + 1e-7
    found = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        f = as_face(ex.Current())
        ex.Next()
        s = BRepAdaptor_Surface(f)
        if s.GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
            continue
        pl = s.Plane()
        d = pl.Axis().Direction()
        if abs(abs(np.array([d.X(), d.Y(), d.Z()]) @ nw) - 1) > 1e-7:
            continue
        loc = pl.Location()
        if abs((np.array([loc.X(), loc.Y(), loc.Z()]) - w0) @ nw) > tol:
            continue
        g = GProp_GProps()
        surface_props(f, g)
        c = g.CentreOfMass()
        c = np.array([c.X(), c.Y(), c.Z()])
        e, w = (c - edge0) @ al, (c - w0) @ d3
        if -tol <= e <= span + tol and -tol <= w <= fl.length + tol:
            found.append(f)
    if not found:
        return []
    tr = gp_Trsf()
    tr.SetDisplacement(gp_Ax3(_pnt(w0), gp_Dir(*np.cross(d3, al)), gp_Dir(*d3)),
                       gp_Ax3(_pnt(a + ba * out), gp_Dir(*np.cross(out, al)), gp_Dir(*out)))
    return [BRepBuilderAPI_Transform(f, tr, True).Shape() for f in found]


def _bottom_faces(sh: Sheet, shape) -> list:
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
    out = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    n = np.asarray(sh.n, float)
    while ex.More():
        f = as_face(ex.Current())
        s = BRepAdaptor_Surface(f)
        if s.GetType() == GeomAbs_SurfaceType.GeomAbs_Plane:
            pl = s.Plane()
            d = pl.Axis().Direction()
            dn = np.array([d.X(), d.Y(), d.Z()])
            loc = pl.Location()
            h = sh.local((loc.X(), loc.Y(), loc.Z()))[2]
            if abs(abs(dn @ n) - 1) < 1e-7 and abs(h) < 1e-6 * max(1.0, sh.t) + 1e-7:
                out.append(f)
        ex.Next()
    return out


def _box(sh: Sheet, shape):
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    as_v = getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex
    pnt = getattr(BRep_Tool, "Pnt_s", None) or BRep_Tool.Pnt
    pts = []
    ex = TopExp_Explorer(shape, TopAbs_VERTEX)
    while ex.More():
        q = pnt(as_v(ex.Current()))
        pts.append(sh.local((q.X(), q.Y(), q.Z()))[:2])
        ex.Next()
    if not pts:
        return (0.0, 0.0), (0.0, 0.0)
    a = np.array(pts)
    return tuple(a.min(axis=0)), tuple(a.max(axis=0))


def outline_2d(sh: Sheet, face, deflection: float) -> list[list[tuple]]:
    """Every edge of the flat face as 2D polylines in the sheet's x, y (arcs as short lines)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.GeomAbs import GeomAbs_CurveType
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    as_e = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    out = []
    ex = TopExp_Explorer(face, TopAbs_EDGE)
    while ex.More():
        c = BRepAdaptor_Curve(as_e(ex.Current()))
        if c.GetType() == GeomAbs_CurveType.GeomAbs_Line:
            ps = [c.Value(c.FirstParameter()), c.Value(c.LastParameter())]
        else:
            d = GCPnts_QuasiUniformDeflection(c, deflection)
            ps = [d.Value(i) for i in range(1, d.NbPoints() + 1)] if d.IsDone() else []
        if len(ps) >= 2:
            out.append([tuple(sh.local((q.X(), q.Y(), q.Z()))[:2]) for q in ps])
        ex.Next()
    return out


def dxf(sh: Sheet, flat: Flat, deflection: float, units: str = "MM") -> str:
    """An ASCII DXF of the flat pattern: layer OUTLINE (cut), BEND (dashed centre lines) and TEXT."""
    lines = outline_2d(sh, flat.face, deflection)
    bends = [(sh.local(p)[:2], sh.local(q)[:2], text) for p, q, text in flat.bends]
    L: list[str] = []

    def g(code, value):
        L.append(str(code))
        L.append(str(value))

    def f(v):
        return f"{float(v):.6f}".rstrip("0").rstrip(".")

    ins = {"MM": 4, "CM": 5, "M": 6, "IN": 1}.get(units.upper(), 0)
    allp = [q for pl in lines for q in pl] or [(0, 0)]
    x0, y0 = min(q[0] for q in allp), min(q[1] for q in allp)
    x1, y1 = max(q[0] for q in allp), max(q[1] for q in allp)
    g(0, "SECTION"); g(2, "HEADER")
    g(9, "$ACADVER"); g(1, "AC1009")
    g(9, "$INSUNITS"); g(70, ins)
    g(9, "$EXTMIN"); g(10, f(x0)); g(20, f(y0))
    g(9, "$EXTMAX"); g(10, f(x1)); g(20, f(y1))
    g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "TABLES")
    dash = max(x1 - x0, y1 - y0, 1e-6) / 80
    g(0, "TABLE"); g(2, "LTYPE"); g(70, 2)
    g(0, "LTYPE"); g(2, "CONTINUOUS"); g(70, 0); g(3, "Solid line"); g(72, 65); g(73, 0); g(40, 0.0)
    g(0, "LTYPE"); g(2, "CENTER"); g(70, 0); g(3, "Centre ____ _ ____"); g(72, 65); g(73, 4)
    g(40, f(dash * 3.5)); g(49, f(dash * 2)); g(49, f(-dash * 0.5)); g(49, f(dash * 0.5)); g(49, f(-dash * 0.5))
    g(0, "ENDTAB")
    g(0, "TABLE"); g(2, "LAYER"); g(70, 3)
    for name, colour, lt in (("OUTLINE", 7, "CONTINUOUS"), ("BEND", 1, "CENTER"), ("TEXT", 3, "CONTINUOUS")):
        g(0, "LAYER"); g(2, name); g(70, 0); g(62, colour); g(6, lt)
    g(0, "ENDTAB")
    g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "ENTITIES")
    for pl in lines:
        for (a, b), (c, d) in zip(pl, pl[1:]):
            g(0, "LINE"); g(8, "OUTLINE"); g(10, f(a)); g(20, f(b)); g(30, 0); g(11, f(c)); g(21, f(d)); g(31, 0)
    hgt = max(x1 - x0, y1 - y0, 1e-6) / 70
    for p, q, text in bends:
        g(0, "LINE"); g(8, "BEND"); g(10, f(p[0])); g(20, f(p[1])); g(30, 0); g(11, f(q[0])); g(21, f(q[1])); g(31, 0)
        mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
        # R12 text is plain ANSI: the degree sign is written %%d, which every reader shows as °
        g(0, "TEXT"); g(8, "TEXT"); g(10, f(mx)); g(20, f(my + hgt * 0.6)); g(30, 0); g(40, f(hgt))
        g(1, text.replace("°", "%%d"))
    g(0, "ENDSEC")
    g(0, "EOF")
    return "\n".join(L) + "\n"
