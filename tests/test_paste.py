"""PLAN item 107: copy and paste - clip data and the history steps a paste runs (PASTE)."""

import pytest

from modeler.commands import Processor
from modeler.commands import clip_handlers as ch


def ok(p, text):
    r = None
    for line in text.strip().splitlines():
        r = p.run(line.strip())
        assert r.ok, (line, r.message)
    return r


def plate():
    p = Processor()
    ok(p, """BLOCK, 0, 0, 0, 10, 20, 5
NAME, LAST, plate
MATERIAL, plate, STEEL
COLOR, plate, RED""")
    return p


def test_same_project_pastes_as_copy_steps():
    p = plate()
    data = ch.copy_bodies(p, [1])
    assert ch.paste_lines(p, data) == ["COPY, 1, 11, 0, 0"]  # beside it: one width and a tenth
    # under the mouse: the bottom centre goes to the point
    assert ch.paste_lines(p, data, ch.offset_to(data, (100, 100, 5))) == ["COPY, 1, 95, 90, 5"]
    ok(p, "COPY, 1, 11, 0, 0")
    assert len(p.model.bodies) == 2 and not p.pasted


def test_other_project_keeps_the_geometry(tmp_path):
    a = plate()
    data = ch.copy_bodies(a, [1])
    b = Processor()
    lines = ch.paste_lines(b, data)
    assert lines == ["PASTE, CLIP1, 11, 0, 0"]
    r = ok(b, lines[0])
    assert "PASTE CLIP1 -> body 1 'plate'" in r.message
    body = b.model.body(1)
    assert body.material == "STEEL" and body.color is not None
    assert ok(b, "PASTE, LIST").message.endswith("CLIP1: plate, steel")
    # pasted twice: the name is taken, the geometry kept once
    assert ch.paste_lines(b, data) == ["PASTE, CLIP1, 11, 0, 0"]
    ok(b, "PASTE, CLIP1, 30, 0, 0")
    assert b.model.body(2).name != "plate" and len(b.pasted) == 1
    # saved with the project; a rebuild needs no clipboard
    f = tmp_path / "b.m3d"
    ok(b, f'SAVE, "{f}"')
    c = Processor()
    ok(c, f'OPEN, "{f}"')
    assert set(c.pasted) == {"CLIP1"} and len(c.model.bodies) == 2
    assert not Processor().run("PASTE, CLIP9").ok


def test_faces_paste_as_a_sheet_body():
    p = plate()
    faces = p.model.entity_ids("FACE")[:2]
    data = ch.copy_faces(p, faces)
    lines = ch.paste_lines(p, data)
    assert lines[0].startswith("PASTE, CLIP1")
    r = ok(p, lines[0])
    assert "plate_faces" in r.message and "(2 faces" in r.message


def test_sketch_geometry_same_and_other_sketch():
    p = Processor()
    ok(p, """SKETCH, s1, XY
SLINE, 0, 0, 10, 0
SCIRCLE, 5, 5, 2
SARC, 0, 0, 5, 0, 90
SSPLINE, 0, 0, 5, 5, 10, 0""")
    data = ch.copy_sketch(p, ["1", "2", "3", "4"])
    assert ch.paste_lines(p, data) == ["STRANSFORM, MOVE, 11, 0, 1, 2, 3, 4, COPY"]
    ok(p, ch.paste_lines(p, data)[0])
    assert len(p.model.sketches["S1"].geos) == 8
    ok(p, "ENDSKETCH\nSKETCH, s2, XY")
    lines = ch.paste_lines(p, data, (20, 0, 0))
    assert lines[:2] == ["SLINE, 20, 0, 30, 0", "SCIRCLE, 25, 5, 2"]
    for line in lines:
        ok(p, line)
    assert len(p.model.sketches["S2"].geos) == 4
    with pytest.raises(Exception):
        ok(p, "ENDSKETCH")
        ch.paste_lines(p, data)
