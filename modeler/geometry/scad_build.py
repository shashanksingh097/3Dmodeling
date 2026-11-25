"""The shapes of OpenSCAD's modules (geometry/scad.py reads the file), built with OCP."""

from __future__ import annotations

import math

import numpy as np
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_GTransform,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon,
    BRepBuilderAPI_Sewing,
    BRepBuilderAPI_Transform,
)
from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCone,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakePrism,
    BRepPrimAPI_MakeRevol,
    BRepPrimAPI_MakeSphere,
)
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_GTrsf, gp_Mat, gp_Pnt, gp_Trsf, gp_Vec, gp_XYZ

NOT_READ = {"hull": "hull()", "minkowski": "minkowski()", "offset": "offset()", "text": "text()",
            "import": "import()", "surface": "surface()", "projection": "projection()", "resize": "resize()",
            "roof": "roof()"}


class BuildError(Exception):
    pass


def _vec3(v, default=0.0) -> list[float]:
    if v is None:
        return [default] * 3
    if isinstance(v, (int, float)):
        return [float(v)] * 3
    v = [float(x) for x in v] + [default] * 3
    return v[:3]


def _num(v, name: str) -> float:
    if not isinstance(v, (int, float)):
        raise BuildError(f"{name} must be a number")
    return float(v)


def union(shapes: list):
    shapes = [s for s in shapes if s is not None]
    if not shapes:
        return None
    out = shapes[0]
    for s in shapes[1:]:
        op = BRepAlgoAPI_Fuse(out, s)
        if not op.IsDone():
            raise BuildError("a union failed in the kernel")
        out = op.Shape()
    if len(shapes) > 1:
        from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

        u = ShapeUpgrade_UnifySameDomain(out, True, True, False)
        u.Build()
        out = u.Shape()
    return out


def matrix(shape, m: np.ndarray):
    """A 4 x 4 matrix on a shape: a plain move when it keeps shapes the same (rotation, mirror, even
    scale), else a general transform."""
    a = m[:3, :3]
    s = abs(np.linalg.det(a)) ** (1 / 3)
    if s > 1e-12 and np.allclose(a.T @ a, (s * s) * np.eye(3), atol=1e-9 * max(1.0, s * s)):
        t = gp_Trsf()
        # gp_Trsf takes a rotation (or mirror) with one scale factor
        t.SetValues(float(a[0, 0]), float(a[0, 1]), float(a[0, 2]), float(m[0, 3]),
                    float(a[1, 0]), float(a[1, 1]), float(a[1, 2]), float(m[1, 3]),
                    float(a[2, 0]), float(a[2, 1]), float(a[2, 2]), float(m[2, 3]))
        return BRepBuilderAPI_Transform(shape, t, True).Shape()
    g = gp_GTrsf()
    g.SetVectorialPart(gp_Mat(*(float(a[i, j]) for i in range(3) for j in range(3))))
    g.SetTranslationPart(gp_XYZ(float(m[0, 3]), float(m[1, 3]), float(m[2, 3])))
    return BRepBuilderAPI_GTransform(shape, g, True).Shape()


def _rot(axis: str, deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    r = np.eye(4)
    i, j = {"x": (1, 2), "y": (2, 0), "z": (0, 1)}[axis]
    r[i, i], r[i, j], r[j, i], r[j, j] = c, -s, s, c
    return r


def rotation(a, v) -> np.ndarray:
    if v is not None and isinstance(a, (int, float)):
        axis = np.array(_vec3(v), float)
        n = np.linalg.norm(axis)
        if n < 1e-12:
            return np.eye(4)
        x, y, z = axis / n
        t = math.radians(float(a))
        c, s, C = math.cos(t), math.sin(t), 1 - math.cos(t)
        r = np.eye(4)
        r[:3, :3] = [[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]]
        return r
    if isinstance(a, (int, float)):
        return _rot("z", float(a))
    ax, ay, az = _vec3(a)
    return _rot("z", az) @ _rot("y", ay) @ _rot("x", ax)  # x first, then y, then z


def _polygon_face(pts, paths=None):
    if not pts or len(pts) < 3:
        raise BuildError("a polygon needs at least 3 points")
    loops = paths or [list(range(len(pts)))]
    faces = []
    for k, loop in enumerate(loops):
        poly = BRepBuilderAPI_MakePolygon()
        for i in loop:
            x, y = float(pts[int(i)][0]), float(pts[int(i)][1])
            poly.Add(gp_Pnt(x, y, 0.0))
        poly.Close()
        if not poly.IsDone():
            raise BuildError("a polygon's points do not make an outline")
        mk = BRepBuilderAPI_MakeFace(poly.Wire(), True)
        if not mk.IsDone():
            raise BuildError("a polygon's outline is not flat or crosses itself")
        faces.append(mk.Face())
    out = faces[0]
    for f in faces[1:]:  # the other paths are holes
        out = BRepAlgoAPI_Cut(out, f).Shape()
    return out


def _circle_face(r: float):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.gp import gp_Circ

    e = BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), r)).Edge()
    return BRepBuilderAPI_MakeFace(BRepBuilderAPI_MakeWire(e).Wire(), True).Face()


def polyhedron(points, faces):
    sew = BRepBuilderAPI_Sewing(1e-6)
    for f in faces:
        poly = BRepBuilderAPI_MakePolygon()
        for i in f:
            poly.Add(gp_Pnt(*(float(c) for c in points[int(i)])))
        poly.Close()
        mk = BRepBuilderAPI_MakeFace(poly.Wire(), True)
        if not mk.IsDone():
            raise BuildError("a polyhedron face is not flat")
        sew.Add(mk.Face())
    sew.Perform()
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
    from OCP.BRepLib import BRepLib
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    ex = TopExp_Explorer(sew.SewedShape(), TopAbs_SHELL)
    if not ex.More():
        raise BuildError("the polyhedron's faces do not close")
    shell = (getattr(TopoDS, "Shell_s", None) or TopoDS.Shell)(ex.Current())
    solid = BRepBuilderAPI_MakeSolid(shell).Solid()
    (getattr(BRepLib, "OrientClosedSolid_s", None) or BRepLib.OrientClosedSolid)(solid)
    return solid


def build(name: str, arg, named: dict, kids, line: int) -> list:
    """The objects one module call makes (a list: OpenSCAD's for loops give several)."""
    if name in NOT_READ:
        raise BuildError(f"{NOT_READ[name]} is not read here")
    if name == "cube":
        size = _vec3(arg("size", 0, 1.0), 1.0)
        if min(size) <= 0:
            raise BuildError("the size must be more than 0")
        s = BRepPrimAPI_MakeBox(*size).Shape()
        if arg("center", 1, False):
            s = matrix(s, _move([-c / 2 for c in size]))
        return [s]
    if name == "sphere":
        r = arg("r", 0, None)
        r = float(arg("d", 99, 2.0)) / 2 if r is None else _num(r, "r")
        return [BRepPrimAPI_MakeSphere(r).Shape()] if r > 0 else []
    if name == "cylinder":
        h = _num(arg("h", 0, 1.0), "h")
        r = named.get("r")
        d = named.get("d")
        r1 = named.get("r1", arg("r1", 1, None))
        r2 = named.get("r2", arg("r2", 2, None))
        if named.get("d1") is not None:
            r1 = named["d1"] / 2
        if named.get("d2") is not None:
            r2 = named["d2"] / 2
        base = r if r is not None else (d / 2 if d is not None else 1.0)
        r1 = base if r1 is None else r1
        r2 = base if r2 is None else r2
        if h <= 0 or (r1 <= 0 and r2 <= 0):
            return []
        ax = gp_Ax2(gp_Pnt(0, 0, -h / 2 if arg("center", 99, False) else 0), gp_Dir(0, 0, 1))
        if abs(r1 - r2) < 1e-12:
            return [BRepPrimAPI_MakeCylinder(ax, float(r1), h).Shape()]
        return [BRepPrimAPI_MakeCone(ax, float(r1), float(r2), h).Shape()]
    if name == "polyhedron":
        pts, faces = arg("points", 0), arg("faces", 1) or named.get("triangles")
        if not pts or not faces:
            raise BuildError("give points and faces")
        return [polyhedron(pts, faces)]
    if name == "square":
        size = _vec3(arg("size", 0, 1.0), 1.0)
        f = _polygon_face([(0, 0), (size[0], 0), (size[0], size[1]), (0, size[1])])
        if arg("center", 1, False):
            f = matrix(f, _move([-size[0] / 2, -size[1] / 2, 0]))
        return [f]
    if name == "circle":
        r = arg("r", 0, None)
        r = float(arg("d", 99, 2.0)) / 2 if r is None else _num(r, "r")
        return [_circle_face(r)] if r > 0 else []
    if name == "polygon":
        return [_polygon_face(arg("points", 0), arg("paths", 1))]
    if name == "linear_extrude":
        h = _num(arg("height", 0, 100.0), "height")
        if float(named.get("twist", 0) or 0) != 0 or _vec3(named.get("scale", 1.0), 1.0)[:2] != [1.0, 1.0]:
            raise BuildError("twist and scale are not read; extrude straight")
        flat = union(kids())
        if flat is None:
            return []
        s = BRepPrimAPI_MakePrism(flat, gp_Vec(0, 0, h)).Shape()
        if arg("center", 99, False):
            s = matrix(s, _move([0, 0, -h / 2]))
        return [s]
    if name == "rotate_extrude":
        ang = float(arg("angle", 99, 360.0))
        flat = union(kids())
        if flat is None:
            return []
        flat = matrix(flat, _rot("x", 90))  # the drawing's y is the height, its x the radius
        axis = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
        if abs(ang) >= 360:
            return [BRepPrimAPI_MakeRevol(flat, axis).Shape()]
        return [BRepPrimAPI_MakeRevol(flat, axis, math.radians(ang)).Shape()]
    if name in ("translate", "rotate", "scale", "mirror", "multmatrix"):
        if name == "translate":
            m = _move(_vec3(arg("v", 0)))
        elif name == "rotate":
            m = rotation(arg("a", 0, 0.0), arg("v", 1))
        elif name == "scale":
            sv = _vec3(arg("v", 0, 1.0), 1.0)
            if min(abs(c) for c in sv) < 1e-12:
                raise BuildError("a scale of 0 flattens the shape")
            m = np.diag([*sv, 1.0])
        elif name == "mirror":
            n = np.array(_vec3(arg("v", 0, [1, 0, 0])), float)
            ln = np.linalg.norm(n)
            m = np.eye(4)
            if ln > 1e-12:
                n /= ln
                m[:3, :3] = np.eye(3) - 2 * np.outer(n, n)
        else:
            mm = np.array(arg("m", 0), float)
            m = np.eye(4)
            m[:mm.shape[0], :mm.shape[1]] = mm
        s = union(kids())
        return [matrix(s, m)] if s is not None else []
    if name in ("union", "color", "render", "group", "echo", "assert"):
        s = union(kids())
        return [s] if s is not None else []
    if name == "difference":
        objs = kids()
        if not objs:
            return []
        out = objs[0]
        rest = union(objs[1:])
        if rest is not None:
            op = BRepAlgoAPI_Cut(out, rest)
            if not op.IsDone():
                raise BuildError("the difference failed in the kernel")
            out = op.Shape()
        return [out]
    if name == "intersection":
        objs = kids()
        if not objs:
            return []
        out = objs[0]
        for s in objs[1:]:
            op = BRepAlgoAPI_Common(out, s)
            if not op.IsDone():
                raise BuildError("the intersection failed in the kernel")
            out = op.Shape()
        return [out]
    raise BuildError(f"unknown module {name}()")


def _move(v) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = v
    return m
