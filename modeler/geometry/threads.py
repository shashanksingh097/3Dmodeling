"""Screw threads and springs.

A thread is cut, never added: a groove with the ISO metric profile (60 degree
flanks) is swept along an exact helix and subtracted from the body. Outside a
shaft the groove runs from just outside the major diameter down to the minor
diameter; inside a hole it runs from just inside the hole wall out to the major
diameter. The same tool shape serves both, so one code path cuts both.

Two things make the booleans reliable (both found by trying):

* the helix is built exactly, as a straight line on a cylinder, not as a
  fitted spline;
* it is split into half turns. A single swept face that wraps round the axis
  many times defeats the boolean (it reports success and removes almost
  nothing); half-turn faces cut cleanly and quickly.

The groove is swept in binormal mode with the thread axis as the fixed
direction, so the profile drawn in a plane through the axis turns rigidly with
the helix: every point of it follows its own helix, which is the exact screw
surface.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakePolygon,
    BRepBuilderAPI_MakeWire,
)
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepLib import BRepLib
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
from OCP.Geom import Geom_CylindricalSurface
from OCP.Geom2d import Geom2d_Line
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.gp import gp_Ax3, gp_Dir, gp_Dir2d, gp_Pnt, gp_Pnt2d, gp_Vec
from OCP.TopAbs import TopAbs_IN, TopAbs_REVERSED
from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Wire

from . import curves as cv
from . import robust

_as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
_build3d = getattr(BRepLib, "BuildCurves3d_s", None) or BRepLib.BuildCurves3d

Point = tuple[float, float, float]

# ISO 261 / ISO 724 coarse pitches, nominal diameter -> pitch
ISO_COARSE = {
    1: 0.25, 1.2: 0.25, 1.4: 0.3, 1.6: 0.35, 2: 0.4, 2.5: 0.45, 3: 0.5, 3.5: 0.6, 4: 0.7, 5: 0.8, 6: 1.0,
    7: 1.0, 8: 1.25, 10: 1.5, 12: 1.75, 14: 2.0, 16: 2.0, 18: 2.5, 20: 2.5, 22: 2.5, 24: 3.0, 27: 3.0,
    30: 3.5, 33: 3.5, 36: 4.0, 39: 4.0, 42: 4.5, 45: 4.5, 48: 5.0, 52: 5.0, 56: 5.5, 60: 5.5, 64: 6.0,
}
# ISO 68-1 basic profile, as multiples of the pitch
H = math.sqrt(3) / 2  # height of the sharp V
EXT_DEPTH = 5 * H / 8  # external thread depth, major to minor (0.5413)
INT_DEPTH = 5 * H / 8  # internal thread depth, minor D1 to major D (0.5413)
ROOT_EXT = 17 * H / 24  # external root depth with the rounded root (0.6134, ISO h3)
TAN30 = math.tan(math.radians(30))
OVERSHOOT = 0.05  # the groove reaches this many pitches past the surface it cuts
MAX_TURNS = 400


class ThreadError(Exception):
    pass


def _fmt(v: float) -> str:
    return f"{v:.4g}"


def designation(d: float, pitch: float) -> str:
    """'M8' for an ISO coarse size, 'M8x1' for any other pitch."""
    c = coarse_for_shaft(d)
    if c is not None and abs(c[0] - d) < 1e-6 and abs(c[1] - pitch) < 1e-9:
        return f"M{_fmt(d)}"
    return f"M{_fmt(d)}x{_fmt(pitch)}"


def coarse_for_shaft(d: float) -> tuple[float, float] | None:
    """(nominal, pitch) of the ISO coarse size whose major diameter is d."""
    for k, p in ISO_COARSE.items():
        if abs(k - d) <= max(0.01, 0.005 * k):
            return float(k), p
    return None


def coarse_for_hole(d_hole: float) -> tuple[float, float] | None:
    """(nominal, pitch) of the ISO coarse size a hole of this diameter is drilled for.

    A hole fits a size when its diameter is between the minor diameter D1 and
    the usual tap drill (nominal minus pitch), give or take a tenth of a pitch.
    """
    for k, p in ISO_COARSE.items():
        d1 = k - 2 * INT_DEPTH * p
        if d1 - 0.1 * p <= d_hole <= k - p + 0.1 * p:
            return float(k), p
    return None


# ---- the round face to thread --------------------------------------------------
@dataclass
class RoundFace:
    centre: Point  # a point on the axis, at the start of the face
    axis: Point  # unit vector from that point along the face
    radius: float
    length: float
    outside: bool  # True for a shaft (material inside the face), False for a hole


def round_face(face: TopoDS_Shape) -> RoundFace:
    f = _as_face(face)
    s = BRepAdaptor_Surface(f)
    if s.GetType() != GeomAbs_SurfaceType.GeomAbs_Cylinder:
        raise ThreadError("pick a cylindrical face: the side of a shaft, or the wall of a hole")
    cyl = s.Cylinder()
    ax = cyl.Axis()
    loc, d = ax.Location(), ax.Direction()
    v0, v1 = s.FirstVParameter(), s.LastVParameter()
    u0, u1 = s.FirstUParameter(), s.LastUParameter()
    if u1 - u0 < 2 * math.pi - 1e-6:
        raise ThreadError("the face is only part of a cylinder; a thread needs the whole way round")
    # which side the material is on: the face normal points out of it
    pnt, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
    s.D1(0.5 * (u0 + u1), 0.5 * (v0 + v1), pnt, du, dv)
    normal = du.Crossed(dv)
    if f.Orientation() == TopAbs_REVERSED:
        normal.Reverse()
    axis_pt = gp_Pnt(loc.X() + d.X() * 0.5 * (v0 + v1), loc.Y() + d.Y() * 0.5 * (v0 + v1),
                     loc.Z() + d.Z() * 0.5 * (v0 + v1))
    radial = gp_Vec(axis_pt, pnt)
    outside = normal.Dot(radial) > 0
    start = (loc.X() + d.X() * v0, loc.Y() + d.Y() * v0, loc.Z() + d.Z() * v0)
    return RoundFace(start, (d.X(), d.Y(), d.Z()), cyl.Radius(), v1 - v0, outside)


def free_ends(body: TopoDS_Shape, rf: RoundFace, tol: float) -> tuple[bool, bool]:
    """Whether each end of the face is free: nothing of the body just beyond it.

    The test point sits a little past the end and a little off the face on
    its open side (just outside a shaft, just inside a hole). Past a free end,
    a chamfer or a countersink it is in air; past a shoulder, a head or the
    bottom of a blind hole it is in material.
    """
    r = rf.radius * (1.01 if rf.outside else 0.99)
    eps = max(0.01 * rf.radius, 10 * tol)
    x, _, _ = cv.plane_axes(rf.axis)
    result = []
    for along in (-eps, rf.length + eps):
        p = cv.add(rf.centre, cv.add(cv.mul(rf.axis, along), cv.mul(x, r)))
        cls = BRepClass3d_SolidClassifier(body, gp_Pnt(*p), tol)
        result.append(cls.State() != TopAbs_IN)
    return result[0], result[1]


# ---- tools ------------------------------------------------------------------
def helix_wire(origin: Point, axis: Point, xdir: Point, r: float, pitch: float, turns: float,
               left: bool = False, per_turn: int = 2) -> TopoDS_Wire:
    """Exact helix (a line on a cylinder) starting at origin + r*xdir, split
    into 1/per_turn turn edges."""
    if turns <= 0 or r <= 0 or pitch <= 0:
        raise ThreadError("the helix needs a positive radius, pitch and number of turns")
    ax = gp_Ax3(gp_Pnt(*origin), gp_Dir(*axis), gp_Dir(*xdir))
    surf = Geom_CylindricalSurface(ax, r)
    line = Geom2d_Line(gp_Pnt2d(0, 0), gp_Dir2d(-2 * math.pi if left else 2 * math.pi, pitch))
    per = math.hypot(2 * math.pi, pitch)  # line length per turn
    n = max(1, math.ceil(turns * per_turn - 1e-9))
    mw = BRepBuilderAPI_MakeWire()
    for i in range(n):
        a = i / per_turn * per
        b = min(turns, (i + 1) / per_turn) * per
        e = BRepBuilderAPI_MakeEdge(line, surf, a, b).Edge()
        _build3d(e)
        mw.Add(e)
    if not mw.IsDone():
        raise ThreadError("could not build the helix")
    return mw.Wire()


def _polygon(points: list[Point]) -> TopoDS_Wire:
    poly = BRepBuilderAPI_MakePolygon()
    for q in points:
        poly.Add(gp_Pnt(*q))
    poly.Close()
    return poly.Wire()


def _sweep(profile: TopoDS_Wire, path: TopoDS_Wire, axis: Point, what: str) -> TopoDS_Shape:
    mk = BRepOffsetAPI_MakePipeShell(path)
    mk.SetMode(gp_Dir(*axis))  # binormal mode: the profile turns about the axis, rigidly
    mk.Add(profile, False, False)
    mk.Build()
    if not mk.IsDone():
        raise ThreadError(f"the kernel could not sweep the {what}")
    mk.MakeSolid()
    shape = mk.Shape()
    if robust.volume(shape) < 0:
        shape = shape.Reversed()
    if not robust.is_valid(shape):
        raise ThreadError(f"the swept {what} is not a valid solid")
    return shape


def groove_profile(major: float, pitch: float, outside: bool, inner_r: float) -> list[tuple[float, float]]:
    """The groove's section as (radius, axial offset) points, centred on 0.

    Outside: from OVERSHOOT past the major radius down to the minor radius
    (ISO h3 with the rounded root), crest flat P/8 left standing. Inside: from
    OVERSHOOT inside the hole wall (``inner_r``) out to the major radius, root
    flat P/8 at the major diameter.
    """
    rmaj = major / 2
    if outside:
        r_in, r_out = rmaj - ROOT_EXT * pitch, rmaj + OVERSHOOT * pitch
        w_maj = 7 / 8 * pitch  # the crest flat P/8 stays
    else:
        r_in, r_out = inner_r - OVERSHOOT * pitch, rmaj
        w_maj = pitch / 8  # the root flat at the major diameter

    def width(r):  # 60 degree flanks: the groove widens towards the outside of a shaft,
        return w_maj + (2 * (r - rmaj) * TAN30 if outside else 2 * (rmaj - r) * TAN30)  # towards the axis in a hole

    pts = [(r_out, -width(r_out) / 2), (r_out, width(r_out) / 2), (r_in, width(r_in) / 2), (r_in, -width(r_in) / 2)]
    if min(width(r_in), width(r_out)) <= 0 or max(width(r_in), width(r_out)) >= pitch:
        raise ThreadError("the thread profile does not fit this pitch")
    return pts


def groove_tool(origin: Point, axis: Point, major: float, pitch: float, start: float, end: float,
                outside: bool, inner_r: float, left: bool = False) -> TopoDS_Shape:
    """The groove as a solid, centred on axial positions ``start`` to ``end``
    (measured from ``origin`` along ``axis``)."""
    turns = (end - start) / pitch
    if turns <= 0:
        raise ThreadError("the thread is too short: give a length of at least one pitch")
    if turns > MAX_TURNS:
        raise ThreadError(f"{turns:.0f} turns is too many (at most {MAX_TURNS}); use a coarser pitch or a shorter length")
    x, _, _ = cv.plane_axes(axis)
    sec = groove_profile(major, pitch, outside, inner_r)
    o = cv.add(origin, cv.mul(axis, start))
    profile = _polygon([cv.add(o, cv.add(cv.mul(x, r), cv.mul(axis, z))) for r, z in sec])
    r_path = 0.5 * (sec[0][0] + sec[2][0])
    path = helix_wire(o, axis, x, r_path, pitch, turns, left)
    return _sweep(profile, path, axis, "thread groove")


def thread_span(rf: RoundFace, ends: tuple[bool, bool], pitch: float, length: float) -> tuple[Point, float, float, str]:
    """Where the groove runs, as (origin, axis, start, end) along a new axis
    that points from the free end into the face, plus a note for the user.

    The groove overshoots a free end by a pitch so the thread runs out of
    the part cleanly, and stops half a groove short of a closed end (a
    shoulder, a head, the bottom of a blind hole) so it never cuts into it.
    """
    free0, free1 = ends
    if not (free0 or free1):
        raise ThreadError("neither end of the face is free (both run into the body), so a thread cannot run out; "
                          "thread a face with an open end")
    full = length <= 0 or length >= rf.length - 1e-9
    half = 7 / 16 * pitch  # half the groove width at the surface
    if free0 and free1 and full:
        return rf.centre, rf.axis, -pitch, rf.length + pitch, "the whole length"
    # start at a free end; with both free, start at the upper end (highest z, then y, then x)
    if free0 and free1:
        top = (rf.axis[2], rf.axis[1], rf.axis[0])
        from_far = top > (0.0, 0.0, 0.0)
    else:
        from_far = free1
    if from_far:
        origin = cv.add(rf.centre, cv.mul(rf.axis, rf.length))
        axis = cv.mul(rf.axis, -1.0)
    else:
        origin, axis = rf.centre, rf.axis
    run = rf.length if full else length
    return origin, axis, -pitch, run - half, ("the whole length" if full else f"{_fmt(run)} from the free end")


# ---- springs ----------------------------------------------------------------
def spring(origin: Point, axis: Point, r: float, pitch: float, turns: float, wire_d: float, left: bool = False,
           closed_ends: float = 0.0, ground: bool = False) -> tuple[TopoDS_Shape, float]:
    """A coil spring: a round wire swept along a helix. Returns (solid, free height).

    ``closed_ends`` turns at each end are wound tight (pitch = wire diameter);
    ``ground`` grinds both ends flat, square to the axis, taking off half a wire.
    """
    if r <= 0 or pitch <= 0 or turns <= 0 or wire_d <= 0:
        raise ThreadError("radius, pitch, turns and wire diameter must all be positive")
    if wire_d >= 2 * r:
        raise ThreadError("the wire is thicker than the coil is wide: make the wire diameter less than 2 x radius")
    if pitch <= wire_d * 1.001 and closed_ends <= 0:
        raise ThreadError(f"pitch {_fmt(pitch)} does not clear the wire ({_fmt(wire_d)}); "
                          "the coils would run into each other")
    if closed_ends < 0 or 2 * closed_ends >= turns:
        raise ThreadError("closed end turns must be fewer than half the turns")
    axis = cv.unit(axis)
    x, y, _ = cv.plane_axes(axis)
    if closed_ends > 0:
        tight = wire_d * 1.02  # touching coils would make the solid touch itself
        if pitch <= tight:
            raise ThreadError(f"pitch {_fmt(pitch)} must be more than the wire diameter for the active coils")
        path, height = _spring_path(origin, axis, r, pitch, turns, closed_ends, tight, left)
    else:
        path = helix_wire(origin, axis, x, r, pitch, turns, left)
        height = pitch * turns
    # the wire's section: a circle square to the helix where it starts
    p0 = cv.add(origin, cv.mul(x, r))
    lead = pitch if closed_ends <= 0 else wire_d * 1.02
    tan = cv.unit(cv.add(cv.mul(y, (-1 if left else 1) * 2 * math.pi * r), cv.mul(axis, lead)))
    section = cv.circle(p0, wire_d / 2, tan)
    coil = _sweep(section, path, axis, "spring wire")
    if ground:
        coil = _grind(coil, origin, axis, wire_d / 2, height - wire_d / 2, r + wire_d)
        height -= wire_d
    return coil, height + wire_d


def _spring_path(origin, axis, r, pitch, turns, closed, tight, left) -> tuple[TopoDS_Wire, float]:
    """A helix whose pitch eases from ``tight`` at the ends to ``pitch`` in the
    middle (a smooth law, so the swept wire has no kinks)."""
    def law(t: float) -> float:
        k = turns * min(t, 1 - t)  # turns from the nearer end
        if k <= closed:
            w = 0.0
        elif k >= closed + 0.5:
            w = 1.0
        else:
            u = (k - closed) / 0.5
            w = u * u * (3 - 2 * u)
        return (tight + (pitch - tight) * w) / pitch

    wire = cv.helix(origin, axis, r, pitch, turns, left=left, pitch_law=law)
    n = 4000
    height = sum(pitch * law((i + 0.5) / n) * turns / n for i in range(n))
    return wire, height


def _grind(coil: TopoDS_Shape, origin, axis, z0: float, z1: float, r: float) -> TopoDS_Shape:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2

    base = cv.add(origin, cv.mul(axis, z0))
    slab = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*base), gp_Dir(*axis)), r * 1.5, z1 - z0).Shape()
    op = BRepAlgoAPI_Common(coil, slab)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        raise ThreadError("could not grind the spring ends flat")
    out = robust.unwrap(op.Shape())
    if not robust.is_valid(out):
        raise ThreadError("grinding the spring ends gave an invalid solid; try without GROUND")
    return out


def describe(major: float, pitch: float, outside: bool, left: bool) -> str:
    minor = major - 2 * (ROOT_EXT if outside else INT_DEPTH) * pitch
    hand = " left-hand" if left else ""
    return (f"{designation(major, pitch)}{hand} {'outside' if outside else 'inside'} thread "
            f"(pitch {_fmt(pitch)}, minor diameter {_fmt(minor)})")

