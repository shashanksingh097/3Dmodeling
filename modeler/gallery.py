"""The examples gallery: a picture and the exact script for every example.

    python -m modeler gallery              remake every picture and docs/EXAMPLES.md
    python -m modeler gallery flange plate remake only these pictures (and the page)
    python -m modeler gallery --page       remake only docs/EXAMPLES.md

``docs/examples/gallery.txt`` lists the examples in the order the page shows
them, one per line:

    script.cmd | Title | view | command; command

``view`` and the commands are as in a shots file (see modeler/render.py);
the commands run after the script, only for the picture (for example to
hide a helper body). The page takes each script's opening comment as its
description, and the numbers a reader should get (bodies, volume) from
tests/corpus/scripts.json, which CI checks against the scripts on every
change. So a picture, its script and its numbers cannot drift apart
without a test failing.

Run it from a source checkout, under Xvfb on Linux without a screen.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
DOCS = os.path.join(ROOT, "docs")
PICTURES = os.path.join(DOCS, "examples")
LIST = os.path.join(PICTURES, "gallery.txt")
PAGE = os.path.join(DOCS, "EXAMPLES.md")
NUMBERS = os.path.join(ROOT, "tests", "corpus", "scripts.json")
SIZE = (1200, 800)


@dataclass
class Example:
    script: str  # file name in scripts/
    title: str
    view: str = "ISO"
    commands: str = ""

    @property
    def stem(self) -> str:
        return os.path.splitext(self.script)[0]

    @property
    def picture(self) -> str:
        return self.stem + ".png"


def read_list(path: str = LIST) -> list[Example]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [s.strip() for s in line.split("|")] + ["", "", ""]
            out.append(Example(parts[0], parts[1] or parts[0], parts[2] or "ISO", parts[3]))
    return out


def description(script_text: str) -> str:
    """The comment lines at the top of a script, joined into a paragraph."""
    lines = []
    for line in script_text.splitlines():
        s = line.strip()
        if not s:
            if lines:
                break
            continue
        if not s.startswith("!"):
            break
        lines.append(s.lstrip("!").strip())
    return " ".join(x for x in lines if x)


def page(examples: list[Example]) -> str:
    """The text of docs/EXAMPLES.md."""
    with open(NUMBERS, encoding="utf-8") as f:
        numbers = json.load(f)
    out = [
        "# Examples",
        "",
        "Every example below is one script in [scripts/](../scripts). Run it and you get the part in the",
        "picture: the numbers under each picture (bodies and volume) are what the script makes, and CI",
        "checks them on every change. Each script is plain text, so read it, change a number at the top,",
        "and run it again.",
        "",
        "**To run one:** in the app, **File > Open example**, then pick it. Or from a terminal:",
        "",
        "```bash",
        "python -m modeler scripts/flange.cmd             # the app, with the model built",
        "python -m modeler run scripts/flange.cmd         # headless: prints every step",
        "python -m modeler run scripts/flange.cmd -D N_BOLTS=8 -q   # with a parameter changed",
        "```",
        "",
        "In the downloaded app, use `3Dmodeling-cli` in place of `python -m modeler`. To check the result,",
        "type `LIST` (bodies) or `MASSPROP` (volume) in the command line.",
        "",
        "The pictures are made by the scripts themselves: `python -m modeler gallery` runs each one and",
        "saves the 3D view (see `modeler/gallery.py`).",
        "",
        "| | Example |",
        "|---|---|",
    ]
    for ex in examples:
        out.append(f"| [<img src=\"examples/{ex.picture}\" width=\"160\">](#{_anchor(ex.title)}) | "
                   f"[{ex.title}](#{_anchor(ex.title)}) |")
    out.append("")
    for ex in examples:
        with open(os.path.join(SCRIPTS, ex.script), encoding="utf-8") as f:
            text = f.read()
        n = numbers.get(ex.script, {})
        out += [
            "---",
            "",
            f"## {ex.title}",
            "",
            f"![{ex.title}](examples/{ex.picture})",
            "",
            description(text),
            "",
            f"**Script:** [scripts/{ex.script}](../scripts/{ex.script}) "
            f"({len(text.splitlines())} lines) · **Run:** `python -m modeler scripts/{ex.script}`",
            "",
        ]
        if n:
            out += [f"**You should get:** {n['bodies']} bod{'y' if n['bodies'] == 1 else 'ies'}, "
                    f"volume {n['volume']:,.1f} mm³" + ("" if n.get("faces") is None else f", {n['faces']} faces"),
                    ""]
        out += [
            "<details><summary>The whole script</summary>",
            "",
            "```text",
            text.rstrip("\n"),
            "```",
            "",
            "</details>",
            "",
        ]
    return "\n".join(out)


def _anchor(title: str) -> str:
    keep = "".join(c for c in title.lower() if c.isalnum() or c in " -")
    return keep.strip().replace(" ", "-")


def render_pictures(examples: list[Example], log=print) -> None:
    from .render import Shot, render

    for ex in examples:
        with open(os.path.join(SCRIPTS, ex.script), encoding="utf-8") as f:
            text = f.read()
        cmds = [c.strip() for c in ex.commands.split(";") if c.strip()]
        t = time.time()
        render(text, [Shot(ex.picture, cmds, ex.view)], PICTURES, SIZE, log=lambda *_: None)
        log(f"{ex.picture}: {time.time() - t:.1f} s")


def main(args: list[str]) -> int:
    examples = read_list()
    if "--page" not in args:
        wanted = {a.removesuffix(".cmd") for a in args}
        todo = [ex for ex in examples if not wanted or ex.stem in wanted]
        unknown = wanted - {ex.stem for ex in examples}
        if unknown:
            print(f"not in {os.path.relpath(LIST, ROOT)}: {', '.join(sorted(unknown))}")
            return 2
        if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
            print("no screen: run under Xvfb, e.g. xvfb-run -a python -m modeler gallery")
            return 2
        render_pictures(todo)
    with open(PAGE, "w", encoding="utf-8", newline="\n") as f:
        f.write(page(examples))
    print(f"wrote {os.path.relpath(PAGE, ROOT)}")
    return 0
