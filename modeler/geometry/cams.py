"""Cams (CAM): the lift law, the disc cam's outline for a roller follower, and the barrel cam's
groove.

A **lift law** is a list of pieces round the turn, written as words:
``R10/120`` rises 10 over 120 degrees, ``D60`` dwells 60 degrees, ``F10/120`` falls 10 over
120 degrees. A letter after a rise or fall picks the motion: ``C`` cycloidal (the default: no
jump in acceleration at the ends), ``H`` simple harmonic, ``P`` the 3-4-5 polynomial, ``V``
constant speed. The pieces add up to 360 degrees and the cam ends where it started.

A **disc cam** turns about its axis and pushes a roller follower that slides along a line
through the axis (+X when the cam is at 0). Turned by A degrees counterclockwise, the roller's
centre sits at base radius + roller radius + lift(A). The outline is the inner edge of the
roller's circles; the steepest **pressure angle** (between the push and the follower's line)
and the sharpest bend of the outline are checked.

A **barrel cam** is a cylinder with a groove round it; the follower slides along the axis by
the lift.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np


class CamError(ValueError):
    pass


@dataclass(frozen=True)
class Piece:
    kind: str  # R, F or D
    angle: float  # degrees
    lift: float = 0.0
    motion: str = "C"


_PIECE = re.compile(r"^([RFD])\s*([0-9.]+)?(?:\s*/\s*([0-9.]+))?\s*([CHPV])?$", re.IGNORECASE)


def parse(text: str) -> list[Piece]:
    pieces = []
    for word in re.split(r"[\s;]+", text.strip().strip('"')):
        if not word:
            continue
        m = _PIECE.match(word)
        if not m:
            raise CamError(f"{word!r} is not a piece of a lift law: R10/120 (rise 10 over 120°), D60 (dwell), "
                           "F10/120 (fall)")
        kind = m.group(1).upper()
        if kind == "D":
            if m.group(3) or not m.group(2):
                raise CamError(f"{word!r}: a dwell is D and its angle, like D60")
            pieces.append(Piece("D", float(m.group(2))))
        else:
            if not m.group(2) or not m.group(3):
                raise CamError(f"{word!r}: a rise or fall is its lift / its angle, like R10/120")
            pieces.append(Piece(kind, float(m.group(3)), float(m.group(2)), (m.group(4) or "C").upper()))
    if not pieces:
        raise CamError("the lift law is empty: write it like R10/120 D60 F10/120 D60")
    total = sum(p.angle for p in pieces)
    if abs(total - 360) > 1e-6:
        raise CamError(f"the pieces of the lift law add up to {total:g} degrees, not 360")
    if any(p.angle <= 0 for p in pieces):
        raise CamError("each piece of the lift law needs an angle above 0")
    net = sum(p.lift if p.kind == "R" else -p.lift if p.kind == "F" else 0.0 for p in pieces)
    if abs(net) > 1e-9:
        raise CamError(f"the cam would not end where it started: the rises and falls differ by {net:g}")
    level, low = 0.0, 0.0
    for p in pieces:
        level += p.lift if p.kind == "R" else -p.lift if p.kind == "F" else 0.0
        low = min(low, level)
    if low < -1e-9:
        raise CamError("the lift law falls below where it starts; start it at its lowest point")
    return pieces


def _shape(motion: str, u: float) -> tuple[float, float]:
    """The share of a rise done at u (0 to 1) and its rate."""
    if motion == "H":
        return (1 - math.cos(math.pi * u)) / 2, math.pi / 2 * math.sin(math.pi * u)
    if motion == "P":
        return 10 * u ** 3 - 15 * u ** 4 + 6 * u ** 5, 30 * u ** 2 - 60 * u ** 3 + 30 * u ** 4
    if motion == "V":
        return u, 1.0
    return u - math.sin(2 * math.pi * u) / (2 * math.pi), 1 - math.cos(2 * math.pi * u)


def lift(pieces: list[Piece], deg: float) -> tuple[float, float]:
    """The lift at an angle, and its rate (lift per radian)."""
    a = deg % 360.0
    level = 0.0
    for p in pieces:
        if a <= p.angle or p is pieces[-1]:
            if p.kind == "D":
                return level, 0.0
            u = min(max(a / p.angle, 0.0), 1.0)
            f, df = _shape(p.motion, u)
            sign = 1 if p.kind == "R" else -1
            return level + sign * p.lift * f, sign * p.lift * df / math.radians(p.angle)
        a -= p.angle
        level += p.lift if p.kind == "R" else -p.lift if p.kind == "F" else 0.0
    return level, 0.0


def stroke(pieces: list[Piece]) -> float:
    return max(lift(pieces, a)[0] for a in np.linspace(0, 360, 721))


@dataclass
class Disc:
    outline: np.ndarray  # (n, 2) points of the cam's outline, in the cam's own frame
    pressure: float  # the steepest pressure angle, degrees
    pressure_at: float  # where (cam angle)
    sharpest: float  # the smallest radius the outline bends round (inf: none convex)
    undercut: bool  # the roller is too big for a bend: the outline would cross itself


def disc(pieces: list[Piece], base: float, roller: float, n: int = 720) -> Disc:
    """A disc cam's outline for a roller follower (roller 0: a knife edge) moving along +X."""
    if base <= 0:
        raise CamError("the base radius must be more than 0")
    if roller < 0:
        raise CamError("the roller radius cannot be negative")
    r0 = base + roller
    th = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    s = np.array([lift(pieces, math.degrees(t)) for t in th])
    r, dr = r0 + s[:, 0], s[:, 1]
    # in the cam's frame the follower sits at angle -A when the cam has turned A
    phi = -th
    pitch = np.column_stack([r * np.cos(phi), r * np.sin(phi)])
    d = np.column_stack([dr * np.cos(phi) + r * np.sin(phi), dr * np.sin(phi) - r * np.cos(phi)])  # d/dA
    tang = d / np.linalg.norm(d, axis=1)[:, None]
    normal = np.column_stack([tang[:, 1], -tang[:, 0]])  # pointing out of the cam
    out = (pitch * normal).sum(axis=1) < 0
    normal[out] = -normal[out]
    outline = pitch - roller * normal
    press = np.degrees(np.arctan2(np.abs(dr), r))
    k = int(np.argmax(press))
    # curvature of the pitch curve (convex parts only): the roller must be smaller than its radius
    x, y = pitch[:, 0], pitch[:, 1]
    dx, dy = np.gradient(x, edge_order=2), np.gradient(y, edge_order=2)
    ddx, ddy = np.gradient(dx, edge_order=2), np.gradient(dy, edge_order=2)
    cross = dx * ddy - dy * ddx
    rho = (dx * dx + dy * dy) ** 1.5 / np.where(np.abs(cross) < 1e-15, 1e-15, np.abs(cross))
    convex = np.sign(cross) == np.sign(np.median(cross))
    sharpest = float(rho[convex].min()) if convex.any() else math.inf
    under = roller > 0 and sharpest < roller * (1 + 1e-6)
    return Disc(outline, float(press[k]), math.degrees(th[k]), sharpest - roller if roller else sharpest, under)


def _spline_face(points: np.ndarray, z: float = 0.0):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.GeomAPI import GeomAPI_PointsToBSpline
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.gp import gp_Pnt

    try:  # OCP 8 renamed the array classes
        from OCP.collections import Array1_gp_Pnt as TColgp_Array1OfPnt
    except ImportError:
        from OCP.TColgp import TColgp_Array1OfPnt
    pts = list(points) + [points[0]]
    arr = TColgp_Array1OfPnt(1, len(pts))
    for i, q in enumerate(pts, 1):
        arr.SetValue(i, gp_Pnt(float(q[0]), float(q[1]), z))
    fit = GeomAPI_PointsToBSpline(arr, 3, 8, GeomAbs_C2, 1e-4)
    if not fit.IsDone():
        raise CamError("the cam outline could not be fitted")
    edge = BRepBuilderAPI_MakeEdge(fit.Curve()).Edge()
    wire = BRepBuilderAPI_MakeWire(edge).Wire()
    return BRepBuilderAPI_MakeFace(wire, True).Face()


def disc_solid(cam: Disc, width: float, bore: float = 0.0):
    """The cam plate: the outline extruded ``width`` along +Z from z = 0, with a bore."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec

    if width <= 0:
        raise CamError("the cam's width must be more than 0")
    shape = BRepPrimAPI_MakePrism(_spline_face(cam.outline[::2]), gp_Vec(0, 0, width)).Shape()
    if bore > 0:
        inner = float(np.min(np.linalg.norm(cam.outline, axis=1)))
        if bore / 2 >= inner * 0.95:
            raise CamError(f"a bore of {bore:g} does not fit inside the cam (its smallest radius is {inner:.4g})")
        cyl = BRepPrimAPI_MakeCylinder(bore / 2, width).Shape()
        cut = BRepAlgoAPI_Cut(shape, cyl)
        if not cut.IsDone():
            raise CamError("the bore could not be cut")
        shape = cut.Shape()
    return shape


def barrel_groove(pieces: list[Piece], radius: float, roller: float, depth: float, z0: float, n: int = 72):
    """The groove of a barrel cam (to cut from a cylinder of ``radius`` about Z): the follower's roller,
    standing out along the radius, at height z0 + lift(A) where the cylinder has turned A."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from OCP.gp import gp_Pnt

    if roller <= 0 or depth <= 0:
        raise CamError("a barrel cam needs a roller radius and a groove depth above 0")
    if depth >= radius:
        raise CamError(f"a groove {depth:g} deep does not fit in a cylinder of radius {radius:g}")
    r_in, r_out = radius - depth, radius + max(1.0, 0.2 * depth)

    def section(t):
        s, ds = lift(pieces, math.degrees(t))
        slope = ds / radius  # the groove's slope on the unrolled cylinder
        half = roller * math.sqrt(1 + slope * slope)  # the roller's width measured along the axis
        c, sn = math.cos(-t), math.sin(-t)
        z = z0 + s
        pts = [gp_Pnt(r * c, r * sn, z + dz) for r, dz in ((r_in, -half), (r_out, -half), (r_out, half),
                                                             (r_in, half))]
        poly = BRepBuilderAPI_MakePolygon()
        for q in pts:
            poly.Add(q)
        poly.Close()
        return poly.Wire()

    halves = []
    for k in range(2):
        loft = BRepOffsetAPI_ThruSections(True, False, 1e-6)
        for i in range(n // 2 + 1):
            loft.AddWire(section(2 * math.pi * (k * (n // 2) + i) / n))
        loft.CheckCompatibility(False)
        loft.Build()
        if not loft.IsDone():
            raise CamError("the groove could not be made")
        halves.append(loft.Shape())
    fuse = BRepAlgoAPI_Fuse(halves[0], halves[1])
    if not fuse.IsDone():
        raise CamError("the groove's halves could not be joined")
    return fuse.Shape()
