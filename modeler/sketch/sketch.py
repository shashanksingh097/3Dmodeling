"""A 2D sketch: points, lines, arcs and circles on a plane, held in place by
constraints and dimensions.

Plain Python + numpy (no kernel, no Qt), so it is tested on its own. The
commands in ``commands/sketch_handlers.py`` drive it; ``profile.py`` turns
its closed loops into faces for EXTRUDE and REVOLVE.

Names used in commands (case does not matter):

====================  =====================================================
``3``                 geometry 3 (a point, line, arc or circle)
``3.S`` ``3.E``       start and end point of line or arc 3
``3.C``               centre of arc or circle 3
``ORIGIN`` (or ``O``)  the sketch origin (fixed)
``H`` ``V``           the sketch's horizontal and vertical axes (fixed lines)
``C4``                constraint or dimension 4 (for SDEL)
====================  =====================================================

Every number lives in one flat array ``x`` (a point is two numbers, a
circle's radius one); constraints are functions of a few of them (see
``solver.py``). Positions are in the plane's own u (along its X) and v
(along its Y).
"""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, field

import numpy as np

from . import solver

GEO_KINDS = ("POINT", "LINE", "ARC", "CIRCLE")
CON_KINDS = ("COINCIDENT", "ON", "HORIZONTAL", "VERTICAL", "PARALLEL", "PERPENDICULAR", "TANGENT", "EQUAL",
             "MIDPOINT", "SYMMETRIC", "CONCENTRIC", "FIX")
DIM_KINDS = ("DIST", "HDIST", "VDIST", "LENGTH", "RADIUS", "DIAMETER", "ANGLE")

# fixed numbers: the origin and one point on each axis
_O, _HX, _VY = 0, 2, 4
_FIXED = {0, 1, 2, 3, 4, 5}


class SketchError(Exception):
    pass


@dataclass
class Geo:
    n: int
    kind: str
    pts: dict[str, int]  # role (P, S, E, C) -> index of the point's u in x
    r: int | None = None  # index of a circle's radius in x
    construction: bool = False


@dataclass
class Con:
    n: int
    kind: str
    refs: tuple[str, ...]
    value: float | None = None  # dimensions: the size (degrees for ANGLE)
    data: dict = field(default_factory=dict)  # which side, fixed position ...
    uid: int = 0  # the history entry that made it (so the GUI can edit it)
    auto: bool = False  # added by a drawing command (a line drawn from a point)

    @property
    def is_dim(self) -> bool:
        return self.kind in DIM_KINDS

    @property
    def label(self) -> str:
        return f"C{self.n}"


_REF = re.compile(r"^\s*(\d+)\s*(?:\.\s*([SECP]))?\s*$", re.I)


@dataclass
class Ref:
    """A resolved name: a point (index into x) or a piece of geometry."""

    text: str
    point: int | None = None
    geo: Geo | None = None
    fixed: bool = False

    @property
    def is_point(self) -> bool:
        return self.point is not None


class Sketch:
    def __init__(self, name: str, frame, base_body: int = 0) -> None:
        self.name = name
        self.frame = frame  # a datum plane (core/datum.py): where the sketch lies in 3D
        self.base_body = base_body  # the body whose face it was drawn on, if any
        self.x: list[float] = [0.0, 0.0, 1.0, 0.0, 0.0, 1.0]
        self.geos: dict[int, Geo] = {}
        self.cons: dict[int, Con] = {}
        self._next_geo = 1
        self._next_con = 1
        self.closed = False  # ENDSKETCH ran
        self.used_by: list[str] = []  # features made from it
        self.dof = 0
        self.free: set[int] = set()
        self.redundant: list[int] = []

    def copy(self) -> "Sketch":
        new = copy.copy(self)
        new.x = list(self.x)
        new.geos = {k: copy.deepcopy(g) for k, g in self.geos.items()}
        new.cons = {k: copy.deepcopy(c) for k, c in self.cons.items()}
        new.free = set(self.free)
        new.redundant = list(self.redundant)
        new.used_by = list(self.used_by)
        return new

    # ---- reading positions ----------------------------------------------
    def pt(self, i: int) -> tuple[float, float]:
        return (self.x[i], self.x[i + 1])

    def radius(self, g: Geo) -> float:
        if g.kind == "CIRCLE":
            return abs(self.x[g.r])
        if g.kind == "ARC":
            c, s = self.pt(g.pts["C"]), self.pt(g.pts["S"])
            return math.hypot(s[0] - c[0], s[1] - c[1])
        raise SketchError(f"{g.n} is a {g.kind.lower()}, which has no radius")

    def arc_angles(self, g: Geo) -> tuple[float, float]:
        """Start and end angle of an arc in degrees, end > start (counter-clockwise)."""
        c, s, e = self.pt(g.pts["C"]), self.pt(g.pts["S"]), self.pt(g.pts["E"])
        a1 = math.degrees(math.atan2(s[1] - c[1], s[0] - c[0]))
        a2 = math.degrees(math.atan2(e[1] - c[1], e[0] - c[0]))
        while a2 <= a1 + 1e-9:
            a2 += 360.0
        return a1, a2

    def fully_defined(self, g: Geo) -> bool:
        idx = [i for p in g.pts.values() for i in (p, p + 1)] + ([g.r] if g.r is not None else [])
        return not any(i in self.free for i in idx)

    def extent(self) -> float:
        pts = [self.pt(p) for g in self.geos.values() for p in g.pts.values()]
        for g in self.geos.values():
            if g.kind in ("CIRCLE", "ARC"):
                c = self.pt(g.pts["C"])
                r = self.radius(g)
                pts += [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)]
        if not pts:
            return 10.0
        us, vs = [p[0] for p in pts] + [0.0], [p[1] for p in pts] + [0.0]
        return max(1.0, max(us) - min(us), max(vs) - min(vs))

    # ---- names -------------------------------------------------------------
    def ref(self, text: str) -> Ref:
        t = str(text).strip().upper()
        if t in ("O", "ORIGIN"):
            return Ref("ORIGIN", point=_O, fixed=True)
        if t in ("H", "V"):
            g = Geo(0, "LINE", {"S": _O, "E": _HX if t == "H" else _VY})
            return Ref(t, geo=g, fixed=True)
        m = _REF.match(t)
        if not m:
            raise SketchError(f"{text!r} is not a sketch name: use a number (3), an end (3.S, 3.E), "
                              "a centre (3.C), ORIGIN, or H / V for the axes")
        n, role = int(m.group(1)), (m.group(2) or "").upper()
        g = self.geos.get(n)
        if g is None:
            have = ", ".join(map(str, sorted(self.geos))) or "none yet"
            raise SketchError(f"sketch {self.name} has no geometry {n} (it has: {have})")
        if not role:
            if g.kind == "POINT":
                return Ref(t, point=g.pts["P"], geo=g)
            return Ref(t, geo=g)
        if role == "P":
            role = "P" if g.kind == "POINT" else "?"
        if role not in g.pts:
            have = ", ".join(f"{n}.{r}" for r in g.pts if r != "P") or str(n)
            raise SketchError(f"{g.kind.lower()} {n} has no point {t} (use {have})")
        return Ref(t, point=g.pts[role], geo=g)

    def describe(self, n: int) -> str:
        g = self.geos[n]
        f = _f
        if g.kind == "POINT":
            return f"point {n} at {f(self.pt(g.pts['P']))}"
        if g.kind == "LINE":
            return f"line {n} {f(self.pt(g.pts['S']))} to {f(self.pt(g.pts['E']))}"
        if g.kind == "CIRCLE":
            return f"circle {n} at {f(self.pt(g.pts['C']))}, r {_n(self.radius(g))}"
        a1, a2 = self.arc_angles(g)
        return f"arc {n} at {f(self.pt(g.pts['C']))}, r {_n(self.radius(g))}, {_n(a1)} to {_n(a2)} deg"

    # ---- adding geometry ------------------------------------------------------
    def _new_point(self, u: float, v: float) -> int:
        self.x += [float(u), float(v)]
        return len(self.x) - 2

    def _geo(self, kind: str, pts: dict[str, int], r: int | None = None, construction: bool = False) -> Geo:
        g = Geo(self._next_geo, kind, pts, r, construction)
        self.geos[g.n] = g
        self._next_geo += 1
        return g

    def point_value(self, at) -> tuple[tuple[float, float], Ref | None]:
        """``at`` is (u, v) or a point name: its position, and the Ref when named."""
        if isinstance(at, (tuple, list)):
            return (float(at[0]), float(at[1])), None
        r = self.ref(at)
        if not r.is_point:
            raise SketchError(f"{at} is a {r.geo.kind.lower()}, not a point (use {at}.S, {at}.E or {at}.C)")
        return self.pt(r.point), r

    def _tie(self, made: list[tuple[str, Ref | None]], uid: int) -> None:
        for mine, other in made:
            if other is not None:
                self.add_con("COINCIDENT", (mine, other.text), uid=uid, auto=True, solve=False)

    def add_point(self, at, uid: int = 0) -> Geo:
        (u, v), r = self.point_value(at)
        g = self._geo("POINT", {"P": self._new_point(u, v)})
        self._tie([(str(g.n), r)], uid)
        return g

    def add_line(self, a, b, uid: int = 0, construction: bool = False) -> Geo:
        (u1, v1), ra = self.point_value(a)
        (u2, v2), rb = self.point_value(b)
        if math.hypot(u2 - u1, v2 - v1) < 1e-9:
            raise SketchError("a line needs two different points")
        g = self._geo("LINE", {"S": self._new_point(u1, v1), "E": self._new_point(u2, v2)}, construction=construction)
        self._tie([(f"{g.n}.S", ra), (f"{g.n}.E", rb)], uid)
        return g

    def add_circle(self, c, r: float, uid: int = 0, construction: bool = False) -> Geo:
        if r <= 0:
            raise SketchError("the radius must be positive")
        (u, v), rc = self.point_value(c)
        cp = self._new_point(u, v)
        self.x.append(float(r))
        g = self._geo("CIRCLE", {"C": cp}, r=len(self.x) - 1, construction=construction)
        self._tie([(f"{g.n}.C", rc)], uid)
        return g

    def add_arc(self, c, r: float, a1: float, a2: float, uid: int = 0, construction: bool = False) -> Geo:
        if r <= 0:
            raise SketchError("the radius must be positive")
        if abs(a2 - a1) < 1e-6 or abs(a2 - a1) >= 360 - 1e-6:
            raise SketchError("an arc needs two different angles less than 360 degrees apart (use SCIRCLE for a full circle)")
        (u, v), rc = self.point_value(c)
        t1, t2 = math.radians(a1), math.radians(a2)
        cp = self._new_point(u, v)
        s = self._new_point(u + r * math.cos(t1), v + r * math.sin(t1))
        e = self._new_point(u + r * math.cos(t2), v + r * math.sin(t2))
        g = self._geo("ARC", {"C": cp, "S": s, "E": e}, construction=construction)
        self._tie([(f"{g.n}.C", rc)], uid)
        return g

    def add_arc_3p(self, a, b, c, uid: int = 0, construction: bool = False) -> Geo:
        """An arc from a through b to c."""
        (x1, y1), ra = self.point_value(a)
        (x2, y2), _ = self.point_value(b)
        (x3, y3), rc = self.point_value(c)
        d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        if abs(d) < 1e-12:
            raise SketchError("the three points are on one line, so they do not make an arc")
        s1, s2, s3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
        ux = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / d
        uy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / d
        r = math.hypot(x1 - ux, y1 - uy)
        a1 = math.degrees(math.atan2(y1 - uy, x1 - ux))
        a3 = math.degrees(math.atan2(y3 - uy, x3 - ux))
        if d < 0:  # clockwise through b: the arc runs from c to a
            a1, a3 = a3, a1
            ra, rc = rc, ra
        g = self.add_arc((ux, uy), r, a1, a3, uid, construction)
        self._tie([(f"{g.n}.S", ra), (f"{g.n}.E", rc)], uid)
        return g

    def add_rect(self, a, b, uid: int = 0, construction: bool = False) -> list[Geo]:
        (u1, v1), ra = self.point_value(a)
        (u2, v2), rb = self.point_value(b)
        if abs(u2 - u1) < 1e-9 or abs(v2 - v1) < 1e-9:
            raise SketchError("a rectangle needs two opposite corners with different u and v")
        corners = [(u1, v1), (u2, v1), (u2, v2), (u1, v2)]
        lines = [self.add_line(corners[i], corners[(i + 1) % 4], uid, construction) for i in range(4)]
        for i in range(4):
            self.add_con("COINCIDENT", (f"{lines[i].n}.E", f"{lines[(i + 1) % 4].n}.S"), uid=uid, auto=True, solve=False)
        for i, kind in enumerate(("HORIZONTAL", "VERTICAL", "HORIZONTAL", "VERTICAL")):
            self.add_con(kind, (str(lines[i].n),), uid=uid, auto=True, solve=False)
        self._tie([(f"{lines[0].n}.S", ra), (f"{lines[1].n}.E", rb)], uid)
        return lines

    def add_poly(self, pts: list, close: bool, uid: int = 0, construction: bool = False) -> list[Geo]:
        if len(pts) < 2:
            raise SketchError("a polyline needs at least two points")
        lines = []
        for i in range(len(pts) - 1):
            lines.append(self.add_line(pts[i], pts[i + 1], uid, construction))
        if close:
            first = self.point_value(pts[0])[0]
            last = self.point_value(pts[-1])[0]
            if math.hypot(first[0] - last[0], first[1] - last[1]) > 1e-9:
                lines.append(self.add_line(pts[-1], pts[0], uid, construction))
        for i in range(len(lines) - 1):
            self.add_con("COINCIDENT", (f"{lines[i].n}.E", f"{lines[i + 1].n}.S"), uid=uid, auto=True, solve=False)
        if close and len(lines) > 2:
            self.add_con("COINCIDENT", (f"{lines[-1].n}.E", f"{lines[0].n}.S"), uid=uid, auto=True, solve=False)
        # a point given by name was tied to both lines that meet there; once is enough
        self._dedupe_ties()
        return lines

    def _dedupe_ties(self) -> None:
        seen = set()
        for k in list(self.cons):
            c = self.cons[k]
            if c.kind == "COINCIDENT":
                pair = frozenset(self.ref(r).point for r in c.refs)
                key = pair
                if key in seen:
                    del self.cons[k]
                seen.add(key)

    def add_slot(self, a, b, r: float, uid: int = 0, construction: bool = False) -> list[Geo]:
        """A slot: two half circles of radius r around a and b, joined by two lines."""
        (u1, v1), ra = self.point_value(a)
        (u2, v2), rb = self.point_value(b)
        L = math.hypot(u2 - u1, v2 - v1)
        if L < 1e-9 or r <= 0:
            raise SketchError("a slot needs two different centres and a positive radius")
        ang = math.degrees(math.atan2(v2 - v1, u2 - u1))
        nu, nv = -(v2 - v1) / L * r, (u2 - u1) / L * r
        a1 = self.add_arc((u1, v1), r, ang + 90, ang + 270, uid, construction)
        a2 = self.add_arc((u2, v2), r, ang - 90, ang + 90, uid, construction)
        l1 = self.add_line((u1 - nu, v1 - nv), (u2 - nu, v2 - nv), uid, construction)
        l2 = self.add_line((u2 + nu, v2 + nv), (u1 + nu, v1 + nv), uid, construction)
        for p, q in ((f"{a1.n}.E", f"{l1.n}.S"), (f"{l1.n}.E", f"{a2.n}.S"),
                     (f"{a2.n}.E", f"{l2.n}.S"), (f"{l2.n}.E", f"{a1.n}.S")):
            self.add_con("COINCIDENT", (p, q), uid=uid, auto=True, solve=False)
        for ln in (l1, l2):
            for arc in (a1, a2):
                self.add_con("TANGENT", (str(ln.n), str(arc.n)), uid=uid, auto=True, solve=False)
        self.add_con("EQUAL", (str(a1.n), str(a2.n)), uid=uid, auto=True, solve=False)
        self._tie([(f"{a1.n}.C", ra), (f"{a2.n}.C", rb)], uid)
        return [a1, a2, l1, l2]

    # ---- constraints ------------------------------------------------------------
    def add_con(self, kind: str, refs: tuple[str, ...], value: float | None = None, uid: int = 0,
                auto: bool = False, solve: bool = True) -> Con:
        kind = kind.upper()
        if kind not in CON_KINDS and kind not in DIM_KINDS:
            raise SketchError(f"unknown constraint {kind}: use one of {', '.join(CON_KINDS + DIM_KINDS)}")
        rs = [self.ref(r) for r in refs if str(r).strip()]
        refs = tuple(r.text for r in rs)
        if kind == "COINCIDENT" and len(rs) == 2 and (rs[0].is_point != rs[1].is_point):
            kind = "ON"  # a point on a curve
            if not rs[0].is_point:
                rs.reverse()
                refs = (refs[1], refs[0])
        con = Con(self._next_con, kind, refs, value, uid=uid, auto=auto)
        _check_shape(self, con, rs)
        if kind in DIM_KINDS:
            if value is None:
                raise SketchError(f"{kind}: give the size")
            if value < 0 or (value == 0 and kind not in ("ANGLE", "HDIST", "VDIST")):
                raise SketchError(f"{kind}: the size must be positive")
        elif value is not None:
            raise SketchError(f"{kind} takes no size (sizes are dimensions: {', '.join(DIM_KINDS)})")
        _choose_sides(self, con, rs)
        self.cons[con.n] = con
        self._next_con += 1
        if solve:
            try:
                self.solve(blame=con.n)
            except SketchError:
                del self.cons[con.n]
                self._next_con -= 1
                raise
        return con

    def measure(self, kind: str, refs: tuple[str, ...]) -> float:
        """The current size a dimension of this kind would have (the GUI's starting value)."""
        rs = [self.ref(r) for r in refs]
        con = Con(0, kind.upper(), tuple(r.text for r in rs))
        _check_shape(self, con, rs)
        _choose_sides(self, con, rs)
        return con.data["now"]

    def set_value(self, n: int, value: float) -> None:
        c = self.cons[n]
        if not c.is_dim:
            raise SketchError(f"C{n} is a {c.kind.lower()} constraint, which has no size")
        c.value = value
        self.solve(blame=n)

    def delete(self, text: str) -> str:
        t = text.strip().upper()
        if t.startswith("C") and t[1:].isdigit():
            n = int(t[1:])
            if n not in self.cons:
                raise SketchError(f"sketch {self.name} has no constraint C{n}")
            c = self.cons.pop(n)
            self.solve()
            return f"deleted {c.kind.lower()} C{n}"
        r = self.ref(t)
        if r.geo is None or r.fixed or "." in t:
            raise SketchError(f"SDEL takes a geometry number (3) or a constraint (C4), not {text}")
        g = self.geos.pop(r.geo.n)
        gone = [k for k, c in self.cons.items() if any(_geo_of(x) == g.n for x in c.refs)]
        for k in gone:
            del self.cons[k]
        self.solve()
        extra = f" and {len(gone)} constraint{'s' if len(gone) != 1 else ''} on it" if gone else ""
        return f"deleted {g.kind.lower()} {g.n}{extra}"

    def move(self, text: str, u: float, v: float) -> None:
        """Drag: put a point (or a whole piece of geometry, by its first point) at (u, v)."""
        r = self.ref(text)
        if r.fixed:
            raise SketchError(f"{text} is fixed")
        if r.is_point:
            pts = [r.point]
            du, dv = u - self.x[r.point], v - self.x[r.point + 1]
        else:
            first = r.geo.pts.get("C", r.geo.pts.get("S", r.geo.pts.get("P")))
            pts = list(r.geo.pts.values())
            du, dv = u - self.x[first], v - self.x[first + 1]
        drag = {}
        for p in pts:
            drag[p] = self.x[p] + du
            drag[p + 1] = self.x[p + 1] + dv
        x = np.array(self.x)
        cons, fixed = self._system()
        solver.solve_dragging(x, cons, fixed, drag)
        self.x = [float(c) for c in x]
        self.solve()

    # ---- solving -----------------------------------------------------------------
    def _system(self) -> tuple[list[solver.Constraint], set[int]]:
        cons: list[solver.Constraint] = []
        for g in self.geos.values():
            if g.kind == "ARC":  # both ends at the same distance from the centre
                c, s, e = g.pts["C"], g.pts["S"], g.pts["E"]
                cons.append(solver.Constraint(-2, (c, c + 1, s, s + 1, e, e + 1), _arc_rule))
        scale = self.extent()
        for con in self.cons.values():
            cons.extend(_build(self, con, scale))
        return cons, set(_FIXED)

    def solve(self, blame: int | None = None) -> solver.Report:
        x = np.array(self.x, dtype=float)
        cons, fixed = self._system()
        rep = solver.solve(x, cons, fixed)
        if not rep.ok or rep.conflicting:
            bad = sorted(set(rep.failed) | set(rep.conflicting))
            who = [f"C{n} ({self.cons[n].kind.lower()})" for n in bad if n in self.cons]
            if blame is not None:
                fights = self._fights(blame)
                others = [f"C{n} ({self.cons[n].kind.lower()})" for n in fights] or \
                    [w for w in who if not w.startswith(f"C{blame} ")]
                raise SketchError(
                    "this cannot hold together with the other constraints"
                    + (f" (it fights {', '.join(others)})" if others else "")
                    + ": the sketch is over-constrained. Delete or change one of them first.")
            raise SketchError("the constraints cannot all hold: " + ", ".join(who))
        old, self.x = self.x, [float(c) for c in x]
        size = max(self.extent(), 1.0)
        for g in self.geos.values():
            short = (g.kind == "LINE" and math.dist(self.pt(g.pts["S"]), self.pt(g.pts["E"])) < 1e-7 * size) or \
                (g.kind in ("ARC", "CIRCLE") and self.radius(g) < 1e-7 * size)
            if short:
                self.x = old
                what = "that" if blame is None else f"C{blame} ({self.cons[blame].kind.lower()})" \
                    if blame in self.cons else "that"
                raise SketchError(f"{what} would shrink {g.kind.lower()} {g.n} to nothing: "
                                  "the sketch is over-constrained there")
        self.dof, self.free, self.redundant = rep.dof, rep.free, rep.redundant
        return rep

    def _fights(self, blame: int) -> list[int]:
        """The constraints that together already fix what constraint ``blame``
        tries to change: its equations are a mix of theirs."""
        x = np.array(self.x, dtype=float)
        cons, fixed = self._system()
        cols = [i for i in range(len(x)) if i not in fixed]
        mine = [k for k, c in enumerate(cons) if c.tag == blame]
        rest = [k for k, c in enumerate(cons) if c.tag != blame]
        _, Jb, _ = solver._system(x, cons, mine, cols)
        _, Jo, owners = solver._system(x, cons, rest, cols)
        if not len(owners) or not len(Jb):
            return []
        alpha = np.linalg.lstsq(Jo.T, Jb.T, rcond=1e-10)[0]
        weight = np.abs(alpha).max(axis=1)
        tags = []
        top = weight.max(initial=0.0)
        for row, k in enumerate(owners):
            t = cons[k].tag
            if weight[row] > 1e-6 * max(1.0, top) and t >= 0 and t not in tags:
                tags.append(t)
        return sorted(tags)

    def status(self) -> str:
        n_geo = len(self.geos)
        n_con = len(self.cons)
        state = "fully defined" if self.dof == 0 and n_geo else f"{self.dof} degree{'s' if self.dof != 1 else ''} of freedom left"
        text = f"sketch {self.name}: {n_geo} geometr{'y' if n_geo == 1 else 'ies'}, {n_con} constraint{'s' if n_con != 1 else ''}, {state}"
        if self.redundant:
            text += f"; {', '.join('C' + str(n) for n in self.redundant)} repeat{'s' if len(self.redundant) == 1 else ''} other constraints"
        return text


# =============================================================================
# constraint equations
# =============================================================================

def _f(p) -> str:
    return "(" + ", ".join(_n(c) for c in p) + ")"


def _n(v: float) -> str:
    v = round(v, 6) + 0.0
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def _geo_of(ref: str) -> int | None:
    m = _REF.match(ref)
    return int(m.group(1)) if m else None


def _arc_rule(v):
    cx, cy, sx, sy, ex, ey = v
    return [math.hypot(sx - cx, sy - cy) - math.hypot(ex - cx, ey - cy)]


def _need(con: Con, rs: list[Ref], pattern: str, msg: str) -> None:
    """pattern: one letter per ref: P point, L line, R round (arc/circle), G any geometry, * anything."""
    def fits(r: Ref, ch: str) -> bool:
        k = r.geo.kind if r.geo is not None and not r.is_point else None
        return {"P": r.is_point, "L": k == "LINE", "R": k in ("ARC", "CIRCLE"), "G": k is not None, "*": True,
                "C": k in ("LINE", "ARC", "CIRCLE")}[ch]

    if len(rs) != len(pattern) or not all(fits(r, ch) for r, ch in zip(rs, pattern)):
        raise SketchError(f"{con.kind}: {msg}")


def _check_shape(sk: Sketch, con: Con, rs: list[Ref]) -> None:
    k = con.kind
    pats = {
        "COINCIDENT": [("PP", "give two points, e.g. 1.E, 2.S")],
        "ON": [("PC", "give a point and a line, arc or circle, e.g. 3.S, 1")],
        "HORIZONTAL": [("L", ""), ("PP", "")], "VERTICAL": [("L", ""), ("PP", "")],
        "PARALLEL": [("LL", "give two lines")], "PERPENDICULAR": [("LL", "give two lines")],
        "TANGENT": [("LR", ""), ("RL", ""), ("RR", "")],
        "EQUAL": [("LL", ""), ("RR", "")],
        "MIDPOINT": [("PL", "give a point and a line")],
        "SYMMETRIC": [("PPL", "give two points and the line they mirror about")],
        "CONCENTRIC": [("RR", "give two arcs or circles")],
        "FIX": [("P", ""), ("G", "")],
        "DIST": [("PP", ""), ("PL", ""), ("LP", ""), ("LL", "")],
        "HDIST": [("PP", ""), ("L", "")], "VDIST": [("PP", ""), ("L", "")],
        "LENGTH": [("L", "give a line")],
        "RADIUS": [("R", "give an arc or circle")], "DIAMETER": [("R", "give an arc or circle")],
        "ANGLE": [("LL", ""), ("L", "")],
    }[k]
    hints = {
        "HORIZONTAL": "give a line, or two points", "VERTICAL": "give a line, or two points",
        "TANGENT": "give a line and an arc or circle, or two arcs/circles",
        "EQUAL": "give two lines (same length) or two arcs/circles (same radius)",
        "FIX": "give a point or one piece of geometry",
        "DIST": "give two points, a point and a line, or two parallel lines",
        "HDIST": "give two points, or a line", "VDIST": "give two points, or a line",
        "ANGLE": "give two lines (or one line, measured from H)",
    }
    errors = []
    for pat, msg in pats:
        try:
            _need(con, rs, pat, msg or hints.get(k, ""))
            break
        except SketchError as exc:
            errors.append(exc)
    else:
        raise errors[0]
    if all(r.fixed for r in rs):
        raise SketchError(f"{k}: the origin and axes are fixed already")
    if k in ("PARALLEL", "PERPENDICULAR", "EQUAL", "CONCENTRIC", "COINCIDENT", "TANGENT", "SYMMETRIC") and len(
            {r.text for r in rs}) < len(rs):
        raise SketchError(f"{k}: give different things")


def _line(sk: Sketch, r: Ref) -> tuple[int, int]:
    return r.geo.pts["S"], r.geo.pts["E"]


def _round(sk: Sketch, r: Ref) -> tuple[int, int | None, int | None]:
    """(centre, radius index for circles, start point for arcs)"""
    g = r.geo
    return g.pts["C"], g.r, g.pts.get("S")


def _cur_angle(sk: Sketch, a: Ref, b: Ref | None) -> float:
    s1, e1 = _line(sk, a)
    d1 = (sk.x[e1] - sk.x[s1], sk.x[e1 + 1] - sk.x[s1 + 1])
    if b is None:
        d2 = (1.0, 0.0)
        d1, d2 = d2, d1
    else:
        s2, e2 = _line(sk, b)
        d2 = (sk.x[e2] - sk.x[s2], sk.x[e2 + 1] - sk.x[s2 + 1])
    return math.degrees(math.atan2(d1[0] * d2[1] - d1[1] * d2[0], d1[0] * d2[0] + d1[1] * d2[1]))


def _signed_dist(sk: Sketch, p: int, s: int, e: int) -> float:
    x = sk.x
    dx, dy = x[e] - x[s], x[e + 1] - x[s + 1]
    L = math.hypot(dx, dy) or 1e-12
    return (dx * (x[p + 1] - x[s + 1]) - dy * (x[p] - x[s])) / L


def _choose_sides(sk: Sketch, con: Con, rs: list[Ref]) -> None:
    """Pick the solution branch from the sketch as drawn (which side of a line,
    inside or outside tangency, which way an angle turns), so a dimension
    keeps the shape and never flips it."""
    k, x, d = con.kind, sk.x, con.data
    if k == "TANGENT":
        if rs[0].geo.kind == "LINE" or rs[1].geo.kind == "LINE":
            ln, rd = (rs[0], rs[1]) if rs[0].geo.kind == "LINE" else (rs[1], rs[0])
            s, e = _line(sk, ln)
            c = rd.geo.pts["C"]
            d["side"] = 1.0 if _signed_dist(sk, c, s, e) >= 0 else -1.0
        else:
            c1, c2 = rs[0].geo.pts["C"], rs[1].geo.pts["C"]
            dist = math.hypot(x[c1] - x[c2], x[c1 + 1] - x[c2 + 1])
            r1, r2 = sk.radius(rs[0].geo), sk.radius(rs[1].geo)
            d["inner"] = abs(dist - abs(r1 - r2)) < abs(dist - (r1 + r2))
    elif k == "FIX":
        if rs[0].is_point:
            d["at"] = [x[rs[0].point], x[rs[0].point + 1]]
        else:
            g = rs[0].geo
            d["at"] = {role: [x[p], x[p + 1]] for role, p in g.pts.items()}
            if g.r is not None:
                d["r"] = x[g.r]
    elif k == "DIST":
        if rs[0].is_point and rs[1].is_point:
            p, q = rs[0].point, rs[1].point
            d["now"] = math.hypot(x[p] - x[q], x[p + 1] - x[q + 1])
        else:
            pt, ln = (rs[0], rs[1]) if rs[0].is_point else (rs[1], rs[0])
            if pt.is_point:
                p = pt.point
            else:  # two lines: from the first line's start to the other line
                pt, ln = rs[1], rs[0]
                p = pt.geo.pts["S"]
            s, e = _line(sk, ln)
            sd = _signed_dist(sk, p, s, e)
            d["side"] = 1.0 if sd >= 0 else -1.0
            d["now"] = abs(sd)
    elif k in ("HDIST", "VDIST"):
        j = 0 if k == "HDIST" else 1
        if len(rs) == 1:
            p, q = _line(sk, rs[0])
        else:
            p, q = rs[0].point, rs[1].point
        delta = x[q + j] - x[p + j]
        d["side"] = 1.0 if delta >= 0 else -1.0
        d["now"] = abs(delta)
    elif k == "LENGTH":
        s, e = _line(sk, rs[0])
        d["now"] = math.hypot(x[e] - x[s], x[e + 1] - x[s + 1])
    elif k in ("RADIUS", "DIAMETER"):
        d["now"] = sk.radius(rs[0].geo) * (2 if k == "DIAMETER" else 1)
    elif k == "ANGLE":
        a = _cur_angle(sk, rs[0], rs[1] if len(rs) > 1 else None)
        d["side"] = 1.0 if a >= 0 else -1.0
        d["now"] = abs(a)
        # measure the angle the user sees: between 0 and 180
    elif k == "SYMMETRIC":
        pass


def _build(sk: Sketch, con: Con, scale: float) -> list[solver.Constraint]:
    """The solver equations of one constraint."""
    rs = [sk.ref(r) for r in con.refs]
    k, d, val, tag = con.kind, con.data, con.value, con.n
    C = solver.Constraint
    out: list[solver.Constraint] = []

    def pts(*rr):
        idx = []
        for p in rr:
            idx += [p, p + 1]
        return tuple(idx)

    if k == "COINCIDENT":
        p, q = rs[0].point, rs[1].point
        out.append(C(tag, pts(p, q), lambda v: [v[0] - v[2], v[1] - v[3]]))
    elif k == "ON":
        p = rs[0].point
        g = rs[1].geo
        if g.kind == "LINE":
            s, e = _line(sk, rs[1])
            out.append(C(tag, pts(p, s, e), _on_line))
        elif g.kind == "CIRCLE":
            c = g.pts["C"]
            out.append(C(tag, pts(p, c) + (g.r,), lambda v: [math.hypot(v[0] - v[2], v[1] - v[3]) - abs(v[4])]))
        else:
            c, s = g.pts["C"], g.pts["S"]
            out.append(C(tag, pts(p, c, s), lambda v: [math.hypot(v[0] - v[2], v[1] - v[3])
                                                      - math.hypot(v[4] - v[2], v[5] - v[3])]))
    elif k in ("HORIZONTAL", "VERTICAL"):
        p, q = _line(sk, rs[0]) if len(rs) == 1 else (rs[0].point, rs[1].point)
        j = 1 if k == "HORIZONTAL" else 0
        out.append(C(tag, (p + j, q + j), lambda v: [v[1] - v[0]]))
    elif k in ("PARALLEL", "PERPENDICULAR"):
        s1, e1 = _line(sk, rs[0])
        s2, e2 = _line(sk, rs[1])
        f = _parallel if k == "PARALLEL" else _perpendicular
        out.append(C(tag, pts(s1, e1, s2, e2), lambda v, f=f: [f(v) * scale]))
    elif k == "ANGLE":
        if len(rs) == 1:
            s1, e1 = _O, 2  # the H axis
            s2, e2 = _line(sk, rs[0])
        else:
            s1, e1 = _line(sk, rs[0])
            s2, e2 = _line(sk, rs[1])
        target = math.radians(val) * d.get("side", 1.0)
        out.append(C(tag, pts(s1, e1, s2, e2), lambda v, t=target: [_angle_err(v, t) * scale]))
    elif k == "TANGENT":
        joint = _shared_end(sk, rs[0].geo, rs[1].geo)
        if joint is not None:
            # they meet at an end: tangent there means the radius is square to
            # the line (or both centres are in line with the joint). Written this
            # way the equation has a clean slope; "distance = radius" would not.
            j, g1, g2 = joint
            if g1.kind == "LINE" or g2.kind == "LINE":
                ln, rd = (g1, g2) if g1.kind == "LINE" else (g2, g1)
                c = rd.pts["C"]
                out.append(C(tag, pts(ln.pts["S"], ln.pts["E"], c, j), lambda v: [_square(v) * scale]))
            else:
                out.append(C(tag, pts(g1.pts["C"], j, g2.pts["C"], j), lambda v: [_parallel(v) * scale]))
        elif rs[0].geo.kind == "LINE" or rs[1].geo.kind == "LINE":
            ln, rd = (rs[0], rs[1]) if rs[0].geo.kind == "LINE" else (rs[1], rs[0])
            s, e = _line(sk, ln)
            c, ri, sp = _round(sk, rd)
            side = d.get("side", 1.0)
            if ri is not None:
                out.append(C(tag, pts(c, s, e) + (ri,), lambda v, sd=side: [_sd(v, 0, 2, 4) - sd * abs(v[6])]))
            else:
                out.append(C(tag, pts(c, s, e, sp), lambda v, sd=side: [_sd(v, 0, 2, 4) - sd * math.hypot(
                    v[6] - v[0], v[7] - v[1])]))
        else:
            idx: list[int] = []
            slots = []
            for r in rs:
                c, ri, sp = _round(sk, r)
                base = len(idx)
                idx += [c, c + 1]
                if ri is not None:
                    idx.append(ri)
                    slots.append((base, base + 2, None))
                else:
                    idx += [sp, sp + 1]
                    slots.append((base, base + 2, base + 3))
            inner = d.get("inner", False)

            def tan_cc(v, slots=slots, inner=inner):
                rr = []
                for c0, a, b in slots:
                    rr.append(abs(v[a]) if b is None else math.hypot(v[a] - v[c0], v[b] - v[c0 + 1]))
                (c1, _, _), (c2, _, _) = slots
                dist = math.hypot(v[c1] - v[c2], v[c1 + 1] - v[c2 + 1])
                return [dist - (abs(rr[0] - rr[1]) if inner else rr[0] + rr[1])]

            out.append(C(tag, tuple(idx), tan_cc))
    elif k == "EQUAL":
        if rs[0].geo.kind == "LINE":
            s1, e1 = _line(sk, rs[0])
            s2, e2 = _line(sk, rs[1])
            out.append(C(tag, pts(s1, e1, s2, e2), lambda v: [math.hypot(v[2] - v[0], v[3] - v[1])
                                                             - math.hypot(v[6] - v[4], v[7] - v[5])]))
        else:
            idx, slots = [], []
            for r in rs:
                c, ri, sp = _round(sk, r)
                if ri is not None:
                    slots.append((len(idx), None))
                    idx.append(ri)
                else:
                    slots.append((len(idx), len(idx) + 2))
                    idx += [c, c + 1, sp, sp + 1]

            def rad(v, s):
                a, b = s
                return abs(v[a]) if b is None else math.hypot(v[b] - v[a], v[b + 1] - v[a + 1])

            out.append(C(tag, tuple(idx), lambda v, sl=slots: [rad(v, sl[0]) - rad(v, sl[1])]))
    elif k == "MIDPOINT":
        p = rs[0].point
        s, e = _line(sk, rs[1])
        out.append(C(tag, pts(p, s, e), lambda v: [v[0] - (v[2] + v[4]) / 2, v[1] - (v[3] + v[5]) / 2]))
    elif k == "SYMMETRIC":
        p, q = rs[0].point, rs[1].point
        s, e = _line(sk, rs[2])

        def sym(v):
            mx, my = (v[0] + v[2]) / 2, (v[1] + v[3]) / 2
            dx, dy = v[6] - v[4], v[7] - v[5]
            L = math.hypot(dx, dy) or 1e-12
            on = (dx * (my - v[5]) - dy * (mx - v[4])) / L
            perp = ((v[2] - v[0]) * dx + (v[3] - v[1]) * dy) / L
            return [on, perp]

        out.append(C(tag, pts(p, q, s, e), sym))
    elif k == "CONCENTRIC":
        c1, c2 = rs[0].geo.pts["C"], rs[1].geo.pts["C"]
        out.append(C(tag, pts(c1, c2), lambda v: [v[0] - v[2], v[1] - v[3]]))
    elif k == "FIX":
        if rs[0].is_point:
            at = d["at"]
            out.append(C(tag, pts(rs[0].point), lambda v, a=at: [v[0] - a[0], v[1] - a[1]]))
        else:
            g = rs[0].geo
            for role, p in g.pts.items():
                a = d["at"][role]
                out.append(C(tag, pts(p), lambda v, a=a: [v[0] - a[0], v[1] - a[1]]))
            if g.r is not None:
                out.append(C(tag, (g.r,), lambda v, r=d["r"]: [v[0] - r]))
    elif k == "DIST":
        if rs[0].is_point and rs[1].is_point:
            out.append(C(tag, pts(rs[0].point, rs[1].point),
                         lambda v, t=val: [math.hypot(v[0] - v[2], v[1] - v[3]) - t]))
        else:
            pt, ln = (rs[0], rs[1]) if rs[0].is_point else (rs[1], rs[0])
            if pt.is_point:
                p = pt.point
                s, e = _line(sk, ln)
                out.append(C(tag, pts(p, s, e), lambda v, t=val * d.get("side", 1.0): [_sd(v, 0, 2, 4) - t]))
            else:  # two lines: parallel, at this distance
                l1, l2 = rs[0], rs[1]
                s1, e1 = _line(sk, l1)
                s2, e2 = _line(sk, l2)
                out.append(C(tag, pts(s2, s1, e1), lambda v, t=val * d.get("side", 1.0): [_sd(v, 0, 2, 4) - t]))
                out.append(C(tag, pts(s1, e1, s2, e2), lambda v: [_parallel(v) * scale]))
    elif k in ("HDIST", "VDIST"):
        j = 0 if k == "HDIST" else 1
        p, q = _line(sk, rs[0]) if len(rs) == 1 else (rs[0].point, rs[1].point)
        out.append(C(tag, (p + j, q + j), lambda v, t=val * d.get("side", 1.0): [v[1] - v[0] - t]))
    elif k == "LENGTH":
        s, e = _line(sk, rs[0])
        out.append(C(tag, pts(s, e), lambda v, t=val: [math.hypot(v[2] - v[0], v[3] - v[1]) - t]))
    elif k in ("RADIUS", "DIAMETER"):
        r = val / 2 if k == "DIAMETER" else val
        c, ri, sp = _round(sk, rs[0])
        if ri is not None:
            out.append(C(tag, (ri,), lambda v, t=r: [abs(v[0]) - t]))
        else:
            out.append(C(tag, pts(c, sp), lambda v, t=r: [math.hypot(v[2] - v[0], v[3] - v[1]) - t]))
    return out


def _shared_end(sk: Sketch, a: Geo, b: Geo):
    """(point, a, b) when an end of a and an end of b are tied by COINCIDENT
    (the point is the arc's end, or a's end for two arcs), else None."""
    ends_a = {a.pts[r] for r in ("S", "E") if r in a.pts}
    ends_b = {b.pts[r] for r in ("S", "E") if r in b.pts}
    if not ends_a or not ends_b:
        return None
    for c in sk.cons.values():
        if c.kind != "COINCIDENT":
            continue
        p, q = (sk.ref(r).point for r in c.refs)
        for x, y in ((p, q), (q, p)):
            if x in ends_a and y in ends_b:
                return (y if a.kind == "LINE" else x), a, b
    return None


def _square(v) -> float:
    """Cosine between the line v[0:4] and the radius from v[4:6] to v[6:8]."""
    d1 = (v[2] - v[0], v[3] - v[1])
    d2 = (v[6] - v[4], v[7] - v[5])
    n = (math.hypot(*d1) * math.hypot(*d2)) or 1e-12
    return (d1[0] * d2[0] + d1[1] * d2[1]) / n


def _sd(v, p, s, e) -> float:
    """Signed distance of point v[p:p+2] from the line v[s:s+2] -> v[e:e+2]."""
    dx, dy = v[e] - v[s], v[e + 1] - v[s + 1]
    L = math.hypot(dx, dy) or 1e-12
    return (dx * (v[p + 1] - v[s + 1]) - dy * (v[p] - v[s])) / L


def _on_line(v):
    return [_sd(v, 0, 2, 4)]


def _dirs(v):
    d1 = (v[2] - v[0], v[3] - v[1])
    d2 = (v[6] - v[4], v[7] - v[5])
    n = (math.hypot(*d1) * math.hypot(*d2)) or 1e-12
    return d1, d2, n


def _parallel(v) -> float:
    d1, d2, n = _dirs(v)
    return (d1[0] * d2[1] - d1[1] * d2[0]) / n


def _perpendicular(v) -> float:
    d1, d2, n = _dirs(v)
    return (d1[0] * d2[0] + d1[1] * d2[1]) / n


def _angle_err(v, target: float) -> float:
    d1, d2, _ = _dirs(v)
    a = math.atan2(d1[0] * d2[1] - d1[1] * d2[0], d1[0] * d2[0] + d1[1] * d2[1])
    err = a - target
    return math.atan2(math.sin(err), math.cos(err))
