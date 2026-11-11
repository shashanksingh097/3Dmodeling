"""Stable references: IDs through operations, names, named sets, geometric selection."""

import math

import pytest

from modeler.commands import Processor


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    results = p.run_script(text)
    bad = [r for r in results if not r.ok]
    assert not bad, bad[0].message
    return results[-1]


def face_z(p, gid):
    return p.evaluate(f"CENT({gid}, 'FACE').z")


def test_face_ids_survive_a_boolean(p):
    ok(p, "BLOCK, 0,0,0, 20,10,5\nCYL, 5,5,-1, 2, 10\nSUBTRACT, 1, 2")
    body = p.model.bodies[3]
    # the six block faces keep 1..6; the hole wall keeps the cylinder's side face ID
    assert set(range(1, 7)) <= set(body.entity_ids["FACE"])
    assert 7 in body.entity_ids["FACE"]
    assert len(body.entity_ids["FACE"]) == 7
    assert face_z(p, 6) == pytest.approx(5)  # still the top
    assert not p.run("PICK, FACE, 8").ok  # the cylinder caps were cut away


def test_split_face_keeps_id_on_largest_piece(p):
    # a thin slot cuts the top face of the block into a big and a small piece
    ok(p, "BLOCK, 0,0,0, 10,10,10\nBLOCK, 7,-1,8, 1,12,5\nSUBTRACT, 1, 2")
    tops = [g for g in p.model.bodies[3].entity_ids["FACE"] if abs(face_z(p, g) - 10) < 1e-6]
    assert 6 in tops and len(tops) == 2
    assert p.evaluate("AREA(6)") == pytest.approx(70)


def test_edge_ids_survive_fillet_and_chamfer(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nPICK, EDGE, 1\nFILLET, 2")
    edges = p.model.bodies[2].entity_ids["EDGE"]
    assert 1 not in edges  # the filleted edge is gone
    assert {2, 3, 4} <= set(edges)  # the untouched ones keep their IDs
    assert set(range(1, 7)) <= set(p.model.bodies[2].entity_ids["FACE"])


def test_selection_follows_through_an_operation(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nSEL, S, FACE, NORMAL, 0,0,1\nCYL, 5,5,-1, 2, 20\nSUBTRACT, 1, 2")
    assert p.model.selection == [6]


def test_move_rotate_keep_body_and_entity_ids(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nNAME, 1, cube\nMOVE, cube, 100\nROTATE, cube, 90, 100,0,0")
    assert list(p.model.bodies) == [1] and p.model.bodies[1].name == "cube"
    assert p.model.bodies[1].entity_ids["FACE"] == [1, 2, 3, 4, 5, 6]
    assert p.evaluate("BBOX(cube).xmin") == pytest.approx(90)
    ok(p, "COPY, cube, 0, 0, 50\nMIRROR, cube, 0,0,0, 1,0,0")
    assert len(p.model.bodies) == 3
    assert p.evaluate("BBOX(LAST).xmax") == pytest.approx(-90)


def test_names_follow_the_part_through_booleans(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nNAME, LAST, base\nCYL, 5,5,-1, 2, 20\nSUBTRACT, base, LAST")
    assert p.model.body_by_name("base").id == 3
    ok(p, "PICK, EDGE, 1\nFILLET, 0.5")
    assert p.model.body_by_name("BASE").id == 4
    ok(p, "SPHERE, 50,0,0, 1")
    assert "already used" in p.run("NAME, LAST, base").message
    assert "not a valid name" in p.run("NAME, LAST, 2x").message
    assert p.evaluate("BODY('base')") == 4
    assert p.evaluate("VOL(base)") < 1000 - math.pi * 4 * 10


def test_named_sets(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nSEL, S, FACE, NORMAL, 0,0,1\nSEL, A, FACE, NORMAL, 0,0,-1\nCM, caps, FACE\nSEL, NONE")
    ok(p, "CMSEL, S, caps")
    assert sorted(p.model.selection) == [5, 6]
    ok(p, "CYL, 5,5,-1, 2, 20\nSUBTRACT, 1, LAST\nSEL, S, FACE, SET, caps")
    assert sorted(p.model.selection) == [5, 6]  # still valid after the hole
    assert "holds FACE" in p.run("SEL, S, EDGE, SET, caps").message
    ok(p, "CMDEL, caps")
    assert not p.run("CMSEL, S, caps").ok


def test_geometric_selection(p):
    ok(p, "BLOCK, 0,0,0, 20,10,5\nCYL, 30,5,0, 4, 12")
    m = p.model
    ok(p, "SEL, S, FACE, NORMAL, 0,0,1")
    assert m.selection == [6, 8]
    ok(p, "SEL, R, FACE, LOC, Z, 5")
    assert m.selection == [6]
    ok(p, "SEL, S, FACE, LOC, Z, 0, 6")
    assert set(m.selection) == {1, 2, 3, 4, 5, 6, 7, 9}  # everything but the cylinder top
    ok(p, "SEL, S, FACE, BOX, -1,-1,-1, 21,11,6")
    assert m.selection == [1, 2, 3, 4, 5, 6]
    ok(p, "SEL, S, FACE, AT, 10, 5, 5")
    assert m.selection == [6]
    assert "no FACE at" in p.run("SEL, S, FACE, AT, 100, 100, 100").message
    ok(p, "SEL, S, FACE, TYPE, CYLINDER")
    assert m.selection == [7]
    ok(p, "SEL, S, EDGE, RADIUS, EQ, 4")
    assert len(m.selection) == 2
    ok(p, "SEL, S, EDGE, SIZE, GT, 15")
    assert len(m.selection) == 6  # 4 edges of 20 plus 2 circles of 25.1
    ok(p, "SEL, S, EDGE, SIZE, BETWEEN, 9, 11")
    assert len(m.selection) == 4
    ok(p, "SEL, S, FACE, ID, 6\nSEL, S, EDGE, OF, FACE")
    assert len(m.selection) == 4
    ok(p, "SEL, S, FACE, BODY, 2")
    assert m.selection == [7, 8, 9]
    ok(p, "SEL, S, BODY, OF, FACE")
    assert m.selection == [2]
    ok(p, "SEL, INVE")
    assert m.selection == [1]
    ok(p, "SEL, S, FACE, 2, 4")  # plain ID range, as in M0
    assert m.selection == [2, 3, 4]
    ok(p, "N = (0, 0, 1)\nSEL, S, FACE, NORMAL, N")
    assert m.selection == [6, 8]


def test_selection_queries_in_expressions(p):
    ok(p, "BLOCK, 0,0,0, 1,1,1\nSEL, ALL, EDGE")
    assert p.evaluate("NSEL()") == 12
    assert p.evaluate("NSEL('FACE')") == 0
    assert p.evaluate("SELID(1)") == 1
    assert p.evaluate("COUNT('FACE')") == 6
    assert p.evaluate("OWNER(5)") == 1
    assert p.evaluate("EXISTS(1)") == 1 and p.evaluate("EXISTS(2)") == 0
    assert p.evaluate("LENGTH(1)") == pytest.approx(1)
