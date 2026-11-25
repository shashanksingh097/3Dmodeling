"""Copy and paste (PLAN item 107): what Ctrl+C holds and the commands Ctrl+V runs.

Ctrl+C takes the picked bodies (or faces, or sketch geometry) as *clip data*: a small dict with
each body's geometry (BREP text), name, colour and material, plus the IDs it had and which
session it came from. Ctrl+V turns clip data into ordinary history steps:

* bodies pasted into the project they came from (still there) become ``COPY, id, dx, dy, dz``;
* anything else (another project, a body since deleted, picked faces) is kept with this project
  under a name (CLIP1, CLIP2 ...) and pasted with ``PASTE, CLIP1, dx, dy, dz``; the project keeps
  that geometry, so the step rebuilds without the clipboard;
* sketch geometry pasted into the sketch it came from becomes ``STRANSFORM, MOVE, du, dv, ...,
  COPY``; into another sketch, the drawing commands that make the same curves (SLINE, SARC ...).

No Qt here: the window puts clip data on the system clipboard and asks :func:`paste_lines` for the
commands. The assistant can call PASTE, LIST to see the kept geometry.
"""

from __future__ import annotations

import math
import uuid

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_Transform
from OCP.gp import gp_Trsf, gp_Vec
from OCP.TopoDS import TopoDS_Compound

from ..lang.expr import format_value
from ..lang.script import is_ident
from .processor import Arg, CommandError, Processor, Text, command
from .take_handlers import from_text, to_text

MIME = "application/x-3dmodeling-clip"
SESSION = uuid.uuid4().hex  # this app run: bodies copied here can be pasted as COPY steps


def _n(v: float) -> str:
    return format_value(round(float(v), 6))


# ---- what Ctrl+C takes ----------------------------------------------------------------------------

def _box(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    b = Bnd_Box()
    BRepBndLib.Add_s(shape, b)
    if b.IsVoid():
        return None
    lo, hi = b.CornerMin(), b.CornerMax()
    return [lo.X(), lo.Y(), lo.Z()], [hi.X(), hi.Y(), hi.Z()]


def _merge_box(boxes):
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return None
    lo = [min(b[0][i] for b in boxes) for i in range(3)]
    hi = [max(b[1][i] for b in boxes) for i in range(3)]
    return lo, hi


def copy_bodies(p: Processor, ids: list[int]) -> dict:
    """Clip data for bodies."""
    items, boxes = [], []
    for bid in ids:
        b = p.model.body(int(bid))
        mat = p.model.materials.get(b.material.upper()) if b.material else None
        items.append({"id": b.id, "name": b.name, "brep": to_text(b.shape),
                      "color": list(b.color) if b.color else None, "material": mat.name if mat else ""})
        boxes.append(_box(b.shape))
    if not items:
        raise CommandError("copy: pick one or more bodies first")
    box = _merge_box(boxes)
    return {"kind": "bodies", "session": SESSION, "source": p.clip_id, "items": items,
            "box": [box[0], box[1]] if box else None}


def copy_faces(p: Processor, ids: list[int]) -> dict:
    """Clip data for picked faces: one sheet body made of them (per body they belong to)."""
    by_body: dict[int, list] = {}
    for gid in ids:
        bid, _ = p.model.entity_owner("FACE", int(gid))
        by_body.setdefault(bid, []).append(p.model.entity_shape("FACE", int(gid)))
    items, boxes = [], []
    for bid, faces in by_body.items():
        b = p.model.body(bid)
        comp = TopoDS_Compound()
        bb = BRep_Builder()
        bb.MakeCompound(comp)
        for f in faces:
            bb.Add(comp, BRepBuilderAPI_Copy(f).Shape())
        items.append({"id": None, "name": f"{b.name}_faces", "brep": to_text(comp),
                      "color": list(b.color) if b.color else None, "material": ""})
        boxes.append(_box(comp))
    if not items:
        raise CommandError("copy: pick one or more faces first")
    box = _merge_box(boxes)
    return {"kind": "bodies", "session": SESSION, "source": p.clip_id, "items": items,
            "box": [box[0], box[1]] if box else None}


def _sketch_line(sk, g, du: float, dv: float) -> str | None:
    from ..sketch import ellipse as el

    def uv(i):
        u, v = sk.pt(i)
        return f"{_n(u + du)}, {_n(v + dv)}"

    tail = ", CONSTR" if g.construction else ""
    if g.kind == "POINT":
        return f"SPOINT, {uv(g.pts['P'])}{tail}"
    if g.kind == "LINE":
        return f"SLINE, {uv(g.pts['S'])}, {uv(g.pts['E'])}{tail}"
    if g.kind == "CIRCLE":
        return f"SCIRCLE, {uv(g.pts['C'])}, {_n(sk.radius(g))}"
    if g.kind == "ARC":
        a1, a2 = sk.arc_angles(g)
        return f"SARC, {uv(g.pts['C'])}, {_n(sk.radius(g))}, {_n(a1)}, {_n(a2)}"
    if g.kind in ("ELLIPSE", "EARC"):
        c, ax, a, b = el.frame(sk, g)
        ang = math.degrees(math.atan2(ax[1], ax[0]))
        base = f"{_n(c[0] + du)}, {_n(c[1] + dv)}, {_n(a)}, {_n(b)}, {_n(ang)}"
        if g.kind == "EARC":
            t1, t2 = el.arc_params(sk, g)
            return f"SEARC, {base}, {_n(t1)}, {_n(t2)}"
        return f"SELLIPSE, {base}"
    if g.kind == "SPLINE":
        pts = sk.spline_points(g)
        if g.closed and len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-9:
            pts = pts[:-1]
        body = ", ".join(f"{_n(u + du)}, {_n(v + dv)}" for u, v in pts)
        return f"SSPLINE, {body}" + (", CLOSE" if g.closed else "")
    return None


def copy_sketch(p: Processor, names: list[str]) -> dict:
    """Clip data for sketch geometry of the open sketch (numbers as in SSEL)."""
    m = p.model
    sk = m.sketches.get(m.active_sketch) if m.active_sketch else None
    if sk is None:
        raise CommandError("copy: no sketch is open")
    nums = sorted({int(s) for s in names if str(s).isdigit() and int(s) in sk.geos})
    if not nums:
        raise CommandError("copy: pick sketch geometry first")
    lines, us, vs = [], [], []
    for n in nums:
        g = sk.geos[n]
        line = _sketch_line(sk, g, 0.0, 0.0)
        if line:
            lines.append(line)
        for i in g.pts.values():
            u, v = sk.pt(i)
            us.append(u)
            vs.append(v)
    return {"kind": "sketch", "session": SESSION, "source": p.clip_id, "sketch": sk.name,
            "nums": nums, "lines": lines, "box": [[min(us), min(vs)], [max(us), max(vs)]]}


# ---- what Ctrl+V runs --------------------------------------------------------------------------------

def default_offset(data: dict) -> tuple[float, float, float]:
    """Beside the originals: one width and a tenth along X (along u in a sketch)."""
    box = data.get("box")
    if not box:
        return (10.0, 0.0, 0.0)
    w = box[1][0] - box[0][0]
    step = w * 1.1 if w > 1e-9 else 10.0
    return (step, 0.0, 0.0)


def offset_to(data: dict, point) -> tuple[float, float, float]:
    """The move that puts the copied things' bottom centre (sketch: centre) at ``point``."""
    box = data.get("box")
    if not box or point is None:
        return default_offset(data)
    lo, hi = box
    if data.get("kind") == "sketch":
        return ((point[0] - (lo[0] + hi[0]) / 2), (point[1] - (lo[1] + hi[1]) / 2), 0.0)
    return (point[0] - (lo[0] + hi[0]) / 2, point[1] - (lo[1] + hi[1]) / 2, point[2] - lo[2])


def _free_key(p: Processor) -> str:
    i = 1
    while f"CLIP{i}" in p.pasted:
        i += 1
    return f"CLIP{i}"


def keep(p: Processor, item: dict) -> str:
    """Keep one copied body's geometry with this project; its name for PASTE."""
    for k, v in p.pasted.items():  # the same geometry pasted again: one copy kept
        if v.get("brep") == item["brep"]:
            return k
    key = _free_key(p)
    p.pasted[key] = {"brep": item["brep"], "name": item.get("name", ""), "color": item.get("color"),
                     "material": item.get("material", "")}
    return key


def paste_lines(p: Processor, data: dict, offset=None) -> list[str]:
    """The history steps that paste ``data`` (moved by ``offset``; default: beside the originals)."""
    kind = data.get("kind")
    off = tuple(offset) if offset is not None else default_offset(data)
    if kind == "bodies":
        out = []
        here = data.get("session") == SESSION and data.get("source") == p.clip_id
        d = f"{_n(off[0])}, {_n(off[1])}, {_n(off[2])}"
        for item in data.get("items", []):
            bid = item.get("id")
            alive = bid is not None and int(bid) in p.model.bodies
            if here and alive and p.model.body(int(bid)).name == item.get("name"):
                out.append(f"COPY, {bid}, {d}")
            else:
                out.append(f"PASTE, {keep(p, item)}, {d}")
        return out
    if kind == "sketch":
        m = p.model
        sk = m.sketches.get(m.active_sketch) if m.active_sketch else None
        if sk is None:
            raise CommandError("paste: open a sketch to paste sketch geometry into")
        du, dv = off[0], off[1]
        same = (data.get("session") == SESSION and data.get("source") == p.clip_id and sk.name == data.get("sketch")
                and all(n in sk.geos for n in data.get("nums", [])))
        if same:
            names = ", ".join(str(n) for n in data["nums"])
            return [f"STRANSFORM, MOVE, {_n(du)}, {_n(dv)}, {names}, COPY"]
        return [_shift(line, du, dv) for line in data.get("lines", [])]
    raise CommandError("paste: the clipboard holds nothing this app can paste")


def _shift(line: str, du: float, dv: float) -> str:
    """Move a drawing command made at (0, 0) offset by (du, dv): its point coordinates."""
    words = [w.strip() for w in line.split(",")]
    name, vals = words[0], words[1:]
    pairs = {"SPOINT": 1, "SLINE": 2, "SCIRCLE": 1, "SARC": 1, "SELLIPSE": 1, "SEARC": 1}
    if name == "SSPLINE":
        npairs = sum(1 for w in vals if _num(w)) // 2
    else:
        npairs = pairs.get(name, 0)
    for k in range(npairs):
        vals[2 * k] = _n(float(vals[2 * k]) + du)
        vals[2 * k + 1] = _n(float(vals[2 * k + 1]) + dv)
    return ", ".join([name, *vals])


def _num(w: str) -> bool:
    try:
        float(w)
        return True
    except ValueError:
        return False


# ---- PASTE ----------------------------------------------------------------------------------------------

@command(
    "PASTE",
    Arg("key", str, help="the kept geometry's name (CLIP1 ...), or LIST"),
    Arg("dx", float, 0.0), Arg("dy", float, 0.0), Arg("dz", float, 0.0),
    Arg("name", Text, "", "a name for the new body (default: the copied body's name, if free)"),
    help="Paste geometry copied with Ctrl+C from another project (or from faces): PASTE, CLIP1, 50, 0, 0 adds it "
         "as a new body moved by (dx, dy, dz). The project keeps the copied geometry, so the step rebuilds "
         "without the clipboard. Bodies copied in this project paste as COPY steps instead. PASTE, LIST lists what "
         "is kept.",
)
def paste(p: Processor, key, dx, dy, dz, name):
    if key == "LIST":
        if not p.pasted:
            return "PASTE: no copied geometry is kept in this project"
        rows = [f"{k}: {v.get('name') or '(no name)'}" + (f", {v['material'].lower()}" if v.get("material") else "")
                for k, v in sorted(p.pasted.items())]
        return "PASTE, LIST:\n  " + "\n  ".join(rows)
    rec = p.pasted.get(key)
    if rec is None:
        have = ", ".join(sorted(p.pasted)) or "none"
        raise CommandError(f"PASTE: no copied geometry {key} in this project (kept: {have}); copy with Ctrl+C "
                           "and paste with Ctrl+V")
    shape = from_text(rec["brep"])
    if dx or dy or dz:
        t = gp_Trsf()
        t.SetTranslation(gp_Vec(dx, dy, dz))
        shape = BRepBuilderAPI_Transform(shape, t, True).Shape()
    want = name or ""
    if not want:
        base = rec.get("name") or ""
        if base and is_ident(base) and p.model.body_by_name(base) is None:
            want = base
    if want:
        try:
            p.model._check_name_free(want)
        except Exception as exc:  # noqa: BLE001 - told as a command error
            raise CommandError(f"PASTE: {exc}") from None
    from .handlers import _added

    body = p.model.add_body(shape, want)
    look = {}
    if rec.get("color"):
        look["color"] = tuple(rec["color"])
    mat = (rec.get("material") or "").upper()
    if mat and mat in p.model.materials:
        look["material"] = p.model.materials[mat].name
    if look:
        p.model.set_style(body.id, **look)
    return _added(p, body, f"PASTE {key}")


def used_keys(p: Processor) -> set[str]:
    """CLIP names the history's PASTE steps use (only those are saved with the project)."""
    out = set()
    for e in p.history:
        text = getattr(e, "text", "") or ""
        words = [w.strip().upper() for w in text.split(",")]
        if len(words) > 1 and words[0] == "PASTE" and words[1] != "LIST":
            out.add(words[1])
    return out
