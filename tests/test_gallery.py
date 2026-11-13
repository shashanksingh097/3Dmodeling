"""The examples gallery stays in step with the scripts: every example has a
picture and an entry, and docs/EXAMPLES.md is what `modeler gallery` writes.
(test_corpus.py checks that each script still makes the numbers shown.)"""

import json
import os

from modeler import gallery as G


def test_every_script_is_in_the_gallery():
    listed = {ex.script for ex in G.read_list()}
    scripts = {n for n in os.listdir(G.SCRIPTS) if n.endswith(".cmd")}
    missing = sorted(scripts - listed)
    assert not missing, (f"add these to docs/examples/gallery.txt, then run "
                         f"`python -m modeler gallery NAME`: {missing}")
    assert not listed - scripts, f"gallery.txt lists scripts that are gone: {sorted(listed - scripts)}"


def test_every_example_has_a_picture_and_numbers():
    with open(G.NUMBERS, encoding="utf-8") as f:
        numbers = json.load(f)
    for ex in G.read_list():
        pic = os.path.join(G.PICTURES, ex.picture)
        assert os.path.getsize(pic) > 5000, f"no picture for {ex.script}: run `python -m modeler gallery {ex.stem}`"
        assert ex.script in numbers, f"{ex.script} has no numbers: run `python tests/test_corpus.py --update`"


def test_page_is_up_to_date():
    with open(G.PAGE, encoding="utf-8") as f:
        on_disk = f.read()
    assert on_disk == G.page(G.read_list()), "docs/EXAMPLES.md is stale: run `python -m modeler gallery --page`"


def test_description_is_the_opening_comment():
    text = "! A plate.\n! Change W.\n\nW = 1\n! not this\n"
    assert G.description(text) == "A plate. Change W."
