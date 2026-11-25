"""Sheet metal found in a solid that was not made with SHEET (PLAN item 71).

An imported bent part is a solid of faces. To unfold it, this finds what SHEET
and FLANGE would have recorded:

* the base: the biggest flat face, its plate lying behind it, and the
  thickness, the gap to the parallel face on the plate's other side;
* each bend off the base: a pair of cylinder faces on one axis whose radii
  differ by the thickness, the bend line where it leaves the base, its angle,
  inside radius, direction (up or down) and the length of its wall.

The result is a ``sheetmetal.Sheet`` with its flanges, so UNFOLD, SHEETINFO
and FLANGE work on the part. A check makes sure the record explains the whole
part: the flat pattern's area times the thickness must match the part's
volume (with the neutral line in the middle that holds exactly for walls of
one thickness), so a part with walls of several thicknesses, or bends off
other bends, is refused with the reason instead of being unfolded wrongly.
"""

from __future__ import annotations

import math

import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE

from . import recognize as rc
from . import robust
from . import sheetmetal as smt

VOLUME_TOL = 0.005  # the flat pattern explains the part's volume to within this share


class NotSheet(Exception):
    pass


def _v(p) -> np.ndarray:
    return np.array([p.X(), p.Y(), p.Z()], float)


def _area(face) -> float:
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, g)
    return g.Mass()


def _centre(face) -> np.ndarray:
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, g)
    return _v(g.CentreOfMass())


def _planes(shape) -> list[tuple]:
    """(face, point on it, outward unit normal, area) for every flat face."""
    out = []
    faces = rc.shape_map(shape, TopAbs_FACE)
    for i in range(1, faces.Extent() + 1):
        f = rc.as_face(faces.FindKey(i))
        if BRepAdaptor_Surface(f).GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
            continue
        p, n = rc.face_normal_at_middle(f)
        out.append((f, np.asarray(p, float), np.asarray(n, float), _area(f)))
    return out


def _cylinders(shape) -> list[dict]:
    out = []
    faces = rc.shape_map(shape, TopAbs_FACE)
    for i in range(1, faces.Extent() + 1):
        f = rc.as_face(faces.FindKey(i))
        s = BRepAdaptor_Surface(f)
        if s.GetType() != GeomAbs_SurfaceType.GeomAbs_Cylinder:
            continue
        cyl = s.Cylinder()
        ax = cyl.Axis()
        u0, u1, _v0, _v1 = rc.BRepTools.UVBounds_s(f)
        out.append({"face": f, "loc": _v(ax.Location()), "dir": _v(ax.Direction()), "r": cyl.Radius(),
                    "span": u1 - u0, "index": i})
    return out


def _thickness(planes, base) -> float:
    """The gap from the base face to the nearest parallel face looking the other way behind it."""
    _f0, p0, n0, _a0 = base
    best = None
    for f, p, n, _a in planes:
        if f.IsSame(base[0]) or n @ n0 > -1 + 1e-7:
            continue
        d = (p0 - p) @ n0  # how far behind the base face (into the material)
        if d > 1e-9 and (best is None or d < best):
            best = d
    if best is None:
        raise NotSheet("no face parallel to the biggest flat face on its other side, so there is no thickness")
    return float(best)


def detect(shape, k: float = smt.K_FACTOR) -> smt.Sheet:
    """The sheet metal record of a solid made of a flat base and flanges bent off it."""
    if not robust.solids(shape):
        raise NotSheet("it is not a solid")
    planes = _planes(shape)
    if not planes:
        raise NotSheet("it has no flat faces")
    base = max(planes, key=lambda x: x[3])
    t = _thickness(planes, base)
    f0, p0, nf, _a = base
    n = -nf  # into the material: the plate lies between h = 0 and h = t
    x = np.cross(n, [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0])
    x /= np.linalg.norm(x)
    y = np.cross(n, x)
    sheet = smt.Sheet(tuple(p0), tuple(x), tuple(y), tuple(n), t, t, k)
    tol = 1e-6 * max(1.0, t) + 1e-7
    base_faces = [pl for pl in planes if abs(abs(pl[2] @ n) - 1) < 1e-7
                  and (abs(sheet.local(pl[1])[2]) < tol or abs(sheet.local(pl[1])[2] - t) < tol)]
    plate_mid = np.mean([pl[1] for pl in base_faces], axis=0)
    flanges = []
    radii = []
    cyls = _cylinders(shape)
    used: set[int] = set()
    for c in cyls:
        if c["index"] in used or abs(c["dir"] @ n) > 1e-7:
            continue  # a hole's wall, or a bend not across the base
        partner = None
        for d in cyls:
            if d is c or d["index"] in used or abs(abs(d["dir"] @ c["dir"]) - 1) > 1e-7:
                continue
            off = d["loc"] - c["loc"]
            off = off - (off @ c["dir"]) * c["dir"]
            if np.linalg.norm(off) < tol and abs(abs(d["r"] - c["r"]) - t) < tol:
                partner = d
                break
        if partner is None:
            continue
        inner, outer = (c, partner) if c["r"] < partner["r"] else (partner, c)
        h_axis = sheet.local(inner["loc"])[2]
        if abs(h_axis - (t + inner["r"])) < tol * 10:
            up = True
        elif abs(h_axis + inner["r"]) < tol * 10:
            up = False
        else:
            continue  # a bend off another bend or off a wall: not across the base
        used |= {inner["index"], outer["index"]}
        fl = _flange(sheet, inner, outer, up, plate_mid, shape)
        flanges.append(fl)
        radii.append(inner["r"])
    sheet = smt.Sheet(sheet.origin, sheet.x, sheet.y, sheet.n, t, (min(radii) if radii else t), k,
                      tuple(flanges))
    _check(sheet, shape)
    return sheet


def _straight_edges(face) -> list[tuple[np.ndarray, np.ndarray]]:
    out = []
    edges = rc.shape_map(face, TopAbs_EDGE)
    for i in range(1, edges.Extent() + 1):
        c = BRepAdaptor_Curve(rc.as_edge(edges.FindKey(i)))
        if c.GetType() == GeomAbs_CurveType.GeomAbs_Line:
            out.append((_v(c.Value(c.FirstParameter())), _v(c.Value(c.LastParameter()))))
    return out


def _flange(sheet: smt.Sheet, inner: dict, outer: dict, up: bool, plate_mid, shape) -> smt.Flange:
    t = sheet.t
    n = np.asarray(sheet.n, float)
    # the bend leaves the base along the straight edge of its inner face, which touches the
    # plate's top (an up bend, h = t) or its bottom (a down bend, h = 0)
    want_h = t if up else 0.0
    face = inner["face"]
    tol = 1e-6 * max(1.0, t) + 1e-6
    line = None
    for a, b in _straight_edges(face):
        if abs(sheet.local(a)[2] - want_h) < tol and abs(sheet.local(b)[2] - want_h) < tol:
            line = (a, b)
            break
    if line is None:
        raise NotSheet("a bend does not meet the base plate along a straight line")
    a, b = line
    a0, b0 = a - want_h * n, b - want_h * n
    along = (b0 - a0) / np.linalg.norm(b0 - a0)
    out = np.cross(along, n)
    out /= np.linalg.norm(out)
    mid = (a0 + b0) / 2
    if (plate_mid - mid) @ out > 0:  # out points away from the plate
        out = -out
    # order a, b so that _outward(a, b) is this out
    if np.linalg.norm(np.cross(b0 - a0, n) / np.linalg.norm(b0 - a0) - out) > 1e-6:
        a0, b0 = b0, a0
    angle = math.degrees(inner["span"])
    fl = smt.Flange(tuple(a0), tuple(b0), tuple(out), up, angle, 0.0, inner["r"])
    # the wall's length: how far its faces reach past the end of the bend
    w0, d3, _al = smt.bent_frame(sheet, fl)
    reach = 0.0
    for pa, pb in _straight_edges_all(shape):
        for q in (pa, pb):
            rel = q - w0
            e = rel @ ((b0 - a0) / np.linalg.norm(b0 - a0))
            if -tol <= e <= np.linalg.norm(b0 - a0) + tol and abs(rel @ np.cross(d3, _al)) <= t + tol:
                reach = max(reach, float(rel @ d3))
    return smt.Flange(tuple(a0), tuple(b0), tuple(out), up, angle, max(0.0, reach), inner["r"])


def _straight_edges_all(shape):
    return _straight_edges(shape)


def _check(sheet: smt.Sheet, shape) -> None:
    """The record must explain the whole part (see the module note)."""
    import dataclasses

    half = dataclasses.replace(sheet, k=0.5)
    try:
        flat = smt.flat_pattern(half, shape)
    except smt.SheetError as exc:
        raise NotSheet(str(exc)) from None
    expect = _area(flat.face) * sheet.t
    vol = robust.volume(shape)
    if vol <= 0 or abs(expect - vol) > VOLUME_TOL * vol:
        raise NotSheet(f"the flat base and {len(sheet.flanges)} bend{'s' if len(sheet.flanges) != 1 else ''} found "
                       f"explain {expect / vol:.0%} of its volume: the walls are not all {sheet.t:g} thick, or "
                       "some bends start from other bends or walls (only flanges bent straight off the base "
                       "can be found)")
