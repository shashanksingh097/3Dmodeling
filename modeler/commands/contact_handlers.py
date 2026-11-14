"""Do parts touch? CONTACT and CLEARANCE.

Both only read the model (they are not in the history). The same answers are
in expressions (TOUCH, OVERLAP, CONTACTAREA, GROUPS, CLEARANCE), so a script can
ASSERT them, and in the assistant's tools.
"""

from __future__ import annotations

import json

from .processor import Arg, CommandError, Processor, Raw, command


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
    if not a and len(out["groups"]) > 1:
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
