"""Geometry from other parts (PLAN item 58): TAKE a face, edge, plane or axis from a part, linked
(follows the part) or copied (kept as it was); DEPENDS shows what uses what, broken links and loops.
Every case is also checked after saving and opening the project."""

import json
import os

import pytest

from modeler.commands import Processor

PLATE = """*PART, plate, W=40
  BLOCK, 0,0,0, W, 20, 5
  CYL, 10,10,-1, 3, 7
  SUBTRACT, 1, 2
*ENDPART"""


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    res = p.run_script(text)
    bad = [r for r in res if not r.ok]
    assert not bad, f"{bad[0].line}: {bad[0].message}"
    return res[-1]


def area(p, name):
    return p.evaluate(f"AREA({name})")


def ctr(p, name):
    from modeler.core.refs import _describe

    return _describe("BODY", p.model.body_by_name(name).shape)["c"]


def reopen(p, tmp_path):
    path = os.path.join(str(tmp_path), "take.m3d")
    ok(p, f'SAVE, "{path}"')
    q = Processor()
    ok(q, f'OPEN, "{path}"')
    return q


def test_list_shows_numbers_and_stays_out_of_the_history(p):
    ok(p, PLATE)
    n = len(p.history)
    msg = p.run("TAKE, LIST, plate").message
    assert "7 faces" in msg and "7: cylinder" in msg and "15 edges" in msg
    assert len(p.history) == n


def test_a_face_plane_and_axis_from_a_part(p):
    ok(p, PLATE + "\nTAKE, FACE, plate, 2, seat\nTAKE, PLANE, plate, 6, endp\nTAKE, AXIS, plate, FACE 7, hole")
    seat = p.model.body_by_name("seat")
    assert seat is not None and area(p, "seat") == pytest.approx(200)
    assert p.model.datums["ENDP"].origin == pytest.approx((40, 10, 2.5))
    ax = p.model.datums["HOLE"]
    assert ax.kind == "AXIS" and ax.origin[:2] == pytest.approx((10, 10))
    assert "curved" in p.run("TAKE, PLANE, plate, 7, nope").message
    assert "not straight" in p.run("TAKE, AXIS, plate, EDGE 10, nope").message
    assert "no face 99" in p.run("TAKE, FACE, plate, 99, nope").message
    assert "already" in p.run("TAKE, FACE, plate, 1, seat").message


def test_from_a_placed_copy_the_geometry_is_where_the_copy_stands(p):
    ok(p, PLATE + "\nINST, plate, 0, 0, 100\nTAKE, EDGE, LAST, 10, rim")
    from modeler.core.refs import _describe

    assert _describe("BODY", p.model.body_by_name("rim").shape)["c"][2] == pytest.approx(105)
    ok(p, "BLOCK, 200,0,0, 1,1,1")
    assert "not a copy of a part" in p.run("TAKE, FACE, LAST, 1, xx").message


def test_a_link_follows_the_part_and_a_copy_does_not(p, tmp_path):
    ok(p, PLATE + "\nTAKE, PLANE, plate, 6, endp\nTAKE, FACE, plate, 6, endlink\nTAKE, FACE, plate, 6, endcopy, COPY")
    ok(p, 'HIST, EDIT, 1, "' + PLATE.replace("W=40", "W=60").replace("\n", "\\n") + '"')
    assert p.model.datums["ENDP"].origin[0] == pytest.approx(60)
    assert ctr(p, "endlink")[0] == pytest.approx(60)
    assert ctr(p, "endcopy")[0] == pytest.approx(40)  # kept as it was
    q = reopen(p, tmp_path)
    assert ctr(q, "endlink")[0] == pytest.approx(60)
    assert ctr(q, "endcopy")[0] == pytest.approx(40)


def test_a_face_that_moves_in_the_numbering_is_found_again(p):
    ok(p, PLATE + "\nTAKE, AXIS, plate, FACE 7, hole")
    # a second hole: face numbers shift, the link follows the cylinder nearest to where it was
    two = PLATE.replace("  SUBTRACT, 1, 2\n", "  SUBTRACT, 1, 2\n  CYL, 5,5,-1, 1, 7\n  SUBTRACT, LAST-1, LAST\n")
    res = p.run('HIST, EDIT, 1, "' + two.replace("\n", "\\n") + '"')
    assert res.ok, res.message
    assert p.model.datums["HOLE"].origin[:2] == pytest.approx((10, 10))


def test_a_face_that_is_gone_is_a_broken_link(p):
    ok(p, PLATE + "\nTAKE, AXIS, plate, FACE 7, hole")
    nohole = "*PART, plate, W=40\n  BLOCK, 0,0,0, W, 20, 5\n*ENDPART"
    p.run('HIST, EDIT, 1, "' + nohole.replace("\n", "\\n") + '"')
    assert not p.history[1].ok and "broken link" in p.history[1].message
    d = json.loads(p.run("DEPENDS, JSON").message)
    assert d["broken"] and d["broken"][0]["step"] == 2
    assert "1 broken link" in p.run("DEPENDS").message


def test_a_part_cannot_take_from_itself(p):
    msg = p.run("*PART, loop\n  BLOCK, 0,0,0, 1,1,1\n  TAKE, FACE, loop, 1, f\n*ENDPART").message
    assert "no part named" in msg or "places itself" in msg or "neither a part" in msg
    ok(p, "*PART, a\n  BLOCK, 0,0,0, 1,1,1\n*ENDPART")
    ok(p, "*PART, b\n  INST, a, 0,0,0\n  TAKE, FACE, a, 1, f\n*ENDPART")
    from modeler.commands.take_handlers import loops

    assert loops(p.parts) == []


def test_depends_lists_files_parts_copies_and_takes(p, tmp_path):
    f = tmp_path / "plate.cmd"
    f.write_text(PLATE + "\n", encoding="utf-8")
    ok(p, f'LIB, LINK, "{f}"\nINST, plate, 0,0,0\nINST, plate, 0,0,50\nTAKE, FACE, plate, 2, seat')
    d = json.loads(p.run("DEPENDS, JSON").message)
    assert d["files"][0]["parts"] == ["plate"] and not d["files"][0]["missing"]
    assert d["parts"][0]["copies"] == [1, 2] and d["parts"][0]["how"] == "linked"
    assert d["takes"][0]["name"] == "seat" and d["takes"][0]["mode"] == "link"
    assert not d["broken"] and not d["loops"]
    msg = p.run("DEPENDS").message
    assert "plate.cmd -> plate" in msg and "seat <- part plate (link)" in msg and "no broken links" in msg
    # the file goes missing: the saved copy is used and DEPENDS says so
    q = reopen(p, tmp_path)
    os.remove(f)
    ok(q, "RELOAD") if q.run("RELOAD").ok else None
    d = json.loads(q.run("DEPENDS, JSON").message)
    assert d["takes"][0]["name"] == "seat"


def test_loops_are_found_in_part_definitions():
    from modeler.commands.take_handlers import loops
    from modeler.lang.script import PartDef

    a = PartDef(0, "A", [], "INST, b, 0,0,0", "")
    b = PartDef(0, "B", [], "TAKE, FACE, a, 1, f", "")
    assert loops({"A": a, "B": b}) == [["A", "B", "A"]]


def test_nothing_to_show(p):
    assert p.run("DEPENDS").message == "nothing here uses other parts or files"
