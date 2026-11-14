"""Part documents: design one part on its own (NEWPART, OPENPART, SAVEPART).

A part document is a normal session whose history holds the part's steps,
so every step shows in History and opens in its form. Its leading
parameter assignments (``D = 8`` before the first step that is not one)
are the part's inputs, with their values as defaults. Saving wraps the
steps into one ``*PART`` block, the same code ``HIST, PART`` writes, and
opening a part file unwraps a block back into steps.

A part document can also stand for a ``*PART`` block inside a project (Edit
part in the window): then saving hands the new block back to the project
instead of writing a file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from ..lang.script import Assign, PartDef, ScriptError, parse
from .processor import Arg, CommandError, Path, Processor, Text, command


@dataclass
class PartDoc:
    name: str  # as the user wrote it (the block's name)
    file: str | None = None  # the part file it is saved to
    # with a sink, SAVEPART hands the block text to it (Edit part in a project)
    sink: Callable[[str], str] | None = None
    where: str = ""  # what the sink stands for, for messages ("history step 5")


def part_blocks(text: str) -> list[PartDef]:
    try:
        stmts = parse(text)
    except ScriptError as exc:
        raise CommandError(f"OPENPART: {exc}") from None
    return [st for st in stmts if isinstance(st, PartDef)]


def _source_name(st: PartDef) -> str:
    """The part's name as written in the file (PartDef keeps it upper-case)."""
    head = st.source.splitlines()[0].split(",")
    return head[1].strip() if len(head) > 1 else st.name.lower()


def open_part_text(p: Processor, text: str, name: str = "", file: str | None = None,
                   sink: Callable[[str], str] | None = None, where: str = "") -> str:
    """Replace the session with one part of ``text``, unwrapped into steps."""
    parts = part_blocks(text)
    if not parts:
        raise CommandError("OPENPART: there is no *PART block in it")
    if name:
        chosen = [st for st in parts if st.name == name.strip().upper()]
        if not chosen:
            raise CommandError(f"OPENPART: no part {name!r}; it holds {', '.join(_source_name(s) for s in parts)}")
        st = chosen[0]
    elif len(parts) > 1:
        raise CommandError(f"OPENPART: it holds {len(parts)} parts ({', '.join(_source_name(s) for s in parts)}); "
                           "name the one to open: OPENPART, file, name")
    else:
        st = parts[0]
    p.reset()
    lines = [f"{k} = {v}" if v is not None else f"{k} = 0    ! no default in the part" for k, v in st.params]
    script = "\n".join(lines) + ("\n" if lines else "") + st.body_text
    results = p.run_script(script)
    p.part_doc = PartDoc(_source_name(st), file, sink, where)
    bad = [r for r in results if not r.ok]
    msg = f"part {p.part_doc.name}: {len(st.params)} input{'s' if len(st.params) != 1 else ''}, " \
          f"{p.cursor - len(lines)} step{'s' if p.cursor - len(lines) != 1 else ''}"
    if bad:
        raise CommandError(msg + f"; stopped at '{bad[0].line}': {bad[0].message}")
    return msg


def part_inputs(p: Processor) -> list[tuple[str, str]]:
    """The part's inputs: the leading NAME = expr entries, with their expressions."""
    out = []
    for e in p.history[: p.cursor]:
        if e.suppressed:
            continue
        try:
            stmts = parse(e.text)
        except ScriptError:
            break
        if len(stmts) == 1 and isinstance(stmts[0], Assign):
            out.append((stmts[0].name, stmts[0].expr))
            continue
        break
    return out


def part_text(p: Processor) -> str:
    """The session's steps wrapped into one *PART block."""
    if p.part_doc is None:
        raise CommandError("SAVEPART: this is not a part document (File > New part, NEWPART, name, "
                           "or OPENPART, file)")
    inputs = part_inputs(p)
    entries = [e for e in p.history[: p.cursor] if not e.suppressed]
    body = entries[len(inputs):]
    if not body:
        raise CommandError("SAVEPART: the part has no steps yet")
    head = f"*PART, {p.part_doc.name}" + "".join(f", {k}={x}" for k, x in inputs)
    block = "\n".join("  " + ln if ln.strip() else "" for e in body for ln in e.text.splitlines())
    return f"{head}\n{block}\n*ENDPART"


def write_part(path: str, name: str, block: str) -> str:
    """Put the block in a part file: in place of the part of the same name if
    the file holds it, else added at the end (other parts and comments stay)."""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            old = fh.read()
        same = [st for st in part_blocks(old) if st.name == name.upper()]
        if same:
            new = old.replace(same[0].source, block, 1)
            how = "replaced"
        else:
            new = old.rstrip() + "\n\n" + block + "\n"
            how = "added to"
    else:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        new, how = block + "\n", "wrote"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new if new.endswith("\n") else new + "\n")
    return how


@command("NEWPART", Arg("name", Text, help="the part's name, e.g. bolt"), session=True,
         help="Start a part document: design one part on its own. Parameters set first (D = 8) are the part's "
              "inputs; SAVEPART writes the steps as one *PART block to a .cmd part file.")
def newpart(p: Processor, name):
    from ..lang.script import is_ident

    if not is_ident(name.strip()):
        raise CommandError(f"NEWPART: {name!r} is not a valid part name")
    p.reset()
    p.project_path = None
    p.part_doc = PartDoc(name.strip())
    return f"new part {name.strip()}: set its inputs first (D = 8), then model it; SAVEPART writes it"


@command("OPENPART", Arg("file", Path, help="a part file (.cmd) or a part name in the library"),
         Arg("name", Text, "", "which part, when the file holds several"), session=True,
         help="Open one part of a part file as a part document: its inputs become parameters and its steps "
              "history entries, each editable in its form. SAVEPART writes it back.")
def openpart(p: Processor, file, name):
    from .part_handlers import resolve_library

    try:
        path = resolve_library(p, file)
    except CommandError as exc:
        raise CommandError(str(exc).replace("LIB:", "OPENPART:")) from None
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    msg = open_part_text(p, text, name, path)
    p.project_path = None
    return f"opened {msg} from {path}"


@command("SAVEPART", Arg("file", Path, "", "the part file (.cmd); default: the one it came from"), session=True,
         help="Save a part document: its steps wrapped in one *PART block, written into the part file (in place "
              "of a part of the same name, other parts in the file stay).")
def savepart(p: Processor, file):
    block = part_text(p)
    doc = p.part_doc
    if doc.sink is not None and not file:
        return doc.sink(block)
    path = file or doc.file
    if not path:
        raise CommandError(f"SAVEPART: give a file name, e.g. SAVEPART, {doc.name.lower()}.cmd")
    if not path.lower().endswith(".cmd"):
        path += ".cmd"
    how = write_part(path, doc.name, block)
    doc.file, doc.sink = path, None
    return f"{how} part {doc.name} in {path}"
