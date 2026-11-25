"""Reading the model as compact, exact data: the model summary, one body, faces and edges.

These are what replace looking at a picture. Every answer is a plain dict
(JSON-ready) with short keys, numbers rounded to what is worth reading
(3 decimals by default), the unit once, and the model revision, so two
answers can be compared. Lists are in ID order and cut at ``limit`` with
``more: n`` saying how many were left out.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_WIRE

from ..commands.queries import bbox, centre, props
from ..core.model import ModelError
from ..geometry import recognize as rc
from ..geometry import robust

if TYPE_CHECKING:
    from ..commands.processor import Processor

DIGITS = 3
LIMIT = 200  # rows in one answer before it is cut


class DescribeError(Exception):
    pass


def num(x: float, digits: int = DIGITS) -> float:
    """A number as it is worth reading: rounded, and never -0.0."""
    v = round(float(x), digits)
    return 0.0 if v == 0 else v


def vec(v, digits: int = DIGITS) -> list[float]:
    return [num(c, digits) for c in v]


def entry_number(p: "Processor", uid: int) -> int | None:
    """1-based history entry with this uid, or None (made outside the history)."""
    if not uid:
        return None
    for i, e in enumerate(p.history, 1):
        if e.uid == uid:
            return i
    return None


def made_by(p: "Processor", kind: str, gid: int) -> int | None:
    return entry_number(p, p.model.origin(kind, gid))


def body_kind(shape) -> str:
    from ..geometry import meshbody, pointcloud

    if pointcloud.is_points(shape):
        return "points"
    if meshbody.is_mesh(shape):  # a mesh body: closed ones have an inside
        return "solid" if meshbody.info(shape).closed else "surface"
    if robust.count(shape, TopAbs_SOLID):
        return "solid"
    if robust.count(shape, TopAbs_SHELL) or robust.count(shape, TopAbs_FACE):
        return "surface"
    if robust.count(shape, TopAbs_WIRE):
        return "curve"
    return "other"


POINTS_CAN = ("a point cloud (scanner points): FITPOINTS fits a plane, cylinder, sphere, cone or freeform face "
              "to a patch of it, DEVIATION measures it against a model, MOVE/ROTATE/HIDE; it has no faces")
FACETED_CAN = ("booleans (UNION, SUBTRACT, INTERSECT), SPLIT, SECTION, PROFILE, PROBE, measuring, "
               "MOVE/ROTATE/SCALE/ARRAY, export")
FACETED_CANNOT = ("FILLET, CHAMFER, SHELL, OFFSET and DRAFT across facets, HOLE on curved areas, and "
                  "PUSHPULL or MOVEFACE of curved areas: every triangle is its own flat face")
MESH_CAN = ("UNION, SUBTRACT, INTERSECT with meshes or solids (fast, on triangles), SMOOTH, REMESH, SIMPLIFY, "
            "MOVE/ROTATE/COPY/MIRROR, BEND/TWIST/TAPER/STRETCH/FLOW, MASSPROP, export to STL/OBJ/3MF/GLTF")
MESH_CANNOT = ("anything that needs faces and edges (FILLET, HOLE, SHELL, SPLIT, SECTION, picks of single "
               "triangles): TOSOLID turns it into a faceted solid first (up to 100,000 triangles)")
_MESH_FORMATS = {"STL", "OBJ", "3MF", "GLTF", "PLY", "OFF", "VTK", "MESH"}


def representation(shape, sample: int = 400) -> str:
    """'mesh' for a mesh body, 'faceted' when the faces are flat triangles (a mesh made into a
    B-rep body), else 'exact'."""
    from OCP.TopAbs import TopAbs_EDGE

    from ..geometry import meshbody, pointcloud

    if meshbody.is_mesh(shape):
        return "mesh"
    if pointcloud.is_points(shape):
        return "points"
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
    n = tri = 0
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More() and n < sample:
        face = as_face(ex.Current())
        ex.Next()
        n += 1
        if BRepAdaptor_Surface(face).GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
            continue
        edges = 0
        ee = TopExp_Explorer(face, TopAbs_EDGE)
        while ee.More() and edges < 4:
            edges += 1
            ee.Next()
        tri += edges == 3
    return "faceted" if n >= 12 and tri >= 0.9 * n else "exact"


def origin_info(p: "Processor", bid: int) -> dict[str, Any]:
    """Where a body came from: the IMPORT that read it (format and file), when it was imported."""
    n = made_by(p, "BODY", bid)
    if not n:
        return {}
    lines = [x.strip() for x in p.history[n - 1].text.splitlines() if x.strip().upper().startswith("IMPORT")]
    rows = [[x.strip().strip('"\'') for x in line.split(",")] for line in lines]
    name = p.model.bodies[bid].name.upper()
    named = [r for r in rows if len(r) > 3 and r[3].upper() == name]
    rows = named or (rows if len(rows) == 1 else [])
    if not rows:
        return {}
    parts = rows[0]
    out: dict[str, Any] = {"imported": True}
    if len(parts) > 1:
        out["format"] = parts[1].upper()
    if len(parts) > 2:
        out["file"] = parts[2].replace("\\", "/").rsplit("/", 1)[-1]
    return out


def find_body(p: "Processor", ref) -> int:
    """A body by ID, name, or a parameter holding either."""
    m = p.model
    if isinstance(ref, str):
        b = m.body_by_name(ref)
        if b is not None:
            return b.id
        try:
            ref = p.evaluate(ref)
        except Exception:
            raise DescribeError(f"no body named {ref!r}") from None
        if isinstance(ref, str):
            b = m.body_by_name(ref)
            if b is None:
                raise DescribeError(f"no body named {ref!r}")
            return b.id
    if isinstance(ref, bool) or not isinstance(ref, (int, float)) or not float(ref).is_integer():
        raise DescribeError(f"a body is an ID or a name, got {ref!r}")
    if int(ref) not in m.bodies:
        raise DescribeError(f"no body {int(ref)}")
    return int(ref)


# ---- the model ---------------------------------------------------------------------


def model_summary(p: "Processor", limit: int = LIMIT) -> dict[str, Any]:
    """Everything in the model, one short row per thing."""
    m = p.model
    bodies = []
    for bid in sorted(m.bodies)[:limit]:
        b = m.bodies[bid]
        kind = body_kind(b.shape)
        row: dict[str, Any] = {"id": bid, "name": b.name, "kind": kind}
        if kind == "solid":
            row["volume"] = num(robust.volume(b.shape))
        rep = representation(b.shape)
        if rep == "faceted":
            row["faceted"] = True
        elif rep == "mesh":
            row["mesh"] = True
        src = origin_info(p, bid)
        if src:
            row["imported"] = src.get("format", True)
        row["bbox"] = vec(bbox(b.shape))
        pieces = len(robust.solids(b.shape))
        if pieces > 1:
            row["pieces"] = pieces
        if not m.is_shown(bid):
            row["hidden"] = True
        if b.layer != "DEFAULT":
            row["layer"] = b.layer
        if b.material:
            row["material"] = b.material.lower()
        bodies.append(row)
    out: dict[str, Any] = {"rev": m.revision, "unit": m.units.lower()}
    if m.tolerance:
        out["tol"] = m.tolerance
    out["bodies"] = bodies
    if len(m.bodies) > limit:
        out["more"] = len(m.bodies) - limit
    if p.params:
        out["params"] = {k: _value(v) for k, v in p.params.items()}
    if m.datums:
        out["datums"] = [{"name": d.name, "kind": d.kind.lower(), "at": vec(d.origin),
                          **({"dir": vec(d.z)} if d.kind != "POINT" else {})} for d in m.datums.values()]
    if m.sketches:
        out["sketches"] = [sk.name for sk in m.sketches.values()]
    if m.named_sets:
        # named as typed; face, edge and point sets also go to STEP files by name (PLAN item 95)
        out["sets"] = {m.set_label(k): {"kind": kind, "ids": ids}
                       for k, (kind, ids) in m.named_sets.items()}
    if m.selection:
        out["selection"] = {"kind": m.selection_kind, "ids": list(m.selection)}
    hist = p.history[: p.cursor]
    out["history"] = {"entries": len(hist),
                      "warnings": sum(1 for e in hist if e.warning),
                      "suppressed": sum(1 for e in hist if e.suppressed)}
    if len(p.history) > p.cursor:
        out["history"]["undone"] = len(p.history) - p.cursor
    return out


def _value(v):
    from ..lang.expr import Vec

    if isinstance(v, Vec):
        return vec(v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return num(v, 6)
    return v


# ---- one body ----------------------------------------------------------------------


def describe_body(p: "Processor", ref, detail: str = "summary", limit: int = LIMIT) -> dict[str, Any]:
    """One body. detail: summary (default), faces, edges."""
    detail = detail.lower()
    if detail not in ("summary", "faces", "edges"):
        raise DescribeError("detail is summary, faces or edges")
    m = p.model
    bid = find_body(p, ref)
    b = m.bodies[bid]
    shape = b.shape
    kind = body_kind(shape)
    out: dict[str, Any] = {"rev": m.revision, "unit": m.units.lower(), "body": bid, "name": b.name, "kind": kind}
    rep = robust.report(shape)
    out["valid"] = bool(rep["ok"])
    if kind == "solid":
        out["volume"] = num(rep["volume"])
        out["pieces"] = rep["solids"]
    out["area"] = num(props("FACE", shape).Mass())
    out["bbox"] = vec(bbox(shape))
    if kind == "solid":
        out["centre"] = vec(centre("BODY", shape))
    out["counts"] = {name: len(b.entity_ids[k]) for k, name in (("FACE", "faces"), ("EDGE", "edges"),
                                                                ("VERTEX", "vertices"))}
    if rep["open_edges"] and kind == "solid":
        out["open_edges"] = rep["open_edges"]
    mb = made_by(p, "BODY", bid)
    if mb:
        out["made_by"] = mb
    out.update(origin_info(p, bid))
    out["representation"] = representation(shape)
    if out["representation"] == "faceted":
        out["faceted"] = {"triangles": out["counts"]["faces"], "works": FACETED_CAN, "does_not_work": FACETED_CANNOT}
    elif out["representation"] == "mesh":
        from ..geometry import meshbody

        info = meshbody.info(shape)
        out["mesh"] = {"triangles": info.triangles, "closed": info.closed, "works": MESH_CAN,
                       "does_not_work": MESH_CANNOT}
    elif out["representation"] == "points":
        out["points"] = {"count": out["counts"]["vertices"], "works": POINTS_CAN}
    elif out.get("imported"):
        out["note"] = ("exact shape from another program, without its feature history: edit it with HOLE, FILLET, "
                       "CHAMFER, SHELL, PUSHPULL, MOVEFACE, REPLACEFACE, DELFACE (remove holes/fillets), booleans; "
                       "HEAL or CHECK if a step fails")
    if detail == "summary":
        out.update(_body_overview(p, b))
    elif detail == "faces":
        ids = sorted(b.entity_ids["FACE"])
        out["faces"] = [face_row(p, i) for i in ids[:limit]]
        if len(ids) > limit:
            out["more"] = len(ids) - limit
    else:
        ids = sorted(b.entity_ids["EDGE"])
        out["edges"] = [edge_row(p, i) for i in ids[:limit]]
        if len(ids) > limit:
            out["more"] = len(ids) - limit
    return out


def _body_overview(p: "Processor", b) -> dict[str, Any]:
    """Faces grouped by type, flat faces by direction, and the holes."""
    types: dict[str, int] = {}
    normals: dict[str, int] = {}
    for gid in b.entity_ids["FACE"]:
        f = rc.as_face(p.model.entity_shape("FACE", gid))
        t = rc.surface_type(f)
        types[t] = types.get(t, 0) + 1
        if t == "plane":
            key = direction_name(rc.face_normal_at_middle(f)[1])
            normals[key] = normals.get(key, 0) + 1
    out: dict[str, Any] = {"face_types": dict(sorted(types.items(), key=lambda kv: (-kv[1], kv[0])))}
    if normals:
        out["flat_faces"] = dict(sorted(normals.items(), key=lambda kv: (-kv[1], kv[0])))
    found = rc.holes(b.shape, p.model.tolerance)
    if found:
        out["holes"] = hole_groups(p, b, found)
    feats = feature_groups(p, b)
    if feats:
        out["features"] = feats
    return out


def feature_groups(p: "Processor", b, limit: int = 30) -> list[dict[str, Any]]:
    """Fillets and rounds by radius, chamfers by size, bosses by size, and each pocket and slot
    (geometry/feature_finder.py), with the faces of each."""
    from ..geometry import feature_finder as ff

    if representation(b.shape) != "exact":
        return []
    try:
        found = ff.find(b.shape)
    except Exception:  # noqa: BLE001 - naming features must never break describe
        return []
    ids = b.entity_ids["FACE"]
    groups: dict[tuple, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for f in found:
        faces = [ids[i - 1] for i in f.faces]
        if f.kind in ("fillet", "round"):
            key = (f.kind, num(f.size))
            g = groups.setdefault(key, {"kind": f.kind, "r": num(f.size), "n": 0, "faces": []})
            g["n"] += 1
            g["faces"] += faces
        elif f.kind == "chamfer":
            d2 = f.extra.get("d2", f.size)
            key = ("chamfer", num(f.size), num(d2))
            g = groups.setdefault(key, {"kind": "chamfer", "d": num(f.size), "n": 0, "faces": []})
            if num(d2) != num(f.size):
                g["d2"] = num(d2)
            g["n"] += 1
            g["faces"] += faces
        elif f.kind == "boss":
            key = ("boss", num(f.size), num(f.extra["height"]), tuple(_axis_key(f.axis)))
            g = groups.setdefault(key, {"kind": "boss", "d": num(f.size), "height": num(f.extra["height"]),
                                        "axis": direction_name(f.axis), "n": 0, "at": [], "faces": []})
            g["n"] += 1
            g["at"].append(vec(f.at))
            g["faces"] += faces
        else:
            rows.append({"kind": f.kind, "depth": num(f.size), "size": [num(v) for v in f.extra["size"]],
                         "open_to": direction_name(f.axis), "floor": ids[f.extra["floor"] - 1],
                         "at": vec(f.at), "faces": sorted(faces)})
    out = list(groups.values()) + rows
    for g in out:
        g["faces"] = sorted(g["faces"])
        if len(g["faces"]) > 12:
            g["faces"] = g["faces"][:12] + [f"... {len(g['faces']) - 12} more"]
    return out[:limit]


def hole_groups(p: "Processor", b, found: list[rc.Hole]) -> list[dict[str, Any]]:
    """Holes of the same size, depth, direction and kind, as one row each."""
    groups: dict[tuple, dict[str, Any]] = {}
    for h in found:
        axis = _axis_key(h.axis)
        key = (num(h.d), num(h.depth), h.through, tuple(axis), h.counterbore and tuple(num(v) for v in h.counterbore))
        g = groups.get(key)
        if g is None:
            g = {"d": num(h.d), "n": 0, "through": h.through, "depth": num(h.depth), "axis": axis}
            if h.counterbore:
                g["counterbore"] = {"d": num(h.counterbore[0]), "depth": num(h.counterbore[1])}
            g["at"] = []
            g["faces"] = []
            groups[key] = g
        g["n"] += 1
        g["at"].append(vec(h.start if h.through else h.mouth))
        g["faces"].extend(b.entity_ids["FACE"][i - 1] for i in h.faces)
    for g in groups.values():
        if g["through"]:
            del g["depth"]
        g["faces"].sort()
        circle = on_circle(g["at"], g["axis"])
        if circle:
            g["pattern"] = circle
    return list(groups.values())


def on_circle(points: list[list[float]], axis) -> dict[str, Any] | None:
    """Three or more points evenly spaced round a circle square to the axis, or None."""
    n = len(points)
    if n < 3:
        return None
    c = [sum(pt[i] for pt in points) / n for i in range(3)]
    d = rc._norm(axis)
    a = tuple(k / d for k in axis)
    rel = [rc._sub(pt, c) for pt in points]
    if any(abs(rc._dot(v, a)) > 1e-3 for v in rel):
        return None  # not all in one plane square to the axis
    radii = [rc._norm(v) for v in rel]
    r = sum(radii) / n
    if r < 1e-6 or max(abs(x - r) for x in radii) > 1e-3 * max(1.0, r):
        return None
    # angles round the axis, from the first point
    x = tuple(k / radii[0] for k in rel[0])
    y = (a[1] * x[2] - a[2] * x[1], a[2] * x[0] - a[0] * x[2], a[0] * x[1] - a[1] * x[0])
    ang = sorted(math.degrees(math.atan2(rc._dot(v, y), rc._dot(v, x))) % 360 for v in rel)
    steps = [b - a_ for a_, b in zip(ang, ang[1:])] + [ang[0] + 360 - ang[-1]]
    step = 360 / n
    even = max(abs(s - step) for s in steps) < 1e-3
    out: dict[str, Any] = {"circle": vec(c), "r": num(r)}
    if even:
        out["step_deg"] = num(step)
    return out


def _axis_key(d) -> list[float]:
    """An axis direction with a fixed sign, so +Z and -Z holes read the same."""
    v = [num(c, 6) for c in d]
    for c in v:
        if c != 0:
            if c < 0:
                v = [-x if x else 0.0 for x in v]
            break
    return [num(c) for c in v]


_NAMED = {(1, 0, 0): "+X", (-1, 0, 0): "-X", (0, 1, 0): "+Y", (0, -1, 0): "-Y", (0, 0, 1): "+Z", (0, 0, -1): "-Z"}


def direction_name(n) -> str:
    """+Z for an axis direction, else the rounded vector as text."""
    r = tuple(num(c, 6) for c in n)
    for k, name in _NAMED.items():
        if all(abs(a - b) < 1e-6 for a, b in zip(r, k)):
            return name
    return "(" + ", ".join(f"{num(c):g}" for c in n) + ")"


# ---- faces and edges ---------------------------------------------------------------------


def face_row(p: "Processor", gid: int) -> dict[str, Any]:
    m = p.model
    try:
        bid, idx = m.entity_owner("FACE", gid)
    except ModelError as exc:
        raise DescribeError(str(exc)) from None
    body = m.bodies[bid]
    f = rc.as_face(m.entity_shape("FACE", gid))
    s = BRepAdaptor_Surface(f)
    t = s.GetType()
    row: dict[str, Any] = {"id": gid, "body": bid, "type": rc.surface_type(f),
                           "area": num(props("FACE", f).Mass()), "centre": vec(centre("FACE", f))}
    if t == GeomAbs_SurfaceType.GeomAbs_Plane:
        row["normal"] = vec(rc.face_normal_at_middle(f)[1])
    elif t in (GeomAbs_SurfaceType.GeomAbs_Cylinder, GeomAbs_SurfaceType.GeomAbs_Cone,
               GeomAbs_SurfaceType.GeomAbs_Sphere, GeomAbs_SurfaceType.GeomAbs_Torus):
        if t == GeomAbs_SurfaceType.GeomAbs_Cylinder:
            c = s.Cylinder()
            row["r"] = num(c.Radius())
        elif t == GeomAbs_SurfaceType.GeomAbs_Cone:
            c = s.Cone()
            row["r"] = num(c.RefRadius())
            row["half_angle"] = num(math.degrees(c.SemiAngle()))
        elif t == GeomAbs_SurfaceType.GeomAbs_Sphere:
            c = s.Sphere()
            row["r"] = num(c.Radius())
        else:
            c = s.Torus()
            row["r"] = num(c.MinorRadius())
            row["R"] = num(c.MajorRadius())
        ax = c.Position().Axis() if t != GeomAbs_SurfaceType.GeomAbs_Sphere else None
        if ax is not None:
            row["axis"] = {"at": vec(rc._xyz(ax.Location())), "dir": vec(rc._xyz(ax.Direction()))}
        else:
            row["at"] = vec(rc._xyz(c.Location()))
        if t in (GeomAbs_SurfaceType.GeomAbs_Cylinder, GeomAbs_SurfaceType.GeomAbs_Sphere):
            pnt, n = rc.face_normal_at_middle(f)
            ref = rc._xyz(ax.Location()) if ax is not None else rc._xyz(c.Location())
            radial = rc._sub(pnt, ref)
            if ax is not None:
                d = rc._xyz(ax.Direction())
                radial = rc._sub(radial, tuple(k * rc._dot(radial, d) for k in d))
            row["inner"] = rc._dot(radial, n) < 0  # concave: the wall of a hole or a fillet in a corner
    nb = _neighbours_of(body, idx)
    row["next_to"] = nb
    mb = made_by(p, "FACE", gid)
    if mb:
        row["made_by"] = mb
    return row


_NB_CACHE: dict[int, tuple[Any, dict[int, set[int]]]] = {}


def _neighbours_of(body, idx: int) -> list[int]:
    """Face IDs next to face idx of the body (shares an edge)."""
    hit = _NB_CACHE.get(id(body.shape))
    if hit is None or hit[0] is not body.shape:
        _NB_CACHE.clear()
        hit = (body.shape, rc.neighbours(body.shape, body.maps["FACE"]))
        _NB_CACHE[id(body.shape)] = hit
    return sorted(body.entity_ids["FACE"][j - 1] for j in hit[1].get(idx, ()))


def edge_row(p: "Processor", gid: int) -> dict[str, Any]:
    m = p.model
    try:
        bid, idx = m.entity_owner("EDGE", gid)
    except ModelError as exc:
        raise DescribeError(str(exc)) from None
    body = m.bodies[bid]
    e = rc.as_edge(m.entity_shape("EDGE", gid))
    c = BRepAdaptor_Curve(e)
    row: dict[str, Any] = {"id": gid, "body": bid, "type": rc.curve_type(e), "length": num(props("EDGE", e).Mass())}
    if BRep_Tool.Degenerated_s(e):
        row["degenerate"] = True
    p0, p1 = c.Value(c.FirstParameter()), c.Value(c.LastParameter())
    a, b = rc._xyz(p0), rc._xyz(p1)
    if rc._norm(rc._sub(a, b)) < 1e-9:
        row["closed"] = True
        row["at"] = vec(a)
    else:
        row["ends"] = [vec(a), vec(b)]
    if c.GetType() == GeomAbs_CurveType.GeomAbs_Circle:
        circ = c.Circle()
        row["r"] = num(circ.Radius())
        row["centre"] = vec(rc._xyz(circ.Location()))
        row["axis"] = vec(rc._xyz(circ.Axis().Direction()))
    elif c.GetType() == GeomAbs_CurveType.GeomAbs_Line:
        row["dir"] = vec(rc._xyz(c.Line().Direction()))
    em = _edge_faces_of(body)
    k = em.FindIndex(e)
    if k:
        faces = {body.maps["FACE"].FindIndex(f) for f in rc._iter_list(em.FindFromIndex(k))}
        faces.discard(0)
        row["faces"] = sorted(body.entity_ids["FACE"][j - 1] for j in faces)
    mb = made_by(p, "EDGE", gid)
    if mb:
        row["made_by"] = mb
    return row


_EF_CACHE: dict[int, tuple[Any, Any]] = {}


def _edge_faces_of(body):
    hit = _EF_CACHE.get(id(body.shape))
    if hit is None or hit[0] is not body.shape:
        _EF_CACHE.clear()
        hit = (body.shape, rc.edge_faces(body.shape))
        _EF_CACHE[id(body.shape)] = hit
    return hit[1]


def vertex_row(p: "Processor", gid: int) -> dict[str, Any]:
    m = p.model
    try:
        bid, _ = m.entity_owner("VERTEX", gid)
    except ModelError as exc:
        raise DescribeError(str(exc)) from None
    return {"id": gid, "body": bid, "at": vec(centre("VERTEX", m.entity_shape("VERTEX", gid)))}


def describe_entities(p: "Processor", kind: str, ids: list[int], limit: int = LIMIT) -> dict[str, Any]:
    """One row per face, edge or vertex (or a short row per body)."""
    kind = kind.upper()
    rows = {"FACE": face_row, "EDGE": edge_row, "VERTEX": vertex_row}.get(kind)
    out: dict[str, Any] = {"rev": p.model.revision, "unit": p.model.units.lower(), "kind": kind}
    if kind == "BODY":
        out["bodies"] = [{k: v for k, v in describe_body(p, i).items() if k not in ("rev", "unit")}
                         for i in ids[:limit]]
    elif rows is None:
        raise DescribeError("kind is BODY, FACE, EDGE or VERTEX")
    else:
        out[kind.lower() + "s"] = [rows(p, i) for i in ids[:limit]]
    if len(ids) > limit:
        out["more"] = len(ids) - limit
    return out


# ---- around: what touches an entity -----------------------------------------------------
def _face_labels(p: "Processor", b) -> dict[int, str]:
    """Face ID -> the feature it belongs to ("hole d6 through", "round r2", "pocket floor" ...)."""
    out: dict[int, str] = {}
    try:
        for h in hole_groups(p, b, rc.holes(b.shape, p.model.tolerance)):
            label = f"hole d{h['d']:g} " + ("through" if h["through"] else f"depth {h['depth']:g}")
            for f in h["faces"]:
                out[f] = label
    except Exception:  # noqa: BLE001
        pass
    for g in feature_groups(p, b, limit=1000):
        if g["kind"] in ("fillet", "round"):
            label = f"{g['kind']} r{g['r']:g}"
        elif g["kind"] == "chamfer":
            label = f"chamfer {g['d']:g}"
        elif g["kind"] == "boss":
            label = f"boss d{g['d']:g}"
        else:
            label = f"{g['kind']} depth {g['depth']:g}"
        for f in g["faces"]:
            if isinstance(f, int):
                out.setdefault(f, label + (" (floor)" if g.get("floor") == f else ""))
    return out


def _short_face(p: "Processor", gid: int, labels: dict[int, str]) -> dict[str, Any]:
    r = face_row(p, gid)
    row: dict[str, Any] = {"id": gid, "type": r["type"], "area": r["area"]}
    if "normal" in r:
        row["facing"] = direction_name(r["normal"])
    for k in ("r", "R", "inner", "half_angle"):
        if k in r:
            row[k] = r[k]
    if gid in labels:
        row["part_of"] = labels[gid]
    if "made_by" in r:
        row["made_by"] = r["made_by"]
    return row


def around(p: "Processor", kind: str, gid: int, depth: int = 1, limit: int = 60) -> dict[str, Any]:
    """The faces touching a face, edge or vertex, ring by ring out to ``depth`` (1 to 3),
    each with its type, size, direction and the feature it belongs to."""
    kind = kind.upper()
    m = p.model
    depth = max(1, min(3, int(depth)))
    try:
        bid, idx = m.entity_owner(kind, gid)
    except ModelError as exc:
        raise DescribeError(str(exc)) from None
    body = m.bodies[bid]
    labels = _face_labels(p, body)
    if kind == "FACE":
        start = {gid}
        centre_row = _short_face(p, gid, labels)
    elif kind == "EDGE":
        start = set(edge_row(p, gid).get("faces", []))
        centre_row = {k: v for k, v in edge_row(p, gid).items() if k not in ("body", "made_by")}
    elif kind == "VERTEX":
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp

        amap = robust._EdgeFaceMap()
        TopExp.MapShapesAndAncestors_s(body.shape, TopAbs_VERTEX, TopAbs_FACE, amap)
        v = m.entity_shape("VERTEX", gid)
        k = amap.FindIndex(v)
        start = set()
        if k:
            for f in rc._iter_list(amap.FindFromIndex(k)):
                j = body.maps["FACE"].FindIndex(f)
                if j:
                    start.add(body.entity_ids["FACE"][j - 1])
        centre_row = vertex_row(p, gid)
    else:
        raise DescribeError("kind is FACE, EDGE or VERTEX")
    out: dict[str, Any] = {"rev": m.revision, "unit": m.units.lower(), "body": bid, "of": {"kind": kind, **centre_row}}
    seen = set(start) if kind == "FACE" else set()
    ring = set(start)
    rings = []
    count = 0
    if kind != "FACE":
        rows = [_short_face(p, f, labels) for f in sorted(ring)]
        rings.append({"depth": 1, "faces": rows})
        count += len(rows)
        seen |= ring
        depth -= 1
    for d in range(depth):
        nxt: set[int] = set()
        for f in ring:
            nxt |= set(_neighbours_of(body, body.entity_ids["FACE"].index(f) + 1))
        nxt -= seen
        seen |= nxt
        rows = [_short_face(p, f, labels) for f in sorted(nxt)[: max(0, limit - count)]]
        count += len(rows)
        rings.append({"depth": len(rings) + 1, "faces": rows})
        if len(nxt) > len(rows):
            rings[-1]["more"] = len(nxt) - len(rows)
        ring = nxt
    out["rings"] = rings
    feats = sorted({r["part_of"] for rg in rings for r in rg["faces"] if "part_of" in r})
    if feats:
        out["features_nearby"] = feats
    return out


# ---- outline: a picture in a few hundred numbers ------------------------------------------
def _rdp(pts: list[tuple[float, float]], eps: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker: drop points closer than eps to the line through their neighbours."""
    if len(pts) < 3:
        return pts
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    ln = math.hypot(dx, dy)
    far, at = -1.0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        d = abs(dy * (x - x0) - dx * (y - y0)) / ln if ln > 1e-12 else math.hypot(x - x0, y - y0)
        if d > far:
            far, at = d, i
    if far <= eps:
        return [pts[0], pts[-1]]
    return _rdp(pts[: at + 1], eps)[:-1] + _rdp(pts[at:], eps)


def _chain(polys: list[list[tuple[float, float]]], tol: float) -> list[list[tuple[float, float]]]:
    """Join polylines that meet end to end."""
    polys = [list(pl) for pl in polys]
    out = []
    while polys:
        cur = polys.pop()
        grown = True
        while grown:
            grown = False
            for i, pl in enumerate(polys):
                if math.dist(cur[-1], pl[0]) < tol:
                    cur += pl[1:]
                elif math.dist(cur[-1], pl[-1]) < tol:
                    cur += pl[-2::-1]
                elif math.dist(cur[0], pl[-1]) < tol:
                    cur = pl[:-1] + cur
                elif math.dist(cur[0], pl[0]) < tol:
                    cur = pl[::-1][:-1] + cur
                else:
                    continue
                polys.pop(i)
                grown = True
                break
        out.append(cur)
    return out


def outline(p: "Processor", ref, view: str = "FRONT", hidden: bool = False, most: int = 400) -> dict[str, Any]:
    """The body's visible edges seen from a view, flattened, joined and simplified to at most
    ``most`` points, with whole circles listed apart: what a picture shows, as numbers.
    ``hidden`` adds the hidden edges."""
    from ..geometry import drawing as dw

    m = p.model
    bid = find_body(p, ref)
    b = m.bodies[bid]
    name = view.strip().upper()
    if name not in dw.VIEWS:
        raise DescribeError(f"view is one of {', '.join(dw.VIEWS)}")
    box = bbox(b.shape)
    size = max(box[3] - box[0], box[4] - box[1], box[5] - box[2], 1e-9)
    v = dw.project(b.shape, name, size / 400, mesh=representation(b.shape) != "exact")
    circles = []
    for cx, cy, r, span in v.circles:
        if span >= 2 * math.pi - 1e-6:
            c = [num(cx), num(cy), num(r)]
            if c not in circles:
                circles.append(c)

    def is_circle(pl) -> bool:
        if len(pl) < 4 or math.dist(pl[0], pl[-1]) > 1e-6 * size:
            return False
        for cx, cy, r in circles:
            if all(abs(math.hypot(x - cx, y - cy) - r) < 1e-3 * max(r, 1e-9) + 1e-6 for x, y in pl[:: max(1, len(pl) // 6)]):
                return True
        return False

    def lines(polys):
        polys = [pl for pl in polys if not is_circle(pl)]
        joined = _chain(polys, 1e-6 * size)
        eps = size * 1e-3
        while True:
            simple = [_rdp(pl, eps) for pl in joined]
            n = sum(len(pl) for pl in simple)
            if n <= most or eps > size * 0.05:
                break
            eps *= 2
        return simple, eps, n

    vis, eps, n = lines(v.visible)
    x0, y0, x1, y1 = v.bounds()
    axes = dw.AXES.get(name)
    out: dict[str, Any] = {"rev": m.revision, "unit": m.units.lower(), "body": bid, "view": name,
                           "x_is": axes[0] if axes else "screen right", "y_is": axes[1] if axes else "screen up",
                           "box": [num(x0), num(y0), num(x1), num(y1)], "width": num(x1 - x0), "height": num(y1 - y0)}
    out["lines"] = [[[num(x), num(y)] for x, y in pl] for pl in vis]
    if circles:
        out["circles"] = [{"centre": c[:2], "r": c[2]} for c in circles]
    if hidden:
        hid, _e, nh = lines(v.hidden)
        out["hidden_lines"] = [[[num(x), num(y)] for x, y in pl] for pl in hid]
    out["points"] = n
    out["simplified_within"] = num(eps)
    path = " ".join("M " + " L ".join(f"{num(x):g} {num(-y):g}" for x, y in pl) for pl in vis)
    out["svg_path"] = path  # y flipped, for an SVG with y down
    return out
