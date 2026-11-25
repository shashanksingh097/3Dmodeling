"""Box and lasso picks in the 3D view (PLAN item 84), without Qt.

A box dragged left to right picks what lies wholly inside it; dragged right
to left it picks whatever it touches (crossing). A lasso picks what lies
wholly inside the loop drawn. The view hands in ``to_pixel``, which turns a 3D point into a screen
point, so the tests can use a pretend camera.

Every face, edge, vertex or body is sampled as screen points: a vertex is its
point, an edge points along it, a face the nodes of its display mesh (and a
few points inside it), a body all of its faces. What is hidden behind other
faces is picked too, as in a wireframe; hidden and see-through bodies the
view does not draw are left out by the caller.

The answer is a list of IDs for ``PICK, kind, "3 5 7"``.
"""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

Pixel = tuple[float, float]
ToPixel = Callable[[tuple[float, float, float]], Pixel]

INSIDE, CROSSING = "INSIDE", "CROSSING"
MAX_FACE_POINTS = 400  # a face with a finer mesh is thinned to this many points
EDGE_POINTS = 16


def box_polygon(a: Pixel, b: Pixel) -> list[Pixel]:
    (x0, y0), (x1, y1) = a, b
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def box_mode(a: Pixel, b: Pixel) -> str:
    """Left to right: inside. Right to left: crossing (as most modellers do)."""
    return INSIDE if b[0] >= a[0] else CROSSING


def inside(pt: Pixel, poly: Sequence[Pixel]) -> bool:
    """Even-odd rule: is the point inside the polygon?"""
    x, y = pt
    n = len(poly)
    hit = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xc = xi + (y - yi) * (xj - xi) / ((yj - yi) or 1e-300)
            if x < xc:
                hit = not hit
        j = i
    return hit


def _tri_has(pt: Pixel, a: Pixel, b: Pixel, c: Pixel) -> bool:
    def s(p, q, r):
        return (p[0] - r[0]) * (q[1] - r[1]) - (q[0] - r[0]) * (p[1] - r[1])

    d1, d2, d3 = s(pt, a, b), s(pt, b, c), s(pt, c, a)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


def _segments_cross(p1: Pixel, p2: Pixel, q1: Pixel, q2: Pixel) -> bool:
    def o(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)

    return o(p1, p2, q1) != o(p1, p2, q2) and o(q1, q2, p1) != o(q1, q2, p2)


def judge(points: Sequence[Pixel], poly: Sequence[Pixel], mode: str,
          tris: Iterable[tuple[Pixel, Pixel, Pixel]] = (), polyline: bool = False) -> bool:
    """Is an entity sampled as ``points`` picked by the region?

    INSIDE: every point is inside. CROSSING: any point is inside, or the region
    reaches into one of its triangles (a big face round a small box), or an
    edge's polyline crosses the region's outline."""
    if not points:
        return False
    flags = [inside(p, poly) for p in points]
    if mode == INSIDE:
        return all(flags)
    if any(flags):
        return True
    for t in tris:
        if any(_tri_has(c, *t) for c in poly):
            return True
    if polyline:
        n = len(poly)
        for a, b in zip(points, points[1:]):
            for i in range(n):
                if _segments_cross(a, b, poly[i], poly[(i + 1) % n]):
                    return True
    return False


# ---- sampling OCCT shapes --------------------------------------------------------------
def _mesh(shape) -> None:
    from OCP.BRepMesh import BRepMesh_IncrementalMesh

    from ..geometry import robust

    d = max(robust.diagonal(shape), 1e-6)
    BRepMesh_IncrementalMesh(shape, 0.01 * d, False, 0.5, False)


def face_samples(face, to_pixel: ToPixel) -> tuple[list[Pixel], list[tuple[Pixel, Pixel, Pixel]]]:
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    face = (getattr(TopoDS, "Face_s", None) or TopoDS.Face)(face)
    loc = TopLoc_Location()
    tri = BRep_Tool.Triangulation_s(face, loc)
    if tri is None:
        _mesh(face)
        tri = BRep_Tool.Triangulation_s(face, loc)
    if tri is None:
        return [], []
    trsf = loc.Transformation()
    n = tri.NbNodes()
    step = max(1, n // MAX_FACE_POINTS)
    px: dict[int, Pixel] = {}

    def node(i: int) -> Pixel:
        if i not in px:
            p = tri.Node(i).Transformed(trsf)
            px[i] = to_pixel((p.X(), p.Y(), p.Z()))
        return px[i]

    pts = [node(i) for i in range(1, n + 1, step)]
    tris = []
    nt = tri.NbTriangles()
    tstep = max(1, nt // MAX_FACE_POINTS)
    for k in range(1, nt + 1, tstep):
        a, b, c = tri.Triangle(k).Get()
        tris.append((node(a), node(b), node(c)))
    return pts, tris


def edge_samples(edge, to_pixel: ToPixel) -> list[Pixel]:
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopoDS import TopoDS

    cast = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    e = cast(edge)
    if BRep_Tool.Degenerated_s(e):
        return []
    c = BRepAdaptor_Curve(e)
    t0, t1 = c.FirstParameter(), c.LastParameter()
    out = []
    for i in range(EDGE_POINTS + 1):
        p = c.Value(t0 + (t1 - t0) * i / EDGE_POINTS)
        out.append(to_pixel((p.X(), p.Y(), p.Z())))
    return out


def vertex_sample(vertex, to_pixel: ToPixel) -> list[Pixel]:
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS

    cast = getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex
    p = BRep_Tool.Pnt_s(cast(vertex))
    return [to_pixel((p.X(), p.Y(), p.Z()))]


def pick_region(model, kind: str, poly: Sequence[Pixel], mode: str, to_pixel: ToPixel,
                bodies: Iterable[int] | None = None) -> list[int]:
    """IDs of the entities of ``kind`` the region picks, among ``bodies`` (default: all shown)."""
    from ..core.model import ModelError

    if len(poly) < 3:
        return []
    ids = list(bodies) if bodies is not None else sorted(model.bodies)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    lo, hi = (min(xs), min(ys)), (max(xs), max(ys))
    out: list[int] = []
    for bid in ids:
        body = model.bodies.get(bid)
        if body is None or body.shape is None:
            continue
        if kind == "BODY":
            pts, tris = [], []
            for gid in body.entity_ids.get("FACE", []):
                p, t = face_samples(model.entity_shape("FACE", gid), to_pixel)
                pts += p
                tris += t
            if not pts:  # a wire body: its edges
                for gid in body.entity_ids.get("EDGE", []):
                    pts += edge_samples(model.entity_shape("EDGE", gid), to_pixel)
            if judge(pts, poly, mode, tris, polyline=not tris):
                out.append(bid)
            continue
        for gid in body.entity_ids.get(kind, []):
            try:
                sub = model.entity_shape(kind, gid)
            except ModelError:
                continue
            if kind == "FACE":
                pts, tris = face_samples(sub, to_pixel)
                if mode == INSIDE and pts and not all(lo[0] <= x <= hi[0] and lo[1] <= y <= hi[1] for x, y in pts):
                    continue  # quick no: a point outside the region's bounds
                ok = judge(pts, poly, mode, tris)
            elif kind == "EDGE":
                ok = judge(edge_samples(sub, to_pixel), poly, mode, polyline=True)
            else:
                ok = judge(vertex_sample(sub, to_pixel), poly, mode)
            if ok:
                out.append(gid)
    return out


def ids_text(ids: Sequence[int]) -> str:
    """The id argument of PICK for several IDs: ``3 5 7``."""
    return " ".join(str(i) for i in ids)
