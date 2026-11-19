"""Involute gears: spur and helical gears, internal gears (a ring with the
teeth inside) and racks, from a module and a tooth count.

The tooth flanks are true involutes of the base circle (sampled and passed
through a smooth spline), joined by an arc at the tip and an arc at the
root; below the base circle the flank goes straight down to the root. A
helical gear is a loft through turned copies of the outline, so the teeth
wind round at the helix angle. Everything is built about the Z axis with
the gear's bottom face on Z = 0; the caller places it.

Sizes (transverse, for a module m, z teeth, pressure angle a):
pitch radius r = m z / 2, base radius rb = r cos a, tip radius r + m,
root radius r - 1.25 m, and two gears of z1 and z2 teeth mesh at the
centre distance m (z1 + z2) / 2 (internal: m (z2 - z1) / 2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ADDENDUM = 1.0  # in modules
DEDENDUM = 1.25


class GearError(ValueError):
    pass


@dataclass
class GearSize:
    module: float  # transverse module (= normal module / cos(helix))
    teeth: int
    pressure: float  # transverse pressure angle, radians
    pitch_r: float
    base_r: float
    tip_r: float
    root_r: float


def size(module: float, teeth: int, pressure_deg: float = 20.0, helix_deg: float = 0.0) -> GearSize:
    """The circles of a gear. ``module`` is the normal module (for a spur gear, the module)."""
    if module <= 0:
        raise GearError("the module must be positive")
    if teeth < 6 or teeth != int(teeth):
        raise GearError("a gear needs a whole number of teeth, at least 6")
    if not 10 <= pressure_deg <= 35:
        raise GearError("the pressure angle should be between 10 and 35 degrees (20 is usual)")
    if abs(helix_deg) >= 60:
        raise GearError("the helix angle must be less than 60 degrees")
    b = math.radians(helix_deg)
    mt = module / math.cos(b)
    at = math.atan(math.tan(math.radians(pressure_deg)) / math.cos(b))
    r = mt * teeth / 2
    return GearSize(mt, int(teeth), at, r, r * math.cos(at), r + ADDENDUM * module, r - DEDENDUM * module)


def _inv(a: float) -> float:
    return math.tan(a) - a


def _half_angle(g: GearSize, rho: float) -> float:
    """Half the angular thickness of a tooth at radius rho (rho >= base radius)."""
    psi = math.pi / (2 * g.teeth)  # half the tooth at the pitch circle (thickness = half the pitch)
    a_rho = math.acos(min(1.0, g.base_r / rho))
    return psi + _inv(g.pressure) - _inv(a_rho)


def outline(g: GearSize, tip_r: float, root_r: float, samples: int = 9):
    """The closed outline as a list of pieces: ("line", p, q), ("arc", p, mid, q), ("curve", [points]).
    Teeth reach out to tip_r, the gaps go down to root_r; flanks are involutes of the base circle."""
    start = max(g.base_r, root_r)
    if tip_r <= start:
        raise GearError("the teeth are too short to have any involute flank")
    th_tip = _half_angle(g, tip_r)
    if th_tip <= 0.01 / g.teeth:
        raise GearError("the teeth come to a point before the tip circle (use more teeth or a smaller "
                        "pressure angle)")
    th0 = _half_angle(g, start)
    pitch = 2 * math.pi / g.teeth
    if 2 * th0 >= pitch * 0.98:
        raise GearError("the teeth are so thick at the root that there is no gap between them")

    def pol(rad, ang):
        return (rad * math.cos(ang), rad * math.sin(ang), 0.0)

    radii = [start + (tip_r - start) * (k / (samples - 1)) ** 1.5 for k in range(samples)]
    pieces = []
    for k in range(g.teeth):
        c = k * pitch
        right = [pol(rho, c - _half_angle(g, rho)) for rho in radii]  # root to tip
        left = [pol(rho, c + _half_angle(g, rho)) for rho in reversed(radii)]  # tip to root
        if root_r < start - 1e-9:
            pieces.append(("line", pol(root_r, c - th0), right[0]))
        pieces.append(("curve", right))
        pieces.append(("arc", right[-1], pol(tip_r, c), left[0]))
        pieces.append(("curve", left))
        if root_r < start - 1e-9:
            pieces.append(("line", left[-1], pol(root_r, c + th0)))
            a0 = c + th0
        else:
            a0 = c + th0
        a1 = c + pitch - th0
        pieces.append(("arc", pol(root_r, a0), pol(root_r, (a0 + a1) / 2), pol(root_r, a1)))
    return pieces


def _wire(pieces):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.GeomAPI import GeomAPI_Interpolate
    from OCP.gp import gp_Pnt

    from .curves import _HArrayPnt as TColgp_HArray1OfPnt

    mk = BRepBuilderAPI_MakeWire()
    for piece in pieces:
        kind = piece[0]
        if kind == "line":
            e = BRepBuilderAPI_MakeEdge(gp_Pnt(*piece[1]), gp_Pnt(*piece[2])).Edge()
        elif kind == "arc":
            arc = GC_MakeArcOfCircle(gp_Pnt(*piece[1]), gp_Pnt(*piece[2]), gp_Pnt(*piece[3])).Value()
            e = BRepBuilderAPI_MakeEdge(arc).Edge()
        else:
            pts = piece[1]
            arr = TColgp_HArray1OfPnt(1, len(pts))
            for i, q in enumerate(pts, 1):
                arr.SetValue(i, gp_Pnt(*q))
            ip = GeomAPI_Interpolate(arr, False, 1e-9)
            ip.Perform()
            e = BRepBuilderAPI_MakeEdge(ip.Curve()).Edge()
        mk.Add(e)
    if not mk.IsDone():
        raise GearError("the tooth outline did not close")
    return mk.Wire()


def _turned(shape, angle: float, z: float = 0.0):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), angle)
    if z:
        s = gp_Trsf()
        s.SetTranslation(gp_Vec(0, 0, z))
        t = s.Multiplied(t)
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def _toothed(g: GearSize, tip_r: float, root_r: float, width: float, helix_deg: float):
    """A solid with the gear's outline, extruded (spur) or twisted (helical) over the width."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec
    from OCP.TopoDS import TopoDS

    w = _wire(outline(g, tip_r, root_r))
    if abs(helix_deg) < 1e-9:
        face = BRepBuilderAPI_MakeFace(w, True).Face()
        return BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, width)).Shape()
    twist = width * math.tan(math.radians(helix_deg)) / g.pitch_r
    n = max(3, int(math.ceil(abs(math.degrees(twist)) / 4.0)) + 1)
    loft = BRepOffsetAPI_ThruSections(True, False, 1e-6)
    loft.CheckCompatibility(False)
    for k in range(n):
        f = k / (n - 1)
        loft.AddWire((getattr(TopoDS, "Wire_s", None) or TopoDS.Wire)(_turned(w, twist * f, width * f)))
    loft.Build()
    if not loft.IsDone():
        raise GearError("the helical teeth could not be lofted")
    return loft.Shape()


def _cyl(r: float, h: float, z0: float = 0.0):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, z0), gp_Dir(0, 0, 1)), r, h).Shape()


def _cut(a, b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut

    op = BRepAlgoAPI_Cut(a, b)
    op.Build()
    if not op.IsDone():
        raise GearError("cutting the gear failed")
    return op.Shape()


def external(module: float, teeth: int, width: float, helix_deg: float = 0.0, bore: float = 0.0,
             pressure_deg: float = 20.0):
    """A spur (helix 0) or helical gear with an optional bore. Returns (shape, GearSize)."""
    if width <= 0:
        raise GearError("the face width must be positive")
    g = size(module, teeth, pressure_deg, helix_deg)
    if g.root_r <= 0:
        raise GearError("the root circle is smaller than nothing")
    shape = _toothed(g, g.tip_r, g.root_r, width, helix_deg)
    if bore:
        if not 0 < bore < 2 * g.root_r * 0.9:
            raise GearError(f"the bore must be smaller than the root circle (diameter {2 * g.root_r:.4g})")
        shape = _cut(shape, _cyl(bore / 2, width + 2, -1))
    return shape, g


def internal(module: float, teeth: int, width: float, helix_deg: float = 0.0, outside: float = 0.0,
             pressure_deg: float = 20.0):
    """A ring gear with the teeth inside. The tooth spaces are the teeth of an outside gear with the
    addendum and dedendum swapped. Returns (shape, GearSize, outside diameter)."""
    if width <= 0:
        raise GearError("the face width must be positive")
    g = size(module, teeth, pressure_deg, helix_deg)
    root = g.pitch_r + DEDENDUM * module  # the internal gear's root, out in the ring
    tip = g.pitch_r - ADDENDUM * module  # its tips, the hole the teeth leave
    if tip <= g.base_r:  # the flanks need to start on the base circle
        tip = g.base_r * 1.0001
    od = outside or 2 * (root + 3 * module)
    if od / 2 <= root:
        raise GearError(f"the outside diameter must be more than the root circle ({2 * root:.4g})")
    if abs(helix_deg) < 1e-9:  # a face with the toothed hole, extruded (much faster than a cut)
        from OCP.BRepBuilderAPI import (
            BRepBuilderAPI_MakeEdge,
            BRepBuilderAPI_MakeFace,
            BRepBuilderAPI_MakeWire,
        )
        from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
        from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt, gp_Vec

        circ = BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)),
                                                                       od / 2)).Edge()).Wire()
        mk = BRepBuilderAPI_MakeFace(circ, True)
        from OCP.TopoDS import TopoDS

        mk.Add((getattr(TopoDS, "Wire_s", None) or TopoDS.Wire)(_wire(outline(g, root, tip)).Reversed()))
        from OCP.ShapeFix import ShapeFix_Face

        fix = ShapeFix_Face(mk.Face())
        fix.FixOrientation()
        fix.Perform()
        return BRepPrimAPI_MakePrism(fix.Face(), gp_Vec(0, 0, width)).Shape(), g, od
    space = _toothed(g, root, tip, width + 2, helix_deg)
    space = _turned(space, 0.0, -1.0)
    ring = _cyl(od / 2, width)
    return _cut(ring, space), g, od


def rack(module: float, teeth: int, width: float, back: float = 0.0, pressure_deg: float = 20.0,
         helix_deg: float = 0.0):
    """A rack along +X: teeth on top (pitch line at Y = 0), a bar of thickness ``back`` under the
    roots, extruded along Z by the width; with a helix angle the teeth lean along X as they go up Z
    (it meshes with a helical gear of the same angle). Returns (shape, pitch along X, total length)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Pnt, gp_Vec

    if module <= 0 or width <= 0:
        raise GearError("the module and the width must be positive")
    if teeth < 1 or teeth != int(teeth):
        raise GearError("a rack needs a whole number of teeth")
    if abs(helix_deg) >= 60:
        raise GearError("the helix angle must be less than 60 degrees")
    b = math.radians(helix_deg)
    a = math.atan(math.tan(math.radians(pressure_deg)) / math.cos(b))  # the pressure angle across X
    p = math.pi * module / math.cos(b)
    ha, hf = ADDENDUM * module, DEDENDUM * module
    back = back or 2 * module
    t = math.tan(a)
    pts = [(0.0, -hf - back)]
    for k in range(int(teeth)):
        x0 = k * p  # the tooth is centred at x0 + p/2; half thickness p/4 at the pitch line
        cx = x0 + p / 2
        pts += [(cx - p / 4 - hf * t, -hf), (cx - p / 4 + ha * t, ha), (cx + p / 4 - ha * t, ha),
                (cx + p / 4 + hf * t, -hf)]
    length = int(teeth) * p
    pts += [(length, -hf), (length, -hf - back)]
    pts.insert(1, (0.0, -hf))
    poly = BRepBuilderAPI_MakePolygon()
    for x, y in pts:
        poly.Add(gp_Pnt(x, y, 0))
    poly.Close()
    if abs(helix_deg) < 1e-9:
        face = BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()
        return BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, width)).Shape(), p, length
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from OCP.gp import gp_Trsf
    from OCP.TopoDS import TopoDS

    t = gp_Trsf()
    t.SetTranslation(gp_Vec(width * math.tan(b), 0, width))
    top = (getattr(TopoDS, "Wire_s", None) or TopoDS.Wire)(BRepBuilderAPI_Transform(poly.Wire(), t, True).Shape())
    loft = BRepOffsetAPI_ThruSections(True, True, 1e-6)
    loft.AddWire(poly.Wire())
    loft.AddWire(top)
    loft.Build()
    if not loft.IsDone():
        raise GearError("the helical rack could not be made")
    return loft.Shape(), p, length


def bevel(module: float, teeth: int, mate: int, width: float, bore: float = 0.0, pressure_deg: float = 20.0):
    """A straight bevel gear for a mate of ``mate`` teeth on an axis at right angles. The back (large
    end) face is at Z = 0, the teeth run up the pitch cone towards its apex on the axis. The tooth
    outline is the spur gear's, shrunk towards the apex (a close stand-in for the true one).
    Returns (shape, GearSize at the large end, pitch cone angle in degrees, apex height)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from OCP.gp import gp_Pnt, gp_Trsf
    from OCP.TopoDS import TopoDS

    if width <= 0:
        raise GearError("the face width must be positive")
    if mate < 6 or mate != int(mate):
        raise GearError("the mate needs a whole number of teeth, at least 6")
    g = size(module, teeth, pressure_deg)
    delta = math.atan2(teeth, mate)
    cone = g.pitch_r / math.sin(delta)  # pitch cone distance, apex to the large end
    apex = g.pitch_r / math.tan(delta)
    if width > cone / 3 + 1e-9:
        raise GearError(f"the face width should be at most a third of the cone distance ({cone / 3:.4g})")
    w = _wire(outline(g, g.tip_r, g.root_r))
    k = (cone - width) / cone
    t = gp_Trsf()
    t.SetScale(gp_Pnt(0, 0, apex), k)
    small = (getattr(TopoDS, "Wire_s", None) or TopoDS.Wire)(BRepBuilderAPI_Transform(w, t, True).Shape())
    loft = BRepOffsetAPI_ThruSections(True, True, 1e-6)
    loft.AddWire(w)
    loft.AddWire(small)
    loft.Build()
    if not loft.IsDone():
        raise GearError("the bevel teeth could not be made")
    shape = loft.Shape()
    if bore:
        if not 0 < bore < 2 * g.root_r * k * 0.9:
            raise GearError(f"the bore must be smaller than the small end's root circle "
                            f"(diameter {2 * g.root_r * k:.4g})")
        shape = _cut(shape, _cyl(bore / 2, apex + 2, -1))
    return shape, g, math.degrees(delta), apex


def worm(module: float, starts: int, length: float, pitch_d: float = 0.0, pressure_deg: float = 20.0):
    """A worm along +Z from 0 to ``length``: ``starts`` threads of axial pitch pi x module (lead: starts
    pitches), right hand. Returns (shape, pitch diameter, lead angle in degrees)."""
    from . import threads as th

    if module <= 0 or length <= 0:
        raise GearError("the module and the length must be positive")
    if starts < 1 or starts > 6 or starts != int(starts):
        raise GearError("a worm has 1 to 6 starts (threads)")
    d1 = pitch_d or 10 * module
    if d1 < 4 * module:
        raise GearError(f"the worm's pitch diameter must be at least 4 modules ({4 * module:g})")
    px = math.pi * module
    lead = starts * px
    a = math.radians(pressure_deg)
    r1 = d1 / 2
    tip, root = r1 + ADDENDUM * module, r1 - DEDENDUM * module
    over = 0.3 * module
    half_root = px / 4 - DEDENDUM * module * math.tan(a)
    if half_root <= 0:
        raise GearError("the pressure angle is too big for this module: the gaps close at the root")
    sec = [(root, -half_root), (tip + over, -(px / 4 + (ADDENDUM * module + over) * math.tan(a))),
           (tip + over, px / 4 + (ADDENDUM * module + over) * math.tan(a)), (root, half_root)]
    shape = _cyl(tip, length)
    turns = length / lead + 2
    for k in range(int(starts)):
        o = (0.0, 0.0, -lead + k * px)
        profile = th._polygon([(r, 0.0, o[2] + z) for r, z in sec])
        path = th.helix_wire(o, (0, 0, 1), (1, 0, 0), (root + tip + over) / 2, lead, turns)
        try:
            tool = th._sweep(profile, path, (0, 0, 1), "worm thread")
        except th.ThreadError as exc:
            raise GearError(str(exc)) from None
        shape = _cut(shape, tool)
    return shape, d1, math.degrees(math.atan(lead / (math.pi * d1)))
