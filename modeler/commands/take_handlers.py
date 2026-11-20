"""Geometry from other parts (TAKE) and what uses what (DEPENDS).

TAKE, FACE, bolt, 3, seat copies face 3 of part ``bolt`` into this project as a sheet body named
``seat``; EDGE (or CURVE) gives a curve body, PLANE a datum plane on a flat face, AXIS a datum axis
along a round face or a straight edge. ``part`` is a part name (its own coordinates, built with its
default values) or an instance body (where that copy stands).

LINK (the default) takes the geometry again on every rebuild, so it follows the part. The face is
found again by what it is: the entity with that number when it is still the same kind of surface
or curve, else the one of that kind nearest to where it was. When nothing of that kind is left the
step fails as a *broken link*. COPY takes it once and keeps that geometry with the project: later
changes to the part do not reach it.

A part cannot take from itself, directly or through other parts (the part build refuses loops).
DEPENDS lists the linked part files, the parts, the copies placed (INST) and the TAKE steps, with
broken links and loops.
"""

from __future__ import annotations

import math
import os
import re
import tempfile

from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Line
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopoDS import TopoDS_Shape

from ..core import datum as dt
from ..core.model import ModelError
from ..core.refs import _describe
from ..geometry import features as ft
from ..geometry.healing import _indexed
from ..lang.expr import format_value
from ..lang.script import is_ident
from .processor import REGISTRY, Arg, CommandError, Processor, Raw, Text, command

WHAT = ("FACE", "EDGE", "CURVE", "PLANE", "AXIS", "LIST")
_KIND = {"FACE": "FACE", "PLANE": "FACE", "EDGE": "EDGE", "CURVE": "EDGE", "AXIS": None}


def _fmt(v) -> str:
    return "(" + ", ".join(format_value(round(float(x), 6)) for x in v) + ")"


# ---- where the geometry comes from ---------------------------------------------------------------

def source(p: Processor, raw: str, what: str) -> tuple[TopoDS_Shape, str, str]:
    """(shape, the part's name, how it was found) for a part name or an instance body."""
    from .part_handlers import build

    s = raw.strip()
    pd = p.parts.get(s.upper()) if is_ident(s) else None
    if pd is not None:
        return build(p, pd, {}), pd.name, f"part {pd.name.lower()}"
    try:
        bid = p._body_ref(REGISTRY["TAKE"], s)
    except CommandError:
        bid = None
    if bid is None or bid not in p.model.bodies:
        known = ", ".join(n.lower() for n in p.parts) or "none"
        raise CommandError(f"{what}: {s!r} is neither a part nor a placed copy (parts: {known})")
    inst = p.model.instances.get(bid)
    if inst is None:
        raise CommandError(f"{what}: body {bid} is not a copy of a part (INST); for this project's own "
                           "faces use PICK or the face ID")
    return p.model.bodies[bid].shape, inst[0], f"the copy of {inst[0].lower()} in body {bid}"


def entities(shape, kind: str) -> list:
    return _indexed(shape, TopAbs_FACE if kind == "FACE" else TopAbs_EDGE)


def _fp(kind: str, shape) -> dict:
    d = _describe(kind, shape)
    return {"type": d["type"], "c": [float(x) for x in d["c"]], "size": float(d["size"]),
            "dir": [float(x) for x in d["dir"]] if d["dir"] else None}


def _same_dir(kind: str, a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    dot = sum(x * y for x, y in zip(a, b))
    return (abs(dot) if kind == "EDGE" else dot) >= 1 - 1e-6


def find_again(items: list, kind: str, n: int, fp: dict | None) -> tuple[int, str]:
    """The 1-based number of the entity a link means: of the entities of the same kind (surface or
    curve type) facing the same way (if any does), the one nearest to where it was; ``n`` when that
    is still it. Raises CommandError when nothing of that kind is left."""
    if fp is None:
        if not 1 <= n <= len(items):
            raise CommandError(f"there is no {kind.lower()} {n} (the part has {len(items)})")
        return n, ""
    descs = [_fp(kind, s) for s in items]
    same = [i for i, d in enumerate(descs, 1) if d["type"] == fp["type"]]
    if not same:
        raise CommandError(f"broken link: the part has no {fp['type'].lower()} {kind.lower()} any more "
                           f"(it was {kind.lower()} {n} at {_fmt(fp['c'])})")
    facing = [i for i in same if _same_dir(kind, descs[i - 1]["dir"], fp.get("dir"))]
    pool = facing or same
    dist = {i: math.dist(descs[i - 1]["c"], fp["c"]) for i in pool}
    if n in dist and dist[n] <= min(dist.values()) + 1e-9:
        return n, ""
    best = min(pool, key=lambda i: dist[i])
    return best, f"{kind.lower()} {n} of the part changed; followed the {fp['type'].lower()} to {kind.lower()} {best}"


# ---- BREP text, for copies kept with the project -------------------------------------------------

def to_text(shape) -> str:
    fd, path = tempfile.mkstemp(suffix=".brep")
    os.close(fd)
    try:
        BRepTools.Write_s(shape, path)
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    finally:
        os.remove(path)


def from_text(text: str) -> TopoDS_Shape:
    fd, path = tempfile.mkstemp(suffix=".brep")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        shape = TopoDS_Shape()
        if not BRepTools.Read_s(shape, path, BRep_Builder()):
            raise CommandError("TAKE: the copy saved in the project cannot be read")
        return shape
    finally:
        os.remove(path)


# ---- TAKE -------------------------------------------------------------------------------------------

def _listing(shape, label: str) -> str:
    lines = [f"{label}: faces and edges by number (TAKE, FACE, part, n, name)"]
    for kind in ("FACE", "EDGE"):
        items = entities(shape, kind)
        lines.append(f"  {len(items)} {kind.lower()}s:")
        for i, s in enumerate(items, 1):
            d = _describe(kind, s)
            size = ("area " if kind == "FACE" else "length ") + format_value(round(d["size"], 4))
            extra = f", r {format_value(round(d['r'], 4))}" if d["r"] else ""
            lines.append(f"    {i}: {d['type'].lower()}, {size}{extra}, at {_fmt(d['c'])}")
    return "\n".join(lines)


def _axis_of(shape, kind: str, n: int) -> tuple[dt.P3, dt.P3]:
    if kind == "FACE":
        s = BRepAdaptor_Surface(ft.as_face(shape))
        if s.GetType() != GeomAbs_Cylinder:
            raise CommandError(f"TAKE: face {n} is not round; an axis needs a cylinder face or a straight edge")
        ax = s.Cylinder().Axis()
    else:
        c = BRepAdaptor_Curve(ft.as_edge(shape))
        if c.GetType() != GeomAbs_Line:
            raise CommandError(f"TAKE: edge {n} is not straight; an axis needs a straight edge or a cylinder face")
        ax = c.Line().Position()
    o, d = ax.Location(), ax.Direction()
    return (o.X(), o.Y(), o.Z()), (d.X(), d.Y(), d.Z())


@command(
    "TAKE",
    Arg("what", str, help="FACE, EDGE (or CURVE), PLANE, AXIS, or LIST"),
    Arg("part", Raw, help="a part name, or a placed copy (instance body)"),
    Arg("n", Raw, "", "the face or edge number in the part (TAKE, LIST, part shows them)"),
    Arg("name", Text, "", "the name of the new body or datum"),
    Arg("mode", str, "LINK", "LINK (follows the part, the default) or COPY (kept as it is now)"),
    help="Use geometry from another part: TAKE, FACE, bolt, 3, seat makes a sheet body from face 3 of part bolt; "
         "EDGE or CURVE a curve body; PLANE a datum plane on a flat face; AXIS a datum axis along a round face "
         "(TAKE, AXIS, bolt, FACE 2, ax) or a straight edge (EDGE 5). The part is a part name (its own "
         "coordinates) or a placed copy (where it stands). LINK (default) follows the part on every rebuild, "
         "and fails as a broken link when the face is gone; COPY keeps the geometry as it is now. TAKE, LIST, "
         "part lists the numbers. DEPENDS shows what uses what.",
)
def take(p: Processor, what, part, n, name, mode):
    if what not in WHAT:
        raise CommandError(f"TAKE: what must be one of {', '.join(WHAT)}")
    if what == "LIST":
        shape, _pname, label = source(p, part, "TAKE")
        return _listing(shape, label)
    if mode not in ("LINK", "COPY"):
        raise CommandError("TAKE: the mode is LINK (follows the part) or COPY (kept as it is now)")
    kind, num = _KIND[what], n.strip()
    if what == "AXIS":  # FACE 2 or EDGE 5
        word, _, rest = num.partition(" ")
        if word.upper() not in ("FACE", "EDGE") or not rest.strip():
            raise CommandError("TAKE: give the axis as FACE n (a round face) or EDGE n (a straight edge)")
        kind, num = word.upper(), rest.strip()
    try:
        idx = int(p.evaluate(num))
    except Exception:  # noqa: BLE001 - any bad number is told the same way
        raise CommandError(f"TAKE: {num or '(nothing)'} is not a {kind.lower()} number "
                           "(TAKE, LIST, part shows them)") from None
    if not name:
        raise CommandError("TAKE: give a name for what is taken")
    from .feature_handlers import _check_name

    _check_name(p, name, "TAKE")
    try:
        p.model._check_name_free(name)
    except ModelError as exc:
        raise CommandError(f"TAKE: {exc}") from None
    key = name.upper()
    shape, pname, label = source(p, part, "TAKE")
    ask = (what, pname, part.strip().upper(), kind, idx)
    old = p.taken.get(key)
    if old is not None and tuple(old["ask"]) != ask:
        old = None  # the step was edited: take afresh
    note = ""
    if mode == "COPY" and old is not None and old.get("brep"):
        geom = from_text(old["brep"])
        got, how = idx, "kept copy"
    else:
        items = entities(shape, kind)
        try:
            got, note = find_again(items, kind, idx, old["fp"] if old and mode == "LINK" else None)
        except CommandError as exc:
            raise CommandError(f"TAKE: {label}: {exc}") from None
        geom = BRepBuilderAPI_Copy(items[got - 1]).Shape()
        how = "linked" if mode == "LINK" else "copied"
    rec = {"ask": list(ask), "mode": mode, "part": pname, "source": label, "row": p.entry_index,
           "fp": _fp(kind, geom)}
    if mode == "COPY":
        rec["brep"] = old["brep"] if old is not None and old.get("brep") else to_text(geom)
    p.taken[key] = rec
    if note:
        p.warn(f"{name}: {note}")
    src = f"{kind.lower()} {got} of {label}"
    tail = " (follows the part)" if mode == "LINK" else " (a copy: changes to the part do not reach it)"
    if what in ("FACE", "EDGE", "CURVE"):
        from .handlers import _added

        body = p.model.add_body(geom, name)
        return _added(p, body, f"TAKE {how} {src}") + tail
    from .feature_handlers import _add

    try:
        if what == "PLANE":
            got_plane = ft.face_plane(geom)
            if got_plane is None:
                raise CommandError(f"TAKE: {src} is curved; a plane needs a flat face")
            d = dt.plane(got_plane[0], got_plane[1], name=name)
        else:
            o, v = _axis_of(geom, kind, got)
            d = dt.axis(o, v, name=name)
    except dt.DatumError as exc:
        raise CommandError(f"TAKE: {exc}") from None
    return _add(p, d, f"{how} from {src}") + tail


# ---- DEPENDS ----------------------------------------------------------------------------------------

_USE = re.compile(r"^\s*(INST\s*,\s*([A-Za-z_]\w*)|TAKE\s*,\s*\w+\s*,\s*([A-Za-z_]\w*))", re.IGNORECASE | re.MULTILINE)


def _uses(text: str) -> set[str]:
    """Part names a part's body places or takes from (INST, part / TAKE, what, part)."""
    return {(a or b).upper() for _all, a, b in _USE.findall(text)}


def loops(parts: dict) -> list[list[str]]:
    """Cycles among parts that place or take from each other."""
    graph = {n: _uses(pd.body_text) & set(parts) for n, pd in parts.items()}
    found, seen = [], set()

    def walk(n, path):
        if n in path:
            cyc = path[path.index(n):] + [n]
            sig = frozenset(cyc)
            if sig not in seen:
                seen.add(sig)
                found.append(cyc)
            return
        for m in sorted(graph.get(n, ())):
            walk(m, path + [n])

    for n in sorted(graph):
        walk(n, [])
    return found


def depends(p: Processor) -> dict:
    from .part_handlers import link_rows, resolve_link

    m = p.model
    files = []
    for fname, lk in p.links.items():
        if fname not in link_rows(p):
            continue
        try:
            _path, missing = resolve_link(p, fname)
        except CommandError:
            missing = True
        files.append({"file": fname, "path": lk.path, "parts": [x.lower() for x in lk.parts],
                      "missing": bool(missing or lk.copy), "step": lk.row + 1})
    parts = []
    for name, pd in p.parts.items():
        got = p.part_files.get(name)
        copies = sorted(bid for bid, (pn, _g) in m.instances.items() if pn == name and bid in m.bodies)
        parts.append({"part": name.lower(), "from": got[0] if got else "", "how": got[1] if got else "here",
                      "uses": sorted(x.lower() for x in _uses(pd.body_text) & set(p.parts)),
                      "copies": copies})
    takes, broken = [], []
    for i, e in enumerate(p.history[: p.cursor]):
        head = e.text.strip().split(",")[0].strip().upper()
        if head != "TAKE" or e.suppressed:
            continue
        bits = [b.strip() for b in e.text.split(",")]
        row = {"step": i + 1, "text": e.text.strip(), "ok": e.ok}
        if len(bits) > 4:
            rec = p.taken.get(bits[4].upper())
            if rec:
                row.update({"name": bits[4], "from": rec["source"], "mode": rec["mode"].lower()})
        takes.append(row)
        if not e.ok:
            broken.append({"step": i + 1, "why": e.message})
    for f in files:
        if f["missing"]:
            broken.append({"step": f["step"], "why": f"part file {f['file']} is missing (using the copy saved "
                                                    "in the project)"})
    for bid, (pn, _g) in m.instances.items():
        if bid in m.bodies and pn not in p.parts:
            broken.append({"body": bid, "why": f"body {bid} is a copy of {pn.lower()}, which is no longer defined"})
    return {"files": files, "parts": parts, "takes": takes, "broken": broken,
            "loops": [[x.lower() for x in c] for c in loops(p.parts)]}


def depends_text(d: dict) -> str:
    if not (d["files"] or d["parts"] or d["takes"]):
        return "nothing here uses other parts or files"
    out = []
    if d["files"]:
        out.append("linked part files:")
        for f in d["files"]:
            state = " (MISSING: the copy saved in the project is used)" if f["missing"] else ""
            out.append(f"  {f['file']} -> {', '.join(f['parts']) or 'no parts'}  [step {f['step']}]{state}")
    if d["parts"]:
        out.append("parts:")
        for r in d["parts"]:
            src = {"linked": f"linked to {r['from']}", "copy": f"linked to {r['from']} (missing)",
                   "loaded": f"loaded from {r['from']}", "here": "defined here"}.get(r["how"], r["how"])
            uses = f"; uses {', '.join(r['uses'])}" if r["uses"] else ""
            copies = ", ".join(map(str, r["copies"])) or "none"
            out.append(f"  {r['part']}: {src}{uses}; placed as bodies {copies}" if r["copies"]
                       else f"  {r['part']}: {src}{uses}; not placed")
    if d["takes"]:
        out.append("geometry taken from parts:")
        for t in d["takes"]:
            if "name" in t:
                out.append(f"  {t['name']} <- {t['from']} ({t['mode']})  [step {t['step']}]"
                           + ("" if t["ok"] else "  BROKEN"))
            else:
                out.append(f"  step {t['step']}: {t['text']}" + ("" if t["ok"] else "  BROKEN"))
    if d["loops"]:
        out.append("loops (a part that places or takes from itself):")
        out += ["  " + " -> ".join(c) for c in d["loops"]]
    if d["broken"]:
        out.append(f"{len(d['broken'])} broken link{'s' if len(d['broken']) != 1 else ''}:")
        for b in d["broken"]:
            where = f"step {b['step']}" if "step" in b else f"body {b['body']}"
            out.append(f"  {where}: {b['why']}")
    elif d["files"] or d["takes"]:
        out.append("no broken links")
    return "\n".join(out)


@command(
    "DEPENDS",
    Arg("fmt", str, "TEXT", "TEXT or JSON"),
    logged=False,
    help="What uses what: the linked part files, the parts (where each comes from, which other parts it uses, "
         "where it is placed), the geometry taken from parts (TAKE), loops, and every broken link.",
)
def depends_cmd(p: Processor, fmt):
    d = depends(p)
    p.give_report("depends", d)
    if fmt == "JSON":
        import json

        return json.dumps(d)
    return depends_text(d)


REGISTRY["TAKE"].queries = ("LIST",)
