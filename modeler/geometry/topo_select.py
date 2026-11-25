"""Picking whole groups of edges and faces (PLAN item 84).

``loop``: the edges round one face that a given edge is part of (the outer
boundary or a hole's rim). ``chain``: the edges joined end to end without a
corner (a filleted rim, a slot outline). ``tangent_faces``: the faces that
meet a given face smoothly, and those that meet them smoothly, and so on
(a face with its fillets, a slot's walls and round ends).

All work on one body's shape and its sub-shapes; the command layer turns the
answers into entity IDs (``SEL, S, EDGE, LOOP, id`` and friends).
"""

from __future__ import annotations

import math

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepGProp import BRepGProp_Face
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_VERTEX, TopAbs_WIRE
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt, gp_Pnt2d, gp_Vec

TANGENT_DEG = 5.0  # two edges (or faces) meeting within this angle meet "without a corner"

_cast = {
    TopAbs_EDGE: getattr(TopoDS, "Edge_s", None) or TopoDS.Edge,
    TopAbs_FACE: getattr(TopoDS, "Face_s", None) or TopoDS.Face,
    TopAbs_VERTEX: getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex,
    TopAbs_WIRE: getattr(TopoDS, "Wire_s", None) or TopoDS.Wire,
}


class SelectError(Exception):
    pass


def _list(lst) -> list:
    return list(lst)


def _ancestors(shape, sub, anc):
    from .analysis import _AncestorMap

    m = _AncestorMap()
    TopExp.MapShapesAndAncestors_s(shape, sub, anc, m)
    return m


def _same(a, b) -> bool:
    return a.IsSame(b)


def _unique(shapes: list) -> list:
    out: list = []
    for s in shapes:
        if not any(_same(s, o) for o in out):
            out.append(s)
    return out


def edge_faces(shape, edge) -> list:
    m = _ancestors(shape, TopAbs_EDGE, TopAbs_FACE)
    i = m.FindIndex(edge)
    if i == 0:
        raise SelectError("that edge is not part of this body")
    return _unique([_cast[TopAbs_FACE](f) for f in _list(m.FindFromIndex(i))])


def _wires(face) -> list:
    out = []
    exp = TopExp_Explorer(face, TopAbs_WIRE)
    while exp.More():
        out.append(_cast[TopAbs_WIRE](exp.Current()))
        exp.Next()
    return out


def _edges(shape) -> list:
    out = []
    exp = TopExp_Explorer(shape, TopAbs_EDGE)
    while exp.More():
        out.append(_cast[TopAbs_EDGE](exp.Current()))
        exp.Next()
    return _unique(out)


def _is_plane(face) -> bool:
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType

    return BRepAdaptor_Surface(face).GetType() == GeomAbs_SurfaceType.GeomAbs_Plane


def loop(shape, edge, face=None) -> list:
    """The edges of the wire of ``face`` that holds ``edge``. Without a face: of the
    faces beside the edge (flat ones first), the one whose outline has the most edges."""
    edge = _cast[TopAbs_EDGE](edge)
    face = _cast[TopAbs_FACE](face) if face is not None else None
    faces = edge_faces(shape, edge)
    if face is None:  # the flat face beside it with the longer outline (a plate's top, not its side)
        flat = [f for f in faces if _is_plane(f)] or faces

        def size(f):
            for w in _wires(f):
                es = _edges(w)
                if any(_same(edge, e) for e in es):
                    return len(es)
            return 0

        face = max(flat, key=size) if flat else None
    elif not any(_same(face, f) for f in faces):
        raise SelectError("that face is not beside that edge")
    if face is None:
        return [edge]
    for w in _wires(face):
        es = _edges(w)
        if any(_same(edge, e) for e in es):
            return es
    return [edge]


def _tangent_at(edge, vertex) -> tuple | None:
    """The edge's direction leaving ``vertex`` (unit), or None for a degenerate edge."""
    if BRep_Tool.Degenerated_s(edge):
        return None
    c = BRepAdaptor_Curve(edge)
    p = BRep_Tool.Pnt_s(vertex)
    t0, t1 = c.FirstParameter(), c.LastParameter()
    a, b = c.Value(t0), c.Value(t1)
    at_start = a.Distance(p) <= b.Distance(p)
    q, v = gp_Pnt(), gp_Vec()
    c.D1(t0 if at_start else t1, q, v)
    n = v.Magnitude()
    if n < 1e-12:
        return None
    s = 1.0 if at_start else -1.0
    return (s * v.X() / n, s * v.Y() / n, s * v.Z() / n)


def _angle(u, v) -> float:
    d = max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1] + u[2] * v[2]))
    return math.degrees(math.acos(d))


def chain(shape, edge, tol_deg: float = TANGENT_DEG) -> list:
    """Edges joined to ``edge`` end to end without a corner (tangent within tol_deg),
    following each joint where exactly one other edge goes on smoothly."""
    edge = _cast[TopAbs_EDGE](edge)
    vmap = _ancestors(shape, TopAbs_VERTEX, TopAbs_EDGE)
    out = [edge]
    todo = [edge]
    while todo:
        e = todo.pop()
        exp = TopExp_Explorer(e, TopAbs_VERTEX)
        vs = []
        while exp.More():
            vs.append(_cast[TopAbs_VERTEX](exp.Current()))
            exp.Next()
        for v in _unique(vs):
            here = _tangent_at(e, v)
            if here is None:
                continue
            i = vmap.FindIndex(v)
            if i == 0:
                continue
            others = [_cast[TopAbs_EDGE](x) for x in _list(vmap.FindFromIndex(i))]
            smooth = []
            for o in _unique(others):
                if _same(o, e):
                    continue
                there = _tangent_at(o, v)
                # leaving the joint along the other edge is going on straight: directions opposite
                if there is not None and _angle(here, tuple(-k for k in there)) <= tol_deg:
                    smooth.append(o)
            if len(smooth) == 1 and not any(_same(smooth[0], x) for x in out):
                out.append(smooth[0])
                todo.append(smooth[0])
    return out


def _normal_on(face, edge) -> tuple | None:
    """The outward normal of ``face`` at the middle of ``edge`` (which lies on it)."""
    face, edge = _cast[TopAbs_FACE](face), _cast[TopAbs_EDGE](edge)
    try:
        c2d = BRep_Tool.CurveOnSurface_s(edge, face, 0.0, 0.0)
        a, b = BRep_Tool.Range_s(edge, face)
    except Exception:  # noqa: BLE001 - no curve on that face
        return None
    if c2d is None:
        return None
    uv = gp_Pnt2d()
    c2d.D0(0.5 * (a + b), uv)
    q, n = gp_Pnt(), gp_Vec()
    BRepGProp_Face(face).Normal(uv.X(), uv.Y(), q, n)
    m = n.Magnitude()
    if m < 1e-12:
        return None
    return (n.X() / m, n.Y() / m, n.Z() / m)


def smooth_joint(face_a, face_b, edge, tol_deg: float = TANGENT_DEG) -> bool:
    na, nb = _normal_on(face_a, edge), _normal_on(face_b, edge)
    if na is None or nb is None:
        return False
    return _angle(na, nb) <= tol_deg


def tangent_faces(shape, face, tol_deg: float = TANGENT_DEG) -> list:
    """``face`` and every face reached from it across edges where the faces meet smoothly."""
    face = _cast[TopAbs_FACE](face)
    emap = _ancestors(shape, TopAbs_EDGE, TopAbs_FACE)
    out = [face]
    todo = [face]
    while todo:
        f = todo.pop()
        for e in _edges(f):
            i = emap.FindIndex(e)
            if i == 0 or BRep_Tool.Degenerated_s(e):
                continue
            for g in _unique([_cast[TopAbs_FACE](x) for x in _list(emap.FindFromIndex(i))]):
                if _same(g, f) or any(_same(g, o) for o in out):
                    continue
                if smooth_joint(f, g, e, tol_deg):
                    out.append(g)
                    todo.append(g)
    return out


def facing_face(shape, edge, view_dir) -> object | None:
    """Of the faces beside ``edge``, the one that faces the viewer most (normal against view_dir)."""
    best, score = None, None
    edge = _cast[TopAbs_EDGE](edge)
    for f in edge_faces(shape, edge):
        n = _normal_on(f, edge)
        if n is None:
            continue
        s = -(n[0] * view_dir[0] + n[1] * view_dir[1] + n[2] * view_dir[2])
        if score is None or s > score:
            best, score = f, s
    return best


_ = TopAbs_REVERSED  # (kept for callers that check face orientation)
