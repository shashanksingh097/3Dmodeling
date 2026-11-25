"""Change a value without breaking the steps built on it.

Changing a number in an early step (HIST, EDIT) runs every later step again.
Most follow; a step that picked a face or an edge the change took away fails.
This module looks before the change is made:

* ``impact(p, n, text)`` runs the edit on a copy of the model (ai/sandbox.py)
  and says which later steps would fail that work now.
* ``direct(p, n, text)`` finds the same change made on the finished model
  instead, as ordinary steps added at the end (the faces the step made, picked
  and pushed or pulled; or the body moved), so nothing built on it breaks. The
  candidate is tried on a copy too and kept only when it changes the volume and
  the size of the model the way the edited step changes its own result.

``EDITCHECK, n, "text"`` reports both, as text and data, for the window's
"this change breaks later steps" question and for the assistant.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..lang.expr import fmt_num
from ..lang.script import Cmd, ScriptError, parse
from .processor import Arg, CommandError, Text, command

if TYPE_CHECKING:
    from .processor import Processor

VOL_TOL = 0.1  # how near the direct change's volume change must come to the step's (relative; later holes and cuts
# take some away), with the same sign
BOX_TOL = 0.02  # and its change of size, relative to the model's size


def _sandbox(p: Processor):
    from ..ai.sandbox import Sandbox

    return Sandbox(p).p


def impact(p: Processor, n: int, text: str) -> dict:
    """What ``HIST, EDIT, n, text`` would do: {"ok": the step itself works, "breaks": [later steps that
    would fail and work now], "message": the step's own error when it fails}."""
    q = _sandbox(p)
    q.skip_unchanged = p.skip_unchanged
    was = {e.uid: e.ok for e in p.history[:p.cursor]}
    try:
        q.edit_entry(n, text)
    except CommandError as exc:
        return {"ok": False, "breaks": [], "message": str(exc), "sandbox": q}
    e = q.history[n - 1]
    breaks = [{"n": j + 1, "label": x.label, "message": x.message.split("\n")[0]}
              for j, x in enumerate(q.history[:q.cursor]) if j >= n and not x.ok and was.get(x.uid, False)]
    return {"ok": e.ok, "message": "" if e.ok else e.message, "breaks": breaks, "sandbox": q}


# ---- the direct change --------------------------------------------------------
def _measure(state_model: dict, bids) -> tuple[float, tuple | None]:
    from ..geometry import robust
    from .queries import bbox

    vol, box = 0.0, None
    for b in bids:
        body = state_model["bodies"].get(b)
        if body is None:
            continue
        try:
            vol += robust.volume(body.shape)
            bb = bbox(body.shape)
        except Exception:  # noqa: BLE001 - a body with no volume (a sketch, a wire) adds nothing
            continue
        box = bb if box is None else tuple(min(box[i], bb[i]) for i in range(3)) + tuple(
            max(box[i], bb[i]) for i in range(3, 6))
    return vol, box


def _step_change(p: Processor, q: Processor, i: int) -> tuple[float, tuple] | None:
    """How step i (0-based) changes its own result in the edited copy q: (volume change, box change)."""
    e_old, e_new = p.history[i], q.history[i]
    if not e_new.ok or e_old.lineage is None or e_new.lineage is None:
        return None
    bids = set(e_old.lineage.made) | set(e_new.lineage.made)
    if not bids:
        return None
    v0, b0 = _measure(p._snaps[i + 1]["model"], bids)
    v1, b1 = _measure(q._snaps[i + 1]["model"], bids)
    if b0 is None or b1 is None:
        return None
    return v1 - v0, tuple(b1[k] - b0[k] for k in range(6))


def _numbers_changed(p: Processor, i: int, old: str, new: str) -> list[tuple[int, float, float]] | None:
    """The arguments of one command whose values differ: [(place, old, new)], or None when the step
    is not one plain command with the same name and only numbers changed."""
    try:
        a, b = parse(old), parse(new)
    except ScriptError:
        return None
    if len(a) != 1 or len(b) != 1 or not isinstance(a[0], Cmd) or not isinstance(b[0], Cmd):
        return None
    if a[0].name != b[0].name:
        return None
    xa, xb = list(a[0].args), list(b[0].args)
    xa += [""] * (len(xb) - len(xa))
    xb += [""] * (len(xa) - len(xb))
    saved = p.params
    p.params = dict(p._snaps[i]["params"])
    out = []
    try:
        for k, (s, t) in enumerate(zip(xa, xb)):
            if s.strip() == t.strip():
                continue
            try:
                u, v = p.evaluate(s or "0"), p.evaluate(t or "0")
            except Exception:  # noqa: BLE001 - a word or a body changed: not a number
                return None
            if not isinstance(u, (int, float)) or not isinstance(v, (int, float)):
                return None
            out.append((k, float(u), float(v)))
    finally:
        p.params = saved
    return out


def _face_groups(p: Processor, uid: int) -> list[list[int]]:
    """The faces of the finished model that step ``uid`` made, grouped: flat faces by plane, round
    faces by axis and radius."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus
    from OCP.TopoDS import TopoDS

    as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
    m = p.model
    groups: dict[tuple, list[int]] = {}
    for b, body in m.bodies.items():
        for fid in body.entity_ids.get("FACE", []):
            if m.origin("FACE", fid) != uid:
                continue
            try:
                s = BRepAdaptor_Surface(as_face(m.entity_shape("FACE", fid)))
            except Exception:  # noqa: BLE001
                continue
            t = s.GetType()
            r = lambda v: round(v, 4)  # noqa: E731
            if t == GeomAbs_Plane:
                pl = s.Plane()
                d, o = pl.Axis().Direction(), pl.Location()
                nx, ny, nz = d.X(), d.Y(), d.Z()
                if (nx, ny, nz) < (0, 0, 0):
                    nx, ny, nz = -nx, -ny, -nz
                key = (b, "P", r(nx), r(ny), r(nz), r(nx * o.X() + ny * o.Y() + nz * o.Z()))
            elif t == GeomAbs_Cylinder:
                c = s.Cylinder()
                ax = c.Axis().Direction()
                key = (b, "C", r(abs(ax.X())), r(abs(ax.Y())), r(abs(ax.Z())), r(c.Radius()))
            elif t in (GeomAbs_Torus, GeomAbs_Sphere, GeomAbs_Cone):
                key = (b, int(t))
            else:
                continue
            groups.setdefault(key, []).append(fid)
    return list(groups.values())


def _body_of_step(p: Processor, i: int) -> list[int]:
    """The bodies of the finished model that come only from what step i made (following later
    steps). A body that a later step joined with others, or cut with them, is left out: moving it
    would move them too."""
    e = p.history[i]
    if e.lineage is None:
        return []
    live = set(e.lineage.made)
    mixed: set[int] = set()
    for x in p.history[i + 1:p.cursor]:
        if x.lineage is None:
            continue
        for made, ins in x.lineage.inputs.items():
            if ins & live:
                live.add(made)
                if ins - live or ins & mixed:
                    mixed.add(made)
    return sorted(b for b in live - mixed if b in p.model.bodies)


def _candidates(p: Processor, i: int, changed: list[tuple[int, float, float]], step: tuple) -> list[str]:
    """Scripts to try, most likely first."""
    dv, db = step
    out = []
    moved = [(db[k] + db[k + 3]) / 2 for k in range(3)]
    if abs(dv) < 1e-9 and any(abs(c) > 1e-9 for c in moved):  # the step's result only moved
        for b in _body_of_step(p, i):
            out.append(f"MOVE, {b}, {', '.join(fmt_num(round(c, 9)) for c in moved)}")
    deltas = []
    for _, u, v in changed:
        dd = v - u
        deltas += [dd, -dd, dd / 2, -dd / 2]
    seen = set()
    deltas = [d for d in deltas if abs(d) > 1e-12 and not (round(d, 12) in seen or seen.add(round(d, 12)))]
    for faces in _face_groups(p, p.history[i].uid):
        for d in deltas:
            out.append(f"PICK, FACE, {' '.join(map(str, faces))}\nPUSHPULL, {fmt_num(round(d, 9))}")
    return out


def _matches(p: Processor, q: Processor, step: tuple) -> bool:
    dv, db = step
    v0, b0 = _measure(p._state()["model"], p.model.bodies)
    v1, b1 = _measure(q._state()["model"], q.model.bodies)
    if b0 is None or b1 is None:
        return False
    size = max(1e-6, max(b0[k + 3] - b0[k] for k in range(3)))
    if dv * (v1 - v0) < 0 or abs((v1 - v0) - dv) > VOL_TOL * max(abs(dv), 1e-3 * abs(v0), 1e-9):
        return False
    return all(abs((b1[k] - b0[k]) - db[k]) <= BOX_TOL * size for k in range(6))


def direct(p: Processor, n: int, text: str, found: dict | None = None) -> str | None:
    """Steps that make the change of ``HIST, EDIT, n, text`` on the finished model instead (None: none found)."""
    i = n - 1
    if not 0 <= i < p.cursor:
        return None
    changed = _numbers_changed(p, i, p.history[i].text, text)
    if not changed:
        return None
    found = found or impact(p, n, text)
    if not found.get("ok"):
        return None
    step = _step_change(p, found["sandbox"], i)
    if step is None:
        return None
    from ..ai.sandbox import Sandbox

    for script in _candidates(p, i, changed, step)[:40]:
        box = Sandbox(p)
        r = box.run(script)
        if r["ok"] and _matches(p, box.p, step):
            return script
    return None


@command(
    "EDITCHECK",
    Arg("n", int, help="history entry number (1-based)"),
    Arg("text", Text, help="its new text (quoted)"),
    logged=False,
    help="Before changing a step: which later steps the change would break (tried on a copy, nothing changes), "
         "and the same change made directly on the finished model instead, as steps added at the end that "
         "break nothing: EDITCHECK, 3, \"EXTRUDE, s1, 20\"",
)
def editcheck(p: Processor, n, text):
    if not 1 <= n <= p.cursor:
        raise CommandError(f"EDITCHECK: no history entry {n} (there are {p.cursor})")
    found = impact(p, n, text)
    data = {"entry": n, "ok": found["ok"], "breaks": found["breaks"], "direct": None}
    if not found["ok"]:
        p.give_report("EDITCHECK", dict(data, message=found["message"]))
        return f"EDITCHECK: the new step {n} itself fails: {found['message']}"
    lines = [f"changing step {n} works"]
    if found["breaks"]:
        lines[0] += f", but {len(found['breaks'])} later step{'s' if len(found['breaks']) != 1 else ''} would fail:"
        lines += [f"  {b['n']}: {b['label']} ({b['message']})" for b in found["breaks"]]
        d = direct(p, n, text, found)
        data["direct"] = d
        if d:
            lines.append("the same change made directly on the finished model, added at the end (nothing breaks):")
            lines += ["  " + x for x in d.splitlines()]
        else:
            lines.append("no direct change found for this one; change it in the history and fix the red steps")
    else:
        lines[0] += "; every later step follows"
    p.give_report("EDITCHECK", data)
    return "\n".join(lines)


def edit_line(line: str) -> tuple[int, str] | None:
    """(n, text) when ``line`` is a ``HIST, EDIT, n, "text"`` command, else None."""
    from .processor import REGISTRY

    try:
        st = parse(line)
    except ScriptError:
        return None
    if len(st) != 1 or not isinstance(st[0], Cmd) or st[0].name != "HIST" or not st[0].args:
        return None
    if st[0].args[0].strip().upper() != "EDIT":
        return None
    return _bound(REGISTRY["HIST"], st[0])


def _bound(cmd, st) -> tuple[int, str] | None:
    from .processor import Processor

    try:
        vals, _ = Processor()._bind(cmd, st.args)
    except Exception:  # noqa: BLE001
        return None
    n = vals.get("n")
    if not isinstance(n, int) or isinstance(n, bool) or not math.isfinite(n):
        return None
    return n, vals.get("text", "")
