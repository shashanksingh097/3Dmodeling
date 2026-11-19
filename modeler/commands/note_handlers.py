"""NOTE (text, sizes, hole and fit notes pinned to the model) and FITS (ISO 286 limits and fits)."""

from __future__ import annotations

import math

import numpy as np

from ..core.model import Note
from ..geometry import fits as ft
from ..geometry import robust
from ..geometry import tolerances as tl
from ..lang.expr import fmt_num
from .processor import Arg, CommandError, Processor, Raw, Text, command

DIA = "\u00f8"  # the diameter sign, as the drawings write it


def _num(v: float) -> str:
    return fmt_num(round(v, 4))


def notes_listing(m) -> list[str]:
    out = []
    for i, n in enumerate(m.notes, 1):
        where = "(" + ", ".join(_num(c) for c in n.at) + ")"
        out.append(f"  {i}: \"{n.text}\" at {where}" + (" with a leader" if n.anchor else "")
                   + (" (a size)" if n.span else ""))
    return out


def _vec(q) -> np.ndarray:
    return np.array([q.X(), q.Y(), q.Z()], float)


def _model_size(p: Processor) -> float:
    m = p.model
    shapes = [b.shape for i, b in m.bodies.items() if m.is_shown(i)]
    if not shapes:
        return 10.0
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    for s in shapes:
        BRepBndLib.Add_s(s, box)
    return max(box.CornerMin().Distance(box.CornerMax()), 1e-6) if not box.IsVoid() else 10.0


def _picked(p: Processor) -> list[tuple[str, object, int]]:
    m = p.model
    if m.selection_kind not in ("FACE", "EDGE", "VERTEX") or not m.selection:
        return []
    return [(m.selection_kind, m.entity_shape(m.selection_kind, g), g) for g in m.selection]


def _face_point(face) -> tuple[np.ndarray, np.ndarray]:
    """A point in the middle of a face and its outward normal there."""
    from OCP.BRepGProp import BRepGProp, BRepGProp_Face
    from OCP.BRepTools import BRepTools
    from OCP.GProp import GProp_GProps
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.TopoDS import TopoDS

    f = (getattr(TopoDS, "Face_s", None) or TopoDS.Face)(face)
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(f, g)
    c = g.CentreOfMass()
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(f)
    from OCP.BRep import BRep_Tool
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf

    srf = BRep_Tool.Surface_s(f)
    proj = GeomAPI_ProjectPointOnSurf(c, srf)
    if proj.NbPoints():
        u, v = proj.LowerDistanceParameters()
    else:
        u, v = (umin + umax) / 2, (vmin + vmax) / 2
    pt, n = gp_Pnt(), gp_Vec()
    BRepGProp_Face(f).Normal(u, v, pt, n)
    nn = _vec(n)
    nn = nn / (np.linalg.norm(nn) or 1.0)
    return _vec(pt), nn


def _edge_ends(edge) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopoDS import TopoDS

    c = BRepAdaptor_Curve((getattr(TopoDS, "Edge_s", None) or TopoDS.Edge)(edge))
    a, b = c.FirstParameter(), c.LastParameter()
    return _vec(c.Value(a)), _vec(c.Value((a + b) / 2)), _vec(c.Value(b))


def _vertex(v) -> np.ndarray:
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS

    return _vec(BRep_Tool.Pnt_s((getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex)(v)))


def _anchor(p: Processor, kind: str, shape) -> tuple[np.ndarray, np.ndarray]:
    """Where a note on a picked entity points to, and the way out from it."""
    m = p.model
    if kind == "FACE":
        return _face_point(shape)
    if kind == "EDGE":
        _a, mid, _b = _edge_ends(shape)
    else:
        mid = _vertex(shape)
    # out from the middle of the shown bodies
    shapes = [b.shape for i, b in m.bodies.items() if m.is_shown(i)]
    cs = []
    for s in shapes:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        box = Bnd_Box()
        BRepBndLib.Add_s(s, box)
        cs.append((_vec(box.CornerMin()) + _vec(box.CornerMax())) / 2)
    centre = np.mean(cs, axis=0) if cs else np.zeros(3)
    out = mid - centre
    if np.linalg.norm(out) < 1e-9:
        out = np.array([0.0, 0.0, 1.0])
    return mid, out / np.linalg.norm(out)


def _placed(p: Processor, kind: str, shape) -> tuple[tuple, tuple]:
    pt, out = _anchor(p, kind, shape)
    lift = 0.12 * _model_size(p)
    up = np.array([0.0, 0.0, 1.0])
    d = out + 0.35 * up  # a little up as well, so leaders lean the same way
    d = d / np.linalg.norm(d)
    return tuple(map(float, pt + lift * d)), tuple(map(float, pt))


def _stacked(p: Processor, at, anchor) -> tuple:
    """Move a new note's text up past the notes already pinned to the same place."""
    if anchor is None:
        return at
    same = sum(1 for n in p.model.notes if n.anchor is not None
               and max(abs(a - b) for a, b in zip(n.anchor, anchor)) < 1e-6)
    if not same:
        return at
    step = 0.05 * _model_size(p)
    return (at[0], at[1], at[2] + step * same)


def _rim_placed(p: Processor, kind: str, shape) -> tuple[tuple, tuple]:
    """A hole or shaft note: the leader goes to the rim at its upper end, the text out past it."""
    from ..geometry import threads as th

    if kind != "FACE":
        return _placed(p, kind, shape)
    rf = th.round_face(shape)
    c0 = np.array(rf.centre, float)
    ax = np.array(rf.axis, float)
    c1 = c0 + ax * rf.length
    end, out = (c1, ax) if c1[2] >= c0[2] - 1e-9 else (c0, -ax)
    side = np.cross(out, [0.0, 0.0, 1.0] if abs(out[2]) < 0.9 else [1.0, 0.0, 0.0])
    side = np.cross(side, out)
    side = side / np.linalg.norm(side) if np.linalg.norm(side) > 1e-9 else np.array([1.0, 0.0, 0.0])
    anchor = end + rf.radius * side
    d = out + 0.8 * side
    at = anchor + 0.12 * _model_size(p) * d / np.linalg.norm(d)
    return tuple(map(float, at)), tuple(map(float, anchor))


def _round_dia(kind: str, shape) -> tuple[float, bool]:
    from ..geometry import threads as th

    if kind == "FACE":
        try:
            rf = th.round_face(shape)
        except th.ThreadError:
            raise CommandError("NOTE: the picked face is not round (pick a hole's or a shaft's side)") from None
        return 2 * rf.radius, rf.outside
    if kind == "EDGE":
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Circle
        from OCP.TopoDS import TopoDS

        c = BRepAdaptor_Curve((getattr(TopoDS, "Edge_s", None) or TopoDS.Edge)(shape))
        if c.GetType() == GeomAbs_Circle:
            return 2 * c.Circle().Radius(), False
    raise CommandError("NOTE: pick a round face (or a circular edge) first")


def _coords(p: Processor, raw: str, what: str) -> list[float]:
    parts = [q.strip() for q in raw.split(",")] if raw.strip() else []
    try:
        return [float(p.evaluate(q)) for q in parts if q]
    except Exception:
        raise CommandError(f"NOTE: {what} must be numbers, got {raw!r}") from None


@command(
    "NOTE",
    Arg("text", Text, help="the text (quoted), or SIZE, HOLE, FIT, GDT, DATUM, DELETE, CLEAR"),
    Arg("a1", Raw, "", "a point x,y,z [, a point x,y,z for the leader]; SIZE: two points; FIT: H7 or H7/g6; "
                       "DELETE: note numbers"),
    Arg("a2", Raw, ""), Arg("a3", Raw, ""), Arg("a4", Raw, ""), Arg("a5", Raw, ""), Arg("a6", Raw, ""),
    help="Notes pinned to the model, shown in the view and on drawings: NOTE, \"Paint black\", 10,20,30 (at a "
         "point) · NOTE, \"Break edges\", 50,0,40, 30,0,20 (with a leader to 30,0,20) · PICK, FACE, 7 then NOTE, "
         "\"Polish\" (on the face) · NOTE, SIZE, 0,0,0, 100,0,0 (a size between two points; or pick two vertices "
         "or one straight edge) · NOTE, HOLE (on a picked round face: its diameter) · NOTE, FIT, H7 (the "
         "diameter with its ISO 286 limits) · NOTE, DATUM, A (a datum letter on the picked face) · NOTE, GDT, "
         "FLATNESS, 0.05 · NOTE, GDT, POSITION, D0.1, A, B (a geometric tolerance frame on the picked face: "
         "STRAIGHTNESS, FLATNESS, CIRCULARITY, CYLINDRICITY, LINEPROFILE, PROFILE, PARALLELISM, "
         "PERPENDICULARITY, ANGULARITY, POSITION, CONCENTRICITY, SYMMETRY, RUNOUT, TOTALRUNOUT; D0.1 is a round "
         "zone; up to three datums) · NOTE, DELETE, 2 · NOTE, CLEAR. LIST, NOTES lists them.",
)
def note(p: Processor, text, a1, a2, a3, a4, a5, a6):
    m = p.model
    rest = ", ".join(q for q in (a1, a2, a3, a4, a5, a6) if q.strip())
    word = text.strip()
    up = word.upper()
    if up == "CLEAR":
        n = m.remove_notes(None)
        return f"removed {n} note{'s' if n != 1 else ''}"
    if up == "DELETE":
        which = [int(round(v)) for v in _coords(p, rest, "the note numbers")]
        if not which:
            raise CommandError("NOTE: give the note numbers to delete: NOTE, DELETE, 2")
        try:
            n = m.remove_notes(which)
        except Exception as exc:
            raise CommandError(f"NOTE: {exc}") from None
        return f"removed {n} note{'s' if n != 1 else ''}"
    picks = _picked(p)
    if up == "SIZE":
        v = _coords(p, rest, "the two points")
        if len(v) >= 6:
            a, b = np.array(v[:3]), np.array(v[3:6])
        elif len(picks) == 2 and all(k == "VERTEX" for k, _s, _g in picks):
            a, b = _vertex(picks[0][1]), _vertex(picks[1][1])
        elif len(picks) == 1 and picks[0][0] == "EDGE":
            a, _mid, b = _edge_ends(picks[0][1])
        else:
            raise CommandError("NOTE: a size needs two points (NOTE, SIZE, x1,y1,z1, x2,y2,z2), two picked "
                               "vertices or one picked edge")
        dist = float(np.linalg.norm(b - a))
        if dist < 1e-12:
            raise CommandError("NOTE: the two points are the same")
        mid = (a + b) / 2
        txt = _num(dist)
        k = m.add_note(Note(txt, tuple(map(float, mid)), None, (tuple(map(float, a)), tuple(map(float, b)))))
        return f"note {k}: size {txt}"
    if up in ("HOLE", "FIT"):
        if len(picks) != 1:
            raise CommandError(f"NOTE: pick one round face first (PICK, FACE, n), then NOTE, {up}")
        kind, shape, gid = picks[0]
        d, shaft = _round_dia(kind, shape)
        txt = f"{DIA}{_num(d)}"
        if up == "FIT":
            spec = rest.strip().strip('"')
            if not spec:
                raise CommandError("NOTE: give the tolerance: NOTE, FIT, H7 (a hole) or g6 (a shaft)")
            if "/" in spec:
                spec = spec.split("/")[1 if shaft else 0].strip()
            try:
                lim = ft.limits(spec, d)
            except ft.FitError as exc:
                raise CommandError(f"NOTE: {exc}") from None
            if lim.hole == shaft:
                p.warn(f"NOTE: {spec} is a {'hole' if lim.hole else 'shaft'} tolerance, and face {gid} is "
                       f"{'a shaft' if shaft else 'a hole'}")
            txt += f" {lim.name} ({lim.text()})"
        at, anchor = _rim_placed(p, kind, shape)
        k = m.add_note(Note(txt, _stacked(p, at, anchor), anchor))
        return f"note {k}: {txt} on {kind.lower()} {gid}"
    if up in ("GDT", "DATUM"):
        if len(picks) != 1:
            raise CommandError(f"NOTE: pick one face or edge first (PICK, FACE, n), then NOTE, {up}, ...")
        kind, shape, gid = picks[0]
        try:
            if up == "DATUM":
                if not a1.strip() or a2.strip():
                    raise CommandError("NOTE: give one datum letter: NOTE, DATUM, A")
                fr, warn = tl.datum(a1), []
                if any(n.frame is not None and n.frame.kind == "DATUM" and n.frame.tol == fr.tol for n in m.notes):
                    raise CommandError(f"NOTE: datum {fr.tol} is already on the model")
            else:
                if not a1.strip() or not a2.strip():
                    raise CommandError("NOTE: give the kind and the tolerance: NOTE, GDT, FLATNESS, 0.05")
                fr, warn = tl.frame(a1, a2, [a3, a4, a5, a6])
                have = {n.frame.tol for n in m.notes if n.frame is not None and n.frame.kind == "DATUM"}
                missing = [d for d in fr.datums if d not in have]
                if missing:
                    warn.append(f"datum {', '.join(missing)} is not on the model yet (NOTE, DATUM, {missing[0]})")
        except tl.ToleranceError as exc:
            raise CommandError(f"NOTE: {exc}") from None
        for w in warn:
            p.warn(f"NOTE: {w}")
        at, anchor = _placed(p, kind, shape)
        k = m.add_note(Note(fr.text(), _stacked(p, at, anchor), anchor, None, fr))
        return f"note {k}: {fr.text()} on {kind.lower()} {gid}"
    if not word:
        raise CommandError("NOTE: give the text, e.g. NOTE, \"Paint black\", 10,20,30")
    v = _coords(p, rest, "the point")
    if len(v) >= 3:
        at = tuple(v[:3])
        anchor = tuple(v[3:6]) if len(v) >= 6 else None
        where = "at (" + ", ".join(_num(c) for c in at) + ")"
    elif len(picks) == 1:
        kind, shape, gid = picks[0]
        at, anchor = _placed(p, kind, shape)
        at = _stacked(p, at, anchor)
        where = f"on {kind.lower()} {gid}"
    else:
        raise CommandError("NOTE: give a point (NOTE, \"text\", x,y,z) or pick one face, edge or vertex first")
    k = m.add_note(Note(word.replace("\\n", "\n"), at, anchor))
    return f"note {k} {where}"


@command(
    "FITS",
    Arg("spec", Text, help="a fit such as H7/g6, or one tolerance: H7 (a hole, capitals) or g6 (a shaft)"),
    Arg("d", float, 0.0, "the nominal size (0: the diameter of the picked round face)"),
    logged=False,
    help="ISO 286 limits and fits: FITS, H7/g6, 25 · FITS, H7, 25 · PICK, FACE, 4 then FITS, H7/p6. It gives "
         "the limits of the hole and the shaft, and the largest and smallest clearance (or interference). "
         "NOTE, FIT, H7 pins the tolerance to a picked face, for the view and drawings.",
)
def fits(p: Processor, spec, d):
    if d < 0:
        raise CommandError("FITS: the size cannot be negative")
    if not d:
        picks = _picked(p)
        if len(picks) != 1:
            raise CommandError("FITS: give the size (FITS, H7/g6, 25) or pick one round face first")
        d, _shaft = _round_dia(picks[0][0], picks[0][1])
    s = spec.strip().strip('"')
    try:
        r = ft.fit(s, d)
    except ft.FitError as exc:
        raise CommandError(f"FITS: {exc}") from None

    def lim(x: ft.Limits) -> str:
        return (f"{'hole' if x.hole else 'shaft'} {DIA}{_num(d)} {x.name}: {x.text()} mm, so "
                f"{ft.mm(d * 1000 + x.lower)} to {ft.mm(d * 1000 + x.upper)}")

    if isinstance(r, ft.Limits):
        return f"FITS {lim(r)}"
    kind = r.kind()
    lines = [f"FITS {s} at {DIA}{_num(d)}: {'an' if kind == 'interference' else 'a'} {kind} fit", "  " + lim(r.hole), "  " + lim(r.shaft)]
    if r.kind() == "clearance":
        lines.append(f"  clearance from {ft.mm(r.least)} to {ft.mm(r.most)} mm")
    elif r.kind() == "interference":
        lines.append(f"  interference from {ft.mm(-r.most)} to {ft.mm(-r.least)} mm (a press fit)")
    else:
        lines.append(f"  from {ft.mm(-r.least)} mm interference to {ft.mm(r.most)} mm clearance")
    return "\n".join(lines)



_LINK_ARGS = [Arg(f"l{i}", Raw, "") for i in range(2, 17)]


@command(
    "STACKUP",
    Arg("l1", Raw, help="the sizes of the chain, each added (+) or taken away (-), with its tolerance"),
    *_LINK_ARGS,
    logged=False,
    help="A tolerance stack-up: the gap a chain of sizes closes on, worst case and statistical (root sum "
         "square): STACKUP, +100 ±0.1, -60 +0/-0.05, -39.8 ±0.05 · STACKUP, +25 H7, -25 g6 (ISO 286 tolerances) "
         "· STACKUP, +W ±0.1, -(W - 0.5) ±0.05, MIN=0.1, MAX=0.8 (parameters, and the gap allowed). The links "
         "are +25 ±0.1, -24.9 +0.1/-0.05 or +25 H7; at most 16. It lists each link's share of the spread, so you "
         "see which tolerance to tighten.",
)
def stackup(p: Processor, l1, **rest):
    texts = [t.strip() for t in (l1, *(rest[f"l{i}"] for i in range(2, 17))) if t and t.strip()]
    limits: dict[str, float] = {}
    links = []
    for t in texts:
        key = t.split("=", 1)[0].strip().upper() if "=" in t else ""
        if key in ("MIN", "MAX"):
            try:
                limits[key] = float(p.evaluate(t.split("=", 1)[1]))
            except Exception:
                raise CommandError(f"STACKUP: {t!r}: the gap allowed must be a number") from None
            continue
        try:
            links.append(tl.parse_link(t, p.evaluate))
        except tl.ToleranceError as exc:
            raise CommandError(f"STACKUP: {exc}") from None
    if not links:
        raise CommandError("STACKUP: give the sizes of the chain: STACKUP, +100 ±0.1, -60 ±0.05, -39.8 ±0.05")
    st = tl.Stack(links)

    def n(v):
        return fmt_num(round(v, 4) + 0.0)

    wlo, whi = st.worst
    rlo, rhi = st.rss
    lines = [f"STACKUP of {len(links)} sizes: the gap is {n(st.nominal)} nominal",
             f"  worst case: {n(wlo)} to {n(whi)} (spread {n(whi - wlo)})",
             f"  statistical (root sum square): {n(rlo)} to {n(rhi)} (spread {n(rhi - rlo)})"]
    for k, (lk, share) in enumerate(zip(links, st.shares()), 1):
        lines.append(f"  {k}. {'+' if lk.sign > 0 else '-'}{n(lk.nominal)} {'+' if lk.upper >= 0 else ''}{n(lk.upper)}"
                     f"/{'+' if lk.lower > 0 else ''}{n(lk.lower)}: {share:.0f}% of the spread")
    if limits:
        lo, hi = limits.get("MIN", -math.inf), limits.get("MAX", math.inf)
        want = (f"from {n(lo)} " if lo > -math.inf else "") + (f"up to {n(hi)}" if hi < math.inf else "")

        def verdict(a, b):
            if a >= lo - 1e-12 and b <= hi + 1e-12:
                return "always within"
            if b < lo or a > hi:
                return "never within"
            return "sometimes outside"

        lines.append(f"  gap allowed {want.strip()}: worst case {verdict(wlo, whi)}, statistical {verdict(rlo, rhi)}")
        if verdict(wlo, whi) != "always within":
            worst_link = max(range(len(links)), key=lambda i: links[i].half)
            lines.append(f"  the widest tolerance is link {worst_link + 1}: tighten it first")
    if wlo < 0 < whi or whi < 0:
        lines.append("  the parts can " + ("overlap (the gap goes below 0)" if whi >= 0 else "never fit: the gap is "
                                           "always below 0"))
    return "\n".join(lines)
