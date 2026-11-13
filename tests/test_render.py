"""Saving a picture of what a script makes (python -m modeler render)."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from modeler.render import Shot, parse_shots, render  # noqa: E402


def test_shots_file():
    shots = parse_shots("# c\na.png | | ISO\nparts/b.png | HIDE, 1; SHOW, 2 | 1,-1,0.5\nc.png\n")
    assert [s.file for s in shots] == ["a.png", "parts/b.png", "c.png"]
    assert shots[1].commands == ["HIDE, 1", "SHOW, 2"] and shots[1].view == "1,-1,0.5"
    assert shots[2].view == "ISO"


def test_render_saves_pictures(tmp_path):
    from PySide6.QtGui import QImage

    saved = render("BLOCK, 0,0,0, 10,10,10\nSEL, S, FACE, NORMAL, 0,0,1",
                   [Shot("iso.png", [], "ISO"), Shot("sub/top.png", ["CYL, 5,5,10, 2, 5"], "0,0,1")],
                   str(tmp_path), (320, 200), log=lambda *_: None)
    assert len(saved) == 2
    img = QImage(saved[1])
    assert (img.width(), img.height()) == (320, 200)
    # the part is drawn: the centre is not the background colour of a corner
    assert img.pixelColor(160, 100) != img.pixelColor(2, 2)


def test_render_reports_a_failing_script(tmp_path):
    with pytest.raises(RuntimeError, match="NOSUCH"):
        render("NOSUCH, 1", [Shot("x.png", [])], str(tmp_path), (64, 64), log=lambda *_: None)
