"""Reading a 2D DXF drawing (SDXF), and tracing outlines from a picture (STRACE).

DXF: the ASCII format, read by hand (group code / value pairs). It keeps the
ENTITIES section's LINE, CIRCLE, ARC, ELLIPSE, LWPOLYLINE and POLYLINE
(bulges become arcs), SPLINE (through its fit points, or sampled from its
control points) and POINT; X and Y only. Blocks (INSERT) are not opened.

Pictures: the picture is turned to grey, split into dark and light at a
threshold, and the edges between them are followed (marching squares) into
closed loops, which are thinned out (Douglas-Peucker) to a tolerance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


class DxfError(ValueError):
    pass


@dataclass
class Entity:
    kind: str  # LINE, CIRCLE, ARC, ELLIPSE, POLY, SPLINE, POINT
    layer: str
    pts: list = field(default_factory=list)  # LINE: 2 points; POLY: (x, y, bulge); SPLINE: points; POINT: 1
    centre: tuple = (0.0, 0.0)
    r: float = 0.0
    a1: float = 0.0  # degrees (ARC) or parameters in radians (ELLIPSE)
    a2: float = 0.0
    major: tuple = (0.0, 0.0)  # ELLIPSE: the major axis from the centre
    ratio: float = 1.0
    closed: bool = False


def _pairs(text: str):
    lines = text.splitlines()
    if len(lines) % 2:
        lines = lines[:-1]
    for i in range(0, len(lines), 2):
        try:
            code = int(lines[i].strip())
        except ValueError:
            raise DxfError(f"line {i + 1} should be a group code, found {lines[i].strip()[:20]!r} (is it a binary "
                           "DXF? save it as ASCII)") from None
        yield code, lines[i + 1].strip()


def _bspline(ctrl: np.ndarray, knots: list[float], degree: int, n: int) -> np.ndarray:
    """Points along a B-spline (de Boor), n of them evenly in the parameter."""
    k = np.array(knots, float)
    t0, t1 = k[degree], k[len(k) - degree - 1]
    out = []
    for t in np.linspace(t0, t1, n):
        s = min(max(np.searchsorted(k, t, side="right") - 1, degree), len(k) - degree - 2)
        d = [ctrl[j + s - degree].copy() for j in range(degree + 1)]
        for r in range(1, degree + 1):
            for j in range(degree, r - 1, -1):
                i = j + s - degree
                den = k[i + degree - r + 1] - k[i]
                a = 0.0 if den == 0 else (t - k[i]) / den
                d[j] = (1 - a) * d[j - 1] + a * d[j]
        out.append(d[degree])
    return np.array(out)


def read(text: str) -> tuple[list[Entity], list[str]]:
    """The drawing's entities, and notes about what was left out."""
    pairs = list(_pairs(text))
    i, n = 0, len(pairs)
    # find the ENTITIES section
    while i < n - 1 and not (pairs[i] == (0, "SECTION") and pairs[i + 1] == (2, "ENTITIES")):
        i += 1
    if i >= n - 1:
        raise DxfError("the file has no ENTITIES section: is it a DXF drawing?")
    i += 2
    out: list[Entity] = []
    skipped: dict[str, int] = {}
    poly: Entity | None = None
    while i < n:
        code, val = pairs[i]
        if code != 0:
            i += 1
            continue
        kind = val.upper()
        if kind == "ENDSEC":
            break
        j = i + 1
        data: list[tuple[int, str]] = []
        while j < n and pairs[j][0] != 0:
            data.append(pairs[j])
            j += 1
        i = j
        g: dict[int, list[str]] = {}
        for c, v in data:
            g.setdefault(c, []).append(v)

        def f(c, k=0, default=0.0):
            try:
                return float(g[c][k])
            except (KeyError, IndexError, ValueError):
                return default

        layer = g.get(8, ["0"])[0]
        if kind == "LINE":
            out.append(Entity("LINE", layer, [(f(10), f(20)), (f(11), f(21))]))
        elif kind == "CIRCLE":
            out.append(Entity("CIRCLE", layer, centre=(f(10), f(20)), r=f(40)))
        elif kind == "ARC":
            out.append(Entity("ARC", layer, centre=(f(10), f(20)), r=f(40), a1=f(50), a2=f(51)))
        elif kind == "ELLIPSE":
            out.append(Entity("ELLIPSE", layer, centre=(f(10), f(20)), major=(f(11), f(21)), ratio=f(40, default=1.0),
                              a1=f(41), a2=f(42, default=2 * math.pi)))
        elif kind == "POINT":
            out.append(Entity("POINT", layer, [(f(10), f(20))]))
        elif kind == "LWPOLYLINE":
            # vertices: each 10 starts one; a 42 (bulge) after it belongs to it
            verts: list[list[float]] = []
            for c, v in data:
                if c == 10:
                    verts.append([float(v), 0.0, 0.0])
                elif c == 20 and verts:
                    verts[-1][1] = float(v)
                elif c == 42 and verts:
                    verts[-1][2] = float(v)
            flags = int(f(70))
            out.append(Entity("POLY", layer, [tuple(q) for q in verts], closed=bool(flags & 1)))
        elif kind == "POLYLINE":
            poly = Entity("POLY", layer, [], closed=bool(int(f(70)) & 1))
        elif kind == "VERTEX" and poly is not None:
            poly.pts.append((f(10), f(20), f(42)))
        elif kind == "SEQEND" and poly is not None:
            out.append(poly)
            poly = None
        elif kind == "SPLINE":
            degree = int(f(71, default=3))
            ctrl = [(float(x), float(y)) for x, y in zip(g.get(10, []), g.get(20, []))]
            fit = [(float(x), float(y)) for x, y in zip(g.get(11, []), g.get(21, []))]
            knots = [float(v) for v in g.get(40, [])]
            closed = bool(int(f(70)) & 1)
            if len(fit) >= 2:
                out.append(Entity("SPLINE", layer, fit, closed=closed))
            elif len(ctrl) > degree and len(knots) == len(ctrl) + degree + 1:
                pts = _bspline(np.array(ctrl), knots, degree, max(8, 3 * len(ctrl)))
                out.append(Entity("SPLINE", layer, [tuple(q) for q in pts], closed=closed))
            else:
                skipped["SPLINE without points"] = skipped.get("SPLINE without points", 0) + 1
        else:
            skipped[kind] = skipped.get(kind, 0) + 1
    notes = [f"{k} x{v}" for k, v in sorted(skipped.items()) if k not in ("SEQEND", "VERTEX", "ATTRIB")]
    return out, notes


def bulge_arc(a, b, bulge: float):
    """The middle point of the arc from a to b with this bulge (tan of a quarter of its angle)."""
    ax, ay = a
    bx, by = b
    mx, my = (ax + bx) / 2, (ay + by) / 2
    dx, dy = bx - ax, by - ay
    chord = math.hypot(dx, dy)
    sag = bulge * chord / 2  # the arc's height over the chord's middle
    # the bulge is positive for counter-clockwise: the middle lies to the right of a->b's left normal...
    nx, ny = dy / chord, -dx / chord
    return (mx + nx * sag, my + ny * sag)


# ---- outlines from a picture ---------------------------------------------------------------

def grey(path: str) -> np.ndarray:
    """A picture as grey levels 0 (black) to 255, rows from the top."""
    from PySide6.QtGui import QImage

    img = QImage(path)
    if img.isNull():
        raise DxfError(f"cannot read the picture {path} (PNG, JPEG, BMP ...)")
    g = img.convertToFormat(QImage.Format_Grayscale8)
    a = np.frombuffer(g.constBits(), np.uint8, g.sizeInBytes()).reshape(g.height(), g.bytesPerLine())
    return a[:, : g.width()].astype(float)


def _simplify(pts: np.ndarray, tol: float) -> np.ndarray:
    """Douglas-Peucker on an open chain."""
    if len(pts) < 3:
        return pts
    keep = np.zeros(len(pts), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        p, q = pts[a], pts[b]
        d = q - p
        ln = np.hypot(*d)
        seg = pts[a + 1:b]
        if ln < 1e-12:
            dist = np.hypot(*(seg - p).T)
        else:
            dist = np.abs(d[0] * (seg[:, 1] - p[1]) - d[1] * (seg[:, 0] - p[0])) / ln
        k = int(np.argmax(dist))
        if dist[k] > tol:
            m = a + 1 + k
            keep[m] = True
            stack += [(a, m), (m, b)]
    return pts[keep]


def trace(levels: np.ndarray, threshold: float, smallest: float = 4.0, tol: float = 0.7) -> list[np.ndarray]:
    """Closed loops (pixel units, y up from the bottom row) round the dark regions: marching squares on
    the grid of pixel centres, padded so every loop closes; loops enclosing fewer than ``smallest``
    pixels are dropped."""
    h, w = levels.shape
    dark = np.zeros((h + 2, w + 2), bool)
    dark[1:-1, 1:-1] = levels < threshold
    # edges between cells: walk each square, link the midpoints of the edges the outline crosses
    # corner order: tl, tr, br, bl (rows grow downwards)
    tl, tr = dark[:-1, :-1], dark[:-1, 1:]
    bl, br = dark[1:, :-1], dark[1:, 1:]
    code = tl * 8 + tr * 4 + br * 2 + bl * 1
    rows, cols = np.nonzero((code != 0) & (code != 15))
    # edge midpoints, in (x, y-down) grid units of padded pixel centres
    top = lambda r, c: (c + 0.5, r)  # noqa: E731
    right = lambda r, c: (c + 1, r + 0.5)  # noqa: E731
    bottom = lambda r, c: (c + 0.5, r + 1)  # noqa: E731
    left = lambda r, c: (c, r + 0.5)  # noqa: E731
    table = {1: [(left, bottom)], 2: [(bottom, right)], 3: [(left, right)], 4: [(right, top)],
             5: [(left, top), (right, bottom)], 6: [(bottom, top)], 7: [(left, top)], 8: [(top, left)],
             9: [(top, bottom)], 10: [(top, right), (bottom, left)], 11: [(top, right)], 12: [(right, left)],
             13: [(right, bottom)], 14: [(bottom, left)]}
    nxt: dict[tuple, tuple] = {}
    for r, c in zip(rows, cols):
        for a, b in table[int(code[r, c])]:
            nxt[a(r, c)] = b(r, c)
    loops = []
    seen: set = set()
    for start in list(nxt):
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        q = nxt.get(start)
        while q is not None and q != start and q not in seen:
            loop.append(q)
            seen.add(q)
            q = nxt.get(q)
        if q != start or len(loop) < 4:
            continue
        arr = np.array(loop, float)
        x, y = arr[:, 0] - 1, arr[:, 1] - 1  # back to unpadded pixel centres
        area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
        if area < smallest:
            continue
        pts = np.column_stack([x, (h - 1) - y])  # y up
        for _ in range(1):  # take the pixel stair-steps out (a sharp corner loses under a pixel)
            pts = (np.roll(pts, 1, axis=0) + pts + np.roll(pts, -1, axis=0)) / 3
        # thin it out: split the loop at its far point so both halves are open chains
        far = int(np.argmax(np.hypot(*(pts - pts[0]).T)))
        a = _simplify(pts[: far + 1], tol)
        b = _simplify(np.vstack([pts[far:], pts[:1]]), tol)
        loops.append(np.vstack([a[:-1], b[:-1]]))
    loops.sort(key=lambda L: -_area(L))
    return loops


def _area(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
