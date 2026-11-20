"""Comparing revisions (PLAN item 56): COMPARE, STEP and COMPARE, PROJECT find faces added, removed,
moved and changed, say how far the surface moved, and colour the changed body."""

import json

import pytest

from modeler.commands import Processor

BASE = "W = 40\nBLOCK, 0,0,0, W, 20, 10\nNAME, LAST, part\nCYL, 10,10,-1, 3, 12\nSUBTRACT, part, LAST"


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    res = p.run_script(text)
    bad = [r for r in res if not r.ok]
    assert not bad, f"{bad[0].line}: {bad[0].message}"
    return res[-1]


def rows(p, text):
    return json.loads(p.run(text).message)["bodies"]


def test_a_new_hole_is_an_added_face(p):
    ok(p, BASE)
    n = p.cursor
    ok(p, "CYL, 30,10,-1, 2, 12\nSUBTRACT, part, LAST")
    (r,) = rows(p, f"COMPARE, STEP, {n}, JSON")
    assert not r["same"] and len(r["added"]) == 1 and r["added"][0]["type"] == "cylinder"
    assert r["added"][0]["at"][:2] == pytest.approx([30, 10])
    assert len(r["changed"]) == 2 and not r["removed"] and not r["moved"]  # top and bottom lost a disc
    assert r["volume"][1] - r["volume"][0] == pytest.approx(-3.14159265 * 4 * 10, rel=1e-6)
    assert r["largest_in"] == pytest.approx(-4.8, abs=0.3) and r["largest_out"] < 1e-6
    assert r["regions"] and r["regions"][0]["worst"] < 0


def test_a_bigger_hole_is_a_changed_face_with_its_radius(p):
    ok(p, BASE)
    ok(p, 'HIST, EDIT, 4, "CYL, 10,10,-1, 4, 12"')
    (r,) = rows(p, "COMPARE, STEP, 0, JSON")
    assert r.get("added_body")  # against the empty start the part is new
    # against the saved first revision
    q = Processor()
    ok(q, BASE)
    path = _save(q)
    r = rows(p, f'COMPARE, PROJECT, "{path}", JSON')[0]
    hole = [c for c in r["changed"] if c["type"] == "cylinder"]
    assert len(hole) == 1 and hole[0]["radius_was"] == pytest.approx(3) and hole[0]["radius"] == pytest.approx(4)
    assert not r["added"] and not r["removed"]


def _save(q):
    import os
    import tempfile

    path = os.path.join(tempfile.mkdtemp(), "rev1.m3d")
    ok(q, f'SAVE, "{path}"')
    return path


def test_a_longer_block_has_a_moved_end_face(p):
    ok(p, BASE)
    path = _save(p)
    ok(p, 'HIST, EDIT, 1, "W = 50"')
    r = rows(p, f'COMPARE, PROJECT, "{path}", JSON')[0]
    moved = r["moved"]
    assert len(moved) == 1 and moved[0]["by"] == pytest.approx([10, 0, 0])
    assert {c["type"] for c in r["changed"]} == {"plane"} and len(r["changed"]) == 4
    msg = p.run(f'COMPARE, PROJECT, "{path}"').message
    assert "moved: face" in msg and "by (10, 0, 0)" in msg and "rev1.m3d" in msg


def test_nothing_changed_says_so(p):
    ok(p, BASE)
    path = _save(p)
    assert p.run(f'COMPARE, PROJECT, "{path}"').message == "no differences from rev1.m3d"
    assert p.run(f"COMPARE, STEP, {p.cursor}").message == f"no differences from step {p.cursor}"


def test_bodies_added_and_removed(p):
    ok(p, BASE)
    n = p.cursor
    ok(p, "SPHERE, 100, 0, 0, 5\nNAME, LAST, ball")
    msg = p.run(f"COMPARE, STEP, {n}").message
    assert "+ body" in msg and "'ball': new since step" in msg


def test_the_changed_body_is_coloured(p):
    ok(p, BASE)
    n = p.cursor
    ok(p, "CYL, 30,10,-1, 2, 12\nSUBTRACT, part, LAST")
    shown = []

    class View:
        def show_analysis(self, a):
            shown.append(a)

    p.view = View()
    p.run(f"COMPARE, STEP, {n}")
    assert shown and shown[-1].mode == "DEVIATION" and shown[-1].body == p.model.body_by_name("part").id


def test_bad_revisions_are_refused(p):
    ok(p, BASE)
    assert "positions go from 0" in p.run("COMPARE, STEP, 99").message
    assert "no such file" in p.run('COMPARE, PROJECT, "nowhere.m3d"').message
    # the old body-to-body COMPARE still works
    ok(p, "BLOCK, 100,0,0, 40, 20, 10")
    assert "not the same shape" in p.run("COMPARE, part, LAST").message
