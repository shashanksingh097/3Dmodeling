"""Assistant safeguards (PLAN item 66): reading and changing tools kept apart, the effect of a
proposal worked out before it runs, a confirm for broad changes, one undo for a whole proposal,
and DESIGNCHECK rows with severity, measured value, limit, fix and whether the fix works."""

import io
import json

import pytest

from modeler.ai import copilot as cp
from modeler.ai import relate as rl
from modeler.ai import safeguards as sg
from modeler.ai.mcp_server import EXTRA_TOOLS, Server
from modeler.ai.tools import Tool, Toolbox
from modeler.commands import Processor


def ok(p, text):
    for r in p.run_script(text):
        assert r.ok, f"{r.line}: {r.message}"
    return p


@pytest.fixture
def three():
    return ok(Processor(), "W = 10\nBLOCK, 0,0,0, W,10,10\nNAME, LAST, a\nBLOCK, 20,0,0, 10,10,10\nNAME, LAST, b\n"
                           "BLOCK, 40,0,0, 10,10,10\nNAME, LAST, c")


# ---- reading and changing kept apart -----------------------------------------------------
def test_every_tool_has_a_kind_and_only_the_mcp_ones_change_anything():
    box = Toolbox(Processor())
    names = [d["name"] for d in box.definitions()] + list(sg.APP_TOOLS) + [t["name"] for t in EXTRA_TOOLS]
    kinds = {n: sg.kind_of(n) for n in names}
    assert set(kinds.values()) <= set(sg.KINDS)
    assert sorted(n for n, k in kinds.items() if k == "change") == ["apply", "export", "save_project"]
    assert {n for n, k in kinds.items() if k == "propose"} == {"propose_commands", "propose_edits"}
    assert sg.TRY_TOOLS <= set(box.tools), "every trying tool exists"


def _sample(schema: dict, name: str):
    t = schema.get("type")
    if "enum" in schema:
        return schema["enum"][0]
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return True
    if t == "array":
        return []
    if t == "object":
        return {}
    return {"script": "SPHERE, 5,5,5, 2", "body": "a", "a": "a", "b": "b", "kind": "FACE"}.get(name, "a")


def test_no_reading_or_trying_tool_changes_the_users_model(three):
    """Every toolbox tool, called with simple arguments, leaves the model, the history, undo and
    the selection as they were (most answers are errors for such arguments; that is fine)."""
    box = Toolbox(three)
    three.model.selection = [1]
    before = sg.fingerprint(three)
    for name, tool in box.tools.items():
        args = {k: _sample(v, k) for k, v in tool.params.items() if k in tool.required or k in ("script", "body")}
        answer = box.call(name, args)
        assert "changed the user's model" not in str(answer.get("error", "")), name
        assert sg.fingerprint(three) == before, name


def test_a_tool_that_changes_the_model_is_put_back(three):
    box = Toolbox(three)
    box.tools["bad"] = Tool("bad", "changes the model", {}, (), lambda: three.run("DELETE, a").ok and {"ok": 1})
    n, bodies = three.cursor, set(three.model.bodies)
    answer = box.call("bad", {})
    assert "changed the user's model" in answer["error"]
    assert three.cursor == n and set(three.model.bodies) == bodies


# ---- the effect, worked out before anything runs -----------------------------------------
def test_the_effect_of_new_steps(three):
    eff = sg.plan_script(three, "SPHERE, 5,5,10, 3\nUNION, a, LAST\nH = 4")
    assert eff["added"] == [] and [r["body"] for r in eff["changed"]] == ["a"]
    va, vb = eff["changed"][0]["volume"]
    assert va == pytest.approx(1000) and vb > va
    assert eff["params"] == {"H": [None, 4]} and eff["steps_added"] == 3 and not eff["broad"]
    assert "Changes a: volume 1000 to" in eff["text"] and "History: 3 new steps" in eff["text"]
    assert three.cursor == 7 and len(three.model.bodies) == 3, "worked out on a copy"


def test_a_failing_proposal_is_refused_before_the_user_sees_it(three):
    assert "error" in sg.plan_script(three, "FILLET, nothing, 2")


@pytest.mark.parametrize("script, reason", [
    ("DELETE, a", "removes 1 body: a"),
    ("MOVE, a, 1,0,0\nMOVE, b, 1,0,0\nMOVE, c, 1,0,0", "changes 3 existing bodies"),
    ("BLOCK, 20,0,0, 6,10,10\nSUBTRACT, b, LAST", "changes the volume of b by more than half"),
    ('EXPORT, STEP, "x.step"', "reads or writes files"),
])
def test_broad_changes_are_named(three, script, reason):
    eff = sg.plan_script(three, script)
    assert any(reason in r for r in eff["broad"]), eff["broad"]


def test_history_edits_say_how_much_is_re_run():
    p = Processor()
    ok(p, "W = 10\n" + "\n".join(f"SPHERE, {i * 3}, 0, 0, 1" for i in range(12)))
    a = cp.CopilotAssistant(p)
    answer = a._propose_edits({"edits": [{"action": "edit", "entry": 1, "text": "W = 12"}], "summary": "wider"})
    assert answer["shown_to_user"] and "re-runs 13 steps of the history" in answer["needs_confirm"]
    small = a._propose_edits({"edits": [{"action": "edit", "entry": 13, "text": "SPHERE, 36, 0, 0, 1.1"}],
                              "summary": "a bigger last ball"})
    assert small["needs_confirm"] == [] and "1 edited" in small["effect"]


def test_propose_commands_carries_the_plan_and_the_effect(three):
    seen = []
    a = cp.CopilotAssistant(three, on_event=lambda k, d: seen.append((k, d)))
    answer = a._propose({"script": "SPHERE, 5,5,10, 3", "summary": "a ball", "plan": "one ball on top of a"})
    prop = [d for k, d in seen if k == "proposal"][-1]
    assert prop.plan == "one ball on top of a" and prop.effect["added"] and not prop.broad
    assert answer["effect"].startswith("Adds 1 body")
    bad = a._propose({"script": "FILLET, nothing, 2", "summary": "x"})
    assert "fails on a copy" in bad["error"]


# ---- one undo for a whole proposal -----------------------------------------------------
def test_one_undo_takes_back_new_steps_and_history_edits_together(three):
    n = three.cursor
    with three.undo_group("the assistant's proposal"):
        ok(three, "SPHERE, 5,5,10, 3\nUNION, a, LAST")
        ok(three, 'HIST, EDIT, 1, "W = 12"')
    assert three.cursor == n + 2 and three.history[0].text == "W = 12"
    assert "undid the assistant's proposal" in three.run("UNDO").message
    assert three.cursor == n and three.history[0].text == "W = 10" and len(three.model.bodies) == 3
    three.run("REDO")
    assert three.cursor == n + 2 and three.history[0].text == "W = 12"


def test_a_group_that_changes_nothing_adds_no_undo_step(three):
    undo = list(three._undo)
    with three.undo_group("nothing"):
        three.run("BOGUS, 1")
    assert three._undo == undo


# ---- the MCP server: annotations, confirm, one undo ----------------------------------
def _call(s, mid, name, args):
    msg = {"jsonrpc": "2.0", "id": mid, "method": "tools/call", "params": {"name": name, "arguments": args}}
    return s.handle(json.dumps(msg))["result"]["structuredContent"]


def test_mcp_tools_are_annotated_and_a_broad_apply_needs_confirm():
    p = ok(Processor(), "BLOCK, 0,0,0, 10,10,10\nNAME, LAST, a\nBLOCK, 20,0,0, 30,10,10")
    s = Server(Toolbox(p), io.StringIO(), "test")
    tools = s.handle(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))["result"]["tools"]
    hints = {t["name"]: t["annotations"]["readOnlyHint"] for t in tools}
    assert not hints["apply"] and not hints["export"] and hints["model_summary"] and hints["run"]
    _call(s, 2, "run", {"script": "DELETE, a\nSPHERE, 0,0,0, 2"})
    r = _call(s, 3, "apply", {})
    assert r["applied"] == 0 and "removes 1 body: a" in r["needs_confirm"][0] and len(p.model.bodies) == 2
    r = _call(s, 4, "apply", {"confirm": True})
    assert r["applied"] == 2 and "Removes a" in r["effect"]
    p.run("UNDO")
    assert len(p.model.bodies) == 2 and p.model.body_by_name("a") is not None
    assert "no argument" in _call(s, 5, "apply", {"force": True})["error"]


# ---- DESIGNCHECK rows ------------------------------------------------------------------
def test_designcheck_rows_have_severity_values_and_a_checked_fix():
    p = ok(Processor(), "BLOCK, 0,0,0, 20,20,20\nNAME, 1, a\nBLOCK, 30,0,0, 40,10,10\nUNION, a, 2\n"
                        "BLOCK, 0,0,30, 20,20,1\nNAME, LAST, plate")
    pieces = rl.design_check(p, "a")["problems"][0]
    assert pieces == {**pieces, "rule": "pieces", "severity": "warning", "measured": 2, "limit": 1,
                      "fix": "EXPLODE, a", "fix_checked": "fixes it"}
    wall = rl.design_check(p, "plate", min_wall=2)
    row = wall["problems"][0]
    assert row["rule"] == "min_wall" and row["measured"] == pytest.approx(1) and row["limit"] == 2
    assert not row["fix_is_command"] and row["fix_checked"] == "not tried" and wall["warnings"] == 1
    text = p.run("DESIGNCHECK, a").message
    assert "WARNING pieces" in text and "measured 2, limit 1; fix: EXPLODE, a (fixes it on a copy)" in text
    assert len(p.model.bodies) == 2, "the fix was only tried on a copy"


def test_designcheck_an_open_shell_is_an_error_with_heal(tmp_path):
    """An import that is a box with one face missing: an open shell."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS_Shell

    shell, bb = TopoDS_Shell(), BRep_Builder()
    bb.MakeShell(shell)
    exp, k = TopExp_Explorer(BRepPrimAPI_MakeBox(10, 10, 10).Shape(), TopAbs_FACE), 0
    while exp.More():
        if k:
            bb.Add(shell, exp.Current())
        k += 1
        exp.Next()
    path = str(tmp_path / "open.brep")
    BRepTools.Write_s(shell, path)
    p = ok(Processor(), f'IMPORT, BREP, "{path}", box')
    out = rl.design_check(p, "box")
    rows = {x["rule"]: x for x in out["problems"]}
    assert rows["closed"]["severity"] == "error" and rows["closed"]["limit"] == 0 and rows["closed"]["measured"] == 4
    assert rows["closed"]["fix"] == "HEAL, box" and out["errors"] >= 1
    # HEAL finds nothing within its tolerance to join the open edges to: said, not hidden
    assert rows["closed"]["fix_checked"] == "does not fix it"
