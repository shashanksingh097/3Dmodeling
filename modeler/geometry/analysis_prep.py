"""Getting parts ready for analysis (PLAN items 80-82): geometry only, for the separate meshing
and solver app. Nothing here meshes or solves.

* ``midsurface``: the middle surface of a thin part, with the thickness found for each face.
  Faces of the part are paired with the face straight across the material (a ray from the face's
  middle, inwards); pairs closer than their size are the two sides of a wall. One side is chosen
  by walking from face to face, and is pulled into the wall by half the thickness. With one
  thickness the side is offset as one sheet, so walls meet at their corners; with several, each
  face is offset on its own and sewn.
* ``beams``: centre lines and profile sizes of long members, for beam models.
* ``fluid_volume``: the inside of a pipe, valve or housing up to its openings, as solids.
* ``enclosure``: a box, cylinder or sphere round the model with the model cut out.
* ``share``: neighbouring parts split where they touch so they use the same face there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Sewing
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepGProp import BRepGProp, BRepGProp_Face
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt, gp_Pnt2d, gp_Vec
from OCP.GProp import GProp_GProps
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_IN, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound

from . import robust
from .recognize import _static

_face, _wire, _vertex, _edge = (_static(TopoDS, k) for k in ("Face", "Wire", "Vertex", "Edge"))

P3 = tuple[float, float, float]


class PrepError(Exception):
    pass


def _explore(shape, kind) -> list:
    out, e = [], TopExp_Explorer(shape, kind)
    while e.More():
        out.append(e.Current())
        e.Next()
    return out


def _index(items, x) -> int:
    for i, y in enumerate(items):
        if y.IsSame(x):
            return i
    return -1


def _compound(shapes):
    b, c = BRep_Builder(), TopoDS_Compound()
    b.MakeCompound(c)
    for s in shapes:
        b.Add(c, s)
    return c


def area(shape) -> float:
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, g)
    return g.Mass()


def _p(v) -> P3:
    return (v.X(), v.Y(), v.Z())


def inside_point(face) -> tuple[gp_Pnt, gp_Vec] | None:
    """A point well inside a face and the face's outward normal there (it follows the face's
    orientation, so on a solid it points out of the material)."""
    f = _face(face)
    u0, u1, v0, v1 = BRepTools.UVBounds_s(f)
    cls = BRepClass_FaceClassifier()
    gf = BRepGProp_Face(f)
    tol = BRep_Tool.Tolerance_s(f)
    tries = [(0.5, 0.5)] + [(a, b) for a in (0.3, 0.7, 0.15, 0.85, 0.5) for b in (0.3, 0.7, 0.15, 0.85, 0.5)]
    for a, b in tries:
        u, v = u0 + a * (u1 - u0), v0 + b * (v1 - v0)
        cls.Perform(f, gp_Pnt2d(u, v), tol)
        if cls.State() != TopAbs_IN:
            continue
        p, n = gp_Pnt(), gp_Vec()
        gf.Normal(u, v, p, n)
        if n.Magnitude() < 1e-12:
            continue
        return p, n.Normalized()
    return None


@dataclass
class Wall:
    face: int  # index of the face on the chosen side
    other: int  # the face across the wall
    thickness: float


@dataclass
class Mid:
    shape: object  # the middle surface (a shell or a compound of faces)
    walls: list[Wall]
    rims: list[int]  # faces of the edges of the walls (left out)
    unpaired: list[int]  # faces with nothing across them within reach (thick parts)
    joined: bool  # one sheet offset as a whole (corners meet), not faces offset one by one
    faces: list = field(default_factory=list)  # (mid face, thickness) for each face of ``shape``
    closed: int = 0  # gaps closed where the thickness changes (strips added between middle faces)


def across(shape, faces) -> list[tuple[int, float] | None]:
    """For each face: the face straight across the material from its middle, and how far."""
    hit = IntCurvesFace_ShapeIntersector()
    hit.Load(shape, 1e-7)
    out = []
    for f in faces:
        got = inside_point(f)
        if got is None:
            out.append(None)
            continue
        p, n = got
        d = gp_Dir(-n.X(), -n.Y(), -n.Z())
        hit.Perform(gp_Lin(p, d), 1e-7, 1e12)
        best = None
        if hit.IsDone():
            for k in range(1, hit.NbPnt() + 1):
                w = hit.WParameter(k)
                if w <= 1e-7:
                    continue
                if best is None or w < best[0]:
                    best = (w, hit.Face(k), hit.UParameter(k), hit.VParameter(k))
        if best is None:
            out.append(None)
            continue
        w, g, u, v = best
        j = _index(faces, g)
        q, m = gp_Pnt(), gp_Vec()
        BRepGProp_Face(_face(g)).Normal(u, v, q, m)
        # across a wall the far face looks the same way the ray goes (out of the material on its side)
        if j < 0 or m.Magnitude() < 1e-12 or m.Normalized().Dot(gp_Vec(d)) < 0.9:
            out.append(None)
            continue
        out.append((j, w))
    return out


def walls(shape, max_t: float = 0.0) -> tuple[list[Wall], list[int], list[int], list]:
    """Pair the faces of a thin solid across its walls and pick one side of each wall.
    Returns (walls, rims, unpaired, faces)."""
    faces = _explore(shape, TopAbs_FACE)
    if not faces:
        raise PrepError("it has no faces")
    acr = across(shape, faces)
    areas = [area(f) for f in faces]
    pair: dict[int, tuple[int, float]] = {}
    for i, a in enumerate(acr):
        if a is None:
            continue
        j, t = a
        size = math.sqrt(max(min(areas[i], areas[j]), 1e-30))
        if (max_t > 0 and t > max_t * (1 + 1e-6)) or (max_t <= 0 and t > 0.35 * size):
            continue  # a thick part, or the ray went along a wall to its far end
        pair[i] = (j, t)
    # neighbours across shared edges
    edges_of = [[e for e in _explore(f, TopAbs_EDGE)] for f in faces]
    near: dict[int, set[int]] = {i: set() for i in range(len(faces))}
    for i in range(len(faces)):
        for j in range(i + 1, len(faces)):
            if any(e.IsSame(x) for e in edges_of[i] for x in edges_of[j]):
                near[i].add(j)
                near[j].add(i)
    back: dict[int, list[int]] = {}
    for i, (j, _) in pair.items():
        back.setdefault(j, []).append(i)
    side: dict[int, int] = {}
    order = sorted(pair, key=lambda i: -areas[i])
    chosen: list[int] = []
    for start in order:
        if start in side:
            continue
        side[start] = 0
        group, todo = [start], [start]
        while todo:
            i = todo.pop()
            j = pair[i][0]
            if j in pair and j not in side:
                side[j] = 1 - side[i]
                group.append(j)
                todo.append(j)
            # faces whose ray lands on this one are across from it too (the two tops of a stepped
            # plate both land on its one bottom)
            for k in back.get(i, ()):
                if k not in side:
                    side[k] = 1 - side[i]
                    group.append(k)
                    todo.append(k)
            for k in near[i]:
                if k in pair and k not in side and k != j:
                    side[k] = side[i]
                    group.append(k)
                    todo.append(k)
        # of a wall's two sides, the one cut into more faces follows the changes of thickness
        # (a stepped plate: the two top faces, not the one flat bottom); else the larger side
        s0 = [i for i in group if side[i] == 0]
        s1 = [i for i in group if side[i] == 1]
        chosen += s1 if len(s1) > len(s0) else s0
    # a wall left with neither side chosen (the plate beside the foot of a rib in a T, whose
    # bottom face looks up into the rib): its own side is added
    for i in sorted(pair, key=lambda i: -areas[i]):
        mine = set(chosen)
        if i not in mine and pair[i][0] not in mine and not any(pair[c][0] == i for c in mine):
            chosen.append(i)
    chosen.sort(key=lambda i: -areas[i])
    out = []
    for i in chosen:
        j, t = pair[i]
        if j in pair and pair[j][0] == i and abs(pair[j][1] - t) > 0.05 * t:  # tapered: the mean of both ways
            t = (t + pair[j][1]) / 2
        out.append(Wall(i, j, t))
    taken = {w.face for w in out} | {w.other for w in out}
    rims = [i for i in range(len(faces)) if i not in taken and any(k in taken for k in near[i])]
    unpaired = [i for i in range(len(faces)) if i not in taken and i not in rims]
    return out, rims, unpaired, faces


def midsurface(shape, max_t: float = 0.0) -> Mid:
    from OCP.BRepOffset import BRepOffset_Mode
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
    from OCP.GeomAbs import GeomAbs_JoinType

    if not robust.solids(shape):
        raise PrepError("it is not a solid")
    ws, rims, unpaired, faces = walls(shape, max_t)
    if not ws:
        raise PrepError("no thin walls found (no face has another close across the material"
                        + (f" within {max_t:g}" if max_t > 0 else "") + ")")
    ts = [w.thickness for w in ws]
    same = max(ts) - min(ts) <= 1e-3 * max(ts)
    joined = False
    result = None
    closed = 0
    if same:
        sew = BRepBuilderAPI_Sewing(1e-6 * max(1.0, robust.diagonal(shape)))
        for w in ws:
            sew.Add(faces[w.face])
        sew.Perform()
        sheet = sew.SewedShape()
        mo = BRepOffsetAPI_MakeOffsetShape()
        try:
            mo.PerformByJoin(sheet, -ts[0] / 2, 1e-6, BRepOffset_Mode.BRepOffset_Skin, False, False,
                             GeomAbs_JoinType.GeomAbs_Intersection)
            if mo.IsDone() and not robust.is_empty(mo.Shape()) and robust.is_valid(mo.Shape()):
                result = mo.Shape()
                joined = True
        except Exception:  # noqa: BLE001 - the kernel refuses some sheets; offset face by face then
            result = None
    per = []
    if result is None:
        pieces = []  # (face, thickness)
        for w in ws:
            mo = BRepOffsetAPI_MakeOffsetShape()
            try:
                mo.PerformByJoin(faces[w.face], -w.thickness / 2, 1e-6, BRepOffset_Mode.BRepOffset_Skin, False,
                                 False, GeomAbs_JoinType.GeomAbs_Arc)
            except Exception:  # noqa: BLE001, S112 - a face the kernel cannot offset is left out
                continue
            if mo.IsDone() and not robust.is_empty(mo.Shape()):
                pieces.extend((_face(x), w.thickness) for x in _explore(mo.Shape(), TopAbs_FACE))
        if not pieces:
            raise PrepError("the walls could not be offset to their middle")
        kept, closed = meet([f for f, _ in pieces], [t for _, t in pieces], max(ts))
        sew = BRepBuilderAPI_Sewing(1e-3 * min(ts))
        for f, _ in kept:
            sew.Add(f)
        sew.Perform()
        result = sew.SewedShape()
        for f, t in kept:
            g = sew.Modified(f) if sew.IsModified(f) else f
            per.append((g, t))
        mids = _explore(result, TopAbs_FACE)
        per = [(mf, next((t for g, t in per if g.IsSame(mf)), _nearest_t(mf, ws, faces, ts))) for mf in mids]
    else:
        per = [(mf, ts[0]) for mf in _explore(result, TopAbs_FACE)]
    return Mid(robust.unwrap(result), ws, rims, unpaired, joined, per, closed)


def _nearest_t(mf, ws, faces, ts) -> float:
    """The thickness of a middle face: the wall whose side lies half that thickness away."""
    got = inside_point(mf)
    if got is None:
        return ts[0]
    best = None
    for w in ws:
        d = _face_distance(faces[w.face], got[0])
        if best is None or abs(d - w.thickness / 2) < best[0]:
            best = (abs(d - w.thickness / 2), w.thickness)
    return best[1] if best else ts[0]


def meet(pieces: list, ts: list[float], reach: float) -> tuple[list, int]:
    """Make middle faces offset one by one meet: close the gaps between them (``close_gaps``),
    split them where they cross, and drop the short ends that stick out past the meeting line
    (a narrow piece joined to the rest along one edge only). Returns ([(face, thickness)], gaps
    closed)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_BuilderAlgo
    from OCP.TopExp import TopExp

    strips = close_gaps(pieces, reach)
    src = list(zip(pieces, ts)) + [(f, ts[i]) for f, i in strips]
    gf = BRepAlgoAPI_BuilderAlgo()
    gf.SetArguments(_list([f for f, _ in src]))
    gf.SetFuzzyValue(1e-4 * min(ts))
    gf.SetRunParallel(False)
    gf.Build()
    if not gf.IsDone():
        return src, len(strips)
    out = []
    for f, t in src:
        if gf.IsDeleted(f):
            continue
        imgs = list(gf.Modified(f)) or [f]
        out.extend((_face(g), t) for g in imgs)
    # short ends past a meeting line: narrow, joined to the rest along one edge only
    comp = _compound([f for f, _ in out])
    emap = robust._EdgeFaceMap()
    TopExp.MapShapesAndAncestors_s(comp, TopAbs_EDGE, TopAbs_FACE, emap)
    keep = []
    for f, t in out:
        shared, length = 0, 0.0
        for e in _explore(f, TopAbs_EDGE):
            k = emap.FindIndex(e)
            if k and emap.FindFromIndex(k).Size() > 1:
                shared += 1
                length += _length(e)
        if shared == 1 and length > 0 and area(f) / length < 0.75 * reach:
            continue
        keep.append((f, t))
    return keep, len(strips)


def _length(edge) -> float:
    g = GProp_GProps()
    BRepGProp.LinearProperties_s(edge, g)
    return g.Mass()


def _plane_of(face):
    s = BRepAdaptor_Surface(face)
    if s.GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
        return None
    pl = s.Plane()
    n, o = pl.Axis().Direction(), pl.Location()
    return np.array([o.X(), o.Y(), o.Z()]), np.array([n.X(), n.Y(), n.Z()])


def _line_ends(edge):
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_CurveType

    c = BRepAdaptor_Curve(edge)
    if c.GetType() != GeomAbs_CurveType.GeomAbs_Line:
        return None
    a, b = c.Value(c.FirstParameter()), c.Value(c.LastParameter())
    return np.array([a.X(), a.Y(), a.Z()]), np.array([b.X(), b.Y(), b.Z()])


def _on_face(face, x: np.ndarray, tol: float) -> bool:
    return _face_distance(face, gp_Pnt(*map(float, x))) <= tol


def _quad(pts) -> object | None:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon

    poly = BRepBuilderAPI_MakePolygon()
    for q in pts:
        poly.Add(gp_Pnt(*map(float, q)))
    poly.Close()
    if not poly.IsDone():
        return None
    mk = BRepBuilderAPI_MakeFace(poly.Wire(), True)
    return mk.Face() if mk.IsDone() else None


def _off(face, a, b, n, reach) -> np.ndarray:
    """The way off a flat face across its straight edge a-b, in the face's plane."""
    d = (b - a) / np.linalg.norm(b - a)
    out = np.cross(d, n)
    if _on_face(face, (a + b) / 2 + out * (1e-3 * reach), 1e-6 * max(1.0, reach)):
        out = -out
    return out


def close_gaps(pieces: list, reach: float) -> list:
    """Where the thickness changes, middle faces offset one by one stop short of each other. For
    flat faces this adds the strips that close the gaps: an edge of one face is carried on in its
    own plane until it meets the plane of a neighbour (walls at an angle: an L or a T), or, when
    the two faces are parallel (a stepped plate), a strip joins the two facing edges straight
    across. Only gaps narrower than ``reach`` (the largest wall thickness) are closed. Returns
    [(strip, index of the piece it carries on)]."""
    planes = [_plane_of(f) for f in pieces]
    tol = 1e-6 * max(1.0, reach)
    strips = []
    edges = []  # (piece, a, b) for each straight boundary edge
    for i, f in enumerate(pieces):
        if planes[i] is None:
            continue
        for e in _explore(f, TopAbs_EDGE):
            ab = _line_ends(_edge(e))
            if ab is not None and np.linalg.norm(ab[1] - ab[0]) > tol:
                edges.append((i, ab[0], ab[1]))
    # an edge already lying on another piece is joined there
    def touching(i, a, b):
        m = (a + b) / 2
        return any(k != i and _on_face(pieces[k], m, 10 * tol) for k in range(len(pieces)))

    free = [(i, a, b) for i, a, b in edges if not touching(i, a, b)]
    bridged: set[tuple[int, int]] = set()
    for i, a, b in free:
        o_i, n_i = planes[i]
        d = (b - a) / np.linalg.norm(b - a)
        out = _off(pieces[i], a, b, n_i, reach)
        m = (a + b) / 2
        best = None
        for j in range(len(pieces)):
            if j == i or planes[j] is None:
                continue
            o_j, n_j = planes[j]
            k = float(np.dot(n_j, out))
            if abs(float(np.dot(n_i, n_j))) > 1 - 1e-6:
                continue  # parallel: bridged below
            if abs(k) < 1e-6:
                continue
            sa = -float(np.dot(n_j, a - o_j)) / k
            sb = -float(np.dot(n_j, b - o_j)) / k
            if not (tol < sa <= reach and tol < sb <= reach):
                continue
            a2, b2 = a + out * sa, b + out * sb
            # the strip has to end on the neighbour or on its own carrying on towards it
            if not (_face_distance(pieces[j], gp_Pnt(*map(float, (a2 + b2) / 2))) <= reach):
                continue
            s = max(sa, sb)
            if best is None or s < best[0]:
                best = (s, a2, b2)
        if best is not None:
            q = _quad([a, b, best[2], best[1]])
            if q is not None:
                strips.append((q, i))
            continue
        # parallel neighbours: join facing edges straight across (the step of a stepped plate)
        for j2, a2, b2 in free:
            if j2 == i or (min(i, j2), max(i, j2)) in bridged or planes[j2] is None:
                continue
            if abs(float(np.dot(n_i, planes[j2][1]))) < 1 - 1e-6:
                continue
            gap = (a2 + b2) / 2 - m
            across = abs(float(np.dot(gap, n_i)))
            sideways = np.linalg.norm(gap - np.dot(gap, n_i) * n_i - np.dot(gap, d) * d)
            d2 = (b2 - a2) / np.linalg.norm(b2 - a2)
            if float(np.dot(out, _off(pieces[j2], a2, b2, planes[j2][1], reach))) > -0.9:
                continue  # the two edges look the same way: layers, not a step
            if across < tol or across > reach or sideways > reach or abs(float(np.dot(d, d2))) < 1 - 1e-6:
                continue
            # the part of both edges that overlaps along d
            t0, t1 = 0.0, float(np.dot(b - a, d))
            u0, u1 = sorted((float(np.dot(a2 - a, d)), float(np.dot(b2 - a, d))))
            lo, hi = max(t0, u0), min(t1, u1)
            if hi - lo <= tol:
                continue
            shift = a2 - a - np.dot(a2 - a, d) * d
            q = _quad([a + d * lo, a + d * hi, a + d * hi + shift, a + d * lo + shift])
            if q is not None:
                strips.append((q, i))
                bridged.add((min(i, j2), max(i, j2)))
    return strips


def _face_distance(face, p: gp_Pnt) -> float:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    d = BRepExtrema_DistShapeShape(face, BRepBuilderAPI_MakeVertex(p).Vertex())
    return d.Value() if d.IsDone() else float("inf")


# ---- beams --------------------------------------------------------------------------------


@dataclass
class Beam:
    p0: P3
    p1: P3
    length: float
    area: float  # of the cross-section at the middle
    iy: float  # second moments of the section about its own centre, in the section's two main directions
    iz: float
    j: float  # a torsion constant: exact for round sections, the thin-wall formula for tubes, else estimated
    y_dir: P3  # the section's first main direction
    profile: str = ""  # from the frame member record when there is one
    size: str = ""


def _section(shape, origin: np.ndarray, axis: np.ndarray):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.gp import gp_Pln

    big = 4 * robust.diagonal(shape)
    pln = gp_Pln(gp_Pnt(*origin), gp_Dir(*axis))
    face = BRepBuilderAPI_MakeFace(pln, -big, big, -big, big).Face()
    com = BRepAlgoAPI_Common(shape, face)
    if not com.IsDone():
        return None
    out = _explore(com.Shape(), TopAbs_FACE)
    return _compound(out) if out else None


def section_props(sec, axis: np.ndarray) -> tuple[float, float, float, float, np.ndarray]:
    """Area, the two main second moments, a torsion constant and the first main direction."""
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(sec, g)
    a = g.Mass()
    m = g.MatrixOfInertia()
    mat = np.array([[m.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)])
    # the matrix is about the centre; for a flat area its value along a direction in the plane is
    # the second moment about that direction, and along the axis the polar moment (the sum of both)
    ax = axis / np.linalg.norm(axis)
    t = np.eye(3) - np.outer(ax, ax)
    vals, vecs = np.linalg.eigh(t @ mat @ t)
    keep = [k for k in np.argsort(vals) if abs(float(np.dot(vecs[:, k], ax))) < 0.5]
    polar = float(ax @ mat @ ax)
    iy, iz = (float(vals[keep[0]]), float(vals[keep[1]])) if len(keep) == 2 else (polar / 2, polar / 2)
    ydir = vecs[:, keep[0]] if keep else np.cross(ax, [1, 0, 0])
    edges = _explore(sec, TopAbs_EDGE)
    perim = 0.0
    for e in edges:
        gg = GProp_GProps()
        BRepGProp.LinearProperties_s(e, gg)
        perim += gg.Mass()
    secs = _explore(sec, TopAbs_FACE)
    holes = sum(max(0, _wires(f) - 1) for f in secs)
    if _round(edges):  # a rod or a round tube: twisting is the polar moment
        j = polar
    elif holes:  # a closed thin wall (box tube): Bredt, 4 Am^2 t / s, Am inside the wall's middle
        from OCP.BRepTools import BRepTools as BT

        filled = sum(area(BRepBuilderAPI_MakeFace(_wire(BT.OuterWire_s(_face(f))), True).Face()) for f in secs)
        a_m = filled - a / 2
        s_mid = perim / 2
        t_wall = a / max(s_mid, 1e-12)
        j = min(polar, 4 * a_m * a_m * t_wall / max(s_mid, 1e-12))
    elif perim * perim / max(a, 1e-30) > 40:  # an open thin section (angle, channel, I): strips, b t^3 / 3
        t_wall = 2 * a / max(perim, 1e-12)
        j = min(polar, (perim / 2) * t_wall ** 3 / 3)
    else:  # a solid block: Saint-Venant's A^4 / (4 pi^2 Ip)
        j = min(polar, a ** 4 / (4 * math.pi ** 2 * max(polar, 1e-30)))
    return a, iy, iz, j, ydir


def _mesh_points(face) -> list[P3]:
    from OCP.TopLoc import TopLoc_Location

    loc = TopLoc_Location()
    tri = BRep_Tool.Triangulation_s(_face(face), loc)
    if tri is None:
        return []
    t = loc.Transformation()
    return [_p(tri.Node(i).Transformed(t)) for i in range(1, tri.NbNodes() + 1)]


def _round(edges) -> bool:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_CurveType

    centres = []
    for e in edges:
        c = BRepAdaptor_Curve(_edge(e))
        if c.GetType() != GeomAbs_CurveType.GeomAbs_Circle:
            return False
        centres.append(np.array(_p(c.Circle().Location())))
    return bool(centres) and all(np.linalg.norm(x - centres[0]) <= 1e-6 * max(1.0, np.linalg.norm(x)) for x in centres)


def _wires(face) -> int:
    from OCP.TopAbs import TopAbs_WIRE

    return len(_explore(face, TopAbs_WIRE))


def beam_of(shape, p0: P3 | None = None, p1: P3 | None = None) -> Beam:
    """The centre line and section of one long member (the line from the member record when given,
    else the longest main axis of its mass)."""
    if p0 is None or p1 is None:
        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, g)
        c = g.CentreOfMass()
        centre = np.array(_p(c))
        pr = g.PrincipalProperties()
        axes = [np.array(_p(v)) for v in (pr.FirstAxisOfInertia(), pr.SecondAxisOfInertia(),
                                           pr.ThirdAxisOfInertia())]
        # the long axis has the smallest moment about it
        moments = pr.Moments()
        ax = axes[int(np.argmin(moments))]
        ax = ax / np.linalg.norm(ax)
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.TopAbs import TopAbs_VERTEX

        BRepMesh_IncrementalMesh(shape, 0.05 * robust.diagonal(shape))
        verts = [_p(BRep_Tool.Pnt_s(_vertex(v))) for v in _explore(shape, TopAbs_VERTEX)]
        verts += [p for f in _explore(shape, TopAbs_FACE) for p in _mesh_points(f)]
        s = (np.asarray(verts) - centre) @ ax
        a0, a1 = centre + s.min() * ax, centre + s.max() * ax
    else:
        a0, a1 = np.array(p0, float), np.array(p1, float)
    ax = a1 - a0
    length = float(np.linalg.norm(ax))
    if length < 1e-12:
        raise PrepError("it has no length")
    ax = ax / length
    mid = (a0 + a1) / 2
    sec = _section(shape, mid, ax)
    if sec is None:
        raise PrepError("the cut across its middle is empty")
    a, iy, iz, j, ydir = section_props(sec, ax)
    gs = GProp_GProps()
    BRepGProp.SurfaceProperties_s(sec, gs)
    sc = np.array(_p(gs.CentreOfMass()))
    off = sc - mid - np.dot(sc - mid, ax) * ax  # the section's centre beside the line: move the line there
    a0, a1 = a0 + off, a1 + off
    return Beam(tuple(map(float, a0)), tuple(map(float, a1)), length, a, iy, iz, j, tuple(map(float, ydir)))


def nodes(beams: list[Beam], tol: float) -> list[tuple[P3, list[tuple[int, int]]]]:
    """Where beam ends meet (within ``tol``): each meeting point with the (beam, end) pairs there."""
    ends = [(i, k, np.array(b.p0 if k == 0 else b.p1)) for i, b in enumerate(beams) for k in (0, 1)]
    groups: list[list] = []
    for i, k, p in ends:
        for g in groups:
            if np.linalg.norm(g[0] - p) <= tol:
                g[1].append((i, k))
                g[2].append(p)
                break
        else:
            groups.append([p, [(i, k)], [p]])
    return [(tuple(map(float, np.mean(g[2], axis=0))), g[1]) for g in groups]


# ---- fluid volumes and enclosures ----------------------------------------------------------


@dataclass
class Opening:
    face: int  # the face (of the part) whose inner edge loop is the opening
    centre: P3
    normal: P3
    area: float


def openings(shape, cap_faces: list[int] | None = None) -> tuple[list, list[Opening]]:
    """The cap faces closing the openings of a part: for each chosen face (or, with none, each
    flat face with an inner loop whose middle is outside the material), a flat face filling the
    inner loop. Returns (caps, openings)."""
    from OCP.BRepTools import BRepTools as BT
    from OCP.TopAbs import TopAbs_WIRE

    faces = _explore(shape, TopAbs_FACE)
    picked = cap_faces if cap_faces else range(len(faces))
    caps, out = [], []
    cls = BRepClass3d_SolidClassifier(shape)
    for i in picked:
        f = _face(faces[i])
        s = BRepAdaptor_Surface(f)
        if s.GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
            if cap_faces:
                raise PrepError(f"face {i + 1} is not flat; pick the flat end face round an opening")
            continue
        outer = BT.OuterWire_s(f)
        inner = [w for w in _explore(f, TopAbs_WIRE) if not w.IsSame(outer)]
        for w in inner:
            mk = BRepBuilderAPI_MakeFace(s.Plane(), _wire(w), True)
            if not mk.IsDone():
                continue
            cap = mk.Face()
            got = inside_point(cap)
            if got is None:
                continue
            cls.Perform(got[0], 1e-7)
            if cls.State() == TopAbs_IN:
                continue  # a boss or a solid plug, not an opening
            g = GProp_GProps()
            BRepGProp.SurfaceProperties_s(cap, g)
            n = s.Plane().Axis().Direction()
            caps.append(cap)
            out.append(Opening(i, _p(g.CentreOfMass()), (n.X(), n.Y(), n.Z()), g.Mass()))
    return caps, out


def fluid_volume(shape, caps: list) -> list:
    """The solids inside ``shape`` closed off by ``caps``: the empty space of a pipe, valve or
    housing that does not reach the outside."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Splitter
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

    lo, hi = _box(shape, 0.05 * robust.diagonal(shape) + 1.0)
    box = BRepPrimAPI_MakeBox(gp_Pnt(*lo), gp_Pnt(*hi)).Shape()
    air = BRepAlgoAPI_Cut(box, shape)
    if not air.IsDone():
        raise PrepError("the space round the part could not be found")
    room = air.Shape()
    if caps:
        sp = BRepAlgoAPI_Splitter()
        sp.SetArguments(_list([room]))
        sp.SetTools(_list(caps))
        sp.Build()
        if not sp.IsDone():
            raise PrepError("the openings could not be closed off")
        room = sp.Shape()
    inside = []
    tol = 1e-6 * max(1.0, robust.diagonal(box))
    for s in _explore(room, TopAbs_SOLID):
        a, b = _box(s, 0.0)
        if any(a[k] <= lo[k] + tol or b[k] >= hi[k] - tol for k in range(3)):
            continue  # reaches the outer box: outside air
        inside.append(s)
    return inside


def _list(shapes):
    try:  # OCP 7.x
        from OCP.TopTools import TopTools_ListOfShape
    except ImportError:  # OCP 8
        from OCP.collections import (
            List_TopoDS_Shape as TopTools_ListOfShape,  # type: ignore[no-redef]
        )
    out = TopTools_ListOfShape()
    for s in shapes:
        out.Append(s)
    return out


def _box(shape, pad: float) -> tuple[np.ndarray, np.ndarray]:
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    return np.array(_p(lo)) - pad, np.array(_p(hi)) + pad


SIDES = ("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX")


def enclosure(shapes: list, kind: str, margins: list[float]) -> tuple[object, dict[str, list[int]], object]:
    """The space round ``shapes`` in a box, cylinder (along Z) or sphere, with them cut out.
    ``margins``: one number for every side, or six (-X, +X, -Y, +Y, -Z, +Z). Returns (solid,
    named outer faces -> face indexes of the result, the outer shape before the cut)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import (
        BRepPrimAPI_MakeBox,
        BRepPrimAPI_MakeCylinder,
        BRepPrimAPI_MakeSphere,
    )
    from OCP.gp import gp_Ax2

    whole = _compound(shapes)
    lo, hi = _box(whole, 0.0)
    m = list(margins) * 6 if len(margins) == 1 else list(margins)
    if len(m) != 6 or any(x < 0 for x in m):
        raise PrepError("give one margin, or six (-X, +X, -Y, +Y, -Z, +Z), none negative")
    lo2 = lo - np.array(m[0::2])
    hi2 = hi + np.array(m[1::2])
    if kind == "BOX":
        outer = BRepPrimAPI_MakeBox(gp_Pnt(*lo2), gp_Pnt(*hi2)).Shape()
    elif kind == "CYLINDER":
        c = (lo + hi) / 2
        r = float(np.linalg.norm((hi - lo)[:2]) / 2 + max(m[:4]))
        outer = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(c[0], c[1], lo2[2]), gp_Dir(0, 0, 1)), r,
                                         float(hi2[2] - lo2[2])).Shape()
    elif kind == "SPHERE":
        c = (lo + hi) / 2
        r = float(np.linalg.norm(hi - lo) / 2 + max(m))
        outer = BRepPrimAPI_MakeSphere(gp_Pnt(*c), r).Shape()
    else:
        raise PrepError("the shape is BOX, CYLINDER or SPHERE")
    cut = BRepAlgoAPI_Cut(outer, whole)
    if not cut.IsDone() or robust.is_empty(cut.Shape()):
        raise PrepError("the model could not be cut out of the enclosure")
    res = robust.unwrap(cut.Shape())
    faces = _explore(res, TopAbs_FACE)
    outer_faces = _explore(outer, TopAbs_FACE)
    named: dict[str, list[int]] = {}
    for i, f in enumerate(faces):
        # faces of the outer shape (cut or not) carry over as themselves or their pieces
        src = [k for k, of in enumerate(outer_faces) if of.IsSame(f) or any(x.IsSame(f) for x in cut.Modified(of))]
        if not src:
            named.setdefault("WALLS", []).append(i)
            continue
        if kind == "BOX":
            s = BRepAdaptor_Surface(_face(f))
            n = s.Plane().Axis().Direction()
            got = inside_point(f)
            nv = got[1] if got else gp_Vec(n)
            k = int(np.argmax(np.abs([nv.X(), nv.Y(), nv.Z()])))
            sign = [nv.X(), nv.Y(), nv.Z()][k] > 0
            named.setdefault(SIDES[2 * k + (1 if sign else 0)], []).append(i)
        elif kind == "CYLINDER":
            s = BRepAdaptor_Surface(_face(f))
            if s.GetType() == GeomAbs_SurfaceType.GeomAbs_Cylinder:
                named.setdefault("SIDE", []).append(i)
            else:
                got = inside_point(f)
                named.setdefault("TOP" if got and got[1].Z() > 0 else "BOTTOM", []).append(i)
        else:
            named.setdefault("OUTER", []).append(i)
    return res, named, outer


# ---- shared faces ------------------------------------------------------------------------------


def share(shapes: list):
    """Split ``shapes`` where they touch so that they use the same face there. Returns (new shapes
    in the same order, the builder for the history)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_BuilderAlgo

    g = BRepAlgoAPI_BuilderAlgo()
    g.SetArguments(_list(shapes))
    g.SetNonDestructive(True)
    g.Build()
    if not g.IsDone():
        raise PrepError("the kernel could not split the parts where they touch")
    out = []
    for s in shapes:
        mod = list(g.Modified(s))
        if not mod:
            out.append(s)
        elif len(mod) == 1:
            out.append(mod[0])
        else:
            out.append(_compound(mod))
    return out, g


def shared_faces(a, b) -> list[tuple[int, int]]:
    """(face of a, face of b) pairs that are the very same face."""
    fa, fb = _explore(a, TopAbs_FACE), _explore(b, TopAbs_FACE)
    return [(i, j) for i, x in enumerate(fa) for j, y in enumerate(fb) if x.IsSame(y)]


def touching_area(a, b) -> float:
    """The area where two solids touch (0 when they are apart or only meet along an edge)."""
    out, _g = share([a, b])
    return sum(area(_explore(out[0], TopAbs_FACE)[i]) for i, _j in shared_faces(out[0], out[1]))


def shared_area(a, b) -> float:
    fa = _explore(a, TopAbs_FACE)
    return sum(area(fa[i]) for i, _j in shared_faces(a, b))


def matching_area(a, b, tol: float) -> float:
    """The area of faces of ``a`` that have a face of ``b`` in the same place (same middle, same
    size), shared or only matching: what a mesher joins."""
    fa, fb = _explore(a, TopAbs_FACE), _explore(b, TopAbs_FACE)
    def key(f):
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, g)
        return np.array(_p(g.CentreOfMass())), g.Mass()
    kb = [key(f) for f in fb]
    total = 0.0
    for f in fa:
        c, ar = key(f)
        if any(np.linalg.norm(c - c2) <= tol and abs(ar - a2) <= tol * max(1.0, math.sqrt(ar)) for c2, a2 in kb):
            total += ar
    return total



# ---- spot welds (PLAN item 99) ----------------------------------------------------------------


@dataclass
class Spot:
    at: P3  # the weld point: halfway between the two parts there
    on_edge: P3  # the point on the edge it was laid out from
    gap: float  # how far apart the two parts are at that point


def spot_places(length: float, pitch: float, margin: float) -> list[float]:
    """Distances along an edge for spot welds ``pitch`` apart, kept ``margin`` from both ends and
    centred on the edge (the left-over length shared between the two ends)."""
    if pitch <= 0:
        raise PrepError("the pitch must be more than 0")
    usable = length - 2 * margin
    if usable < -1e-9:
        raise PrepError(f"the edge ({length:g} long) is shorter than twice the end distance ({margin:g})")
    n = int(math.floor(max(usable, 0.0) / pitch + 1e-9)) + 1
    start = (length - (n - 1) * pitch) / 2
    return [start + k * pitch for k in range(n)]


def spot_welds(edge, a, b, pitch: float, margin: float) -> list[Spot]:
    """Spot weld points along ``edge`` joining shapes ``a`` and ``b``: laid out every ``pitch``
    along the edge, each moved to halfway between the nearest points of the two parts."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.GCPnts import GCPnts_AbscissaPoint

    c = BRepAdaptor_Curve(_edge(edge))
    t0 = c.FirstParameter()
    length = GCPnts_AbscissaPoint.Length_s(c)
    out = []
    for s in spot_places(length, pitch, margin):
        ap_ = GCPnts_AbscissaPoint(c, s, t0)
        q = c.Value(ap_.Parameter() if ap_.IsDone() else t0)
        v = BRepBuilderAPI_MakeVertex(q).Vertex()
        near = []
        for shape in (a, b):
            d = BRepExtrema_DistShapeShape(v, shape)
            if not d.IsDone() or d.NbSolution() < 1:
                raise PrepError("the nearest point on a part could not be found")
            near.append(d.PointOnShape2(1))
        pa, pb = near
        mid = ((pa.X() + pb.X()) / 2, (pa.Y() + pb.Y()) / 2, (pa.Z() + pb.Z()) / 2)
        out.append(Spot(mid, _p(q), pa.Distance(pb)))
    return out
