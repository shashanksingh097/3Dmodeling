"""PLAN items 89-91 without a window: "did you mean", the faults of a failure and
WHY (89), REPEAT (90), PROPS and the assistant's properties tool (91)."""

import json

import pytest

from modeler.commands.processor import REGISTRY, Processor


def run(p, text):
    for line in text.strip().splitlines():
        r = p.run(line)
        assert r.ok, f"{line}: {r.message}"
    return r


def fails(p, line):
    r = p.run(line)
    assert not r.ok, line
    return r.message


@pytest.fixture
def p():
    return Processor()


# ---- 89: did you mean ----------------------------------------------------------------------
def test_misspelt_command_suggests_the_nearest(p):
    msg = fails(p, "BLOK, 0,0,0, 1,1,1")
    assert "did you mean BLOCK?" in msg


def test_misspelt_command_far_from_any_gets_no_suggestion(p):
    msg = fails(p, "QQQQQQQ, 1")
    assert "did you mean" not in msg


def test_misspelt_body_name_suggests_the_body(p):
    run(p, "BLOCK, 0,0,0, 10,10,10\nNAME, LAST, plate\nCYL, 0,0,0, 2, 20\nNAME, LAST, peg")
    msg = fails(p, "SUBTRACT, plaet, peg")
    assert "did you mean plate?" in msg


def test_misspelt_parameter_suggests_the_parameter(p):
    run(p, "WIDTH = 30")
    msg = fails(p, "BLOCK, 0,0,0, WIDHT, 10, 10")
    assert "WIDHT" in msg.upper() and "did you mean WIDTH" in msg


def test_failed_history_step_message_has_the_suggestion(p):
    run(p, "BLOCK, 0,0,0, 10,10,10\nNAME, LAST, plate\nCYL, 0,0,0, 2, 20\nNAME, LAST, peg\nSUBTRACT, plate, peg")
    run(p, 'HIST, EDIT, 5, "SUBTRACT, plaet, peg"')
    e = p.history[4]
    assert not e.ok and "did you mean plate?" in e.message


def test_did_you_mean_leaves_other_messages_alone(p):
    assert p.did_you_mean("FILLET: radius too big") == "FILLET: radius too big"
    assert p.did_you_mean("") == ""
    once = p.did_you_mean("unknown command 'BLOK'")
    assert p.did_you_mean(once) == once  # not twice


def test_near_fixes_rewrite_the_line():
    from modeler.commands.why_handlers import near_fixes

    got = near_fixes("blok, 1,1,1,2,2,2", "unknown command 'BLOK' (type HELP for a list); did you mean BLOCK?")
    assert got == [("Use BLOCK", "BLOCK, 1,1,1,2,2,2")]
    got = near_fixes("SUBTRACT, plaet, b", "no body or parameter named 'plaet'; did you mean plate or plat?")
    assert [g[1] for g in got] == ["SUBTRACT, plate, b", "SUBTRACT, plat, b"]
    assert near_fixes("SUBTRACT, xplaet, b", "no body named 'plaet'; did you mean plate?") == []
    assert near_fixes("", "x") == [] and near_fixes("FILLET, 9", "too big") == []


# ---- 89: what is at fault --------------------------------------------------------------------
def test_fault_from_the_entities_the_message_names(p):
    from modeler.commands.why_handlers import fault_for

    run(p, "BLOCK, 0,0,0, 10,10,10")
    f = fault_for(p, "X", "the faces 2 and 3 cannot be joined")
    assert f == {"kind": "FACE", "ids": [2, 3], "from": "the message"}
    f = fault_for(p, "X", "edge 4 is too short")
    assert f["kind"] == "EDGE" and f["ids"] == [4]
    assert fault_for(p, "X", "face 999 is odd") is None  # not an entity: nothing


def test_fault_is_the_pick_for_a_typed_line(p):
    from modeler.commands.why_handlers import fault_for

    run(p, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1")
    msg = fails(p, "FILLET, 50")
    f = fault_for(p, "FILLET, 50", msg, typed=True)
    assert f["kind"] == "EDGE" and f["ids"] == [1] and f["from"] == "the pick it used"


def test_fault_is_the_body_when_the_pick_is_elsewhere(p):
    from modeler.commands.why_handlers import fault_for

    run(p, "BLOCK, 0,0,0, 10,10,10\nNAME, LAST, plate\nBLOCK, 30,0,0, 10,10,10\nNAME, LAST, other\nBLOCK, 90,0,0, 5,5,5")
    run(p, "PICK, EDGE, 30")  # an edge of the third block
    f = fault_for(p, "SUBTRACT, plate, other", "SUBTRACT: nothing is left", typed=True)
    assert f["kind"] == "BODY" and sorted(f["ids"]) == [1, 2]


def test_unknown_command_has_no_fault(p):
    from modeler.commands.why_handlers import fault_for

    run(p, "BLOCK, 0,0,0, 10,10,10\nPICK, FACE, 1")
    assert fault_for(p, "BLOK, 1", "unknown command 'BLOK'", typed=True) is None


def _failed_fillet(p):
    run(p, 'BLOCK, 0,0,0, 20, 20, 20\nPICK, EDGE, 1\nFILLET, 5\nHIST, EDIT, 1, "BLOCK, 0,0,0, 4, 4, 4"')
    assert not p.history[2].ok


def test_step_fault_uses_the_pick_the_step_was_given(p):
    from modeler.commands.why_handlers import failed_steps, step_fault

    _failed_fillet(p)
    assert failed_steps(p) == [3]
    f = step_fault(p, 3)
    assert f["kind"] == "EDGE" and f["ids"] == [1]


def test_diagnose_returns_the_fault(p):
    from modeler.ai.diagnose import diagnose

    _failed_fillet(p)
    d = diagnose(p, 3)
    assert d["fault"]["kind"] == "EDGE" and d["fault"]["ids"] == [1]
    assert d["fixes"] and d["fixes"][0]["run"].startswith("HIST, EDIT, 3")


def test_diagnose_of_a_typed_line_returns_the_fault(p):
    from modeler.ai.diagnose import diagnose

    run(p, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1")
    d = diagnose(p, line="FILLET, 50")
    assert d["fault"] == {"kind": "EDGE", "ids": [1], "from": "the pick it used"}


def test_why_on_a_failed_step(p):
    _failed_fillet(p)
    r = run(p, "WHY, 3")
    assert "Step 3" in r.message and "Fixes" in r.message
    assert "At fault: edge 1" in r.message
    assert len(p.model.preview) == 1 and p.model.preview[0][1] == "fault"  # red in the view
    run(p, "WHY, OFF")
    assert p.model.preview == []


def test_why_json_and_default_step(p):
    _failed_fillet(p)
    d = json.loads(run(p, "WHY, 3, JSON").message)
    assert d["step"] == 3 and d["failed"] and d["fault"]["ids"] == [1]
    d2 = json.loads(run(p, "WHY, JSON").message)  # the first failed step
    assert d2["step"] == 3


def test_why_on_the_last_typed_failure(p):
    run(p, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1")
    fails(p, "FILLET, 50")
    r = run(p, "WHY")
    assert "FILLET, 50" in r.message and "edge 1" in r.message


def test_why_on_a_good_step_and_errors(p):
    run(p, "BLOCK, 0,0,0, 10,10,10")
    assert "without a problem" in run(p, "WHY, 1").message
    assert "1 history steps" in fails(p, "WHY, 7")
    assert "step number" in fails(p, "WHY, abc")
    assert "no step has failed" in fails(p, "WHY")
    assert "cleared" in run(p, "WHY, OFF").message


def test_why_is_not_in_the_history(p):
    _failed_fillet(p)
    n = len(p.history)
    run(p, "WHY, 3")
    run(p, "WHY, OFF")
    assert len(p.history) == n


def test_why_lights_up_and_off_clears(p):
    from modeler.commands import why_handlers as wh

    _failed_fillet(p)

    assert wh.show_fault(p, wh.step_fault(p, 3)) == 1
    assert wh.show_fault(p, None) == 0


def test_fault_text():
    from modeler.commands.why_handlers import fault_text

    assert fault_text(None) == ""
    assert fault_text({"kind": "EDGE", "ids": [3]}) == "at fault: edge 3"
    assert fault_text({"kind": "FACE", "ids": [1, 2]}) == "at fault: faces 1, 2"
    assert fault_text({"kind": "VERTEX", "ids": [1, 2]}) == "at fault: vertices 1, 2"
    assert fault_text({"kind": "BODY", "ids": [4, 5]}) == "at fault: bodies 4, 5"
    assert fault_text({"kind": "FACE", "ids": list(range(30))}).endswith("...")


# ---- 90: REPEAT ------------------------------------------------------------------------------
def test_repeat_runs_the_last_step_on_the_new_pick(p):
    run(p, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1\nFILLET, 2\nPICK, EDGE, 3")
    r = run(p, "REPEAT")
    assert r.message.startswith("repeated FILLET, 2")
    assert [e.text for e in p.history][-2:] == ["PICK, EDGE, 3", "FILLET, 2"]


def test_repeat_with_a_pick(p):
    run(p, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1\nFILLET, 2")
    run(p, "REPEAT, EDGE, 3 5")
    assert [e.text for e in p.history][-2:] == ["PICK, EDGE, 3 5", "FILLET, 2"]
    assert p.model.bodies[max(p.model.bodies)].shape is not None


def test_repeat_with_sel(p):
    run(p, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1\nFILLET, 2\nSEL, S, EDGE, ID, 3")
    run(p, "REPEAT")
    assert p.history[-1].text == "FILLET, 2"


def test_repeat_show_and_errors(p):
    assert "nothing to repeat" in fails(p, "REPEAT")
    assert "nothing to repeat yet" in run(p, "REPEAT, SHOW").message
    run(p, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1\nFILLET, 2")
    assert run(p, "REPEAT, SHOW").message == "REPEAT runs: FILLET, 2"
    assert "give the IDs" in fails(p, "REPEAT, EDGE")
    msg = fails(p, "REPEAT, EDGE, 999")
    assert msg.startswith("REPEAT:")


def test_repeat_failure_is_reported_and_can_be_diagnosed(p):
    run(p, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1\nFILLET, 2\nPICK, BODY, 2")
    run(p, "PICK, FACE, 1")
    msg = fails(p, "REPEAT")
    assert msg.startswith("REPEAT (FILLET, 2):")
    assert p.last_failure["line"] == "FILLET, 2"


def test_picks_queries_and_history_edits_are_not_repeated(p):
    run(p, "BLOCK, 0,0,0, 20,20,20\nPICK, EDGE, 1\nFILLET, 2")
    for line in ("PICK, EDGE, 3", "SELINFO", "LIST", "UNDO", "REDO", "WHY, OFF", "REPEAT, SHOW",
                 "HIST, ROLLBACK, 3", "HIST, ROLLBACK, 3"):
        p.run(line)
        assert p.last_tool == "FILLET, 2", line


def test_last_tool_follows_model_steps_and_resets(p):
    run(p, "BLOCK, 0,0,0, 20,20,20")
    assert p.last_tool == "BLOCK, 0,0,0, 20,20,20"
    run(p, "CYL, 0,0,0, 2, 30")
    assert p.last_tool == "CYL, 0,0,0, 2, 30"
    fails(p, "FILLET, 9999")
    assert p.last_tool == "CYL, 0,0,0, 2, 30"  # a failed line is not remembered
    p.reset()
    assert p.last_tool == ""


def test_scripts_do_not_set_the_repeat(p):
    p.run_script("BLOCK, 0,0,0, 20,20,20\nCYL, 0,0,0, 2, 30")
    assert p.last_tool == ""


def test_repeat_is_not_logged(p):
    assert not REGISTRY["REPEAT"].logged
    run(p, "BLOCK, 0,0,0, 20,20,20")
    run(p, "REPEAT")
    assert [e.text for e in p.history] == ["BLOCK, 0,0,0, 20,20,20"] * 2


# ---- 91: PROPS -------------------------------------------------------------------------------
def _plate(p):
    run(p, "W = 40\nBLOCK, 0,0,0, W, 20, 10\nNAME, LAST, plate\nMATERIAL, plate, ALUMINIUM\nPICK, EDGE, 1\nFILLET, 2")


def _rows(d):
    return {r["key"]: r for r in d["rows"]}


def test_props_table(p):
    from modeler.commands import props_handlers as ph

    _plate(p)
    bid = p.model.body_by_name("plate").id
    d = ph.properties(p, bid)
    rows = _rows(d)
    assert rows["name"]["value"] == "plate" and rows["name"]["edit"] == "NAME"
    assert (rows["x"]["value"], rows["y"]["value"], rows["z"]["value"]) == (20, 10, 5)
    assert rows["material"]["value"] == "aluminium"
    assert rows["layer"]["value"] == "default"
    assert rows["size"]["value"] == [40, 20, 10]
    assert 0 < rows["mass (kg)"]["value"] < 0.03 and not rows["volume"]["edit"]
    assert rows["2.dx"]["value"] == "W" and rows["2.dx"]["edit"] == "HIST, EDIT"
    assert rows["6.r"]["value"] == "2"
    assert "3.b" not in rows and "4.name" not in rows  # NAME and MATERIAL steps are rows of their own


def test_props_text(p):
    _plate(p)
    text = run(p, "PROPS, plate").message
    assert text.startswith("properties of body 2 (plate), in mm:")
    for word in ("where", "look", "numbers", "step 2: BLOCK", "step 6: FILLET", "2.dx", "PROPS, b, key, value"):
        assert word in text, word


def test_props_of_the_pick(p):
    _plate(p)
    run(p, "PICK, FACE, 3")
    assert "properties of body 2" in run(p, "PROPS").message
    run(p, "PICK, BODY, 2")
    assert json.loads(run(p, "PROPS, SEL, JSON").message)["body"] == 2
    p.model.selection = []
    assert "pick a body" in fails(p, "PROPS")


def test_props_moves_the_centre(p):
    _plate(p)
    r = run(p, "PROPS, plate, x, 50")
    assert r.message.startswith("MOVE, plate, 30, 0, 0")
    assert p.history[-1].text == "MOVE, plate, 30, 0, 0"
    run(p, "PROPS, plate, z, -5")
    assert p.history[-1].text == "MOVE, plate, 0, 0, -10"
    assert "already at" in fails(p, "PROPS, plate, x, 50")
    assert "needs a number" in fails(p, "PROPS, plate, y, nothing_here")


def test_props_expression_value(p):
    _plate(p)
    run(p, "PROPS, plate, x, W + 10")
    assert p.history[-1].text == "MOVE, plate, 30, 0, 0"


def test_props_turn(p):
    _plate(p)
    run(p, "PROPS, plate, turn, Z 90")
    assert p.history[-1].text == "ROTATE, plate, 90, 20, 10, 5, 0, 0, 1"
    rows = _rows(json.loads(run(p, "PROPS, plate, JSON").message))
    assert rows["size"]["value"] == [20, 40, 10]
    assert "axis and an angle" in fails(p, "PROPS, plate, turn, 90")


def test_props_look_rows(p):
    _plate(p)
    run(p, "PROPS, plate, colour, red")
    assert p.history[-1].text == "COLOR, plate, red"
    run(p, "PROPS, plate, color, DEFAULT")
    run(p, "PROPS, plate, material, steel")
    assert p.history[-1].text == "MATERIAL, plate, steel"
    run(p, "PROPS, plate, layer, parts")  # a new layer is made first
    assert [e.text for e in p.history[-2:]] == ["LAYER, parts, NEW", "LAYER, parts, ADD, plate"]
    run(p, "PROPS, plate, layer, default")
    assert p.history[-1].text == "LAYER, default, ADD, plate"
    rows = _rows(json.loads(run(p, "PROPS, plate, JSON").message))
    assert rows["material"]["value"] == "steel" and rows["layer"]["value"] == "default"
    assert "a word of letters" in fails(p, "PROPS, plate, layer, two words")


def test_props_name(p):
    _plate(p)
    run(p, "PROPS, plate, name, base")
    assert p.model.body_by_name("base") is not None
    assert "a word of letters" in fails(p, "PROPS, base, name, 2x")


def test_props_step_value_edits_the_step(p):
    _plate(p)
    run(p, "PROPS, plate, 2.dy, 30")
    assert p.history[1].text == "BLOCK, 0, 0, 0, W, 30, 10"
    rows = _rows(json.loads(run(p, "PROPS, plate, JSON").message))
    assert rows["size"]["value"] == [40, 30, 10]
    run(p, "PROPS, plate, 6.r, 3")
    assert p.history[5].text == "FILLET, 3"
    run(p, "UNDO")
    assert p.history[5].text == "FILLET, 2"


def test_props_read_only_and_unknown_keys(p):
    _plate(p)
    msg = fails(p, "PROPS, plate, volume, 3")
    assert "cannot be changed here" in msg and "2.dx" in msg
    assert "cannot be changed" in fails(p, "PROPS, plate, kind, mesh")
    assert "no body" in fails(p, "PROPS, 99")


def test_props_of_a_part_copy(p):
    p.run_unit("*PART, peg, D=4, L=10\nCYL, 0,0,0, D/2, L\n*ENDPART")
    run(p, "INST, peg, 50,0,0, D=6")
    rows = _rows(json.loads(run(p, "PROPS, LAST, JSON").message))
    assert rows["part"]["value"] == "peg"
    assert rows["2.x"]["value"] == "50" and rows["2.D"]["value"] == "6"
    assert rows["2.L"]["value"] == "10" and "default" in rows["2.L"]["about"]
    run(p, "PROPS, LAST, 2.L, 25")
    assert p.history[1].text == "INST, peg, 50, 0, 0, D=6, L=25"
    run(p, "PROPS, LAST, 2.D, 8")
    assert p.history[1].text == "INST, peg, 50, 0, 0, D=8, L=25"
    rows = _rows(json.loads(run(p, "PROPS, LAST, JSON").message))
    assert rows["size"]["value"] == [8, 8, 25]


def test_props_of_a_step(p):
    run(p, "BLOCK, 0,0,0, 20,10,5\nCYL, 0,0,0, 3, 10\nSUBTRACT, 1, 2")
    text = run(p, "PROPS, STEP 3").message
    assert text.startswith("step 3: SUBTRACT, 1, 2, made body 3") and "3.a" in text
    run(p, "PROPS, #1, dx, 30")
    assert p.history[0].text == "BLOCK, 0, 0, 0, 30, 10, 5"
    run(p, "PROPS, step1, 1.dz, 8")
    assert p.history[0].text == "BLOCK, 0, 0, 0, 30, 10, 8"
    assert "3 history steps" in fails(p, "PROPS, STEP 9")
    assert "has no value" in fails(p, "PROPS, #1, radius, 3")


def test_props_of_a_block_step(p):
    from modeler.commands import props_handlers as ph

    run(p, "*DO, i, 1, 2\nBLOCK, i*20, 0, 0, 5, 5, 5\n*ENDDO")
    d = ph.step_properties(p, 1)
    assert d["rows"] == [] and "block" in d["note"]


def test_props_many_steps_shows_the_first_and_last(p):
    from modeler.commands import props_handlers as ph

    run(p, "BLOCK, 0,0,0, 40,40,40")
    for e in (1, 2, 3, 4, 5):
        run(p, f"PICK, EDGE, {e}\nFILLET, 1")
    rows = ph.step_rows(p, max(p.model.bodies))
    steps = sorted({r["step"] for r in rows})
    assert len(steps) == ph.MAX_STEPS and steps[0] == 1


def test_props_is_not_logged(p):
    assert not REGISTRY["PROPS"].logged
    _plate(p)
    n = len(p.history)
    run(p, "PROPS, plate")
    assert len(p.history) == n


# ---- the assistant ---------------------------------------------------------------------------
def test_assistant_properties_tool(p):
    from modeler.ai.tools import Toolbox

    _plate(p)
    tb = Toolbox(p)
    assert "properties" in tb.tools
    d = tb.call("properties", {"body": "plate"})
    assert d["body"] == 2 and any(r["key"] == "2.dx" for r in d["rows"]) and "PROPS" in d["change"]
    run(p, "PICK, FACE, 3")
    assert tb.properties()["body"] == 2
    assert tb.properties(step=2)["step"] == 2
    assert "error" in tb.call("properties", {"step": 99})
    assert "error" in tb.call("properties", {"body": "nothing"})


def test_assistant_diagnose_tool_has_the_fault(p):
    from modeler.ai.tools import Toolbox

    _failed_fillet(p)
    d = Toolbox(p).call("diagnose", {"step": 3})
    assert d["fault"]["kind"] == "EDGE"


def test_skill_notes():
    import os

    import modeler

    root = os.path.join(os.path.dirname(modeler.__file__), "skills")
    basics = open(os.path.join(root, "modeling-basics", "SKILL.md"), encoding="utf-8").read()
    assert "REPEAT" in basics and "SEL, S, EDGE" in basics and "`properties`" in basics
    fixing = open(os.path.join(root, "fixing-failed-steps", "SKILL.md"), encoding="utf-8").read()
    assert "`fault`" in fixing and "WHY, n" in fixing and "did you mean" in fixing
