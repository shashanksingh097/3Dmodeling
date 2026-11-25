"""Edit a sketch that features already use, in place (the history stays whole).

``SKETCH, name`` (no plane) on a closed sketch that an EXTRUDE, REVOLVE or other
feature already used opens it where it was drawn: the model goes back to just
before the first step that used it, and the steps from there on are put aside.
The new sketch lines are recorded there, in their place in the history. When
the sketch is closed (``ENDSKETCH``), the steps put aside come back after them
and run again, so every feature follows the changed sketch.

UNDO back over the reopen cancels the edit: the history is as it was.
One UNDO after ``ENDSKETCH`` takes back the whole edit.

While the edit is open, SAVE (and the window's autosave) write the project as
it was before the edit, so a file never holds a half-done edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .processor import Processor


@dataclass
class SketchEdit:
    name: str  # the sketch, upper case
    at: int  # 0-based history place of the first step that used it (where the new lines go)
    tail: list = field(default_factory=list)  # the entries put aside (Entry objects)
    before: dict = field(default_factory=dict)  # history_backup() from before the edit
    mark: int = 0  # len(_undo) when the edit started


def first_use(p: Processor, key: str) -> int | None:
    """0-based index of the first applied entry after which sketch ``key`` is used, or None."""
    for j in range(p.cursor):
        sk = p._snaps[j + 1]["model"]["sketches"].get(key)
        if sk is not None and sk.used_by:
            return j
    return None


def wants_edit(p: Processor, name: str, on: str) -> bool:
    """Is ``SKETCH, name`` (no plane) a reopen of a sketch that steps already use?"""
    m = p.model
    if p.sketch_edit is not None or m.active_sketch or on.strip():
        return False
    sk = m.sketches.get(name.strip().upper())
    return sk is not None and bool(sk.used_by)


def begin(p: Processor, name: str) -> str:
    """Put aside the steps from the first use of sketch ``name`` on, and go back to before it."""
    from .processor import CommandError

    key = name.strip().upper()
    j = first_use(p, key)
    if j is None:
        raise CommandError(f"SKETCH: no step of the history uses sketch {name}")
    if key not in p._snaps[j]["model"]["sketches"]:
        raise CommandError(f"SKETCH: sketch {name} is made and used in the same step "
                           f"({p.history[j].label}); edit that step instead (HIST, EDIT, {j + 1})")
    p.unexplode()
    p._drop_redo_tail()
    m = p.model
    se = SketchEdit(key, j, list(p.history[j:p.cursor]), p.history_backup(), len(p._undo))
    view = (set(m.view_hidden), set(m.view_shown), dict(m.faded))
    p.history = p.history[:j]
    p._snaps = p._snaps[:j + 1]
    p.cursor = j
    p._restore(p._snaps[j], emit=False)
    m.view_hidden, m.view_shown, m.faded = view
    m.restore(m.snapshot())  # one refresh: the later bodies leave the view
    p.sketch_edit = se
    p._redo = []
    return (f"editing sketch {p._snaps[j]['model']['sketches'][key].name} where it was drawn "
            f"(before step {j + 1}); {len(se.tail)} later step{'s' if len(se.tail) != 1 else ''} "
            "wait and run again with the changed sketch at ENDSKETCH")


def finish(p: Processor) -> str:
    """Bring the steps put aside back after the sketch's new lines and run them again."""
    se, p.sketch_edit = p.sketch_edit, None
    if se is None:
        return ""
    if p.cursor <= se.at:  # the reopen itself was undone: no edit
        p.history_restore(se.before, emit=False)
        del p._undo[min(se.mark, len(p._undo)):]
        p._redo = []
        p.model.restore(p.model.snapshot())
        p._history_changed()
        return "sketch edit cancelled; the history is as it was"
    p._drop_redo_tail()
    start = p.cursor
    p.history.extend(se.tail)
    p._snaps.extend([p._snaps[-1]] * len(se.tail))  # placeholders, rebuilt below
    p.cursor += len(se.tail)
    msg = p.rebuild(start) if se.tail else ""
    del p._undo[min(se.mark, len(p._undo)):]
    p._redo = []
    p._push_undo({"kind": "hist", "label": f"edit of sketch {se.name.lower()}", "before": se.before,
                  "after": p.history_backup()})
    return f"sketch {se.name.lower()} changed; the later steps ran again: {msg}" if msg else ""


def saved_entries(p: Processor) -> list:
    """The entries a project file holds: during an open sketch edit, the history as it was before it."""
    se = p.sketch_edit
    if se is None:
        return p.history[:p.cursor]
    return se.before["history"][:se.before["cursor"]]
