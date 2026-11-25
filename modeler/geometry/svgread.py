"""Reading SVG drawings into sketches (PLAN item 101). No Qt here.

``read(text)`` turns the drawing's shapes into the same entities as DXF files (geometry/dxfread.py
Entity), so SSVG places them in a sketch the way SDXF does:

* path (M L H V C S Q T A Z, absolute and relative), line, polyline, polygon, rect (rounded
  corners too), circle and ellipse;
* transform on any element or group (matrix, translate, scale, rotate, skewX, skewY);
* sizes in millimetres: a width with a unit and a viewBox give the drawing's scale, otherwise one
  user unit is a CSS pixel (1/96 inch);
* y turned to point up, with the drawing's lower edge on y = 0.

Circular arcs come in as arcs (a polyline bulge) and circles as circles while the transform keeps
them round; Beziers come in as splines through points on them; anything that is no longer round
(an ellipse arc, a squashed circle) as an ellipse or short straight pieces. Text and pictures are
left out and named in the notes.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

import numpy as np

from .dxfread import DxfError, Entity

MM_PER_PX = 25.4 / 96
_UNITS_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72, "pc": 25.4 / 6, "px": MM_PER_PX, "": MM_PER_PX,
             "q": 0.25, "m": 1000.0}
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_SKIP = {"text", "image", "use", "defs", "clipPath", "mask", "pattern", "marker", "symbol", "style", "title",
         "desc", "metadata", "linearGradient", "radialGradient", "filter", "foreignObject", "namedview"}


class SvgError(DxfError):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _length(text: str | None) -> tuple[float, str] | None:
    if not text:
        return None
    m = re.fullmatch(rf"\s*({_NUM})\s*([a-zA-Z%]*)\s*", text)
    if not m or m.group(2) == "%":
        return None
    return float(m.group(1)), m.group(2).lower()


def _nums(text: str) -> list[float]:
    return [float(x) for x in re.findall(_NUM, text or "")]


def transform(text: str | None) -> np.ndarray:
    """An SVG transform list as a 3 x 3 matrix."""
    out = np.eye(3)
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text or ""):
        v = _nums(args)
        t = np.eye(3)
        if name == "matrix" and len(v) == 6:
            t[:2] = [[v[0], v[2], v[4]], [v[1], v[3], v[5]]]
        elif name == "translate" and v:
            t[0, 2], t[1, 2] = v[0], v[1] if len(v) > 1 else 0.0
        elif name == "scale" and v:
            t[0, 0], t[1, 1] = v[0], v[1] if len(v) > 1 else v[0]
        elif name == "rotate" and v:
            a = math.radians(v[0])
            r = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
            if len(v) >= 3:
                c, b = np.eye(3), np.eye(3)
                c[:2, 2], b[:2, 2] = (v[1], v[2]), (-v[1], -v[2])
                r = c @ r @ b
            t = r
        elif name == "skewX" and v:
            t[0, 1] = math.tan(math.radians(v[0]))
        elif name == "skewY" and v:
            t[1, 0] = math.tan(math.radians(v[0]))
        else:
            continue
        out = out @ t
    return out


def _similar(m: np.ndarray) -> float:
    """The uniform scale of a transform that keeps circles round (rotation, mirror, move), else 0."""
    a = m[:2, :2]
    c0, c1 = a[:, 0], a[:, 1]
    s0, s1 = np.linalg.norm(c0), np.linalg.norm(c1)
    if s0 < 1e-12 or abs(s0 - s1) > 1e-9 * max(s0, s1) or abs(float(c0 @ c1)) > 1e-9 * s0 * s1:
        return 0.0
    return float(s0)


class _Out:
    """Entities in the sketch's frame: every point goes through the element's full transform."""

    def __init__(self, layer: str, m: np.ndarray, ents: list):
        self.layer, self.m, self.ents = layer, m, ents
        self.det = float(np.linalg.det(m[:2, :2]))

    def p(self, x: float, y: float) -> tuple[float, float]:
        q = self.m @ np.array([x, y, 1.0])
        return float(q[0]), float(q[1])

    def line(self, a, b):
        pa, pb = self.p(*a), self.p(*b)
        if math.dist(pa, pb) > 1e-12:
            self.ents.append(Entity("LINE", self.layer, [pa, pb]))

    def spline(self, pts):
        q = [self.p(*v) for v in pts]
        self.ents.append(Entity("SPLINE", self.layer, q))

    def circle(self, cx, cy, r):
        s = _similar(self.m)
        if s:
            self.ents.append(Entity("CIRCLE", self.layer, [], centre=self.p(cx, cy), r=r * s))
        else:
            self.ellipse(cx, cy, r, r)

    def ellipse(self, cx, cy, rx, ry):
        c = self.p(cx, cy)
        ax = self.p(cx + rx, cy)
        by = self.p(cx, cy + ry)
        u = (ax[0] - c[0], ax[1] - c[1])
        v = (by[0] - c[0], by[1] - c[1])
        lu, lv = math.hypot(*u), math.hypot(*v)
        if abs(u[0] * v[0] + u[1] * v[1]) > 1e-9 * max(lu * lv, 1e-30):  # sheared: points round it
            n = 72
            pts = [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n))
                   for k in range(n)]
            self.ents.append(Entity("POLY", self.layer, [(*self.p(*q), 0.0) for q in pts], closed=True))
            return
        if lu < lv:
            u, lu, lv = v, lv, lu
        self.ents.append(Entity("ELLIPSE", self.layer, [], centre=c, major=u, ratio=lv / lu, a1=0.0,
                                a2=2 * math.pi))

    def arc(self, a, b, rx, ry, phi, large, sweep):
        """An SVG elliptical arc from a to b: a bulge when it stays circular, else short pieces."""
        if math.dist(a, b) < 1e-12:
            return
        rx, ry = abs(rx), abs(ry)
        if rx < 1e-12 or ry < 1e-12:
            self.line(a, b)
            return
        cx, cy, t1, dt, rx, ry = _centre(a, b, rx, ry, phi, large, sweep)
        if abs(rx - ry) <= 1e-9 * max(rx, ry) and _similar(self.m):
            # circular: split into pieces under a half turn, each a two-point polyline with a bulge
            n = max(1, int(math.ceil(abs(dt) / math.pi - 1e-9)))
            sign = 1.0 if self.det > 0 else -1.0
            for k in range(n):
                ta, tb = t1 + dt * k / n, t1 + dt * (k + 1) / n
                pa = (cx + rx * math.cos(ta), cy + rx * math.sin(ta)) if k else a
                pb = (cx + rx * math.cos(tb), cy + rx * math.sin(tb)) if k < n - 1 else b
                bulge = math.tan(sign * (tb - ta) / 4)
                self.ents.append(Entity("POLY", self.layer, [(*self.p(*pa), bulge), (*self.p(*pb), 0.0)]))
            return
        n = max(4, int(abs(dt) / (math.pi / 32)) + 1)
        cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
        pts = []
        for k in range(n + 1):
            t = t1 + dt * k / n
            x, y = rx * math.cos(t), ry * math.sin(t)
            pts.append((cx + cp * x - sp * y, cy + sp * x + cp * y))
        pts[0], pts[-1] = a, b
        self.ents.append(Entity("POLY", self.layer, [(*self.p(*q), 0.0) for q in pts]))


def _centre(a, b, rx, ry, phi, large, sweep):
    """SVG's endpoint arc as centre, start angle, sweep and the radii (grown if too small)."""
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (a[0] - b[0]) / 2, (a[1] - b[1]) / 2
    x1, y1 = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1 / rx) ** 2 + (y1 / ry) ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    k = math.sqrt(max(0.0, num / den)) if den > 0 else 0.0
    if bool(large) == bool(sweep):
        k = -k
    cx1, cy1 = k * rx * y1 / ry, -k * ry * x1 / rx
    cx = cp * cx1 - sp * cy1 + (a[0] + b[0]) / 2
    cy = sp * cx1 + cp * cy1 + (a[1] + b[1]) / 2

    def ang(ux, uy, vx, vy):
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    t1 = ang(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    dt = ang((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    return cx, cy, t1, dt, rx, ry


def _bezier(pts, n: int = 6) -> list:
    """Points along a quadratic or cubic Bezier (the ends included)."""
    p = np.array(pts, float)
    out = []
    for k in range(n + 1):
        t = k / n
        if len(p) == 3:
            q = (1 - t) ** 2 * p[0] + 2 * (1 - t) * t * p[1] + t * t * p[2]
        else:
            q = (1 - t) ** 3 * p[0] + 3 * (1 - t) ** 2 * t * p[1] + 3 * (1 - t) * t * t * p[2] + t ** 3 * p[3]
        out.append((float(q[0]), float(q[1])))
    return out


def path(d: str, out: _Out) -> None:
    toks = re.findall(rf"[MmLlHhVvCcSsQqTtAaZz]|{_NUM}", d or "")
    i, cmd = 0, ""
    cur = start = (0.0, 0.0)
    last_c = last_q = None  # the previous control point (for S and T)

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    def flag():
        # arc flags may be written without separators ("a1 1 0 01 10 10")
        nonlocal i
        t = toks[i]
        if len(t) > 1 and t[0] in "01" and t[1:].lstrip("+-").replace(".", "", 1).isdigit():
            toks[i] = t[1:]
            return int(t[0])
        i += 1
        return int(float(t))

    while i < len(toks):
        t = toks[i]
        if re.fullmatch(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                if math.dist(cur, start) > 1e-12:
                    out.line(cur, start)
                cur, last_c, last_q = start, None, None
                continue
        elif not cmd:
            raise SvgError("a path starts with a number, not a command")
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = cur if rel else (0.0, 0.0)
        try:
            if c == "M":
                cur = start = (ox + num(), oy + num())
                cmd = "l" if rel else "L"  # more pairs after M are lines
                last_c = last_q = None
            elif c == "L":
                q = (ox + num(), oy + num())
                out.line(cur, q)
                cur, last_c, last_q = q, None, None
            elif c == "H":
                q = ((ox if rel else 0.0) + num(), cur[1])
                out.line(cur, q)
                cur, last_c, last_q = q, None, None
            elif c == "V":
                q = (cur[0], (oy if rel else 0.0) + num())
                out.line(cur, q)
                cur, last_c, last_q = q, None, None
            elif c == "C":
                c1, c2, q = (ox + num(), oy + num()), (ox + num(), oy + num()), (ox + num(), oy + num())
                out.spline(_bezier([cur, c1, c2, q]))
                cur, last_c, last_q = q, c2, None
            elif c == "S":
                c1 = (2 * cur[0] - last_c[0], 2 * cur[1] - last_c[1]) if last_c else cur
                c2, q = (ox + num(), oy + num()), (ox + num(), oy + num())
                out.spline(_bezier([cur, c1, c2, q]))
                cur, last_c, last_q = q, c2, None
            elif c == "Q":
                c1, q = (ox + num(), oy + num()), (ox + num(), oy + num())
                out.spline(_bezier([cur, c1, q]))
                cur, last_c, last_q = q, None, c1
            elif c == "T":
                c1 = (2 * cur[0] - last_q[0], 2 * cur[1] - last_q[1]) if last_q else cur
                q = (ox + num(), oy + num())
                out.spline(_bezier([cur, c1, q]))
                cur, last_c, last_q = q, None, c1
            elif c == "A":
                rx, ry, phi = num(), num(), num()
                large, sweep = flag(), flag()
                q = (ox + num(), oy + num())
                out.arc(cur, q, rx, ry, phi, large, sweep)
                cur, last_c, last_q = q, None, None
            else:
                raise SvgError(f"unknown path command {cmd!r}")
        except (IndexError, ValueError):
            raise SvgError(f"a path's {cmd!r} has too few numbers") from None


def _rect(el, out: _Out) -> None:
    f = lambda k: float(_nums(el.get(k, "0"))[0]) if _nums(el.get(k, "0")) else 0.0  # noqa: E731
    x, y, w, h = f("x"), f("y"), f("width"), f("height")
    if w <= 0 or h <= 0:
        return
    rx, ry = el.get("rx"), el.get("ry")
    rx = f("rx") if rx is not None else (f("ry") if ry is not None else 0.0)
    ry = f("ry") if ry is not None else rx
    rx, ry = min(rx, w / 2), min(ry, h / 2)
    if rx <= 0 or ry <= 0:
        path(f"M{x},{y} H{x + w} V{y + h} H{x} Z", out)
        return
    path(f"M{x + rx},{y} H{x + w - rx} A{rx},{ry} 0 0 1 {x + w},{y + ry} V{y + h - ry} "
         f"A{rx},{ry} 0 0 1 {x + w - rx},{y + h} H{x + rx} A{rx},{ry} 0 0 1 {x},{y + h - ry} "
         f"V{y + ry} A{rx},{ry} 0 0 1 {x + rx},{y} Z", out)


def read(text: str) -> tuple[list[Entity], list[str], dict]:
    """(entities in mm with y up, notes on what was left out, info: width, height, mm per unit)."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SvgError(f"not an SVG file ({exc})") from None
    if _local(root.tag) != "svg":
        raise SvgError("not an SVG file (no <svg> at the top)")
    vb = _nums(root.get("viewBox", ""))
    wl, hl = _length(root.get("width")), _length(root.get("height"))
    unit = MM_PER_PX
    if len(vb) == 4 and vb[2] > 0 and wl is not None:
        unit = wl[0] * _UNITS_MM.get(wl[1], MM_PER_PX) / vb[2]
    elif wl is not None and wl[1] in _UNITS_MM and wl[1] not in ("", "px"):
        unit = _UNITS_MM[wl[1]]
    height = vb[1] + vb[3] if len(vb) == 4 else (hl[0] if hl else 0.0)
    # user units to mm, y up with the drawing's lower edge at 0
    top = np.array([[unit, 0, 0], [0, -unit, height * unit], [0, 0, 1.0]])
    ents: list[Entity] = []
    skipped: dict[str, int] = {}

    def walk(el, m, layer):
        tag = _local(el.tag)
        if tag in _SKIP:
            if tag in ("text", "image", "use"):
                skipped[tag] = skipped.get(tag, 0) + 1
            return
        style = (el.get("style") or "") + ";display:" + (el.get("display") or "")
        if re.search(r"display\s*:\s*none", style):
            return
        m = m @ transform(el.get("transform"))
        if tag == "g":
            name = el.get("{http://www.inkscape.org/namespaces/inkscape}label") or el.get("id") or ""
            if el.get("{http://www.inkscape.org/namespaces/inkscape}groupmode") == "layer" or not layer:
                layer = name or layer
            for ch in el:
                walk(ch, m, layer)
            return
        if tag == "svg" and el is not root:
            for ch in el:
                walk(ch, m, layer)
            return
        out = _Out(layer or "0", m, ents)
        n = lambda k: (_nums(el.get(k, "0")) or [0.0])[0]  # noqa: E731
        if tag == "path":
            path(el.get("d", ""), out)
        elif tag == "line":
            out.line((n("x1"), n("y1")), (n("x2"), n("y2")))
        elif tag in ("polyline", "polygon"):
            v = _nums(el.get("points", ""))
            pts = list(zip(v[0::2], v[1::2]))
            for a, b in zip(pts, pts[1:]):
                out.line(a, b)
            if tag == "polygon" and len(pts) > 2:
                out.line(pts[-1], pts[0])
        elif tag == "rect":
            _rect(el, out)
        elif tag == "circle":
            if n("r") > 0:
                out.circle(n("cx"), n("cy"), n("r"))
        elif tag == "ellipse":
            if n("rx") > 0 and n("ry") > 0:
                if abs(n("rx") - n("ry")) < 1e-12:
                    out.circle(n("cx"), n("cy"), n("rx"))
                else:
                    out.ellipse(n("cx"), n("cy"), n("rx"), n("ry"))
        elif tag == "svg":
            pass
        for ch in el if tag not in ("g", "svg") else ():
            walk(ch, m, layer)

    for ch in root:
        walk(ch, top, "")
    notes = [f"{v} {k}{'s' if v != 1 else ''}" for k, v in sorted(skipped.items())]
    w = (vb[2] if len(vb) == 4 else (wl[0] if wl else 0.0)) * unit
    return ents, notes, {"width": w, "height": height * unit, "mm_per_unit": unit}
