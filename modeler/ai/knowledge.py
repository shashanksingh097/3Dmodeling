"""Three read tools the assistant was missing (docs/M12-assistant-skills.md 4.2):

* ``search_docs``: the parts of LANGUAGE.md, USER-GUIDE.md, the skills and the
  example scripts that match some words, trimmed, with no network and no
  extra package (plain keyword ranking);
* ``parameters``: every parameter with its value, the step that sets it and
  the steps that read it, so "make it 10 mm wider" becomes a one-line edit;
* ``sketch_state``: a sketch's geometry, constraints, freedom left, repeated
  constraints and closed profiles.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ..commands.processor import Processor

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def docs_dir() -> str | None:
    """LANGUAGE.md and USER-GUIDE.md: bundled with a built app, or the repository's docs/."""
    for d in (os.path.join(PKG, "docs"), os.path.join(os.path.dirname(PKG), "docs")):
        if os.path.isfile(os.path.join(d, "LANGUAGE.md")):
            return d
    return None


def examples_dir() -> str | None:
    for d in (os.path.join(PKG, "examples"), os.path.join(os.path.dirname(PKG), "scripts")):
        if os.path.isdir(d) and any(n.endswith(".cmd") for n in os.listdir(d)):
            return d
    return None


# ---- search_docs ------------------------------------------------------------------------
@dataclass
class Doc:
    source: str  # "LANGUAGE.md", "skill", "example" ...
    title: str
    text: str
    ref: str  # section heading, skill name or file name


WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]*|\d+(?:\.\d+)?")
STOP = set("a an and are as at be by can do does for from has have how i in is it its of on or so that the "
           "then this to was what when where which with you your".split())


def _words(text: str) -> list[str]:
    return [w.lower() for w in WORD.findall(text) if w.lower() not in STOP]


def _sections(path: str, source: str) -> list[Doc]:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    out: list[Doc] = []
    head, buf = "", []
    for line in text.splitlines():
        if re.match(r"^#{2,3} ", line):
            if buf and head:
                out.append(Doc(source, head, "\n".join(buf).strip(), head))
            head, buf = line.lstrip("#").strip(), []
        else:
            buf.append(line)
    if buf and head:
        out.append(Doc(source, head, "\n".join(buf).strip(), head))
    return out


@lru_cache(maxsize=4)
def _corpus(project_dir: str = "") -> tuple[list[Doc], dict[str, float], float]:
    docs: list[Doc] = []
    d = docs_dir()
    if d:
        for name in ("LANGUAGE.md", "USER-GUIDE.md"):
            f = os.path.join(d, name)
            if os.path.isfile(f):
                docs += _sections(f, name)
    from . import skills as sk

    for s in sk.discover(project_dir).values():
        docs.append(Doc("skill", s.title, s.description + "\n\n" + s.body, s.name))
    ex = examples_dir()
    if ex:
        for n in sorted(os.listdir(ex)):
            if n.endswith(".cmd"):
                with open(os.path.join(ex, n), encoding="utf-8") as fh:
                    docs.append(Doc("example", n, fh.read(), n))
    # inverse document frequency of every word
    df: dict[str, int] = {}
    for doc in docs:
        for w in set(_words(doc.title + " " + doc.text)):
            df[w] = df.get(w, 0) + 1
    n = max(1, len(docs))
    idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
    avg = sum(len(_words(doc.text)) for doc in docs) / n
    return docs, idf, avg


def _score(doc: Doc, q: list[str], idf: dict[str, float], avg: float) -> float:
    """BM25 over the text, with the title counted three times."""
    words = _words(doc.text)
    title = _words(doc.title)
    tf: dict[str, int] = {}
    for w in words:
        tf[w] = tf.get(w, 0) + 1
    for w in title:
        tf[w] = tf.get(w, 0) + 3
    k1, b = 1.2, 0.75
    norm = k1 * (1 - b + b * len(words) / max(avg, 1.0))
    s = 0.0
    for w in q:
        f = tf.get(w, 0)
        if f:
            s += idf.get(w, 0.0) * f * (k1 + 1) / (f + norm)
    return s


def _trim(text: str, q: list[str], most: int) -> str:
    """The part of a long text around the lines that match, at most ``most`` characters."""
    if len(text) <= most:
        return text
    lines = text.splitlines()
    hits = [i for i, ln in enumerate(lines) if any(w in ln.lower() for w in q)]
    if not hits:
        return text[:most].rstrip() + "\n..."
    keep: list[int] = []
    for i in hits:
        for j in range(max(0, i - 2), min(len(lines), i + 4)):
            if j not in keep:
                keep.append(j)
    out, size, last = [], 0, -2
    for j in sorted(keep):
        if j != last + 1 and out:
            out.append("...")
        out.append(lines[j])
        size += len(lines[j]) + 1
        last = j
        if size > most:
            break
    return "\n".join(out)[:most + 200]


def search_docs(query: str, limit: int = 4, sources: list[str] | None = None, project_dir: str = "",
                most: int = 1500) -> dict[str, Any]:
    q = _words(query)
    if not q:
        raise ValueError("search_docs needs some words to look for")
    docs, idf, avg = _corpus(project_dir)
    if sources:
        want = {s.lower() for s in sources}
        docs = [d for d in docs if d.source.lower() in want
                or (d.source.endswith(".md") and ("docs" in want or d.source.lower().removesuffix(".md") in want))]
    ranked = sorted(((s, d) for d in docs if (s := _score(d, q, idf, avg)) > 0), key=lambda t: -t[0])
    rows = [{"source": d.source, "title": d.title, "ref": d.ref, "text": _trim(d.text, q, most)}
            for _s, d in ranked[:max(1, limit)]]
    out: dict[str, Any] = {"results": rows}
    if len(ranked) > limit:
        out["more"] = [f"{d.source}: {d.title}" for _s, d in ranked[limit:limit + 6]]
    if not rows:
        out["hint"] = "no match; try other words, or find_commands for command names"
    return out


# ---- parameters -------------------------------------------------------------------------
def _sets(text: str) -> set[str]:
    """The parameter names a history entry assigns at its top level."""
    from ..lang.script import Assign, ScriptError, parse

    try:
        stmts = parse(text)
    except ScriptError:
        return set()
    return {st.name.upper() for st in stmts if isinstance(st, Assign)}


def parameters(p: Processor) -> dict[str, Any]:
    from ..lang.expr import format_value

    rows = []
    setters: dict[str, list[int]] = {}
    for i, e in enumerate(p.history[:p.cursor], 1):
        for name in _sets(e.text):
            setters.setdefault(name, []).append(i)
    unknown_reads = []
    for name, value in p.params.items():
        key = name.upper()
        by = setters.get(key, [])
        readers, all_readers = [], []
        for i, e in enumerate(p.history[:p.cursor], 1):
            if i in by:
                continue
            r = e.reads
            if r is None:
                continue
            if r.params is None:
                all_readers.append(i)
            elif key in {k.upper() for k in r.params}:
                readers.append(i)
        row: dict[str, Any] = {"name": name, "value": format_value(value)}
        if by:
            row["set_by"] = by
            text = p.history[by[-1] - 1].text.strip().replace('"', "'")
            row["edit"] = f'HIST, EDIT, {by[-1]}, "' + text.replace("\n", "\\n") + '"'  # comments kept
        else:
            row["set_by"] = "not in the history (a -D value, a configuration or a loop variable)"
        row["read_by"] = readers
        if name in getattr(p, "drive", {}):
            row["driven"] = True
        rows.append(row)
        if all_readers:
            unknown_reads = all_readers
    out: dict[str, Any] = {"parameters": rows}
    if unknown_reads:
        out["note"] = (f"steps {', '.join(map(str, unknown_reads[:10]))} may read any parameter "
                       f"(they look at all of them)")
    if p.configs:
        out["configurations"] = {k: {n: format_value(v) for n, v in vals.items()} for k, vals in p.configs.items()}
    return out


# ---- sketch_state -----------------------------------------------------------------------
def sketch_state(p: Processor, name: str = "") -> dict[str, Any]:
    from ..sketch import profile as prof
    from ..sketch.sketch import SketchError

    m = p.model
    if not m.sketches:
        raise ValueError("there are no sketches")
    key = (name or m.active_sketch or "").strip().upper()
    if not key:
        return {"sketches": [{"name": s.name, "status": s.status()} for s in m.sketches.values()],
                "hint": "give a name for one sketch's details"}
    sk = m.sketches.get(key)
    if sk is None:
        raise ValueError(f"no sketch {name!r}; sketches: {', '.join(s.name for s in m.sketches.values())}")
    geos = []
    for n, g in sorted(sk.geos.items()):
        row: dict[str, Any] = {"n": n, "kind": g.kind.lower(), "is": sk.describe(n)}
        if g.construction:
            row["construction"] = True
        if not sk.fully_defined(g):
            row["free"] = True
        geos.append(row)
    cons = []
    for c in (sk.cons.values() if isinstance(sk.cons, dict) else sk.cons):
        row = {"c": c.n, "kind": c.kind, "on": list(c.refs)}
        if c.value is not None:
            row["value"] = c.value
        cons.append(row)
    out: dict[str, Any] = {"name": sk.name, "status": sk.status(), "dof": sk.dof,
                           "fully_defined": sk.dof == 0 and bool(sk.geos), "open": not sk.closed,
                           "geometry": geos, "constraints": cons}
    if sk.redundant:
        out["repeated"] = [f"C{n}" for n in sk.redundant]
    try:
        regs = prof.regions(sk)
        out["profiles"] = [{"area": round(abs(outer.area), 6), "holes": len(holes)} for outer, holes in regs]
    except SketchError as exc:
        out["profiles"] = []
        out["profile_problem"] = str(exc)
    used = getattr(sk, "used_by", None)
    if used:
        out["used_by"] = list(used) if not callable(used) else list(used())
    return out
