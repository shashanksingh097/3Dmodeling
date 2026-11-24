"""Tables on drawing sheets (PLAN item 72): balloons with a parts list, a hole table and a revision
table, made again from the model every time the sheets are written.

* ``DRAWSHEET, ..., tables`` or ``SHEETTABLE, sheet, PARTS+HOLES`` says which a sheet carries:
  BALLOONS, PARTS, HOLES, REVISIONS (ALL for every one, NONE for none). Balloons come with the
  parts list.
* ``REVISION, B, "Hole moved"`` adds a row to the revision table (the newest one is the title
  block's REV unless PROPERTY, REVISION says otherwise).
* ``SHEETDATA, sheet`` gives the rows of the sheet's tables as data, for the assistant and for
  checks, without writing anything.
"""

from __future__ import annotations

import datetime
import re

import numpy as np

from .processor import Arg, CommandError, Processor, Text, command

WORDS = ("BALLOONS", "PARTS", "HOLES", "REVISIONS")
THREAD_RE = re.compile(r"\b(M\d+(?:[.,]\d+)?(?:\s*[x×]\s*\d+(?:[.,]\d+)?)?|\d+/\d+-\d+\s*UN[CFE]?|"
                       r"#\d+-\d+\s*UN[CFE]?|G\s?\d/\d+|\d/\d+\s*NPT)", re.I)


def parse_tables(text: str) -> list[str]:
    """The table words in the order they are kept: "parts+holes" -> ["BALLOONS", "PARTS", "HOLES"]."""
    raw = [w.strip().upper() for w in re.split(r"[+\s;]+", (text or "").strip().strip('"')) if w.strip()]
    if not raw or raw == ["NONE"]:
        return []
    if "ALL" in raw:
        return list(WORDS)
    alias = {"BOM": "PARTS", "PARTSLIST": "PARTS", "LIST": "PARTS", "HOLE": "HOLES", "REV": "REVISIONS",
             "REVISION": "REVISIONS", "BALLOON": "BALLOONS", "PART": "PARTS"}
    out = set()
    for w in raw:
        w = alias.get(w, w)
        if w not in WORDS:
            raise CommandError(f"the tables are {', '.join(WORDS)}, ALL or NONE, joined with + (not {w.lower()})")
        out.add(w)
    if "PARTS" in out:
        out.add("BALLOONS")
    return [w for w in WORDS if w in out]


def tables_text(words: list[str]) -> str:
    return "+".join(w.lower() for w in words) if words else "none"


# ---- what goes on the sheet --------------------------------------------------------------------------

def _num(v: float) -> str:
    from ..lang.expr import fmt_num

    return fmt_num(round(float(v), 3))


def _vertex_near(shape, target: np.ndarray) -> tuple:
    """A point on the part to end a balloon's leader on: the vertex nearest its centre."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    best, bd = None, None
    ex = TopExp_Explorer(shape, TopAbs_VERTEX)
    while ex.More():
        q = BRep_Tool.Pnt_s((getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex)(ex.Current()))
        v = np.array([q.X(), q.Y(), q.Z()])
        d = float(np.linalg.norm(v - target))
        if bd is None or d < bd:
            best, bd = v, d
        ex.Next()
    return tuple(best if best is not None else target)


def _centre(shape) -> np.ndarray:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    a, b = box.CornerMin(), box.CornerMax()
    return np.array([(a.X() + b.X()) / 2, (a.Y() + b.Y()) / 2, (a.Z() + b.Z()) / 2])


def parts_rows(p: Processor, bodies) -> list[dict]:
    """The parts-list rows of the bodies on the sheet, numbered as BOM numbers them."""
    from .config_handlers import bom_rows

    ids = {b.id for b in bodies}
    return [r for r in bom_rows(p) if ids & set(r["bodies"])]


def hole_rows(p: Processor, bodies) -> list[dict]:
    """A row per hole in the sheet's solids: tag, position (the hole's mouth), diameter, depth, thread."""
    from ..geometry import found, meshbody, robust

    out = []
    for body in bodies:
        if meshbody.is_mesh(body.shape) or not robust.solids(body.shape):
            continue
        try:
            feats = found.find(body.shape, ("HOLE",))
        except Exception:  # noqa: BLE001 - a body the finder cannot read has no rows
            continue
        for f in feats:
            mouth = np.array(f.info.get("mouth", f.at), float)
            axis = np.array(f.info.get("axis", (0, 0, 1)), float)
            if f.info.get("top"):
                mouth = np.array(f.info["top"], float)  # a counterbored hole starts at its counterbore
            elif f.info.get("through"):
                # either end is the mouth: give the one on the +X/+Y/+Z side (the top for a vertical hole)
                up = axis if axis[np.argmax(np.abs(axis))] > 0 else -axis
                other = mouth - axis * float(f.info.get("depth", 0.0))
                if (other - mouth) @ up > 0:
                    mouth = other
            out.append({"body": body.id, "x": float(mouth[0]), "y": float(mouth[1]), "z": float(mouth[2]),
                        "d": float(f.size), "through": bool(f.info.get("through")),
                        "depth": float(f.info.get("depth", 0.0)), "axis": [float(c) for c in axis],
                        "counterbore": f.info.get("counterbore"), "thread": _thread(p, mouth, axis, f.size)})
    out.sort(key=lambda r: (-r["d"], not r["through"], r["counterbore"] is not None, round(r["x"], 6),
                            round(r["y"], 6), round(r["z"], 6)))
    letters = {}
    for r in out:
        cb = r["counterbore"]
        key = (round(r["d"], 6), r["through"], 0.0 if r["through"] else round(r["depth"], 6),
               tuple(round(c, 6) for c in cb) if cb else None, r["thread"])  # one letter per kind of hole
        if key not in letters:
            letters[key] = chr(ord("A") + len(letters)) if len(letters) < 26 else f"Z{len(letters) - 25}"
        letter = letters[key]
        n = sum(1 for q in out if q.get("tag", "").startswith(letter) and q.get("tag", "")[len(letter):].isdigit())
        r["tag"] = f"{letter}{n + 1}"
    return out


def _thread(p: Processor, mouth, axis, d) -> str:
    """The thread written in a note pinned on this hole (NOTE on its face, or a size note on its axis)."""
    for n in p.model.notes:
        for q in (n.anchor, n.at):
            if q is None:
                continue
            rel = np.asarray(q, float) - mouth
            off = rel - (rel @ axis) * axis
            if np.linalg.norm(off) <= d / 2 * 1.05 + 1e-6:
                hit = THREAD_RE.search(n.text)
                if hit:
                    return hit.group(1).replace(" ", "")
    return ""


def revision_rows(p: Processor) -> list[dict]:
    return [dict(r) for r in p.model.revisions]


def build(p: Processor, words: list[str], bodies, units: str):
    """(tables, marks, data) for a sheet that carries these tables."""
    from ..geometry import sheet_tables as st

    tables, marks, data = [], [], {}
    u = units.lower()
    if "HOLES" in words:
        rows = hole_rows(p, bodies)
        data["holes"] = [{k: v for k, v in r.items() if k != "axis"} for r in rows]
        if rows:
            body_rows = []
            for r in rows:
                depth = "THRU" if r["through"] else _num(r["depth"])
                size = f"Ø{_num(r['d'])}"
                if r["counterbore"]:
                    size += f" CBORE Ø{_num(r['counterbore'][0])} DP {_num(r['counterbore'][1])}"
                body_rows.append([r["tag"], _num(r["x"]), _num(r["y"]), _num(r["z"]), size, depth,
                                  r["thread"] or "-"])
                marks.append({"kind": "tag", "label": r["tag"], "point": (r["x"], r["y"], r["z"]),
                              "axis": r["axis"], "r": r["d"] / 2})
            tables.append(st.Table(f"HOLES ({u})", ["TAG", "X", "Y", "Z", "SIZE", "DEPTH", "THREAD"],
                                   body_rows, "top", {1, 2, 3}))
    if "REVISIONS" in words:
        rows = revision_rows(p)
        data["revisions"] = rows
        tables.insert(0, st.Table("REVISIONS", ["REV", "DESCRIPTION", "DATE", "BY"],
                                  [[r["rev"], r["text"], r.get("date", ""), r.get("by", "")] for r in rows]
                                  or [["-", "(none yet: REVISION, A, \"First issue\")", "", ""]], "top"))
    if "PARTS" in words:
        rows = parts_rows(p, bodies)
        data["parts"] = [{"item": r["item"], "name": r["name"], "qty": r["qty"], "material": r["material"],
                          "mass": r["mass"], "values": r["values"], "bodies": list(r["bodies"])} for r in rows]
        has_mass = any(r["mass"] for r in rows)
        head = ["ITEM", "QTY", "PART", "MATERIAL"] + (["MASS (g)"] if has_mass else [])
        body_rows = []
        for r in reversed(rows):  # a parts list reads up from the title block
            name = r["name"] + (f" ({r['values']})" if r["values"] else "")
            row = [str(r["item"]), str(r["qty"]), name, (r["material"] or "-").lower()]
            if has_mass:
                row.append(_num(r["mass"] * 1000) if r["mass"] else "-")
            body_rows.append(row)
        tables.append(st.Table("PARTS LIST", head, body_rows, "bottom", {0, 1, 4}))
    if "BALLOONS" in words:
        rows = parts_rows(p, bodies)
        by_id = {b.id: b for b in bodies}
        for r in rows:
            bid = next(b for b in r["bodies"] if b in by_id)
            shape = by_id[bid].shape
            marks.append({"kind": "balloon", "label": str(r["item"]), "point": _vertex_near(shape, _centre(shape))})
        data["balloons"] = [{"item": r["item"], "body": next(b for b in r["bodies"] if b in by_id)} for r in rows]
    return tables, marks, data


# ---- commands ----------------------------------------------------------------------------------------

@command(
    "SHEETTABLE",
    Arg("sheet", str, help="the sheet's name (DRAWSHEET)"),
    Arg("tables", Text, "ALL", "BALLOONS, PARTS, HOLES, REVISIONS joined with +; ALL or NONE"),
    help="The tables a drawing sheet carries, made again from the model each time the sheets are written: "
         "SHEETTABLE, front, PARTS+HOLES. PARTS is the parts list (with balloons on the drawing), HOLES a hole "
         "table with a tag beside each hole, REVISIONS the revision table (REVISION adds rows). NONE takes "
         "them off.",
)
def sheettable(p: Processor, sheet, tables):
    m = p.model
    key = sheet.upper()
    if key not in m.drawsheets:
        have = ", ".join(s["name"] for s in m.drawsheets.values()) or "none yet (DRAWSHEET adds one)"
        raise CommandError(f"SHEETTABLE: there is no sheet {sheet.lower()} (sheets: {have})")
    try:
        words = parse_tables(tables)
    except CommandError as exc:
        raise CommandError(f"SHEETTABLE: {exc}") from None
    m.drawsheets = {**m.drawsheets, key: {**m.drawsheets[key], "tables": "+".join(words)}}
    return f"sheet {m.drawsheets[key]['name']}: tables {tables_text(words)}"


@command(
    "REVISION",
    Arg("rev", str, "", "the revision: A, B, 2 ... (none: list them); DELETE, rev removes one"),
    Arg("text", Text, "", "what changed"),
    Arg("date", Text, "", "the date (default: today)"),
    Arg("by", Text, "", "who made it (default: PROPERTY AUTHOR)"),
    help="A row of the drawing sheets' revision table: REVISION, B, \"Hole moved 5 mm\" [, date] [, by]. The "
         "newest revision is the title block's REV unless PROPERTY, REVISION is set. REVISION lists them; "
         "REVISION, DELETE, B removes one.",
)
def revision(p: Processor, rev, text, date, by):
    m = p.model
    rev = rev.strip()
    if not rev:
        if not m.revisions:
            return "no revisions (REVISION, A, \"First issue\" adds one)"
        return "\n".join(f"{r['rev']}  {r.get('date', '')}  {r['text']}" + (f"  ({r['by']})" if r.get("by") else "")
                         for r in m.revisions)
    if rev.upper() == "DELETE":
        which = text.strip().strip('"').upper()
        left = [r for r in m.revisions if r["rev"].upper() != which]
        if len(left) == len(m.revisions):
            raise CommandError(f"REVISION: there is no revision {which}")
        m.revisions = left
        return f"removed revision {which}"
    text = text.strip().strip('"')
    if not text:
        raise CommandError("REVISION: say what changed: REVISION, B, \"Hole moved 5 mm\"")
    props = {k.upper(): v for k, v in m.properties.items()}
    row = {"rev": rev.upper(), "text": text,
           "date": date.strip().strip('"') or props.get("DATE") or datetime.date.today().isoformat(),
           "by": by.strip().strip('"') or props.get("AUTHOR", "")}
    old = [r for r in m.revisions if r["rev"].upper() != row["rev"]]
    changed = len(old) != len(m.revisions)
    m.revisions = old + [row]
    return f"revision {row['rev']}: {text}" + (" (changed)" if changed else "")


@command(
    "SHEETDATA",
    Arg("sheet", str, "", "the sheet's name (default: the first sheet)"),
    logged=False,
    help="The rows of a drawing sheet's tables as data, without writing anything: SHEETDATA, front gives its "
         "parts list, hole table (tag, position, size, depth, thread), revisions and balloons.",
)
def sheetdata(p: Processor, sheet):
    m = p.model
    if not m.drawsheets:
        raise CommandError("SHEETDATA: there are no sheets (DRAWSHEET adds one)")
    key = sheet.upper() if sheet else next(iter(m.drawsheets))
    if key not in m.drawsheets:
        raise CommandError(f"SHEETDATA: there is no sheet {sheet.lower()}")
    s = m.drawsheets[key]
    words = parse_tables(s.get("tables", ""))
    b = s.get("b") or 0
    if b:
        bodies = [m.body(b)]
    else:
        hidden = getattr(m, "hidden", set()) or set()
        bodies = [x for x in m.bodies.values() if x.id not in hidden] or list(m.bodies.values())
    _t, _m, data = build(p, words, bodies, m.units)
    p.give_report("SHEETDATA", {"sheet": s["name"], "tables": [w.lower() for w in words], **data})
    lines = [f"sheet {s['name']}: tables {tables_text(words)}"]
    for r in data.get("parts", []):
        lines.append(f"  item {r['item']}: {r['qty']} x {r['name']}" + (f" ({r['material'].lower()})"
                                                                         if r["material"] else ""))
    for r in data.get("holes", []):
        lines.append(f"  hole {r['tag']}: Ø{_num(r['d'])} at ({_num(r['x'])}, {_num(r['y'])}, {_num(r['z'])}), "
                     + ("through" if r["through"] else f"{_num(r['depth'])} deep")
                     + (f", {r['thread']}" if r["thread"] else ""))
    for r in data.get("revisions", []):
        lines.append(f"  revision {r['rev']}: {r['text']}")
    if len(lines) == 1:
        lines.append("  no tables (SHEETTABLE, name, ALL adds them)")
    return "\n".join(lines)
