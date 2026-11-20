"""Drawings that follow the model (PLAN item 61): sheets kept in the history (DRAWSHEET), several
sheets written as one PDF (DRAWINGS), written again after a rebuild and a save (AUTO), title block
templates, and sizes pinned to the model checked against it."""

import os
import re

import pytest

from modeler.commands import Processor

MODEL = """W = 40
BLOCK, 0,0,0, W, 20, 10
NAME, LAST, plate
CYL, 10,10,-1, 3, 12
SUBTRACT, plate, LAST"""


@pytest.fixture
def p():
    q = Processor()
    ok(q, MODEL)
    return q


def ok(p, text):
    res = p.run_script(text)
    bad = [r for r in res if not r.ok]
    assert not bad, f"{bad[0].line}: {bad[0].message}"
    return res[-1]


def pages(path):
    data = open(path, "rb").read()  # noqa: SIM115
    return int(re.search(rb"/Count (\d+)", data).group(1)), data


def test_several_sheets_make_one_pdf(p, tmp_path):
    ok(p, "DRAWSHEET, views, STANDARD\nDRAWSHEET, plan, TOP, 0, OVERALL, A3, 1:1\n"
          'DRAWSHEET, cut, FRONT, 0, NONE, A4, , "Y 10"')
    path = str(tmp_path / "plate.pdf")
    msg = p.run(f'DRAWINGS, "{path}"').message
    assert "wrote 3 sheets" in msg and "sheet 2 plan: top, 2 sizes, A3 at 1:1" in msg
    n, data = pages(path)
    assert n == 3 and b"SHEET 1 of 3" in data and b"SHEET 3 of 3" in data
    assert "3 sheets:" in p.run("DRAWINGS").message
    # one SVG per sheet
    msg = p.run(f'DRAWINGS, "{tmp_path / "plate.svg"}"').message
    assert sorted(f for f in os.listdir(tmp_path) if f.endswith(".svg")) == [
        "plate_cut.svg", "plate_plan.svg", "plate_views.svg"]


def test_the_sheets_follow_the_model_and_auto_writes_again(p, tmp_path):
    ok(p, "DRAWSHEET, plan, TOP, 0, OVERALL, A3, 1:1")
    path = str(tmp_path / "plate.pdf")
    ok(p, f'DRAWINGS, "{path}", AUTO')
    _n, before = pages(path)
    assert b"(40) Tj" in before
    ok(p, 'HIST, EDIT, 1, "W = 55"')  # a rebuild: the PDF is written again with the new size
    _n, after = pages(path)
    assert b"(55) Tj" in after and b"(40) Tj" not in after
    # kept through save and open, and written again on save
    proj = str(tmp_path / "p.m3d")
    os.remove(path)
    ok(p, f'SAVE, "{proj}"')
    assert os.path.exists(path)
    q = Processor()
    ok(q, f'OPEN, "{proj}"')
    assert q.drawings_auto == path and "plan" in q.run("DRAWINGS").message.lower()
    assert "no longer written" in q.run("DRAWINGS, , OFF").message and q.drawings_auto == ""


def test_a_title_block_template(p, tmp_path):
    tpl = tmp_path / "company.tpl"
    tpl.write_text("! our title block\npaper = A3\nrow = TITLE\nrow = NUMBER, REVISION\n"
                   "row = MATERIAL, SCALE, SHEET\nCOMPANY = Example Ltd\nrow = AUTHOR, COMPANY\n",
                   encoding="utf-8")
    ok(p, f'PROPERTY, TITLE, Base plate\nPROPERTY, NUMBER, BP-7\nDRAWSHEET, a, TOP, 0, ALL, , , , , "{tpl}"')
    path = str(tmp_path / "t.pdf")
    msg = p.run(f'DRAWINGS, "{path}"').message
    assert "A3" in msg
    _n, data = pages(path)
    for text in (b"(Base plate)", b"(BP-7)", b"(Example Ltd)", b"(1 of 1)", b"(Number)"):
        assert text in data
    bad = tmp_path / "bad.tpl"
    bad.write_text("paper = B5\n", encoding="utf-8")
    assert "the paper is one of" in p.run(f'DRAWSHEET, b, TOP, 0, ALL, , , , , "{bad}"').message


def test_sizes_on_the_model_are_checked(p):
    # a size between two corners, a diameter picked from the hole (follows it), and one typed by hand
    from modeler.core.refs import _describe

    hole = next(g for g in p.model.entity_ids("FACE")
                if _describe("FACE", p.model.entity_shape("FACE", g))["type"] == "CYLINDER")
    ok(p, f'NOTE, SIZE, 0,0,0, 40,0,0\nPICK, FACE, {hole}\nNOTE, HOLE\nNOTE, "\u00f86", 20,10,15, 13,10,10')
    assert "3 sizes on the model checked: all fit the model" in p.run("DRAWINGS").message
    ok(p, 'HIST, EDIT, 1, "W = 50"\nHIST, EDIT, 4, "CYL, 10,10,-1, 4, 12"')
    msg = p.run("DRAWINGS").message
    assert "2 of 3 sizes on the model are out of date" in msg
    assert "note 1 (40): its ends no longer meet the model as they did (an end on a vertex is now on edge)" in msg
    assert "note 3 (\u00f86): the hole is now \u00f88" in msg
    assert "note 2" not in msg  # picked from the model: it follows the hole


def test_sheets_are_history_steps_and_bad_ones_are_refused(p):
    ok(p, "DRAWSHEET, a, TOP")
    assert "sheet 1 a changed" in p.run("DRAWSHEET, a, FRONT").message
    assert "removed sheet a" in p.run("DRAWSHEET, DELETE, a").message
    assert "no sheets" in p.run("DRAWINGS").message
    assert "no sheets" in p.run('DRAWINGS, "x.pdf"').message
    assert "the paper is one of" in p.run("DRAWSHEET, b, TOP, 0, ALL, B5").message
    assert "sizes are" in p.run("DRAWSHEET, b, TOP, 0, SOME").message
    ok(p, "UNDO")
    assert "a" in p.model.drawsheets or "A" in p.model.drawsheets
