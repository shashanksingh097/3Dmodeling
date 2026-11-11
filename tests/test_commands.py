"""Headless tests: commands and model, no window needed."""

import pytest
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from modeler.commands import REGISTRY, Processor


@pytest.fixture
def p():
    return Processor()


def run_ok(p, line):
    r = p.run(line)
    assert r.ok, r.message
    return r


def centre(shape):
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, g)
    c = g.CentreOfMass()
    return round(c.X(), 6), round(c.Y(), 6), round(c.Z(), 6)


def test_block_gets_global_entity_ids(p):
    run_ok(p, "BLOCK, 0,0,0, 20,10,5")
    run_ok(p, "block, 30,0,0, 1,1,1")  # case-insensitive
    m = p.model
    assert sorted(m.bodies) == [1, 2]
    assert m.bodies[1].entity_ids["FACE"] == [1, 2, 3, 4, 5, 6]
    assert m.bodies[2].entity_ids["FACE"] == [7, 8, 9, 10, 11, 12]
    assert m.bodies[2].entity_ids["EDGE"][0] == 13
    assert m.bodies[2].entity_ids["VERTEX"][0] == 9
    assert m.entity_owner("FACE", 9) == (2, 3)


def test_face_6_of_a_block_is_its_top(p):
    run_ok(p, "BLOCK, 0,0,0, 20,10,5")
    assert centre(p.model.entity_shape("FACE", 6)) == (10, 5, 5)


def test_primitives(p):
    assert "3 faces" in run_ok(p, "CYL, 0,0,0, 2, 5").message
    assert "1 faces" in run_ok(p, "SPHERE, 0,0,0, 3").message


def test_bad_input_is_reported_not_raised(p):
    for line, msg in [
        ("NOPE, 1", "unknown command"),
        ("BLOCK, 0,0,0, 1,1", "required"),
        ("BLOCK, 0,0,0, 1,1,x", "must be a number"),
        ("BLOCK, 0,0,0, 1,1,-1", "positive"),
        ("PICK, FACE, 1", "no FACE with ID 1"),
        ("PICK, BLOB, 1", "unknown entity kind"),
    ]:
        r = p.run(line)
        assert not r.ok and msg in r.message, (line, r.message)
    assert p.log == []  # failed commands are not logged


def test_pick_and_sel(p):
    run_ok(p, "BLOCK, 0,0,0, 1,1,1")
    m = p.model
    run_ok(p, "PICK, FACE, 6")
    assert (m.selection_kind, m.selection) == ("FACE", [6])
    run_ok(p, "PICK, FACE, 2, A")
    assert m.selection == [6, 2]
    run_ok(p, "PICK, FACE, 6, U")
    assert m.selection == [2]
    run_ok(p, "PICK, EDGE, 3")  # a new kind starts a new set
    assert (m.selection_kind, m.selection) == ("EDGE", [3])
    run_ok(p, "SEL, S, VERTEX, 2, 4")
    assert m.selection == [2, 3, 4]
    run_ok(p, "SEL, ALL, BODY")
    assert (m.selection_kind, m.selection) == ("BODY", [1])
    run_ok(p, "SEL, NONE")
    assert m.selection == []


def test_log_replays_to_same_model(p):
    script = """
    ! comment line
    BLOCK, 0,0,0, 20,10,5   ! trailing comment
    CYL, 30,5,0, 4, 12
    PICK, FACE, 6
    PICK, FACE, 8, A
    LIST
    """
    assert all(r.ok for r in p.run_script(script))
    assert p.log == ["BLOCK, 0, 0, 0, 20, 10, 5", "CYL, 30, 5, 0, 4, 12", "PICK, FACE, 6", "PICK, FACE, 8, A"]
    q = Processor()
    assert all(r.ok for r in q.run_script("\n".join(p.log)))
    assert q.model.selection == p.model.selection == [6, 8]
    assert q.log == p.log


def test_view_commands_work_headless(p):
    for line in ("VIEW, TOP", "FIT", "PICKMODE, EDGE"):
        run_ok(p, line)
    assert not p.run("VIEW, SIDEWAYS").ok


def test_clear_restarts_ids(p):
    run_ok(p, "BLOCK, 0,0,0, 1,1,1")
    run_ok(p, "PICK, FACE, 1")
    run_ok(p, "CLEAR")
    assert p.model.bodies == {} and p.model.selection == []
    run_ok(p, "BLOCK, 0,0,0, 1,1,1")
    assert p.model.bodies[1].entity_ids["FACE"][0] == 1


def test_help_covers_every_command(p):
    text = run_ok(p, "HELP").message
    for name in REGISTRY:
        assert name in text
        assert run_ok(p, f"HELP, {name}").message.startswith(name)


def volume(p, bid):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(p.model.bodies[bid].shape, g)
    return g.Mass()


def test_booleans_consume_inputs_and_make_new_body(p):
    run_ok(p, "BLOCK, 0,0,0, 10,10,10")
    run_ok(p, "BLOCK, 5,0,0, 10,10,10")
    run_ok(p, "UNION, 1, 2")
    assert sorted(p.model.bodies) == [3]
    assert volume(p, 3) == pytest.approx(1500)
    run_ok(p, "CYL, 5,5,-1, 2, 12")
    run_ok(p, "CYL, 10,5,-1, 1, 12")
    run_ok(p, "SUBTRACT, 3, 4, 5")
    assert sorted(p.model.bodies) == [6]
    assert volume(p, 6) == pytest.approx(1500 - 3.14159265 * 50, rel=1e-6)
    run_ok(p, "SPHERE, 0,0,0, 5")
    run_ok(p, "INTERSECT, 6, 7")
    assert volume(p, 8) == pytest.approx(4 / 3 * 3.14159265 * 125 / 8, rel=1e-6)
    assert not p.run("UNION, 8, 99").ok
    assert not p.run("UNION, 8, 8").ok
    assert not p.run("UNION, 8").ok


def test_fillet_and_chamfer_selected_edges(p):
    run_ok(p, "BLOCK, 0,0,0, 10,10,10")
    assert "select edges" in p.run("FILLET, 1").message
    run_ok(p, "PICK, EDGE, 1")
    r = run_ok(p, "FILLET, 2")
    assert "1 edges of body 1 -> body 2" in r.message
    assert volume(p, 2) == pytest.approx(1000 - (4 - 3.14159265) * 10, rel=1e-6)
    run_ok(p, "PICK, BODY, 2")
    run_ok(p, "CHAMFER, 0.5")
    assert sorted(p.model.bodies) == [3]
    assert not p.run("PICK, EDGE, 1").ok  # IDs of consumed bodies are gone


def test_cone_and_torus(p):
    run_ok(p, "CONE, 0,0,0, 5, 0, 10")
    run_ok(p, "TORUS, 0,0,0, 10, 2")
    assert volume(p, 2) == pytest.approx(2 * 3.14159265**2 * 10 * 4, rel=1e-6)
    assert not p.run("TORUS, 0,0,0, 2, 5").ok


def test_flange_example_script():
    p = Processor()
    with open("scripts/flange.cmd", encoding="utf-8") as f:
        results = p.run_script(f.read())
    assert all(r.ok for r in results), [r for r in results if not r.ok]
    assert sorted(p.model.bodies) == [14, 17]
    assert p.model.selection == [78]
