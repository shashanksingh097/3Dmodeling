"""SHEETNOTE: drawing details kept on a drawing sheet (PLAN item 100): centre marks and centre lines
on holes, cosmetic threads, surface finish and weld symbols, and leader notes. They are drawn
(geometry/sheet_details.py) each time DRAWINGS writes the sheets, so they follow the model."""

from __future__ import annotations

import re

import numpy as np

from ..core.model import UNITS
from ..lang.expr import fmt_num
from .processor import Arg, CommandError, Processor, Raw, Text, command

KINDS = ("CENTRES", "THREADS", "FINISH", "WELD", "LEADER", "DELETE", "LIST")
_ALIASES = {"CENTERS": "CENTRES", "CENTRE": "CENTRES", "CENTER": "CENTRES", "THREAD": "THREADS",
            "NOTE": "LEADER", "SURFACE": "FINISH"}
_TARGET = re.compile(r"^\s*(?:(FACE|EDGE|VERTEX|F|E|V)\s*)?(\d+)\s*$", re.I)


def _kind(word: str) -> str:
    k = word.strip().upper()
    k = _ALIASES.get(k, k)
    if k not in KINDS:
        raise CommandError(f"SHEETNOTE: the kind is one of {', '.join(KINDS)}")
    return k


def _target(text: str) -> tuple[str, int]:
    """FACE 12, EDGE 5, VERTEX 3 (or F12, E5, V3); a bare number is a face."""
    hit = _TARGET.match(text or "")
    if not hit:
        raise CommandError("SHEETNOTE: say what it points at: a face ID (12), or FACE 12, EDGE 5, VERTEX 3")
    k = (hit.group(1) or "FACE").upper()
    k = {"F": "FACE", "E": "EDGE", "V": "VERTEX"}.get(k, k)
    return k, int(hit.group(2))


def _describe(d: dict) -> str:
    k = d["kind"]
    if k in ("CENTRES", "THREADS"):
        return "centre marks and centre lines on the holes" if k == "CENTRES" else "cosmetic threads on tapped holes"
    if k == "FINISH":
        return (f"surface finish on face {d['id']}" + (f": Ra {fmt_num(d['ra'])}" if d.get("ra") else "")
                + (f" ({d['text']})" if d.get("text") else ""))
    if k == "WELD":
        return f"weld symbol on {d['body_name']}"
    return f"leader on {d['on'].lower()} {d['id']}: {d['text']}"


def _sheet(p: Processor, name: str) -> tuple[str, dict]:
    m = p.model
    key = name.strip().upper()
    if key not in m.drawsheets:
        have = ", ".join(s["name"] for s in m.drawsheets.values()) or "none yet (DRAWSHEET adds one)"
        raise CommandError(f"SHEETNOTE: there is no sheet {name.strip().lower()} (sheets: {have})")
    return key, m.drawsheets[key]


@command(
    "SHEETNOTE",
    Arg("sheet", str, help="the sheet's name (DRAWSHEET)"),
    Arg("kind", str, "LIST", "CENTRES, THREADS, FINISH, WELD, LEADER; DELETE or LIST"),
    Arg("on", Raw, "", "FINISH and LEADER: the face (12) or FACE 12, EDGE 5, VERTEX 3; WELD: the weld bead; "
                       "DELETE: the detail's number, or ALL"),
    Arg("value", Raw, "", "FINISH: the roughness Ra; LEADER: the note's text"),
    Arg("text", Text, "", "FINISH: how it is made (ground, lapped ...)"),
    help="Drawing details on a sheet, drawn again from the model each time DRAWINGS writes the sheets: "
         "SHEETNOTE, front, CENTRES (centre marks and centre lines on the holes) · SHEETNOTE, front, THREADS "
         "(cosmetic threads on holes with a thread noted on them) · SHEETNOTE, front, FINISH, 12, 1.6, ground "
         "(a surface finish symbol on face 12) · SHEETNOTE, front, WELD, weld_1 (the weld symbol of a WELD bead, "
         "with its size and length) · SHEETNOTE, front, LEADER, EDGE 5, \"Break sharp edges\" · SHEETNOTE, "
         "front lists them; SHEETNOTE, front, DELETE, 2 (or ALL) removes them.",
)
def sheetnote(p: Processor, sheet, kind, on, value, text):
    m = p.model
    key, s = _sheet(p, sheet)
    k = _kind(kind)
    have = list(s.get("notes", []))
    if k == "LIST":
        p.give_report("SHEETNOTE", {"sheet": s["name"], "notes": [dict(d, n=i + 1) for i, d in enumerate(have)]})
        if not have:
            return f"sheet {s['name']}: no drawing details (SHEETNOTE, {s['name']}, CENTRES adds centre marks)"
        return "\n".join([f"sheet {s['name']}: {len(have)} detail{'s' if len(have) != 1 else ''}"]
                         + [f"  {i + 1}. {_describe(d)}" for i, d in enumerate(have)])
    if k == "DELETE":
        w = str(on).strip().upper()
        if w == "ALL":
            new = []
        else:
            try:
                n = int(float(p.evaluate(w))) if w else 0
            except Exception:  # noqa: BLE001
                n = 0
            if not 1 <= n <= len(have):
                raise CommandError(f"SHEETNOTE: give the number of the detail to remove (1 to {len(have)}) or ALL"
                                   if have else f"SHEETNOTE: sheet {s['name']} has no details")
            new = have[:n - 1] + have[n:]
        m.drawsheets = {**m.drawsheets, key: {**s, "notes": new}}
        return f"sheet {s['name']}: {len(have) - len(new)} detail{'s' if len(have) - len(new) != 1 else ''} removed"
    if k in ("CENTRES", "THREADS"):
        if str(on).strip() or str(value).strip():
            raise CommandError(f"SHEETNOTE: {k} takes nothing more: SHEETNOTE, {s['name']}, {k}")
        if any(d["kind"] == k for d in have):
            return f"sheet {s['name']} already has {_describe({'kind': k})}"
        d = {"kind": k}
    elif k == "FINISH":
        on_kind, gid = _target(str(on))
        if on_kind != "FACE":
            raise CommandError("SHEETNOTE: a surface finish goes on a face")
        _check(m, "FACE", gid)
        ra = 0.0
        if str(value).strip():
            try:
                ra = float(p.evaluate(str(value)))
            except Exception:  # noqa: BLE001
                raise CommandError(f"SHEETNOTE: the roughness Ra must be a number, not {value!r}") from None
            if ra <= 0:
                raise CommandError("SHEETNOTE: the roughness Ra must be more than 0")
        if not ra and not text:
            raise CommandError("SHEETNOTE: give the roughness Ra (FINISH, 12, 1.6) or how it is made")
        d = {"kind": k, "on": "FACE", "id": gid, "ra": ra, "text": text}
    elif k == "WELD":
        try:
            bid = p._body_ref(_cmd(), str(on).strip())
        except CommandError:
            raise CommandError("SHEETNOTE: WELD takes a weld bead (WELD made it): SHEETNOTE, front, WELD, "
                               "weld_1") from None
        if bid not in m.welds:
            raise CommandError(f"SHEETNOTE: body {bid} is not a weld bead (WELD, a, b makes one)")
        d = {"kind": k, "body": bid, "body_name": m.bodies[bid].name}
    else:  # LEADER
        on_kind, gid = _target(str(on))
        _check(m, on_kind, gid)
        words = str(value).strip()
        if len(words) >= 2 and words[0] == words[-1] == '"':
            words = words[1:-1]
        if not words:
            raise CommandError("SHEETNOTE: give the note's text: SHEETNOTE, front, LEADER, 12, \"Break edges\"")
        d = {"kind": k, "on": on_kind, "id": gid, "text": words}
    new = have + [d]
    m.drawsheets = {**m.drawsheets, key: {**s, "notes": new}}
    p.give_report("SHEETNOTE", {"sheet": s["name"], "added": dict(d, n=len(new)),
                                "notes": [dict(x, n=i + 1) for i, x in enumerate(new)]})
    return f"sheet {s['name']}: {len(new)}. {_describe(d)} (drawn when DRAWINGS writes the sheets)"


def _cmd():
    from .processor import REGISTRY

    return REGISTRY["SHEETNOTE"]


def _check(m, kind: str, gid: int) -> None:
    try:
        m.entity_shape(kind, gid)
    except Exception:  # noqa: BLE001
        raise CommandError(f"SHEETNOTE: there is no {kind.lower()} {gid}") from None


# ---- for DRAWINGS ------------------------------------------------------------------------------


def _major(thread: str, units: str) -> float:
    """A thread's outer diameter in the model's units: M6 is 6 mm, 1/4-20 a quarter inch."""
    from ..geometry import fasteners as fs

    t = thread.strip().upper().replace(" ", "")
    hit = re.match(r"M(\d+(?:[.,]\d+)?)", t)
    if hit:
        return float(hit.group(1).replace(",", ".")) * UNITS["MM"] / UNITS[units.upper()]
    for size, row in fs.INCH.items():
        if t.startswith(size.upper()):
            return row[0] * UNITS["IN"] / UNITS[units.upper()]
    return 0.0


def resolve(p: Processor, notes: list[dict], bodies) -> tuple[list[dict], list[dict]]:
    """(holes, details) for geometry/sheet_details.draw: the records with points taken from the model
    as it is now. A detail whose face or bead is gone carries ``missing`` (a warning)."""
    from ..geometry import analysis_prep as ap
    from .queries import centre

    m = p.model
    holes = []
    if any(d["kind"] in ("CENTRES", "THREADS") for d in notes):
        from .sheet_table_handlers import hole_rows

        holes = hole_rows(p, bodies)
        for r in holes:
            r["major"] = _major(r["thread"], m.units) if r.get("thread") else 0.0
    out = []
    for d in notes:
        w = dict(d)
        if d["kind"] in ("FINISH", "LEADER"):
            try:
                shape = m.entity_shape(d["on"], d["id"])
            except Exception:  # noqa: BLE001 - the face went away
                w["missing"] = f"the {d['kind'].lower()} on {d['on'].lower()} {d['id']} is left off: it is gone"
                out.append(w)
                continue
            w["normal"] = None
            if d["on"] == "FACE":
                got = ap.inside_point(ap._face(shape))
                if got is not None:
                    q, n = got
                    w["point"], w["normal"] = (q.X(), q.Y(), q.Z()), (n.X(), n.Y(), n.Z())
            if "point" not in w:
                w["point"] = tuple(centre(d["on"], shape))
        elif d["kind"] == "WELD":
            if d["body"] not in m.bodies or d["body"] not in m.welds:
                w["missing"] = f"the weld symbol for {d['body_name']} is left off: the bead is gone"
                out.append(w)
                continue
            ln, size = m.welds[d["body"]][0], m.welds[d["body"]][1]
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
            from OCP.BRepExtrema import BRepExtrema_DistShapeShape
            from OCP.gp import gp_Pnt

            c = np.asarray(centre("BODY", m.bodies[d["body"]].shape), float)
            dist = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, c))).Vertex(),
                                              m.bodies[d["body"]].shape)
            q = dist.PointOnShape2(1) if dist.IsDone() and dist.NbSolution() else None
            w["point"] = (q.X(), q.Y(), q.Z()) if q is not None else tuple(c)
            w["size"], w["length"] = round(float(size), 6), round(float(ln), 3)
        out.append(w)
    return holes, out
