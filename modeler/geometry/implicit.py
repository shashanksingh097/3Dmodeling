"""Implicit shapes (M6b): a shape is where a field f(x, y, z) is at most 0.

A field is written in the script language (``SQRT(x**2 + y**2 + z**2) - 10``)
and compiled here to a numpy function, so a million grid points take a
fraction of a second. Building blocks (balls, boxes, rods, gyroids ...) give
fields that are distances, or close to it, so ``f - 1`` grows a shape by
about 1 and ``ABS(f) - t/2`` makes a wall of thickness t around a surface.
Smooth blends (``SMIN``, ``SMAX``) join shapes with a fillet of a given size.

``mesh_field`` turns a field into a closed triangle mesh on a grid, by
marching tetrahedra: each grid cube is cut into six tetrahedra that share
the cube's long diagonal, the same way in every cube, so the triangles of
neighbouring cubes meet edge to edge and the mesh is closed (manifold).
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

Field = Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray]

# the most grid points one shape may use (about 160 per side)
MAX_POINTS = 4_500_000


class FieldError(Exception):
    pass


@dataclass(frozen=True)
class FieldDef:
    """A named field: its text and the box it was meshed in (kept in the model)."""

    name: str
    text: str
    box: tuple[float, float, float, float, float, float]
    fn: Field = None  # type: ignore[assignment]


# ---- building blocks ------------------------------------------------------------
def _rad(a):
    return np.radians(a)


def _tpms(kind: str):
    def fn(x, y, z, cell, *off):
        if not np.all(np.asarray(cell) > 0):
            raise FieldError(f"{kind}: the cell size must be positive")
        ox, oy, oz = (list(off) + [0.0, 0.0, 0.0])[:3]
        k = 2 * np.pi / cell
        u, v, w = k * (x - ox), k * (y - oy), k * (z - oz)
        if kind == "GYROID":
            g = np.sin(u) * np.cos(v) + np.sin(v) * np.cos(w) + np.sin(w) * np.cos(u)
            scale = 1 / 1.5  # the gradient of the gyroid is about 1.5 k near its surface
        elif kind == "SCHWARZ":
            g = np.cos(u) + np.cos(v) + np.cos(w)
            scale = 1 / 1.7
        else:  # DIAMOND
            g = (np.sin(u) * np.sin(v) * np.sin(w) + np.sin(u) * np.cos(v) * np.cos(w)
                 + np.cos(u) * np.sin(v) * np.cos(w) + np.cos(u) * np.cos(v) * np.sin(w))
            scale = 1 / 1.4
        return g * scale / k  # about the distance to the surface, near it

    return fn


def _ball(x, y, z, cx, cy, cz, r):
    return np.sqrt((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2) - r


def _box(x, y, z, cx, cy, cz, sx, sy, sz, *rnd):
    r = rnd[0] if rnd else 0.0
    qx, qy, qz = np.abs(x - cx) - sx / 2 + r, np.abs(y - cy) - sy / 2 + r, np.abs(z - cz) - sz / 2 + r
    out = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2)
    return out + np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0) - r


def _rod(x, y, z, x1, y1, z1, x2, y2, z2, r):
    return seg_dist(x, y, z, (x1, y1, z1), (x2, y2, z2)) - r


def seg_dist(x, y, z, a, b):
    ax, ay, az = a
    dx, dy, dz = b[0] - ax, b[1] - ay, b[2] - az
    ll = dx * dx + dy * dy + dz * dz
    px, py, pz = x - ax, y - ay, z - az
    t = np.clip((px * dx + py * dy + pz * dz) / (ll if ll > 0 else 1.0), 0.0, 1.0)
    return np.sqrt((px - t * dx) ** 2 + (py - t * dy) ** 2 + (pz - t * dz) ** 2)


def _torus(x, y, z, cx, cy, cz, big, small):
    q = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) - big
    return np.sqrt(q * q + (z - cz) ** 2) - small


def _cylz(x, y, z, cx, cy, r):
    return np.sqrt((x - cx) ** 2 + (y - cy) ** 2) - r


def smin(a, b, k):
    """Smooth minimum (a union with a fillet about k wide)."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def _min(*args):
    out = args[0]
    for a in args[1:]:
        out = np.minimum(out, a)
    return out


def _max(*args):
    out = args[0]
    for a in args[1:]:
        out = np.maximum(out, a)
    return out


# name -> (function, needs x,y,z first, allowed arg counts)
_XYZ_FUNCS: dict[str, tuple[Callable, tuple[int, ...]]] = {
    "GYROID": (_tpms("GYROID"), (1, 4)),
    "SCHWARZ": (_tpms("SCHWARZ"), (1, 4)),
    "DIAMOND": (_tpms("DIAMOND"), (1, 4)),
    "BALL": (_ball, (4,)),
    "BOX": (_box, (6, 7)),
    "ROD": (_rod, (7,)),
    "TORUS": (_torus, (5,)),
    "CYLZ": (_cylz, (3,)),
}
_PLAIN_FUNCS: dict[str, tuple[Callable, tuple[int, ...]]] = {
    "SIN": (lambda a: np.sin(_rad(a)), (1,)),
    "COS": (lambda a: np.cos(_rad(a)), (1,)),
    "TAN": (lambda a: np.tan(_rad(a)), (1,)),
    "ASIN": (lambda a: np.degrees(np.arcsin(a)), (1,)),
    "ACOS": (lambda a: np.degrees(np.arccos(a)), (1,)),
    "ATAN": (lambda a: np.degrees(np.arctan(a)), (1,)),
    "ATAN2": (lambda a, b: np.degrees(np.arctan2(a, b)), (2,)),
    "SQRT": (lambda a: np.sqrt(np.maximum(a, 0)), (1,)),
    "ABS": (np.abs, (1,)),
    "EXP": (np.exp, (1,)),
    "LOG": (lambda a: np.log(np.maximum(a, 1e-300)), (1,)),
    "MIN": (_min, tuple(range(2, 9))),
    "MAX": (_max, tuple(range(2, 9))),
    "SMIN": (smin, (3,)),
    "SMAX": (smax, (3,)),
    "SDIFF": (lambda a, b, k: smax(a, -b, k), (3,)),
    "CLAMP": (lambda a, lo, hi: np.clip(a, lo, hi), (3,)),
    "MOD": (lambda a, b: np.mod(a, b), (2,)),
    "SIGN": (np.sign, (1,)),
}
FUNCTION_NAMES = sorted(set(_XYZ_FUNCS) | set(_PLAIN_FUNCS))
_CONSTANTS = {"PI": math.pi, "E": math.e}
_BIN = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide, ast.Pow: np.power}


def compile_field(text: str, lookup: Callable[[str], float], fields: dict[str, FieldDef]) -> Field:
    """The field written in ``text`` as a numpy function of x, y, z arrays.

    ``lookup(NAME)`` gives a parameter's value (raise KeyError if there is
    none); ``fields`` are earlier named fields, used by their name."""
    src = text.strip()
    if not src:
        raise FieldError("the field is empty")
    if "^" in src:
        raise FieldError("use ** for powers (x**2), not ^")
    try:
        tree = ast.parse(src, mode="eval").body
    except SyntaxError as exc:
        raise FieldError(f"cannot read {src!r}: {exc.msg}") from None

    def build(n: ast.AST) -> Callable:
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            v = float(n.value)
            return lambda x, y, z: v
        if isinstance(n, ast.Name):
            key = n.id.upper()
            if key == "X":
                return lambda x, y, z: x
            if key == "Y":
                return lambda x, y, z: y
            if key == "Z":
                return lambda x, y, z: z
            if key in fields:
                fd = fields[key]
                if fd.fn is None:  # came back from the rebuild helper without its function
                    object.__setattr__(fd, "fn", compile_field(fd.text, lookup, fields))
                f = fd.fn
                return lambda x, y, z: f(x, y, z)
            try:
                v = lookup(key)
            except KeyError:
                v = _CONSTANTS.get(key)
                if v is None:
                    raise FieldError(f"unknown name {n.id!r} (x, y, z, a parameter, or a field made by IMPLICIT)") from None
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise FieldError(f"{n.id} is not a number")
            v = float(v)
            return lambda x, y, z: v
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            a = build(n.operand)
            return (lambda x, y, z: -a(x, y, z)) if isinstance(n.op, ast.USub) else a
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            a, b, op = build(n.left), build(n.right), _BIN[type(n.op)]
            return lambda x, y, z: op(a(x, y, z), b(x, y, z))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and not n.keywords:
            name = n.func.id.upper()
            args = [build(a) for a in n.args]
            if name in _XYZ_FUNCS:
                fn, counts = _XYZ_FUNCS[name]
                if len(args) not in counts:
                    raise FieldError(f"{name}() takes {' or '.join(map(str, counts))} numbers, got {len(args)}")
                consts = []
                for a in args:  # building blocks take plain numbers (centres, sizes)
                    v = a(0.0, 0.0, 0.0)
                    if np.ndim(v) or a(1.0, 2.0, 3.0) != v:
                        raise FieldError(f"{name}() takes numbers, not expressions in x, y, z")
                    consts.append(float(v))
                return lambda x, y, z: fn(x, y, z, *consts)
            if name in _PLAIN_FUNCS:
                fn, counts = _PLAIN_FUNCS[name]
                if len(args) not in counts:
                    raise FieldError(f"{name}() takes {' or '.join(map(str, counts))} argument(s), got {len(args)}")
                return lambda x, y, z: fn(*(a(x, y, z) for a in args))
            raise FieldError(f"unknown function {name}() in a field (use {', '.join(FUNCTION_NAMES)})")
        raise FieldError(f"{type(n).__name__} is not allowed in a field")

    f = build(tree)

    def field(x, y, z):
        with np.errstate(all="ignore"):
            v = f(x, y, z)
        return np.broadcast_to(np.asarray(v, dtype=float), np.shape(x))

    return field


# ---- meshing ----------------------------------------------------------------------
# the six tetrahedra of a cube, all around the diagonal from corner 0 to corner 6
_CORNERS = np.array([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)])
_TETS = np.array([(0, 1, 2, 6), (0, 2, 3, 6), (0, 3, 7, 6), (0, 7, 4, 6), (0, 4, 5, 6), (0, 5, 1, 6)])


def grid_for(box, cell: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Grid lines covering the box with one spare line outside on every side."""
    lo, hi = np.array(box[:3], float), np.array(box[3:], float)
    if np.any(hi <= lo):
        raise FieldError("the box must have a positive size along x, y and z")
    if cell <= 0:
        raise FieldError("the cell size must be positive")
    n = np.ceil((hi - lo) / cell).astype(int) + 1
    total = int(np.prod(n + 2))
    if total > MAX_POINTS:
        smallest = float((np.prod(hi - lo) / MAX_POINTS) ** (1 / 3)) * 1.05
        raise FieldError(f"a cell of {cell:g} needs {total:,} grid points, more than {MAX_POINTS:,}; "
                         f"use a cell of at least {smallest:.3g}, or a smaller box")
    axes = [lo[i] - cell + cell * np.arange(n[i] + 2) for i in range(3)]
    return axes[0], axes[1], axes[2]


def sample(fn: Field, box, cell: float) -> tuple[np.ndarray, tuple]:
    """The field on the grid (x varies slowest); the spare outside layer is
    forced to 'outside', so the shape is closed where the box cuts it."""
    xs, ys, zs = grid_for(box, cell)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    vals = np.array(fn(X, Y, Z), dtype=float)
    if not np.isfinite(vals).any():
        raise FieldError("the field has no value anywhere in the box (a division by zero?)")
    vals[~np.isfinite(vals)] = cell
    # cut by the box exactly at its faces (a flat cap where the shape reaches it)
    lo, hi = box[:3], box[3:]
    cut = np.maximum.reduce([lo[0] - X, X - hi[0], lo[1] - Y, Y - hi[1], lo[2] - Z, Z - hi[2]])
    vals = np.maximum(vals, cut)
    big = max(cell, 1e-9)
    vals[0, :, :] = vals[-1, :, :] = big
    vals[:, 0, :] = vals[:, -1, :] = big
    vals[:, :, 0] = vals[:, :, -1] = big
    vals[vals == 0] = 1e-12 * big  # a point exactly on the surface would make empty triangles
    return vals, (xs, ys, zs)


def march(vals: np.ndarray, axes) -> tuple[np.ndarray, np.ndarray]:
    """Closed triangle mesh of where ``vals`` < 0 (marching tetrahedra)."""
    xs, ys, zs = axes
    nx, ny, nz = vals.shape
    inside = vals < 0
    # cubes the surface passes through: some corners inside, some not
    c = [inside[i:nx - 1 + i, j:ny - 1 + j, k:nz - 1 + k] for i, j, k in _CORNERS]
    anyin = np.logical_or.reduce(c)
    allin = np.logical_and.reduce(c)
    ci, cj, ck = np.nonzero(anyin & ~allin)
    if len(ci) == 0:
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.int64)
    flat = vals.reshape(-1)

    def pid(i, j, k):
        return (i * ny + j) * nz + k

    corner_ids = np.stack([pid(ci + a, cj + b, ck + d) for a, b, d in _CORNERS], axis=1)  # (cubes, 8)
    tets = corner_ids[:, _TETS].reshape(-1, 4)  # (cubes*6, 4)
    tv = flat[tets]
    tin = tv < 0
    cnt = tin.sum(axis=1)
    keep = (cnt > 0) & (cnt < 4)
    tets, tv, tin, cnt = tets[keep], tv[keep], tin[keep], cnt[keep]

    # sort each tet's corners: inside ones first, so each case has one layout
    order = np.argsort(~tin, axis=1, kind="stable")
    tets = np.take_along_axis(tets, order, axis=1)
    tv = np.take_along_axis(tv, order, axis=1)

    # one corner in: triangle on edges 0-1, 0-2, 0-3
    m1 = cnt == 1
    # three in: triangle on edges 3-0, 3-1, 3-2 (the one outside corner is 3)
    m3 = cnt == 3
    # two in (0, 1), out (2, 3): quad on edges 0-2, 0-3, 1-3, 1-2
    m2 = cnt == 2
    # which way round each (sorted) tet is: the sign of its volume, in grid steps
    def ijk(ids):
        return np.stack([ids // (ny * nz), (ids // nz) % ny, ids % nz], axis=1)

    q0, q1, q2, q3 = (ijk(tets[:, i]) for i in range(4))
    det = np.einsum("ij,ij->i", q1 - q0, np.cross(q2 - q0, q3 - q0))
    groups = [
        (m1, [(0, 1), (0, 2), (0, 3)]),
        (m3, [(0, 3), (1, 3), (2, 3)]),
        (m2, [(0, 2), (0, 3), (1, 3)]),
        (m2, [(0, 2), (1, 3), (1, 2)]),
    ]
    tri_a, tri_b, tri_neg = [], [], []
    for mask, slots in groups:
        t = tets[mask]
        if len(t) == 0:
            continue
        tri_a.append(np.stack([t[:, s_[0]] for s_ in slots], axis=1))
        tri_b.append(np.stack([t[:, s_[1]] for s_ in slots], axis=1))
        tri_neg.append(det[mask] < 0)
    A = np.concatenate(tri_a)
    B = np.concatenate(tri_b)
    NEG = np.concatenate(tri_neg)
    # each edge's point is found once, so neighbouring triangles share it
    lo_, hi_ = np.minimum(A, B), np.maximum(A, B)
    n_all = nx * ny * nz
    key = lo_.astype(np.int64) * n_all + hi_
    ukey, inv = np.unique(key.reshape(-1), return_inverse=True)
    ea, eb = ukey // n_all, ukey % n_all
    va, vb = flat[ea], flat[eb]
    s = va / (va - vb)

    def xyz(ids):
        k = ids % nz
        j = (ids // nz) % ny
        i = ids // (ny * nz)
        return np.stack([xs[i], ys[j], zs[k]], axis=1)

    pa, pb = xyz(ea), xyz(eb)
    pts = pa + s[:, None] * (pb - pa)
    tris = inv.reshape(-1, 3)
    # with the inside corners first, a triangle of a positive tet faces out as
    # written; one of a negative tet is turned over (no geometry involved, so
    # even slivers face the right way)
    tris[NEG] = tris[NEG][:, ::-1]
    # drop triangles with no area (two points on one grid corner)
    ok = (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])
    return pts, tris[ok]


def mesh_field(fn: Field, box, cell: float) -> tuple[np.ndarray, np.ndarray]:
    vals, axes = sample(fn, box, cell)
    if not (vals < 0).any():
        raise FieldError("the field is nowhere below 0 in the box, so there is no shape")
    return march(vals, axes)


# ---- lattices ----------------------------------------------------------------------
LATTICES = ("GYROID", "SCHWARZ", "DIAMOND", "CUBIC", "BCC", "OCTET")

_UNIT_STRUTS = {
    # struts in one unit cell (corners at 0 and 1); edges of the cell are shared with neighbours
    "CUBIC": [((0, 0, 0), (1, 0, 0)), ((0, 1, 0), (1, 1, 0)), ((0, 0, 1), (1, 0, 1)), ((0, 1, 1), (1, 1, 1)),
              ((0, 0, 0), (0, 1, 0)), ((1, 0, 0), (1, 1, 0)), ((0, 0, 1), (0, 1, 1)), ((1, 0, 1), (1, 1, 1)),
              ((0, 0, 0), (0, 0, 1)), ((1, 0, 0), (1, 0, 1)), ((0, 1, 0), (0, 1, 1)), ((1, 1, 0), (1, 1, 1))],
    "BCC": [((0, 0, 0), (1, 1, 1)), ((1, 0, 0), (0, 1, 1)), ((0, 1, 0), (1, 0, 1)), ((1, 1, 0), (0, 0, 1))],
    "OCTET": [((0, 0, 0), (1, 1, 0)), ((1, 0, 0), (0, 1, 0)), ((0, 0, 1), (1, 1, 1)), ((1, 0, 1), (0, 1, 1)),
              ((0, 0, 0), (1, 0, 1)), ((1, 0, 0), (0, 0, 1)), ((0, 1, 0), (1, 1, 1)), ((1, 1, 0), (0, 1, 1)),
              ((0, 0, 0), (0, 1, 1)), ((0, 1, 0), (0, 0, 1)), ((1, 0, 0), (1, 1, 1)), ((1, 1, 0), (1, 0, 1))],
}


def lattice_field(kind: str, cell: float, thickness: float, origin=(0.0, 0.0, 0.0)) -> Field:
    """A lattice as a field: sheets (gyroid, Schwarz, diamond) of the given wall
    thickness, or struts (cubic, BCC, octet) of that diameter."""
    kind = kind.upper()
    if kind not in LATTICES:
        raise FieldError(f"the lattice is one of {', '.join(LATTICES)}")
    if cell <= 0 or thickness <= 0:
        raise FieldError("the cell size and the thickness must be positive")
    if thickness >= cell:
        raise FieldError("the thickness must be smaller than the cell")
    ox, oy, oz = origin
    if kind in ("GYROID", "SCHWARZ", "DIAMOND"):
        tp = _tpms(kind)
        return lambda x, y, z: np.abs(tp(x, y, z, cell, ox, oy, oz)) - thickness / 2
    struts = _UNIT_STRUTS[kind]
    r = thickness / 2

    def fn(x, y, z):
        u = np.mod(x - ox, cell) / cell
        v = np.mod(y - oy, cell) / cell
        w = np.mod(z - oz, cell) / cell
        d = None
        for a, b in struts:
            s = seg_dist(u, v, w, a, b)
            d = s if d is None else np.minimum(d, s)
        return d * cell - r

    return fn
