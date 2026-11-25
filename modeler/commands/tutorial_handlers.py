"""TUTORIAL: short lessons that check the model as you go (PLAN item 94).

A tutorial is a text file (``modeler/tutorials/*.tut``, or one of your own in
the user tutorial folder) with a header and steps::

    ! tutorial: first_part
    ! title: Your first part
    ! about: one line on what it teaches
    ! order: 1                      (where it sits in the list)
    ! start: BLOCK, 0, 0, 0, 30, 20, 4   (steps the lesson's project starts with)

    ## Make a block
    The text of the step (a few sentences, **bold** for buttons).
    hint: BLOCK, 0, 0, 0, 60, 40, 10    (what "Show me" runs; any number of lines)
    check: COUNT("BODY"), GE, 1 ! a body in the model
                     (ASSERT text, then what it means in words after "!";
                      all must pass to finish the step)

A step without checks is one to read: Next goes on. The checks use the same
expectations as ASSERT (ai/expect.py), so they look at the model itself and
do not care whether the user clicked, typed or asked the assistant.

``TUTORIAL`` lists the lessons, ``TUTORIAL, name`` starts one in a new
project, and ``TUTORIAL, CHECK | NEXT | BACK | HINT | SHOW | STOP | JSON``
move through it. The window's Tutorial panel is the same commands with
buttons; it checks again after every step.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from .processor import Arg, CommandError, Processor, Raw, command

BUILT_IN = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tutorials")
ACTIONS = ("LIST", "CHECK", "NEXT", "BACK", "HINT", "SHOW", "STOP", "JSON", "STATUS")


def user_dir() -> str:
    """Where your own tutorials go: beside your templates; ``MODELER_TUTORIALS`` overrides it."""
    if os.environ.get("MODELER_TUTORIALS"):
        return os.environ["MODELER_TUTORIALS"]
    from .template_handlers import user_dir as templates

    return os.path.join(os.path.dirname(templates()), "tutorials")


@dataclass
class Step:
    title: str
    text: str = ""
    hints: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)  # each check in words ("" if none given)


@dataclass
class Tutorial:
    name: str
    title: str
    about: str = ""
    order: int = 99
    start: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    path: str = ""


@dataclass
class Lesson:
    """A tutorial being followed: where the user is and what passed."""

    tut: Tutorial
    index: int = 0
    done: set[int] = field(default_factory=set)
    results: list[dict] = field(default_factory=list)  # the last check of the current step

    @property
    def step(self) -> Step:
        return self.tut.steps[self.index]

    @property
    def last(self) -> bool:
        return self.index >= len(self.tut.steps) - 1


def parse(text: str, path: str = "") -> Tutorial:
    head: dict[str, Any] = {"start": []}
    steps: list[Step] = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not steps and line.startswith("!"):
            m = re.match(r"!\s*([a-z]+)\s*:\s*(.*)$", line, re.I)
            if m:
                key, value = m.group(1).lower(), m.group(2).strip()
                if key == "start":
                    head["start"].append(value)
                else:
                    head[key] = value
            continue
        if line.startswith("## "):
            steps.append(Step(line[3:].strip()))
            continue
        if not steps:
            if line.strip():
                raise CommandError(f"tutorial {path or ''} line {n}: text before the first '## step'")
            continue
        m = re.match(r"(hint|check)\s*:\s*(.*)$", line.strip(), re.I)
        if m and m.group(1).lower() == "hint":
            steps[-1].hints.append(m.group(2).strip())
        elif m:
            what, _, label = m.group(2).partition(" ! ")
            steps[-1].checks.append(what.strip())
            steps[-1].labels.append(label.strip())
        else:
            steps[-1].text += line + "\n"
    for s in steps:
        s.text = re.sub(r"\n{3,}", "\n\n", s.text).strip()
    name = head.get("tutorial") or os.path.splitext(os.path.basename(path))[0]
    if not name:
        raise CommandError("tutorial: no '! tutorial: name' line")
    if not steps:
        raise CommandError(f"tutorial {name}: no steps ('## title' lines)")
    try:
        order = int(head.get("order", 99))
    except ValueError:
        order = 99
    return Tutorial(name, head.get("title", name), head.get("about", ""), order, head["start"], steps, path)


def available() -> list[Tutorial]:
    """Built-in tutorials, then your own (yours win on a name clash)."""
    found: dict[str, Tutorial] = {}
    for folder in (BUILT_IN, user_dir()):
        if not os.path.isdir(folder):
            continue
        for f in sorted(os.listdir(folder)):
            if f.endswith(".tut"):
                path = os.path.join(folder, f)
                try:
                    with open(path, encoding="utf-8") as fh:
                        t = parse(fh.read(), path)
                except (OSError, CommandError):
                    continue
                found[t.name.lower()] = t
    return sorted(found.values(), key=lambda t: (t.order, t.name))


def find(name: str) -> Tutorial:
    key = name.strip().strip('"').lower()
    tuts = available()
    for t in tuts:
        if t.name.lower() == key or t.title.lower() == key:
            return t
    names = ", ".join(t.name for t in tuts)
    raise CommandError(f"no tutorial {name!r}: there are {names}")


# ---- following a lesson -------------------------------------------------------------------------------

def check_step(p: Processor, lesson: Lesson) -> bool:
    """Run the current step's checks; True when all pass (a step with no checks passes)."""
    from ..ai import expect

    results = []
    step = lesson.step
    for c, label in zip(step.checks, step.labels):
        try:
            o = expect.check(p, c)
            results.append({"check": c, "label": label, "pass": o.passed, "said": o.sentence()})
        except expect.ExpectError as exc:
            said = str(exc)
            m = re.match(r"unknown name '([^']+)'", said)
            results.append({"check": c, "label": label, "pass": False,
                            "said": f"not yet: nothing is called {m.group(1)}" if m else f"not yet: {said}"})
    lesson.results = results
    ok = all(r["pass"] for r in results)
    if ok and lesson.step.checks:
        lesson.done.add(lesson.index)
    return ok


def state(p: Processor) -> dict[str, Any]:
    """The lesson as data (TUTORIAL, JSON; the panel and the assistant read this)."""
    lesson = p.tutorial
    if lesson is None:
        return {"tutorial": None, "available": [{"name": t.name, "title": t.title, "about": t.about}
                                                for t in available()]}
    s = lesson.step
    return {"tutorial": lesson.tut.name, "title": lesson.tut.title, "step": lesson.index + 1,
            "steps": len(lesson.tut.steps), "step_title": s.title, "text": s.text, "hints": list(s.hints),
            "checks": list(lesson.results), "passed": _passed(lesson), "last": lesson.last,
            "done": sorted(i + 1 for i in lesson.done)}


def _passed(lesson: Lesson) -> bool:
    return not lesson.step.checks or (bool(lesson.results) and all(r["pass"] for r in lesson.results))


def step_text(p: Processor) -> str:
    lesson = p.tutorial
    s = lesson.step
    lines = [f"{lesson.tut.title}: step {lesson.index + 1} of {len(lesson.tut.steps)}: {s.title}", "",
             _plain(s.text)]
    if s.checks:
        lines.append("")
        for r in lesson.results:
            lines.append(("  ✓ " if r["pass"] else "  · ") + r_text(r))
        if _passed(lesson):
            lines.append("done: TUTORIAL, NEXT goes on" if not lesson.last else "done: that was the last step")
    if s.hints:
        lines.append("(TUTORIAL, SHOW runs: " + " / ".join(s.hints) + ")")
    return "\n".join(lines)


def r_text(r: dict) -> str:
    """A check in words: its label, and what was found when it does not pass yet."""
    said = r["said"].removeprefix("ok: ")
    if not r.get("label"):
        return said
    return r["label"] if r["pass"] else f"{r['label']} (now: {said})"


def _plain(text: str) -> str:
    return text.replace("**", "").replace("`", "")


def _tell_ui(p: Processor) -> None:
    ui = p.ui
    if ui is not None and hasattr(ui, "tutorial_changed"):
        try:
            ui.tutorial_changed()
        except Exception:  # noqa: BLE001  (the panel must never break the command)
            pass


def start(p: Processor, t: Tutorial) -> list:
    """A new project with the lesson's start steps, and the lesson at step 1."""
    p.reset()
    p.project_path = None
    results = []
    for line in t.start:  # one by one, so a start step may be a history edit (HIST, EDIT ...)
        r = p.run(line)
        results.append(r)
        if not r.ok:
            raise CommandError(f"the tutorial {t.name} could not set up its project: '{line}': {r.message}")
    p.saved_script = p.script()  # nothing of yours to lose yet
    p.tutorial = Lesson(t)
    check_step(p, p.tutorial)
    return results


def _unsaved(p: Processor) -> bool:
    return bool(p.history) and p.saved_script != p.script()


@command(
    "TUTORIAL",
    Arg("action", Raw, "", help="a tutorial's name to start it, or LIST, CHECK, NEXT, BACK, HINT, SHOW, STOP, "
                                "STATUS, JSON"),
    Arg("how", Raw, "", help="with a name: NEW starts even if the project has unsaved changes"),
    session=True,
    help="Short lessons that check your model as you go. TUTORIAL lists them; TUTORIAL, first_part starts "
         "one in a new project; TUTORIAL, CHECK says what is still missing; NEXT and BACK move between steps; "
         "HINT shows what to do and SHOW does it for you; STOP ends the lesson. In the window: Help > "
         "Tutorials, and the Tutorial panel.",
)
def tutorial(p: Processor, action, how):
    word = (action or "").strip()
    up = word.upper()
    lesson: Lesson | None = p.tutorial
    if up in ("", "LIST"):
        tuts = available()
        lines = ["tutorials (TUTORIAL, name starts one):"]
        lines += [f"  {t.name:<18} {t.title}: {t.about}" for t in tuts]
        if lesson is not None:
            lines.append(f"following: {lesson.tut.name}, step {lesson.index + 1} of {len(lesson.tut.steps)}")
        return "\n".join(lines)
    if up == "JSON":
        import json

        if lesson is not None:
            check_step(p, lesson)
        return json.dumps(state(p), indent=1)
    if up in ACTIONS:
        if lesson is None:
            raise CommandError(f"TUTORIAL, {up}: no tutorial is running: TUTORIAL lists them")
        if up == "STOP":
            p.tutorial = None
            _tell_ui(p)
            return f"stopped the tutorial {lesson.tut.name} (your model stays as it is)"
        if up in ("CHECK", "STATUS"):
            check_step(p, lesson)
            _tell_ui(p)
            return step_text(p)
        if up == "HINT":
            if not lesson.step.hints:
                return f"step {lesson.index + 1} has nothing to type: read it, then TUTORIAL, NEXT"
            return "type (or TUTORIAL, SHOW to run it):\n" + "\n".join("  " + h for h in lesson.step.hints)
        if up == "SHOW":
            return _show(p, lesson)
        if up == "NEXT":
            if not check_step(p, lesson):
                missing = [r_text(r) for r in lesson.results if not r["pass"]]
                _tell_ui(p)
                raise CommandError(f"TUTORIAL, NEXT: step {lesson.index + 1} is not done yet: "
                                   + "; ".join(missing) + " (TUTORIAL, HINT shows what to do)")
            if lesson.last:
                p.tutorial = None
                _tell_ui(p)
                return f"finished the tutorial {lesson.tut.title}: well done"
            lesson.index += 1
            check_step(p, lesson)
            _tell_ui(p)
            return step_text(p)
        if up == "BACK":
            if lesson.index == 0:
                raise CommandError("TUTORIAL, BACK: this is the first step")
            lesson.index -= 1
            check_step(p, lesson)
            _tell_ui(p)
            return step_text(p)
    t = find(word)
    if _unsaved(p) and (how or "").strip().upper() != "NEW":
        raise CommandError(f"TUTORIAL, {t.name}: the project has unsaved changes, and a tutorial starts a new "
                           f"project: SAVE first, or TUTORIAL, {t.name}, NEW to start anyway")
    start(p, t)
    _tell_ui(p)
    return f"started the tutorial {t.title} ({len(t.steps)} steps)\n\n" + step_text(p)


def _show(p: Processor, lesson: Lesson) -> str:
    """Run the step's hint lines, as if the user had typed them."""
    if not lesson.step.hints:
        return f"step {lesson.index + 1} has nothing to run: read it, then TUTORIAL, NEXT"
    said = []
    for h in lesson.step.hints:
        r = p.run(h)
        said.append(f"{h}: {r.message.splitlines()[0] if r.message else 'ok'}")
        if not r.ok:
            break
    check_step(p, lesson)
    _tell_ui(p)
    return "\n".join(said) + "\n\n" + step_text(p)
