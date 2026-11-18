"""Will an assembly stand up under gravity? A geometry check, not a solver.

Every pair of parts is measured (geometry/contact.py ideas, face by face):
they overlap, touch (on faces, along a line or at points), are a hair
apart (a gap that was probably meant to be a touch), or are apart.

* **Connected to the ground.** Parts are linked when they touch or overlap.
  The ground is a floor under the lowest part (or a body you name). A part
  with no chain of links to the ground floats: it would fall.
* **Each part on what holds it.** The points where a part touches others
  from below (the other part's surface faces up there) are its supports.
  When its centre of mass, seen from above, lies inside the outline of its
  supports, it sits; the margin is how far the centre may move before it
  leaves that outline. Outside, it tips off. Touching only at its sides
  (nothing under it) it needs a fastener. Parts you list as fastened
  (bolted, glued, welded) and parts that overlap a neighbour (a press fit)
  are taken as held.
* **The whole on the floor.** The same test for all parts together on the
  floor, with the angle it can lean before it tips.

What it cannot know: friction, fasteners not modelled as parts, and
whether the parts below can carry the load (that is STRESS's question, part
by part).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

UP_FACE = 0.5  # a supporting surface faces up within 60 degrees of straight up


class GravityError(ValueError):
    pass


@dataclass
class Link:
    a: int  # part index
    b: int
    state: str  # "overlap", "touch", "gap", "apart"
    kind: str = ""  # touch: "face", "line", "point"
    distance: float = 0.0
    # contact points with the outward normal of b's surface there: b holds a up where n_b points up
    points_a: list = field(default_factory=list)  # [(point, normal of b's surface at it)]
    points_b: list = field(default_factory=list)  # [(point, normal of a's surface at it)]


@dataclass
class Part:
    key: object  # the caller's id (a body ID, or "floor")
    shape: object
    mass: float
    centre: np.ndarray
    ground: bool = False
    fastened: bool = False


def _api(cls, name):
    return getattr(cls, name + "_s", None) or getattr(cls, name)


def _xyz(p) -> np.ndarray:
    return np.array([p.X(), p.Y(), p.Z()])


def mass_centre(shape, density: float) -> tuple[float, np.ndarray]:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, g, 1e-7)
    return abs(g.Mass()) * density, _xyz(g.CentreOfMass())


def floor_block(shapes, down: np.ndarray):
    """A slab just under the lowest point of the shapes (along ``down``), wider than all of them."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    pts = np.concatenate([_vertices(s) for s in shapes] + [_samples(s) for s in shapes])
    h = pts @ down
    low = float(h.max())  # furthest along down
    size = float(np.ptp(pts, axis=0).max()) + 1.0
    up = -down
    ref = np.array([1.0, 0.0, 0.0]) if abs(up[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    x = ref - (ref @ up) * up
    x /= np.linalg.norm(x)
    y = np.cross(up, x)
    c = pts.mean(axis=0)
    c = c - (c @ down) * down + low * down  # on the floor level
    corner = c - 2 * size * x - 2 * size * y - size * up
    ax = gp_Ax2(gp_Pnt(*corner), gp_Dir(*up), gp_Dir(*x))
    return BRepPrimAPI_MakeBox(ax, 4 * size, 4 * size, size).Shape(), low


def _vertices(shape) -> np.ndarray:
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    v = _api(TopoDS, "Vertex")
    out = []
    ex = TopExp_Explorer(shape, TopAbs_VERTEX)
    while ex.More():
        out.append(_xyz(BRep_Tool.Pnt_s(v(ex.Current()))))
        ex.Next()
    return np.array(out).reshape(-1, 3)


def _samples(shape) -> np.ndarray:
    """Points of a coarse mesh of the shape (curved faces have few vertices)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    cp = BRepBuilderAPI_Copy(shape).Shape()
    BRepMesh_IncrementalMesh(cp, 0.05, True, 0.3, True)  # (deflection relative to each edge)
    out = []
    ex = TopExp_Explorer(cp, TopAbs_FACE)
    while ex.More():
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(_api(TopoDS, "Face")(ex.Current()), loc)
        ex.Next()
        if tri is None:
            continue
        t = loc.Transformation()
        out += [_xyz(tri.Node(i).Transformed(t)) for i in range(1, tri.NbNodes() + 1)]
    return np.array(out).reshape(-1, 3)


def _normal(face, pt) -> np.ndarray:
    """The outward normal of a face at (near) a point."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt, gp_Vec

    pj = GeomAPI_ProjectPointOnSurf(gp_Pnt(*map(float, pt)), BRep_Tool.Surface_s(face))
    if not pj.NbPoints():
        return np.zeros(3)
    u, v = pj.LowerDistanceParameters()
    p, n = gp_Pnt(), gp_Vec()
    BRepGProp_Face(face).Normal(u, v, p, n)  # follows the face's orientation
    m = n.Magnitude()
    return np.array([n.X(), n.Y(), n.Z()]) / m if m > 1e-12 else np.zeros(3)


def _faces(shape):
    from . import contact as ct

    return ct._faces(shape)


def link(i: int, j: int, a, b, tol: float, near: float) -> Link:
    """How part i (shape a) meets part j (shape b), with the contact points and normals."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Section
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    from . import contact as ct

    fa, fb = _faces(a), _faces(b)
    d, pa, pb, _na, _nb = ct.gap(a, b, stop=tol, faces=(fa, fb))
    if d > tol:
        if ct._inside(a, b) is None and ct._inside(b, a) is None:
            return Link(i, j, "gap" if d <= near else "apart", distance=d)
    c = ct.contact(a, b, tol)
    if c.state == "overlap":
        return Link(i, j, "overlap")
    if c.state == "apart":
        return Link(i, j, "gap" if c.distance <= near else "apart", distance=c.distance)
    out = Link(i, j, "touch", c.kind)
    area_pts, line_pts = [], []  # faces lying on each other, else faces meeting along curves or at points
    for _i, f1, b1 in fa:
        for _j, f2, b2 in fb:
            if ct.boxes_apart(b1, b2, tol):
                continue
            dd = BRepExtrema_DistShapeShape(f1, f2)
            if not dd.IsDone() or not dd.NbSolution() or dd.Value() > tol:
                continue
            common = ct._boolean(BRepAlgoAPI_Common, f1, f2, tol)
            if common is not None and ct._has(common, ct.TopAbs_FACE) and ct._area(common) > tol * tol:
                area_pts += [(q, f1, f2) for q in list(_vertices(common)) + list(_samples(common))]
                continue
            sec = ct._boolean(BRepAlgoAPI_Section, f1, f2, tol)
            pts = list(_edge_points(sec)) if sec is not None and ct._has(sec, ct.TopAbs_EDGE) else []
            if not pts:
                pts = [_xyz(dd.PointOnShape1(k)) for k in range(1, dd.NbSolution() + 1)]
            line_pts += [(q, f1, f2) for q in pts]
    # where faces lie on each other, the edges of those faces also meet other faces along lines: those
    # lines are not extra supports
    for q, f1, f2 in area_pts or line_pts:
        out.points_a.append((q, _normal(f2, q)))
        out.points_b.append((q, _normal(f1, q)))
    return out


def _edge_points(shape, n: int = 9) -> np.ndarray:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    out = []
    ex = TopExp_Explorer(shape, TopAbs_EDGE)
    while ex.More():
        c = BRepAdaptor_Curve(_api(TopoDS, "Edge")(ex.Current()))
        ex.Next()
        t0, t1 = c.FirstParameter(), c.LastParameter()
        out += [_xyz(c.Value(t0 + (t1 - t0) * k / (n - 1))) for k in range(n)]
    return np.array(out).reshape(-1, 3)


# ---- 2D outlines ---------------------------------------------------------------------------


def plane_axes(down: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    up = -down
    ref = np.array([1.0, 0.0, 0.0]) if abs(up[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    x = ref - (ref @ up) * up
    x /= np.linalg.norm(x)
    return x, np.cross(up, x)


def hull(pts: np.ndarray) -> np.ndarray:
    """The convex outline of 2D points, anticlockwise (Andrew's monotone chain); 1 or 2 points when
    they all lie on one point or line."""
    p = np.unique(np.round(pts, 9), axis=0)
    if len(p) <= 2:
        return p
    p = p[np.lexsort((p[:, 1], p[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for q in p:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 1e-12:
            lower.pop()
        lower.append(q)
    for q in p[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 1e-12:
            upper.pop()
        upper.append(q)
    h = np.array(lower[:-1] + upper[:-1])
    if len(h) < 3:  # all on a line: its two ends
        d = p - p[0]
        k = d @ (p[-1] - p[0])
        return np.array([p[int(np.argmin(k))], p[int(np.argmax(k))]])
    return h


def margin(c: np.ndarray, h: np.ndarray) -> float:
    """How far 2D point c lies inside outline h (negative: outside, by that much). On a line or a
    point (no area) it is 0 at best."""
    if len(h) == 1:
        return -float(np.linalg.norm(c - h[0]))
    if len(h) == 2:
        a, b = h
        t = np.clip((c - a) @ (b - a) / max((b - a) @ (b - a), 1e-30), 0, 1)
        return -float(np.linalg.norm(c - (a + t * (b - a))))
    best = math.inf
    outside = 0.0
    for k in range(len(h)):
        a, b = h[k], h[(k + 1) % len(h)]
        e = b - a
        n = np.array([e[1], -e[0]]) / max(np.linalg.norm(e), 1e-30)  # outward for anticlockwise
        s = float((c - a) @ n)
        if s > 0:
            t = np.clip((c - a) @ e / max(e @ e, 1e-30), 0, 1)
            outside = max(outside, float(np.linalg.norm(c - (a + t * e))))
        best = min(best, -s)
    return -outside if outside > 0 else best


# ---- the check -----------------------------------------------------------------------------


@dataclass
class Verdict:
    part: int
    state: str  # "ground", "floats", "sits", "tips", "sides", "held"
    margin: float = 0.0
    on: list = field(default_factory=list)  # the parts it rests on / hangs from


@dataclass
class Result:
    links: list
    verdicts: list
    whole_margin: float | None = None  # the whole on the floor (None: a named ground)
    whole_angle: float | None = None  # degrees it can lean before tipping
    floating: list = field(default_factory=list)


def supports(part: int, links: list[Link], down: np.ndarray) -> tuple[list[np.ndarray], list[int]]:
    """Points where others hold part ``part`` up from below, and which parts those are."""
    pts, who = [], []
    for ln in links:
        if ln.state != "touch":
            continue
        if ln.a == part:
            got, other = ln.points_a, ln.b
        elif ln.b == part:
            got, other = ln.points_b, ln.a
        else:
            continue
        up_here = [q for q, n in got if float(n @ -down) >= UP_FACE]
        if up_here:
            pts += up_here
            who.append(other)
    return pts, who


def check(parts: list[Part], down, tol: float, near: float) -> Result:
    down = np.asarray(down, float)
    down = down / np.linalg.norm(down)
    from . import contact as ct

    boxes = [ct.box_of(p.shape) for p in parts]
    links = []
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            if ct.box_distance(boxes[i], boxes[j]) > max(near, tol):
                continue
            links.append(link(i, j, parts[i].shape, parts[j].shape, tol, near))
    # connected to the ground through touches and overlaps
    joined = {i: set() for i in range(len(parts))}
    for ln in links:
        if ln.state in ("touch", "overlap"):
            joined[ln.a].add(ln.b)
            joined[ln.b].add(ln.a)
    seen = {i for i, p in enumerate(parts) if p.ground}
    todo = list(seen)
    while todo:
        k = todo.pop()
        for o in joined[k]:
            if o not in seen:
                seen.add(o)
                todo.append(o)
    x, y = plane_axes(down)
    verdicts = []
    for i, p in enumerate(parts):
        if p.ground:
            verdicts.append(Verdict(i, "ground"))
            continue
        if i not in seen:
            verdicts.append(Verdict(i, "floats"))
            continue
        pts, who = supports(i, links, down)
        overlapped = sorted(ln.b if ln.a == i else ln.a for ln in links
                            if ln.state == "overlap" and i in (ln.a, ln.b))
        if p.fastened or overlapped:
            verdicts.append(Verdict(i, "held", on=overlapped or sorted(joined[i])))
            continue
        if not pts:
            verdicts.append(Verdict(i, "sides", on=sorted(joined[i])))
            continue
        P = np.array(pts)
        h = hull(np.stack([P @ x, P @ y], axis=1))
        m = margin(np.array([p.centre @ x, p.centre @ y]), h)
        verdicts.append(Verdict(i, "sits" if m > tol else "tips", m, sorted(set(who))))
    res = Result(links, verdicts, floating=[i for i in range(len(parts)) if i not in seen])
    floor = [i for i, p in enumerate(parts) if p.ground and p.key == "floor"]
    if floor:
        f = floor[0]
        on_floor = [ln for ln in links if ln.state == "touch" and f in (ln.a, ln.b)]
        pts = [q for ln in on_floor for q, _n in (ln.points_a if ln.b == f else ln.points_b)]
        movers = [p for k, p in enumerate(parts) if not p.ground and k in seen]
        total = sum(p.mass for p in movers)
        if pts and total > 0:
            c = sum(p.mass * p.centre for p in movers) / total
            P = np.array(pts)
            h = hull(np.stack([P @ x, P @ y], axis=1))
            res.whole_margin = margin(np.array([c @ x, c @ y]), h)
            level = float(np.mean(P @ down))
            height = max(level - float(c @ down), 1e-9)
            res.whole_angle = math.degrees(math.atan2(max(res.whole_margin, 0.0), height))
    return res
