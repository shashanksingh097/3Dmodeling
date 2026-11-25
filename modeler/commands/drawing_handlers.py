"""DRAWING: 2D drawings of the bodies (SVG or DXF), the standard views with
hidden lines dashed. The work is in ``geometry/drawing.py``."""

from __future__ import annotations

import os

from .processor import Arg, BodyRef, CommandError, Path, Processor, Text, command


def _exact_extent(bodies) -> dict[str, float] | None:
    """The bodies' size along X, Y and Z from their exact geometry (no tolerance gap)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    try:
        for x in bodies:
            BRepBndLib.AddOptimal_s(x.shape, box, False, False)
    except Exception:
        return None
    if box.IsVoid():
        return None
    lo, hi = box.CornerMin(), box.CornerMax()
    return {"X": hi.X() - lo.X(), "Y": hi.Y() - lo.Y(), "Z": hi.Z() - lo.Z()}


def make_sheet(p: Processor, what: str, ext: str, views, b, sizes, sheet, scale, section, detail,
               extra: dict | None = None, template=None, tables: str = "", sheet_notes: list | None = None,
               placed: list | None = None):
    """The views of one sheet, laid out (and on paper when there is one): (views, bounds, page or None,
    bodies, sizes written, notes placed)."""
    from ..geometry import drawing as dr
    from ..geometry import meshbody
    from ..geometry import sheets as sh
    from .handlers import _compound

    paper = (sheet or p.model.properties.get("SHEET", "") or ("AUTO" if ext == ".pdf" else "NONE")).upper()
    if not sheet and ext == ".dxf":
        paper = "NONE"  # a DXF is always at true size; a template's paper is for the PDF and SVG sheets
    if paper not in ("NONE", "AUTO", *sh.PAPER):
        raise CommandError(f"{what}: the sheet is one of {', '.join(sh.PAPER)}, AUTO or NONE")
    if ext == ".pdf" and paper == "NONE":
        raise CommandError(f"{what}: a PDF is always on paper: give A4 ... A0 or AUTO")
    if ext == ".dxf" and paper != "NONE":
        raise CommandError(f"{what}: a DXF is drawn at true size, with no paper; use .pdf or .svg for a sheet")
    try:
        factor = sh.parse_scale(scale)
        cuts = [sh.parse_cut(c) for c in section.strip().strip('"').split(";") if c.strip()]
        details = [sh.parse_detail(c) for c in detail.strip().strip('"').split(";") if c.strip()]
    except sh.SheetError as exc:
        raise CommandError(f"{what}: {exc}") from None
    try:
        names = dr.parse_views(views)
    except ValueError as exc:
        raise CommandError(f"{what}: {exc}") from None
    m = p.model
    if b:
        bodies = [m.body(b)]
    else:
        hidden = getattr(m, "hidden", set()) or set()
        bodies = [x for x in m.bodies.values() if x.id not in hidden] or list(m.bodies.values())
    if not bodies:
        raise CommandError(f"{what}: there are no bodies")
    meshes = [x for x in bodies if meshbody.is_mesh(x.shape)]
    solids = [x for x in bodies if not meshbody.is_mesh(x.shape)]
    size = 1.0
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    for x in bodies:
        try:
            BRepBndLib.Add_s(x.shape, box)
        except AttributeError:
            BRepBndLib.Add(x.shape, box)
    if not box.IsVoid():
        size = max(box.CornerMin().Distance(box.CornerMax()), 1e-9)
    exact = _exact_extent(bodies)
    deflection = size / 2000
    out = []
    for name in names:
        v = dr.View(name)
        for group, mesh in ((solids, False), (meshes, True)):
            if group:
                shape = group[0].shape if len(group) == 1 else _compound([x.shape for x in group])
                one = dr.project(shape, name, deflection, mesh)
                v.visible += one.visible
                v.hidden += one.hidden
                v.circles += one.circles
        out.append(v)
    letters = iter("ABCDEFGHJKLMNPRSTUVWXYZ")
    try:
        if cuts:
            solid = [x.shape for x in solids]
            if not solid:
                raise sh.SheetError("a section needs solid bodies (not meshes)")
            whole = solid[0] if len(solid) == 1 else _compound(solid)
            for axis, value in cuts:
                letter = next(letters)
                out.append(sh.section_view(whole, axis, value, letter, deflection))
                for v in out:
                    if sh.section_line(v, axis, value, letter):
                        break
        for name, point, r, k in details:
            parent = next((v for v in out if v.name == name), None)
            if parent is None:
                raise sh.SheetError(f"the detail is taken from the {name.lower()} view, which is not on the "
                                    f"drawing: add it to the views")
            out.append(sh.detail_view(parent, point, r, k, next(letters)))
    except sh.SheetError as exc:
        raise CommandError(f"{what}: {exc}") from None
    except StopIteration:
        raise CommandError(f"{what}: too many sections and details") from None
    try:
        nsizes = dr.dimension(out, sizes, exact)
    except ValueError as exc:
        raise CommandError(f"{what}: {exc}") from None
    nnotes = dr.add_notes(out, m.notes, size) if getattr(m, "notes", None) else 0
    if sheet_notes:  # SHEETNOTE: centre marks, threads, finish and weld symbols, leaders (PLAN item 100)
        from ..geometry import sheet_details as sd
        from .sheet_note_handlers import resolve

        holes, wanted = resolve(p, sheet_notes, bodies)
        got, warns = sd.draw(out, holes, wanted, size)
        for w in warns:
            p.warn(f"{what}: {w}")
        if placed is not None:
            placed.extend(got)
    bounds = dr.layout(out)
    page = None
    sheet_tables, marks = [], []
    if tables and paper != "NONE":
        from ..geometry import sheet_tables as stb
        from .sheet_table_handlers import build, parse_tables

        sheet_tables, marks, _data = build(p, parse_tables(tables), bodies, m.units)
    if paper != "NONE":
        if m.units.upper() != "MM" and not factor:
            p.warn(f"{what}: the model is in {m.units.lower()}; the sheet takes 1 {m.units.lower()} as 1 mm "
                   f"before scaling")
        try:
            paper, factor = sh.fit(bounds, paper, factor,
                                   stb.side_width(sheet_tables, sh.TITLE_W) if sheet_tables else 0.0)
        except sh.SheetError as exc:
            raise CommandError(f"{what}: {exc}") from None
        props = dict(m.properties)
        if "MATERIAL" not in {k.upper() for k in props}:
            mats = sorted({x.material.lower() for x in bodies if x.material})
            if mats:
                props["MATERIAL"] = ", ".join(mats)
        if "TITLE" not in {k.upper() for k in props} and len(bodies) == 1 and bodies[0].name:
            props["TITLE"] = bodies[0].name
        if "REVISION" not in {k.upper() for k in props} and getattr(m, "revisions", None):
            props["REVISION"] = m.revisions[-1]["rev"]
        if extra:
            props.update(extra)
        page = sh.compose(out, bounds, paper, factor, props, m.units, template, sheet_tables, marks)
    return out, bounds, page, bodies, nsizes, nnotes


@command(
    "DRAWING",
    Arg("file", Path, help="the file to write: .pdf, .svg or .dxf"),
    Arg("views", str, "STANDARD", "STANDARD (front, top, right and iso), or views joined with +: "
                                  "TOP+FRONT, ISO ..."),
    Arg("b", BodyRef, 0, "body to draw (default: all shown bodies)"),
    Arg("sizes", str, "ALL", "sizes to write: ALL (overall sizes and hole diameters), OVERALL, HOLES or NONE"),
    Arg("sheet", str, "", "the paper: A4, A3, A2, A1, A0, AUTO (the smallest that fits at 1:1, else A3) or NONE "
                          "(true size, no frame); default AUTO for .pdf, NONE for .svg and .dxf"),
    Arg("scale", Text, "", "on paper: 1:2, 2:1 ... (default: the largest usual scale that fits)"),
    Arg("section", Text, "", "section views: an axis and a place, like \"X 30\" (several with ; between)"),
    Arg("detail", Text, "", "detail views: a flat view, a model point, a radius and how much bigger, like "
                            "\"FRONT 20 0 5 8 3\" (several with ;)"),
    logged=False,
    help="Write a 2D drawing of the bodies, at true size: DRAWING, \"part.svg\" [, views] [, body] [, sizes]. "
         "STANDARD views are front, top above it, right beside it and an isometric view; or give "
         "TOP, FRONT, RIGHT, LEFT, BACK, BOTTOM, ISO joined with +. Hidden edges are dashed. Sizes: the "
         "overall width, depth and height, each once, and the diameter of every whole circle seen "
         "face-on, equal ones counted (4x D8); sizes NONE leaves them off. .dxf files open in any CAD "
         "program (layers VISIBLE, HIDDEN, TEXT, DIMS). On paper (.pdf, or sheet A4 ...): a frame and a title "
         "block from PROPERTY values, at a usual scale. Sections are cut and hatched (\"X 30\"); details "
         "show part of a view bigger (\"FRONT 20 0 5 8 3\"). Runs when given; not kept in the history.",
)
def drawing(p: Processor, file, views, b, sizes, sheet, scale, section, detail):
    from ..geometry import drawing as dr
    from ..geometry import sheets as sh

    ext = os.path.splitext(file)[1].lower()
    if ext not in (".svg", ".dxf", ".pdf"):
        raise CommandError("DRAWING: the file must end in .pdf, .svg or .dxf")
    out, bounds, page, bodies, nsizes, nnotes = make_sheet(p, "DRAWING", ext, views, b, sizes, sheet, scale,
                                                           section, detail)
    m = p.model
    if ext == ".pdf":
        data: bytes | str = sh.pdf(page)
    elif ext == ".svg":
        data = sh.svg(page) if page is not None else dr.svg(out, bounds, m.units)
    else:
        data = dr.dxf(out, bounds, m.units)
    path = os.path.abspath(file)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        with open(path, "wb" if isinstance(data, bytes) else "w", **({} if isinstance(data, bytes) else
                                                                      {"encoding": "utf-8"})) as f:
            f.write(data)
    except OSError as exc:
        raise CommandError(f"DRAWING: could not write {file}: {exc.strerror}") from None
    edges = sum(len(v.visible) + len(v.hidden) for v in out)
    return (f"wrote a drawing of {len(bodies)} bod{'y' if len(bodies) == 1 else 'ies'} to {file}: "
            f"{', '.join(v.title.lower() for v in out)} view{'s' if len(out) > 1 else ''}, {edges} edges, "
            f"{nsizes} size{'' if nsizes == 1 else 's'}, "
            + (f"{nnotes} note{'' if nnotes == 1 else 's'} placed, " if nnotes else "")
            + (f"{page.paper} at {sh.scale_text(page.scale)}" if page is not None else
               f"{(bounds[2] - bounds[0]):.4g} x {(bounds[3] - bounds[1]):.4g} {m.units.lower()}"))


@command(
    "PROPERTY",
    Arg("key", str, "", "TITLE, NUMBER, MATERIAL, AUTHOR, COMPANY, REVISION, DATE, or any word (none: list them)"),
    Arg("value", Text, "", "its value (none: remove it)"),
    help="The project's properties, shown in a drawing sheet's title block: PROPERTY, TITLE, Mounting bracket · "
         "PROPERTY, NUMBER, MB-001 · PROPERTY (lists them) · PROPERTY, REVISION (removes it)",
)
def prop(p: Processor, key, value):
    m = p.model
    if not key:
        if not m.properties:
            return "no properties (PROPERTY, TITLE, ... sets one)"
        return "\n".join(f"{k}: {v}" for k, v in sorted(m.properties.items()))
    value = value.strip().strip('"')
    if not value:
        if m.properties.pop(key, None) is None:
            return f"{key} was not set"
        return f"{key} removed"
    m.properties[key] = value
    return f"{key} = {value}"
