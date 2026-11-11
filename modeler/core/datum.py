"""Datum geometry: named planes, axes and points to build on.

A datum is not a body. It has no faces to pick and takes no part in
booleans or exports; it is a reference that other commands use by name:
a plane to split by or to draw on, an axis to turn about, a point to
measure from.

Every datum is a frame: an origin and three directions at right angles.

* PLANE: ``z`` is the normal; ``x`` and ``y`` lie in the plane, so a plane
  is also a local coordinate system (``WORKPLANE`` draws in it).
* AXIS: ``z`` is the direction of the line through ``origin``.
* POINT: only ``origin`` matters.

This module is plain Python (no kernel, no Qt).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

P3 = tuple[float, float, float]

KINDS = ("PLANE", "AXIS", "POINT")


class DatumError(Exception):
    pass


def sub(a, b) -> P3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b) -> P3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a, k: float) -> P3:
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b) -> P3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a) -> float:
    return math.sqrt(dot(a, a))


def unit(a, what: str = "direction") -> P3:
    n = norm(a)
    if n < 1e-12:
        raise DatumError(f"the {what} cannot be (0, 0, 0)")
    return (a[0] / n, a[1] / n, a[2] / n)


def _clean(v) -> P3:
    """Round away the noise of unit vectors (0.9999999999 -> 1, -0.0 -> 0)."""
    return tuple(round(float(c), 12) + 0.0 for c in v)  # type: ignore[return-value]


def plane_axes(normal, angle_deg: float = 0.0) -> tuple[P3, P3, P3]:
    """(x, y, z) of a plane with this normal: the same rule the profile
    commands use. Normal +Z: X is world X. Any other normal: X is level
    (world Z x normal) and Y points as far up as the plane allows."""
    z = unit(normal, "normal")
    if abs(z[2]) > 1 - 1e-9:
        x: P3 = (1.0, 0.0, 0.0)
    else:
        x = unit(cross((0.0, 0.0, 1.0), z))
    y = cross(z, x)
    if angle_deg:
        a = math.radians(angle_deg)
        c, s = math.cos(a), math.sin(a)
        x = add(mul(x, c), mul(y, s))
    return _clean(x), _clean(cross(z, x)), _clean(z)


@dataclass(frozen=True)
class Datum:
    kind: str  # PLANE, AXIS or POINT
    name: str  # "" for a frame that is not stored (a work plane on a face, say)
    origin: P3
    z: P3 = (0.0, 0.0, 1.0)
    x: P3 = (1.0, 0.0, 0.0)

    @property
    def y(self) -> P3:
        return _clean(cross(self.z, self.x))

    # ---- local <-> world -------------------------------------------------
    def point(self, u: float, v: float, w: float = 0.0) -> P3:
        """World position of local (u, v, w): u along X, v along Y, w along the normal."""
        y = self.y
        return tuple(self.origin[i] + u * self.x[i] + v * y[i] + w * self.z[i] for i in range(3))  # type: ignore[return-value]

    def direction(self, d) -> P3:
        """A local direction in world coordinates."""
        y = self.y
        return tuple(d[0] * self.x[i] + d[1] * y[i] + d[2] * self.z[i] for i in range(3))  # type: ignore[return-value]

    def local(self, p) -> P3:
        """Local (u, v, w) of a world point."""
        d = sub(p, self.origin)
        return (dot(d, self.x), dot(d, self.y), dot(d, self.z))

    def height(self, p) -> float:
        """Signed distance of a world point from the plane (positive on the normal's side)."""
        return dot(sub(p, self.origin), self.z)

    def moved(self, offset: float) -> "Datum":
        return Datum(self.kind, self.name, _clean(add(self.origin, mul(self.z, offset))), self.z, self.x)

    def named(self, name: str) -> "Datum":
        return Datum(self.kind, name, self.origin, self.z, self.x)


def plane(origin, normal, angle_deg: float = 0.0, name: str = "") -> Datum:
    x, _, z = plane_axes(normal, angle_deg)
    return Datum("PLANE", name, _clean(origin), z, x)


def plane_through(p1, p2, p3, name: str = "") -> Datum:
    """Plane through three points: origin at the first, X towards the second."""
    x = sub(p2, p1)
    n = cross(x, sub(p3, p1))
    if norm(x) < 1e-12 or norm(n) < 1e-9 * max(1.0, norm(x) * norm(sub(p3, p1))):
        raise DatumError("the three points are on one line, so they do not fix a plane")
    return Datum("PLANE", name, _clean(p1), _clean(unit(n)), _clean(unit(x)))


def axis(origin, direction, name: str = "") -> Datum:
    x, _, z = plane_axes(unit(direction, "axis direction"))
    return Datum("AXIS", name, _clean(origin), z, x)


def point(origin, name: str = "") -> Datum:
    return Datum("POINT", name, _clean(origin))


BASE_PLANES = {
    "XY": ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "YZ": ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
    "ZX": ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "XZ": ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
}
BASE_AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
