"""Getting parts ready for analysis (PLAN items 80-82, geometry/analysis_prep.py): middle surfaces
and beam lines, flow and air volumes, parts that share faces, merging small faces. Geometry only:
the separate analysis app meshes and solves."""

from __future__ import annotations

import re

import numpy as np

from ..geometry import analysis_prep as ap
from ..geometry import meshbody as mb
from ..geometry import robust
from ..lang.expr import fmt_num
from .processor import REGISTRY, Arg, BodyRef, CommandError, Processor, Raw, command
from .wrap_handlers import wrap_targets


def _solid(p: Processor, cmd: str, b: int):
    body = p.model.body(b)
    if mb.is_mesh(body.shape):
        raise CommandError(f"{cmd}: body {b} is a mesh body; TOSOLID, {b} makes a solid of it first")
    if not robust.solids(body.shape):
        raise CommandError(f"{cmd}: body {b} is not a solid")
    return body


def _gids(body, kind: str, idx: list[int]) -> list[int]:
    ids = body.entity_ids[kind]
    return [ids[i] for i in idx if 0 <= i < len(ids)]


def _gid_of(p: Processor, body, kind: str, sub) -> int:
    try:
        return p.model.find_entity(body.id, kind, sub)
    except Exception:  # noqa: BLE001 - a piece the kernel copied: no ID
        return 0


def _free(m, base: str) -> str:
    """``base``, or base_2, base_3 ... when a body already has that name."""
    taken = {b.name.lower() for b in m.bodies.values()}
    if base.lower() not in taken:
        return base
    k = 2
    while f"{base}_{k}".lower() in taken:
        k += 1
    return f"{base}_{k}"


def _t(x: float) -> str:
    return fmt_num(round(x, 6))


# ---- item 80 --------------------------------------------------------------------------------


@command(
    "MIDSURFACE",
    Arg("b", BodyRef, help="a thin part (sheet metal, a shelled housing, a tube, a plate)"),
    Arg("max", float, 0.0, "walls up to this thick only (0: any wall thinner than its faces are wide)"),
    help="The middle surface of a thin part, for a shell model in the analysis app: MIDSURFACE, bracket. Each "
         "wall's two sides are paired, one side is pulled half the thickness into the wall, and the thickness is "
         "kept on each face of the new surface body (in the answer, and on the faces in STEP). With one "
         "thickness the walls meet at their corners; with several, each face is offset on its own and the "
         "flat ones are carried on (or cut back) until they meet, so steps, L and T joins stay closed",
)
def midsurface(p: Processor, b, max):  # the argument's name in the command
    from .handlers import _added

    if max < 0:
        raise CommandError("MIDSURFACE: the largest thickness cannot be negative")
    body = _solid(p, "MIDSURFACE", b)
    try:
        mid = ap.midsurface(body.shape, max)
    except ap.PrepError as exc:
        raise CommandError(f"MIDSURFACE: body {b}: {exc}") from None
    m = p.model
    new = m.add_body(mid.shape, name=_free(m, f"{body.name}_mid") if body.name != f"body{body.id}" else "")
    per = {}
    for face, t in mid.faces:
        gid = _gid_of(p, new, "FACE", face)
        if gid:
            per[gid] = round(float(t), 9)
    m.thickness[new.id] = per
    ts = sorted({round(w.thickness, 6) for w in mid.walls})
    walls = [{"face": g, "across": o, "thickness": round(w.thickness, 6)}
             for w in mid.walls for g, o in zip(_gids(body, "FACE", [w.face]), _gids(body, "FACE", [w.other]))]
    d = {"body": b, "new_body": new.id, "thickness": ts[0] if len(ts) == 1 else ts, "joined": mid.joined,
         "faces": [{"face": g, "thickness": t} for g, t in sorted(per.items())], "walls": walls,
         "gaps_closed": mid.closed, "free_edges": robust.open_edges(mid.shape),
         "rims": _gids(body, "FACE", mid.rims), "left_out": _gids(body, "FACE", mid.unpaired),
         "area": round(ap.area(mid.shape), 6)}
    p.give_report("MIDSURFACE", d)
    tt = _t(ts[0]) if len(ts) == 1 else ", ".join(map(_t, ts))
    notes = [f"thickness {tt}", f"{len(mid.walls)} wall face{'s' if len(mid.walls) != 1 else ''}"]
    if mid.joined:
        notes.append("walls meet at their corners")
    else:
        notes.append("faces offset one by one (several thicknesses)"
                     + (f", {mid.closed} gap{'s' if mid.closed != 1 else ''} closed where the thickness changes"
                        if mid.closed else ""))
    if d["left_out"]:
        notes.append(f"faces {', '.join(map(str, d['left_out']))} have no wall across them (too thick; left out)")
    return _added(p, new, f"MIDSURFACE of body {b} ({'; '.join(notes)})")


def _beam_bodies(p: Processor, what: str) -> list[int]:
    ids = wrap_targets(p, what, "BEAMS")
    return [i for i in ids if robust.solids(p.model.body(i).shape)]


@command(
    "BEAMS",
    Arg("what", Raw, "ALL", "frame members or long parts: a body, several (\"3 7\" or names), SEL, or ALL"),
    Arg("join", float, 0.0, "ends closer than this are one joint (0: half the largest section's size)"),
    help="Centre lines of frame members with their sections, for a beam model in the analysis app: BEAMS, ALL. "
         "Each member becomes a line (one new curve body holds them all), with its section's area, second "
         "moments, torsion constant and main direction in the answer, and where the ends meet. MEMBER bodies "
         "keep their profile name and size",
)
def beams(p: Processor, what, join):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex
    from OCP.gp import gp_Pnt

    from .handlers import _added

    m = p.model
    ids = _beam_bodies(p, what)
    if not ids:
        raise CommandError("BEAMS: no solids to find centre lines of")
    rows, lines = [], []
    for bid in ids:
        body = m.body(bid)
        rec = m.members.get(bid)
        try:
            bm = ap.beam_of(body.shape, rec.p0 if rec else None, rec.p1 if rec else None)
        except ap.PrepError as exc:
            raise CommandError(f"BEAMS: body {bid}: {exc}") from None
        if rec is not None:
            bm.profile, bm.size = rec.profile, rec.size_text()
        rows.append((bid, bm))
    sizes = [np.sqrt(bm.area) for _, bm in rows]
    tol = join if join > 0 else 0.5 * max(sizes) * 1.5
    joints = ap.nodes([bm for _, bm in rows], tol)
    # the lines meet in one vertex at each joint, so the beam model is connected there
    vert = {}
    for pt, ends in joints:
        v = BRepBuilderAPI_MakeVertex(gp_Pnt(*pt)).Vertex()
        for end in ends:
            vert[end] = v
    edges = [BRepBuilderAPI_MakeEdge(vert[(i, 0)], vert[(i, 1)]).Edge() for i in range(len(rows))]
    new = m.add_body(ap._compound(edges) if len(edges) > 1 else edges[0], name=_free(m, "beams"))
    out = []
    for (bid, bm), e in zip(rows, edges):
        g = _gid_of(p, new, "EDGE", e)
        name = m.body(bid).name
        out.append({"body": bid, "name": name, "edge": g, "p0": [round(x, 6) for x in bm.p0],
                    "p1": [round(x, 6) for x in bm.p1], "length": round(bm.length, 6), "area": round(bm.area, 6),
                    "iy": round(bm.iy, 6), "iz": round(bm.iz, 6), "j": round(bm.j, 6),
                    "y_dir": [round(x, 6) for x in bm.y_dir], "profile": bm.profile, "size": bm.size})
        sec = f"{bm.profile} {bm.size}, " if bm.profile else ""
        lines.append(f"  {name} (body {bid}, edge {g}): {sec}length {_t(bm.length)}, area {bm.area:.5g}, "
                     f"Iy {bm.iy:.5g}, Iz {bm.iz:.5g}, J {bm.j:.5g}")
    js = [{"at": [round(x, 6) for x in pt], "ends": [{"body": rows[i][0], "end": k} for i, k in ends]}
          for pt, ends in joints if len(ends) > 1]
    free = sum(1 for _pt, ends in joints if len(ends) == 1)
    d = {"beams": out, "joints": js, "free_ends": free, "join_tolerance": round(tol, 6), "new_body": new.id}
    p.give_report("BEAMS", d)
    head = _added(p, new, f"BEAMS: {len(rows)} centre line{'s' if len(rows) != 1 else ''}, {len(js)} joint"
                          f"{'s' if len(js) != 1 else ''}, {free} free end{'s' if free != 1 else ''}")
    return head + "\n" + "\n".join(lines)


# ---- item 81 --------------------------------------------------------------------------------


def _cap_faces(p: Processor, body, caps: str) -> list[int] | None:
    """Face indexes (0-based, in the body) from AUTO, SEL or face IDs; None for AUTO."""
    words = [w for w in re.split(r"[\s;]+", str(caps).strip().strip('"')) if w]
    m = p.model
    if not words or [w.upper() for w in words] == ["AUTO"]:
        return None
    if [w.upper() for w in words] == ["SEL"]:
        if m.selection_kind != "FACE" or not m.selection:
            raise CommandError("FLUIDVOLUME: SEL needs the end faces round the openings picked first")
        gids = list(m.selection)
    else:
        try:
            gids = [int(float(p.evaluate(w))) for w in words]
        except Exception:  # noqa: BLE001
            raise CommandError("FLUIDVOLUME: the openings are AUTO, SEL or face IDs (\"12 15\")") from None
    out = []
    for g in gids:
        try:
            owner, idx = m.entity_owner("FACE", g)
        except Exception:  # noqa: BLE001
            raise CommandError(f"FLUIDVOLUME: no face {g}") from None
        if owner != body.id:
            raise CommandError(f"FLUIDVOLUME: face {g} is on body {owner}, not on body {body.id}")
        out.append(idx - 1)
    return out


@command(
    "FLUIDVOLUME",
    Arg("b", BodyRef, help="a pipe, valve or housing"),
    Arg("caps", Raw, "AUTO", "the openings: AUTO (every flat face with a hole that leads out), SEL (the end "
                             "faces picked), or face IDs \"12 15\""),
    help="The inside of a pipe, valve or housing up to its openings, as a new solid for a flow model: "
         "FLUIDVOLUME, valve. Each opening is closed by a flat cap across the hole in its end face; the answer "
         "lists the openings and the faces of the new body that close them (inlets and outlets). A closed "
         "housing gives its inner space",
)
def fluidvolume(p: Processor, b, caps):
    from .handlers import _added

    m = p.model
    body = _solid(p, "FLUIDVOLUME", b)
    picked = _cap_faces(p, body, caps)
    try:
        cap_faces, opens = ap.openings(body.shape, picked)
        solids = ap.fluid_volume(body.shape, cap_faces)
    except ap.PrepError as exc:
        raise CommandError(f"FLUIDVOLUME: body {b}: {exc}") from None
    if not solids:
        raise CommandError(f"FLUIDVOLUME: body {b} has no inside closed off by "
                           + (f"its {len(opens)} openings" if opens else "its walls")
                           + "; pick the end faces round the openings (SEL) if some were missed")
    base = body.name if body.name != f"body{body.id}" else f"body{body.id}"
    msgs, made = [], []
    for k, s in enumerate(sorted(solids, key=lambda x: -robust.volume(x))):
        new = m.add_body(s, name=_free(m, f"{base}_fluid"))
        ends = _opening_faces(p, new, opens)
        for e in ends:  # named sets that go to STEP for the analysis app (PLAN item 95)
            if e["face"]:
                m.save_set(f"{new.name}_opening_{e['opening']}", "FACE", [e["face"]])
        made.append({"body": new.id, "volume": round(robust.volume(s), 6), "openings": ends})
        msgs.append(_added(p, new, f"fluid volume {robust.volume(s):.6g} {m.units.lower()}3"
                                   + (f", openings on faces {', '.join(str(e['face']) for e in ends)}" if ends else "")))
    d = {"body": b, "openings": [{"face": _gids(body, "FACE", [o.face])[0], "centre": [round(x, 6) for x in o.centre],
                                  "normal": [round(x, 6) for x in o.normal], "area": round(o.area, 6)} for o in opens],
         "volumes": made}
    p.give_report("FLUIDVOLUME", d)
    head = (f"FLUIDVOLUME of body {b}: {len(opens)} opening{'s' if len(opens) != 1 else ''}"
            + (" (" + "; ".join(f"face {x['face']}, area {x['area']:.5g}" for x in d["openings"]) + ")" if opens else
               " (a closed inside)"))
    return head + "\n" + "\n".join(msgs)


def _opening_faces(p: Processor, new, opens) -> list[dict]:
    """The faces of the fluid body that close each opening: flat, on the opening's plane and round
    its centre."""
    from OCP.TopAbs import TopAbs_FACE

    out = []
    faces = ap._explore(new.shape, TopAbs_FACE)
    for k, o in enumerate(opens):
        c, n = np.array(o.centre), np.array(o.normal)
        for f in faces:
            got = ap.inside_point(f)
            if got is None:
                continue
            q = np.array(ap._p(got[0]))
            nv = np.array([got[1].X(), got[1].Y(), got[1].Z()])
            on_plane = abs(float(np.dot(q - c, n))) <= 1e-6 * max(1.0, np.linalg.norm(c))
            if on_plane and abs(abs(nv @ n) - 1) < 1e-6 and abs(ap.area(f) - o.area) <= 1e-3 * o.area:
                out.append({"opening": k + 1, "face": _gid_of(p, new, "FACE", f)})
                break
    return out


@command(
    "ENCLOSURE",
    Arg("what", Raw, "ALL", "the model: a body, several (\"3 7\" or names), SEL, or ALL (every shown body)"),
    Arg("shape", str, "BOX", "BOX, CYLINDER (along Z) or SPHERE"),
    Arg("margin", Raw, "10", "the space round the model: one number, or six \"-X +X -Y +Y -Z +Z\" (more "
                             "behind a part in a flow)"),
    help="The air round a model, for a flow or field model: ENCLOSURE, ALL, BOX, 20 puts a box 20 bigger on "
         "every side round the shown bodies, with them cut out, as a new solid. ENCLOSURE, car, BOX, \"50 200 "
         "50 50 0 50\" leaves more room behind. The answer names the outer faces (XMIN ... ZMAX, SIDE, TOP, "
         "BOTTOM, OUTER) and the walls of the model, by face ID",
)
def enclosure(p: Processor, what, shape, margin):
    from .handlers import _added

    m = p.model
    ids = wrap_targets(p, what, "ENCLOSURE")
    for i in ids:
        if mb.is_mesh(m.body(i).shape):
            raise CommandError(f"ENCLOSURE: body {i} is a mesh body; TOSOLID, {i} makes a solid of it first")
    try:
        ms = [float(p.evaluate(w)) for w in re.split(r"[\s;]+", str(margin).strip().strip('"')) if w]
    except Exception:  # noqa: BLE001
        raise CommandError("ENCLOSURE: the margin is a number, or six numbers \"-X +X -Y +Y -Z +Z\"") from None
    try:
        res, named, _outer = ap.enclosure([m.body(i).shape for i in ids], shape.upper(), ms or [10.0])
    except ap.PrepError as exc:
        raise CommandError(f"ENCLOSURE: {exc}") from None
    new = m.add_body(res, name=_free(m, "enclosure"))
    faces = {k: _gids(new, "FACE", v) for k, v in named.items()}
    for k, v in faces.items():  # named sets that go to STEP (PLAN item 95)
        if v:
            m.save_set(f"{new.name}_{k.lower()}", "FACE", v)
    d = {"bodies": ids, "shape": shape.upper(), "margins": ms, "new_body": new.id,
         "volume": round(robust.volume(res), 6), "faces": faces}
    p.give_report("ENCLOSURE", d)
    sides = "; ".join(f"{k} {', '.join(map(str, v))}" if k != "WALLS" else f"{len(v)} faces of the model"
                      for k, v in faces.items())
    return _added(p, new, f"ENCLOSURE {shape.upper()} round {len(ids)} bod{'y' if len(ids) == 1 else 'ies'} "
                          f"(volume {robust.volume(res):.6g}; faces: {sides}; saved as sets {new.name}_<side>)")


# ---- item 82 --------------------------------------------------------------------------------


def _pairs(p: Processor, ids: list[int]) -> list[tuple[int, int, float]]:
    """Pairs of the bodies that touch over an area: (a, b, area)."""
    from ..geometry import contact as ct

    m = p.model
    out = []
    boxes = {i: ct.box_of(m.body(i).shape) for i in ids}
    for k, a in enumerate(ids):
        for b in ids[k + 1:]:
            gap = 1e-6 * max(1.0, robust.diagonal(m.body(a).shape))
            if ct.boxes_apart(boxes[a], boxes[b], gap):
                continue
            ar = ap.touching_area(m.body(a).shape, m.body(b).shape)
            if ar > 1e-9:
                out.append((a, b, ar))
    return out


@command(
    "SHAREFACES",
    Arg("what", Raw, "ALL", "the parts: two or more bodies (\"3 7\" or names), SEL, or ALL"),
    Arg("how", str, "DO", "DO: split them where they touch so they use the same face there; CHECK: only list "
                          "the touching pairs and whether they share their faces yet (not kept)"),
    help="Parts that share faces, so the analysis app meshes them as one connected piece: SHAREFACES, ALL splits "
         "every pair of touching parts along the outline of their contact, so both use the very same face "
         "there (kept as one face in BREP; in STEP both get the same face, edge for edge). SHAREFACES, ALL, CHECK "
         "lists the touching pairs still apart. IMPRINT marks one part only",
)
def share(p: Processor, what, how):
    m = p.model
    if how not in ("DO", "CHECK"):
        raise CommandError("SHAREFACES: the last word is DO or CHECK")
    ids = wrap_targets(p, what, "SHAREFACES")
    for i in ids:
        _solid(p, "SHAREFACES", i)
    if len(ids) < 2:
        raise CommandError("SHAREFACES: give two or more bodies")
    pairs = _pairs(p, ids)
    rows = []
    for a, b, ar in pairs:
        sa, sb = m.body(a).shape, m.body(b).shape
        shared = ap.shared_area(sa, sb)
        match = ap.matching_area(sa, sb, 1e-6 * max(1.0, robust.diagonal(sa)))
        rows.append({"a": a, "b": b, "touching": round(ar, 6), "shared": round(shared, 6),
                     "matching": round(match, 6), "ok": match >= ar * (1 - 1e-6)})
    if how == "CHECK":
        apart = [r for r in rows if not r["ok"]]
        d = {"bodies": ids, "pairs": rows, "apart": len(apart)}
        p.give_report("SHAREFACES", d)
        if not rows:
            return f"SHAREFACES CHECK: none of the {len(ids)} bodies touch over an area"
        lines = [f"  {r['a']} and {r['b']}: touching {r['touching']:.5g}, "
                 + ("same faces" if r["ok"] else f"apart (matching {r['matching']:.5g})") for r in rows]
        head = (f"SHAREFACES CHECK: {len(rows)} touching pair{'s' if len(rows) != 1 else ''}, "
                + (f"{len(apart)} still apart; SHAREFACES, {what} splits them" if apart else "all share their faces"))
        return head + "\n" + "\n".join(lines)
    if not pairs:
        raise CommandError("SHAREFACES: none of these bodies touch over an area (CLASH lists overlaps, CONTACT gaps)")
    touched = sorted({x for a, b, _ in pairs for x in (a, b)})
    shapes = [m.body(i).shape for i in touched]
    try:
        out, maker = ap.share(shapes)
    except ap.PrepError as exc:
        raise CommandError(f"SHAREFACES: {exc}") from None
    before = {i: len(m.body(i).entity_ids["FACE"]) for i in touched}
    for i, s in zip(touched, out):
        m.replace([i], robust.unwrap(s), maker, same_id=True)
    split = {i: len(m.body(i).entity_ids["FACE"]) - before[i] for i in touched}
    total = sum(r["touching"] for r in rows)
    d = {"bodies": touched, "pairs": [{"a": a, "b": b, "touching": round(ar, 6)} for a, b, ar in pairs],
         "new_faces": split, "area": round(total, 6)}
    p.give_report("SHAREFACES", d)
    return (f"SHAREFACES: {len(pairs)} touching pair{'s' if len(pairs) != 1 else ''} now use the same faces (area "
            f"{total:.6g}); " + ", ".join(f"body {i} +{n} face{'s' if n != 1 else ''}" for i, n in split.items()))


REGISTRY["SHAREFACES"].query_word = "CHECK"


@command(
    "IMPRINT",
    Arg("a", BodyRef, help="the part whose faces are split"),
    Arg("b", BodyRef, help="the part that touches it (it stays as it is)"),
    help="Mark where another part touches this one: IMPRINT, plate, pad splits the plate's face along the "
         "pad's outline, so the contact patch is its own face (for a load or a fixed patch in the analysis "
         "app). SHAREFACES splits both parts",
)
def imprint(p: Processor, a, b):
    from .handlers import _added

    m = p.model
    if a == b:
        raise CommandError("IMPRINT: give two different bodies")
    sa, sb = _solid(p, "IMPRINT", a).shape, _solid(p, "IMPRINT", b).shape
    ar = ap.touching_area(sa, sb)
    if ar <= 1e-9:
        raise CommandError(f"IMPRINT: bodies {a} and {b} do not touch over an area")
    out, maker = ap.share([sa, sb])
    before = len(m.body(a).entity_ids["FACE"])
    new = m.replace([a], robust.unwrap(out[0]), maker, same_id=True)
    patch = [_gid_of(p, new, "FACE", f) for f, _ in _touching_faces(new.shape, out[1])]
    d = {"a": a, "b": b, "area": round(ar, 6), "faces": patch}
    p.give_report("IMPRINT", d)
    return _added(p, new, f"IMPRINT of body {b} on body {a}: contact area {ar:.6g} on face"
                          f"{'s' if len(patch) != 1 else ''} {', '.join(map(str, patch))} "
                          f"(+{len(new.entity_ids['FACE']) - before} faces)")


def _touching_faces(a, b):
    from OCP.TopAbs import TopAbs_FACE

    fa = ap._explore(a, TopAbs_FACE)
    return [(fa[i], j) for i, j in ap.shared_faces(a, b)]


@command(
    "MERGEFACES",
    Arg("b", BodyRef, help="a solid"),
    Arg("what", str, "SAME", "SAME: join neighbouring faces on the same surface; SMALL: also remove faces "
                             "narrower than the size (the slivers CHECK, b, FLAWS lists)"),
    Arg("size", float, 0.0, "for SMALL: faces narrower than this go (0: a hundredth of the body's size)"),
    help="Fewer, cleaner faces for meshing: MERGEFACES, part joins faces that lie on one surface (seams left "
         "by booleans and imports); MERGEFACES, part, SMALL, 0.5 also removes sliver faces under 0.5 wide, the "
         "faces round them growing to close the gap. Says what is left",
)
def mergefaces(p: Processor, b, what, size):
    from ..geometry import direct as de
    from ..geometry import healing
    from .handlers import _added

    m = p.model
    if what not in ("SAME", "SMALL"):
        raise CommandError("MERGEFACES: the second word is SAME or SMALL")
    if size < 0:
        raise CommandError("MERGEFACES: the size cannot be negative")
    body = _solid(p, "MERGEFACES", b)
    n0 = len(body.entity_ids["FACE"])
    shape, maker, joined = robust.merge_faces(body.shape)
    if joined:
        body = m.replace([b], shape, maker, same_id=True)
    removed, kept = 0, []
    if what == "SMALL":
        tol = size or 0.01 * robust.diagonal(body.shape)
        f = healing.inspect(body.shape, tol)
        idx = [i for i, _w in f.slivers]
        if idx:
            faces = [body.maps["FACE"].FindKey(i + 1) for i in idx]
            try:
                s2, mk2 = de.delete_faces(body.shape, faces)
            except de.DirectError:
                s2 = None
            if s2 is not None and not robust.is_empty(s2) and robust.is_valid(s2):
                body = m.replace([b], robust.unwrap(s2), mk2, same_id=True)
                removed = len(idx)
            else:  # one at a time: keep the ones that work
                for gid in _gids(body, "FACE", idx):
                    try:
                        cur = m.body(b)
                        s3, mk3 = de.delete_faces(cur.shape, [m.entity_shape("FACE", gid)])
                    except Exception:  # noqa: BLE001
                        kept.append(gid)
                        continue
                    if robust.is_empty(s3) or not robust.is_valid(s3):
                        kept.append(gid)
                        continue
                    m.replace([b], robust.unwrap(s3), mk3, same_id=True)
                    removed += 1
        body = m.body(b)
        left = healing.inspect(body.shape, tol)
        kept = _gids(body, "FACE", [i for i, _ in left.slivers])
    n1 = len(body.entity_ids["FACE"])
    d = {"body": b, "faces_before": n0, "faces_after": n1, "joined": joined, "removed": removed, "left": kept}
    p.give_report("MERGEFACES", d)
    if not joined and not removed:
        return (f"MERGEFACES: nothing to merge on body {b} ({n0} faces)"
                + (f"; slivers {', '.join(map(str, kept))} could not be removed (DELFACE, or HEAL)" if kept else ""))
    words = [f"{joined} joined"] if joined else []
    if removed:
        words.append(f"{removed} sliver{'s' if removed != 1 else ''} removed")
    msg = f"MERGEFACES body {b}: {n0} -> {n1} faces ({', '.join(words)})"
    if kept:
        msg += f"; slivers {', '.join(map(str, kept))} are left (DELFACE them, or HEAL)"
    return _added(p, body, msg)


# ---- item 99 ---------------------------------------------------------------------------------


@command(
    "SPOTWELD",
    Arg("a", BodyRef, help="one part (a sheet metal part, a plate, or a middle surface)"),
    Arg("b", BodyRef, help="the part it is welded to"),
    Arg("edge", int, help="the edge the welds run along (a flange's edge, or the line where the parts lap)"),
    Arg("pitch", float, help="the distance from one weld to the next"),
    Arg("margin", float, 0.0, "the least distance from the ends of the edge (0: half the pitch)"),
    Arg("dia", float, 5.0, "the weld nugget's diameter, kept with the points for the analysis app"),
    help="Spot welds along an edge: SPOTWELD, lid, box, 12, 25. Points are laid out every pitch along the edge, "
         "centred on it, and each is moved halfway between the two parts there. They become one body of points "
         "(spotwelds) and a named set; EXPORT, STEP writes each point with its name, the two parts and the "
         "nugget size, for the analysis app to make its connectors.",
)
def spotweld(p: Processor, a, b, edge, pitch, margin, dia):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.gp import gp_Pnt

    from .handlers import _added

    m = p.model
    if a == b:
        raise CommandError("SPOTWELD: give two different parts")
    if pitch <= 0 or dia <= 0 or margin < 0:
        raise CommandError("SPOTWELD: the pitch and the diameter must be more than 0, and the end distance not "
                           "below 0")
    try:
        es = m.entity_shape("EDGE", edge)
    except Exception:  # noqa: BLE001 - an unknown ID
        raise CommandError(f"SPOTWELD: there is no edge {edge}") from None
    ba, bb = m.body(a), m.body(b)
    for x in (ba, bb):
        if mb.is_mesh(x.shape):
            raise CommandError(f"SPOTWELD: body {x.id} is a mesh body; TOSOLID, {x.id} makes a solid of it first")
    try:
        spots = ap.spot_welds(es, ba.shape, bb.shape, pitch, margin or pitch / 2)
    except ap.PrepError as exc:
        raise CommandError(f"SPOTWELD: {exc}") from None
    reach = max(dia, 0.02 * min(robust.diagonal(ba.shape), robust.diagonal(bb.shape)))
    if all(s.gap > reach for s in spots):
        raise CommandError(f"SPOTWELD: bodies {a} and {b} are not close along edge {edge} (they are "
                           f"{_t(min(s.gap for s in spots))} apart at best); pick an edge where they lap")
    far = [k + 1 for k, s in enumerate(spots) if s.gap > reach]
    if far:
        p.warn(f"SPOTWELD: at weld{'s' if len(far) != 1 else ''} {', '.join(map(str, far))} the parts are more "
               f"than {_t(reach)} apart")
    shape = ap._compound([BRepBuilderAPI_MakeVertex(gp_Pnt(*s.at)).Vertex() for s in spots])
    new = m.add_body(shape, name=_free(m, "spotwelds"))
    na = ba.name if ba.name != f"body{a}" else f"body {a}"
    nb = bb.name if bb.name != f"body{b}" else f"body {b}"
    m.spotwelds[new.id] = {"a": a, "b": b, "a_name": na, "b_name": nb, "edge": edge, "pitch": pitch,
                           "diameter": dia}
    set_name = new.name
    ids = list(new.entity_ids["VERTEX"])
    m.save_set(set_name, "VERTEX", ids)
    r6 = lambda v: [round(c, 6) + 0.0 for c in v]  # noqa: E731
    d = {"a": a, "b": b, "edge": edge, "pitch": pitch, "diameter": dia, "new_body": new.id, "set": set_name,
         "count": len(spots),
         "welds": [{"n": k + 1, "point": gid, "at": r6(s.at), "gap": round(s.gap, 6)}
                   for k, (gid, s) in enumerate(zip(ids, spots))]}
    p.give_report("SPOTWELD", d)
    return _added(p, new, f"SPOTWELD: {len(spots)} weld{'s' if len(spots) != 1 else ''} joining {na} and {nb} "
                          f"along edge {edge}, {_t(pitch)} apart, nugget {_t(dia)} (set {set_name})")
