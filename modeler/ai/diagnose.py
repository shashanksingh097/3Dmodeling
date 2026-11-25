"""Help when a step fails (docs/M12-assistant-skills.md 4.3, PLAN item 46).

``diagnose`` looks at a failed step (a history entry that fails after an
edit, one with a warning, or the last line typed that failed), tries the
fixes that usually work for that command in a sandbox copy of the model and
says which ones pass, with the exact line to run. Nothing touches the
user's model. The same answer is behind the Why? item on a failed step in
the History panel, which works without the assistant.

Fixes tried, by what the message says:

* "the largest radius/distance/wall that works here is about X": the same
  step with a size a little under X;
* "try a smaller ...", "does not fit", "too large": the step with each
  number made smaller in turn;
* a fillet or chamfer after a ``SHELL``: the same step moved before the shell;
* a boolean (UNION, SUBTRACT, INTERSECT) that fails: ``HEAL`` on its bodies first;
* an unknown command, or a name that does not exist: the nearest names.

A fix counts when the step then runs and no other step fails because of it.
"""

from __future__ import annotations

import difflib
import re
import time
from typing import Any

from ..commands.processor import REGISTRY, Processor
from ..lang.script import first_code_line, split_args, strip_comment
from .sandbox import Sandbox, SandboxError, _hint

TIME_LIMIT = 40.0  # seconds for all the tries together
MAX_TRIES = 10

SIZE_RE = re.compile(r"(?:radius|distance|wall of|wall|angle|thickness)\s+(-?\d+(?:\.\d+)?(?:e-?\d+)?)", re.I)
LIMIT_RE = re.compile(r"(?:largest|thickest|biggest|smallest)\s+[a-z ]*?\s+(?:that works|that fits)[a-z ]*?about\s+"
                      r"(-?\d+(?:\.\d+)?(?:e-?\d+)?)", re.I)
SMALLER_RE = re.compile(r"try a (?:smaller|thinner|lower)|does not fit|too large|too big|too thick|run into each other",
                        re.I)
NAME_RE = re.compile(r"(?:no (body|sketch|named set|set|part|datum|layer|parameter)(?: or \w+)?(?: named)?|unknown (name))"
                     r" '([^']+)'", re.I)
SOFT = "\x00"  # marks a name fix: worth showing even when the step then fails for another reason
BOOLEANS = {"UNION", "SUBTRACT", "INTERSECT", "SPLIT"}
BLENDS = {"FILLET", "CHAMFER"}
THINNING = {"SHELL", "OFFSET", "THICKEN", "DRAFT"}  # a smaller first number is worth a try whatever the message


class DiagnoseError(ValueError):
    pass


def _nice(v: float) -> float:
    """A round number a little under v (two significant figures, rounded down)."""
    if v <= 0:
        return v
    import math

    e = math.floor(math.log10(v)) - 1
    step = 10.0 ** e
    out = math.floor(v * 0.95 / step) * step
    return float(f"{out:.6g}") if out > 0 else float(f"{v * 0.9:.3g}")


def _fmt(v: float) -> str:
    return f"{v:.6g}"


def _split_cmd(text: str) -> tuple[list[str], str, list[str]] | None:
    """(comment lines, command word, argument texts) of a one-command entry, else None."""
    lines = text.strip().splitlines()
    comments = [ln for ln in lines if ln.strip().startswith("!") or not ln.strip()]
    code = [ln for ln in lines if ln.strip() and not ln.strip().startswith("!")]
    if len(code) != 1:
        return None
    parts = split_args(strip_comment(code[0]))
    if not parts or not re.match(r"^\*?[A-Za-z][A-Za-z0-9_]*$", parts[0].strip()):
        return None
    return comments, parts[0].strip(), [a.strip() for a in parts[1:]]


def _join(comments: list[str], word: str, args: list[str]) -> str:
    while args and args[-1] == "":
        args = args[:-1]
    line = ", ".join([word] + args)
    return "\n".join(comments + [line]) if comments else line


def _quote(text: str) -> str:
    return '"' + text.strip().replace('"', "'").replace("\n", "\\n") + '"'


# ---- the step to look at -----------------------------------------------------------------
def _target(p: Processor, step: int | None, line: str | None) -> dict[str, Any]:
    if line:
        line = line.strip()
        box = Sandbox(p)
        r = box.p.run_unit(line)
        if r.ok and not r.warning:
            return {"kind": "line", "text": line, "ok": True, "message": r.message}
        return {"kind": "line", "text": line, "ok": r.ok, "message": r.message if not r.ok else r.warning}
    if step is None:
        bad = [i for i, e in enumerate(p.history[:p.cursor], 1) if not e.suppressed and (not e.ok or e.warning)]
        if bad:
            step = next((i for i in bad if not p.history[i - 1].ok), bad[0])
        else:
            last = getattr(p, "last_failure", None)
            if last:
                return {"kind": "line", "text": last["line"], "ok": False, "message": last["message"]}
            raise DiagnoseError("no step has failed: every history step ran, and nothing typed since has failed")
    if not 1 <= step <= p.cursor:
        raise DiagnoseError(f"there are {p.cursor} history steps; give 1 to {p.cursor}")
    e = p.history[step - 1]
    return {"kind": "step", "n": step, "text": e.text, "ok": e.ok,
            "message": e.message if not e.ok else (e.warning or e.message)}


# ---- trying a fix ------------------------------------------------------------------------
def _failures(p: Processor) -> list[int]:
    return [i for i, e in enumerate(p.history[:p.cursor], 1) if not e.suppressed and not e.ok]


def _try(p: Processor, t: dict, run: str, before: list[int]) -> dict[str, Any]:
    """Run a fix in a sandbox copy of the whole model; ok when nothing fails that did not before
    and the step itself now runs."""
    box = Sandbox(p)
    out = box.run(run, stop_on_error=True, time_limit=TIME_LIMIT)
    if not out.get("ok"):
        rows = out.get("entries") or []
        msg = next((r.get("msg", "") for r in rows if not r.get("ok")), "") or "refused"
        return {"ok": False, "why": msg.split("\n")[0]}
    if t["kind"] == "step":
        now = _failures(box.p)
        if now:
            e = box.p.history[now[0] - 1]
            return {"ok": False, "why": f"step {now[0]} then fails: {(e.message or '').splitlines()[0]}"}
        e = box.p.history[min(t["n"], box.p.cursor) - 1] if box.p.cursor else None
        warn = e.warning if e is not None and e.warning else ""
        return {"ok": True, "warning": warn} if warn else {"ok": True}
    return {"ok": True}


def _edit_line(t: dict, new_text: str) -> str:
    if t["kind"] == "step":
        return f"HIST, EDIT, {t['n']}, {_quote(new_text)}"
    return new_text


def _candidates(p: Processor, t: dict) -> list[tuple[str, str]]:
    """(what, command to run) pairs to try, best first."""
    out: list[tuple[str, str]] = []
    msg = t["message"] or ""
    split = _split_cmd(t["text"])
    if split is None:
        return out
    comments, word, args = split
    up = word.upper()

    # the values of the arguments, as the step saw them
    try:
        box = Sandbox(p, t["n"]) if t["kind"] == "step" else Sandbox(p)
        values: list[float | None] = []
        for a in args:
            try:
                v = box.p.evaluate(a) if a else None
                values.append(float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None)
            except Exception:  # noqa: BLE001 - names, words, SEL ...
                values.append(None)
    except SandboxError:
        values = [None] * len(args)

    def with_arg(i: int, v: float) -> str:
        new = list(args)
        new[i] = _fmt(v)
        return _join(comments, word, new)

    def why_param(i: int) -> str:
        a = args[i]
        return f" ({a} is a parameter: or set {a} = ...)" if re.match(r"^[A-Za-z_]\w*$", a) else ""

    def param_edit(i: int, v: float) -> tuple[str, str] | None:
        """When the argument is a parameter set by an earlier history step, the edit of that step."""
        a = args[i]
        if t["kind"] != "step" or not re.match(r"^[A-Za-z_]\w*$", a):
            return None
        for k in range(t["n"] - 1, 0, -1):
            text = p.history[k - 1].text
            pat = re.compile(r"^(\s*" + re.escape(a) + r"\s*=\s*)([^!\n]+?)(\s*(?:!.*)?)$", re.I | re.M)
            if pat.search(text):
                new = pat.sub(lambda mm: mm.group(1) + _fmt(v) + mm.group(3), text, count=1)
                return (f"set {a} = {_fmt(v)} (step {k})", f"HIST, EDIT, {k}, {_quote(new)}")
        return None

    def size_fixes(i: int, v: float, what: str) -> None:
        pe = param_edit(i, v)
        if pe:
            out.append((pe[0] + what, pe[1]))
        out.append((f"use {_fmt(v)} instead of {args[i]}" + what + ("" if pe else why_param(i)),
                    _edit_line(t, with_arg(i, v))))

    # 1. the message names the largest size that works
    lim = LIMIT_RE.search(msg)
    size = SIZE_RE.search(msg)
    if lim:
        limit = float(lim.group(1))
        target = float(size.group(1)) if size else None
        idx = [i for i, v in enumerate(values) if v is not None and target is not None and abs(v - target) < 1e-9]
        if not idx:
            idx = [i for i, v in enumerate(values) if v is not None and v > limit][:1]
        for i in idx[:1]:
            size_fixes(i, _nice(limit), f", under the largest that works (about {_fmt(limit)})")
            size_fixes(i, _nice(limit * 0.6), "")
    # 2. smaller numbers
    elif SMALLER_RE.search(msg) or up in THINNING:
        nums = [i for i, v in enumerate(values) if v is not None and v > 0]
        for factor in (0.5, 0.25):
            for i in nums[:4]:
                size_fixes(i, values[i] * factor, "")

    # 3. a blend and a shell in the wrong order: move the failing step (with the SEL just before it)
    #    before the other one
    other = {"SHELL": BLENDS}.get(up) or ({"SHELL"} if up in BLENDS else set())
    if other and t["kind"] == "step":
        earlier = [i for i, e in enumerate(p.history[:t["n"] - 1], 1)
                   if (s := _split_cmd(e.text)) and s[1].upper() in other]
        if earlier:
            k = earlier[-1]
            prev = _split_cmd(p.history[k - 2].text) if k >= 2 else None
            if prev and prev[1].upper() in ("SEL", "PICK"):
                k -= 1  # in front of the other step's own selection
            first = t["n"]
            mine = _split_cmd(p.history[t["n"] - 2].text) if t["n"] >= 2 else None
            if mine and mine[1].upper() in ("SEL", "PICK") and t["n"] - 1 > k:
                first = t["n"] - 1
            moves = [f"HIST, MOVE, {first + j}, {k + j}" for j in range(t["n"] - first + 1)]
            what = "shell before rounding the edges" if up == "SHELL" else "round the edges before the shell"
            out.append((f"{what}: move step{'s' if len(moves) > 1 else ''} {first}"
                        f"{'-' + str(t['n']) if len(moves) > 1 else ''} to {k}", "\n".join(moves)))

    # 4. a boolean: heal its bodies first
    if up in BOOLEANS and (re.search(r"fail|invalid|not valid|could not|cannot", msg, re.I)):
        bodies = [a for a in args[:2] if a and a.upper() not in ("SEL", "ALL")]
        if bodies:
            heal = "\n".join(f"HEAL, {b}" for b in bodies)
            if t["kind"] == "step":
                run = f"HIST, INSERT, {t['n']}, {_quote(heal.splitlines()[0])}"
                if len(bodies) > 1:
                    run += f"\nHIST, INSERT, {t['n'] + 1}, {_quote(heal.splitlines()[1])}"
                out.append(("heal the bodies first (HEAL closes small gaps and fixes bad faces)", run))
            else:
                out.append(("heal the bodies first (HEAL closes small gaps and fixes bad faces)",
                            heal + "\n" + t["text"]))

    # 5. names
    if "unknown command" in msg.lower():
        for near in difflib.get_close_matches(up, list(REGISTRY), n=3, cutoff=0.6):
            out.append((f"{near} instead of {word}" + SOFT, _edit_line(t, _join(comments, near, args))))
    m = NAME_RE.search(msg)
    if m:
        kind, bad = (m.group(1) or m.group(2)).lower(), m.group(3)
        names = _names(p, kind)
        for near in difflib.get_close_matches(bad.lower(), [n.lower() for n in names], n=3, cutoff=0.5):
            real = next(n for n in names if n.lower() == near)
            new = [real if a.strip().strip('"').lower() == bad.lower() else a for a in args]
            if new != args:
                out.append((f"{real} instead of {bad} (names here: {', '.join(names[:8])})" + SOFT,
                            _edit_line(t, _join(comments, word, new))))
    seen, uniq = set(), []
    for what, run in out:
        if run not in seen:
            seen.add(run)
            uniq.append((what, run))
    return uniq[:MAX_TRIES]


def _names(p: Processor, kind: str) -> list[str]:
    m = p.model
    if kind == "body":
        return [b.name for b in m.bodies.values() if getattr(b, "name", "")]
    if kind == "sketch":
        return [s.name for s in m.sketches.values()]
    if kind in ("set", "named set"):
        return list(getattr(m, "named_sets", {}) or {})
    if kind == "parameter":
        return list(p.params)
    if kind == "part":
        return list(p.parts)
    if kind == "name":
        return _names(p, "body") + _names(p, "sketch") + _names(p, "set") + _names(p, "parameter")
    if kind == "datum":
        return list(getattr(m, "datums", {}) or {})
    return []


# ---- the whole answer --------------------------------------------------------------------
def diagnose(p: Processor, step: int | None = None, line: str | None = None, run_fixes: bool = True) -> dict[str, Any]:
    t = _target(p, step, line)
    out: dict[str, Any] = {}
    if t["kind"] == "step":
        out["step"] = t["n"]
    out["line"] = t["text"]
    if t["ok"] and t["kind"] == "line":
        out["ok"] = True
        out["message"] = (t["message"] or "").splitlines()[0] if t["message"] else "it runs"
        return out
    out["failed"] = not t["ok"]
    out["message"] = t["message"]
    hint = _hint(t["message"] or "")
    if hint:
        out["hint"] = hint
    from ..commands import why_handlers as wh

    fault = (wh.step_fault(p, t["n"]) if t["kind"] == "step"
             else wh.fault_for(p, t["text"], t["message"] or "", typed=True))
    if fault:
        out["fault"] = fault
    split = _split_cmd(t["text"])
    if split:
        word = split[1].upper()
        c = REGISTRY.get(word)
        if c is not None:
            out["command"] = word
            out["arguments"] = ", ".join([word] + [a.name for a in c.args])
        from . import skills as sk

        guides = ["fixing-failed-steps"] + [s.name for s in sk.for_command(word, p.project_dir)
                                            if s.name != "fixing-failed-steps"]
        out["guides"] = guides
    if not run_fixes or (t["ok"] and t["kind"] == "step"):
        if t["ok"]:
            out["note"] = "the step ran; the message above is a warning to check"
        return out
    before = _failures(p)
    fixes, tried = [], []
    start = time.monotonic()
    for what, run in _candidates(p, t):
        if time.monotonic() - start > TIME_LIMIT:
            tried.append({"fix": what, "result": "not tried (time limit)"})
            continue
        soft = what.endswith(SOFT)
        what = what.rstrip(SOFT)
        res = _try(p, t, run, before)
        if not res["ok"] and soft and not NAME_RE.search(res["why"]) and "unknown command" not in res["why"]:
            fixes.append({"fix": what, "run": run, "then": res["why"]})
            continue
        if res["ok"]:
            row = {"fix": what, "run": run}
            if res.get("warning"):
                row["warning"] = res["warning"].splitlines()[0]
            fixes.append(row)
            if len(fixes) >= 3:
                break
        else:
            tried.append({"fix": what, "result": res["why"]})
    out["fixes"] = fixes
    if tried:
        out["tried"] = tried
    if not fixes:
        out["next"] = ("no usual fix worked; read the message and the guide, look at the bodies with describe_body, "
                       "or try the step on its own in the sandbox")
    return out


def why_text(d: dict[str, Any]) -> str:
    """The diagnose answer as plain text for a person (the Why? window)."""
    if d.get("ok"):
        return f"{d['line']}\n\nThis line runs now: {d.get('message', '')}"
    head = f"Step {d['step']}: " if "step" in d else ""
    lines = [head + first_code_line(d["line"]), ""]
    lines.append(("It failed: " if d.get("failed") else "It ran, with a warning: ") + (d.get("message") or ""))
    if d.get("arguments"):
        lines += ["", "Arguments: " + d["arguments"]]
    if d.get("fixes"):
        lines += ["", "Fixes (tried on a copy of your model):"]
        for f in d["fixes"]:
            lines.append(f"  - {f['fix']}:")
            lines += ["      " + ln for ln in f["run"].splitlines()]
            if f.get("then"):
                lines.append(f"      (the name is right, but the step then says: {f['then']})")
    elif d.get("failed"):
        lines += ["", d.get("next", "")]
    if d.get("tried"):
        lines += ["", "Tried and did not work:"]
        lines += [f"  - {f['fix']}: {f['result']}" for f in d["tried"]]
    return "\n".join(lines).rstrip()
