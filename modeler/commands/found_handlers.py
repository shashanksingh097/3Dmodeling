"""FEATURES, DEFEATURE, RESIZE: editing parts that have no history (PLAN item 70).

An imported STEP part is one body of faces. These commands find the holes,
rounds, chamfers and rows of holes on it (geometry/found.py), list them as
data, and change or remove all the ones of a kind and size in one step:

    FEATURES, part                      ! what is there, numbered
    DEFEATURE, part, FILLET, LT, 2      ! every round smaller than 2 goes
    RESIZE, part, HOLE, EQ, 6, 8        ! every 6 mm hole becomes 8 mm
    SEL, S, FACE, LIKE, 31              ! faces like face 31 (all holes of its size ...)
"""

from __future__ import annotations

from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet

from ..geometry import direct as de
from ..geometry import found as fd
from ..geometry import robust
from ..lang.expr import fmt_num
from .processor import Arg, BodyRef, CommandError, Processor, Raw, command

OPS = ("ALL", "EQ", "NE", "LT", "LE", "GT", "GE")
_PLURAL = {"HOLES": "HOLE", "FILLETS": "FILLET", "ROUNDS": "FILLET", "ROUND": "FILLET",
           "CHAMFERS": "CHAMFER", "PATTERNS": "PATTERN"}


def _kind(what: str, text: str, allowed: tuple[str, ...] = fd.KINDS + ("ALL",)) -> str:
    k = (text or "ALL").strip().upper()
    k = _PLURAL.get(k, k)
    if k not in allowed:
        raise CommandError(f"{what}: kind {text!r} is not one of {', '.join(allowed)}")
    return k


def _solid(p: Processor, what: str, b: int):
    body = p.model.body(b)
    if not robust.solids(body.shape):
        raise CommandError(f"{what}: body {b} is not a solid")
    return body


def _gids(body, faces: list[int]) -> list[int]:
    ids = body.entity_ids["FACE"]
    return [ids[i - 1] for i in faces if 0 < i <= len(ids)]


def features_of(p: Processor, b: int, kinds=fd.KINDS) -> list[fd.Feature]:
    return fd.find(p.model.body(b).shape, tuple(kinds))


def rows(p: Processor, b: int, kinds=fd.KINDS) -> list[dict]:
    """The features of body b as data, with the model's face IDs."""
    body = p.model.body(b)
    out = []
    for n, f in enumerate(features_of(p, b, kinds), 1):
        r = f.row(n)
        r["faces"] = _gids(body, f.faces)
        out.append(r)
    return out


def _describe(r: dict) -> str:
    k, s = r["kind"], fmt_num(round(r["size"], 4))
    if k == "HOLE":
        how = "through" if r.get("through") else f"{fmt_num(round(r['depth'], 4))} deep"
        cb = f", counterbore {fmt_num(round(r['counterbore'][0], 4))}" if r.get("counterbore") else ""
        return f"hole d {s} {how}{cb}"
    if k == "FILLET":
        return f"{'inside' if r.get('concave') else 'outside'} round r {s}"
    if k == "CHAMFER":
        return f"chamfer {s}" + (" x 45" if "leg" in r else f" wide (angles {r['angles']})")
    if r.get("pattern") == "LINEAR":
        return f"row of {r['count']} holes d {s}, step {fmt_num(round(r['step'], 4))} (holes {r['holes']})"
    return f"ring of {r['count']} holes d {s} on r {fmt_num(round(r['radius'], 4))}, " \
           f"{fmt_num(round(r['angle'], 4))} degrees apart (holes {r['holes']})"


@command(
    "FEATURES",
    Arg("b", BodyRef, help="a solid, an imported one too"),
    Arg("kind", str, "ALL", "ALL, HOLE, FILLET, CHAMFER or PATTERN"),
    logged=False,
    help="List the holes, rounds, chamfers and rows of holes found on a body, even one with no history (an "
         "imported STEP part): FEATURES, part · FEATURES, part, HOLE. Each row gives the size and the face IDs; "
         "then DEFEATURE or RESIZE changes them in bulk, and SEL, S, FACE, LIKE, id picks the ones like a face.",
)
def features(p: Processor, b, kind):
    k = _kind("FEATURES", kind)
    _solid(p, "FEATURES", b)
    found = rows(p, b, fd.KINDS if k == "ALL" else (k,) if k != "PATTERN" else ("HOLE", "PATTERN"))
    if k == "PATTERN":
        found = [r for r in found if r["kind"] == "PATTERN"]
    p.give_report("FEATURES", {"body": b, "features": found})
    if not found:
        return f"body {b}: no {'features' if k == 'ALL' else k.lower() + 's'} found"
    lines = [f"body {b}: {len(found)} feature{'s' if len(found) != 1 else ''}"]
    for r in found:
        lines.append(f"  {r['n']}. {_describe(r)} - faces {' '.join(map(str, r['faces']))}")
    return "\n".join(lines)


def _pick(p: Processor, what: str, b: int, kind: str, op: str, value: float, kinds=None) -> list[fd.Feature]:
    if op not in OPS:
        raise CommandError(f"{what}: {op!r} is not one of {', '.join(OPS)}")
    feats = [f for f in features_of(p, b, kinds or (kind,)) if f.kind == kind]
    hit = [f for f in feats if fd.compare(op, value, f.size)]
    if not hit:
        sizes = sorted({round(f.size, 4) for f in feats})
        have = f" (sizes found: {', '.join(fmt_num(s) for s in sizes)})" if sizes else " (none found)"
        raise CommandError(f"{what}: body {b} has no {kind.lower()} {op} {fmt_num(value)}{have}")
    return hit


@command(
    "DEFEATURE",
    Arg("b", BodyRef, help="a solid"),
    Arg("kind", str, help="HOLE, FILLET or CHAMFER"),
    Arg("op", str, "ALL", "ALL, EQ, NE, LT, LE, GT or GE"),
    Arg("value", float, 0.0, "the size to compare with: diameter, radius or chamfer size"),
    help="Remove features in bulk and close the gaps: DEFEATURE, part, FILLET, LT, 2 (every round under 2) · "
         "DEFEATURE, part, HOLE, EQ, 3 · DEFEATURE, part, CHAMFER. Good for simplifying imported parts; "
         "FEATURES lists what is there.",
)
def defeature(p: Processor, b, kind, op, value):
    from .handlers import _added

    k = _kind("DEFEATURE", kind, ("HOLE", "FILLET", "CHAMFER"))
    body = _solid(p, "DEFEATURE", b)
    hit = _pick(p, "DEFEATURE", b, k, op, value)
    faces = sorted({f for x in hit for f in x.faces})
    new = _remove(p, "DEFEATURE", body, faces)
    return _added(p, new, f"DEFEATURE removed {len(hit)} {k.lower()}{'s' if len(hit) != 1 else ''} "
                          f"({len(faces)} faces) of body {b}")


def _remove(p: Processor, what: str, body, faces: list[int]):
    m = p.model
    shapes = [body.maps["FACE"].FindKey(i) for i in faces]
    try:
        shape, maker = de.delete_faces(body.shape, shapes)
    except de.DirectError as exc:
        raise CommandError(f"{what}: body {body.id}: {exc}") from None
    if robust.is_empty(shape) or not robust.is_valid(shape):
        raise CommandError(f"{what}: removing these faces leaves an invalid body {body.id}")
    return m.replace([body.id], robust.unwrap(shape), maker, same_id=True)


@command(
    "RESIZE",
    Arg("b", BodyRef, help="a solid"),
    Arg("kind", str, help="HOLE, FILLET or CHAMFER"),
    Arg("op", str, help="EQ, NE, LT, LE, GT, GE or ALL: which ones"),
    Arg("value", Raw, "", "the size to compare with (left empty for ALL)"),
    Arg("new", float, 0.0, "the new diameter, radius or chamfer size"),
    help="Change the size of features in bulk, on any solid (imported ones too): RESIZE, part, HOLE, EQ, 6, 8 "
         "(every 6 hole becomes 8) · RESIZE, part, FILLET, LT, 2, 1 · RESIZE, part, CHAMFER, ALL, , 1.5. "
         "Holes keep their position, depth and counterbore; rounds and chamfers are made again on the edge "
         "they leave.",
)
def resize(p: Processor, b, kind, op, value, new):
    from .handlers import _added

    k = _kind("RESIZE", kind, ("HOLE", "FILLET", "CHAMFER"))
    v = 0.0 if (op == "ALL" and not str(value).strip()) else float(p.evaluate(str(value) or "0"))
    if new <= 0:
        raise CommandError("RESIZE: the new size must be more than 0")
    body = _solid(p, "RESIZE", b)
    hit = _pick(p, "RESIZE", b, k, op, v)
    if k == "HOLE":
        new_body = _resize_holes(p, body, hit, new)
    else:
        new_body = _resize_blends(p, body, hit, new, k)
    sizes = sorted({round(x.size, 4) for x in hit})
    return _added(p, new_body, f"RESIZE {len(hit)} {k.lower()}{'s' if len(hit) != 1 else ''} of body {b} "
                               f"from {', '.join(fmt_num(s) for s in sizes)} to {fmt_num(new)}")


def _resize_holes(p: Processor, body, hit: list[fd.Feature], new: float):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType

    faces, dists = [], []
    for h in hit:
        for i in h.faces:
            f = body.maps["FACE"].FindKey(i)
            s = BRepAdaptor_Surface(fd.rc.as_face(f))
            if s.GetType() != GeomAbs_SurfaceType.GeomAbs_Cylinder:
                continue  # the bottom and the counterbore step follow
            if abs(2 * s.Cylinder().Radius() - h.size) > 1e-6 * max(1.0, h.size):
                continue  # the counterbore keeps its size
            faces.append(f)
            dists.append((h.size - new) / 2)  # positive adds material: the hole gets smaller
    if new >= min((h.info.get("counterbore") or [float("inf")])[0] for h in hit):
        raise CommandError("RESIZE: the new hole would be as wide as its counterbore")
    try:
        shape, maker = de.push_pull(body.shape, faces, dists)
    except de.DirectError as exc:
        raise CommandError(f"RESIZE: body {body.id}: {exc}") from None
    if robust.is_empty(shape) or not robust.is_valid(shape) or robust.volume(shape) <= 0:
        raise CommandError(f"RESIZE: a {fmt_num(new)} hole does not fit (it would break through a wall)")
    return p.model.replace([body.id], robust.unwrap(shape), maker, same_id=True)


def _resize_blends(p: Processor, body, hit: list[fd.Feature], new: float, kind: str):
    """Take the rounds (or chamfers) off, then round (or chamfer) the sharp edges they leave."""
    at = [x.at for x in hit]
    reach = max(x.size for x in hit) * 2 + 1e-6
    faces = sorted({f for x in hit for f in x.faces})
    plain = _remove(p, "RESIZE", body, faces)
    edges = fd._sharp_edges_near(plain.shape, at, reach)
    if len(edges) < len(hit):
        raise CommandError(f"RESIZE: could not find the sharp edges the old {kind.lower()}s left")
    mk = BRepFilletAPI_MakeFillet(plain.shape) if kind == "FILLET" else BRepFilletAPI_MakeChamfer(plain.shape)
    for e in edges:
        mk.Add(new, e)
    try:
        mk.Build()
        ok = mk.IsDone()
    except Exception:  # noqa: BLE001 - OCCT throws on blends it cannot make
        ok = False
    if not ok:
        raise CommandError(f"RESIZE: the kernel could not make a {fmt_num(new)} {kind.lower()} here; "
                           "try a smaller size")
    shape = mk.Shape()
    if robust.is_empty(shape) or not robust.is_valid(shape):
        raise CommandError(f"RESIZE: a {fmt_num(new)} {kind.lower()} gives an invalid body")
    return p.model.replace([plain.id], robust.unwrap(shape), mk, same_id=True)


# ---- SEL, ..., LIKE and SEL, ..., FEATURE -----------------------------------------


def like(p: Processor, kind: str, gid: int, scope: str = "BODY") -> list[int]:
    """Entities like this one: the faces of every feature of the same kind and size when
    it belongs to a found feature, else the same type and size of face or edge."""
    m = p.model
    bid, idx = m.entity_owner(kind, gid)
    bodies = [bid] if scope != "ALL" else sorted(m.bodies)
    if kind == "FACE":
        try:
            feats = features_of(p, bid, ("HOLE", "FILLET", "CHAMFER"))
        except Exception:  # noqa: BLE001 - a mesh or a sheet: plain matching below
            feats = []
        mine = next((f for f in feats if idx in f.faces), None)
        if mine is not None:
            out: list[int] = []
            for ob in bodies:
                body = m.bodies[ob]
                if not robust.solids(body.shape):
                    continue
                for f in features_of(p, ob, ("HOLE", "FILLET", "CHAMFER")):
                    if f.kind == mine.kind and abs(f.size - mine.size) <= 1e-6 * max(1.0, mine.size):
                        out += _gids(body, f.faces)
            return sorted(set(out))
    key = _shape_key(kind, m.entity_shape(kind, gid))
    out = []
    for ob in bodies:
        for g in m.bodies[ob].entity_ids[kind]:
            if _same_key(_shape_key(kind, m.entity_shape(kind, g)), key):
                out.append(g)
    return sorted(out)


def _shape_key(kind: str, s):
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_CurveType as C
    from OCP.GeomAbs import GeomAbs_SurfaceType as S
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    g = GProp_GProps()
    if kind == "FACE":
        a = BRepAdaptor_Surface(fd.rc.as_face(s))
        t = a.GetType()
        if t == S.GeomAbs_Cylinder:
            return ("cyl", a.Cylinder().Radius())
        if t == S.GeomAbs_Sphere:
            return ("sph", a.Sphere().Radius())
        if t == S.GeomAbs_Torus:
            return ("tor", a.Torus().MajorRadius(), a.Torus().MinorRadius())
        if t == S.GeomAbs_Cone:
            return ("cone", abs(a.Cone().SemiAngle()))
        BRepGProp.SurfaceProperties_s(s, g)
        return (fd.rc.SURFACE_NAMES.get(t, "other"), g.Mass())
    if kind == "EDGE":
        a = BRepAdaptor_Curve(fd.rc.as_edge(s))
        if a.GetType() == C.GeomAbs_Circle:
            return ("circle", a.Circle().Radius())
        BRepGProp.LinearProperties_s(s, g)
        return (fd.rc.CURVE_NAMES.get(a.GetType(), "other"), g.Mass())
    if kind == "BODY":
        BRepGProp.VolumeProperties_s(s, g)
        return ("body", g.Mass())
    return ("vertex",)


def _same_key(a, b) -> bool:
    if a[0] != b[0] or len(a) != len(b):
        return False
    return all(abs(x - y) <= 1e-6 * max(1.0, abs(y)) for x, y in zip(a[1:], b[1:]))


def feature_faces(p: Processor, kind: str, op: str, value: float) -> list[int]:
    """Face IDs of every found feature of a kind (and size) on every solid body."""
    out: list[int] = []
    for bid, body in p.model.bodies.items():
        if not robust.solids(body.shape):
            continue
        for f in features_of(p, bid, (kind,) if kind != "PATTERN" else ("HOLE", "PATTERN")):
            if f.kind == kind and fd.compare(op, value, f.size):
                out += _gids(body, f.faces)
    return sorted(set(out))
