"""Surface inspection: how well faces join (CONTINUITY), how a curve bends (curvature combs), and
the places on a body that deserve a second look (INSPECT).

CONTINUITY looks along every edge between two faces at a few points and measures three things:

* the gap between the two faces' surfaces there (G0: they meet);
* the angle between their normals (G1: they are tangent);
* each face's curvature straight across the edge (G2: the curvature carries on).

Each join is then *open* (a gap over the tolerance), *sharp* (a real edge, over KINK_DEG), a
*kink* (a crease of a few degrees: nearly tangent, which is almost always a mistake), *G1*
(tangent, the curvature jumps) or *G2*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.gp import gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp

from . import analysis as an
from . import robust

KINK_DEG = 5.0  # joins between CREASE_DEG and this are kinks: nearly tangent, likely by mistake


@dataclass
class Joint:
    edge: int
    faces: tuple[int, int]
    gap: float
    angle: float
    k_a: float
    k_b: float
    kind: str  # open, sharp, kink, G1, G2
    at: tuple[float, float, float]

    def as_dict(self) -> dict:
        r = lambda x: round(float(x), 6)  # noqa: E731
        return {"edge": self.edge, "faces": list(self.faces), "kind": self.kind, "gap": r(self.gap),
                "angle": r(self.angle), "curvature": [r(self.k_a), r(self.k_b)], "at": [r(x) for x in self.at]}


def continuity(shape, edge_ids: dict, face_ids: dict, tol: float, samples: int = 9) -> tuple[list[Joint], int]:
    """Every join between two faces, judged; and how many edges have one face only (open)."""
    m = an._AncestorMap()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, m)
    flat = 1.0 / (an.FLAT * max(robust.diagonal(shape), 1e-6))
    out, open_edges = [], 0
    for i in range(1, m.Extent() + 1):
        edge = an._as_edge(m.FindKey(i))
        if BRep_Tool.Degenerated_s(edge):
            continue
        uniq = []
        for f in m.FindFromIndex(i):
            if not any(f.IsSame(g) for g in uniq):
                uniq.append(f)
        if len(uniq) == 1:
            if not BRep_Tool.IsClosed_s(edge, an._as_face(uniq[0])):
                open_edges += 1
            continue
        if len(uniq) != 2:
            continue
        gid = an._lookup(edge_ids, edge)
        if gid is None:
            continue
        fa, fb = an._FaceEval(an._as_face(uniq[0])), an._FaceEval(an._as_face(uniq[1]))
        ids = (an._lookup(face_ids, uniq[0]) or 0, an._lookup(face_ids, uniq[1]) or 0)
        c = BRepAdaptor_Curve(edge)
        t0, t1 = c.FirstParameter(), c.LastParameter()
        gap = ang = 0.0
        kab = (0.0, 0.0)
        where = None
        for s in range(samples):
            t = t0 + (t1 - t0) * (s + 0.5) / samples
            p, v = gp_Pnt(), gp_Vec()
            c.D1(t, p, v)
            T = np.array([v.X(), v.Y(), v.Z()])
            if np.linalg.norm(T) < 1e-12:
                continue
            T /= np.linalg.norm(T)
            q = (p.X(), p.Y(), p.Z())
            a, b = fa.at_point(q), fb.at_point(q)
            if a is None or b is None or not (a.ok and b.ok):
                continue
            g = float(np.linalg.norm(np.asarray(a.p) - np.asarray(b.p)))
            d = math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(a.n, b.n))))))
            if g > gap or where is None:
                gap = max(gap, g)
            if d >= ang:
                ang, where = d, q
            ka, kb = a.across(T), b.across(T)
            if abs(ka - kb) > abs(kab[0] - kab[1]):
                kab = (ka, kb)
        if where is None:
            continue
        if gap > tol:
            kind = "open"
        elif ang > KINK_DEG:
            kind = "sharp"
        elif ang > an.CREASE_DEG:
            kind = "kink"
        elif abs(kab[0] - kab[1]) > an.G2_REL * max(abs(kab[0]), abs(kab[1])) + max(flat, 1e-9):
            kind = "G1"
        else:
            kind = "G2"
        out.append(Joint(gid, ids, gap, ang, kab[0], kab[1], kind, where))
    out.sort(key=lambda j: j.edge)
    return out, open_edges


def smallest_radius(shape, face_ids: dict) -> tuple[float, int | None, tuple | None]:
    """The tightest bend on the body's faces: (radius, face ID, where); inf when all is flat."""
    m = an.mesh(shape)
    k = np.nan_to_num(np.maximum(np.abs(m.k1), np.abs(m.k2)), nan=0.0)
    if not len(k) or k.max() <= 0:
        return math.inf, None, None
    i = int(np.argmax(k))
    # the face the node is on (the first triangle using it)
    tri = int(np.flatnonzero((m.tris == i).any(axis=1))[0])
    face = m.faces[m.face_of_tri[tri]]
    return 1.0 / k[i], an._lookup(face_ids, face), tuple(float(x) for x in m.nodes[i])


# ---- curvature combs ---------------------------------------------------------------------------------
@dataclass
class Comb:
    edge: int
    points: np.ndarray  # along the curve
    tips: np.ndarray  # the comb's tips (point + scale * curvature * normal)
    curvature: np.ndarray
    inflections: int

    @property
    def tightest(self) -> float:
        k = float(np.abs(self.curvature).max()) if len(self.curvature) else 0.0
        return math.inf if k <= 0 else 1.0 / k


def comb(edge, gid: int, n: int = 40, scale: float = 0.0, size: float = 1.0) -> Comb:
    """Curvature comb of one edge: at ``n`` points the curvature, drawn as a tooth along the
    curve's normal (towards the centre of the bend, outward for display), ``scale`` long per unit
    curvature (0: the largest tooth is a tenth of ``size``)."""
    from OCP.BRepLProp import BRepLProp_CLProps

    c = BRepAdaptor_Curve(an._as_edge(edge))
    t0, t1 = c.FirstParameter(), c.LastParameter()
    pts, nrm, ks, bis = [], [], [], []
    for s in range(n + 1):
        t = t0 + (t1 - t0) * s / n
        pr = BRepLProp_CLProps(c, t, 2, 1e-9)
        p = pr.Value()
        k = pr.Curvature() if pr.IsTangentDefined() else 0.0
        d = np.zeros(3)
        b = np.zeros(3)
        if k > 1e-12:
            from OCP.gp import gp_Dir

            nd = gp_Dir()
            pr.Normal(nd)
            d = np.array([nd.X(), nd.Y(), nd.Z()])
            v = gp_Vec()
            c.D1(t, gp_Pnt(), v)
            b = np.cross([v.X(), v.Y(), v.Z()], d)
            b = b / max(np.linalg.norm(b), 1e-300)
        pts.append((p.X(), p.Y(), p.Z()))
        nrm.append(d)
        ks.append(k)
        bis.append(b)
    # a flat curve bends to one side or the other: sign the curvature by its binormal, so a change of
    # side (an inflection) shows; a curve that twists in space has no sides
    bis = np.array(bis)
    good = np.linalg.norm(bis, axis=1) > 0.5
    if good.sum() > 1:
        ref = bis[good][0]
        dots = bis[good] @ ref
        if (np.abs(dots) > 0.999).all():
            flip = np.zeros(len(ks), dtype=bool)
            flip[np.flatnonzero(good)[dots < 0]] = True
            ks = [-k if f else k for k, f in zip(ks, flip)]
    pts, nrm, ks = np.array(pts), np.array(nrm), np.array(ks)
    big = float(np.abs(ks).max()) if len(ks) else 0.0
    sc = scale or (0.1 * size / big if big > 0 else 0.0)
    tips = pts - nrm * (np.abs(ks) * sc)[:, None]  # the teeth stand outside the bend
    signs = np.sign(ks[np.abs(ks) > 1e-9 * max(big, 1e-30)])
    inflections = int((np.diff(signs) != 0).sum()) if len(signs) > 1 else 0
    return Comb(gid, pts, tips, ks, inflections)


def comb_shape(combs: list[Comb]):
    """The teeth and the line through their tips, as edges to draw."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.TopoDS import TopoDS_Compound

    b, comp = BRep_Builder(), TopoDS_Compound()
    b.MakeCompound(comp)

    def seg(a, z):
        if np.linalg.norm(np.asarray(a) - np.asarray(z)) > 1e-9:
            b.Add(comp, BRepBuilderAPI_MakeEdge(gp_Pnt(*map(float, a)), gp_Pnt(*map(float, z))).Edge())

    for cb in combs:
        for p, q in zip(cb.points, cb.tips):
            seg(p, q)
        for q0, q1 in zip(cb.tips[:-1], cb.tips[1:]):
            seg(q0, q1)
    return comp


# ---- INSPECT: places worth a second look ---------------------------------------------------------
def inspect(shape, edge_ids: dict, face_ids: dict, face_list: list[int], tol: float) -> dict:
    """Kinks, gaps, open edges, the tightest bend, the thinnest wall, slivers and tiny faces."""
    from . import healing

    size = max(robust.diagonal(shape), 1e-9)
    joints, open_edges = continuity(shape, edge_ids, face_ids, tol)
    r, rf, rat = smallest_radius(shape, face_ids)
    flaws = healing.inspect(shape, tol)
    out: dict = {"tolerance": tol, "joins": len(joints), "open_edges": open_edges,
                 "kinks": [j.as_dict() for j in joints if j.kind == "kink"],
                 "gaps": [j.as_dict() for j in joints if j.kind == "open"],
                 "g1": [j.edge for j in joints if j.kind == "G1"],
                 "smallest_radius": None if math.isinf(r) else {"radius": round(r, 6), "face": rf,
                                                                 "at": [round(x, 6) for x in rat]},
                 "tight": bool(not math.isinf(r) and r < 1e-3 * size),
                 "slivers": [{"face": face_list[i] if i < len(face_list) else i + 1, "width": round(w, 9)}
                             for i, w in flaws.slivers],
                 "tiny_faces": []}
    areas = []
    from .healing import _area, _indexed

    for i, f in enumerate(_indexed(shape, TopAbs_FACE)):
        areas.append((i, _area(f)))
    total = sum(a for _, a in areas) or 1.0
    out["tiny_faces"] = [face_list[i] if i < len(face_list) else i + 1 for i, a in areas if a < 1e-6 * total]
    if robust.solids(shape):
        from . import probe as pr

        try:
            spots = pr.wall_thickness(shape, 3)
            if spots:
                w = min(spots, key=lambda s: s.thickness)
                out["thinnest_wall"] = {"t": round(float(w.thickness), 6), "face": an._lookup(face_ids, w.face),
                                        "at": [round(float(x), 6) for x in w.point]}
        except Exception:  # noqa: BLE001 - a measurement that fails is left out, not a failure
            pass
    out["suspicious"] = (len(out["kinks"]) + len(out["gaps"]) + len(out["slivers"]) + len(out["tiny_faces"])
                         + (1 if out["tight"] else 0) + (1 if open_edges and robust.solids(shape) else 0))
    return out
