"""Layers, colours and materials: LAYER, COLOR, MATERIAL, ISOLATE, SEL by layer,
MASSPROP from materials, and how all of it follows bodies through operations."""

import pytest

from modeler.commands import Processor
from modeler.gui import forms as F


@pytest.fixture
def p():
    return Processor()


def ok(p, line):
    r = p.run(line)
    assert r.ok, r.message
    return r.message


def bad(p, line):
    r = p.run(line)
    assert not r.ok, f"{line} should fail, got: {r.message}"
    return r.message


def test_new_bodies_go_on_the_current_layer(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10")
    assert p.model.body(1).layer == "DEFAULT"
    msg = ok(p, "LAYER, bolts")
    assert "new layer bolts" in msg and "new bodies go on layer bolts" in msg
    ok(p, "CYL, 0,0,0, 2, 10")
    assert p.model.body(2).layer == "bolts"
    assert p.model.current_layer == "BOLTS"
    ok(p, "LAYER, DEFAULT")
    ok(p, "SPHERE, 0,0,0, 3")
    assert p.model.body(3).layer == "DEFAULT"
    # NEW makes a layer without switching
    ok(p, "LAYER, frame, NEW, GREEN")
    assert p.model.current_layer == "DEFAULT"
    assert p.model.layers["FRAME"].color == pytest.approx((70 / 255, 170 / 255, 90 / 255))
    assert "already exists" in bad(p, "LAYER, frame, NEW")


def test_results_keep_the_layer_colour_and_material_of_their_first_input(p):
    ok(p, "LAYER, plate")
    ok(p, "BLOCK, 0,0,0, 20,20,5")
    ok(p, "COLOR, LAST, BLUE")
    ok(p, "MATERIAL, LAST, ALUMINIUM")
    ok(p, "LAYER, DEFAULT")
    ok(p, "CYL, 10,10,0, 3, 5")
    ok(p, "SUBTRACT, 1, 2")
    b = p.model.bodies[p.model.last_body]
    assert (b.layer, b.material) == ("plate", "ALUMINIUM")
    assert b.color is not None
    ok(p, "MOVE, LAST, 5")
    assert p.model.bodies[p.model.last_body].layer == "plate"
    ok(p, "COPY, LAST, 40")  # a copy too, although the current layer is DEFAULT
    c = p.model.bodies[p.model.last_body]
    assert (c.layer, c.material, c.color) == ("plate", "ALUMINIUM", b.color)
    ok(p, "ARRAY, LINEAR, LAST, 3, 0, 30, 0")
    assert {x.layer for x in p.model.bodies.values()} == {"plate"}


def test_layer_off_hides_its_bodies_and_measuring_skips_them(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10")
    ok(p, "LAYER, extra")
    ok(p, "BLOCK, 20,0,0, 10,10,10")
    ok(p, "LAYER, extra, OFF")
    assert p.model.shown_ids() == [1]
    assert "body 1:" in ok(p, "MASSPROP")
    ok(p, "SHOW, ALL")  # SHOW, ALL undoes HIDE, not a layer that is off
    assert p.model.shown_ids() == [1]
    assert "layer extra is off" in ok(p, "SHOW, ALL")
    ok(p, "LAYER, ALL, ON")
    assert p.model.shown_ids() == [1, 2]


def test_a_locked_layer_protects_its_bodies(p):
    ok(p, "LAYER, fixed")
    ok(p, "BLOCK, 0,0,0, 10,10,10")
    ok(p, "LAYER, DEFAULT")
    ok(p, "CYL, 5,5,0, 2, 20")
    ok(p, "LAYER, fixed, LOCK")
    ok(p, "SEL, S, EDGE, BODY, 1")
    for line in ("DELETE, 1", "MOVE, 1, 5", "SUBTRACT, 1, 2", "COLOR, 1, RED", "MATERIAL, 1, STEEL",
                 "LAYER, DEFAULT, ADD, 1", "FILLET, 1"):
        msg = bad(p, line)
        assert "locked" in msg, (line, msg)
    # a locked tool is not used up either: nothing changed
    assert sorted(p.model.bodies) == [1, 2]
    assert "locked" in bad(p, "SUBTRACT, 2, 1")
    assert sorted(p.model.bodies) == [1, 2]
    assert "locked" in bad(p, "LAYER, fixed, ADD, 2")
    assert "locked" in bad(p, "LAYER, fixed, DELETE")
    ok(p, "COPY, 1, 20")  # reading it is fine
    ok(p, "LAYER, fixed, UNLOCK")
    ok(p, "SUBTRACT, 1, 2")


def test_add_rename_delete(p):
    ok(p, "BLOCK, 0,0,0, 1,1,1")
    ok(p, "BLOCK, 5,0,0, 1,1,1")
    ok(p, "BLOCK, 9,0,0, 1,1,1")
    ok(p, "LAYER, pipes, NEW")
    ok(p, "SEL, S, BODY, 1")
    ok(p, "SEL, A, BODY, 3")
    assert "2 bodies (1, 3) now on layer pipes" in ok(p, "LAYER, pipes, ADD, SEL")
    # SEL of faces means their bodies
    ok(p, "SEL, S, FACE, BODY, 2")
    ok(p, "LAYER, pipes, ADD")
    assert all(b.layer == "pipes" for b in p.model.bodies.values())
    ok(p, "LAYER, pipes")
    ok(p, "LAYER, pipes, RENAME, ducts")
    assert all(b.layer == "ducts" for b in p.model.bodies.values())
    assert p.model.current_layer == "DUCTS"
    assert "3 bodies moved to DEFAULT" in ok(p, "LAYER, ducts, DELETE")
    assert p.model.current_layer == "DEFAULT"
    assert all(b.layer == "DEFAULT" for b in p.model.bodies.values())
    assert "cannot be deleted" in bad(p, "LAYER, DEFAULT, DELETE")
    assert "no layer named" in bad(p, "LAYER, nothere, OFF")
    assert "not a valid layer name" in bad(p, "LAYER, 3x")


def test_colours(p):
    ok(p, "BLOCK, 0,0,0, 1,1,1")
    ok(p, "COLOR, 1, #ff8000")
    assert p.model.body(1).color == pytest.approx((1.0, 128 / 255, 0.0))
    ok(p, "COLOR, 1, 0, 255, 0")
    assert p.model.body(1).color == pytest.approx((0.0, 1.0, 0.0))
    ok(p, "C = (0, 0, 255)")
    ok(p, "COLOR, 1, C")
    assert p.model.body(1).color == pytest.approx((0.0, 0.0, 1.0))
    ok(p, 'COLOR, 1, "#f00"')
    assert p.model.body(1).color == pytest.approx((1.0, 0.0, 0.0))
    assert "unknown colour" in bad(p, "COLOR, 1, PLAID")
    assert "0 to 255" in bad(p, "COLOR, 1, 300, 0, 0")
    # drawn colour: own, else layer, else material
    ok(p, "COLOR, 1, DEFAULT")
    assert p.model.display_color(1) is None
    ok(p, "MATERIAL, 1, BRASS")
    assert p.model.display_color(1) == p.model.materials["BRASS"].color
    ok(p, "LAYER, DEFAULT, COLOR, RED")
    assert p.model.display_color(1) == pytest.approx((214 / 255, 64 / 255, 56 / 255))
    ok(p, "COLOR, ALL, WHITE")
    assert p.model.display_color(1) == pytest.approx((240 / 255,) * 3)


def test_materials_give_mass(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10")  # 1000 mm3
    ok(p, "BLOCK, 20,0,0, 10,10,10")
    assert "no mass" not in ok(p, "MASSPROP")
    ok(p, "MATERIAL, 1, STEEL")
    assert "bodies 2 have no material" in ok(p, "MASSPROP")
    ok(p, "MATERIAL, 2, CFRP, 1600, BLACK")  # a new material
    msg = ok(p, "MASSPROP")
    assert "mass 0.00945 kg (cfrp, steel)" in msg
    # the centre of mass moves toward the heavy steel block
    assert "centre of mass (" in msg and float(msg.split("centre of mass (")[1].split(",")[0]) < 15
    assert "mass 0.00785 kg" in ok(p, "MASSPROP, 1")
    assert "mass 0.0027 kg" in ok(p, "MASSPROP, 1, 2700")  # a density given wins
    ok(p, "MATERIAL, 1, aluminum")  # aliases
    assert p.model.body(1).material == "ALUMINIUM"
    assert "built in" in bad(p, "MATERIAL, 1, STEEL, 7000")
    assert "no material named" in bad(p, "MATERIAL, 1, UNOBTAINIUM")
    ok(p, "MATERIAL, 1, NONE")
    assert p.model.body(1).material == ""
    assert "CFRP" in ok(p, "LIST, MATERIALS")


def test_sel_by_layer_and_material(p):
    ok(p, "BLOCK, 0,0,0, 1,1,1")
    ok(p, "LAYER, b")
    ok(p, "BLOCK, 5,0,0, 1,1,1")
    ok(p, "CYL, 9,0,0, 1, 1")
    ok(p, "MATERIAL, 3, BRASS")
    ok(p, "SEL, S, BODY, LAYER, b")
    assert p.model.selection == [2, 3]
    ok(p, "SEL, S, FACE, LAYER, DEFAULT")
    assert len(p.model.selection) == 6
    ok(p, "SEL, S, BODY, MAT, BRASS")
    assert p.model.selection == [3]


def test_isolate(p):
    ok(p, "BLOCK, 0,0,0, 1,1,1")
    ok(p, "LAYER, b")
    ok(p, "BLOCK, 5,0,0, 1,1,1")
    ok(p, "BLOCK, 9,0,0, 1,1,1")
    ok(p, "ISOLATE, 1")
    assert p.model.shown_ids() == [1]
    ok(p, "SHOW, ALL")
    ok(p, "ISOLATE, b")  # a layer
    assert p.model.shown_ids() == [2, 3]
    ok(p, "SHOW, ALL")
    ok(p, "SEL, S, BODY, 1")
    ok(p, "SEL, A, BODY, 3")
    ok(p, "ISOLATE")
    assert p.model.shown_ids() == [1, 3]


def test_undo_and_history_edit_keep_layers_in_step(p):
    ok(p, "LAYER, a")
    ok(p, "BLOCK, 0,0,0, 1,1,1")
    ok(p, "LAYER, a, OFF")
    assert p.model.shown_ids() == []
    p.undo()
    assert p.model.shown_ids() == [1]
    p.undo()
    p.undo()
    assert "A" not in p.model.layers and p.model.current_layer == "DEFAULT"
    p.redo()
    p.redo()
    assert p.model.body(1).layer == "a"
    # change the layer step: the body lands on the renamed layer
    ok(p, 'HIST, EDIT, 1, "LAYER, b"')
    assert p.model.body(1).layer == "b"


def test_a_saved_script_replays_layers(p, tmp_path):
    for line in ("LAYER, frame, NEW, #3366cc", "LAYER, frame", "BLOCK, 0,0,0, 4,4,4", "MATERIAL, LAST, STEEL",
                 "LAYER, DEFAULT", "CYL, 0,0,0, 1, 8", "COLOR, LAST, ORANGE", "LAYER, frame, LOCK"):
        ok(p, line)
    f = tmp_path / "m.json"
    ok(p, f'SAVE, "{f}"')
    q = Processor()
    r = q.run(f'OPEN, "{f}"')
    assert r.ok, r.message
    a, b = q.model.body(1), q.model.body(2)
    assert (a.layer, a.material) == ("frame", "STEEL")
    assert b.layer == "DEFAULT" and b.color is not None
    assert q.model.layers["FRAME"].locked


def test_list_shows_layers(p):
    ok(p, "LAYER, x")
    ok(p, "BLOCK, 0,0,0, 1,1,1")
    msg = ok(p, "LIST")
    assert "(layer x)" in msg and "x: 1 body, colour default [current]" in msg


def test_every_new_command_has_a_form():
    assert F.missing_forms() == []
    for name in ("LAYER", "COLOR", "MATERIAL", "ISOLATE"):
        F.spec(name)


def test_glass_is_drawn_see_through_and_keeps_it_when_redefined(p):
    ok(p, "BLOCK, 0,0,0, 10,10,2")
    assert p.model.display_transparency(1) == 0.0
    ok(p, "MATERIAL, 1, GLASS")
    assert 0 < p.model.display_transparency(1) < 1
    ok(p, "MATERIAL, 1, GLASS, 2500, #335577")   # same material, another colour
    assert 0 < p.model.display_transparency(1) < 1
    ok(p, "MATERIAL, 1, STEEL")
    assert p.model.display_transparency(1) == 0.0
