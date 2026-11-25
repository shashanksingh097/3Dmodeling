"""Drawing details on the sheets (PLAN item 100): centre marks and centre lines on holes, cosmetic
threads, surface finish symbols, weld symbols and leader notes. No Qt here.

Each detail is drawn into the flat views (geometry/drawing.py View) before they are laid out, in the
view's own units, so it moves and scales with the view. ``draw`` takes plain records made by the
command layer (commands/sheet_note_handlers.py) from the model:

* hole: {x, y, z, d, depth, through, axis, thread, major} (sheet_table_handlers.hole_rows plus the
  thread's major diameter, 0 when it has none)
* finish: {point, normal, ra, text}
* weld: {point, size, length}
* leader: {point, normal (or None), text}
* size: {line: (a, b)} or {circle: {centre, r, axis}} (PLAN item 110)

and returns what was placed, as data: [{kind, view, at (x, y in the view), ...}].
"""

from __future__ import annotations

import math

import numpy as np

from . import drawing as dr

ARC_STEPS = 36


def _flat(v: dr.View):
    from OCP.gp import gp_Pnt, gp_Pnt2d

    pr = dr._projector(v.name)

    def f(q):
        out = gp_Pnt2d()
        pr.Project(gp_Pnt(*map(float, q)), out)
        return out.X(), out.Y()

    return f


def _look(v: dr.View) -> np.ndarray:
    z = np.array(dr.VIEWS[v.name][0], float)
    return z / np.linalg.norm(z)


def _arc(c, r: float, a0: float, a1: float) -> list:
    n = max(4, int(ARC_STEPS * abs(a1 - a0) / 360))
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]


def _unit2(d) -> tuple[float, float] | None:
    ln = math.hypot(d[0], d[1])
    return None if ln < 1e-9 else (d[0] / ln, d[1] / ln)


def _leader(v: dr.View, tip, d, h: float) -> tuple[float, float]:
    """A thin leader with an arrow at ``tip`` going out along ``d`` (3 text heights): its far end."""
    q = (tip[0] + d[0] * 3 * h, tip[1] + d[1] * 3 * h)
    v.dims.lines.append((tip, q))
    v.dims.arrows.append((tip, (-d[0], -d[1])))
    return q


def _outwards(v: dr.View, p, normal) -> tuple[float, float]:
    """The way a leader leaves a point: along the face's normal as seen in the view, else away from
    the middle of the view, else up and to the right."""
    f = _flat(v)
    if normal is not None:
        a = f(np.asarray(p, float))
        b = f(np.asarray(p, float) + np.asarray(normal, float))
        u = _unit2((b[0] - a[0], b[1] - a[1]))
        if u is not None and math.hypot(b[0] - a[0], b[1] - a[1]) > 0.3:
            return u
    x0, y0, x1, y1 = v.bounds()
    a = f(np.asarray(p, float))
    u = _unit2((a[0] - (x0 + x1) / 2, a[1] - (y0 + y1) / 2))
    if u is None:
        return (math.sqrt(0.5), math.sqrt(0.5))
    # keep leaders at a slant: easier to tell from the part's own lines
    ang = math.degrees(math.atan2(u[1], u[0]))
    ang = 45 + 90 * round((ang - 45) / 90)
    return (math.cos(math.radians(ang)), math.sin(math.radians(ang)))


def _view_for(views: list[dr.View], normal, edge_on: bool) -> dr.View | None:
    """The flat view to put a symbol on: where the face is seen edge on (a surface finish, as drawn
    by hand), else the one that looks at it most squarely."""
    flat = [v for v in views if v.name in dr.VIEWS and v.name != "ISO"]
    if not flat:
        return None
    if normal is None:
        return flat[0]
    n = np.asarray(normal, float)
    if edge_on:
        side = [v for v in flat if abs(n @ _look(v)) < 1e-3]
        if side:
            return side[0]
    return max(flat, key=lambda v: -(n @ _look(v)))


def centre_marks(views: list[dr.View], holes: list[dict], h: float) -> list[dict]:
    """A cross on each hole seen end on, and a centre line along each hole seen from the side."""
    out = []
    for v in views:
        if v.name not in dr.VIEWS or v.name == "ISO":
            continue
        f, look = _flat(v), _look(v)
        for r in holes:
            ax = np.asarray(r["axis"], float)
            mouth = np.array([r["x"], r["y"], r["z"]], float)
            rad = r["d"] / 2
            e = max(0.3 * rad, 0.8 * h)
            k = abs(ax @ look)
            if abs(k - 1) < 1e-6:
                c = f(mouth)
                v.thin.append([(c[0] - rad - e, c[1]), (c[0] + rad + e, c[1])])
                v.thin.append([(c[0], c[1] - rad - e), (c[0], c[1] + rad + e)])
                out.append({"kind": "centre_mark", "view": v.name, "at": [round(c[0], 6), round(c[1], 6)],
                            "d": r["d"]})
            elif k < 1e-6:
                a, b = f(mouth + ax * e), f(mouth - ax * (r["depth"] + e))
                v.thin.append([a, b])
                out.append({"kind": "centre_line", "view": v.name, "from": [round(a[0], 6), round(a[1], 6)],
                            "to": [round(b[0], 6), round(b[1], 6)], "d": r["d"]})
    return out


def threads(views: list[dr.View], holes: list[dict]) -> list[dict]:
    """Cosmetic threads on tapped holes: the thin three-quarter circle of the thread's outer size
    seen end on, and two thin lines along the thread seen from the side."""
    out = []
    for v in views:
        if v.name not in dr.VIEWS or v.name == "ISO":
            continue
        f, look = _flat(v), _look(v)
        for r in holes:
            major = r.get("major") or 0.0
            if major <= r["d"]:
                continue
            ax = np.asarray(r["axis"], float)
            mouth = np.array([r["x"], r["y"], r["z"]], float)
            k = abs(ax @ look)
            if abs(k - 1) < 1e-6:
                c = f(mouth)
                v.thin.append(_arc(c, major / 2, 0.0, 270.0))
                out.append({"kind": "thread", "view": v.name, "at": [round(c[0], 6), round(c[1], 6)],
                            "thread": r.get("thread", ""), "major": major})
            elif k < 1e-6:
                side = np.cross(ax, look)
                side /= np.linalg.norm(side)
                for s in (1, -1):
                    a = f(mouth + side * s * major / 2)
                    b = f(mouth + side * s * major / 2 - ax * r["depth"])
                    v.thin.append([a, b])
                out.append({"kind": "thread", "view": v.name, "at": [round(c, 6) for c in f(mouth)],
                            "thread": r.get("thread", ""), "major": major})
    return out


def finish(views: list[dr.View], rec: dict, h: float) -> dict | None:
    """The surface finish tick (machined: the closed tick) with its Ra value, on a leader."""
    v = _view_for(views, rec.get("normal"), True)
    if v is None:
        return None
    tip = _flat(v)(rec["point"])
    q = _leader(v, tip, _outwards(v, rec["point"], rec.get("normal")), h)
    a, b, c = q, (q[0] - 0.6 * h, q[1] + h), (q[0] + 1.2 * h, q[1] + 2 * h)
    v.thin.append([b, a, c])
    v.thin.append([b, (q[0] + 0.6 * h, q[1] + h)])  # the bar: material is taken off
    words = f"Ra {_n(rec['ra'])}" if rec.get("ra") else ""
    if rec.get("text"):
        v.thin.append([c, (c[0] + max(3, len(rec["text"])) * 0.6 * h, c[1])])
        v.notes.append((c[0] + len(rec["text"]) * 0.3 * h + 0.3 * h, c[1] + 0.7 * h, h, rec["text"]))
    if words:
        v.notes.append((q[0] + 0.3 * h + len(words) * 0.3 * h, q[1] + 2.6 * h + (0 if not rec.get("text") else h),
                        h, words))
    return {"kind": "finish", "view": v.name, "at": [round(tip[0], 6), round(tip[1], 6)], "ra": rec.get("ra"),
            "text": rec.get("text", "")}


def weld(views: list[dr.View], rec: dict, h: float) -> dict | None:
    """The weld symbol: an arrow to the bead, the reference line, the fillet triangle with the size
    on its left and the length on its right."""
    v = _view_for(views, None, False)
    if v is None:
        return None
    tip = _flat(v)(rec["point"])
    d = _outwards(v, rec["point"], None)
    q = _leader(v, tip, d, h)
    right = d[0] >= 0
    s = 1 if right else -1
    end = (q[0] + s * 8 * h, q[1])
    v.thin.append([q, end])
    t0 = q[0] + s * 3 * h
    v.thin.append([(t0, q[1]), (t0, q[1] + 1.4 * h), (t0 + s * 1.4 * h, q[1]), (t0, q[1])])
    size = _n(rec["size"])
    v.notes.append((t0 - s * (0.4 * h + len(size) * 0.3 * h), q[1] + 0.7 * h, h, size))
    if rec.get("length"):
        ln = _n(rec["length"])
        v.notes.append((t0 + s * (1.8 * h + len(ln) * 0.3 * h), q[1] + 0.7 * h, h, ln))
    return {"kind": "weld", "view": v.name, "at": [round(tip[0], 6), round(tip[1], 6)], "size": rec["size"],
            "length": rec.get("length")}


def leader(views: list[dr.View], rec: dict, h: float) -> dict | None:
    """A note on a leader: the arrow on the point, a short landing, the text after it."""
    v = _view_for(views, rec.get("normal"), False)
    if v is None:
        return None
    tip = _flat(v)(rec["point"])
    d = _outwards(v, rec["point"], rec.get("normal"))
    q = _leader(v, tip, d, h)
    s = 1 if d[0] >= 0 else -1
    land = (q[0] + s * h, q[1])
    v.dims.lines.append((q, land))
    text = rec["text"]
    v.notes.append((land[0] + s * (0.4 * h + len(text) * 0.3 * h), land[1] - 0.0 * h, h, text))
    return {"kind": "leader", "view": v.name, "at": [round(tip[0], 6), round(tip[1], 6)], "text": text}


def edge_size(views: list[dr.View], rec: dict, h: float) -> dict | None:
    """The size of one edge: a straight edge's length in a view that shows it true (along the view's
    across or up direction when it can), a round edge's diameter in a view that looks down its axis."""
    flat = [v for v in views if v.name in dr.VIEWS and v.name != "ISO"]
    if not flat:
        return None
    if "circle" in rec:
        c = rec["circle"]
        ax = np.asarray(c["axis"], float)
        v = next((v for v in flat if abs(abs(ax @ _look(v)) - 1) < 1e-6), None)
        if v is None:
            return None
        cx, cy = _flat(v)(c["centre"])
        text = f"\u00d8{_n(round(2 * c['r'], 4))}"
        dr._diameter(v.dims, (cx, cy, c["r"]), len(v.dims.texts), text, [])
        return {"kind": "size", "view": v.name, "at": [round(cx, 6), round(cy, 6)], "text": text}
    a3, b3 = (np.asarray(q, float) for q in rec["line"])
    d3 = b3 - a3
    ln = float(np.linalg.norm(d3))
    if ln < 1e-9:
        return None
    v = next((v for v in flat if abs(d3 @ _look(v)) < 1e-6 * ln), None)
    if v is None:
        return None
    f = _flat(v)
    a, b = f(a3), f(b3)
    x0, y0, x1, y1 = v.bounds()
    text = _n(round(ln, 4))
    if abs(a[1] - b[1]) < 1e-6 * ln:  # across: below the view, or above when the edge is in its top half
        at = y0 - 2.5 * h if a[1] <= (y0 + y1) / 2 else y1 + 2.5 * h
        dr._linear(v.dims, a, b, False, at, text)
    elif abs(a[0] - b[0]) < 1e-6 * ln:  # up: beside the view
        at = x1 + 2.5 * h if a[0] >= (x0 + x1) / 2 else x0 - 2.5 * h
        dr._linear(v.dims, a, b, True, at, text)
    else:  # slanted: a line along it, set off to one side
        u = ((b[0] - a[0]) / math.dist(a, b), (b[1] - a[1]) / math.dist(a, b))
        nrm = (-u[1], u[0])
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if (mid[0] - (x0 + x1) / 2) * nrm[0] + (mid[1] - (y0 + y1) / 2) * nrm[1] < 0:
            nrm = (-nrm[0], -nrm[1])
        off = 2.5 * h
        pa = (a[0] + nrm[0] * off, a[1] + nrm[1] * off)
        pb = (b[0] + nrm[0] * off, b[1] + nrm[1] * off)
        v.dims.lines += [(a, (pa[0] + nrm[0] * 0.6 * h, pa[1] + nrm[1] * 0.6 * h)),
                         (b, (pb[0] + nrm[0] * 0.6 * h, pb[1] + nrm[1] * 0.6 * h)), (pa, pb)]
        v.dims.arrows += [(pa, (-u[0], -u[1])), (pb, u)]
        ang = math.degrees(math.atan2(u[1], u[0]))
        if ang > 90:
            ang -= 180
        elif ang < -90:
            ang += 180
        tm = ((pa[0] + pb[0]) / 2 + nrm[0] * 0.75 * h, (pa[1] + pb[1]) / 2 + nrm[1] * 0.75 * h)
        v.dims.texts.append((tm, ang, text))
    return {"kind": "size", "view": v.name, "at": [round((a[0] + b[0]) / 2, 6), round((a[1] + b[1]) / 2, 6)],
            "text": text}


def _n(x: float) -> str:
    return f"{x:.6g}"


def text_height(views: list[dr.View], size: float) -> float:
    """The text height the sizes use, so the details match them (else a 70th of the part)."""
    sized = [v.dims.height for v in views if v.dims.lines or v.dims.texts]
    return max(sized) if sized else size / 70


def draw(views: list[dr.View], holes: list[dict], wanted: list[dict], size: float) -> tuple[list[dict], list[str]]:
    """Draw the sheet's details (``wanted``: the records kept on the sheet, resolved to points by the
    command layer) on its views. Returns (placed, warnings)."""
    h = text_height(views, size)
    placed, warn = [], []
    kinds = {w["kind"] for w in wanted}
    if "CENTRES" in kinds:
        placed += centre_marks(views, holes, h)
    if "THREADS" in kinds:
        got = threads(views, holes)
        if not got and holes:
            warn.append("no hole has a thread noted on it (NOTE, ..., \"M6\" on the hole's face): no cosmetic "
                        "threads drawn")
        placed += got
    for w in wanted:
        fn = {"FINISH": finish, "WELD": weld, "LEADER": leader, "SIZE": edge_size}.get(w["kind"])
        if fn is None:
            continue
        if w.get("missing"):
            warn.append(w["missing"])
            continue
        got = fn(views, w, h)
        if got is None:
            warn.append(f"the {w['kind'].lower()} has no flat view to go on" if w["kind"] != "SIZE" else
                        f"the size of edge {w['id']} has no view that shows it true (add one that looks square at it)")
        else:
            placed.append(got)
    return placed, warn
