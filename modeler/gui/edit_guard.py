"""Ask before a change of a step breaks the steps built on it.

Every value changed in the window (the Properties panel, a step's form, the
item panel, the Parameters table, the sketch sizes) ends as one
``HIST, EDIT, n, "text"``. Before it runs, ``check`` tries it on a copy of the
model (commands/edit_impact.py). When later steps that work now would fail,
the window asks what to do:

* change it in the history anyway (those steps turn red, to fix or delete),
* make the same change directly on the finished model, as steps added at the
  end (offered when one is found: the faces the step made pushed or pulled,
  or the body moved), so nothing breaks,
* or leave everything as it is.

``choose`` is the question; tests replace it. A ``HIST, EDIT`` typed in the command line runs as
typed (``EDITCHECK`` asks the same question in words); MODELER_EDIT_QUESTION=0 turns it off.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..commands.processor import Result

CHECK_LIMIT = 8.0  # seconds: later steps that took longer than this to run are not tried first


@dataclass
class Question:
    n: int  # the step being changed (1-based)
    label: str  # its first line now
    breaks: list = field(default_factory=list)  # [{"n", "label", "message"}]
    direct: str | None = None  # the steps that make the change on the finished model, or None


HISTORY, DIRECT, CANCEL = "history", "direct", "cancel"


def question_for(p, n: int, text: str) -> Question | None:
    """The question to ask before ``HIST, EDIT, n, text``, or None when nothing would break."""
    from ..commands import edit_impact as ei

    if not 1 <= n <= p.cursor:
        return None
    if sum(e.seconds for e in p.history[n - 1:p.cursor]) > CHECK_LIMIT:
        return None  # a long rebuild: trying it twice costs too much; red steps say what broke
    found = ei.impact(p, n, text)
    if not found["ok"] or not found["breaks"]:
        return None  # the step itself fails (HIST, EDIT says so and changes nothing) or all is well
    return Question(n, p.history[n - 1].label, found["breaks"], ei.direct(p, n, text, found))


def check(win, text: str) -> Result | None:
    """Run before ``text`` in the window: None lets it run as typed; a Result is what happened instead
    (already shown in the output)."""
    import os

    from ..commands.edit_impact import edit_line

    if os.environ.get("MODELER_EDIT_QUESTION") == "0" or getattr(win, "typing", False):
        return None  # turned off, or HIST, EDIT typed in the command line: it runs as typed
    hit = edit_line(text)
    if hit is None:
        return None
    p = win.processor
    q = question_for(p, *hit)
    if q is None:
        return None
    answer = choose(win, q)
    if answer == HISTORY:
        return None
    if answer == DIRECT and q.direct:
        with p.undo_group(f"direct change for step {q.n}"):
            results = p.run_script(q.direct)
        res = results[-1] if results else Result("", True)
        if res.ok:
            p._finish(Result(f"! direct change instead of editing step {q.n}", True, f"step {q.n} stays as it was; the change was made on the finished "
                                       "model instead, by the steps above"))
        return res
    return p._finish(Result(text.strip(), False, f"not changed: step {q.n} stays as it was"))


def text_of(q: Question) -> str:
    many = len(q.breaks) != 1
    lines = [f"Changing step {q.n} ({q.label}) would break {len(q.breaks)} later step{'s' if many else ''}:"]
    lines += [f"   {b['n']}: {b['label']}  ({b['message']})" for b in q.breaks[:6]]
    if len(q.breaks) > 6:
        lines.append(f"   ... and {len(q.breaks) - 6} more")
    if q.direct:
        lines.append("\nThe same change can be made directly on the finished model instead, as steps "
                     "added at the end (nothing breaks):")
        lines += ["   " + x for x in q.direct.splitlines()]
    else:
        lines.append("\nNo direct way was found for this change.")
    return "\n".join(lines)


def choose(win, q: Question) -> str:
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(win)
    box.setWindowTitle("This change breaks later steps")
    box.setIcon(QMessageBox.Question)
    box.setText(text_of(q))
    direct_b = box.addButton("Change it directly", QMessageBox.AcceptRole) if q.direct else None
    hist_b = box.addButton("Change it in the history", QMessageBox.DestructiveRole)
    box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(direct_b or hist_b)
    box.exec()
    hit = box.clickedButton()
    if direct_b is not None and hit is direct_b:
        return DIRECT
    if hit is hist_b:
        return HISTORY
    return CANCEL
