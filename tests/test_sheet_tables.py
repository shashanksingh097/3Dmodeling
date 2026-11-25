"""PLAN item 72: balloons, a parts list, a hole table and a revision table on drawing sheets."""

import os

import pytest

from modeler.commands import Processor
from modeler.gui import body_menu as bm

PLATE = """BLOCK, 0,0,0, 100, 60, 10
NAME, LAST, plate
HOLE, plate, 20, 20, 10, 8
HOLE, plate, 80, 20, 10, 8
HOLE, plate, 50, 40, 10, 6, 5
HOLE, plate, 20, 45, 10, 6, 0, CBORE, 11, 4
BLOCK, 0,0,10, 20, 10, 20
NAME, LAST, post
PROPERTY, TITLE, Plate
DRAWSHEET, s1, STANDARD, 0, ALL, A3
"""


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


@pytest.fixture
def plate():
    p = Processor()
    ok(p, PLATE)
    return p


def _rows(p):
    r = p.run("SHEETDATA, s1")
    assert r.ok, r.message
    return r.report


def test_hole_table_rows(plate):
    ok(plate, "SHEETTABLE, s1, HOLES")
    rep = _rows(plate)
    holes = rep["holes"]
    assert [h["tag"] for h in holes] == ["A1", "A2", "B1", "C1"]  # by size, then position
    a1 = holes[0]
    assert a1["d"] == pytest.approx(8) and a1["through"]
    assert (a1["x"], a1["y"], a1["z"]) == pytest.approx((20, 20, 10))
    blind = next(h for h in holes if h["d"] == pytest.approx(6) and not h["counterbore"])
    assert not blind["through"] and blind["depth"] == pytest.approx(5)
    cb = next(h for h in holes if h["counterbore"])
    assert cb["counterbore"][0] == pytest.approx(11)
    assert "parts" not in rep


def test_thread_from_note(plate):
    ok(plate, 'NOTE, "M8x1.25", 30, 30, 15, 20, 20, 10\nSHEETTABLE, s1, HOLES')
    holes = _rows(plate)["holes"]
    assert holes[0]["thread"] == "M8x1.25"
    assert holes[1]["thread"] == ""


def test_parts_list_and_balloons(plate):
    ok(plate, "SHEETTABLE, s1, PARTS")
    rep = _rows(plate)
    assert rep["tables"] == ["balloons", "parts"]  # balloons come with the parts list
    assert [r["name"] for r in rep["parts"]] == ["plate", "post"]
    assert len(rep["balloons"]) == 2


def test_revisions_and_title_block(plate, tmp_path):
    ok(plate, 'REVISION, A, "First issue"\nREVISION, B, "Holes moved", 2026-11-24, Sam\nSHEETTABLE, s1, REVISIONS')
    rep = _rows(plate)
    assert [r["rev"] for r in rep["revisions"]] == ["A", "B"]
    assert rep["revisions"][1]["by"] == "Sam"
    out = tmp_path / "s.svg"
    ok(plate, f'DRAWINGS, "{out}"')
    text = (tmp_path / "s_s1.svg").read_text(encoding="utf-8")
    assert "REVISIONS" in text and "Holes moved" in text
    assert "REV  B" in text  # the newest revision in the title block
    ok(plate, 'REVISION, DELETE, B')
    assert [r["rev"] for r in plate.model.revisions] == ["A"]
    assert not plate.run("REVISION, DELETE, Q").ok
    assert not plate.run("REVISION, C").ok  # says what changed


def test_tables_follow_the_model(plate, tmp_path):
    ok(plate, "SHEETTABLE, s1, ALL")
    assert len(_rows(plate)["holes"]) == 4
    ok(plate, "HOLE, plate, 80, 45, 10, 5")
    assert len(_rows(plate)["holes"]) == 5
    out = tmp_path / "all.pdf"
    ok(plate, f'DRAWINGS, "{out}"')
    assert out.stat().st_size > 1000
    svg = tmp_path / "all.svg"
    ok(plate, f'DRAWINGS, "{svg}"')
    text = (tmp_path / "all_s1.svg").read_text(encoding="utf-8")
    for word in ("PARTS LIST", "HOLES (mm)", "REVISIONS", ">A1<", ">D1<"):
        assert word in text, word


def test_drawsheet_tables_argument_and_errors(plate):
    ok(plate, "DRAWSHEET, s2, TOP, 0, ALL, A4, , , , , HOLES+REV")
    assert plate.model.drawsheets["S2"]["tables"] == "HOLES+REVISIONS"
    assert "tables holes+revisions" in plate.run("DRAWSHEET, s2, TOP, 0, ALL, A4, , , , , HOLES+REV").message
    assert not plate.run("DRAWSHEET, s3, TOP, 0, ALL, A4, , , , , CHAIRS").ok
    assert not plate.run("SHEETTABLE, nosuch, ALL").ok
    ok(plate, "SHEETTABLE, s2, NONE")
    assert plate.model.drawsheets["S2"]["tables"] == ""


def test_undo_keeps_revisions_with_the_model(plate):
    ok(plate, 'REVISION, A, "First issue"')
    snap = plate.model.snapshot()
    ok(plate, 'REVISION, B, "Second"')
    plate.model.restore(snap)
    assert [r["rev"] for r in plate.model.revisions] == ["A"]


def test_right_click_items(plate):
    labels = {i.label: i for i in bm.empty_items(plate.model)}
    add = labels["Sheet s1: add a hole table"]
    assert add.commands == ["SHEETTABLE, s1, HOLES"]
    ok(plate, add.commands[0])
    labels = {i.label: i for i in bm.body_items(plate.model, next(iter(plate.model.bodies)))}
    assert labels["Sheet s1: take off the hole table"].commands == ["SHEETTABLE, s1, NONE"]
    assert labels["Sheet s1: add a parts list and balloons"].commands == ["SHEETTABLE, s1, HOLES+PARTS"]
    empty = Processor()
    assert not [i for i in bm.empty_items(empty.model) if i.form == "DRAWSHEET"]  # nothing to draw yet
    ok(empty, "BLOCK, 0,0,0, 1,1,1")
    assert [i for i in bm.empty_items(empty.model) if i.form == "DRAWSHEET"]


def test_sheetdata_without_sheets():
    p = Processor()
    assert not p.run("SHEETDATA").ok
    assert os.path.basename(__file__)


# ---- drawing details (PLAN item 100) -------------------------------------------------------

DETAILS = """BLOCK, 0,0,0, 100, 60, 10
NAME, LAST, plate
HOLE, plate, 20, 20, 10, 8
HOLE, plate, 80, 20, 10, 6.8
NOTE, "M8", 90, 30, 15, 80, 20, 10
BLOCK, 0,50,10, 100, 10, 30
NAME, LAST, wall
WELD, plate, wall, 4
DRAWSHEET, s1, STANDARD, 0, ALL, A3
"""


def test_sheet_details_are_drawn(tmp_path):
    p = Processor()
    ok(p, DETAILS)
    ok(p, 'SHEETNOTE, s1, CENTRES\nSHEETNOTE, s1, THREADS\nSHEETNOTE, s1, FINISH, 6, 1.6, ground\n'
          'SHEETNOTE, s1, WELD, weld_1\nSHEETNOTE, s1, LEADER, EDGE 3, "Break sharp edges"')
    assert p.run("SHEETNOTE, s1").ok
    assert [d["kind"] for d in p.reports["SHEETNOTE"]["notes"]] == ["CENTRES", "THREADS", "FINISH", "WELD", "LEADER"]
    r = p.run(f'DRAWINGS, "{tmp_path / "d.svg"}"')
    assert "12 details" in r.message
    got = p.reports["drawings"]["details"]["s1"]
    kinds = [d["kind"] for d in got]
    marks = [d for d in got if d["kind"] == "centre_mark"]
    assert len(marks) == 2 and {d["view"] for d in marks} == {"TOP"}  # both holes, seen end on
    assert kinds.count("centre_line") == 4  # front and right, each hole
    threads = [d for d in got if d["kind"] == "thread"]
    assert threads and all(d["thread"] == "M8" and d["major"] == pytest.approx(8) for d in threads)  # 6.8 tapped
    fin = next(d for d in got if d["kind"] == "finish")
    assert fin["ra"] == 1.6 and fin["view"] == "FRONT"  # the top face seen edge on
    weld = next(d for d in got if d["kind"] == "weld")
    assert weld["size"] == 4 and weld["length"] == pytest.approx(220)
    svg = (tmp_path / "d_s1.svg").read_text()
    assert "Ra 1.6" in svg and "Break sharp edges" in svg and "ground" in svg
    # changing the sheet keeps its details; DELETE takes one off
    ok(p, "DRAWSHEET, s1, TOP+FRONT, 0, ALL, A3")
    assert len(p.model.drawsheets["S1"]["notes"]) == 5
    ok(p, "SHEETNOTE, s1, DELETE, 2")
    assert [d["kind"] for d in p.model.drawsheets["S1"]["notes"]] == ["CENTRES", "FINISH", "WELD", "LEADER"]
    assert p.run("UNDO").ok and len(p.model.drawsheets["S1"]["notes"]) == 5


def test_sheet_details_refuse_bad_input():
    p = Processor()
    ok(p, DETAILS)
    for line, words in (("SHEETNOTE, s2, CENTRES", "no sheet s2"), ("SHEETNOTE, s1, ARROW", "the kind is one of"),
                        ("SHEETNOTE, s1, FINISH, EDGE 3, 1.6", "goes on a face"),
                        ("SHEETNOTE, s1, WELD, plate", "not a weld bead"),
                        ("SHEETNOTE, s1, LEADER, 9999, \"x\"", "no face 9999"),
                        ("SHEETNOTE, s1, DELETE, 1", "has no details")):
        r = p.run(line)
        assert not r.ok and words in r.message, (line, r.message)


def test_sheet_detail_menus():
    p = Processor()
    ok(p, DETAILS)
    labels = [i.label for i in bm.sheet_items(p.model)]
    assert "Sheet s1: add centre marks on the holes" in labels and "Sheet s1: add cosmetic threads" in labels
    ok(p, "SHEETNOTE, s1, CENTRES")
    items = {i.label: i.commands for i in bm.sheet_items(p.model)}
    assert items["Sheet s1: take off the centre marks on the holes"] == ["SHEETNOTE, s1, DELETE, 1"]
    p.model.select("FACE", [6])
    tools = {i.label: i for i in bm.pick_tools(p)}
    assert tools["Surface finish on sheet s1…"].commands == ["SHEETNOTE, s1, FINISH, 6, 1.6"]
    assert tools["Note on sheet s1…"].form == "SHEETNOTE"
    weld = p.model.body_by_name("weld_1").id
    p.model.select("BODY", [weld])
    assert any(i.commands == [f"SHEETNOTE, s1, WELD, {weld}"] for i in bm.pick_tools(p))
