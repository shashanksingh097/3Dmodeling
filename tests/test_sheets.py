"""Drawing sheets (geometry/sheets.py): PDF, paper and title block, sections, details, PROPERTY."""

import numpy as np
import pytest

from modeler.commands import Processor
from modeler.geometry import sheets as sh


def run(p, *lines):
    for line in lines:
        r = p.run(line)
        assert r.ok, (line, r.message)
    return r


def _bracket(p):
    run(p, "BLOCK, 0,0,0, 80,50,20", "NAME, LAST, bracket", "CYL, 20, 25, -1, 6, 30", "SUBTRACT, bracket, LAST",
        "CYL, 60, 25, -1, 6, 30", "SUBTRACT, bracket, LAST", "BLOCK, 30, -1, 12, 20, 52, 10",
        "SUBTRACT, bracket, LAST", "MATERIAL, bracket, ALUMINIUM")


def test_scales_paper_and_hatching():
    assert sh.parse_scale("1:2") == 0.5 and sh.parse_scale("2:1") == 2 and sh.parse_scale("") == 0
    assert sh.scale_text(0.5) == "1:2" and sh.scale_text(5) == "5:1"
    with pytest.raises(sh.SheetError):
        sh.parse_scale("0:1")
    assert sh.fit((0, 0, 100, 60), "AUTO") == ("A4", 2)  # small: A4, drawn bigger
    assert sh.fit((0, 0, 800, 300), "AUTO") == ("A3", 0.2)  # 390/800 -> 1:5
    assert sh.fit((0, 0, 100, 60), "A3", 1) == ("A3", 1)
    # a 10 x 10 square with a 4 x 4 hole: hatching stays out of the hole
    sq = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
    hole = np.array([[3, 3], [7, 3], [7, 7], [3, 7]], float)
    lines = sh.hatch([sq, hole], 1.0)
    assert lines
    for a, b in lines:
        mid = (np.array(a) + np.array(b)) / 2
        assert not (3 + 1e-6 < mid[0] < 7 - 1e-6 and 3 + 1e-6 < mid[1] < 7 - 1e-6)
        assert -1e-9 <= min(a[0], b[0]) and max(a[0], b[0]) <= 10 + 1e-9


def test_pdf_sheet_with_title_block_section_and_detail(tmp_path):
    p = Processor()
    _bracket(p)
    run(p, "PROPERTY, TITLE, Mounting bracket", "PROPERTY, NUMBER, MB-001")
    assert "NUMBER: MB-001" in run(p, "PROPERTY").message
    f = tmp_path / "b.pdf"
    msg = run(p, f'DRAWING, {f}, STANDARD, , ALL, , , "X 20", "FRONT 30 0 12 6 3"').message
    assert "section a-a, detail b (3:1)" in msg and "A3 at 1:1" in msg
    data = f.read_bytes()
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    assert b"(Mounting bracket) Tj" in data and b"(MATERIAL  aluminium) Tj" in data
    assert b"(SECTION A-A) Tj" in data and b"(DETAIL B \\(3:1\\)) Tj" in data
    xref = int(data.rsplit(b"startxref", 1)[1].split()[0])
    assert data[xref:xref + 4] == b"xref"


def test_svg_on_paper_and_errors(tmp_path):
    p = Processor()
    _bracket(p)
    f = tmp_path / "b.svg"
    msg = run(p, f'DRAWING, {f}, FRONT+TOP, , ALL, A3, 1:2, "Y 25"').message
    assert "A3 at 1:2" in msg
    text = f.read_text()
    assert 'width="420mm"' in text and "SECTION A-A" in text and "bracket" in text  # the title: the body's name
    plain = tmp_path / "plain.svg"
    assert "x" in run(p, f"DRAWING, {plain}").message  # no paper: true size, as before
    assert "SECTION" not in plain.read_text()
    for bad in (f'DRAWING, {tmp_path / "x.dxf"}, , , ALL, A4', f'DRAWING, {tmp_path / "x.pdf"}, , , ALL, NONE',
                f'DRAWING, {tmp_path / "x.pdf"}, , , ALL, , , "X 500"', f'DRAWING, {tmp_path / "x.pdf"}, , , ALL, , , "Q 5"',
                f'DRAWING, {tmp_path / "x.pdf"}, TOP, , ALL, , , , "FRONT 0 0 0 5 2"',
                f'DRAWING, {tmp_path / "x.pdf"}, , , ALL, B5'):
        assert not p.run(bad).ok, bad


def test_property_round_trips_through_undo_and_save(tmp_path):
    p = Processor()
    run(p, "PROPERTY, TITLE, Lid", "PROPERTY, AUTHOR, me")
    assert p.model.properties == {"TITLE": "Lid", "AUTHOR": "me"}
    run(p, "PROPERTY, AUTHOR")
    assert p.model.properties == {"TITLE": "Lid"}
    p.undo()
    assert p.model.properties["AUTHOR"] == "me"
