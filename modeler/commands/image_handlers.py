"""Sketching from drawings and pictures: SDXF (a DXF file into the open sketch), STRACE (outlines
traced from a picture into the open sketch) and IMAGE (a picture shown on a plane to sketch over)."""

from __future__ import annotations

import math
import os

import numpy as np

from ..core.model import Picture
from ..geometry import dxfread as dx
from ..lang.expr import fmt_num
from ..sketch.sketch import SketchError
from .feature_handlers import plane_ref
from .processor import Arg, CommandError, Path, Processor, Text, command
from .sketch_handlers import _active, _store

MAX_ENTITIES = 3000


class _Joiner:
    """Ties the ends of curves that land on the same spot (within a tolerance)."""

    def __init__(self, sk, tol: float) -> None:
        self.sk, self.tol, self.seen = sk, tol, {}

    def key(self, q):
        return (round(q[0] / self.tol), round(q[1] / self.tol))

    def at(self, q):
        """The point to draw from: an earlier end there (a name), or the position."""
        return self.seen.get(self.key(q), (float(q[0]), float(q[1])))

    def note(self, q, ref: str) -> None:
        self.seen.setdefault(self.key(q), ref)


def _file(p: Processor, file: str, what: str) -> str:
    path = p.file_map.get(file, file)
    if not os.path.isfile(path):
        raise CommandError(f"{what}: no such file: {file}")
    return path


def _repair_hint(sk) -> str:
    """"; SREPAIR would ..." when the drawing came in with gaps, specks or chains of short lines."""
    from ..sketch import repair as rp

    try:
        fix = rp.survey(sk)
    except SketchError:
        return ""
    if not (fix["gaps_closed"] or fix["splines"] or fix["tiny_removed"] or fix["duplicates"]):
        return ""
    return f"; SREPAIR would help: {rp.as_text(fix, doing=False)}"


def _place(p: Processor, sk, ents, scale: float, du: float, dv: float, what: str):
    """Put DXF-style entities (geometry/dxfread.Entity) into the open sketch, scaled and moved, with
    ends that meet tied together. Returns (curves made, count per kind)."""

    def tr(q):
        return (q[0] * scale + du, q[1] * scale + dv)

    pts = [tr(q) for e in ents for q in (e.pts or [e.centre])]
    span = max(1e-9, max(math.dist(pts[0], q) for q in pts)) if pts else 1.0
    j = _Joiner(sk, 1e-6 * max(span, 1.0))
    uid = p.entry_uid
    made, counts = [], {}

    def line(a, b):
        if math.dist(a, b) < j.tol:
            return
        g = sk.add_line(j.at(a), j.at(b), uid)
        j.note(a, f"{g.n}.S")
        j.note(b, f"{g.n}.E")
        made.append(g)

    def arc3(a, mid, b):
        g = sk.add_arc_3p(j.at(a), mid, j.at(b), uid)
        s, e = sk.pt(g.pts["S"]), sk.pt(g.pts["E"])
        for q in (a, b):
            j.note(q, f"{g.n}.S" if math.dist(q, s) <= math.dist(q, e) else f"{g.n}.E")
        made.append(g)

    try:
        for e in ents:
            counts[e.kind] = counts.get(e.kind, 0) + 1
            if e.kind == "LINE":
                line(tr(e.pts[0]), tr(e.pts[1]))
            elif e.kind == "POINT":
                made.append(sk.add_point(tr(e.pts[0]), uid))
            elif e.kind == "CIRCLE":
                made.append(sk.add_circle(tr(e.centre), e.r * scale, uid))
            elif e.kind == "ARC":
                c = tr(e.centre)
                r = e.r * scale
                a1, a2 = e.a1, e.a2 if e.a2 > e.a1 else e.a2 + 360
                pa = (c[0] + r * math.cos(math.radians(a1)), c[1] + r * math.sin(math.radians(a1)))
                pb = (c[0] + r * math.cos(math.radians(a2)), c[1] + r * math.sin(math.radians(a2)))
                am = math.radians((a1 + a2) / 2)
                arc3(pa, (c[0] + r * math.cos(am), c[1] + r * math.sin(am)), pb)
            elif e.kind == "ELLIPSE":
                c = tr(e.centre)
                ax = (c[0] + e.major[0] * scale, c[1] + e.major[1] * scale)
                b = math.hypot(*e.major) * scale * e.ratio
                full = abs((e.a2 - e.a1) - 2 * math.pi) < 1e-6 or abs(e.a2 - e.a1) < 1e-9
                if full:
                    made.append(sk.add_ellipse(c, ax, b, uid))
                else:
                    made.append(sk.add_ellipse(c, ax, b, uid, t1=math.degrees(e.a1), t2=math.degrees(e.a2)))
            elif e.kind == "POLY":
                vs = e.pts
                n = len(vs)
                for k in range(n if e.closed else n - 1):
                    a, b = vs[k], vs[(k + 1) % n]
                    pa, pb = tr(a), tr(b)
                    if abs(a[2]) > 1e-9 and math.dist(pa, pb) > j.tol:
                        arc3(pa, dx.bulge_arc(pa, pb, a[2]), pb)
                    else:
                        line(pa, pb)
            elif e.kind == "SPLINE":
                q = [tr(v) for v in e.pts]
                if e.closed and len(q) > 2 and math.dist(q[0], q[-1]) < j.tol:
                    q = q[:-1]
                if e.closed:
                    made.append(sk.add_spline(q, True, uid))
                else:
                    q[0], q[-1] = j.at(q[0]), j.at(q[-1])
                    g = sk.add_spline(q, False, uid)
                    j.note(e.pts and tr(e.pts[0]), f"{g.n}.S")
                    j.note(tr(e.pts[-1]), f"{g.n}.E")
                    made.append(g)
        sk._dedupe_ties()
        sk.solve()
    except SketchError as exc:
        raise CommandError(f"{what}: {exc}") from None
    return made, counts


@command(
    "SDXF",
    Arg("file", Path, help="a DXF drawing (ASCII)"),
    Arg("scale", float, 1.0, "multiply its sizes by this (25.4: a drawing in inches into mm)"),
    Arg("du", float, 0.0, "move it along the sketch's u"), Arg("dv", float, 0.0, "and v"),
    Arg("layer", Text, "", "only this layer (none: all)"),
    help="Read a 2D DXF drawing into the open sketch: SDXF, bracket.dxf · SDXF, part.dxf, 25.4 (inches) · "
         "SDXF, plate.dxf, 1, -50, -30, OUTLINE (one layer, moved). Lines, arcs, circles, ellipses, polylines "
         "(with their arcs) and splines come in as sketch curves, with ends that meet tied together, so closed "
         "outlines EXTRUDE. Saved projects keep a copy of the file.",
)
def sdxf(p: Processor, file, scale, du, dv, layer):
    sk = _active(p, "SDXF")
    path = _file(p, file, "SDXF")
    if scale <= 0:
        raise CommandError("SDXF: the scale must be more than 0")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            ents, notes = dx.read(f.read())
    except dx.DxfError as exc:
        raise CommandError(f"SDXF: {os.path.basename(path)}: {exc}") from None
    want = layer.strip().strip('"').upper()
    if want:
        ents = [e for e in ents if e.layer.upper() == want]
    if not ents:
        raise CommandError("SDXF: nothing to read" + (f" on layer {layer.strip()}" if want else ""))
    if len(ents) > MAX_ENTITIES:
        raise CommandError(f"SDXF: {len(ents)} curves is too many (at most {MAX_ENTITIES}); pick a layer")

    made, counts = _place(p, sk, ents, scale, du, dv, "SDXF")
    said = (f"read {len(made)} curves from {os.path.basename(path)} ("
            + ", ".join(f"{v} {k.lower()}{'s' if v != 1 else ''}" for k, v in sorted(counts.items())) + ")"
            + (f"; left out: {', '.join(notes)}" if notes else "") + _repair_hint(sk))
    return _store(p, sk, said)


@command(
    "SSVG",
    Arg("file", Path, help="an SVG drawing (from Inkscape, Illustrator, a laser cutter's software ...)"),
    Arg("scale", float, 1.0, "multiply its sizes by this (after its own size in mm)"),
    Arg("du", float, 0.0, "move it along the sketch's u"), Arg("dv", float, 0.0, "and v"),
    Arg("layer", Text, "", "only this layer or group (its label or id; none: all)"),
    help="Read an SVG drawing into the open sketch: SSVG, logo.svg · SSVG, plate.svg, 1, -50, -30, CUT (one "
         "layer, moved). Paths (lines, arcs, Beziers), rectangles, circles, ellipses, lines and polygons come in "
         "as sketch curves at their size in mm (the file's width and viewBox, else 96 pixels to the inch), y "
         "up, with ends that meet tied together so closed outlines EXTRUDE. Text and pictures are left out. "
         "Saved projects keep a copy of the file.",
)
def ssvg(p: Processor, file, scale, du, dv, layer):
    from ..core.model import UNITS
    from ..geometry import svgread as sv

    sk = _active(p, "SSVG")
    path = _file(p, file, "SSVG")
    if scale <= 0:
        raise CommandError("SSVG: the scale must be more than 0")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            ents, notes, info = sv.read(f.read())
    except sv.SvgError as exc:
        raise CommandError(f"SSVG: {os.path.basename(path)}: {exc}") from None
    want = layer.strip().strip('"').upper()
    if want:
        layers = sorted({e.layer for e in ents})
        ents = [e for e in ents if e.layer.upper() == want]
        if not ents:
            raise CommandError(f"SSVG: nothing on layer {layer.strip()} (layers: {', '.join(layers) or 'none'})")
    if not ents:
        raise CommandError("SSVG: no shapes to read in the drawing")
    if len(ents) > MAX_ENTITIES:
        raise CommandError(f"SSVG: {len(ents)} curves is too many (at most {MAX_ENTITIES}); pick a layer")
    k = scale * UNITS["MM"] / UNITS[p.model.units]  # the file is read in mm
    made, _counts = _place(p, sk, ents, k, du, dv, "SSVG")
    counts: dict[str, int] = {}
    for e in ents:  # in the drawing's own words: a two-point piece with a bulge is an arc
        kind = e.kind
        if kind == "POLY":
            kind = "ARC" if len(e.pts) == 2 and abs(e.pts[0][2]) > 1e-12 else "POLYLINE"
        elif kind == "SPLINE":
            kind = "CURVE"
        counts[kind] = counts.get(kind, 0) + 1
    size = f"{fmt_num(round(info['width'] * k, 3))} x {fmt_num(round(info['height'] * k, 3))}"
    said = (f"read {len(made)} curves from {os.path.basename(path)}, {size} ("
            + ", ".join(f"{v} {kind.lower()}{'s' if v != 1 else ''}" for kind, v in sorted(counts.items())) + ")"
            + (f"; left out: {', '.join(notes)}" if notes else "") + _repair_hint(sk))
    return _store(p, sk, said)


@command(
    "STRACE",
    Arg("file", Path, help="a picture (PNG, JPEG, BMP ...): dark shapes on a light ground"),
    Arg("width", help="how wide the whole picture is in the sketch"),
    Arg("threshold", float, 128.0, "grey level 0 to 255: darker than this is inside a shape"),
    Arg("du", float, 0.0, "where the picture's lower left corner goes along u"), Arg("dv", float, 0.0, "and v"),
    Arg("smooth", str, "SPLINE", "SPLINE (smooth closed curves) or LINES (straight pieces)"),
    Arg("detail", float, 0.7, "how closely the outline follows the pixels, in pixels (bigger: fewer points)"),
    help="Trace the outlines of the dark shapes in a picture into the open sketch: STRACE, logo.png, 80 (the "
         "picture 80 wide, its corner at the sketch's origin) · STRACE, scan.jpg, 120, 100, -60, -40, LINES. "
         "Each outline is a closed curve (holes too), ready to EXTRUDE. Saved projects keep a copy of the file.",
)
def strace(p: Processor, file, width, threshold, du, dv, smooth, detail):
    sk = _active(p, "STRACE")
    path = _file(p, file, "STRACE")
    if width <= 0:
        raise CommandError("STRACE: the width must be more than 0")
    if smooth not in ("SPLINE", "LINES"):
        raise CommandError("STRACE: smooth is SPLINE or LINES")
    if detail <= 0:
        raise CommandError("STRACE: the detail must be more than 0")
    try:
        lv = dx.grey(path)
    except dx.DxfError as exc:
        raise CommandError(f"STRACE: {exc}") from None
    h, w = lv.shape
    if w * h > 4_000_000:
        raise CommandError(f"STRACE: the picture is {w} x {h}: make it smaller than 4 million pixels first")
    loops = dx.trace(lv, threshold, smallest=max(4.0, 1e-5 * w * h), tol=detail)
    if not loops:
        raise CommandError(f"STRACE: no dark shapes (darker than {fmt_num(threshold)}) in the picture")
    if len(loops) > 300:
        raise CommandError(f"STRACE: {len(loops)} outlines is too many; raise the threshold or clean the picture")
    s = width / w
    uid = p.entry_uid
    made = 0
    try:
        for L in loops:
            q = [(float(x * s + du), float(y * s + dv)) for x, y in L]
            if len(q) < 3:
                continue
            if smooth == "LINES":
                sk.add_poly(q, True, uid)
            else:
                _smooth_loop(sk, q, uid)
            made += 1
        sk.solve()
    except SketchError as exc:
        raise CommandError(f"STRACE: {exc}") from None
    n_pts = sum(len(L) for L in loops)
    return _store(p, sk, f"traced {made} outline{'s' if made != 1 else ''} ({n_pts} points) from "
                         f"{os.path.basename(path)}, {fmt_num(width)} wide")


CORNER = 40.0  # degrees of turn at a point that make it a corner of a traced outline


def _smooth_loop(sk, q: list, uid: int) -> None:
    """A traced outline as smooth curves between its corners, straight lines where it runs straight
    from corner to corner; a loop with no corners is one closed spline."""
    n = len(q)
    turn = []
    for i in range(n):
        a, b, c = q[i - 1], q[i], q[(i + 1) % n]
        t1 = math.atan2(b[1] - a[1], b[0] - a[0])
        t2 = math.atan2(c[1] - b[1], c[0] - b[0])
        turn.append(abs((math.degrees(t2 - t1) + 180) % 360 - 180))
    corners = [i for i in range(n) if turn[i] > CORNER]
    if not corners:
        sk.add_spline(q, True, uid)
        return
    first_ref = prev_ref = None
    for k, ci in enumerate(corners):
        cj = corners[(k + 1) % len(corners)]
        run = [q[(ci + t) % n] for t in range(((cj - ci) % n) or n + 1)] + [q[cj]]
        start = prev_ref or run[0]
        last = k == len(corners) - 1
        end = first_ref if last and first_ref else run[-1]
        if len(run) <= 3 and len(corners) > 1:  # corner to corner (or one point between): a straight line
            g = sk.add_line(start, end, uid)
        else:
            g = sk.add_spline([start, *run[1:-1], end], False, uid)
        if first_ref is None:
            first_ref = f"{g.n}.S"
        prev_ref = f"{g.n}.E"


@command(
    "IMAGE",
    Arg("file", Path, help="a picture (PNG, JPEG, BMP ...), or CLEAR to take them all away"),
    Arg("plane", Text, "XY", "the plane it lies on: XY, YZ, ZX or a datum plane"),
    Arg("width", float, 100.0, "how wide it is (its height follows from the picture)"),
    Arg("du", float, 0.0, "where its lower left corner goes along the plane's X"), Arg("dv", float, 0.0, "and Y"),
    Arg("opacity", float, 0.6, "0 (clear) to 1 (solid)"),
    help="Show a picture on a plane at a known size, to sketch over it: IMAGE, front.jpg, XY, 240 (240 wide, its "
         "corner at the origin) · IMAGE, side.png, ZX, 240, -120, 0, 0.4 · IMAGE, CLEAR. It is only shown: it is "
         "not a body. Saved projects keep a copy of the file. STRACE traces the outlines of a picture into a "
         "sketch.",
)
def image(p: Processor, file, plane, width, du, dv, opacity):
    m = p.model
    if file.strip().strip('"').upper() == "CLEAR":
        n = m.set_pictures([])
        return f"removed {n} picture{'s' if n != 1 else ''}"
    path = _file(p, file, "IMAGE")
    if width <= 0:
        raise CommandError("IMAGE: the width must be more than 0")
    if not 0 <= opacity <= 1:
        raise CommandError("IMAGE: the opacity is from 0 to 1")
    try:
        lv = dx.grey(path)
    except dx.DxfError as exc:
        raise CommandError(f"IMAGE: {exc}") from None
    h_px, w_px = lv.shape
    d = plane_ref(p, plane, "IMAGE")
    height = width * h_px / w_px
    pic = Picture(path, d.origin, d.x, d.y, width, height, du, dv, opacity)
    m.set_pictures(list(m.pictures) + [pic])
    return (f"picture {len(m.pictures)}: {os.path.basename(path)} on {d.name or 'the plane'}, "
            f"{fmt_num(round(width, 4))} x {fmt_num(round(height, 4))}, its corner at ({fmt_num(du)}, {fmt_num(dv)})")


def corners(pic: Picture) -> list[tuple[float, float, float]]:
    """A picture's corners in the world: lower left, lower right, upper right, upper left."""
    o, x, y = np.array(pic.origin), np.array(pic.xdir), np.array(pic.ydir)
    out = []
    for u, v in ((0, 0), (1, 0), (1, 1), (0, 1)):
        q = o + x * (pic.du + u * pic.width) + y * (pic.dv + v * pic.height)
        out.append(tuple(float(c) for c in q))
    return out
