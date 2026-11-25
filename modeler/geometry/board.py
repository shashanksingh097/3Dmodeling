"""Reading circuit boards for enclosures (PLAN item 103): IDF (.emn with its .emp library) and
KiCad (.kicad_pcb) files. The reading has no Qt and no kernel; :func:`build_board` and
:func:`build_part` make the shapes.

What comes out (:class:`Board`), in mm with y up and the board's top face at z = thickness:

* the outline: loops of lines and arcs (the first, largest one is the board, the others cut-outs);
* the drilled holes (x, y, diameter, plated, what they belong to) and which are mounting holes;
* the parts: reference (R1, U3 ...), package, place, rotation, side (TOP or BOTTOM), outline in
  the board's plane and height. An IDF part takes its outline and height from the library file;
  a KiCad part is the box of its courtyard (else of its pads) with the height from a ``Height``
  property, else a guess from its reference letters (the report says which).
"""

from __future__ import annotations

import math
import re
import shlex
from dataclasses import dataclass, field

THOU = 0.0254  # mm


class BoardError(Exception):
    pass


@dataclass
class Seg:
    """One piece of an outline: a line (a, b), an arc (a, b, mid) or a full circle (centre, r)."""

    kind: str  # LINE, ARC, CIRCLE
    a: tuple[float, float]
    b: tuple[float, float] = (0.0, 0.0)
    mid: tuple[float, float] | None = None
    r: float = 0.0


@dataclass
class Hole:
    x: float
    y: float
    dia: float
    plated: bool = True
    owner: str = ""  # a part reference, BOARD, VIA ...
    mounting: bool = False


@dataclass
class Part:
    ref: str
    package: str
    x: float
    y: float
    rot: float  # degrees, counter-clockwise seen from the top
    side: str  # TOP or BOTTOM
    outline: list[Seg]  # in the board's plane, placed
    height: float
    offset: float = 0.0  # gap between the board face and the part
    height_from: str = "file"  # file, guess, given


@dataclass
class Board:
    name: str
    fmt: str  # IDF or KICAD
    thickness: float
    loops: list[list[Seg]]
    holes: list[Hole] = field(default_factory=list)
    parts: list[Part] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def move(self, dx: float, dy: float) -> None:
        """Shift everything in the board's plane."""
        self.loops = [[_place_seg(s, dx, dy, 0.0) for s in loop] for loop in self.loops]
        for h in self.holes:
            h.x, h.y = h.x + dx, h.y + dy
        for pt in self.parts:
            pt.x, pt.y = pt.x + dx, pt.y + dy
            pt.outline = [_place_seg(s, dx, dy, 0.0) for s in pt.outline]

    def bounds(self) -> tuple[float, float, float, float]:
        pts = [q for loop in self.loops[:1] for s in loop for q in seg_points(s)]
        if not pts:
            raise BoardError("the board has no outline")
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        return min(xs), min(ys), max(xs), max(ys)


# ---- geometry helpers ---------------------------------------------------------------------------

def arc_mid(a, b, angle: float) -> tuple[float, float]:
    """The middle point of the arc from a to b that turns ``angle`` degrees (counter-clockwise > 0)."""
    th = math.radians(angle)
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dx, dy = b[0] - a[0], b[1] - a[1]
    c = math.hypot(dx, dy)
    if c < 1e-12:
        raise BoardError("an arc starts and ends at the same point")
    d = (c / 2) / math.tan(th / 2)  # from the chord's middle to the centre, to the left of a->b
    cx, cy = mx - dy / c * d, my + dx / c * d
    ux, uy = a[0] - cx, a[1] - cy
    h = th / 2
    return (cx + ux * math.cos(h) - uy * math.sin(h), cy + ux * math.sin(h) + uy * math.cos(h))


def seg_points(s: Seg, n: int = 8) -> list[tuple[float, float]]:
    """Points along a piece, for sizes and areas."""
    if s.kind == "LINE":
        return [s.a, s.b]
    if s.kind == "CIRCLE":
        return [(s.a[0] + s.r * math.cos(2 * math.pi * i / n), s.a[1] + s.r * math.sin(2 * math.pi * i / n))
                for i in range(n)]
    c = _centre(s.a, s.mid, s.b)
    if c is None:
        return [s.a, s.mid, s.b]
    a0 = math.atan2(s.a[1] - c[1], s.a[0] - c[0])
    am = math.atan2(s.mid[1] - c[1], s.mid[0] - c[0])
    a1 = math.atan2(s.b[1] - c[1], s.b[0] - c[0])
    r = math.dist(c, s.a)
    sweep = (a1 - a0) % (2 * math.pi)
    if (am - a0) % (2 * math.pi) > sweep:  # it goes the other way round
        sweep -= 2 * math.pi
    return [(c[0] + r * math.cos(a0 + sweep * i / n), c[1] + r * math.sin(a0 + sweep * i / n)) for i in range(n + 1)]


def _centre(p1, p2, p3):
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return (ux, uy)


def loop_area(loop: list[Seg]) -> float:
    pts = [q for s in loop for q in seg_points(s, 16)]
    if len(loop) == 1 and loop[0].kind == "CIRCLE":
        return math.pi * loop[0].r ** 2
    return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                   for i in range(len(pts)))) / 2


def _xf(q, x, y, rot, mirror=False):
    lx, ly = (-q[0] if mirror else q[0]), q[1]
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    return (x + lx * c - ly * s, y + lx * s + ly * c)


def _place_seg(s: Seg, x, y, rot, mirror=False) -> Seg:
    if s.kind == "CIRCLE":
        return Seg("CIRCLE", _xf(s.a, x, y, rot, mirror), r=s.r)
    return Seg(s.kind, _xf(s.a, x, y, rot, mirror), _xf(s.b, x, y, rot, mirror),
               _xf(s.mid, x, y, rot, mirror) if s.mid else None)


def chain(segs: list[Seg], tol: float = 0.01) -> list[list[Seg]]:
    """Unordered pieces (KiCad's Edge.Cuts) to closed loops, largest first."""
    loops = [[s] for s in segs if s.kind == "CIRCLE"]
    open_ = [s for s in segs if s.kind != "CIRCLE"]
    while open_:
        loop = [open_.pop(0)]
        start, end = loop[0].a, loop[0].b
        grew = True
        while grew and math.dist(start, end) > tol:
            grew = False
            for i, s in enumerate(open_):
                if math.dist(s.a, end) <= tol:
                    loop.append(s)
                elif math.dist(s.b, end) <= tol:
                    loop.append(Seg(s.kind, s.b, s.a, s.mid))
                else:
                    continue
                end = loop[-1].b
                open_.pop(i)
                grew = True
                break
        if math.dist(start, end) > tol:
            raise BoardError(f"the board outline is not closed: a gap at ({end[0]:.3f}, {end[1]:.3f})")
        loops.append(loop)
    loops.sort(key=loop_area, reverse=True)
    return loops


# ---- part heights when the file has none ----------------------------------------------------------
GUESS = (("BT", 6.0), ("LED", 1.5), ("USB", 4.0), ("SW", 5.0), ("CN", 8.0), ("FB", 1.0), ("TP", 2.0),
         ("R", 0.6), ("C", 1.2), ("L", 2.0), ("D", 1.2), ("U", 1.6), ("IC", 1.6), ("Q", 1.2), ("Y", 1.2),
         ("X", 1.2), ("J", 8.0), ("P", 8.0), ("S", 5.0), ("K", 15.0), ("T", 10.0), ("F", 2.0), ("H", 0.0))


def guess_height(ref: str) -> float:
    m = re.match(r"[A-Za-z]+", ref)
    letters = m.group(0).upper() if m else ""
    for pre, h in GUESS:
        if letters == pre:
            return h
    for pre, h in GUESS:
        if letters.startswith(pre):
            return h
    return 3.0


# ---- IDF ------------------------------------------------------------------------------------------

def _sections(text: str) -> list[tuple[str, list[str], list[list[str]]]]:
    """(.NAME, words after the name, record lines as words) for each section of an IDF file."""
    out = []
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("."):
            word = line.split()[0].upper()
            if word.startswith(".END_"):
                cur = None
                continue
            cur = (word, line.split()[1:], [])
            out.append(cur)
            continue
        if cur is None:
            continue
        try:
            cur[2].append(shlex.split(line))
        except ValueError:
            cur[2].append(line.split())
    return out


def _f(word: str, what: str) -> float:
    try:
        return float(word)
    except ValueError:
        raise BoardError(f"{what}: {word!r} is not a number") from None


def _idf_loops(rows: list[list[str]], k: float, what: str) -> list[list[Seg]]:
    """IDF loop points (label x y angle) to loops of pieces."""
    loops: dict[str, list[Seg]] = {}
    prev: dict[str, tuple[float, float]] = {}
    order: list[str] = []
    for row in rows:
        if len(row) < 4:
            raise BoardError(f"{what}: a loop point needs a label, x, y and an angle ({' '.join(row)})")
        lab = row[0]
        q = (_f(row[1], what) * k, _f(row[2], what) * k)
        ang = _f(row[3], what)
        if lab not in loops:
            loops[lab] = []
            order.append(lab)
            prev[lab] = q
            continue
        a = prev[lab]
        if abs(abs(ang) - 360) < 1e-6:
            loops[lab].append(Seg("CIRCLE", a, r=math.dist(a, q)))
        elif abs(ang) < 1e-9:
            if math.dist(a, q) > 1e-9:
                loops[lab].append(Seg("LINE", a, q))
        else:
            loops[lab].append(Seg("ARC", a, q, arc_mid(a, q, ang)))
        prev[lab] = q
    out = [loops[lab] for lab in order if loops[lab]]
    out.sort(key=loop_area, reverse=True)
    return out


def _units(word: str) -> float:
    w = word.upper()
    if w in ("MM", "METRIC"):
        return 1.0
    if w in ("THOU", "MIL", "MILS"):
        return THOU
    if w in ("TNM",):
        return 1e-5
    raise BoardError(f"unknown units {word!r} (MM or THOU)")


def read_idf_library(text: str) -> dict[tuple[str, str], tuple[list[list[Seg]], float]]:
    """(geometry name, part number) -> (outline loops in mm, height mm), from an .emp file."""
    lib = {}
    for name, _words, rows in _sections(text):
        if name not in (".ELECTRICAL", ".MECHANICAL") or not rows:
            continue
        head = rows[0]
        if len(head) < 4:
            raise BoardError(f"{name}: the first line is: geometry name, part number, units, height")
        k = _units(head[2])
        height = _f(head[3], name) * k
        loops = _idf_loops([r for r in rows[1:] if len(r) >= 4 and not r[0].upper().startswith("PROP")], k, name)
        lib[(head[0], head[1])] = (loops, height)
        lib.setdefault((head[0], ""), (loops, height))
    return lib


def read_idf(text: str, library: str = "", name: str = "") -> Board:
    """An IDF 3.0 board file (.emn), with its library file's text (.emp) when there is one."""
    secs = _sections(text)
    if not secs or secs[0][0] != ".HEADER":
        raise BoardError("not an IDF file (it does not start with .HEADER)")
    head = secs[0][2]
    if len(head) < 2 or len(head[1]) < 2:
        raise BoardError("the IDF header has no board name and units")
    k = _units(head[1][1])
    bname = name or head[1][0]
    lib = read_idf_library(library) if library else {}
    thickness = 0.0
    loops: list[list[Seg]] = []
    holes: list[Hole] = []
    parts: list[Part] = []
    notes: list[str] = []
    for sname, _words, rows in secs[1:]:
        if sname == ".BOARD_OUTLINE" and rows:
            thickness = _f(rows[0][0], sname) * k
            loops += _idf_loops(rows[1:], k, sname)
        elif sname == ".DRILLED_HOLES":
            for r in rows:
                if len(r) < 3:
                    continue
                plated = len(r) < 4 or r[3].upper() == "PTH"
                # diameter x y plating part hole-type owner
                owner = r[4] if len(r) > 4 else ""
                kind = r[5].upper() if len(r) > 5 else ""
                h = Hole(_f(r[1], sname) * k, _f(r[2], sname) * k, _f(r[0], sname) * k, plated, owner)
                h.mounting = kind in ("MTG", "TOOL") or owner.upper() == "BOARD" and not plated
                holes.append(h)
        elif sname == ".PLACEMENT":
            for i in range(0, len(rows) - 1, 2):
                a, b = rows[i], rows[i + 1]
                if len(a) < 3 or len(b) < 5:
                    raise BoardError(f".PLACEMENT: part {' '.join(a)} needs x, y, offset, rotation, side")
                geom, pn, ref = a[0], a[1], a[2]
                x, y, off, rot = (_f(v, ".PLACEMENT") for v in b[:4])
                side = "BOTTOM" if b[4].upper().startswith("BOT") else "TOP"
                got = lib.get((geom, pn)) or lib.get((geom, ""))
                if got is None:
                    notes.append(f"{ref}: no outline for {geom} in the library file; drawn as a 2 mm square")
                    sq = [Seg("LINE", (-1, -1), (1, -1)), Seg("LINE", (1, -1), (1, 1)),
                          Seg("LINE", (1, 1), (-1, 1)), Seg("LINE", (-1, 1), (-1, -1))]
                    outline, height, src = sq, guess_height(ref), "guess"
                else:
                    outline, height, src = (got[0][0] if got[0] else []), got[1], "file"
                placed = [_place_seg(s, x * k, y * k, rot, side == "BOTTOM") for s in outline]
                parts.append(Part(ref, geom, x * k, y * k, rot, side, placed, height, off * k, src))
    if not loops:
        raise BoardError("the IDF file has no .BOARD_OUTLINE")
    if thickness <= 0:
        raise BoardError("the board thickness is missing or not more than 0")
    return Board(bname, "IDF", thickness, loops, holes, parts, notes)


# ---- KiCad ----------------------------------------------------------------------------------------

def _sexpr(text: str):
    toks = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+', text)
    stack: list[list] = [[]]
    for t in toks:
        if t == "(":
            stack.append([])
        elif t == ")":
            if len(stack) < 2:
                raise BoardError("the KiCad file has a ')' too many")
            done = stack.pop()
            stack[-1].append(done)
        elif t.startswith('"'):
            stack[-1].append(bytes(t[1:-1], "utf-8").decode("unicode_escape") if "\\" in t else t[1:-1])
        else:
            stack[-1].append(t)
    if len(stack) != 1 or not stack[0]:
        raise BoardError("the KiCad file is cut short (a '(' is not closed)")
    return stack[0][0]


def _kids(node, name: str):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == name]


def _kid(node, name: str):
    got = _kids(node, name)
    return got[0] if got else None


def _xy(node, name: str):
    c = _kid(node, name)
    if c is None or len(c) < 3:
        return None
    return (float(c[1]), -float(c[2]))  # KiCad's y points down


def _layer(node) -> str:
    c = _kid(node, "layer")
    return str(c[1]) if c is not None and len(c) > 1 else ""


def _shape_segs(node) -> list[Seg]:
    """gr_/fp_ line, arc, circle, rect, poly to pieces (y up)."""
    kind = node[0].split("_", 1)[1]
    if kind == "line":
        a, b = _xy(node, "start"), _xy(node, "end")
        return [Seg("LINE", a, b)] if a and b and math.dist(a, b) > 1e-9 else []
    if kind == "arc":
        a, b, m = _xy(node, "start"), _xy(node, "end"), _xy(node, "mid")
        if m is not None:
            return [Seg("ARC", a, b, m)]
        ang = _kid(node, "angle")  # KiCad 5: start is the centre, end a point, angle the turn
        c, q = a, b
        if ang is None:
            return []
        th = -float(ang[1])  # clockwise on a y-down screen is counter-clockwise here
        r = math.dist(c, q)
        a0 = math.atan2(q[1] - c[1], q[0] - c[0])
        end = (c[0] + r * math.cos(a0 + math.radians(th)), c[1] + r * math.sin(a0 + math.radians(th)))
        mid = (c[0] + r * math.cos(a0 + math.radians(th / 2)), c[1] + r * math.sin(a0 + math.radians(th / 2)))
        return [Seg("ARC", q, end, mid)]
    if kind == "circle":
        c, q = _xy(node, "center"), _xy(node, "end")
        return [Seg("CIRCLE", c, r=math.dist(c, q))] if c and q else []
    if kind == "rect":
        a, b = _xy(node, "start"), _xy(node, "end")
        if not (a and b):
            return []
        p = [a, (b[0], a[1]), b, (a[0], b[1])]
        return [Seg("LINE", p[i], p[(i + 1) % 4]) for i in range(4)]
    if kind == "poly":
        pts = _kid(node, "pts")
        q = [(float(c[1]), -float(c[2])) for c in (pts[1:] if pts else []) if isinstance(c, list) and c[0] == "xy"]
        return [Seg("LINE", q[i], q[(i + 1) % len(q)]) for i in range(len(q)) if math.dist(q[i], q[(i + 1) % len(q)]) > 1e-9]
    return []


def _fp_ref(fp) -> str:
    for c in _kids(fp, "property"):
        if len(c) > 2 and str(c[1]).lower() == "reference":
            return str(c[2])
    for c in _kids(fp, "fp_text"):
        if len(c) > 2 and c[1] == "reference":
            return str(c[2])
    return ""


def _fp_height(fp) -> float | None:
    for c in _kids(fp, "property"):
        if len(c) > 2 and str(c[1]).lower() in ("height", "component height"):
            m = re.match(r"\s*([0-9.]+)\s*(mm)?", str(c[2]))
            if m:
                return float(m.group(1))
    return None


def read_kicad(text: str, name: str = "") -> Board:
    root = _sexpr(text)
    if not isinstance(root, list) or root[0] != "kicad_pcb":
        raise BoardError("not a KiCad board file (it does not start with (kicad_pcb)")
    gen = _kid(root, "general")
    th = _kid(gen, "thickness") if gen is not None else None
    thickness = float(th[1]) if th is not None else 1.6
    edge: list[Seg] = []
    for c in root[1:]:
        if isinstance(c, list) and c and str(c[0]).startswith("gr_") and _layer(c) == "Edge.Cuts":
            edge += _shape_segs(c)
    holes: list[Hole] = []
    parts: list[Part] = []
    notes: list[str] = []
    for fp in [c for c in root[1:] if isinstance(c, list) and c and c[0] in ("footprint", "module")]:
        at = _kid(fp, "at")
        x, y = float(at[1]), -float(at[2])
        rot = float(at[3]) if len(at) > 3 else 0.0
        side = "BOTTOM" if _layer(fp).startswith("B.") else "TOP"
        ref = _fp_ref(fp) or "?"
        pkg = str(fp[1]).split(":")[-1]
        mount = "mountinghole" in pkg.lower().replace("_", "")

        def place(q, rot=rot):
            return _xf(q, x, y, rot)

        cy: list[tuple[float, float]] = []
        pads: list[tuple[float, float]] = []
        for c in fp[1:]:
            if not (isinstance(c, list) and c):
                continue
            if str(c[0]).startswith("fp_"):
                lay = _layer(c)
                segs = _shape_segs(c)
                if lay == "Edge.Cuts":
                    edge += [_place_seg(s, x, y, rot) for s in segs]
                elif lay.endswith(".CrtYd"):
                    cy += [q for s in segs for q in seg_points(s)]
            elif c[0] == "pad":
                pat = _kid(c, "at")
                size = _kid(c, "size")
                px, py = float(pat[1]), -float(pat[2])
                prot = float(pat[3]) if len(pat) > 3 else rot
                w, h = (float(size[1]), float(size[2])) if size is not None else (0.0, 0.0)
                pr = prot - rot  # the pad's own turn within the part
                for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
                    pads.append(_xf((dx, dy), px, py, pr))
                drill = _kid(c, "drill")
                if drill is not None and len(drill) > 1:
                    try:
                        d = float(drill[2] if drill[1] == "oval" else drill[1])
                    except (ValueError, IndexError):
                        d = 0.0
                    if d > 0:
                        gx, gy = place((px, py))
                        plated = len(c) > 2 and c[2] == "thru_hole"
                        holes.append(Hole(gx, gy, d, plated, ref, mount or not plated and d >= 2.0))
        box = cy or pads
        if mount or not box:
            continue
        lx, ly = [q[0] for q in box], [q[1] for q in box]
        x0, x1, y0, y1 = min(lx), max(lx), min(ly), max(ly)
        if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
            continue
        loc = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        outline = [Seg("LINE", place(loc[i]), place(loc[(i + 1) % 4])) for i in range(4)]
        h = _fp_height(fp)
        src = "file"
        if h is None:
            h, src = guess_height(ref), "guess"
        if h <= 0:
            continue
        parts.append(Part(ref, pkg, x, y, rot, side, outline, h, 0.0, src))
    for v in [c for c in root[1:] if isinstance(c, list) and c and c[0] == "via"]:
        q = _xy(v, "at")
        d = _kid(v, "drill")
        if q and d is not None:
            holes.append(Hole(q[0], q[1], float(d[1]), True, "VIA"))
    if not edge:
        raise BoardError("the KiCad board has no outline (nothing on the Edge.Cuts layer)")
    loops = chain(edge)
    guessed = [p.ref for p in parts if p.height_from == "guess"]
    if guessed:
        notes.append(f"{len(guessed)} part heights are guesses from their reference letters "
                     "(give a Height property in KiCad, or change the boxes)")
    return Board(name or "board", "KICAD", thickness, loops, holes, parts, notes)


def read(path: str, library: str = "", name: str = "") -> Board:
    """A board file by its ending: .emn/.idf/.brd (IDF) or .kicad_pcb."""
    import os

    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        raise BoardError(f"cannot read {path} ({exc})") from None
    if ext == ".kicad_pcb" or text.lstrip().startswith("(kicad_pcb"):
        return read_kicad(text, name)
    lib = ""
    if library:
        try:
            with open(library, encoding="utf-8", errors="replace") as fh:
                lib = fh.read()
        except OSError as exc:
            raise BoardError(f"cannot read the library file {library} ({exc})") from None
    return read_idf(text, lib, name)


# ---- shapes ---------------------------------------------------------------------------------------

def _wire(loop: list[Seg], z: float):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.GC import GC_MakeArcOfCircle, GC_MakeSegment
    from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt

    mw = BRepBuilderAPI_MakeWire()
    for s in loop:
        if s.kind == "CIRCLE":
            e = BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(s.a[0], s.a[1], z), gp_Dir(0, 0, 1)), s.r)).Edge()
        elif s.kind == "ARC" and _centre(s.a, s.mid, s.b) is not None:
            e = BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(gp_Pnt(s.a[0], s.a[1], z), gp_Pnt(s.mid[0], s.mid[1], z),
                                                           gp_Pnt(s.b[0], s.b[1], z)).Value()).Edge()
        else:
            e = BRepBuilderAPI_MakeEdge(GC_MakeSegment(gp_Pnt(s.a[0], s.a[1], z), gp_Pnt(s.b[0], s.b[1], z)).Value()).Edge()
        mw.Add(e)
    if not mw.IsDone():
        raise BoardError("an outline loop does not join up")
    return mw.Wire()


def _prism(loop: list[Seg], z0: float, h: float):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec

    mf = BRepBuilderAPI_MakeFace(_wire(loop, z0), True)
    if not mf.IsDone():
        raise BoardError("an outline loop is not flat and closed")
    return BRepPrimAPI_MakePrism(mf.Face(), gp_Vec(0, 0, h)).Shape()


def build_board(b: Board, holes: list[Hole]):
    """The board as a solid plate from z = 0 to its thickness, with its cut-outs and the holes given."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.TopoDS import TopoDS_Compound

    shape = _prism(b.loops[0], 0.0, b.thickness)
    cut = TopoDS_Compound()
    bb = BRep_Builder()
    bb.MakeCompound(cut)
    n = 0
    for loop in b.loops[1:]:
        bb.Add(cut, _prism(loop, -1.0, b.thickness + 2.0))
        n += 1
    for h in holes:
        bb.Add(cut, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(h.x, h.y, -1.0), gp_Dir(0, 0, 1)), h.dia / 2,
                                             b.thickness + 2.0).Shape())
        n += 1
    if n:
        op = BRepAlgoAPI_Cut(shape, cut)
        op.Build()
        if not op.IsDone():
            raise BoardError("cutting the holes out of the board failed")
        shape = op.Shape()
    return shape


def build_part(b: Board, part: Part):
    """A part as a solid standing on its side of the board."""
    if part.side == "TOP":
        return _prism(part.outline, b.thickness + part.offset, part.height)
    return _prism(part.outline, -part.offset - part.height, part.height)
