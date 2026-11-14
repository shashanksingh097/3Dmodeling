"""Lineage: which history steps made a body (STEPS, the model tree)."""

import pytest

from modeler.commands import Processor
from modeler.commands.lineage import body_steps, made_by
from modeler.gui import tree_model as tm


@pytest.fixture
def p():
    return Processor()


def ok(p, line):
    r = p.run(line)
    assert r.ok, r.message
    return r.message


def rows(p, bid):
    return [j + 1 for j in body_steps(p, bid)]


def test_steps_follow_booleans_copies_and_styling(p):
    for line in ("BLOCK, 0,0,0, 20,20,5", "CYL, 10,10,0, 3, 5", "SUBTRACT, 1, 2", "COPY, 3, 30,0,0",
                 "COLOR, 3, RED", "NAME, 3, plate", "BLOCK, 100,0,0, 5,5,5", "SPHERE, 0,0,50, 4"):
        ok(p, line)
    assert rows(p, 3) == [1, 2, 3, 5, 6]
    assert rows(p, 4) == [1, 2, 3, 4]  # the copy: not the later colour of the original
    assert rows(p, 5) == [7]
    assert made_by(p, 2) == [3]  # SUBTRACT (row 3, 0-based 2) made body 3
    msg = ok(p, "STEPS, plate")
    assert "5 steps" in msg and "3: SUBTRACT, 1, 2" in msg


def test_a_body_rebuilt_under_its_id_keeps_its_earlier_steps(p):
    ok(p, "BLOCK, 0,0,0, 20,20,5")
    ok(p, "CYL, 10,10,0, 3, 5")
    ok(p, "SUBTRACT, 1, 2")
    ok(p, "MOVE, 3, 5,0,0")
    assert rows(p, 3) == [1, 2, 3, 4]


def test_loops_do_not_tie_every_instance_together(p):
    p.run_script(open("scripts/bolted_plate.cmd").read())
    plate = p.model.body_by_name("plate")
    plate = plate.id if hasattr(plate, "id") else plate
    texts = [p.history[j].label for j in body_steps(p, plate)]
    assert texts[0].startswith("CYL") and texts[-1].startswith("*DO")
    bolt = next(b for b in p.model.bodies if p.model.instances.get(b, ("",))[0].upper() == "BOLT")
    texts = [p.history[j].label for j in body_steps(p, bolt)]
    assert texts[0].startswith("*PART, bolt") and not any(t.startswith("CYL") for t in texts)


def test_lineage_survives_history_edits_and_projects(p, tmp_path):
    ok(p, "BLOCK, 0,0,0, 20,20,5")
    ok(p, "CYL, 10,10,0, 3, 5")
    ok(p, "SUBTRACT, 1, 2")
    ok(p, 'HIST, EDIT, 2, "CYL, 10,10,0, 4, 5"')
    assert rows(p, 3) == [1, 2, 3]
    f = tmp_path / "l.m3d"
    ok(p, f'SAVE, "{f}"')
    q = Processor()
    ok(q, f'OPEN, "{f}"')
    assert rows(q, 3) == [1, 2, 3]
    q.run("HIST, SUPPRESS, 2")  # the SUBTRACT now fails: a failed step makes nothing
    assert 3 not in q.model.bodies and rows(q, 1) == [1]


def test_tree_groups_parts_bodies_datums_and_sets(p):
    p.run_script(open("scripts/bolted_plate.cmd").read())
    ok(p, "PLANE, mid, XY, 5")
    ok(p, "SEL, S, FACE, ID, 1, 2")
    ok(p, "CM, top, FACE")
    ok(p, "FADE, plate")
    nodes = tm.tree_nodes(p)
    keys = [n.key for n in nodes]
    assert keys == ["group:parts", "group:bodies", "group:datums", "group:sets"]
    bolt = tm.find(nodes, "part:BOLT")
    assert bolt.label == "bolt (6)" and all(c.label.startswith("bolt") for c in bolt.children)
    plate = next(c for c in tm.find(nodes, "group:bodies").children if c.label.startswith("plate"))
    assert plate.state == "faded" and plate.shown
    assert tm.find(nodes, "datum:MID").tip == "plane mid"
    assert tm.eye_command(bolt, False) == "DISPLAY, HIDE, " + " ".join(map(str, bolt.ids))
    ok(p, tm.eye_command(bolt, False))
    assert tm.find(tm.tree_nodes(p), "part:BOLT").shown is False


def test_tree_pick_commands(p):
    ok(p, "BLOCK, 0,0,0, 5,5,5")
    ok(p, "BLOCK, 10,0,0, 5,5,5")
    assert tm.pick_command(p.model, 1, False) == "PICK, BODY, 1"
    ok(p, "PICK, BODY, 1")
    assert tm.pick_command(p.model, 2, True) == "PICK, BODY, 2, A"
    assert tm.pick_command(p.model, 1, True) == "PICK, BODY, 1, U"


def test_steps_has_no_form_but_is_listed():
    from modeler.gui import forms as F

    assert F.missing_forms() == []
