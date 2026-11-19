"""The user guide website: every page made from the docs, the command
registry and one tested example per command.

    python -m modeler docs            write the site's source to build/docs-site
    python -m modeler docs --serve    the same, then show it at http://127.0.0.1:8000
    python -m modeler docs --build    the same, then write the finished site to build/site
    python -m modeler docs --pictures remake the pictures of the examples marked "pic"
                                      (needs a screen; xvfb-run -a on Linux)
    python -m modeler docs --check    run every example and say which fail

The site is MkDocs with the Material theme (pip install mkdocs-material).
Nothing in build/ is kept in git: the pages are made again from

* docs/site/            hand-written pages (home, quick start), mkdocs.yml, style, screenshots
* docs/site/command-examples.cmd   one runnable example per command
* docs/USER-GUIDE.md    split into the "Using the app" pages
* docs/LANGUAGE.md      split into the "Command language" pages, one per section
* docs/EXAMPLES.md      the examples gallery, with its pictures
* the command registry  signature, help and arguments of every command

so a new command, argument or help text shows up on the website without
writing a page, and tests/test_docsite.py fails until it has an example.
"""

from __future__ import annotations

import os
import posixpath
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
SITE_SRC = os.path.join(DOCS, "site")
EXAMPLES_FILE = os.path.join(SITE_SRC, "command-examples.cmd")
EXAMPLE_FILES = os.path.join(SITE_SRC, "example-files")
PICTURES = os.path.join(SITE_SRC, "img", "commands")
OUT = os.path.join(ROOT, "build", "docs-site")
REPO = "https://github.com/shashanksingh097/3Dmodeling"
PIC_SIZE = (720, 480)


# ----------------------------------------------------------------- examples

@dataclass
class Example:
    name: str
    code: str
    caption: str = ""
    flags: set[str] = field(default_factory=set)
    line: int = 0  # where it starts in command-examples.cmd

    @property
    def picture(self) -> str:
        return slug(self.name) + ".png"


def read_examples(path: str = EXAMPLES_FILE) -> dict[str, Example]:
    """Command name -> its example, in file order. Text before the first "@" is the file's own notes."""
    out: dict[str, Example] = {}
    cur: Example | None = None
    body: list[str] = []

    def close():
        if cur is None:
            return
        while body and not body[-1].strip():
            body.pop()
        cap = []
        while body and body[0].lstrip().startswith("!"):
            cap.append(body.pop(0).strip().lstrip("!").strip())
        cur.caption = " ".join(cap)
        cur.code = "\n".join(body).rstrip() + "\n"
        out[cur.name] = cur

    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for n, line in enumerate(lines, 1):
        if line.startswith("@"):
            close()
            words = line[1:].split()
            cur = Example(words[0].upper(), "", flags=set(w.lower() for w in words[1:]), line=n)
            if cur.name in out:
                raise ValueError(f"command-examples.cmd:{n}: a second example for {cur.name}")
            body = []
        elif cur is not None:
            if line.startswith("! ====="):
                continue
            body.append(line)
    close()
    return out


def run_example(ex: Example, processor=None) -> list:
    """Run one example in a new model, in a fresh folder holding the example files.
    Returns the results; the last one is not ok when it failed."""
    from .commands import Processor

    p = processor or Processor()
    here = os.getcwd()
    with tempfile.TemporaryDirectory(prefix="m3d-doc-") as tmp:
        if os.path.isdir(EXAMPLE_FILES):
            for n in os.listdir(EXAMPLE_FILES):
                shutil.copy(os.path.join(EXAMPLE_FILES, n), tmp)
        os.chdir(tmp)
        try:
            return p.run_script(ex.code)
        finally:
            os.chdir(here)


def uses_command(ex: Example) -> bool:
    """The example has a line that runs its own command."""
    for line in ex.code.splitlines():
        text = line.split("!")[0].strip()
        head = re.split(r"[\s,]", text, maxsplit=1)[0].upper() if text else ""
        if head == ex.name:
            return True
    return False


# ----------------------------------------------------------------- helpers

def slug(text: str) -> str:
    """The anchor MkDocs gives a heading (its default toc slugify)."""
    import unicodedata

    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[-\s]+", "-", s)


def short_signature(c) -> str:
    """BLOCK, x, y, z ... with a long run of optional v1, v2 ... written once."""
    parts = [c.name]
    args = list(c.args)
    i = 0
    while i < len(args):
        a = args[i]
        m = re.fullmatch(r"([a-z]+)(\d+)", a.name)
        if m and a.default is not None:
            stem = m.group(1)
            j = i
            while j < len(args) and re.fullmatch(stem + r"\d+", args[j].name) and args[j].default is not None:
                j += 1
            if j - i > 3:
                parts.append(f"[{args[i].name}], [{args[i + 1].name}] ...")
                i = j
                continue
        parts.append(a.name if a.default is None else f"[{a.name}]")
        i += 1
    return ", ".join(parts)


_ARG = r'\s*(?:"[^"]*"|\([^()]*\)|\[[^\]]*\]|[^\s,()\[\]]*)'
_CALL = re.compile(r"^([*/]?[A-Z][A-Z0-9_]*(?:," + _ARG + r")*(?:\s*\[[^\]]*\])*)(.*)$", re.S)


def _code_call(bit: str) -> str:
    """'HOLE, plate, 20,10,5, 6 (through)' -> '`HOLE, plate, 20,10,5, 6` (through)'."""
    from .commands.processor import REGISTRY

    m = _CALL.match(bit.strip())
    if not m or m.group(1).split(",")[0].strip() not in REGISTRY or "`" in bit:
        return bit
    call, rest = m.group(1).rstrip(), m.group(2)
    if rest and not rest[0] in " .;":
        return bit
    return f"`{call}`" + rest


def _help_md(text: str) -> str:
    """A command's help text as Markdown: its " · " separated examples on lines of their own,
    the commands in them as code."""
    bits = [b.strip() for b in text.split(" · ")]
    first = bits[0]
    m = re.match(r"^(.*?[:.]\s)([*/]?[A-Z][A-Z0-9_]*,.*)$", first)
    if m and len(bits) > 1:
        lead, call = m.group(1), m.group(2)
        bits = [lead.rstrip()] + [call] + bits[1:]
    elif m:
        return m.group(1) + _code_call(m.group(2))
    if len(bits) == 1:
        return text
    return bits[0] + "\n\n" + "\n".join(f"* {_code_call(b)}" for b in bits[1:])


GROUP_INTRO = {
    "Parameters": "Named numbers and families of sizes. A parameter is set with `NAME = value`; any number in any command can be an expression of parameters.",
    "Solids": "Basic solid shapes. The numbers are positions and sizes in the model's unit (mm by default).",
    "Sketch": "2D sketches held by constraints and sizes, pushed or turned into solids. The commands used inside an open sketch are under [Inside a sketch](inside-a-sketch.md).",
    "Curves": "Curves in space: paths for sweeps and pipes, rails, sections for lofts.",
    "Profiles": "Flat closed curves, the sections of lofts and sweeps.",
    "Shapes from curves": "Solids and surfaces made by moving or blending curves.",
    "Freeform (NURBS)": "Curves and surfaces you shape by their control points, and tools to join, trim and check smooth surfaces.",
    "Combine": "Booleans: join bodies, cut one from another, keep what they share.",
    "Features": "Holes, rounds, shells and other features made on an existing part.",
    "Select": "Select faces, edges, vertices or bodies by what they are, so a script keeps working when sizes change.",
    "Check": "Answers about the model in words and numbers, and checks that make a step fail when they do not hold.",
    "Inside a sketch": "These commands work while a sketch is open (after `SKETCH`, before `ENDSKETCH`). Curves are numbered 1, 2, 3 ... in the order they are made; `3.S`, `3.E` and `3.C` are the start, end and centre of curve 3, and `ORIGIN` (or `O`) is the sketch's origin.",
}


# ----------------------------------------------------------------- reference pages

def _groups():
    from .gui.catalog import groups

    return groups()


def reference_pages(examples: dict[str, Example], outputs: dict[str, list[str]] | None = None,
                    pictures: set[str] | None = None) -> dict[str, str]:
    """reference/<group>.md for every heading, and reference/index.md."""
    from .commands.processor import REGISTRY
    from .gui import catalog
    from .gui import forms as F

    outputs = outputs or {}
    pictures = pictures if pictures is not None else _existing_pictures()
    script_lines = catalog.examples()
    pages: dict[str, str] = {}
    where = {n: slug(cat) for cat, names in _groups() for n in names}
    index = ["# Command reference", "",
             f"Every command of the app, {len(REGISTRY)} of them, under the same headings as the "
             "**Commands** menu. Each one has the way to type it, what every argument means and "
             "a small example you can paste into the command line (each example is run by the "
             "tests, so it works as shown). Square brackets mark optional arguments.", "",
             "In the app, **Help > Command reference** (Ctrl+F1) shows the same, and "
             "`HELP, name` prints it in the output.", ""]
    for cat, names in _groups():
        page = slug(cat)
        index.append(f"## [{cat}]({page}.md)\n")
        index.append(" · ".join(f"[`{n}`]({page}.md#{slug(n)})" for n in names) + "\n")
        out = [f"# {cat}", ""]
        if cat in GROUP_INTRO:
            out += [_link_commands(GROUP_INTRO[cat], where, page), ""]
        out += [" · ".join(f"[`{n}`](#{slug(n)})" for n in names), ""]
        for n in names:
            c = REGISTRY[n]
            out += [f"## {n}", "", f"```text\n{short_signature(c)}\n```", "",
                    _link_commands(_help_md(c.help), where, page, skip=n), ""]
            rows = [a for a in c.args if a.help or a.default is not None]
            if rows and not re.search(r"\[v\d+\], \[v\d+\] \.\.\.", short_signature(c)) or (
                    rows and len(rows) <= 6):
                out += ["| Argument | Default | Meaning |", "|---|---|---|"]
                for a in c.args:
                    d = "" if a.default is None else f"`{a.default}`" if str(a.default) != "" else "empty"
                    out.append(f"| `{a.name}` | {d} | {(a.help or '').replace('|', '/')} |")
                out.append("")
            ex = examples.get(n)
            if ex:
                out += ["**Example**" + (f": {ex.caption}" if ex.caption else ""), "",
                        "```text\n" + ex.code.rstrip() + "\n```", ""]
                said = outputs.get(n)
                if said:
                    out += ['??? note "What it prints"', "",
                            "    ```text\n" + "\n".join("    " + s for s in said) + "\n    ```", ""]
                if ex.picture in pictures:
                    out += [f"![{n} example](../img/commands/{ex.picture}){{ loading=lazy width=480 }}", ""]
                if "window" in ex.flags:
                    out += ["!!! info \"Runs in the app\"\n    This command needs the app's 3D view.", ""]
            lines = [(f, t) for f, t in script_lines.get(n, []) if not ex or t.strip() not in ex.code][:3]
            if lines:
                out.append("From the example scripts:\n")
                out += [f"* `{t}` in [{f}]({REPO}/blob/main/scripts/{f})" for f, t in lines]
                out.append("")
            try:
                F.spec(n)
                out += [f"*In the app: **Commands > {cat}**, or type `{n}` and press F2 for its form.*", ""]
            except F.FormError:
                pass
        pages[f"reference/{page}.md"] = "\n".join(out)
    pages["reference/index.md"] = "\n".join(index)
    return pages


def _link_commands(text: str, where: dict[str, str], page: str, skip: str = "", prefix: str = "") -> str:
    """`NAME ...` in back quotes becomes a link to the command's reference entry."""

    def link(m: re.Match) -> str:
        word = m.group(1)
        head = re.split(r"[\s,]", word.strip(), maxsplit=1)[0]
        if head != head.upper() or head not in where or head == skip:
            return m.group(0)
        target = f"{prefix}{where[head]}.md" if where[head] != page or prefix else ""
        return f"[`{word}`]({target}#{slug(head)})"

    # only outside fenced code
    parts = re.split(r"(```.*?```)", text, flags=re.S)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"(?<![`\[])`([^`\n]+)`(?![`\]])", link, parts[i])
    return "".join(parts)


def _existing_pictures() -> set[str]:
    return set(os.listdir(PICTURES)) if os.path.isdir(PICTURES) else set()


# ----------------------------------------------------------------- guide pages from the Markdown docs

@dataclass
class Section:
    title: str  # without its number
    slug_old: str  # the anchor the heading had in the big file
    body: str
    path: str = ""  # page path in the site


def split_doc(text: str) -> tuple[str, list[Section]]:
    """The text before the first "## " heading, and one section per "## " heading."""
    parts = re.split(r"^## (.+)$", text, flags=re.M)
    head = parts[0]
    out = []
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1]
        plain = re.sub(r"^\d+\.\s*", "", title)
        out.append(Section(plain, _gh_slug(title), body))
    return head, out


def _gh_slug(title: str) -> str:
    """The anchor GitHub gives a heading (the links inside the docs use these)."""
    s = title.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def _section_page(sec: Section, where: dict[str, str]) -> str:
    body = sec.body.strip("\n")
    body = re.sub(r"^---\s*$", "", body, flags=re.M).rstrip()
    # one heading level up: ### becomes ##
    body = re.sub(r"^(#{3,6}) ", lambda m: m.group(1)[1:] + " ", body, flags=re.M)
    return f"# {sec.title}\n\n" + body + "\n"


def _rewrite_links(md: str, page: str, anchors: dict[tuple[str, str], tuple[str, str]],
                   files: dict[str, str]) -> str:
    """Make the big files' links work between the split pages.

    anchors: (source file, old anchor) -> (page, new anchor); files: source file -> its first page."""
    here = posixpath.dirname(page)

    def rel(target: str) -> str:
        return posixpath.relpath(target, here or ".")

    def fix(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        if re.match(r"^[a-z]+:", url):
            return m.group(0)
        path, _, frag = url.partition("#")
        src = {"": CURRENT[0]}.get(path, path.split("/")[-1] if path.endswith(".md") else path)
        if src in files or (not path and frag):
            key = (src, frag)
            if frag and key in anchors:
                p, a = anchors[key]
                return f"[{label}]({rel(p)}{'#' + a if a else ''})"
            if src in files:
                return f"[{label}]({rel(files[src])})"
        if path.startswith("../scripts/") or path.startswith("../"):
            return f"[{label}]({REPO}/blob/main/{path[3:]}{'#' + frag if frag else ''})"
        if path.endswith(".md") and posixpath.basename(path) not in files:
            return f"[{label}]({REPO}/blob/main/docs/{path}{'#' + frag if frag else ''})"
        if path.startswith("examples/") or path.startswith("../docs/examples/"):
            return f"[{label}]({rel('examples/' + posixpath.basename(path))})"
        return m.group(0)

    parts = re.split(r"(```.*?```)", md, flags=re.S)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)", fix, parts[i])
        parts[i] = re.sub(r"!\[([^\]]*)\]\((?:\.\./docs/)?examples/([^)\s]+)\)",
                          lambda m: f"![{m.group(1)}]({rel('examples/' + m.group(2))})", parts[i])
    return "".join(parts)


CURRENT = [""]  # the source file being rewritten (for links that are only #anchor)

# The "Command language" pages, in groups, by section number of docs/LANGUAGE.md
LANGUAGE_GROUPS: list[tuple[str, list[int]]] = [
    ("Basics", [1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12]),
    ("Shapes", [9, 13, 14, 16, 18, 19, 20, 21, 24]),
    ("Parts and assemblies", [17, 30, 33, 35]),
    ("Organise and check", [15, 22, 23, 44]),
    ("Meshes, scans and sculpting", [25, 26, 27, 28, 29, 34]),
    ("Special parts", [31, 32, 36, 41, 42, 43, 45]),
    ("Strength, making and pictures", [37, 38, 39, 40]),
]
# The "Using the app" pages: docs/USER-GUIDE.md section numbers
GUIDE_GROUPS: list[tuple[str, list[int]]] = [
    ("Getting started", [1, 2, 3, 4, 5]),
    ("Working in the app", [6, 7, 8, 9, 10, 11, 12, 13, 14]),
    ("The assistant", [15]),
]


def guide_pages() -> tuple[dict[str, str], list, list]:
    """Pages from USER-GUIDE.md and LANGUAGE.md, and their nav entries."""
    docs = {
        "USER-GUIDE.md": ("app", GUIDE_GROUPS),
        "LANGUAGE.md": ("language", LANGUAGE_GROUPS),
    }
    split: dict[str, tuple[str, list[Section]]] = {}
    anchors: dict[tuple[str, str], tuple[str, str]] = {}
    files: dict[str, str] = {}
    for src, (folder, _) in docs.items():
        with open(os.path.join(DOCS, src), encoding="utf-8") as f:
            head, secs = split_doc(f.read())
        split[src] = (head, secs)
        files[src] = f"{folder}/index.md"
        for sec in secs:
            sec.path = f"{folder}/{slug(sec.title)}.md"
            anchors[(src, sec.slug_old)] = (sec.path, "")
            for m in re.finditer(r"^#{3,6} (.+)$", sec.body, flags=re.M):
                anchors[(src, _gh_slug(m.group(1)))] = (sec.path, slug(m.group(1)))
    files["EXAMPLES.md"] = "examples.md"
    pages: dict[str, str] = {}
    navs = []
    for src, (folder, groups) in docs.items():
        head, secs = split[src]
        CURRENT[0] = src
        number = {i + 1: s for i, s in enumerate(secs)}
        nav = []
        listed = set()
        for title, nums in groups:
            entries = []
            for k in nums:
                if k in number:
                    s = number[k]
                    entries.append({s.title: s.path})
                    listed.add(k)
            nav.append({title: entries})
        rest = [number[k] for k in number if k not in listed]
        if rest:
            nav.append({"More": [{s.title: s.path} for s in rest]})
        for s in secs:
            pages[s.path] = _rewrite_links(_section_page(s, {}), s.path, anchors, files)
        # the folder's index: the file's opening text and a list of its pages
        intro = re.sub(r"^Contents:.*", "", head, flags=re.S | re.M).strip()
        intro = re.sub(r"^# .*\n", "", intro).strip()
        lines = [f"# {'Using the app' if folder == 'app' else 'The command language'}", "",
                 _rewrite_links(intro, files[src], anchors, files), ""]
        for title, nums in groups:
            lines.append(f"## {title}\n")
            lines += [f"* [{number[k].title}]({posixpath.basename(number[k].path)})" for k in nums if k in number]
            lines.append("")
        pages[files[src]] = "\n".join(lines)
        navs.append(nav)
    CURRENT[0] = ""
    return pages, navs[0], navs[1]


def link_commands_in_pages(pages: dict[str, str]) -> None:
    """In the guide pages, `NAME, ...` in back quotes links to the command reference."""
    where = {n: slug(cat) for cat, names in _groups() for n in names}
    for path, md in pages.items():
        if path.startswith("reference/"):
            continue
        depth = path.count("/")
        prefix = "../" * depth + "reference/"
        pages[path] = _link_commands(md, where, "", prefix=prefix)


def examples_page() -> str:
    with open(os.path.join(DOCS, "EXAMPLES.md"), encoding="utf-8") as f:
        md = f.read()
    CURRENT[0] = "EXAMPLES.md"
    md = _rewrite_links(md, "examples.md", {}, {"EXAMPLES.md": "examples.md"})
    CURRENT[0] = ""
    # pictures: the gallery's are copied next to the page, in examples/
    return md.replace("](examples/", "](examples/")


# ----------------------------------------------------------------- putting it together

def run_all(examples: dict[str, Example], log=print) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Run every example (but the ones that need the window): what each printed, and the failures."""
    said: dict[str, list[str]] = {}
    bad: dict[str, str] = {}
    for ex in examples.values():
        if "window" in ex.flags:
            continue
        t = time.time()
        try:
            res = run_example(ex)
        except Exception as exc:  # noqa: BLE001  (a crash is a failure to report)
            bad[ex.name] = f"crashed: {exc}"
            continue
        if res and not res[-1].ok:
            bad[ex.name] = f"{res[-1].line.splitlines()[0]}: {res[-1].message}"
            continue
        mine = [r for r in res if r.line.split(",")[0].strip().upper() == ex.name and r.message]
        tail = mine[-2:] if mine else res[-1:]
        lines = []
        for r in tail:
            lines.append("> " + r.line.splitlines()[0])
            lines += [s for s in r.message.splitlines()[:14]]
        said[ex.name] = lines
        if time.time() - t > 5:
            log(f"  {ex.name}: {time.time() - t:.1f} s")
    return said, bad


def nav_yaml(nav, indent: int = 2) -> str:
    out = []
    pad = " " * indent
    for item in nav:
        if isinstance(item, str):
            out.append(f"{pad}- {item}")
            continue
        (k, v), = item.items()
        if isinstance(v, list):
            out.append(f"{pad}- {_q(k)}:")
            out.append(nav_yaml(v, indent + 4))
        else:
            out.append(f"{pad}- {_q(k)}: {v}")
    return "\n".join(out)


def _q(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"'


def _shown_path(path: str) -> str:
    """path from the repository when it is inside it (on Windows it may be on another drive)."""
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return path


def build(out: str = OUT, run: bool = True, log=print) -> dict[str, str]:
    """Write the site's source (Markdown pages and mkdocs.yml) to out. Returns the failing examples."""
    examples = read_examples()
    said, bad = run_all(examples, log) if run else ({}, {})
    pages: dict[str, str] = {}
    gp, app_nav, lang_nav = guide_pages()
    pages.update(gp)
    pages["examples.md"] = examples_page()
    link_commands_in_pages(pages)
    pages.update(reference_pages(examples, said))
    if os.path.isdir(out):
        shutil.rmtree(out)
    docs_out = os.path.join(out, "docs")
    # hand-written pages, style and screenshots
    for dirpath, _, names in os.walk(SITE_SRC):
        rel = os.path.relpath(dirpath, SITE_SRC)
        if rel.startswith("example-files"):
            continue
        for n in names:
            if n in ("mkdocs.yml", "command-examples.cmd"):
                continue
            dst = os.path.join(docs_out, rel, n)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(os.path.join(dirpath, n), dst)
    os.makedirs(os.path.join(docs_out, "examples"), exist_ok=True)
    for n in os.listdir(os.path.join(DOCS, "examples")):
        if n.endswith(".png"):
            shutil.copy(os.path.join(DOCS, "examples", n), os.path.join(docs_out, "examples", n))
    hand = {}
    for path in ("index.md", "quick-start.md"):
        with open(os.path.join(SITE_SRC, path), encoding="utf-8") as f:
            hand[path] = f.read()
    link_commands_in_pages(hand)
    pages.update(hand)
    for path, md in pages.items():
        dst = os.path.join(docs_out, path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
    ref_nav = [{"All commands": "reference/index.md"}] + [
        {cat: f"reference/{slug(cat)}.md"} for cat, _ in _groups()]
    nav = [
        {"Home": "index.md"},
        {"Quick start": "quick-start.md"},
        {"Using the app": [{"Overview": "app/index.md"}] + app_nav},
        {"Command language": [{"Overview": "language/index.md"}] + lang_nav},
        {"Command reference": ref_nav},
        {"Examples": "examples.md"},
    ]
    with open(os.path.join(SITE_SRC, "mkdocs.yml"), encoding="utf-8") as f:
        base = f.read()
    with open(os.path.join(out, "mkdocs.yml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(base.rstrip() + "\n\nnav:\n" + nav_yaml(nav) + "\n")
    log(f"wrote {len(pages)} pages to {_shown_path(out)}"
        + (f"; {len(bad)} examples failed" if bad else ""))
    return bad


# ----------------------------------------------------------------- pictures

def render_pictures(names: list[str] | None = None, log=print) -> None:
    """A picture of what each example marked "pic" makes (docs/site/img/commands)."""
    from .render import Shot, render

    os.makedirs(PICTURES, exist_ok=True)
    here = os.getcwd()
    for ex in read_examples().values():
        if "pic" not in ex.flags or (names and ex.name not in names):
            continue
        t = time.time()
        with tempfile.TemporaryDirectory(prefix="m3d-pic-") as tmp:
            for n in os.listdir(EXAMPLE_FILES) if os.path.isdir(EXAMPLE_FILES) else []:
                shutil.copy(os.path.join(EXAMPLE_FILES, n), tmp)
            os.chdir(tmp)
            try:
                render(ex.code, [Shot(ex.picture, ["FIT"], "ISO")], PICTURES, PIC_SIZE, log=lambda *_: None)
            finally:
                os.chdir(here)
        log(f"{ex.picture}: {time.time() - t:.1f} s")


def main(args: list[str]) -> int:
    if "--screens" in args:
        take_screens()
        sys.stdout.flush()
        os._exit(0)  # closing the window would ask about unsaved work
    if "--pictures" in args:
        if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
            print("no screen: run under Xvfb, e.g. xvfb-run -a python -m modeler docs --pictures")
            return 2
        render_pictures([a.upper() for a in args if not a.startswith("--")] or None)
        return 0
    if "--check" in args:
        _, bad = run_all(read_examples())
        for n, why in bad.items():
            print(f"{n}: {why}")
        print(f"{len(bad)} failed" if bad else "every example runs")
        return 1 if bad else 0
    bad = build(run="--fast" not in args)
    for n, why in bad.items():
        print(f"example {n} failed: {why}")
    if bad:
        return 1
    if "--serve" in args or "--build" in args:
        import subprocess

        cmd = [sys.executable, "-m", "mkdocs", "serve" if "--serve" in args else "build",
               "-f", os.path.join(OUT, "mkdocs.yml")]
        if "--build" in args:
            cmd += ["-d", os.path.join(ROOT, "build", "site"), "--strict"]
        return subprocess.call(cmd)
    return 0


# ----------------------------------------------------------------- screenshots of the window

SCREENS = os.path.join(SITE_SRC, "img", "app")


def take_screens(log=print) -> None:
    """Full-window pictures for the guide's pages (docs/site/img/app). Needs a screen (Xvfb)."""
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from .gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    os.makedirs(SCREENS, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="m3d-shots-")
    settings = QSettings(os.path.join(tmp, "settings.ini"), QSettings.IniFormat)
    win = MainWindow(settings=settings, autosave="off")
    win.move(0, 0)
    win.resize(1500, 940)
    win.show()

    def pump(n: int = 10) -> None:
        for _ in range(n):
            app.processEvents()
            time.sleep(0.02)

    for _ in range(200):
        pump(1)
        if win.viewport._initialized:
            break

    def shot(name: str, widget=None) -> None:
        pump(30)
        w = widget or win
        screen = QGuiApplication.primaryScreen()
        g = w.frameGeometry()
        pic = screen.grabWindow(0, g.x(), g.y(), g.width(), g.height())
        pic.save(os.path.join(SCREENS, name))
        log(f"{name}: {pic.width()} x {pic.height()}")

    def run(text: str) -> None:
        res = win.processor.run_script(text)
        if res and not res[-1].ok:
            raise RuntimeError(f"{res[-1].line}: {res[-1].message}")
        pump(20)

    with open(os.path.join(ROOT, "scripts", "flange.cmd"), encoding="utf-8") as f:
        run(f.read())
    win.execute("VIEW, ISO")
    win.execute("FIT")
    shot("window.png")

    win.execute("NEW")
    run("BLOCK, 0,0,0, 80, 50, 8\nNAME, LAST, plate\nPLANE, top, XY, 8")
    for line in ("SKETCH, boss, top", "SRECT, 10, 10, 50, 40", "SCIRCLE, 65, 25, 8",
                 "SDIM, LENGTH, 1, 40", "SDIM, RADIUS, 5, 8"):
        win.execute(line)
    win.execute("FIT")
    shot("sketch.png")
    win.execute("ENDSKETCH")

    from .gui.form_dialog import open_form

    win.execute("VIEW, ISO")
    win.execute("FIT")
    win.execute("PICK, FACE, 6")
    dlg = open_form(win, "HOLE")
    dlg.move(800, 190)
    shot("form.png")
    dlg.close()

    help_dlg = win.shell.show_command_reference("HOLE") if hasattr(win, "shell") else None
    if help_dlg is not None:
        help_dlg.move(260, 120)
        shot("help.png", help_dlg)
        help_dlg.close()
    shutil.rmtree(tmp, ignore_errors=True)
