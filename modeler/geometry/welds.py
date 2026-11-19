"""Weld beads where two parts meet (WELD).

The joint is where the two solids' surfaces cross or touch: the section of
one with the other (for parts resting face to face, the outline of the
patch where they touch). A bead is a round tube of the weld size across,
swept along each joint edge, with a ball at each end so the pieces join,
fused into one solid. Its length is the joint's length.
"""

from __future__ import annotations


class WeldError(ValueError):
    pass


def _edges(shape) -> list:
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    as_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    out = []
    ex = TopExp_Explorer(shape, TopAbs_EDGE)
    while ex.More():
        out.append(as_edge(ex.Current()))
        ex.Next()
    return out


def joint(a, b) -> list:
    """The edges where two solids meet (empty when they do not touch)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section

    sec = BRepAlgoAPI_Section(a, b)
    sec.Build()
    if not sec.IsDone():
        raise WeldError("the joint could not be found")
    return _edges(sec.Shape())


def length(edges) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    total = 0.0
    for e in edges:
        g = GProp_GProps()
        BRepGProp.LinearProperties_s(e, g)
        total += g.Mass()
    return total


def bead(edges, size: float):
    """A round bead of diameter ``size`` along the edges, as one solid."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
    from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt, gp_Vec
    from .contact import TopTools_ListOfShape

    if size <= 0:
        raise WeldError("the weld size must be positive")
    r = size / 2
    pieces = []
    ends: list[gp_Pnt] = []
    for e in edges:
        c = BRepAdaptor_Curve(e)
        t0, t1 = c.FirstParameter(), c.LastParameter()
        p0, v0 = gp_Pnt(), gp_Vec()
        c.D1(t0, p0, v0)
        if v0.Magnitude() < 1e-12 or c.Value(t0).Distance(c.Value(t1)) + abs(t1 - t0) < 1e-9:
            continue
        circ = BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(p0, gp_Dir(v0)), r)).Edge()).Wire()
        prof = BRepBuilderAPI_MakeFace(circ, True).Face()
        path = BRepBuilderAPI_MakeWire(e).Wire()
        pipe = BRepOffsetAPI_MakePipe(path, prof)
        pipe.Build()
        if not pipe.IsDone():
            raise WeldError("a bead could not be swept along the joint")
        pieces.append(pipe.Shape())
        for q in (c.Value(t0), c.Value(t1)):
            if not any(q.Distance(o) < 1e-6 * max(1.0, size) for o in ends):
                ends.append(q)
    if not pieces:
        raise WeldError("the joint has no edges to weld along")
    # (a ball just bigger than the tube: the same size would touch the tube's end tangentially, which
    # booleans handle badly)
    pieces += [BRepPrimAPI_MakeSphere(q, r * 1.06).Shape() for q in ends]
    if len(pieces) == 1:
        return pieces[0]
    fuse = BRepAlgoAPI_Fuse()
    args, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    args.Append(pieces[0])
    for s in pieces[1:]:
        tools.Append(s)
    fuse.SetArguments(args)
    fuse.SetTools(tools)
    fuse.SetFuzzyValue(1e-5 * max(1.0, size))
    fuse.Build()
    if not fuse.IsDone():
        raise WeldError("the bead pieces could not be joined")
    return fuse.Shape()
