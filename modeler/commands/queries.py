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
    if box.IsVoid():  # a mesh body has only triangles
        BRepBndLib.Add_s(shape, box, True)
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

    def _contact(fn, a, b):
        from ..ai import contact as cx
        from ..ai.describe import DescribeError

        try:
            return cx.pair_state(p, body_id(a, fn), body_id(b, fn))
        except (DescribeError, ValueError) as exc:
            raise ExprError(f"{fn}(): {exc}") from None

    def touch(a, b):
        return 1 if _contact("TOUCH", a, b).state == "touch" else 0

    def overlap(a, b):
        return _contact("OVERLAP", a, b).volume

    def contact_area(a, b):
        return _contact("CONTACTAREA", a, b).area

    def groups():
        from ..ai import contact as cx
        from ..ai.describe import DescribeError

        try:
            return cx.group_count(p)
        except DescribeError as exc:
            raise ExprError(f"GROUPS(): {exc}") from None

    def fitgap(a, b):
        from ..ai import contact as cx
        from ..ai.describe import DescribeError

        try:
            return cx.tightest_fit(p, body_id(a, "CLEARANCE"), body_id(b, "CLEARANCE"))
        except DescribeError as exc:
            raise ExprError(f"CLEARANCE(): {exc}") from None

    # ---- the analysis checks as numbers (their reports, see Processor.give_report) ----
    def quiet(fn, *args):
        """Run a check's handler for its report only: no colours or marks in the view, and
        the model's own analysis and reports left as they were. Cached per model state."""
        key = (fn.__name__, args, id(m), m.units,
               tuple((i, id(b.shape), b.material, i in m.hidden) for i, b in sorted(m.bodies.items())),
               tuple((k, v[0], tuple(v[1])) for k, v in sorted(m.named_sets.items())))
        cache = p.__dict__.setdefault("_query_reports", {})
        if key in cache:
            return cache[key]
        from .processor import CommandError

        saved = (p.view, getattr(p, "analysis", None), p.last_report, dict(p.reports))
        p.view = None
        try:
            fn(p, *args)
            rep = p.last_report
        except CommandError as exc:
            raise ExprError(str(exc)) from None
        finally:
            p.view, p.analysis, p.last_report = saved[0], saved[1], saved[2]
            p.reports.clear()
            p.reports.update(saved[3])
        if len(cache) > 32:
            cache.clear()
        cache[key] = rep
        return rep

    def mass(b):
        from ..core.model import UNITS

        bid = body_id(b, "MASS")
        dens = m.density(bid)
        if not dens:
            raise ExprError(f"MASS(): body {bid} has no material (MATERIAL, b, STEEL) to weigh it")
        g = props("BODY", m.body(bid).shape)
        return dens * abs(g.Mass()) * (UNITS[m.units] / 1000.0) ** 3

    def stress_report(fn, b, fixed, loaded, fx=0.0, fy=0.0, fz=0.0, h=0.0):
        from .stress_handlers import stress

        bid = body_id(b, fn)
        return quiet(stress, bid, str(fixed), str(loaded), "FORCE", float(fx), float(fy), float(fz), float(h))

    def safety(b, fixed, loaded, fx=0.0, fy=0.0, fz=0.0, h=0.0):
        sf = stress_report("SAFETY", b, fixed, loaded, fx, fy, fz, h)["safety_factor"]
        return float("inf") if sf is None else sf

    def maxstress(b, fixed, loaded, fx=0.0, fy=0.0, fz=0.0, h=0.0):
        return stress_report("MAXSTRESS", b, fixed, loaded, fx, fy, fz, h)["max_stress_MPa"]

    def deflect(b, fixed, loaded, fx=0.0, fy=0.0, fz=0.0, h=0.0):
        return stress_report("DEFLECT", b, fixed, loaded, fx, fy, fz, h)["max_deflection_mm"]

    def overhangs(b, angle=45.0, up="+Z"):
        from .print_handlers import printcheck

        return quiet(printcheck, body_id(b, "OVERHANGS"), str(up), float(angle), 0.0)["overhang_area"]

    def gravity_report(ground="FLOOR", fastened=""):
        from .gravity_handlers import gravity

        g = ground if isinstance(ground, str) else str(body_id(ground, "FLOATING"))
        return quiet(gravity, g, str(fastened), 0.0, 0.0, -1.0, 0.0)

    def floating(ground="FLOOR", fastened=""):
        return len(gravity_report(ground, fastened)["problems"])

    def tipangle(ground="FLOOR", fastened=""):
        a = gravity_report(ground, fastened)["tip_angle"]
        return 0.0 if a is None else a

    def qty(name):
        from .config_handlers import bom_rows

        want = str(name).strip().upper()
        return sum(r["qty"] for r in bom_rows(p) if r["name"].upper() == want)

    def sameshape(a, b):
        from ..ai import relate as rl
        from ..ai.describe import DescribeError

        try:
            return 1 if rl.compare(p, body_id(a, "SAMESHAPE"), body_id(b, "SAMESHAPE"))["same"] else 0
        except DescribeError as exc:
            raise ExprError(f"SAMESHAPE(): {exc}") from None

    def problems(b, min_wall=0.0):
        from ..ai import relate as rl
        from ..ai.describe import DescribeError

        try:
            return len(rl.design_check(p, body_id(b, "PROBLEMS"), float(min_wall))["problems"])
        except DescribeError as exc:
            raise ExprError(f"PROBLEMS(): {exc}") from None

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
        "TOUCH": touch,
        "OVERLAP": overlap,
        "CONTACTAREA": contact_area,
        "GROUPS": groups,
        "SAMESHAPE": sameshape,
        "PROBLEMS": problems,
        "MASS": mass,
        "SAFETY": safety,
        "MAXSTRESS": maxstress,
        "DEFLECT": deflect,
        "OVERHANGS": overhangs,
        "FLOATING": floating,
        "TIPANGLE": tipangle,
        "QTY": qty,
        "CLEARANCE": fitgap,
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
