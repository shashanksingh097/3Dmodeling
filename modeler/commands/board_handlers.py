"""BOARD: a circuit board from an IDF or KiCad file, ready to design an enclosure around (PLAN 103).

The board outline becomes a plate (with its cut-outs and mounting holes), and each part a named
body standing on its side of the board (R1, U3, J1 ...) on the layer ``<name>_parts``. The report
hands over what an enclosure needs: the board's size and thickness, the tallest part above and
below, the mounting holes, and every part with its place, size and side. One history step.
"""

from __future__ import annotations

import os

from ..core.model import UNITS, Layer
from ..lang.expr import fmt_num
from ..lang.script import is_ident
from .processor import Arg, CommandError, Path, Processor, Text, command

HOLES = ("MOUNT", "ALL", "NONE")
PLACES = ("ORIGIN", "CENTRE", "FILE")
MAX_PARTS = 3000
BOARD_GREEN = (0.13, 0.42, 0.22)
PART_GREY = (0.22, 0.23, 0.26)


def _name(p: Processor, want: str, taken: set[str]) -> str:
    base = "".join(c if c.isalnum() or c == "_" else "_" for c in want) or "part"
    if base[0].isdigit():
        base = "p" + base
    name, k = base, 2
    while name.upper() in taken or p.model.body_by_name(name) is not None or name.upper() in p.model.datums \
            or name.upper() in p.model.sketches:
        name, k = f"{base}_{k}", k + 1
    taken.add(name.upper())
    return name


def library_for(p: Processor, file: str, lib: str) -> str:
    """The IDF library file (.emp): the one given, else the one next to the board file."""
    if lib.strip():
        path = p.file_map.get(lib, lib)
        if not os.path.isfile(path):
            raise CommandError(f"BOARD: no such library file: {lib}")
        return path
    stem = os.path.splitext(file)[0]
    for ext in (".emp", ".EMP"):
        cand = stem + ext
        path = p.file_map.get(cand, cand)
        if os.path.isfile(path):
            return path
    real = p.file_map.get(file, file)
    for ext in (".emp", ".EMP"):
        cand = os.path.splitext(real)[0] + ext
        if os.path.isfile(cand):
            return cand
    return ""


def _box(shape) -> list[list[float]]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    bb = Bnd_Box()
    BRepBndLib.Add_s(shape, bb)
    lo, hi = bb.CornerMin(), bb.CornerMax()
    x0, y0, z0, x1, y1, z1 = lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()
    return [[round(x0, 4), round(y0, 4), round(z0, 4)], [round(x1, 4), round(y1, 4), round(z1, 4)]]


@command(
    "BOARD",
    Arg("file", Path, help="the board: IDF (.emn, with its .emp library next to it) or KiCad (.kicad_pcb)"),
    Arg("name", Text, "board", "the board body's name (its parts go on the layer NAME_parts)"),
    Arg("holes", str, "MOUNT", "which drilled holes to cut: MOUNT (mounting and big unplated ones), ALL or NONE"),
    Arg("height", float, 0.0, "the height of parts the file gives none for (0: a guess from R, C, U, J ...)"),
    Arg("lib", Path, "", "the IDF library file, when it is not next to the board file"),
    Arg("at", str, "ORIGIN", "where it goes: ORIGIN (the board's lower left corner at 0,0), CENTRE (its middle "
                             "at 0,0) or FILE (where the file has it)"),
    help=("A circuit board to design an enclosure around: BOARD, controller.kicad_pcb · BOARD, main.emn, pcb · "
          "BOARD, main.emn, pcb, ALL, 3. The outline becomes a plate from z 0 up to its thickness (cut-outs and "
          "mounting holes cut), each part a named body (R1, U3 ...) on its side, on layer NAME_parts. The "
          "report gives the size, the tallest part above and below, the mounting holes and every part. Saved "
          "projects keep a copy of the files."),
)
def board(p: Processor, file, name, holes, height, lib, at):
    from ..geometry import board as bd
    from ..geometry import robust
    from .handlers import _added

    path = p.file_map.get(file, file)
    if not os.path.isfile(path):
        raise CommandError(f"BOARD: no such file: {file}")
    hk = (holes or "MOUNT").strip().upper()
    if hk not in HOLES:
        raise CommandError(f"BOARD: holes is one of {', '.join(HOLES)}")
    if height < 0:
        raise CommandError("BOARD: the part height cannot be negative")
    nm = (name or "board").strip()
    if not is_ident(nm):
        raise CommandError(f"BOARD: {nm!r} is not a valid name (letters, digits, _)")
    if p.model.body_by_name(nm) is not None:
        raise CommandError(f"BOARD: the name {nm} is already used by body {p.model.body_by_name(nm).id}")
    libpath = "" if path.lower().endswith(".kicad_pcb") else library_for(p, file, lib)
    try:
        b = bd.read(path, libpath, nm)
    except bd.BoardError as exc:
        raise CommandError(f"BOARD: {os.path.basename(path)}: {exc}") from None
    except (ValueError, IndexError, TypeError) as exc:
        raise CommandError(f"BOARD: {os.path.basename(path)} cannot be read ({exc})") from None
    where = (at or "ORIGIN").strip().upper().replace("CENTER", "CENTRE")
    if where not in PLACES:
        raise CommandError(f"BOARD: at is one of {', '.join(PLACES)}")
    if where != "FILE":
        bx0, by0, bx1, by1 = b.bounds()
        b.move(-bx0, -by0) if where == "ORIGIN" else b.move(-(bx0 + bx1) / 2, -(by0 + by1) / 2)
    if len(b.parts) > MAX_PARTS:
        raise CommandError(f"BOARD: {len(b.parts)} parts is too many (at most {MAX_PARTS})")
    if height:
        for part in b.parts:
            if part.height_from == "guess":
                part.height, part.height_from = height, "given"
    if b.fmt == "IDF" and not libpath and b.parts:
        b.notes.append("no library file (.emp): parts are 2 mm squares of guessed height")
    cut = {"ALL": b.holes, "NONE": []}.get(hk, [h for h in b.holes if h.mounting])
    k = UNITS["MM"] / UNITS[p.model.units]  # the file is read in mm

    def scaled(shape):
        if abs(k - 1) < 1e-12:
            return shape
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.gp import gp_Pnt, gp_Trsf

        t = gp_Trsf()
        t.SetScale(gp_Pnt(0, 0, 0), k)
        return BRepBuilderAPI_Transform(shape, t, True).Shape()

    try:
        plate = bd.build_board(b, cut)
    except bd.BoardError as exc:
        raise CommandError(f"BOARD: {exc}") from None
    if not robust.solids(plate):
        raise CommandError("BOARD: the outline does not make a solid plate")
    m = p.model
    body = m.add_body(scaled(plate), nm)
    m.set_style(body.id, color=BOARD_GREEN)
    lines = [_added(p, body, "BOARD")]
    layer = f"{nm}_parts"
    if b.parts and layer.upper() not in m.layers:
        m.put_layer(Layer(layer, PART_GREY))
    taken: set[str] = set()
    made = []
    failed = []
    for part in b.parts:
        if part.height <= 0 or not part.outline:
            continue
        try:
            shape = bd.build_part(b, part)
        except (bd.BoardError, RuntimeError, ValueError, AttributeError):
            failed.append(part.ref)
            continue
        pb = m.add_body(scaled(shape), _name(p, part.ref, taken))
        m.set_style(pb.id, layer=layer)
        made.append((part, pb))
    x0, y0, x1, y1 = b.bounds()
    top = max([pt.offset + pt.height for pt, _ in made if pt.side == "TOP"], default=0.0)
    bottom = max([pt.offset + pt.height for pt, _ in made if pt.side == "BOTTOM"], default=0.0)
    mounting = [h for h in b.holes if h.mounting]

    def r(v):
        return round(v * k, 4)

    # the space the board and its parts take (parts may stand over the edge, as connectors do)
    boxes = [_box(pb.shape) for _, pb in made]
    env = {"min": [min([r(x0)] + [bx[0][0] for bx in boxes]), min([r(y0)] + [bx[0][1] for bx in boxes]),
                   min([r(-bottom)] + [bx[0][2] for bx in boxes])],
           "max": [max([r(x1)] + [bx[1][0] for bx in boxes]), max([r(y1)] + [bx[1][1] for bx in boxes]),
                   max([r(b.thickness + top)] + [bx[1][2] for bx in boxes])]}

    report = {
        "board": body.id, "name": nm, "format": b.fmt, "file": os.path.basename(path), "unit": m.units.lower(),
        "thickness": r(b.thickness), "min": [r(x0), r(y0)], "max": [r(x1), r(y1)],
        "size": [r(x1 - x0), r(y1 - y0)], "cutouts": len(b.loops) - 1,
        "tallest_top": r(top), "tallest_bottom": r(bottom),
        # the space the board and its parts take: what an enclosure goes round
        "envelope": env,
        "holes": len(b.holes), "holes_cut": len(cut),
        "mounting_holes": [{"x": r(h.x), "y": r(h.y), "dia": r(h.dia), "owner": h.owner} for h in mounting],
        "layer": layer,
        "parts": [{"ref": pt.ref, "body": pb.id, "name": pb.name, "package": pt.package, "side": pt.side,
                   "x": r(pt.x), "y": r(pt.y), "rot": round(pt.rot, 3), "height": r(pt.height),
                   "height_from": pt.height_from,
                   "box": bx}
                  for (pt, pb), bx in zip(made, boxes)],
        "notes": b.notes + ([f"parts not made: {', '.join(failed[:10])}"] if failed else []),
    }
    p.give_report("BOARD", report)
    u = m.units.lower()
    head = (f"BOARD {os.path.basename(path)} ({b.fmt}): {fmt_num(r(x1 - x0))} x {fmt_num(r(y1 - y0))} {u}, "
            f"{fmt_num(r(b.thickness))} thick, {len(made)} part{'s' if len(made) != 1 else ''} on layer {layer}; "
            f"tallest {fmt_num(r(top))} above, {fmt_num(r(bottom))} below; "
            f"{len(mounting)} mounting hole{'s' if len(mounting) != 1 else ''}"
            + (f", {len(cut)} holes cut" if cut else ""))
    out = [lines[0]] + ["note: " + n for n in report["notes"]]
    return "\n".join(out + [head])  # the summary last: the history shows the last line
