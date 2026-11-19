"""Standard fasteners from ISO tables: socket head cap screws (ISO 4762),
hex head screws (ISO 4017), hex nuts (ISO 4032) and plain washers
(ISO 7089), M3 to M24.

Each is built about the Z axis: a screw's head sits on Z = 0 and goes up,
its shank goes down to Z = -length; a nut or washer sits on Z = 0 and goes
up. Real threads are cut with the THREAD machinery (threads.py) when asked,
plain ones leave the shank at the nominal diameter (a nut's hole too, so a
plain screw fits a plain nut).
"""

from __future__ import annotations

import math

from . import threads as th

# size: (pitch, cap head dia dk, cap head height k, socket across flats, socket depth)
CAP = {3: (0.5, 5.5, 3, 2.5, 1.3), 4: (0.7, 7, 4, 3, 2), 5: (0.8, 8.5, 5, 4, 2.5), 6: (1.0, 10, 6, 5, 3),
       8: (1.25, 13, 8, 6, 4), 10: (1.5, 16, 10, 8, 5), 12: (1.75, 18, 12, 10, 6), 16: (2.0, 24, 16, 14, 8),
       20: (2.5, 30, 20, 17, 10), 24: (3.0, 36, 24, 19, 12)}
# size: (across flats s, hex head height k, nut height m)
HEX = {3: (5.5, 2, 2.4), 4: (7, 2.8, 3.2), 5: (8, 3.5, 4.7), 6: (10, 4, 5.2), 8: (13, 5.3, 6.8),
       10: (16, 6.4, 8.4), 12: (18, 7.5, 10.8), 16: (24, 10, 14.8), 20: (30, 12.5, 18), 24: (36, 15, 21.5)}
# size: (inner dia, outer dia, thickness)
WASHER = {3: (3.2, 7, 0.5), 4: (4.3, 9, 0.8), 5: (5.3, 10, 1), 6: (6.4, 12, 1.6), 8: (8.4, 16, 1.6),
          10: (10.5, 20, 2), 12: (13, 24, 2.5), 16: (17, 30, 3), 20: (21, 37, 3), 24: (25, 44, 4)}

KINDS = {"CAP": "ISO 4762 socket head cap screw", "HEXBOLT": "ISO 4017 hex head screw",
         "NUT": "ISO 4032 hex nut", "WASHER": "ISO 7089 plain washer"}
SCREWS = ("CAP", "HEXBOLT")


class FastenerError(ValueError):
    pass


def size_of(text: str) -> int:
    t = text.strip().upper()
    t = t.removeprefix("M")
    try:
        d = float(t)
    except ValueError:
        raise FastenerError(f"{text!r} is not a size; give M3, M4, M5, M6, M8, M10, M12, M16, M20 or M24") from None
    if d != int(d) or int(d) not in CAP:
        raise FastenerError(f"M{t} is not in the table; sizes are M3, M4, M5, M6, M8, M10, M12, M16, M20, M24")
    return int(d)


def thread_length(d: int, length: float) -> float:
    """ISO 4762 thread length b for a cap screw (the rest of a long screw is a plain shank)."""
    b = 2 * d + 12 if length <= 125 else 2 * d + 16 if length <= 200 else 2 * d + 29
    return min(length, b)


def _cyl(r, h, z0=0.0):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, z0), gp_Dir(0, 0, 1)), r, h).Shape()


def _hex_prism(s, h, z0=0.0):
    """A hexagon of across-flats s, from z0 up by h, flats facing +-X... corners on +-X."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Pnt, gp_Vec

    e = s / math.sqrt(3)  # corner radius
    poly = BRepBuilderAPI_MakePolygon()
    for k in range(6):
        a = math.pi / 3 * k
        poly.Add(gp_Pnt(e * math.cos(a), e * math.sin(a), z0))
    poly.Close()
    return BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(poly.Wire(), True).Face(), gp_Vec(0, 0, h)).Shape()


def _bool(kind, a, b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse

    op = {"cut": BRepAlgoAPI_Cut, "fuse": BRepAlgoAPI_Fuse, "common": BRepAlgoAPI_Common}[kind](a, b)
    op.Build()
    if not op.IsDone():
        raise FastenerError(f"building the fastener failed ({kind})")
    return op.Shape()


def _chamfer_cone(r_face, z_face, h, up: bool):
    """A cone that trims the corners of a hex at 30 degrees from the face at z_face (r_face across the
    face), reaching h into the part (up: the face is the top)."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    grow = h / math.tan(math.radians(30))
    if up:
        return BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(0, 0, z_face - h), gp_Dir(0, 0, 1)), r_face + grow, r_face,
                                    h).Shape()
    return BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(0, 0, z_face), gp_Dir(0, 0, 1)), r_face, r_face + grow, h).Shape()


def _end_chamfer(shape, z_end, r, c):
    """Bevel the circular edge of the shank end (at z_end, radius r) by c."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
    from OCP.GeomAbs import GeomAbs_Circle
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    ex = TopExp_Explorer(shape, TopAbs_EDGE)
    mk = BRepFilletAPI_MakeChamfer(shape)
    found = False
    while ex.More():
        e = (getattr(TopoDS, "Edge_s", None) or TopoDS.Edge)(ex.Current())
        ad = BRepAdaptor_Curve(e)
        if ad.GetType() == GeomAbs_Circle:
            c0 = ad.Circle()
            if abs(c0.Radius() - r) < 1e-6 and abs(c0.Location().Z() - z_end) < 1e-6:
                mk.Add(c, e)
                found = True
                break
        ex.Next()
    if not found:
        return shape
    mk.Build()
    return mk.Shape() if mk.IsDone() else shape


def _round_face(shape, r):
    """The cylindrical face of radius r (the shank or the nut's hole)."""
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        try:
            rf = th.round_face(ex.Current())
            if abs(rf.radius - r) < 1e-6:
                return rf
        except th.ThreadError:
            pass
        ex.Next()
    raise FastenerError("could not find the face to thread")


def _thread(shape, rf, major, pitch, length, tol=1e-4):
    ends = th.free_ends(shape, rf, tol)
    origin, axis, a, b, _where = th.thread_span(rf, ends, pitch, length)
    tool = th.groove_tool(origin, axis, major, pitch, a, b, rf.outside, rf.radius, False)
    return _bool("cut", shape, tool)


def build(kind: str, d: int, length: float = 0.0, threaded: bool = False):
    """The fastener's shape and a description, e.g. 'M8x20 ISO 4762 socket head cap screw'."""
    if kind not in KINDS:
        raise FastenerError(f"the kind must be one of {', '.join(KINDS)}")
    pitch, dk, k, s_sock, t_sock = CAP[d]
    if kind in SCREWS:
        if length <= 0:
            raise FastenerError("give the screw's length (under the head), e.g. 20")
        if length < 2 * pitch:
            raise FastenerError("the screw is too short")
        shank = _cyl(d / 2, length + 1e-3, -length)
        if kind == "CAP":
            head = _cyl(dk / 2, k)
            head = _bool("cut", head, _hex_prism(s_sock, t_sock + 1, k - t_sock))
        else:
            s, kh, _m = HEX[d]
            head = _bool("common", _hex_prism(s, kh), _chamfer_cone(0.95 * s / 2, kh, kh, True))
        shape = _bool("fuse", head, shank)
        from . import robust

        shape = robust.unwrap(robust.merge_faces(shape)[0])
        shape = _end_chamfer(shape, -length, d / 2, min(pitch, d / 8))
        tl = length if kind == "HEXBOLT" else thread_length(d, length)
        if threaded:
            shape = _thread(shape, _round_face(shape, d / 2), d, pitch, tl)
        label = f"M{d}x{length:g} {KINDS[kind]}"
        return shape, label
    if kind == "NUT":
        s, _kh, mh = HEX[d]
        nut = _hex_prism(s, mh)
        nut = _bool("common", nut, _chamfer_cone(0.95 * s / 2, mh, mh, True))
        nut = _bool("common", nut, _chamfer_cone(0.95 * s / 2, 0.0, mh, False))
        hole = (d - 2 * th.INT_DEPTH * pitch) if threaded else d
        nut = _bool("cut", nut, _cyl(hole / 2, mh + 2, -1))
        if threaded:
            nut = _thread(nut, _round_face(nut, hole / 2), d, pitch, 0.0)
        return nut, f"M{d} {KINDS[kind]}"
    d1, d2, h = WASHER[d]
    washer = _bool("cut", _cyl(d2 / 2, h), _cyl(d1 / 2, h + 2, -1))
    return washer, f"M{d} {KINDS[kind]}"


def height(kind: str, d: int) -> float:
    """How far the part stands up from its seat (a screw's head, a nut, a washer)."""
    if kind == "CAP":
        return CAP[d][2]
    if kind == "HEXBOLT":
        return HEX[d][1]
    if kind == "NUT":
        return HEX[d][2]
    return WASHER[d][2]
