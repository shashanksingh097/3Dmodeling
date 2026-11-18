"""2.5D milling paths from a solid's flat faces, and G-code for them.

The tool is a flat end mill along Z, cutting down from the top of the part
(its highest point) in steps. All work is in the part's own coordinates, so
set the machine's zero where the part's zero is.

* FACE: zig-zag passes over a flat face (its outline grown by the tool
  radius), one level, to make it flat and at height.
* POCKET: clears down to a flat floor facing up, inside its outline and
  around its islands (the floor face's holes), in rings offset by the
  stepover; the last ring runs along the wall.
* OUTLINE: runs around a flat face's outline (facing up or down) (and inside its holes) at the
  tool radius outside the material, down to the part's bottom, to cut the
  part out of a plate.

Rings come from OCCT's 2D offset of the face (BRepOffsetAPI_MakeOffset);
curves are cut as short straight moves (G1) within ``TOL``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

TOL = 0.01  # chord error of the straight moves along curves, mm
OPS = ("FACE", "POCKET", "OUTLINE")


class MillError(ValueError):
    pass


@dataclass
class Path:
    """Cutting moves in order: each item is one run of points cut without lifting the tool."""

    runs: list = field(default_factory=list)  # [(n, 3) arrays]
    safe: float = 0.0  # height the tool lifts to between runs
    notes: list = field(default_factory=list)

    def cut_length(self) -> float:
        return float(sum(np.linalg.norm(np.diff(r, axis=0), axis=1).sum() for r in self.runs))

    def plunge(self) -> float:
        return float(sum(max(self.safe - r[0, 2], 0.0) for r in self.runs))

    def bounds(self):
        allp = np.concatenate(self.runs)
        return allp.min(axis=0), allp.max(axis=0)


def _api(cls, name):
    return getattr(cls, name + "_s", None) or getattr(cls, name)


def flat_up(face, either: bool = False) -> float:
    """The height of a flat face facing +Z (its outward normal up; either: or down); else an error."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType
    from OCP.TopAbs import TopAbs_REVERSED

    s = BRepAdaptor_Surface(face)
    if s.GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
        raise MillError("it is not flat")
    pl = s.Plane()
    d = pl.Axis().Direction()
    n = np.array([d.X(), d.Y(), d.Z()])
    if face.Orientation() == TopAbs_REVERSED:
        n = -n
    if (abs(n[2]) if either else n[2]) < 1 - 1e-7:
        raise MillError("it does not face straight up (+Z): the tool comes down along Z")
    return float(pl.Location().Z())


def wire_points(wire, tol: float = TOL) -> np.ndarray:
    """The points along a wire, in order, closed (last point = first) when the wire is."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.TopAbs import TopAbs_REVERSED

    pts: list = []
    ex = BRepTools_WireExplorer(wire)
    while ex.More():
        e = ex.Current()
        ex.Next()
        if BRep_Tool.Degenerated_s(e):
            continue
        c = BRepAdaptor_Curve(e)
        d = GCPnts_QuasiUniformDeflection(c, tol)
        if d.IsDone() and d.NbPoints() >= 2:
            q = [d.Value(i) for i in range(1, d.NbPoints() + 1)]
        else:
            q = [c.Value(c.FirstParameter()), c.Value(c.LastParameter())]
        seg = [(v.X(), v.Y(), v.Z()) for v in q]
        if e.Orientation() == TopAbs_REVERSED:
            seg.reverse()
        if pts and np.allclose(pts[-1], seg[0], atol=1e-6):
            seg = seg[1:]
        pts += seg
    return np.array(pts, float)


def _wires(shape) -> list:
    from OCP.TopAbs import TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    out = []
    ex = TopExp_Explorer(shape, TopAbs_WIRE)
    while ex.More():
        out.append(_api(TopoDS, "Wire")(ex.Current()))
        ex.Next()
    return out


def offset_rings(face, dist: float) -> list[np.ndarray]:
    """The face's boundary moved ``dist`` into it (negative: out of it), as closed point runs."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset
    from OCP.GeomAbs import GeomAbs_JoinType

    off = BRepOffsetAPI_MakeOffset(face, GeomAbs_JoinType.GeomAbs_Arc)
    try:
        off.Perform(-dist)
    except Exception:  # noqa: BLE001  (OCCT raises when the face vanishes)
        return []
    if not off.IsDone():
        return []
    return [r for r in (wire_points(w) for w in _wires(off.Shape())) if len(r) >= 3]


def levels(top: float, bottom: float, step: float) -> list[float]:
    """Heights from just under top down to bottom in equal steps no bigger than ``step``."""
    depth = top - bottom
    if depth <= 1e-9:
        return [bottom]
    n = max(1, math.ceil(depth / step - 1e-9))
    return [top - depth * (k + 1) / n for k in range(n)]


def _at(ring: np.ndarray, z: float) -> np.ndarray:
    r = ring.copy()
    r[:, 2] = z
    return r


def pocket(face, top: float, tool: float, step_down: float, step_over: float) -> Path:
    """Rings inside the floor face, centre first, at each level from top down to the floor."""
    floor = flat_up(face)
    if floor >= top - 1e-9:
        raise MillError("its floor is at the top of the part: nothing to clear (use FACE)")
    r = tool / 2
    rings: list[list[np.ndarray]] = []
    d = r
    while True:
        got = offset_rings(face, d)
        if not got:
            break
        rings.append(got)
        d += step_over
        if len(rings) > 10_000:
            raise MillError("too many rings: the stepover is too small")
    if not rings:
        raise MillError(f"the tool ({tool:g} across) does not fit in it")
    path = Path(safe=top + max(2.0, r))
    for z in levels(top, floor, step_down):
        for ring_set in reversed(rings):  # from the middle out to the wall
            for ring in ring_set:
                path.runs.append(_at(ring, z))
    return path


def outline(face, top: float, bottom: float, tool: float, step_down: float) -> Path:
    """Around the face's outline (and inside its holes), the tool's edge on the line, down to bottom."""
    flat_up(face, either=True)
    rings = offset_rings(face, -tool / 2)
    if not rings:
        raise MillError("could not offset its outline")
    path = Path(safe=top + max(2.0, tool / 2))
    small = len(_wires(face)) - len(rings)
    if small > 0:
        path.notes.append(f"{small} hole{'s are' if small > 1 else ' is'} smaller than the tool and left uncut")
    for z in levels(top, bottom, step_down):
        for ring in rings:
            path.runs.append(_at(ring, z))
    return path


def facing(face, top: float, tool: float, step_down: float, step_over: float) -> Path:
    """Zig-zag passes along X over the face's outline grown by the tool radius, from top down to the face."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    z0 = flat_up(face)
    bb = Bnd_Box()
    _api(BRepBndLib, "AddOptimal")(face, bb, False, False)
    a, c = bb.CornerMin(), bb.CornerMax()
    x0, y0, x1, y1 = a.X(), a.Y(), c.X(), c.Y()
    r = tool / 2
    x0, x1 = x0 - r, x1 + r
    ys = list(np.arange(y0, y1 + 1e-9, step_over)) if y1 - y0 > 1e-9 else [y0]
    if ys[-1] < y1 - 1e-9:
        ys.append(y1)
    path = Path(safe=max(top, z0) + max(2.0, r))
    for z in levels(max(top, z0), z0, step_down):
        pts = []
        for k, y in enumerate(ys):
            a, b = (x0, x1) if k % 2 == 0 else (x1, x0)
            pts += [(a, y, z), (b, y, z)]
        path.runs.append(np.array(pts, float))
    return path


def gcode(path: Path, feed: float, speed: float, title: str = "") -> str:
    """G-code (mm, absolute): rapid to the safe height between runs, plunge at a third of the feed."""
    lines = ["%", f"(made by 3Dmodeling{': ' + title if title else ''})", "G21 G90 G17 G94",
             f"S{speed:.0f} M3", f"G0 Z{path.safe:.3f}"]
    for run in path.runs:
        x, y, z = run[0]
        lines.append(f"G0 X{x:.3f} Y{y:.3f}")
        lines.append(f"G1 Z{z:.3f} F{feed / 3:.0f}")
        lines.append(f"F{feed:.0f}")
        for x, y, z in run[1:]:
            lines.append(f"G1 X{x:.3f} Y{y:.3f} Z{z:.3f}")
        lines.append(f"G0 Z{path.safe:.3f}")
    lines += ["M5", "M30", "%"]
    return "\n".join(lines) + "\n"


def minutes(path: Path, feed: float) -> float:
    """Cutting time at the feed (plunges at a third of it), without rapids."""
    return (path.cut_length() + 3 * path.plunge()) / max(feed, 1e-9)


def shape(path: Path):
    """The path as a compound of polylines, for the view (cuts only; rapids are left out)."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
    from OCP.gp import gp_Pnt
    from OCP.TopoDS import TopoDS_Compound

    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    for run in path.runs:
        poly = BRepBuilderAPI_MakePolygon()
        last = None
        for q in run:
            if last is not None and np.linalg.norm(q - last) < 1e-9:
                continue
            poly.Add(gp_Pnt(*map(float, q)))
            last = q
        if poly.IsDone():
            b.Add(comp, poly.Wire())
    return comp
