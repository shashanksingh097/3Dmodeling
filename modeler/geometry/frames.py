"""Frames and weldments (PLAN item 25): structural members along straight lines, with mitred or
butted corners, and the cut list.

A member is a profile (square or rectangular tube, round tube or bar, flat bar, angle, channel,
I-beam) swept straight along one segment of a path. Where two segments meet, MITRE cuts both on
the plane halfway between them; BUTT runs the first through and stops the second at its side.
The profile is centred on the path and turned so its height lies along the path's plane normal
(a planar frame), or along Z.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

PROFILES = {
    "SQUARE": ("w x t", "square tube, w wide, wall t (t 0: solid bar)"),
    "RECT": ("w x h x t", "rectangular tube, w wide, h high, wall t (t 0: solid bar)"),
    "ROUND": ("d x t", "round tube, outside diameter d, wall t (t 0: solid bar)"),
    "FLAT": ("w x t", "flat bar, w wide, t thick"),
    "ANGLE": ("w x h x t", "angle (L), legs w and h, t thick"),
    "CHANNEL": ("w x h x t", "channel (U), w across the flanges' backs, h high, t thick"),
    "IBEAM": ("w x h x t", "I-beam, flanges w wide, h high, web and flanges t thick"),
}


class FrameError(Exception):
    pass


@dataclass(frozen=True)
class Member:
    profile: str
    size: tuple  # numbers as given
    p0: tuple  # the path segment
    p1: tuple
    n0: tuple  # the end cut planes' normals (pointing out of the member)
    n1: tuple
    length: float  # longest point to longest point along the axis

    def size_text(self) -> str:
        return "x".join(f"{v:g}" for v in self.size)

    def end_angles(self) -> tuple[float, float]:
        """Each end cut's angle from square, in degrees (0: square, 45: a 90 degree mitre)."""
        d = np.subtract(self.p1, self.p0)
        d = d / np.linalg.norm(d)
        return tuple(round(math.degrees(math.acos(min(1.0, abs(float(np.dot(n, d)))))), 2)
                     for n in (self.n0, self.n1))


def parse_size(profile: str, text: str) -> tuple:
    if profile not in PROFILES:
        raise FrameError(f"no profile {profile}: " + ", ".join(PROFILES))
    want = PROFILES[profile][0].count("x") + 1
    try:
        vals = tuple(float(v) for v in re.split(r"\s*[xX*]\s*", text.strip().strip('"')) if v)
    except ValueError:
        raise FrameError(f"the size of a {profile} is {PROFILES[profile][0]} (like 40x40x3)") from None
    if len(vals) != want:
        raise FrameError(f"the size of a {profile} is {PROFILES[profile][0]} ({PROFILES[profile][1]})")
    if any(v < 0 for v in vals) or any(v <= 0 for v in vals[:-1]) or (profile in ("FLAT", "ANGLE", "CHANNEL",
                                                                                   "IBEAM") and vals[-1] <= 0):
        raise FrameError("sizes must be more than 0 (a wall may be 0 for a solid bar)")
    w = vals[0]
    h = vals[1] if want == 3 else w
    t = vals[-1]
    if profile in ("SQUARE", "RECT", "ROUND") and t > 0 and 2 * t >= min(w, h):
        raise FrameError("the wall is too thick for the size")
    if profile in ("ANGLE", "CHANNEL", "IBEAM") and 2 * t >= min(w, h):
        raise FrameError("the thickness is too big for the size")
    return vals


def outline(profile: str, size: tuple) -> list:
    """The profile as polygons in its own (x across, y up) plane, centred on its box: [outer, hole?]
    or, for ROUND, [("CIRCLE", r), ("CIRCLE", r_in)?]."""
    if profile == "ROUND":
        d, t = size
        return [("CIRCLE", d / 2)] + ([("CIRCLE", d / 2 - t)] if t > 0 else [])
    if profile in ("SQUARE", "RECT"):
        w, h, t = (size[0], size[0], size[1]) if profile == "SQUARE" else size
        out = [_rect(w, h)]
        return out + ([_rect(w - 2 * t, h - 2 * t)] if t > 0 else [])
    if profile == "FLAT":
        w, t = size
        return [_rect(w, t)]
    w, h, t = size
    if profile == "ANGLE":
        pts = [(0, 0), (w, 0), (w, t), (t, t), (t, h), (0, h)]
    elif profile == "CHANNEL":
        pts = [(0, 0), (w, 0), (w, h), (w - t, h), (w - t, t), (t, t), (t, h), (0, h)]
    else:  # IBEAM
        c = w / 2
        pts = [(0, 0), (w, 0), (w, t), (c + t / 2, t), (c + t / 2, h - t), (w, h - t), (w, h), (0, h),
               (0, h - t), (c - t / 2, h - t), (c - t / 2, t), (0, t)]
    return [[(x - w / 2, y - h / 2) for x, y in pts]]


def _rect(w, h):
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def half_reach(profile: str, size: tuple) -> float:
    """The farthest the profile reaches from the path."""
    if profile == "ROUND":
        return size[0] / 2
    w = size[0]
    h = size[1] if len(size) == 3 else (w if profile == "SQUARE" else size[1])
    return math.hypot(w, h) / 2


def path_up(points: list) -> np.ndarray:
    """The direction the profiles' height follows: the path's plane normal if it has one, else Z."""
    p = np.asarray(points, float)
    if len(p) >= 3:
        c = p - p.mean(axis=0)
        _u, s, vt = np.linalg.svd(c, full_matrices=False)
        if s[1] > 1e-9 * max(1.0, s[0]) and s[2] < 1e-7 * max(1.0, s[0]):
            n = vt[2]
            return n if n[np.argmax(np.abs(n))] > 0 else -n
    return np.array([0.0, 0.0, 1.0])


def _frame(d: np.ndarray, up: np.ndarray, turn: float = 0.0):
    """Across (x) and up (y) for a member along d, the profile turned ``turn`` degrees about it."""
    y = up - (up @ d) * d
    if np.linalg.norm(y) < 1e-6:  # the member runs along "up": use X (or Y) instead
        alt = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        y = alt - (alt @ d) * d
    y /= np.linalg.norm(y)
    x = np.cross(y, d)
    if turn:
        c, sn = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        x, y = c * x + sn * y, -sn * x + c * y
    return x, y


def _pnt(q):
    from OCP.gp import gp_Pnt

    return gp_Pnt(*map(float, q))


def _face(polys, origin, x, y):
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakePolygon,
        BRepBuilderAPI_MakeWire,
    )
    from OCP.gp import gp_Ax2, gp_Circ, gp_Dir

    def wire(poly):
        if poly[0] == "CIRCLE":
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge

            n = np.cross(x, y)
            circ = gp_Circ(gp_Ax2(_pnt(origin), gp_Dir(*n), gp_Dir(*x)), poly[1])
            return BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(circ).Edge()).Wire()
        mk = BRepBuilderAPI_MakePolygon()
        for u, v in poly:
            mk.Add(_pnt(origin + u * x + v * y))
        mk.Close()
        return mk.Wire()

    fm = BRepBuilderAPI_MakeFace(wire(polys[0]), True)
    for hole in polys[1:]:
        w = wire(hole)
        w.Reverse()
        fm.Add(w)
    if not fm.IsDone():
        raise FrameError("could not draw the profile")
    from OCP.ShapeFix import ShapeFix_Face

    fix = ShapeFix_Face(fm.Face())
    fix.FixOrientation()
    fix.Perform()
    return fix.Face()


def _prism(face, v):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec

    mk = BRepPrimAPI_MakePrism(face, gp_Vec(*map(float, v)))
    mk.Build()
    return mk.Shape()


def _halfspace_cut(shape, point, normal, size):
    """Keep the part of ``shape`` behind the plane through ``point`` (``normal`` points away)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pln

    n = np.asarray(normal, float)
    pl = gp_Pln(gp_Ax3(_pnt(point), gp_Dir(*n)))
    face = BRepBuilderAPI_MakeFace(pl, -size, size, -size, size).Face()
    box = _prism(face, n * size)
    mk = BRepAlgoAPI_Cut(shape, box)
    mk.Build()
    if not mk.IsDone():
        raise FrameError("could not cut a member's end")
    return mk.Shape()


def members(points: list, closed: bool, profile: str, size: tuple, corner: str = "MITRE", turn: float = 0.0):
    """One (shape, Member) per segment of the path through ``points``."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut

    pts = [np.asarray(p, float) for p in points]
    if closed and np.linalg.norm(pts[0] - pts[-1]) < 1e-9:
        pts = pts[:-1]
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    if closed:
        segs.append((pts[-1], pts[0]))
    if not segs:
        raise FrameError("the path needs at least two points")
    for a, b in segs:
        if np.linalg.norm(b - a) < 1e-9:
            raise FrameError("the path has a segment of no length")
    up = path_up(pts)
    reach = half_reach(profile, size)
    polys = outline(profile, size)
    # what a butted member stops against: the profile's box (a round one: its circle, a hair bigger, since
    # equal round tubes meeting are tangent and the kernel cannot cut that exactly)
    if profile == "ROUND":
        envelope = [("CIRCLE", size[0] / 2 * (1 + 1e-6))]
    else:
        xs = [u for u, _v in outline(profile, size)[0]]
        ys = [v for _u, v in outline(profile, size)[0]]
        envelope = [_rect(max(xs) - min(xs), max(ys) - min(ys))]
    k = len(segs)
    dirs = [(b - a) / np.linalg.norm(b - a) for a, b in segs]
    big = 4 * (max(float(np.linalg.norm(b - a)) for a, b in segs) + 4 * reach)
    out = []
    solids = []
    for i, (a, b) in enumerate(segs):
        d = dirs[i]
        x, y = _frame(d, up, turn)
        prev = i - 1 if (i > 0 or closed) else None
        nxt = i + 1 if (i < k - 1 or closed) else None
        if nxt is not None:
            nxt %= k
        ends = []
        for j, (p, other, sign) in enumerate(((a, prev, -1), (b, nxt, 1))):
            n = sign * d  # square end, pointing out of the member
            if other is not None:
                e = dirs[other]
                cos_turn = float(np.dot(d, e))
                if cos_turn < -1 + 1e-9:
                    raise FrameError("the path turns straight back on itself")
                if corner == "MITRE" and cos_turn < 1 - 1e-9:
                    n = (d + e) if sign > 0 else -(e + d)  # the plane halfway between the two
                    n = n / np.linalg.norm(n)
            ends.append((p, n, other))
        ext = 4 * reach + 1.0
        start = a - d * ext
        face = _face(polys, start, x, y)
        shape = _prism(face, d * (np.linalg.norm(b - a) + 2 * ext))
        for p, n, _other in ends:
            shape = _halfspace_cut(shape, p, n, big)
        solids.append((shape, d, ends, x, y))
    if corner == "BUTT":  # at each corner the ending member runs through; the next one stops at its side
        frames_ = [_frame(dd, up, turn) for dd in dirs]
        fixed = []
        for i, (a, b) in enumerate(segs):
            d = dirs[i]
            x, y = frames_[i]
            ends = list(solids[i][2])
            prev, nxt = ends[0][2], ends[1][2]
            turn_in = prev is not None and float(np.dot(d, dirs[prev])) < 1 - 1e-9
            turn_out = nxt is not None and float(np.dot(d, dirs[nxt])) < 1 - 1e-9
            # the far end: past the joint to the far side of the next member
            stop = _reach_along(envelope, *frames_[nxt], d) if turn_out else 0.0
            # the near end starts just behind the previous member, so cutting it away leaves nothing behind
            # (a round one starts on the joint: its saddle is all in front of it)
            start = a - d * _reach_along(envelope, *frames_[prev], -d) if turn_in and profile != "ROUND" else a
            shape = _prism(_face(polys, start, x, y), b + d * (stop + reach) - start)
            shape = _halfspace_cut(shape, b + d * stop, d, big)
            if not turn_in:
                shape = _halfspace_cut(shape, a, -d, big)
            else:  # the near end: cut away the previous member, run through as above
                pd = dirs[prev]
                pa, pb = segs[prev]
                px, py = frames_[prev]
                pstop = _reach_along(envelope, x, y, pd)
                env = _prism(_face(envelope, pa - pd * (4 * reach + 1.0), px, py),
                             pb + pd * pstop - (pa - pd * (4 * reach + 1.0)))
                mk = BRepAlgoAPI_Cut(shape, env)
                mk.Build()
                shape = mk.Shape()
                side = -(d - float(np.dot(d, pd)) * pd)
                ends[0] = (a, tuple(side / np.linalg.norm(side)), prev)
            ends[1] = (b, tuple(d), nxt)
            fixed.append((shape, d, ends, x, y))
        solids = fixed
    for i, (shape, d, ends, _x, _y) in enumerate(solids):
        a, b = segs[i]
        lo, hi = _extent(shape, a, d)
        rec = Member(profile, tuple(size), tuple(a), tuple(b), tuple(ends[0][1]), tuple(ends[1][1]), hi - lo)
        out.append((shape, rec))
    return out


def _reach_along(envelope, x, y, d) -> float:
    """How far a member's envelope (profile in its frame x, y) reaches from its axis along d."""
    if envelope[0][0] == "CIRCLE":
        r = envelope[0][1]
        return r * math.hypot(float(np.dot(x, d)), float(np.dot(y, d)))
    return max(float(np.dot(u * x + v * y, d)) for u, v in envelope[0])


def _extent(shape, a, d) -> tuple[float, float]:
    """The shape's range along the line a + s d (exact, also for curved ends)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax3, gp_Dir, gp_Trsf

    x = np.cross(d, [0.0, 0.0, 1.0])
    if np.linalg.norm(x) < 1e-6:
        x = np.cross(d, [1.0, 0.0, 0.0])
    tr = gp_Trsf()
    tr.SetTransformation(gp_Ax3(_pnt(a), gp_Dir(*d), gp_Dir(*x)))  # world -> the line's frame
    moved = BRepBuilderAPI_Transform(shape, tr, True).Shape()
    box = Bnd_Box()
    (getattr(BRepBndLib, "AddOptimal_s", None) or BRepBndLib.AddOptimal)(moved, box, False, False)
    return box.CornerMin().Z(), box.CornerMax().Z()
