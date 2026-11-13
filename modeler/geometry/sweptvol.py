"""The volume a tool body sweeps through as it moves along a path without
turning (a cutter running along a slot), so it can be cut away.

Three ways, best first:

* a **ball** (one spherical face): a round pipe along the path, with the
  ball at each end. Exact for any path.
* an **upright cylinder** (an end mill: a cylinder and its two flat ends)
  moving square to its axis (a path in a plane across the axis): the
  cylinder's rectangular cross-section swept along the path, kept upright,
  with the cylinder at each end. Exact.
* anything else: copies of the tool close enough along the path that the
  ridges between them are lower than the tolerance, fused. The result says
  how high the ridges can be.
"""

from __future__ import annotations

import math

import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Sphere
from OCP.gp import gp_Dir, gp_Trsf, gp_Vec
from OCP.TopAbs import TopAbs_FACE

from . import robust
from . import sweep as sw
from .curves import CurveError
from .deform import _subs, _as_face


class SweptVolumeError(CurveError):
    pass


def _moved(shape, v):
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(*map(float, v)))
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def _fuse(shapes: list):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

    try:
        from OCP.TopTools import TopTools_ListOfShape as _List
    except ImportError:  # OCP 8
        from OCP.collections import List_TopoDS_Shape as _List

    args, tools = _List(), _List()
    args.Append(shapes[0])
    for s in shapes[1:]:
        tools.Append(s)
    f = BRepAlgoAPI_Fuse()
    f.SetArguments(args)
    f.SetTools(tools)
    f.SetRunParallel(True)
    f.Build()
    if not f.IsDone():
        raise SweptVolumeError("the pieces of the swept volume could not be joined")
    u = ShapeUpgrade_UnifySameDomain(f.Shape(), True, True, True)
    u.Build()
    return u.Shape()


def _kind(tool):
    """('BALL', centre, r) | ('CYL', centre, axis, r, h) | None."""
    faces = [BRepAdaptor_Surface(_as_face(f)) for f in _subs(tool, TopAbs_FACE)]
    types = [f.GetType() for f in faces]
    if types == [GeomAbs_Sphere]:
        s = faces[0].Sphere()
        c = s.Location()
        return ("BALL", np.array([c.X(), c.Y(), c.Z()]), s.Radius())
    if len(types) == 3 and types.count(GeomAbs_Cylinder) == 1 and types.count(GeomAbs_Plane) == 2:
        cyl = faces[types.index(GeomAbs_Cylinder)].Cylinder()
        ax = cyl.Axis()
        a = np.array([ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()])
        o = np.array([ax.Location().X(), ax.Location().Y(), ax.Location().Z()])
        for f in faces:
            if f.GetType() == GeomAbs_Plane:
                n = f.Plane().Axis().Direction()
                if abs(abs(n.X() * a[0] + n.Y() * a[1] + n.Z() * a[2]) - 1) > 1e-9:
                    return None
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(tool, box, False, False)
        lo, hi = box.CornerMin(), box.CornerMax()
        corners = np.array([[x, y, z] for x in (lo.X(), hi.X()) for y in (lo.Y(), hi.Y()) for z in (lo.Z(), hi.Z())])
        along = (corners - o) @ a
        # the box's extent along the axis bounds the cylinder's ends (exactly so for an axis along X, Y or Z)
        t0, t1 = along.min(), along.max()
        centre = o + a * (0.5 * (t0 + t1))
        return ("CYL", centre, a, cyl.Radius(), t1 - t0)
    return None


def swept_volume(tool, path_wire, tol: float | None = None):
    """(shape, how, ridge): the volume the tool sweeps moving along the path
    without turning, how it was made, and the ridge height left (0 when exact).
    The tool is taken where it is: it moves by path(s) - path(start)."""
    ps = sw.PathSampler(path_wire)
    p0 = np.array(ps.at(0.0)[0])
    pend = np.array(ps.at(ps.length)[0])
    size = max(robust.diagonal(tool), 1e-9)
    tol = tol if tol is not None else 2e-3 * size
    kind = _kind(tool)
    end_tool = _moved(tool, pend - p0)
    if kind is not None and kind[0] == "BALL":
        _, c, r = kind
        path = _moved(path_wire, c - p0)
        from .curves import circle

        o, t = sw.PathSampler(sw.as_wire(path, "the path")).at(0.0)
        prof = circle(o, r, t)
        pipe = sw.exact_sweep(prof, sw.as_wire(path, "the path"), "MINTWIST", True, "SWEEPVOL")
        return _fuse([pipe, tool, end_tool]), "exact: a round pipe with the ball at each end", 0.0
    if kind is not None and kind[0] == "CYL":
        _, c, a, r, h = kind
        tans = np.array([ps.at(ps.length * i / 64)[1] for i in range(65)])
        if np.max(np.abs(tans @ a)) < 1e-6:
            from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell

            path = sw.as_wire(_moved(path_wire, c - p0), "the path")
            o, t = sw.PathSampler(path).at(0.0)
            side = np.cross(a, t)
            from .curves import polyline

            corners = [np.asarray(o) + side * sx * r + a * sy * h / 2 for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            prof = polyline([tuple(map(float, q)) for q in corners], closed=True)
            mk = BRepOffsetAPI_MakePipeShell(path)
            mk.SetMode(gp_Dir(*map(float, a)))  # keep the cutter upright: its axis stays the binormal
            mk.Add(prof, False, False)
            mk.Build()
            if mk.IsDone():
                mk.MakeSolid()
                band = mk.Shape()
                return _fuse([band, tool, end_tool]), "exact: the cutter's section swept upright, with the cutter at each end", 0.0
    # copies along the path, close enough that the ridges between them stay low
    r = 0.5 * size
    step = 2 * math.sqrt(max(r * r - (r - tol) ** 2, 1e-18))
    n = max(2, int(math.ceil(ps.length / step)))
    if n > 400:
        raise SweptVolumeError(f"the path is so long for this tool that it would take {n} copies; split the path "
                               "or give a coarser tolerance")
    copies = [_moved(tool, np.array(ps.at(ps.length * i / n)[0]) - p0) for i in range(n + 1)]
    d = ps.length / n
    ridge = r - math.sqrt(max(r * r - d * d / 4, 0.0))
    return _fuse(copies), f"{n + 1} copies along the path", ridge
