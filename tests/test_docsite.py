"""The user guide website (modeler/docsite.py): every command has an example
that runs, and the pages are made without broken links between them."""

import os
import re
import textwrap

import pytest

from modeler import docsite as D
from modeler.commands.processor import REGISTRY

EXAMPLES = D.read_examples()

try:  # pictures and fonts need Qt's GUI library, which needs libEGL; CI's plain Linux runners lack it
    from PySide6.QtGui import QImage  # noqa: F401
    QT_GUI = True
except ImportError:
    QT_GUI = False


def test_every_command_has_one_example():
    missing = sorted(set(REGISTRY) - set(EXAMPLES))
    assert not missing, f"add an example to docs/site/command-examples.cmd for: {missing}"
    gone = sorted(set(EXAMPLES) - set(REGISTRY))
    assert not gone, f"examples for commands that no longer exist: {gone}"


def test_each_example_uses_its_command_and_has_a_caption():
    for ex in EXAMPLES.values():
        assert D.uses_command(ex), f"the example for {ex.name} never runs {ex.name}"
        assert ex.caption, f"the example for {ex.name} has no caption (a ! line under its @ line)"


@pytest.mark.parametrize("name", [n for n, e in EXAMPLES.items() if "window" not in e.flags])
def test_example_runs(name):
    res = D.run_example(EXAMPLES[name])
    assert res, "the example ran nothing"
    last = res[-1]
    if not last.ok and not QT_GUI:
        pytest.skip(f"needs Qt's GUI library here: {last.message[:80]}")
    assert last.ok, f"command-examples.cmd:{EXAMPLES[name].line}: {last.line.splitlines()[0]}: {last.message}"


def _code_blocks(md: str) -> list[str]:
    return [textwrap.dedent(b) for b in re.findall(r"```text\n(.*?)```", md, flags=re.S)]


@pytest.mark.parametrize("page", ["index.md", "quick-start.md"])
def test_scripts_on_hand_written_pages_run(page):
    with open(os.path.join(D.SITE_SRC, page), encoding="utf-8") as f:
        blocks = _code_blocks(re.sub(r"^    ", "", f.read(), flags=re.M))
    assert blocks
    for code in blocks:
        res = D.run_example(D.Example("page", code))
        assert res and res[-1].ok, f"{page}: {res[-1].line}: {res[-1].message}"


def test_signature_shortens_long_optional_lists():
    assert D.short_signature(REGISTRY["BLOCK"]) == "BLOCK, x, y, z, dx, dy, dz"
    assert D.short_signature(REGISTRY["SPOLY"]) == "SPOLY, [v1], [v2] ..."


def test_help_text_examples_become_code():
    md = D._help_md(REGISTRY["HOLE"].help)
    assert "* `HOLE, plate, 20,10,5, 6` (through)" in md


def test_pages_link_only_to_pages_that_exist(tmp_path):
    D.build(str(tmp_path), run=False, log=lambda *_: None)
    docs = tmp_path / "docs"
    assert (tmp_path / "mkdocs.yml").exists()
    bad = []
    for path in docs.rglob("*.md"):
        text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
        for target in re.findall(r"\]\(([^)\s#]+\.(?:md|png|svg))(?:#[^)]*)?\)", text):
            if re.match(r"^[a-z]+:", target):
                continue
            if not (path.parent / target).resolve().exists():
                bad.append(f"{path.relative_to(docs)} -> {target}")
    assert not bad, "broken links:\n" + "\n".join(bad[:30])


def test_every_command_is_on_a_reference_page(tmp_path):
    D.build(str(tmp_path), run=False, log=lambda *_: None)
    text = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "docs" / "reference").glob("*.md"))
    missing = [n for n in REGISTRY if f"\n## {n}\n" not in text]
    assert not missing, missing


def test_every_guide_page_has_pictures(tmp_path):
    D.build(str(tmp_path), run=False, log=lambda *_: None)
    docs = tmp_path / "docs"
    bare = [str(p.relative_to(docs)) for p in docs.rglob("*.md")
            if p.parent.name in ("app", "language", "reference") and "img/" not in p.read_text(encoding="utf-8")]
    assert not bare, f"pages without a picture: {bare}"
    examples = (docs / "examples.md").read_text(encoding="utf-8")
    assert "<img src=" not in examples, "raw HTML pictures break under MkDocs' page folders"
