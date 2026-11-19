"""Features for moulded plastic parts: screw bosses with support ribs, snap
hooks and vents (a grille of slots through a wall).

Bosses and snap hooks are built about +Z at the origin (the caller places
them and fuses them to the part); a vent is a set of slot-shaped cutters
laid on a flat face.
"""

from __future__ import annotations

import math


class PlasticError(ValueError):
    pass


def _cyl(r, h, z0=0.0):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, z0), gp_Dir(0, 0, 1)), r, h).Shape()


def _prism(points, vec):
    """A closed polygon (3D points) pushed along vec."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Pnt, gp_Vec

    poly = BRepBuilderAPI_MakePolygon()
    for q in points:
        poly.Add(gp_Pnt(*q))
    poly.Close()
    return BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(poly.Wire(), True).Face(), gp_Vec(*vec)).Shape()


def _bool(kind, a, b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse

    op = (BRepAlgoAPI_Fuse if kind == "fuse" else BRepAlgoAPI_Cut)(a, b)
    op.Build()
    if not op.IsDone():
        raise PlasticError(f"building the feature failed ({kind})")
    return op.Shape()


def boss(height: float, outside: float, hole: float, ribs: int = 4, rib_thickness: float = 0.0,
         rib_length: float = 0.0, hole_depth: float = 0.0):
    """A screw boss standing on Z = 0: a tube of the outside diameter with a hole from the top, and
    ``ribs`` ribs round it, sloping from 0.8 of the height at the boss down to a quarter of the height
    at their far end. Returns (boss, hole cutter)."""
    if height <= 0 or outside <= 0:
        raise PlasticError("the height and the outside diameter must be positive")
    if not 0 <= hole < outside:
        raise PlasticError("the hole must be smaller than the outside diameter")
    if ribs < 0 or ribs != int(ribs) or ribs > 12:
        raise PlasticError("ribs must be a whole number from 0 to 12")
    shape = _cyl(outside / 2, height)
    t = rib_thickness or max(0.6 * (outside - hole) / 2, 0.05 * outside)
    length = rib_length or 0.75 * outside
    r0 = outside / 2 - 0.1 * t  # start just inside the tube so the rib joins it
    for k in range(int(ribs)):
        a = 2 * math.pi * k / ribs
        c, s = math.cos(a), math.sin(a)
        prof = [(r0, 0.0), (r0 + length, 0.0), (r0 + length, 0.25 * height), (r0, 0.8 * height)]
        # the profile in the plane of the rib (radial, up), pushed sideways by the thickness
        pts = [(x * c - (-t / 2) * s, x * s + (-t / 2) * c, z) for x, z in prof]
        rib = _prism(pts, (-s * t, c * t, 0.0))
        shape = _bool("fuse", shape, rib)
    cutter = None
    if hole:
        depth = hole_depth or height
        if depth > height + 1e-9:
            raise PlasticError("the hole cannot be deeper than the boss")
        cutter = _cyl(hole / 2, depth + 1.0, height - depth)
    return shape, cutter


def snap_hook(length: float, width: float, thickness: float, overhang: float = 0.0, lead: float = 30.0,
              ret: float = 90.0):
    """A cantilever snap hook standing on Z = 0, the beam from x = -thickness to 0, the hook sticking
    out along +X at the top. ``lead`` is the angle of the slope that pushes it in (from the beam),
    ``ret`` the angle of the catch (90: it does not let go)."""
    if min(length, width, thickness) <= 0:
        raise PlasticError("the length, width and thickness must be positive")
    over = overhang or thickness
    if over <= 0:
        raise PlasticError("the overhang must be positive")
    if not 10 <= lead <= 80:
        raise PlasticError("the lead angle should be 10 to 80 degrees")
    if not 30 <= ret <= 90:
        raise PlasticError("the catch angle should be 30 to 90 degrees")
    lead_h = over / math.tan(math.radians(lead))
    catch_h = over / math.tan(math.radians(ret)) if ret < 89.999 else 0.0
    tip = 0.15 * thickness  # a small flat at the top
    z_catch = length - tip - lead_h
    if z_catch - catch_h < 0.3 * length:
        raise PlasticError("the hook is too big for the beam's length (make it longer or the overhang smaller)")
    # (the hook: a catch from the beam out to the overhang, then the lead slope back to the beam)
    prof = [(-thickness, 0.0), (0.0, 0.0), (0.0, z_catch - catch_h), (over, z_catch), (over, z_catch + tip),
            (0.0, z_catch + tip + lead_h), (-thickness, z_catch + tip + lead_h)]
    pts = [(x, -width / 2, z) for x, z in prof]
    return _prism(pts, (0.0, width, 0.0)), z_catch


def slot(length: float, width: float, depth: float):
    """A slot (two half circles joined by straight sides) along X, centred at the origin, from Z = 0 up
    by depth."""
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeWire,
    )
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.gp import gp_Pnt, gp_Vec

    r = width / 2
    h = max(length / 2 - r, 0.0)
    if h < 1e-9:
        return _cyl(r, depth)
    p1, p2, p3, p4 = gp_Pnt(-h, -r, 0), gp_Pnt(h, -r, 0), gp_Pnt(h, r, 0), gp_Pnt(-h, r, 0)
    mk = BRepBuilderAPI_MakeWire()
    mk.Add(BRepBuilderAPI_MakeEdge(p1, p2).Edge())
    mk.Add(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(p2, gp_Pnt(h + r, 0, 0), p3).Value()).Edge())
    mk.Add(BRepBuilderAPI_MakeEdge(p3, p4).Edge())
    mk.Add(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(p4, gp_Pnt(-h - r, 0, 0), p1).Value()).Edge())
    face = BRepBuilderAPI_MakeFace(mk.Wire(), True).Face()
    return BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, depth)).Shape()


def vent_centres(count: int, pitch: float) -> list[float]:
    """Offsets across the slots of a grille, centred on 0."""
    return [(k - (count - 1) / 2) * pitch for k in range(count)]
