"""How two solids meet: apart (with the gap), touching (on a face, a line or a
point) or overlapping (with the volume in common); and how a shaft sits in a hole.

These are the measurements under the CONTACT and FIT commands and the
assistant's contact tools. Everything works on kernel shapes and 1-based face
indices; modeler/ai/contact.py turns them into IDs and short answers.

Touching is decided with a tolerance ``tol``: bodies closer than it touch.
The contact itself is found face by face: every pair of faces (one from each
body) closer than ``tol`` is cut against each other. Faces lying on each other
give an area (a block standing on a plate, a pin in a hole of its own size);
faces that only meet along a curve give a length (a cylinder lying on a
plate); otherwise the bodies meet at points (a ball on a plate).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Section
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS_Shape

try:  # OCP 7.x
    from OCP.TopTools import TopTools_ListOfShape
except ImportError:  # OCP 8
    from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape  # type: ignore[no-redef]

from . import recognize as rc
from . import robust

P3 = tuple[float, float, float]


# ---- boxes ---------------------------------------------------------------------------------


def box_of(shape: TopoDS_Shape) -> tuple[float, ...]:
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if box.IsVoid():
        return (0.0,) * 6
    lo, hi = box.CornerMin(), box.CornerMax()
    return lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()


def boxes_apart(a: tuple[float, ...], b: tuple[float, ...], gap: float) -> bool:
    """True when the boxes are further apart than ``gap`` along some axis."""
    return any(a[i + 3] + gap < b[i] or b[i + 3] + gap < a[i] for i in range(3))


def size_of(*boxes: tuple[float, ...]) -> float:
    return max(max(b[i + 3] - b[i] for i in range(3)) for b in boxes)


def default_tol(*shapes: TopoDS_Shape, extra: float = 0.0) -> float:
    """The touching tolerance: a millionth of the size (at least 1e-6), plus the model's own."""
    return max(1e-6, 1e-6 * size_of(*(box_of(s) for s in shapes))) + extra


# ---- one pair --------------------------------------------------------------------------------


@dataclass
class Contact:
    state: str  # "apart", "touch" or "overlap"
    distance: float = 0.0  # the gap when apart (0 otherwise)
    at_a: P3 = (0.0, 0.0, 0.0)  # nearest points (apart), or a point of the contact
    at_b: P3 = (0.0, 0.0, 0.0)
    near_a: list[int] = field(default_factory=list)  # faces nearest the other body (apart)
    near_b: list[int] = field(default_factory=list)
    kind: str = ""  # touch: "face", "line" or "point"
    area: float = 0.0  # touch on faces: the area in common
    length: float = 0.0  # touch along curves: their length
    faces_a: list[int] = field(default_factory=list)  # touch / overlap: faces of a in the contact
    faces_b: list[int] = field(default_factory=list)
    volume: float = 0.0  # overlap: the volume in common
    overlap_box: tuple[float, ...] = ()  # overlap: the box round the common volume
    fraction: float = 0.0  # overlap: the common volume over the smaller body's volume


def _faces(shape: TopoDS_Shape):
    m = rc.shape_map(shape, TopAbs_FACE)
    return [(i, rc.as_face(m.FindKey(i)), box_of(m.FindKey(i))) for i in range(1, m.Extent() + 1)]


def _xyz(p) -> P3:
    return (p.X(), p.Y(), p.Z())


def _area(shape: TopoDS_Shape) -> float:
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, g)
    return g.Mass()


def _length(shape: TopoDS_Shape) -> float:
    g = GProp_GProps()
    BRepGProp.LinearProperties_s(shape, g)
    return g.Mass()


def _has(shape: TopoDS_Shape, what) -> bool:
    return TopExp_Explorer(shape, what).More()


def _boolean(cls, a: TopoDS_Shape, b: TopoDS_Shape, fuzzy: float):
    op = cls()
    la, lb = TopTools_ListOfShape(), TopTools_ListOfShape()
    la.Append(a)
    lb.Append(b)
    op.SetArguments(la)
    op.SetTools(lb)
    if fuzzy > 0:
        op.SetFuzzyValue(fuzzy)
    op.Build()
    return op.Shape() if op.IsDone() else None


def box_distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """The distance between two boxes (0 when they meet): a lower bound for the shapes in them."""
    d2 = 0.0
    for i in range(3):
        g = max(b[i] - a[i + 3], a[i] - b[i + 3], 0.0)
        d2 += g * g
    return math.sqrt(d2)


def _inside(shape: TopoDS_Shape, other: TopoDS_Shape) -> P3 | None:
    """A vertex of ``shape`` inside solid ``other`` (one body buried in the other), else None."""
    from .probe import classify

    exp = TopExp_Explorer(shape, TopAbs_VERTEX)
    if not exp.More():
        return None
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS

    v = getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex
    pt = _xyz(BRep_Tool.Pnt_s(v(exp.Current())))
    return pt if classify(other, pt) == "inside" else None


def gap(a: TopoDS_Shape, b: TopoDS_Shape, stop: float = -1.0, faces=None) -> tuple[float, P3, P3, list[int], list[int]]:
    """Shortest distance between the surfaces of two solids, the two nearest points and the
    faces they lie on (1-based indices).

    Measured face against face, nearest boxes first, stopping once no box can be nearer than
    the best found so far: much faster than one kernel call on two whole bodies with many
    curved faces (a threaded bolt). With ``stop`` >= 0, it returns as soon as a distance at
    most ``stop`` is found (enough to know two bodies touch)."""
    fa, fb = faces if faces is not None else (_faces(a), _faces(b))
    pairs = sorted((box_distance(b1, b2), i, f1, j, f2) for i, f1, b1 in fa for j, f2, b2 in fb) \
        if len(fa) * len(fb) <= 40000 else None
    if pairs is None:  # very many faces: let the kernel do it in one call
        d = BRepExtrema_DistShapeShape(a, b)
        if not d.IsDone() or d.NbSolution() == 0:
            raise ValueError("the kernel could not measure the distance between them")
        return d.Value(), _xyz(d.PointOnShape1(1)), _xyz(d.PointOnShape2(1)), [], []
    best, pa, pb = math.inf, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    near_a: set[int] = set()
    near_b: set[int] = set()
    for lower, i, f1, j, f2 in pairs:
        eps = 1e-9 * max(1.0, best if best < math.inf else 1.0)
        if lower > best + eps:
            break
        d = BRepExtrema_DistShapeShape(f1, f2)
        if not d.IsDone() or d.NbSolution() == 0:
            continue
        v = d.Value()
        if v < best - eps:
            best, pa, pb = v, _xyz(d.PointOnShape1(1)), _xyz(d.PointOnShape2(1))
            near_a, near_b = {i}, {j}
        elif v <= best + eps:
            near_a.add(i)
            near_b.add(j)
        if 0 <= stop and best <= stop:
            break
    if best == math.inf:
        raise ValueError("the kernel could not measure the distance between them")
    return best, pa, pb, sorted(near_a), sorted(near_b)


def contact(a: TopoDS_Shape, b: TopoDS_Shape, tol: float | None = None) -> Contact:
    """How solid ``a`` meets solid ``b``."""
    if tol is None:
        tol = default_tol(a, b)
    faces = (_faces(a), _faces(b))
    d, pa, pb, na, nb = gap(a, b, stop=tol, faces=faces)
    if d > tol:
        buried = _inside(a, b) or _inside(b, a)
        if buried is None:
            return Contact("apart", d, pa, pb, na, nb)
        pa = pb = buried  # one is inside the other: all of it is overlap
    va, vb = robust.volume(a), robust.volume(b)
    op = BRepAlgoAPI_Common()
    la, lb = TopTools_ListOfShape(), TopTools_ListOfShape()
    la.Append(a)
    lb.Append(b)
    op.SetArguments(la)
    op.SetTools(lb)
    op.SetRunParallel(True)
    op.SetUseOBB(True)
    op.Build()
    vol, shape = 0.0, None
    if op.IsDone() and not robust.is_empty(op.Shape()):
        shape = op.Shape()
        vol = robust.volume(shape)
    small = max(min(va, vb), 1e-30)
    if shape is not None and vol > max(1e-9 * small, tol ** 3):
        c = Contact("overlap", 0.0, pa, pb, volume=vol, overlap_box=box_of(shape), fraction=vol / small)
        c.faces_a, c.faces_b = _overlap_faces(op, faces[0], shape), _overlap_faces(op, faces[1], shape)
        return c
    return _touch(a, b, tol, pa, pb, faces)


def _count(lst) -> int:
    return lst.Size() if hasattr(lst, "Size") else lst.Extent()


def _overlap_faces(op, faces, common) -> list[int]:
    """Faces of a body that bound the common volume (the faces that dig into the other body),
    from the boolean's own history: kept as they were, or cut down to a piece."""
    kept = rc.shape_map(common, TopAbs_FACE)
    out = []
    for i, f, _ in faces:
        if kept.Contains(f) or _count(op.Modified(f)) > 0:
            out.append(i)
    return out


def _touch(a, b, tol, pa, pb, faces) -> Contact:
    c = Contact("touch", 0.0, pa, pb)
    fa, fb = faces
    area = length = 0.0
    on_a: set[int] = set()
    on_b: set[int] = set()
    lines_a: set[int] = set()
    lines_b: set[int] = set()
    for i, f1, b1 in fa:
        for j, f2, b2 in fb:
            if boxes_apart(b1, b2, tol):
                continue
            d = BRepExtrema_DistShapeShape(f1, f2)
            if not d.IsDone() or not d.NbSolution() or d.Value() > tol:
                continue
            inter = _boolean(BRepAlgoAPI_Common, f1, f2, tol)
            got = _area(inter) if inter is not None and _has(inter, TopAbs_FACE) else 0.0
            if got > tol * tol:
                area += got
                on_a.add(i)
                on_b.add(j)
                continue
            sec = _boolean(BRepAlgoAPI_Section, f1, f2, tol)
            ln = _length(sec) if sec is not None and _has(sec, TopAbs_EDGE) else 0.0
            if ln > tol:
                length += ln
                lines_a.add(i)
                lines_b.add(j)
    if area > 0:
        c.kind, c.area, c.faces_a, c.faces_b = "face", area, sorted(on_a), sorted(on_b)
    elif length > 0:
        # a curve is shared by the faces on both sides of an edge: count it once per face pair seen
        c.kind, c.length, c.faces_a, c.faces_b = "line", length / _shared_count(lines_a, lines_b), sorted(lines_a), sorted(lines_b)
    else:
        c.kind = "point"
        _, _, _, c.faces_a, c.faces_b = gap(a, b, faces=faces)
    return c


def _shared_count(fa: set[int], fb: set[int]) -> float:
    """A contact line along an edge of one body is met by both faces at that edge; halve it then."""
    return 2.0 if (len(fa) > 1) != (len(fb) > 1) and min(len(fa), len(fb)) == 1 else 1.0


# ---- shafts in holes ---------------------------------------------------------------------------


@dataclass
class Round:
    """A full cylinder of a body: a shaft (convex) or a hole (concave)."""

    r: float
    loc: P3  # a point on the axis
    d: P3  # unit axis
    t0: float  # where the cylinder starts and ends along the axis, from loc
    t1: float
    faces: list[int]
    hole: bool
    thread: bool = False  # crest or root pieces of a screw thread (next to helical faces)


def rounds(shape: TopoDS_Shape, tol: float = 1e-6) -> list[Round]:
    """Every full round (all the way round) cylinder of a body, faces of one axis and radius joined."""
    faces = rc.shape_map(shape, TopAbs_FACE)
    groups: list[dict] = []
    for i in range(1, faces.Extent() + 1):
        info = rc._cylinder_info(rc.as_face(faces.FindKey(i)))
        if info is None:
            continue
        loc, d, r, span, (v0, v1), concave = info
        rtol = tol + 1e-7 * max(1.0, r)
        for g in groups:
            if g["hole"] != concave or abs(g["r"] - r) > rtol or abs(abs(rc._dot(g["d"], d)) - 1) > 1e-9:
                continue
            off = rc._sub(loc, g["loc"])
            along = rc._dot(off, g["d"])
            if rc._norm(rc._sub(off, tuple(c * along for c in g["d"]))) > rtol * 10:
                continue
            g["faces"].append(i)
            g["span"] += span
            sign = 1.0 if rc._dot(g["d"], d) > 0 else -1.0
            g["t"] += [along + sign * v0, along + sign * v1]
            break
        else:
            groups.append({"loc": loc, "d": d, "r": r, "span": span, "faces": [i], "t": [v0, v1], "hole": concave})
    out = []
    near = None
    for g in groups:
        if g["span"] < 2 * math.pi - 1e-6:
            continue  # a fillet or a rounded end, not a shaft or a hole
        r = Round(g["r"], g["loc"], g["d"], min(g["t"]), max(g["t"]), sorted(g["faces"]), g["hole"])
        if len(r.faces) > 2:  # a thread leaves its crests (or roots) as many short cylinder pieces
            near = near if near is not None else rc.neighbours(shape, faces)
            helical = {k for i in r.faces for k in near[i]
                       if rc.surface_type(faces.FindKey(k)) not in ("plane", "cylinder", "cone")}
            r.thread = len(helical) >= 2
        out.append(r)
    return out


@dataclass
class Fit:
    shaft: Round
    hole: Round
    shaft_in: str  # "a" or "b": which body has the shaft
    clearance: float  # radial: hole radius minus shaft radius (negative: interference)
    offset: float  # distance between the axes
    tilt: float  # angle between the axes, degrees
    engaged: float  # length along the axis where shaft and hole overlap
    state: str  # "clearance", "line to line", "interference", or "thread" (a threaded shaft in a threaded hole)

    @property
    def min_gap(self) -> float:
        """The tightest side: clearance less the axis offset."""
        return self.clearance - self.offset


def _axis_gap(s: Round, h: Round) -> tuple[float, float, float]:
    """(offset of the shaft's axis from the hole's, over the engaged length; engaged length; tilt deg)."""
    c = max(-1.0, min(1.0, abs(rc._dot(s.d, h.d))))
    tilt = math.degrees(math.acos(c))
    # the shaft's ends on the hole's axis
    ends = []
    for t in (s.t0, s.t1):
        p = rc._add_scaled(s.loc, s.d, t)
        ends.append(rc._dot(rc._sub(p, h.loc), h.d))
    lo, hi = max(min(ends), h.t0), min(max(ends), h.t1)
    engaged = hi - lo
    if engaged <= 0:
        return math.inf, engaged, tilt
    worst = 0.0
    base, dsd = rc._dot(rc._sub(s.loc, h.loc), h.d), rc._dot(s.d, h.d)
    for t in (lo, hi):
        # the point of the shaft's axis level with t on the hole's axis
        p = rc._add_scaled(s.loc, s.d, (t - base) / dsd)
        rel = rc._sub(p, h.loc)
        along = rc._dot(rel, h.d)
        worst = max(worst, rc._norm(rc._sub(rel, tuple(x * along for x in h.d))))
    return worst, engaged, tilt


def fits(a: TopoDS_Shape, b: TopoDS_Shape, tol: float | None = None) -> list[Fit]:
    """Every shaft of one body that sits in a hole of the other, with its clearance."""
    if tol is None:
        tol = default_tol(a, b)
    ra, rb = rounds(a, tol), rounds(b, tol)
    out = []
    for shafts, holes, side in ((ra, rb, "a"), (rb, ra, "b")):
        for s in shafts:
            if s.hole:
                continue
            for h in holes:
                if not h.hole:
                    continue
                if abs(abs(rc._dot(s.d, h.d)) - 1) > 1e-4:  # more than about 0.8 deg apart
                    continue
                off, engaged, tilt = _axis_gap(s, h)
                if engaged <= tol or off >= max(h.r, s.r):
                    continue
                cl = h.r - s.r
                if s.thread and h.thread:
                    state = "thread"
                elif abs(cl) <= tol and off <= tol:
                    state = "line to line"
                elif cl - off < -tol:
                    state = "interference"
                else:
                    state = "clearance"
                out.append(Fit(s, h, side, cl, off, tilt, engaged, state))
    out.sort(key=lambda f: (f.shaft_in, round(f.shaft.r, 6), f.shaft.faces))
    return out
