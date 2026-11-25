"""PIN: measurements kept in the view and measured again after every change (PLAN item 115).

``PIN, gap, DIST, FACE, 6, BODY, lid`` keeps the distance between face 6 and the lid in the 3D
view, as a line between the nearest points with its value, and measures it again whenever the
model changes (the IDs of faces, edges and bodies stay with them through edits). A pin can carry
limits: ``PIN, gap, DIST, FACE, 6, BODY, lid, 2`` wants at least 2 and turns red below it;
``PIN, a, ANGLE, FACE, 3, FACE, 9, 89.5, 90.5`` wants the angle in that range. The pins are history
steps, saved with the project; ``PIN`` lists them with their values now, as data for the assistant
(report "pins"), and ``PIN, DELETE, gap`` / ``PIN, CLEAR`` remove them.
"""

from __future__ import annotations

import math

from ..core import datum as dt
from ..core.model import ModelError
from ..geometry import features as ft
from ..lang.expr import fmt_num
from ..lang.script import is_ident
from .measure_handlers import _Thing, _things
from .processor import Arg, CommandError, Processor, Raw, command

KINDS = ("DIST", "ANGLE")


def _n(v: float) -> str:
    return fmt_num(round(float(v), 4) + 0.0)


def _ref_of(p: Processor, t: _Thing) -> list:
    """What a measured thing is, kept so it can be found again: [kind, id or name]."""
    if t.datum is not None:
        return ["DATUM", t.label]
    kind, _, gid = t.label.partition(" ")
    return [kind, int(gid)]


def _thing(model, ref) -> _Thing:
    kind, what = ref
    if kind == "DATUM":
        if str(what).upper() in dt.BASE_PLANES:
            from .feature_handlers import plane_ref

            return _Thing(str(what), datum=plane_ref(None, str(what), "PIN"))
        return _Thing(str(what), datum=model.datum(str(what)))
    shape = model.entity_shape(kind, int(what))
    label = f"{kind} {what}"
    if kind == "BODY":
        b = model.bodies.get(int(what))
        if b is not None and b.name:
            label = b.name
    return _Thing(label, shape=shape, kind=kind)


def measure(model, pin: dict) -> dict:
    """A pin's value now: {name, kind, value, a, b (points for the line), text, ok (None without limits), error}."""
    out = {"name": pin["name"], "kind": pin["kind"], "value": None, "a": None, "b": None, "ok": None, "error": "",
           "lo": pin.get("lo"), "hi": pin.get("hi")}
    try:
        a, b = (_thing(model, r) for r in pin["refs"])
    except (ModelError, KeyError, ValueError, CommandError) as exc:
        out["error"] = f"what it measured is gone ({exc})"
        out["text"] = f"{pin['name']}: ?"
        return out
    try:
        if pin["kind"] == "DIST":
            d, pa, pb = ft.distance(a.get_shape(), b.get_shape())
            out.update(value=d, a=pa, b=pb)
        else:
            da, db = a.direction(), b.direction()
            if da is None or db is None:
                raise ft.FeatureError("one of them has no direction")
            (va, ka), (vb, kb) = da, db
            between = math.degrees(math.acos(max(-1.0, min(1.0, dt.dot(va, vb)))))
            if ka == kb == "line":
                between = min(between, 180 - between)
            elif ka != kb:
                between = abs(90 - between)
            out["value"] = between
            try:  # where to draw it: between the two things' nearest points
                _d, pa, pb = ft.distance(a.get_shape(), b.get_shape())
                out.update(a=pa, b=pb)
            except ft.FeatureError:
                pass
    except ft.FeatureError as exc:
        out["error"] = str(exc)
        out["text"] = f"{pin['name']}: ?"
        return out
    v = out["value"]
    lo, hi = pin.get("lo"), pin.get("hi")
    if lo is not None or hi is not None:
        out["ok"] = (lo is None or v >= lo - 1e-9) and (hi is None or v <= hi + 1e-9)
    unit = " deg" if pin["kind"] == "ANGLE" else ""
    out["text"] = f"{pin['name']}: {_n(v)}{unit}" + ("" if out["ok"] is not False else " (!)")
    return out


def _limits_text(pin: dict) -> str:
    lo, hi = pin.get("lo"), pin.get("hi")
    if lo is not None and hi is not None:
        return f"wants {_n(lo)} to {_n(hi)}"
    if lo is not None:
        return f"wants at least {_n(lo)}"
    if hi is not None:
        return f"wants at most {_n(hi)}"
    return ""


def _line(model, pin: dict) -> str:
    r = measure(model, pin)
    what = " to ".join(f"{k} {w}" for k, w in pin["refs"])
    lim = _limits_text(pin)
    if r["error"]:
        state = f"cannot be measured: {r['error']}"
    else:
        state = r["text"].split(": ", 1)[1].replace(" (!)", "")
        if r["ok"] is False:
            state += f", OUT of range ({lim})"
        elif r["ok"]:
            state += f", in range ({lim})"
    return f"  {pin['name']} ({pin['kind'].lower()}, {what}): {state}"


def report(model) -> list[dict]:
    out = []
    for pin in model.measure_pins:
        r = measure(model, pin)
        out.append({"name": pin["name"], "kind": pin["kind"], "refs": [list(x) for x in pin["refs"]],
                    "value": None if r["value"] is None else round(r["value"], 6), "lo": pin.get("lo"),
                    "hi": pin.get("hi"), "ok": r["ok"], "error": r["error"]})
    return out


def _num(p: Processor, raw: str, what: str):
    raw = str(raw).strip()
    if not raw:
        return None
    try:
        return float(p.evaluate(raw))
    except Exception:  # noqa: BLE001
        raise CommandError(f"PIN: {what} must be a number, not {raw!r}") from None


@command(
    "PIN",
    Arg("name", Raw, "", "the pin's name; DELETE, CLEAR or nothing (list them)"),
    Arg("kind", Raw, "", "DIST or ANGLE (with DELETE: the pin's name)"),
    Arg("k1", Raw, ""), Arg("i1", Raw, ""), Arg("k2", Raw, ""), Arg("i2", Raw, ""),
    Arg("lo", Raw, "", "the least it may be (empty: no least)"),
    Arg("hi", Raw, "", "the most it may be (empty: no most)"),
    help="Keep a measurement in the view, measured again after every change: PIN, gap, DIST, FACE, 6, BODY, lid "
         "(or PIN, gap, DIST with two things picked) · PIN, a, ANGLE, FACE, 3, FACE, 9 · limits: PIN, gap, DIST, "
         "FACE, 6, BODY, lid, 2 (at least 2: red below) or ..., 89.5, 90.5 (a range). PIN alone lists them with "
         "their values now; PIN, DELETE, gap and PIN, CLEAR remove them.",
)
def pin(p: Processor, name, kind, k1, i1, k2, i2, lo, hi):
    m = p.model
    word = str(name).strip()
    up = word.upper()
    if not word:
        p.give_report("pins", {"pins": report(m)})
        if not m.measure_pins:
            return "no pinned measurements (PIN, name, DIST, ... adds one)"
        return "\n".join([f"{len(m.measure_pins)} pinned measurement{'s' if len(m.measure_pins) != 1 else ''}:"]
                         + [_line(m, x) for x in m.measure_pins])
    if up == "CLEAR":
        n = len(m.measure_pins)
        m.set_pins([])
        return f"removed {n} pinned measurement{'s' if n != 1 else ''}"
    if up == "DELETE":
        target = str(kind).strip().upper()
        left = [x for x in m.measure_pins if x["name"].upper() != target]
        if len(left) == len(m.measure_pins):
            raise CommandError(f"PIN: there is no pin {str(kind).strip()!r} "
                               f"(pins: {', '.join(x['name'] for x in m.measure_pins) or 'none'})")
        m.set_pins(left)
        return f"removed pin {str(kind).strip()}"
    if not is_ident(word):
        raise CommandError(f"PIN: {word!r} is not a valid name (letters, digits, _)")
    k = str(kind).strip().upper() or "DIST"
    if k in ("DISTANCE",):
        k = "DIST"
    if k not in KINDS:
        raise CommandError("PIN: the kind is DIST or ANGLE")
    a, b = _things(p, "PIN", [k1, i1, k2, i2])
    lo_v, hi_v = _num(p, lo, "the least"), _num(p, hi, "the most")
    if lo_v is not None and hi_v is not None and lo_v > hi_v:
        raise CommandError("PIN: the least is more than the most")
    new = {"name": word, "kind": k, "refs": [_ref_of(p, a), _ref_of(p, b)], "lo": lo_v, "hi": hi_v}
    r = measure(m, new)
    if r["error"]:
        raise CommandError(f"PIN: {r['error']}")
    pins = [x for x in m.measure_pins if x["name"].upper() != up]
    replaced = len(pins) != len(m.measure_pins)
    m.set_pins(pins + [new])
    p.give_report("pins", {"pins": report(m)})
    return ("changed " if replaced else "pinned ") + _line(m, new).strip()
