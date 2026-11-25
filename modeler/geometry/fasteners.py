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
from dataclasses import dataclass

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


# =============================================================================
# More standard parts (PLAN item 98): countersunk, button-head and set screws,
# dowel and spring pins, threaded inserts, ball bearings, circlips, parallel
# keys, and inch screws, nuts and washers. ``make`` builds any of them;
# ``hole_for`` gives the hole that fits it in the part it goes into.
# =============================================================================
IN = 25.4

# ISO 10642 countersunk socket screws (90°): size: (head dia dk, head height k, socket across flats)
CSK = {3: (6.72, 1.86, 2), 4: (8.96, 2.48, 2.5), 5: (11.2, 3.1, 3), 6: (13.44, 3.72, 4), 8: (17.92, 4.96, 5),
       10: (22.4, 6.2, 6), 12: (26.88, 7.44, 8), 16: (33.6, 8.8, 10), 20: (40.32, 10.16, 12)}
# ISO 7380 button head socket screws: size: (head dia, head height, socket across flats)
BUTTON = {3: (5.7, 1.65, 2), 4: (7.6, 2.2, 2.5), 5: (9.5, 2.75, 3), 6: (10.5, 3.3, 4), 8: (14, 4.4, 5),
          10: (17.5, 5.5, 6), 12: (21, 6.6, 8), 16: (28, 8.8, 10)}
# ISO 4026 set screws (flat point): size: (socket across flats, socket depth)
SET = {3: (1.5, 1.2), 4: (2, 1.5), 5: (2.5, 2), 6: (3, 2), 8: (4, 3), 10: (5, 4), 12: (6, 4.8), 16: (8, 6.4),
       20: (10, 8), 24: (12, 10)}
# ISO 273 medium clearance holes
CLEARANCE = {3: 3.4, 4: 4.5, 5: 5.5, 6: 6.6, 8: 9, 10: 11, 12: 13.5, 16: 17.5, 20: 22, 24: 26}
# ISO 8734 dowel pins: diameters; ISO 8752 spring pins: diameter: wall
DOWELS = (2, 2.5, 3, 4, 5, 6, 8, 10, 12, 16, 20)
SPRING = {2: 0.4, 2.5: 0.5, 3: 0.6, 4: 0.8, 5: 1, 6: 1.2, 8: 1.5, 10: 2, 12: 2.5, 16: 3, 20: 4}
# heat-set threaded inserts (common sizes): size: (outside dia, length, hole dia)
INSERT = {2: (3.6, 4, 3.2), 3: (4.6, 5.7, 4.0), 4: (5.6, 8.1, 5.0), 5: (6.4, 9.5, 5.8), 6: (8.0, 12.7, 7.5),
          8: (10, 12.7, 9.5)}
# deep groove ball bearings: designation: (bore d, outside D, width B)
BEARINGS = {"623": (3, 10, 4), "624": (4, 13, 5), "625": (5, 16, 5), "626": (6, 19, 6), "608": (8, 22, 7),
            "609": (9, 24, 7), "6000": (10, 26, 8), "6001": (12, 28, 8), "6002": (15, 32, 9), "6003": (17, 35, 10),
            "6004": (20, 42, 12), "6005": (25, 47, 12), "6200": (10, 30, 9), "6201": (12, 32, 10),
            "6202": (15, 35, 11), "6203": (17, 40, 12), "6204": (20, 47, 14), "6205": (25, 52, 15)}
# DIN 471 circlips for shafts: shaft d: (thickness, groove dia, radial width)
CIRCLIP = {8: (0.8, 7.6, 1.5), 10: (1, 9.6, 1.8), 12: (1, 11.5, 1.8), 15: (1, 14.3, 2.2), 17: (1, 16.2, 2.3),
           20: (1.2, 19, 2.6), 25: (1.2, 23.9, 3), 30: (1.5, 28.6, 3.5), 35: (1.5, 33, 3.9), 40: (1.75, 37.5, 4.4)}
# DIN 6885 A parallel keys: (shaft over, up to): (width b, height h)
KEYS = [((6, 8), (2, 2)), ((8, 10), (3, 3)), ((10, 12), (4, 4)), ((12, 17), (5, 5)), ((17, 22), (6, 6)),
        ((22, 30), (8, 7)), ((30, 38), (10, 8)), ((38, 44), (12, 8)), ((44, 50), (14, 9)), ((50, 58), (16, 10))]
# inch (UNC) sizes, in inches: label: (major dia, threads per inch, cap head dia, cap head height, socket af,
# hex af, hex head height, nut height, washer id, washer od, washer t)
INCH = {"#4-40": (0.112, 40, 0.183, 0.112, 0.094, 0.25, 0.08, 0.094, 0.125, 0.312, 0.032),
        "#6-32": (0.138, 32, 0.226, 0.138, 0.109, 0.3125, 0.09, 0.109, 0.156, 0.375, 0.049),
        "#8-32": (0.164, 32, 0.270, 0.164, 0.141, 0.34375, 0.11, 0.125, 0.188, 0.438, 0.049),
        "#10-24": (0.190, 24, 0.312, 0.190, 0.156, 0.375, 0.12, 0.125, 0.219, 0.500, 0.049),
        "1/4-20": (0.250, 20, 0.375, 0.250, 0.188, 0.4375, 0.163, 0.21875, 0.281, 0.625, 0.065),
        "5/16-18": (0.3125, 18, 0.469, 0.3125, 0.250, 0.5, 0.211, 0.265625, 0.344, 0.688, 0.065),
        "3/8-16": (0.375, 16, 0.5625, 0.375, 0.3125, 0.5625, 0.243, 0.328125, 0.406, 0.812, 0.065),
        "1/2-13": (0.500, 13, 0.750, 0.500, 0.375, 0.75, 0.323, 0.4375, 0.531, 1.062, 0.095)}
INCH_CLEAR = {"#4-40": 0.120, "#6-32": 0.144, "#8-32": 0.170, "#10-24": 0.201, "1/4-20": 0.266,
              "5/16-18": 0.328, "3/8-16": 0.397, "1/2-13": 0.531}

ALL_KINDS = {**KINDS, "CSK": "ISO 10642 countersunk socket screw", "BUTTON": "ISO 7380 button head screw",
             "SET": "ISO 4026 set screw", "DOWEL": "ISO 8734 dowel pin", "SPRINGPIN": "ISO 8752 spring pin",
             "INSERT": "heat-set threaded insert", "BEARING": "deep groove ball bearing",
             "CIRCLIP": "DIN 471 circlip", "KEY": "DIN 6885 A parallel key"}
ALIASES = {"BOLT": "HEXBOLT", "HEX": "HEXBOLT", "SHCS": "CAP", "SCREW": "CAP", "COUNTERSUNK": "CSK",
           "FLAT": "CSK", "BHCS": "BUTTON", "GRUB": "SET", "PIN": "DOWEL", "ROLLPIN": "SPRINGPIN",
           "RING": "CIRCLIP", "SNAPRING": "CIRCLIP"}
LENGTHED = ("CAP", "HEXBOLT", "CSK", "BUTTON", "SET", "DOWEL", "SPRINGPIN", "KEY")
INCH_KINDS = ("CAP", "HEXBOLT", "NUT", "WASHER", "SET")
# how a part sits on its seat: "down" goes into the hole from the seat (a screw's shank, a pin, an insert,
# a bearing in its bore); "up" stands on the seat (a nut, a washer, a circlip, a key)
INTO = ("CAP", "HEXBOLT", "CSK", "BUTTON", "SET", "DOWEL", "SPRINGPIN", "INSERT", "BEARING")


def kind_of(text: str) -> str:
    k = text.strip().upper()
    k = ALIASES.get(k, k)
    if k not in ALL_KINDS:
        raise FastenerError(f"the kind must be one of {', '.join(ALL_KINDS)}")
    return k


def _num(v: float) -> str:
    return f"{v:g}"


def _metric(text: str, table, what: str) -> int:
    t = text.strip().upper().removeprefix("M")
    try:
        d = float(t)
    except ValueError:
        raise FastenerError(f"{text!r} is not a size; give one of {', '.join('M' + _num(k) for k in table)}") from None
    if d not in table:
        raise FastenerError(f"M{_num(d)} is not in the {what} table; sizes are "
                            f"{', '.join('M' + _num(k) for k in table)}")
    return int(d) if d == int(d) else d


def _inch(text: str) -> str | None:
    t = text.strip().upper().replace(" ", "").replace("NO.", "#")
    return next((k for k in INCH if k.upper() == t or k.split("-")[0].upper() == t), None)


@dataclass
class Made:
    shape: object
    label: str  # "M8x25 ISO 4762 socket head cap screw"
    name: str  # the base of the body's name: M8x25_CAP
    kind: str
    d: float  # the thread or pin diameter (mm); a bearing's bore, a circlip's shaft
    pitch: float = 0.0
    length: float = 0.0  # how far it goes into the hole (screws, pins, inserts, bearings)
    head: float = 0.0  # a head's diameter (counterbores and countersinks)
    head_h: float = 0.0
    clearance: float = 0.0  # the clearance hole
    fit_hole: float = 0.0  # the hole it is pressed into (pins, inserts, bearings)
    inch: bool = False


def make(kind: str, size: str, length: float = 0.0, threaded: bool = False) -> Made:
    """Any standard part from the tables. Screws, pins, inserts and bearings go into their hole from the
    seat at Z = 0 down along -Z (a screw's head and a button stand up from it, a countersunk head sinks
    into it); nuts, washers, circlips and keys stand up from Z = 0."""
    k = kind_of(kind)
    inch = _inch(size)
    if inch is not None:
        return _make_inch(k, inch, length, threaded)
    if k in KINDS:
        d = size_of(size)
        shape, label = build(k, d, length, threaded)
        pitch = CAP[d][0]
        base = f"M{d}x{_num(length)}_{k}" if k in SCREWS else f"M{d}_{k}"
        head = CAP[d][1] if k == "CAP" else HEX[d][0] * 2 / math.sqrt(3) if k == "HEXBOLT" else 0.0
        return Made(shape, label, base, k, d, pitch, length if k in SCREWS else 0.0, head,
                    height(k, d), CLEARANCE[d])
    if k in ("CSK", "BUTTON", "SET"):
        table = {"CSK": CSK, "BUTTON": BUTTON, "SET": SET}[k]
        d = _metric(size, table, ALL_KINDS[k])
        if length <= 0:
            raise FastenerError("give the screw's length, e.g. 20")
        pitch = CAP[d][0]
        if k == "CSK":
            dk, kh, s = CSK[d]
            if length <= kh:
                raise FastenerError(f"an M{d} countersunk screw is longer than its head ({_num(kh)})")
            shape = _csk(d, dk, kh, s, length)
            head, head_h = dk, kh
        elif k == "BUTTON":
            dk, kh, s = BUTTON[d]
            shape = _button(d, dk, kh, s, length)
            head, head_h = dk, kh
        else:
            s, t = SET[d]
            shape = _bool("cut", _cyl(d / 2, length, -length), _hex_prism(s, t + 1, -t))
            head, head_h = 0.0, 0.0
        shape = _end_chamfer(shape, -length, d / 2, min(pitch, d / 8))
        if threaded:
            shape = _thread(shape, _round_face(shape, d / 2), d, pitch,
                            length - (CSK[d][1] if k == "CSK" else 0.0))
        return Made(shape, f"M{d}x{_num(length)} {ALL_KINDS[k]}", f"M{d}x{_num(length)}_{k}", k, d, pitch,
                    length, head, head_h, CLEARANCE.get(d, d * 1.1))
    if k in ("DOWEL", "SPRINGPIN"):
        d = _pin_size(size, DOWELS if k == "DOWEL" else tuple(SPRING))
        if length <= 0:
            raise FastenerError("give the pin's length, e.g. 20")
        if k == "DOWEL":
            shape = _cyl(d / 2, length, -length)
            c = min(0.15 * d, length / 4)
            shape = _end_chamfer(_end_chamfer(shape, -length, d / 2, c), 0.0, d / 2, c)
        else:
            wall = SPRING[d]
            tube = _bool("cut", _cyl(d / 2, length, -length), _cyl(d / 2 - wall, length + 2, -length - 1))
            slot = _box(-d, -0.1 * d, -length - 1, d, 0.2 * d, length + 2, x0=0.0)
            shape = _bool("cut", tube, slot)
        return Made(shape, f"{_num(d)}x{_num(length)} {ALL_KINDS[k]}", f"D{_num(d)}x{_num(length)}_{k}".replace(".", "_"),
                    k, d, 0.0, length, fit_hole=d)
    if k == "INSERT":
        d = _metric(size, INSERT, ALL_KINDS[k])
        od, ln, hole = INSERT[d]
        body = _bool("cut", _cyl(od / 2, ln, -ln), _cyl(d / 2, ln + 2, -ln - 1))
        for z in (-0.3 * ln, -0.7 * ln):  # two grooves for the plastic to flow into
            ring = _bool("cut", _cyl(od / 2 + 1, 0.12 * ln, z - 0.06 * ln), _cyl(od / 2 - 0.25, 0.12 * ln + 2,
                                                                                  z - 0.06 * ln - 1))
            body = _bool("cut", body, ring)
        return Made(body, f"M{d} {ALL_KINDS[k]} ({_num(od)} x {_num(ln)})", f"M{d}_INSERT", k, d, CAP.get(d, (0.4,))[0],
                    ln, fit_hole=hole)
    if k == "BEARING":
        des = size.strip().upper().removesuffix("-2RS").removesuffix("2RS").removesuffix("ZZ")
        if des not in BEARINGS:
            raise FastenerError(f"{size!r} is not in the bearing table; sizes are {', '.join(BEARINGS)}")
        bd, od, w = BEARINGS[des]
        ring_in, ring_out = bd + 0.3 * (od - bd), od - 0.3 * (od - bd)
        ring = _bool("cut", _cyl(od / 2, w, -w), _cyl(bd / 2, w + 2, -w - 1))
        recess = min(0.3, w / 10)
        for z in (-recess, -w - 1e-6):  # the seals sit a little below both faces
            groove = _bool("cut", _cyl(ring_out / 2, recess + 1e-6, z), _cyl(ring_in / 2, recess + 2, z - 1))
            ring = _bool("cut", ring, groove)
        return Made(ring, f"{des}-2RS {ALL_KINDS[k]} ({_num(bd)} x {_num(od)} x {_num(w)})", f"B{des}", k, bd, 0.0,
                    w, fit_hole=od)
    if k == "CIRCLIP":
        d = _pin_size(size, tuple(CIRCLIP))
        s, groove, width = CIRCLIP[d]
        ring = _bool("cut", _cyl(groove / 2 + width, s), _cyl(groove / 2, s + 2, -1))
        gap = _wedge(groove / 2 + width + 1, s, 40)
        return Made(_bool("cut", ring, gap), f"{_num(d)} {ALL_KINDS[k]} (groove {_num(groove)})",
                    f"D{_num(d)}_CIRCLIP", k, d, 0.0, 0.0, fit_hole=groove)
    # KEY
    b, h = _key_size(size)
    if length <= b:
        raise FastenerError(f"give the key's length (more than its width {_num(b)})")
    return Made(_key(b, h, length), f"{_num(b)}x{_num(h)}x{_num(length)} {ALL_KINDS[k]}",
                f"KEY{_num(b)}x{_num(h)}x{_num(length)}".replace(".", "_"), k, b, 0.0, 0.0)


def _pin_size(text: str, table) -> float:
    t = text.strip().upper().removeprefix("D").removeprefix("Ø")
    try:
        d = float(t)
    except ValueError:
        raise FastenerError(f"{text!r} is not a size; give one of {', '.join(_num(x) for x in table)}") from None
    if d not in table:
        raise FastenerError(f"{_num(d)} is not in the table; sizes are {', '.join(_num(x) for x in table)}")
    return int(d) if d == int(d) else d


def _key_size(text: str) -> tuple[float, float]:
    t = text.strip().upper()
    if "X" in t:
        try:
            b, h = (float(v) for v in t.split("X", 1))
        except ValueError:
            raise FastenerError(f"{text!r} is not a key size; give width x height (6x6) or the shaft (20)") from None
        if b <= 0 or h <= 0:
            raise FastenerError("a key's width and height must be more than 0")
        return b, h
    try:
        shaft = float(t.removeprefix("D"))
    except ValueError:
        raise FastenerError(f"{text!r} is not a key size; give width x height (6x6) or the shaft (20)") from None
    for (lo, hi), bh in KEYS:
        if lo < shaft <= hi:
            return bh
    raise FastenerError(f"no DIN 6885 key for a {_num(shaft)} shaft (6 to 58)")


def _box(x, y, z, dx, dy, dz, x0=None):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    return BRepPrimAPI_MakeBox(gp_Pnt(x if x0 is None else x0, y, z), dx, dy, dz).Shape()


def _wedge(r, h, deg):
    """A pie slice round +X, deg wide, from z = -1 up by h + 2 (the gap of a circlip)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Pnt, gp_Vec

    a = math.radians(deg / 2)
    poly = BRepBuilderAPI_MakePolygon()
    for q in ((0, 0), (2 * r * math.cos(a), -2 * r * math.sin(a)), (2 * r * math.cos(a), 2 * r * math.sin(a))):
        poly.Add(gp_Pnt(q[0], q[1], -1))
    poly.Close()
    return BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(poly.Wire(), True).Face(), gp_Vec(0, 0, h + 2)).Shape()


def _key(b, h, length):
    """A form A key: round ends, along X, centred on the origin, standing on Z = 0."""
    body = _box(-(length - b) / 2, -b / 2, 0, length - b, b, h)
    for x in (-(length - b) / 2, (length - b) / 2):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

        body = _bool("fuse", body, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, 0, 0), gp_Dir(0, 0, 1)), b / 2, h).Shape())
    from . import robust

    return robust.unwrap(robust.merge_faces(body)[0])


def _csk(d, dk, kh, s, length):
    """A 90° countersunk head whose top is the seat (Z = 0), sunk into the part, and the shank below."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone

    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    head = BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(0, 0, -kh), gp_Dir(0, 0, 1)), d / 2, dk / 2, kh).Shape()
    shape = _bool("fuse", head, _cyl(d / 2, length - kh + 1e-3, -length))
    from . import robust

    shape = robust.unwrap(robust.merge_faces(shape)[0])
    return _bool("cut", shape, _hex_prism(s, 0.6 * kh + 1, -0.6 * kh))


def _button(d, dk, kh, s, length):
    """A button head: a low dome on the seat, the shank below."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
    from OCP.gp import gp_Pnt

    r = (dk / 2) ** 2 / (2 * kh) + kh / 2  # the sphere through the head's rim and top
    dome = _bool("common", _cyl(dk / 2, kh), BRepPrimAPI_MakeSphere(gp_Pnt(0, 0, kh - r), r).Shape())
    shape = _bool("fuse", dome, _cyl(d / 2, length + 1e-3, -length))
    from . import robust

    shape = robust.unwrap(robust.merge_faces(shape)[0])
    return _bool("cut", shape, _hex_prism(s, 0.6 * kh + 1, kh - 0.6 * kh))


def _inch_base(size: str) -> str:
    """A name-safe form of an inch size: UNC1_4_20, UNC10_24."""
    return "UNC" + size.replace("#", "").replace("/", "_").replace("-", "_")


def _make_inch(k: str, size: str, length: float, threaded: bool) -> Made:
    if k not in INCH_KINDS:
        raise FastenerError(f"inch sizes are for {', '.join(INCH_KINDS)}; a {k.lower()} is metric only")
    dia, tpi, hd, hh, sock, af, hexh, nuth, wid, wod, wt = (v * IN if i != 1 else v for i, v in enumerate(INCH[size]))
    pitch = IN / tpi
    d = dia
    clear = INCH_CLEAR[size] * IN
    if k in ("CAP", "HEXBOLT", "SET"):
        if length <= 0:
            raise FastenerError("give the screw's length in mm (25.4 per inch), e.g. 25.4")
        shank = _cyl(d / 2, length + 1e-3, -length)
        if k == "CAP":
            head = _bool("cut", _cyl(hd / 2, hh), _hex_prism(sock, 0.5 * hh + 1, 0.5 * hh))
            shape = _bool("fuse", head, shank)
        elif k == "HEXBOLT":
            head = _bool("common", _hex_prism(af, hexh), _chamfer_cone(0.95 * af / 2, hexh, hexh, True))
            shape = _bool("fuse", head, shank)
        else:
            shape = _bool("cut", _cyl(d / 2, length, -length), _hex_prism(sock * 0.6, 0.5 * d + 1, -0.5 * d))
        from . import robust

        shape = robust.unwrap(robust.merge_faces(shape)[0])
        shape = _end_chamfer(shape, -length, d / 2, min(pitch, d / 8))
        if threaded:
            shape = _thread(shape, _round_face(shape, d / 2), d, pitch, length)
        name = {"CAP": "socket head cap screw", "HEXBOLT": "hex head screw", "SET": "socket set screw"}[k]
        inches = f"{length / IN:.4g}"
        return Made(shape, f"{size} x {inches} in {name} (ASME B18)", f"{_inch_base(size)}x{inches}in_{k}".replace(".", "_"),
                    k, d, pitch, length, hd if k == "CAP" else af * 2 / math.sqrt(3) if k == "HEXBOLT" else 0.0,
                    hh if k == "CAP" else hexh if k == "HEXBOLT" else 0.0, clear, inch=True)
    if length:
        raise FastenerError(f"a {k.lower()} has no length; leave it empty")
    if k == "NUT":
        nut = _hex_prism(af, nuth)
        nut = _bool("common", nut, _chamfer_cone(0.95 * af / 2, nuth, nuth, True))
        hole = (d - 2 * th.INT_DEPTH * pitch) if threaded else d
        nut = _bool("cut", nut, _cyl(hole / 2, nuth + 2, -1))
        if threaded:
            nut = _thread(nut, _round_face(nut, hole / 2), d, pitch, 0.0)
        return Made(nut, f"{size} hex nut (ASME B18.2.2)", f"{_inch_base(size)}_NUT",
                    k, d, pitch, inch=True)
    washer = _bool("cut", _cyl(wod / 2, wt), _cyl(wid / 2, wt + 2, -1))
    return Made(washer, f"{size} SAE flat washer", f"{_inch_base(size)}_WASHER",
                k, d, pitch, inch=True)


def hole_for(made: Made, how: str) -> dict:
    """The hole that fits a part in what it goes into, as HOLE arguments: d, depth (0: through), kind, d2, h2,
    and ``sink``: how far below the seat the part's own seat goes (a counterbore). ``how``: CLEAR (a clearance
    hole; a countersunk screw also gets its countersink), TAP (a tap drill as deep as the screw, for a
    threaded part), CBORE (a counterbore for the head) or FIT (the hole a pin, insert or bearing is
    pressed into)."""
    k, how = made.kind, (how or "").strip().upper() or ("FIT" if made.kind in ("DOWEL", "SPRINGPIN", "INSERT",
                                                                                 "BEARING") else "CLEAR")
    if k not in INTO:
        raise FastenerError(f"a {k.lower()} needs no hole; HOLE is for screws, pins, inserts and bearings")
    if how == "FIT":
        if not made.fit_hole:
            raise FastenerError(f"FIT is for pins, inserts and bearings; a screw takes CLEAR, TAP or CBORE")
        return {"d": made.fit_hole, "depth": made.length, "kind": "SIMPLE", "d2": 0.0, "h2": 0.0, "sink": 0.0}
    if k in ("DOWEL", "SPRINGPIN", "INSERT", "BEARING"):
        raise FastenerError(f"a {k.lower()} goes into a FIT hole")
    if how == "TAP":
        tap = made.d - made.pitch
        return {"d": round(tap, 4), "depth": made.length + 2 * made.pitch, "kind": "SIMPLE", "d2": 0.0, "h2": 0.0,
                "sink": 0.0}
    if how == "CBORE":
        if k not in ("CAP", "BUTTON", "HEXBOLT") or not made.head:
            raise FastenerError("CBORE is for screws with a head that stands up (CAP, BUTTON, HEXBOLT)")
        d2 = round(made.head + (1.0 if not made.inch else 0.04 * IN), 4)
        h2 = round(made.head_h + 0.5, 4)
        return {"d": made.clearance, "depth": 0.0, "kind": "CBORE", "d2": d2, "h2": h2, "sink": h2}
    if how != "CLEAR":
        raise FastenerError("the hole is CLEAR, TAP, CBORE or FIT")
    if k == "CSK":
        return {"d": made.clearance, "depth": 0.0, "kind": "CSINK", "d2": round(made.head, 4), "h2": 90.0, "sink": 0.0}
    return {"d": made.clearance, "depth": 0.0, "kind": "SIMPLE", "d2": 0.0, "h2": 0.0, "sink": 0.0}


def bom_group(name: str) -> str | None:
    """The standard part a body named by FASTENER is (its name less the _1, _2 ...), or None."""
    import re

    m = re.fullmatch(r"(.+_(?:" + "|".join(ALL_KINDS) + r"))_\d+", name, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.fullmatch(r"(B\d{3,4}|KEY[\d.x_]+)_\d+", name, flags=re.IGNORECASE)  # bearings B608_1, keys KEY6x6x30_1
    return m.group(1) if m else None


def group_text(base: str) -> str:
    """What a BOM row of standard parts says about them: the standard."""
    tail = base.rsplit("_", 1)[-1].upper()
    if tail in ALL_KINDS:
        return ALL_KINDS[tail]
    if base.upper().startswith("KEY"):
        return ALL_KINDS["KEY"]
    return ALL_KINDS["BEARING"] if base.upper().startswith("B") else "standard part"
