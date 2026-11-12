"""Equation surfaces: x(u,v), y(u,v), z(u,v) fitted to one exact B-spline surface.

The equation is sampled on a grid and a B-spline surface is interpolated
through the grid points, so the result is ordinary exact geometry: it can be
cut, filleted, thickened and exported like any other face.

A surface that closes on itself in both directions (a sphere, a torus, a
shell) is sewn into a solid. To sew it, the one surface is split into four
patches; their shared edges then sew like the edges of any other faces.
"""

from __future__ import annotations

from collections.abc import Callable

from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeSolid,
    BRepBuilderAPI_Sewing,
)
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
from OCP.gp import gp_Pnt
from OCP.ShapeFix import ShapeFix_Solid
from OCP.TopAbs import TopAbs_SHELL
from OCP.TopoDS import TopoDS

from .curves import CurveError, norm, sub
from .robust import is_valid, volume

try:  # OCP 8.x
    from OCP.collections import Array2_gp_Pnt as _Array2Pnt
except ImportError:  # OCP 7.x
    from OCP.TColgp import TColgp_Array2OfPnt as _Array2Pnt  # type: ignore[no-redef]

_as_shell = getattr(TopoDS, "Shell_s", None) or TopoDS.Shell


def grid(fn: Callable[[float, float], tuple], u0: float, u1: float, v0: float, v1: float, nu: int, nv: int):
    return [[tuple(fn(u0 + (u1 - u0) * i / nu, v0 + (v1 - v0) * j / nv)) for j in range(nv + 1)]
            for i in range(nu + 1)]


def fit(points: list[list[tuple]]):
    nu, nv = len(points) - 1, len(points[0]) - 1
    arr = _Array2Pnt(1, nu + 1, 1, nv + 1)
    for i, row in enumerate(points):
        for j, q in enumerate(row):
            arr.SetValue(i + 1, j + 1, gp_Pnt(*map(float, q)))
    mk = GeomAPI_PointsToBSplineSurface()
    try:
        mk.Interpolate(arr)
    except Exception as exc:  # noqa: BLE001 - OCCT throws Standard_Failure on bad grids
        raise CurveError(f"the kernel could not fit a surface through the points ({exc})") from None
    if not mk.IsDone():
        raise CurveError("the kernel could not fit a surface through the points")
    return mk.Surface()


def _closes(points, tol: float) -> tuple[bool, bool]:
    """Whether the grid comes back to its start along u, and along v."""
    cu = all(norm(sub(a, b)) < tol for a, b in zip(points[0], points[-1]))
    cv = all(norm(sub(row[0], row[-1])) < tol for row in points)
    return cu, cv


def _solid(shell):
    so = BRepBuilderAPI_MakeSolid(shell).Solid()
    fx = ShapeFix_Solid(so)
    fx.Perform()
    return fx.Solid()


def param_surface(fn, u0, u1, v0, v1, nu: int = 32, nv: int = 32, thick: float = 0.0):
    """(shape, what) for the equation surface; ``what`` says what it became."""
    pts = grid(fn, u0, u1, v0, v1, nu, nv)
    size = max(norm(q) for row in pts for q in row)
    span = max(norm(sub(a, b)) for row in pts for a, b in zip(row, row[1:]))
    if span < 1e-9:
        raise CurveError("the surface has no size (every point is the same)")
    tol = 1e-7 * max(1.0, size)
    surf = fit(pts)
    cu, cv = _closes(pts, tol)
    if cu and cv or (cu or cv) and _degenerate_ends(pts, cu, tol):
        U0, U1, V0, V1 = surf.Bounds()
        sew = BRepBuilderAPI_Sewing(max(1e-4, 1e-6 * size))
        for i in range(2):
            for j in range(2):
                sew.Add(BRepBuilderAPI_MakeFace(surf, U0 + (U1 - U0) * i / 2, U0 + (U1 - U0) * (i + 1) / 2,
                                                V0 + (V1 - V0) * j / 2, V0 + (V1 - V0) * (j + 1) / 2, 1e-6).Face())
        sew.Perform()
        sewn = sew.SewedShape()
        if sewn.ShapeType() == TopAbs_SHELL and sew.NbFreeEdges() == 0:
            solid = _solid(_as_shell(sewn))
            if is_valid(solid) and volume(solid) > 0:
                if thick:
                    raise CurveError("the surface is closed, so it is already a solid; leave the thickness out")
                return solid, "closed, solid"
    face = BRepBuilderAPI_MakeFace(surf, 1e-6).Face()
    if not thick:
        return face, "surface"
    mk = BRepOffsetAPI_MakeThickSolid()
    mk.MakeThickSolidBySimple(face, float(thick))
    mk.Build()
    if not mk.IsDone() or not is_valid(mk.Shape()):
        raise CurveError(f"the surface cannot be thickened by {thick:g} (it curves too tightly somewhere)")
    shape = mk.Shape()
    if volume(shape) < 0:
        shape.Reverse()
    return shape, f"thickened {thick:g}"


def _degenerate_ends(pts, closed_u: bool, tol: float) -> bool:
    """Closed one way, with both ends of the other way shrunk to a point (a sphere's poles)."""
    if closed_u:  # the v ends: columns 0 and -1 collapse
        ends = ([row[0] for row in pts], [row[-1] for row in pts])
    else:
        ends = (pts[0], pts[-1])
    return all(max(norm(sub(q, e[0])) for q in e) < tol for e in ends)
