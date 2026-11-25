"""Drawings that follow the model: sheets kept in the history (DRAWSHEET), written together as one
PDF with a page per sheet or one SVG per sheet (DRAWINGS), written again after every rebuild and
save when asked (AUTO), title block templates, and the sizes on the model checked against it.

``DRAWSHEET, name, views [, body, sizes, paper, scale, section, detail, template]`` is a history
step that says what a sheet shows, not a picture of it: the views are made from the model each
time the drawings are written, so they always show the model as it is.

The size check looks at the sizes pinned to the model with ``NOTE, SIZE`` (between two points)
and ``NOTE, HOLE``/``FIT`` (a diameter): a size whose ends no longer lie on the model, or a
diameter that is no longer the hole's, is out of date and is named.
"""

from __future__ import annotations

import os
import re

import numpy as np

from ..lang.script import is_ident
from .processor import Arg, BodyRef, CommandError, Path, Processor, Text, command

DIA = ("\u00d8", "\u00f8")  # the diameter sign: capital or small o-slash


def _sheets_text(p: Processor) -> list[str]:
    out = []
    for i, (name, s) in enumerate(p.model.drawsheets.items(), 1):
        bits = [s["views"].lower()]
        if s.get("b"):
            bits.append(f"body {s['b']}")
        bits.append(s.get("paper") or "AUTO")
        if s.get("scale"):
            bits.append(s["scale"])
        if s.get("section"):
            bits.append(f"section {s['section']}")
        if s.get("detail"):
            bits.append(f"detail {s['detail']}")
        if s.get("template"):
            bits.append(f"template {os.path.basename(s['template'])}")
        if s.get("tables"):
            bits.append(f"tables {s['tables'].lower()}")
        if s.get("notes"):
            n = len(s["notes"])
            bits.append(f"{n} drawing detail{'s' if n != 1 else ''} (SHEETNOTE, {s['name']} lists them)")
        out.append(f"  sheet {i} {s['name']}: " + ", ".join(bits))
    return out


@command(
    "DRAWSHEET",
    Arg("name", Text, help="the sheet's name (DELETE, name removes one)"),
    Arg("views", str, "STANDARD", "STANDARD, or views joined with +: TOP+FRONT, ISO ..."),
    Arg("b", BodyRef, 0, "body to draw (default: all shown bodies)"),
    Arg("sizes", str, "ALL", "ALL, OVERALL, HOLES or NONE"),
    Arg("paper", str, "", "A4 ... A0 or AUTO (default: the template's paper, else AUTO)"),
    Arg("scale", Text, "", "1:2, 2:1 ... (default: the largest usual scale that fits)"),
    Arg("section", Text, "", "section views, like \"X 30\""),
    Arg("detail", Text, "", "detail views, like \"FRONT 20 0 5 8 3\""),
    Arg("template", Path, "", "a title block template file (see LANGUAGE.md)"),
    Arg("tables", Text, "", "tables on the sheet: BALLOONS, PARTS, HOLES, REVISIONS joined with +, or ALL"),
    help="A drawing sheet kept with the model: DRAWSHEET, front, TOP+FRONT, 0, ALL, A3. The views are made from "
         "the model each time DRAWINGS writes the sheets, so they follow every change. Several sheets make one "
         "PDF with a page each. Tables (last argument, or SHEETTABLE): PARTS (a parts list with balloons), "
         "HOLES (a hole table with tags), REVISIONS, or ALL. DRAWSHEET, DELETE, name removes one.",
)
def drawsheet(p: Processor, name, views, b, sizes, paper, scale, section, detail, template, tables=""):
    from .sheet_table_handlers import parse_tables

    from ..geometry import drawing as dr
    from ..geometry import sheets as sh

    m = p.model
    if name.upper() == "DELETE":
        key = views.upper()
        if key not in m.drawsheets:
            raise CommandError(f"DRAWSHEET: there is no sheet {views.lower()}")
        m.drawsheets = {k: v for k, v in m.drawsheets.items() if k != key}
        return f"removed sheet {views.lower()}"
    if not is_ident(name):
        raise CommandError(f"DRAWSHEET: {name!r} is not a valid sheet name (letters, digits, _)")
    paper = paper.upper()
    if paper and paper not in ("AUTO", *sh.PAPER):
        raise CommandError(f"DRAWSHEET: the paper is one of {', '.join(sh.PAPER)} or AUTO")
    if sizes not in ("ALL", "OVERALL", "HOLES", "NONE"):
        raise CommandError("DRAWSHEET: sizes are ALL, OVERALL, HOLES or NONE")
    try:
        dr.parse_views(views)
        sh.parse_scale(scale)
        [sh.parse_cut(c) for c in section.strip().strip('"').split(";") if c.strip()]
        [sh.parse_detail(c) for c in detail.strip().strip('"').split(";") if c.strip()]
        if template:
            sh.read_template(template)
        words = parse_tables(tables)
    except CommandError as exc:
        raise CommandError(f"DRAWSHEET: {exc}") from None
    except (ValueError, sh.SheetError) as exc:
        raise CommandError(f"DRAWSHEET: {exc}") from None
    if b:
        m.body(b)
    key = name.upper()
    new = key not in m.drawsheets
    m.drawsheets = {**m.drawsheets, key: {"name": name, "views": views, "b": b, "sizes": sizes, "paper": paper,
                                          "scale": scale, "section": section, "detail": detail,
                                          "template": os.path.abspath(template) if template else "",
                                          "tables": "+".join(words),
                                          "notes": list(m.drawsheets.get(key, {}).get("notes", []))}}
    n = list(m.drawsheets).index(key) + 1
    return f"sheet {n} {name} " + ("added" if new else "changed") + "\n" + "\n".join(_sheets_text(p)[n - 1:n])


# ---- writing them --------------------------------------------------------------------------------

def write_all(p: Processor, path: str) -> list[str]:
    """Write every sheet: one PDF with a page each, or one SVG per sheet. Returns the lines to show."""
    from ..geometry import sheets as sh
    from .drawing_handlers import make_sheet

    m = p.model
    if not m.drawsheets:
        raise CommandError("DRAWINGS: there are no sheets (DRAWSHEET, name, views ... adds one)")
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".pdf", ".svg"):
        raise CommandError("DRAWINGS: the file must end in .pdf (a page per sheet) or .svg (a file per sheet)")
    pages, lines = [], []
    details: dict[str, list] = {}
    p.sheet_details = details  # what SHEETNOTE details were drawn where, for DRAWINGS's answer
    total = len(m.drawsheets)
    for i, s in enumerate(m.drawsheets.values(), 1):
        tpl = sh.read_template(s["template"]) if s.get("template") else None
        paper = s.get("paper") or (tpl.paper if tpl is not None and tpl.paper else "AUTO")
        b = s.get("b") or 0
        if b and b not in m.bodies:
            raise CommandError(f"DRAWINGS: sheet {s['name']} draws body {b}, which no longer exists")
        placed: list = []
        out, _bounds, page, _bodies, nsizes, _nn = make_sheet(
            p, f"DRAWINGS, sheet {s['name']}", ".pdf", s["views"], b, s["sizes"], paper, s["scale"], s["section"],
            s["detail"], extra={"SHEET": f"{i} of {total}", "SHEETNAME": s["name"]}, template=tpl,
            tables=s.get("tables", ""), sheet_notes=s.get("notes"), placed=placed)
        pages.append(page)
        for w in page.warnings:
            p.warn(f"DRAWINGS, sheet {s['name']}: {w}")
        details[s["name"]] = placed
        lines.append(f"  sheet {i} {s['name']}: {', '.join(v.title.lower() for v in out)}, {nsizes} "
                     f"size{'s' if nsizes != 1 else ''}"
                     + (f", {len(placed)} detail{'s' if len(placed) != 1 else ''}" if placed else "")
                     + f", {page.paper} at {sh.scale_text(page.scale)}")
    full = os.path.abspath(path)
    os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
    try:
        if ext == ".pdf":
            with open(full, "wb") as fh:
                fh.write(sh.pdf_pages(pages))
            files = [path]
        else:
            stem = os.path.splitext(full)[0]
            files = []
            for s, page in zip(m.drawsheets.values(), pages):
                f = f"{stem}_{s['name'].lower()}.svg"
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(sh.svg(page))
                files.append(f)
    except OSError as exc:
        raise CommandError(f"DRAWINGS: could not write {path}: {exc.strerror}") from None
    head = (f"wrote {total} sheet{'s' if total != 1 else ''} to "
            + (path if len(files) == 1 else ", ".join(os.path.basename(f) for f in files)))
    return [head, *lines]


def refresh(p: Processor) -> None:
    """Write the drawings again (AUTO): after a rebuild and a save. A failure is a warning."""
    path = getattr(p, "drawings_auto", "")
    if not path or not p.model.drawsheets:
        return
    try:
        write_all(p, path)
    except CommandError as exc:
        p.warn(f"the drawings were not written again: {exc}")


# ---- sizes on the model, checked --------------------------------------------------------------------

def _shown_solids(p: Processor):
    from ..geometry import meshbody

    m = p.model
    return [b for bid, b in sorted(m.bodies.items()) if m.is_shown(bid) and not meshbody.is_mesh(b.shape)]


def _dist(shape, pt) -> float:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt

    v = BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, pt))).Vertex()
    d = BRepExtrema_DistShapeShape(v, shape)
    return d.Value() if d.IsDone() else float("inf")


def _tolerance(p: Processor, bodies) -> float:
    from ..geometry import robust

    size = max([robust.diagonal(b.shape) for b in bodies] or [1.0])
    return max(1e-6 * size, getattr(p.model, "tolerance", 0.0) or 0.0, 1e-7)


def touches(p: Processor, pt) -> str:
    """What a point lies on: a VERTEX, else an EDGE, else a FACE of a shown body, or ""."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer

    bodies = _shown_solids(p)
    if not bodies:
        return ""
    tol = _tolerance(p, bodies)
    near = [b for b in bodies if _dist(b.shape, pt) <= tol]
    for kind, name in ((TopAbs_VERTEX, "VERTEX"), (TopAbs_EDGE, "EDGE"), (TopAbs_FACE, "FACE")):
        for b in near:
            ex = TopExp_Explorer(b.shape, kind)
            while ex.More():
                if _dist(ex.Current(), pt) <= tol:
                    return name
                ex.Next()
    return ""


def _round_faces_near(shape, pt, tol):
    """(distance, radius) of the nearest round face, among faces within ``tol`` of the point."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    from ..core.refs import _describe

    v = BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, pt))).Vertex()
    best = (float("inf"), None)
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        d = BRepExtrema_DistShapeShape(v, ex.Current())
        if d.IsDone() and d.Value() <= tol:
            r = _describe("FACE", ex.Current())["r"]
            if r is not None and d.Value() < best[0]:
                best = (d.Value(), r)
        ex.Next()
    return best


def check_sizes(p: Processor) -> list[dict]:
    """Every size note, and whether it still fits the model."""
    from ..geometry import robust

    m = p.model
    bodies = _shown_solids(p)
    if not bodies:
        return []
    size = max(robust.diagonal(b.shape) for b in bodies)
    tol = _tolerance(p, bodies)
    out = []
    for k, n in enumerate(m.notes, 1):
        row = None
        if n.span is not None:
            a, b = n.span
            was = tuple(n.ends or ("", ""))
            if not any(was):
                continue  # the size was not on the model when made (a centre, say): nothing to check
            now = (touches(p, a) if was[0] else "", touches(p, b) if was[1] else "")
            ends = [min(_dist(x.shape, q) for x in bodies) for q in (a, b)]
            row = {"note": k, "text": n.text, "kind": "size", "ok": now == was, "was": list(was), "now": list(now),
                   "ends_off": [round(e, 6) for e in ends],
                   "length": round(float(np.linalg.norm(np.subtract(b, a))), 6)}
        elif n.text.startswith(DIA):
            num = re.match(r"[\u00d8\u00f8]\s*([0-9.]+)", n.text)
            where = n.anchor or n.at
            if not num:
                continue
            _d, r = min((_round_faces_near(x.shape, where, max(tol, 0.05 * size)) for x in bodies),
                        key=lambda t: t[0])
            row = {"note": k, "text": n.text, "kind": "hole", "ok": False}
            if r is not None:
                now = 2 * r
                row["now"] = round(now, 6)
                row["ok"] = abs(now - float(num.group(1))) <= max(tol, 0.5 * 10 ** -_decimals(num.group(1)))
        if row is not None:
            out.append(row)
    return out


def _decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def sizes_text(rows: list[dict]) -> list[str]:
    bad = [r for r in rows if not r["ok"]]
    if not rows:
        return []
    if not bad:
        return [f"{len(rows)} size{'s' if len(rows) != 1 else ''} on the model checked: all fit the model"]
    out = [f"{len(bad)} of {len(rows)} sizes on the model are out of date:"]
    for r in bad:
        if r["kind"] == "size":
            moved = [f"{w.lower()} is now " + (f"on {n.lower()}" if n else f"{off:.6g} off the model")
                     for w, n, off in zip(r["was"], r["now"], r["ends_off"]) if w and w != n]
            out.append(f"  note {r['note']} ({r['text']}): its ends no longer meet the model as they did "
                       f"(an end on a {'; '.join(moved)})")
        elif "now" in r:
            out.append(f"  note {r['note']} ({r['text']}): the hole is now {r['text'][0]}{r['now']:g}")
        else:
            out.append(f"  note {r['note']} ({r['text']}): no round face there any more")
    out.append("  (delete them with NOTE, DELETE, n and add them again)")
    return out


@command(
    "DRAWINGS",
    Arg("file", Path, "", "a .pdf (a page per sheet) or .svg (a file per sheet); none: list the sheets"),
    Arg("mode", str, "", "AUTO: write them again after every rebuild and save; OFF: stop that"),
    logged=False,
    help="Write the drawing sheets (DRAWSHEET): DRAWINGS, \"part.pdf\" writes one PDF with a page per sheet, "
         "made from the model as it is now; DRAWINGS, \"part.pdf\", AUTO also writes it again after every "
         "rebuild and save. DRAWINGS alone lists the sheets and checks the sizes pinned to the model (NOTE, "
         "SIZE / HOLE) against it.",
)
def drawings(p: Processor, file, mode):
    if mode not in ("", "AUTO", "OFF"):
        raise CommandError("DRAWINGS: the mode is AUTO or OFF")
    if mode == "OFF":
        p.drawings_auto = ""
        return "the drawings are no longer written again by themselves"
    checked = check_sizes(p)
    p.give_report("drawings", {"sheets": list(p.model.drawsheets.values()), "sizes": checked,
                               "auto": getattr(p, "drawings_auto", "")})
    if not file:
        if not p.model.drawsheets:
            lines = ["no sheets (DRAWSHEET, name, views ... adds one)"]
        else:
            lines = [f"{len(p.model.drawsheets)} sheet{'s' if len(p.model.drawsheets) != 1 else ''}:",
                     *_sheets_text(p)]
            if getattr(p, "drawings_auto", ""):
                lines.append(f"written again after every rebuild and save to {p.drawings_auto}")
        return "\n".join(lines + sizes_text(checked))
    lines = write_all(p, file)
    if "drawings" in p.reports:
        p.reports["drawings"]["details"] = dict(getattr(p, "sheet_details", {}))
    if mode == "AUTO":
        p.drawings_auto = os.path.abspath(file)
        lines.append("they will be written again after every rebuild and save")
    bad = [r for r in checked if not r["ok"]]
    if bad:
        p.warn(f"{len(bad)} size{'s' if len(bad) != 1 else ''} on the model {'are' if len(bad) != 1 else 'is'} "
               "out of date (DRAWINGS lists them)")
    return "\n".join(lines + sizes_text(checked))
