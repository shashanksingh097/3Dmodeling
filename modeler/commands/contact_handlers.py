"""Do parts touch? CONTACT and CLEARANCE.

Both only read the model (they are not in the history). The same answers are
in expressions (TOUCH, OVERLAP, CONTACTAREA, GROUPS, CLEARANCE), so a script can
ASSERT them, and in the assistant's tools.
"""

from __future__ import annotations

import json

from .processor import REGISTRY, Arg, CommandError, Processor, Raw, command


def _n(v) -> str:
    return f"{v:g}"


def _p3(v) -> str:
    return "(" + ", ".join(_n(x) for x in v) + ")"


def _name(row) -> str:
    return f"{row['id']} ({row['name']})" if row.get("name") else str(row["id"])


def pair_text(r: dict) -> str:
    a, b = _name(r["a"]), _name(r["b"])
    if r["state"] == "apart":
        return (f"bodies {a} and {b} are apart: gap {_n(r['gap'])} from {_p3(r['from'])} to {_p3(r['to'])} "
                f"(faces {r['faces_a']} and {r['faces_b']})")
    if r["state"] == "touch":
        how = {"face": f"on faces, area {_n(r.get('area', 0))}",
               "line": f"along a line, length {_n(r.get('length', 0))}",
               "point": f"at a point {_p3(r['at'])}"}[r["touch"]]
        return f"bodies {a} and {b} touch {how} (faces {r['faces_a']} and {r['faces_b']})"
    bx = r["overlap_box"]
    return (f"bodies {a} and {b} OVERLAP: {_n(r['volume'])} in common "
            f"({_n(100 * r['fraction_of_smaller'])}% of the smaller), overlap box {_p3(bx['size'])} "
            f"from {_p3(bx['min'])} to {_p3(bx['max'])}")


@command(
    "CONTACT",
    Arg("a", Raw, "", help="a body; left out: every pair of shown bodies"),
    Arg("b", Raw, "", help="a second body; left out: body a against every other shown body"),
    Arg("tol", float, 0.0, help="closer than this counts as touching (0: a millionth of the size)"),
    Arg("near", float, 0.0, help="also list pairs whose gap is at most this"),
    Arg("fmt", str, "TEXT", help="TEXT or JSON"),
    logged=False,
    help=(
        "Do parts touch? CONTACT, a, b says apart (the gap and where), touching (on faces with the area, "
        "along a line, or at a point) or overlapping (the volume in common) · CONTACT, bolt checks one "
        "body against all others · CONTACT alone checks every pair and lists the groups of bodies that "
        "hold together and the ones touching nothing · CONTACT, , , 0, 0.5 also lists gaps up to 0.5. "
        "In expressions: TOUCH(a, b), OVERLAP(a, b), CONTACTAREA(a, b), GROUPS()"
    ),
)
def contact_cmd(p: Processor, a, b, tol, near, fmt):
    from ..ai import contact as cx
    from ..ai import describe as ds

    a, b = a.strip(), b.strip()
    if tol < 0 or near < 0:
        raise CommandError("CONTACT: tol and near cannot be negative")
    try:
        if a and b:
            out = cx.contact(p, a, b, tol)
            return json.dumps(out, separators=(",", ":")) if fmt == "JSON" else pair_text(out)
        if b and not a:
            raise CommandError("CONTACT: give the first body too")
        out = cx.assembly(p, None, a or None, tol, near)
    except ds.DescribeError as exc:
        raise CommandError(f"CONTACT: {exc}") from None
    if fmt == "JSON":
        return json.dumps(out, separators=(",", ":"))
    lines = [pair_text(r) for r in out["overlaps"] + out["touching"] + out.get("near", [])]
    if a and not lines:
        lines.append(f"body {a} touches nothing")
    if not a and 1 < len(out["groups"]) <= 10:
        for g in out["groups"]:
            lines.append(f"group: {', '.join(map(str, g))}")
    lines.append(f"{out['bodies']} bodies, {out['pairs']} pairs: {out['summary']}")
    if "stopped" in out:
        lines.append("stopped: " + out["stopped"])
    return "\n".join(lines)


@command(
    "CLEARANCE",
    Arg("a", Raw, help="a body"),
    Arg("b", Raw, help="the other body"),
    Arg("fmt", str, "TEXT", help="TEXT or JSON"),
    logged=False,
    help=(
        "How shafts sit in holes: CLEARANCE, bolt, plate finds every round shaft of one body inside a round hole "
        "of the other and gives both diameters, the clearance (negative: interference), how far the axes are "
        "off and the engaged length; a screw thread is named as one. CLEARANCE(a, b) is the tightest gap: ASSERT, CLEARANCE(pin, plate), GE, 0.05"
    ),
)
def fit_cmd(p: Processor, a, b, fmt):
    from ..ai import contact as cx
    from ..ai import describe as ds

    try:
        out = cx.fit(p, a.strip(), b.strip())
    except ds.DescribeError as exc:
        raise CommandError(f"CLEARANCE: {exc}") from None
    if fmt == "JSON":
        return json.dumps(out, separators=(",", ":"))
    if not out["fits"]:
        return f"bodies {_name(out['a'])} and {_name(out['b'])}: {out['note']}"
    lines = []
    for r in out["fits"]:
        s, h = r["shaft"], r["hole"]
        if r["state"] == "thread":
            lines.append(f"thread of body {s['body']} (crests d {_n(s['d'])}) in the thread of body {h['body']} "
                         f"(crests d {_n(h['d'])}), engaged {_n(r['engaged'])}; CONTACT says whether they clash")
            continue
        text = (f"shaft d {_n(s['d'])} of body {s['body']} in hole d {_n(h['d'])} of body {h['body']}: "
                f"{r['state']}, clearance {_n(r['clearance'])} ({_n(r['per_side'])} a side)")
        if r["axis_offset"]:
            text += f", axes {_n(r['axis_offset'])} apart (tightest gap {_n(r['tightest_gap'])})"
        if r.get("tilt_deg"):
            text += f", tilted {_n(r['tilt_deg'])} deg"
        lines.append(text + f", engaged {_n(r['engaged'])}")
    return "\n".join(lines)


# ---- placement, design rules, same shape -------------------------------------------------------


@command(
    "RELATE",
    Arg("a", Raw, help="a body"),
    Arg("b", Raw, help="the body to compare its place with"),
    Arg("fmt", str, "TEXT", help="TEXT or JSON"),
    logged=False,
    help=(
        "Where a body sits relative to another: RELATE, lid, box gives, along X, Y and Z, on which side "
        "and how far, or within, around or overlapping; how far their centres are apart and on which axes "
        "they are centred; what it rests on; flat faces that are flush; round faces on the same axis"
    ),
)
def relate_cmd(p: Processor, a, b, fmt):
    from ..ai import describe as ds
    from ..ai import relate as rl

    try:
        out = rl.placement(p, a.strip(), b.strip())
    except ds.DescribeError as exc:
        raise CommandError(f"RELATE: {exc}") from None
    if fmt == "JSON":
        return json.dumps(out, separators=(",", ":"))
    lines = [f"body {_name(out['a'])} relative to body {_name(out['b'])}:"]
    for ax, r in out["axes"].items():
        how = r["a_is"].replace("- side", f"-{ax} side").replace("+ side", f"+{ax} side")
        extra = f", gap {_n(r['gap'])}" if "gap" in r else f", overlap {_n(r['overlap'])}"
        lines.append(f"  {ax}: {how}{extra}")
    lines.append(f"  centres {_p3(out['centre_offset'])} apart"
                 + (f"; centred on {', '.join(out['centred_on'])}" if out["centred_on"] else ""))
    if "contact" in out:
        lines.append(f"  contact: {out['contact']}")
    for r in out.get("rests", []):
        lines.append(f"  {r}")
    if out.get("flush"):
        lines.append(f"  flush faces: " + ", ".join(f"{f['face_a']} with {f['face_b']}" for f in out["flush"][:10]))
    for c in out.get("coaxial", [])[:10]:
        kinds = ["hole" if c["a_hole"] else "shaft", "hole" if c["b_hole"] else "shaft"]
        lines.append(f"  on one axis {_p3(c['axis'])}: {kinds[0]} d {_n(c['d_a'])} and {kinds[1]} d {_n(c['d_b'])}")
    return "\n".join(lines)


@command(
    "DESIGNCHECK",
    Arg("b", Raw, help="the body"),
    Arg("minwall", float, 0.0, help="also report walls thinner than this"),
    Arg("minedge", float, 0.0, help="edges shorter and faces narrower than this (0: a thousandth of the size)"),
    Arg("fmt", str, "TEXT", help="TEXT or JSON"),
    logged=False,
    help=(
        "Rule checks on a body, each problem with IDs: broken or open, not a solid, loose pieces, tiny edges, "
        "sliver faces, faces cutting through each other, and with minwall thin walls: DESIGNCHECK, housing, 2. "
        "Each problem has a severity (ERROR or WARNING), the value measured and the limit it breaks, and a "
        "fix, tried on a copy of the model to say whether it works. "
        "PROBLEMS(b) counts them: ASSERT, PROBLEMS(housing), EQ, 0"
    ),
)
def designcheck_cmd(p: Processor, b, minwall, minedge, fmt):
    from ..ai import describe as ds
    from ..ai import relate as rl

    if minwall < 0 or minedge < 0:
        raise CommandError("DESIGNCHECK: minwall and minedge cannot be negative")
    try:
        out = rl.design_check(p, b.strip(), minwall, minedge)
    except ds.DescribeError as exc:
        raise CommandError(f"DESIGNCHECK: {exc}") from None
    if fmt == "JSON":
        return json.dumps(out, separators=(",", ":"))
    head = f"body {_name(out['body'])}: "
    if out["ok"]:
        return head + "no problems (" + ", ".join(out["checked"]) + ")"
    n = len(out["problems"])
    lines = [head + f"{n} problem{'s' if n != 1 else ''} ({out['errors']} error{'s' if out['errors'] != 1 else ''}, "
             f"{out['warnings']} warning{'s' if out['warnings'] != 1 else ''})"]
    for pr in out["problems"]:
        ids = pr.get("edges") or pr.get("faces")
        lines.append(f"  {pr['severity'].upper()} {pr['rule']}: {pr['message']}"
                     + (f" ({'edges' if 'edges' in pr else 'faces'} {ids})" if ids else ""))
        lines.append(f"      measured {_v(pr['measured'])}, limit {_v(pr['limit'])}; fix: {pr['fix']}"
                     + (f" ({pr['fix_checked']} on a copy)" if pr["fix_checked"] != "not tried" else ""))
    return "\n".join(lines)


def _v(x) -> str:
    return f"{x:g}" if isinstance(x, float) else str(x)


@command(
    "COMPARE",
    Arg("a", Raw, help="a body; or STEP or PROJECT to compare revisions"),
    Arg("b", Raw, help="the other body; or the history position (STEP) or project file (PROJECT)"),
    Arg("fmt", Raw, "TEXT", help="TEXT or JSON; for revisions: the body to compare (default: all)"),
    Arg("c", Raw, "", help="for revisions: the tolerance (default: a thousandth of the size)"),
    Arg("d", Raw, "", help="for revisions: TEXT or JSON"),
    logged=False,
    help=(
        "Are two bodies the same shape? COMPARE, left, right compares volume, area, faces and inertia and "
        "says whether b is a moved copy or a mirror image of a, or what differs. SAMESHAPE(a, b) is 1 or 0 · "
        "Revisions: COMPARE, STEP, 5 [, body [, tol [, JSON]]] compares the model as it was after step 5 with "
        "now, COMPARE, PROJECT, \"old.m3d\" a saved project with now: faces added, removed, moved and changed, "
        "how far the surface moved, and the changed body coloured by distance"
    ),
)
def compare_cmd(p: Processor, a, b, fmt, c, d):
    from ..ai import describe as ds
    from ..ai import relate as rl

    if a.strip().upper() in ("STEP", "PROJECT"):
        return _compare_revisions(p, a.strip().upper(), b.strip(), fmt.strip(), c.strip(), d.strip())
    fmt = fmt.strip().upper() or "TEXT"

    try:
        out = rl.compare(p, a.strip(), b.strip())
    except ds.DescribeError as exc:
        raise CommandError(f"COMPARE: {exc}") from None
    if fmt == "JSON":
        return json.dumps(out, separators=(",", ":"))
    head = f"bodies {_name(out['a'])} and {_name(out['b'])}: "
    if out["same"]:
        if out["how"] == "moved copy":
            return head + f"the same shape, moved by {_p3(out['move'])}"
        if out["how"] == "mirror image":
            text = head + f"mirror images across the plane {out['mirror_normal'].lower()} = {_n(out['plane_at'])}"
            return text + (f", then moved {_p3(out['then_moved'])}" if "then_moved" in out else "")
        return head + out["how"]
    lines = [head + "not the same shape"]
    for k, d in out["differs"].items():
        if k == "faces":
            lines.append(f"  faces: {d['a']} against {d['b']}")
        elif k == "inertia":
            lines.append(f"  inertia: {d['a']} against {d['b']}")
        else:
            lines.append(f"  {k}: {_n(d['a'])} against {_n(d['b'])} (b - a = {_n(d['b_minus_a'])})")
    return "\n".join(lines)


# ---- COMPARE, STEP / PROJECT: two revisions of the model --------------------------------------------
def _old_bodies(p: Processor, how: str, ref: str) -> tuple[dict, str]:
    """The bodies of the other revision, and how to name it."""
    if how == "STEP":
        try:
            n = int(p.evaluate(ref))
        except Exception:  # noqa: BLE001
            raise CommandError("COMPARE, STEP: give a history position (0 is the empty start)") from None
        if not 0 <= n <= p.cursor:
            raise CommandError(f"COMPARE, STEP: positions go from 0 (the empty start) to {p.cursor} (now)")
        return dict(p._snaps[n]["model"]["bodies"]), f"step {n}"
    path = ref[1:-1] if len(ref) >= 2 and ref[0] in "\"'" and ref[-1] == ref[0] else ref
    path = p.file_map.get(path, path)
    import os

    if not os.path.isfile(path):
        raise CommandError(f"COMPARE, PROJECT: no such file: {path}")
    other = Processor()
    res = other.run(f'OPEN, "{path}"')
    if not res.ok:
        raise CommandError(f"COMPARE, PROJECT: {res.message}")
    return dict(other.model.bodies), os.path.basename(path)


def _compare_revisions(p: Processor, how: str, ref: str, body: str, tol: str, fmt: str) -> str:
    from ..geometry import meshbody as mb
    from ..geometry import revdiff as rd
    from ..geometry import robust
    from .analysis_handlers import Analysis

    if body.upper() in ("TEXT", "JSON"):  # COMPARE, STEP, 5, JSON: the format, no body
        body, fmt = "", fmt or body
    fmt = (fmt or "TEXT").upper()
    if fmt not in ("TEXT", "JSON"):
        raise CommandError("COMPARE: the format is TEXT or JSON")
    old, label = _old_bodies(p, how, ref)
    new = dict(p.model.bodies)
    if body:
        bid = p._body_arg(REGISTRY["COMPARE"], body)
        nb = new[bid]
        match = old.get(bid) if bid in old and old[bid].name == nb.name else next(
            (x for x in old.values() if x.name == nb.name), old.get(bid))
        pairs = [(match, nb)]
    else:
        pairs = []
        used = set()
        for nb in new.values():
            ob = next((x for x in old.values() if x.name == nb.name and x.id not in used), None)
            if ob is None and nb.id in old and nb.id not in used and old[nb.id].name.startswith("body"):
                ob = old[nb.id]
            if ob is not None:
                used.add(ob.id)
            pairs.append((ob, nb))
        pairs += [(ob, None) for ob in old.values() if ob.id not in used]
    try:
        tol_v = float(p.evaluate(tol)) if tol else 0.0
    except Exception:  # noqa: BLE001
        raise CommandError("COMPARE: the tolerance is a number") from None
    if tol_v < 0:
        raise CommandError("COMPARE: the tolerance cannot be negative")
    rows, lines, colour = [], [], None
    for ob, nb in pairs:
        if nb is None:
            rows.append({"old": ob.id, "new": None, "name": ob.name, "removed_body": True})
            lines.append(f"- body {ob.id} '{ob.name}': only in {label}")
            continue
        if ob is None:
            rows.append({"old": None, "new": nb.id, "name": nb.name, "added_body": True})
            lines.append(f"+ body {nb.id} '{nb.name}': new since {label}")
            continue
        if ob.shape is nb.shape:
            rows.append({"old": ob.id, "new": nb.id, "name": nb.name, "same": True})
            continue
        if mb.is_mesh(ob.shape) or mb.is_mesh(nb.shape):
            rows.append({"old": ob.id, "new": nb.id, "name": nb.name, "mesh": True})
            lines.append(f"~ body {nb.id} '{nb.name}': a mesh body; DEVIATION measures meshes")
            continue
        t = tol_v or 1e-3 * max(robust.diagonal(nb.shape), 1e-9)
        dd = rd.compare_body(ob.shape, nb.shape, ob.entity_ids.get("FACE"), nb.entity_ids.get("FACE"), t)
        dd.old_id, dd.new_id, dd.name = ob.id, nb.id, nb.name
        rows.append(dd.as_dict())
        if dd.same:
            continue
        head = f"~ body {nb.id} '{nb.name}'"
        if dd.volume:
            v0, v1 = dd.volume
            head += f": volume {v0:.6g} -> {v1:.6g} ({v1 - v0:+.4g})"
        lines.append(head)
        lines.append(f"    {dd.unchanged} faces the same; {len(dd.changed)} changed, {len(dd.moved)} moved, "
                     f"{len(dd.added)} added, {len(dd.removed)} removed")
        for r in dd.changed[:8]:
            extra = (f", radius {r['radius_was']:.4g} -> {r['radius']:.4g}" if "radius" in r else "")
            lines.append(f"    changed: face {r['face']} ({r['type']}, was {r['was']}): area {r['area_was']:.4g} -> "
                         f"{r['area']:.4g}{extra}")
        for r in dd.moved[:8]:
            lines.append(f"    moved: face {r['face']} ({r['type']}, was {r['was']}) by {_p3(r['by'])}")
        for r in dd.added[:8]:
            lines.append(f"    added: face {r['face']} ({r['type']}, area {r['area']:.4g}) at {_p3(r['at'])}")
        for r in dd.removed[:8]:
            lines.append(f"    removed: face {r['face']} of {label} ({r['type']}, area {r['area']:.4g}) at {_p3(r['at'])}")
        if dd.regions:
            lines.append(f"    the surface moved by up to {dd.largest_out:+.4g} / {dd.largest_in:+.4g}; "
                         f"{100 * dd.off:.1f}% of it by more than {t:.3g}")
        if colour is None:
            colour = (nb.id, ob.shape, t)
    if not lines:
        lines.append(f"no differences from {label}")
    else:
        lines.insert(0, f"COMPARE {label} with now:")
    if colour is not None:
        from ..geometry import deviation as dv

        bid, old_shape, t = colour
        tg = dv.target(old_shape, min(t / 4, robust.diagonal(old_shape) / 1000))
        p.analysis = Analysis(bid, "DEVIATION", (0.0, 0.0, 1.0), 0.0, field=dv.Field(tg), scale=t)
        hook = getattr(p.view, "show_analysis", None) if p.view else None
        if hook:
            hook(p.analysis)
        lines.append(f"  body {bid} is coloured by how far it moved: green the same, red outward, blue inward "
                     "(ANALYZE, OFF ends it)")
    if fmt == "JSON":
        return json.dumps({"against": label, "bodies": rows}, separators=(",", ":"))
    return "\n".join(lines)
