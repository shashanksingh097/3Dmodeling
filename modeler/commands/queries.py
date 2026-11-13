"""Model queries usable inside expressions: ``VOL(3)``, ``CENT(3).z``, ``NSEL()`` ...

Each takes IDs (or body names) and returns a number, a point or a record.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from ..core.model import ModelError, check_kind
from ..lang.expr import ExprError, Record, Vec

if TYPE_CHECKING:
    from .processor import Processor

try:
    from OCP.TopoDS import TopoDS

    _as_vertex = getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex
except ImportError:  # pragma: no cover
    _as_vertex = None


def props(kind: str, shape) -> GProp_GProps:
    g = GProp_GProps()
    if kind == "BODY":
        BRepGProp.VolumeProperties_s(shape, g)
    elif kind == "FACE":
        BRepGProp.SurfaceProperties_s(shape, g)
    elif kind == "EDGE":
        BRepGProp.LinearProperties_s(shape, g)
    return g


def centre(kind: str, shape) -> Vec:
    if kind == "VERTEX":
        p = BRep_Tool.Pnt_s(_as_vertex(shape))
    else:
        p = props(kind, shape).CentreOfMass()
    return Vec((p.X(), p.Y(), p.Z()))


def bbox(shape) -> tuple[float, ...]:
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)  # tight box, no tolerance gap
    lo, hi = box.CornerMin(), box.CornerMax()
    return lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()


def functions(p: "Processor") -> dict[str, Callable[..., Any]]:
    m = p.model

    def body_id(v, fn: str) -> int:
        if isinstance(v, str):
            b = m.body_by_name(v)
            if b is None:
                raise ExprError(f"{fn}(): no body named {v!r}")
            return b.id
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not float(v).is_integer():
            raise ExprError(f"{fn}() needs a body ID or name")
        return int(v)

    def shape_of(fn: str, ident, kind="BODY"):
        if not isinstance(kind, str):
            raise ExprError(f"{fn}(): the kind must be text such as \"FACE\"")
        try:
            k = check_kind(kind)
            gid = body_id(ident, fn) if k == "BODY" else int(ident)
            return k, m.entity_shape(k, gid)
        except ModelError as exc:
            raise ExprError(f"{fn}(): {exc}") from None

    def vol(b):
        return props("BODY", shape_of("VOL", b)[1]).Mass()

    def area(i, kind="FACE"):
        k, s = shape_of("AREA", i, kind)
        return props("FACE", s).Mass()

    def length(i):
        return props("EDGE", shape_of("LENGTH", i, "EDGE")[1]).Mass()

    def cent(i, kind="BODY"):
        k, s = shape_of("CENT", i, kind)
        return centre(k, s)

    def box(i, kind="BODY"):
        _, s = shape_of("BBOX", i, kind)
        x0, y0, z0, x1, y1, z1 = bbox(s)
        return Record("BBOX", xmin=x0, ymin=y0, zmin=z0, xmax=x1, ymax=y1, zmax=z1, dx=x1 - x0, dy=y1 - y0, dz=z1 - z0)

    def nsel(kind=None):
        if kind is not None and check_kind(str(kind)) != m.selection_kind:
            return 0
        return len(m.selection)

    def selid(n=1):
        n = int(n)
        if not 1 <= n <= len(m.selection):
            raise ExprError(f"SELID({n}): only {len(m.selection)} selected")
        return m.selection[n - 1]

    def count(kind="BODY"):
        return len(m.entity_ids(check_kind(str(kind))))

    def body(name):
        return body_id(name, "BODY")

    def owner(i, kind="FACE"):
        try:
            return m.entity_owner(check_kind(str(kind)), int(i))[0]
        except ModelError as exc:
            raise ExprError(f"OWNER(): {exc}") from None

    def exists(i, kind="BODY"):
        try:
            shape_of("EXISTS", i, kind)
            return 1
        except ExprError:
            return 0

    def param(name, default=None):
        try:
            return p._lookup(str(name).upper())
        except KeyError:
            if default is None:
                raise ExprError(f"PARAM(): no parameter {name!r}") from None
            return default

    def datum(name, fn):
        if not isinstance(name, str):
            raise ExprError(f"{fn}(): give the datum's name in quotes, e.g. {fn}(\"mid\")")
        key = name.upper()
        from ..core import datum as dt

        if key in dt.BASE_PLANES:
            o, n = dt.BASE_PLANES[key]
            return dt.plane(o, n, name=key)
        if key in dt.BASE_AXES:
            return dt.axis((0, 0, 0), dt.BASE_AXES[key], name=key)
        try:
            return m.datum(name)
        except ModelError as exc:
            raise ExprError(f"{fn}(): {exc}") from None

    def origin(name):
        return Vec(datum(name, "ORIGIN").origin)

    def direction(name):
        return Vec(datum(name, "DIR").z)

    def gap(a, b):
        from ..geometry.features import distance

        return distance(m.body(body_id(a, "GAP")).shape, m.body(body_id(b, "GAP")).shape)[0]

    def pitch(d):
        from ..geometry.threads import coarse_for_shaft

        c = coarse_for_shaft(float(d))
        if c is None:
            raise ExprError(f"PITCH({d:g}): not an ISO metric coarse size")
        return c[1]

    def shape_body(b, fn):
        return m.body(body_id(b, fn)).shape

    def valid(b):
        from ..geometry import robust

        return 1 if robust.report(shape_body(b, "VALID"))["ok"] else 0

    def pieces(b):
        from ..geometry import robust

        return len(robust.solids(shape_body(b, "PIECES")))

    def nfaces(b, kind=None):
        bid = body_id(b, "NFACES")
        ids = m.body(bid).entity_ids["FACE"]
        if kind is None:
            return len(ids)
        from ..geometry import recognize as rc

        want = str(kind).lower()
        if want not in rc.SURFACE_NAMES.values():
            raise ExprError(f"NFACES(): the type is one of {', '.join(sorted(set(rc.SURFACE_NAMES.values())))}")
        return sum(1 for i in ids if rc.surface_type(m.entity_shape("FACE", i)) == want)

    def holes(b, d=None, through=None):
        from ..geometry import recognize as rc

        found = rc.holes(shape_body(b, "HOLES"), m.tolerance)
        if d is not None and float(d) > 0:
            tol = 1e-6 * max(1.0, float(d)) + m.tolerance
            found = [h for h in found if abs(h.d - float(d)) <= tol]
        if through is not None:
            found = [h for h in found if h.through == bool(through)]
        return len(found)

    def symmetric(b, plane):
        from ..geometry import recognize as rc

        d = datum(plane, "SYMMETRIC")
        if d.kind != "PLANE":
            raise ExprError("SYMMETRIC(): give a plane, e.g. SYMMETRIC(b, \"YZ\")")
        try:
            return 1 if rc.mirror_matches(shape_body(b, "SYMMETRIC"), d.origin, d.z) else 0
        except ValueError as exc:
            raise ExprError(f"SYMMETRIC(): {exc}") from None

    def minwall(b):
        from ..ai.probe import min_wall

        return min_wall(shape_body(b, "MINWALL"))

    def _nurbs(b, fn):
        from ..geometry import nurbs as nb

        try:
            return nb, nb.geometry_of(m.body(body_id(b, fn)).shape, need_whole=False)
        except (nb.CurveError, ModelError) as exc:
            raise ExprError(f"{fn}(): {exc}") from None

    def pole(b, i, j=None):
        nb, g = _nurbs(b, "POLE")
        idx = (int(i),) if j is None else (int(i), int(j))
        try:
            return Vec(nb.pole(g, idx))
        except nb.CurveError as exc:
            raise ExprError(f"POLE(): {exc}") from None

    def npoles(b, direction="U"):
        nb, g = _nurbs(b, "NPOLES")
        if isinstance(g, nb.Geom_BSplineCurve):
            return g.NbPoles()
        return g.NbUPoles() if str(direction).upper() == "U" else g.NbVPoles()

    def _along(b, t, fn):
        from ..geometry import curves as cv
        from ..geometry import sweep as sw

        try:
            ps = sw.PathSampler(sw.as_wire(m.body(body_id(b, fn)).shape, f"the {fn}() body"))
        except (cv.CurveError, ModelError) as exc:
            raise ExprError(f"{fn}(): {exc}") from None
        t = float(t)
        if not 0 <= t <= 1:
            raise ExprError(f"{fn}(): t goes from 0 (the start) to 1 (the end), got {t:g}")
        return ps.at(ps.length * t)

    def curve_point(b, t):
        return Vec(_along(b, t, "CURVEPT")[0])

    def curve_tangent(b, t):
        return Vec(_along(b, t, "CURVETAN")[1])

    return {
        "CURVEPT": curve_point,
        "CURVETAN": curve_tangent,
        "POLE": pole,
        "NPOLES": npoles,
        "MINWALL": minwall,
        "VALID": valid,
        "PIECES": pieces,
        "NFACES": nfaces,
        "HOLES": holes,
        "SYMMETRIC": symmetric,
        "PITCH": pitch,
        "ORIGIN": origin,
        "DIR": direction,
        "GAP": gap,
        "VOL": vol,
        "AREA": area,
        "LENGTH": length,
        "CENT": cent,
        "BBOX": box,
        "NSEL": nsel,
        "SELID": selid,
        "COUNT": count,
        "BODY": body,
        "OWNER": owner,
        "EXISTS": exists,
        "PARAM": param,
    }
