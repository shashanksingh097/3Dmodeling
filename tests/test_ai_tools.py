"""Tools for the AI assistant (docs/M9-ai-tools.md, step M9a): reading the model
as text, ASSERT and its queries, selectors, LINT, DIFF and the sandbox.

The answer formats are checked exactly where it matters, because the
assistant relies on them staying the same."""

import json

import pytest

from modeler.__main__ import main
from modeler.ai import describe as ds
from modeler.ai import selectors as sl
from modeler.ai.sandbox import Sandbox
from modeler.ai.tools import Toolbox
from modeler.commands import Processor
from modeler.geometry import recognize as rc

FLANGE = """D = 100
T = 12
CYL, 0,0,0, D/2, T
NAME, LAST, flange
HOLE, flange, 0,0,T, 30
*DO, i, 0, N - 1
  HOLE, flange, 40*cos(i*360/N), 40*sin(i*360/N), T, 8
*ENDDO
"""


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1].message if rs else ""


def err(p, line):
    r = p.run(line)
    assert not r.ok, r.message
    return r.message


def flange(p, n=6):
    ok(p, f"N = {n}\n" + FLANGE)
    return p.model.body_by_name("flange")


# ---- recognising holes ---------------------------------------------------------------


def test_holes_through_blind_counterbore_and_drill_tip(p):
    ok(p, "BLOCK, 0,0,0, 60,40,10\nNAME, LAST, plate\n"
          "HOLE, plate, 10,10,10, 6\n"  # through
          "HOLE, plate, 25,10,10, 6, 4\n"  # blind, flat floor
          "HOLE, plate, 40,10,10, 5, 6, SIMPLE, , , 118\n"  # blind with a drill point
          "HOLE, plate, 10,30,10, 6, , CBORE, 11, 4\n"  # through, counterbored
          "HOLE, plate, 30,30,10, 6, , CSINK, 12\n")  # through, countersunk
    found = rc.holes(p.model.body_by_name("plate").shape)
    rows = sorted((round(h.d, 3), h.through, round(h.depth, 3), h.counterbore and round(h.counterbore[0], 3),
                   round(h.centre[0], 3), round(h.centre[1], 3)) for h in found)
    assert rows == [
        (5.0, False, 6.0, None, 40.0, 10.0),
        (6.0, False, 4.0, None, 25.0, 10.0),
        (6.0, True, 6.0, 11.0, 10.0, 30.0),
        (6.0, True, 10.0 - 3.0, None, 30.0, 30.0),  # the countersink cone takes the top 3 mm
        (6.0, True, 10.0, None, 10.0, 10.0),
    ]
    blind = next(h for h in found if h.d == pytest.approx(6) and not h.through)
    assert blind.mouth[2] == pytest.approx(10)  # the open end is at the top


def test_a_concave_fillet_is_not_a_hole(p):
    ok(p, "BLOCK, 0,0,0, 20,20,5\nBLOCK, 0,0,5, 5,20,10\nUNION, 1, 2\n"
          "SEL, S, EDGE, LOC, Z, 5\nSEL, R, EDGE, LOC, X, 5\nFILLET, 2")
    b = p.model.bodies[p.model.last_body]
    assert p.evaluate(f"NFACES({b.id}, \"cylinder\")") == 1  # the fillet is a quarter cylinder ...
    assert rc.holes(b.shape) == []  # ... and not a hole


# ---- queries for ASSERT -----------------------------------------------------------------


def test_new_queries(p):
    flange(p)
    assert p.evaluate("VALID(flange)") == 1
    assert p.evaluate("PIECES(flange)") == 1
    assert p.evaluate("NFACES(flange)") == 10
    assert p.evaluate("NFACES(flange, \"cylinder\")") == 8
    assert p.evaluate("HOLES(flange)") == 7
    assert p.evaluate("HOLES(flange, 8)") == 6
    assert p.evaluate("HOLES(flange, 30, 1)") == 1
    assert p.evaluate("HOLES(flange, 8, 0)") == 0
    assert p.evaluate("SYMMETRIC(flange, \"YZ\")") == 1
    assert p.evaluate("SYMMETRIC(flange, \"XY\")") == 0
    ok(p, "MOVE, flange, 0, 0, -6")
    assert p.evaluate("SYMMETRIC(flange, \"XY\")") == 1
    ok(p, "BLOCK, 100,0,0, 1,1,1\nNAME, LAST, a\nBLOCK, 200,0,0, 1,1,1\nUNION, a, LAST")
    assert p.evaluate("PIECES(LAST)") == 2


def test_assert_passes_quietly_and_fails_the_step(p):
    flange(p)
    n = len(p.history)
    assert ok(p, "ASSERT, HOLES(flange, 8), EQ, 6") == "ok: HOLES(flange, 8) = 6"
    assert len(p.history) == n + 1  # a check is part of the script
    ok(p, "ASSERT, VALID(flange)\nASSERT, BBOX(flange).dz, EQ, 12, 0.01\nASSERT, VOL(flange), BETWEEN, 80000, 83000\n"
          "ASSERT, VOL(flange) > 1000\nASSERT, PIECES(flange), EQ, 1")
    assert err(p, "ASSERT, BBOX(flange).dz, EQ, 12.5, 0.01") == \
        "ASSERT failed: BBOX(flange).dz is 12, expected EQ 12.5 (± 0.01)"
    assert err(p, "ASSERT, SYMMETRIC(flange, \"XY\")") == 'ASSERT failed: SYMMETRIC(flange, "XY") is false'
    assert "expected GT 1000000" in err(p, "ASSERT, VOL(flange) > 1e6")
    assert "not a number" in err(p, "ASSERT, BBOX(flange), EQ, 1")
    assert "unknown comparison" in err(p, "ASSERT, VOL(flange), ABOUT, 1")


def test_assert_follows_parameter_edits(p):
    flange(p)
    ok(p, "ASSERT, HOLES(flange, 8), EQ, N")
    p.edit_entry(1, "N = 9")
    assert all(e.ok for e in p.history)
    assert p.evaluate("HOLES(flange, 8)") == 9


# ---- describing ---------------------------------------------------------------------------


def test_describe_body_summary_format(p):
    flange(p)
    d = ds.describe_body(p, "flange")
    holes = d.pop("holes")
    d.pop("rev")
    assert d == {"unit": "mm", "body": d["body"], "name": "flange", "kind": "solid", "valid": True,
                 "volume": 82146.365, "pieces": 1, "area": 20401.503, "bbox": [-50.0, -50.0, 0.0, 50.0, 50.0, 12.0],
                 "centre": [0.0, 0.0, 6.0], "counts": {"faces": 10, "edges": 24, "vertices": 16},
                 "made_by": 7, "face_types": {"cylinder": 8, "plane": 2}, "flat_faces": {"+Z": 1, "-Z": 1}}
    assert [(h["d"], h["n"], h["through"]) for h in holes] == [(8.0, 6, True), (30.0, 1, True)]
    assert holes[0]["pattern"] == {"circle": [0.0, 0.0, 12.0], "r": 40.0, "step_deg": 60.0}
    assert len(json.dumps(d)) + len(json.dumps(holes)) < 1600  # a few hundred tokens


def test_describe_faces_and_edges(p):
    flange(p)
    faces = ds.describe_body(p, "flange", "faces")["faces"]
    assert [f["id"] for f in faces] == sorted(f["id"] for f in faces)
    top = next(f for f in faces if f.get("normal") == [0.0, 0.0, 1.0])
    assert top["type"] == "plane" and top["centre"][2] == 12.0 and len(top["next_to"]) == 8
    walls = [f for f in faces if f["type"] == "cylinder" and f["inner"]]
    assert sorted(f["r"] for f in walls) == [4.0] * 6 + [15.0]
    edges = ds.describe_body(p, "flange", "edges")["edges"]
    rim = [e for e in edges if e.get("r") == 50.0]
    assert len(rim) == 2 and all(len(e["faces"]) == 2 for e in rim)


def test_describe_command(p):
    flange(p)
    text = ok(p, "DESCRIBE, flange")
    assert "holes:" in text and "d 8 n 6 through yes" in text
    data = json.loads(p.run("DESCRIBE, flange, JSON").message)
    assert data["name"] == "flange"
    assert json.loads(p.run("DESCRIBE, JSON").message)["bodies"][0]["name"] == "flange"
    ok(p, "SEL, S, FACE, NORMAL, 0,0,1")
    assert "faces:" in p.run("DESCRIBE, SEL").message
    assert "no body named 'nope'" in err(p, "DESCRIBE, nope")
    n = len(p.history)
    p.run("DESCRIBE")
    assert len(p.history) == n  # DESCRIBE only reads


# ---- selectors -------------------------------------------------------------------------------


def test_selector_for_survives_a_history_edit(p):
    ok(p, "W = 40\nBLOCK, 0,0,0, W, 20, 10\nNAME, LAST, plate\nHOLE, plate, 10, 10, 10, 6\nHOLE, plate, 30, 10, 10, 4")
    small = next(f for f in ds.describe_body(p, "plate", "faces")["faces"] if f.get("r") == 2.0)
    out = sl.selector_for(p, "FACE", small["id"])
    assert out["unique"] and out["robust"]
    assert sl.preview_selection(p, out["lines"])["ids"] == [small["id"]]
    ok(p, "\n".join(out["lines"]))
    # an earlier step changes: the hole's face may get another ID, the lines still find it
    p.edit_entry(1, "W = 60")
    assert len(p.model.selection) == 1
    f = ds.describe_entities(p, "FACE", p.model.selection)["faces"][0]
    assert f["r"] == 2.0 and f["centre"][0] == 30.0


def test_selector_for_look_alikes_and_bodies(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nNAME, LAST, cube\nBLOCK, 20,0,0, 10,10,10")
    assert sl.selector_for(p, "BODY", 1) == {"kind": "BODY", "id": 1, "unique": True, "robust": True,
                                             "lines": ["SEL, S, BODY, ID, cube"]}
    assert sl.selector_for(p, "BODY", 2)["robust"] is False  # no name: only the ID
    top = sl.selector_for(p, "FACE", p.model.bodies[2].entity_ids["FACE"][5])
    assert top["unique"] and sl.preview_selection(p, top["lines"])["count"] == 1
    edge = ok(p, "SELFOR, EDGE, 1").splitlines()
    assert sl.preview_selection(p, edge)["ids"] == [1]


def test_preview_leaves_the_selection_and_history_alone(p):
    flange(p)
    ok(p, "SEL, S, FACE, NORMAL, 0,0,-1")
    before = (list(p.model.selection), p.model.selection_kind, len(p.history), p.model.revision)
    got = sl.preview_selection(p, ["SEL, S, FACE, TYPE, CYLINDER", "SEL, R, FACE, RADIUS, EQ, 4"])
    assert got["count"] == 6 and got["after_each_line"] == [8, 6]
    assert (list(p.model.selection), p.model.selection_kind, len(p.history), p.model.revision) == before
    with pytest.raises(sl.SelectorError):
        sl.preview_selection(p, ["BLOCK, 0,0,0, 1,1,1"])


# ---- LINT and DIFF --------------------------------------------------------------------------------


def test_lint_finds_problems_without_running(p):
    from modeler.ai.lint import lint

    out = lint(p, "W = 10\nBLOK, 0,0,0, W, W, W\nCYL, 0,0,0, R, 5\nPICK, FACE, 3\nCYL, 1,2,3,4,5,6,7,8,9,10\n"
                  "SAVE, \"x.m3d\"\nSEL, S, FACE, ID, 4\nBLOCK, 0,0\n*DO, i, 1, 3\n  BLOCK, i, 0, 0, 1, 1, 1\n*ENDDO",
               sandbox=True)
    msgs = [(i["line"], i["level"], i["msg"].split(";")[0]) for i in out["issues"]]
    assert (2, "error", "unknown command BLOK") in msgs
    assert (3, "warning", "R is not set before this line") in msgs
    assert any(m[0] == 4 and m[1] == "warning" for m in msgs)
    assert any(m[0] == 5 and "at most" in m[2] for m in msgs)
    assert any(m[0] == 6 and "sandbox" in m[2] for m in msgs)
    assert any(m[0] == 7 and "SEL by ID" in m[2] for m in msgs)
    assert (8, "error", "BLOCK is missing z, dx, dy, dz") in msgs
    assert not any(m[0] in (9, 10) for m in msgs)  # the loop variable is known
    assert out["ok"] is False
    assert "did you mean BLOCK" in next(i["msg"] for i in out["issues"] if i["line"] == 2)
    assert lint(p, open("scripts/flange.cmd").read())["issues"] == []
    assert ok(p, "LINT") == "no problems found"


def test_diff_between_history_positions(p):
    flange(p)
    d = ok(p, "DIFF, 0")
    assert "+ body" in d and "flange" in d and "N = 6 (new)" in d
    ok(p, "MOVE, flange, 0, 0, 5")
    last = json.loads(p.run("DIFF, , , JSON").message)
    assert last["changed"][0]["name"] == "flange" and "bbox" in last["changed"][0]
    assert "volume" not in last["changed"][0] or last["changed"][0]["volume"][0] == last["changed"][0]["volume"][1]


# ---- the sandbox ----------------------------------------------------------------------------------


def test_sandbox_never_touches_the_model(p):
    flange(p)
    before = (len(p.history), p.cursor, dict(p.model.bodies), p.model.revision, dict(p.params))
    box = Sandbox(p)
    out = box.run("CYL, 0,0,T, 20, 10\nUNION, flange, LAST\nASSERT, HOLES(flange, 30), EQ, 1")
    assert out["ok"], out
    assert out["entries"][0]["changes"]["added"][0]["faces"] == 3
    assert box.p.evaluate("BBOX(flange).dz") == pytest.approx(22)
    assert (len(p.history), p.cursor, dict(p.model.bodies), p.model.revision, dict(p.params)) == before
    assert box.script() == "CYL, 0,0,T, 20, 10\nUNION, flange, LAST\nASSERT, HOLES(flange, 30), EQ, 1"


def test_sandbox_starts_and_stops(p):
    flange(p)
    empty = Sandbox(p, "empty")
    assert empty.p.model.bodies == {} and empty.p.cursor == 0
    early = Sandbox(p, 6)  # the model before entry 6 (the first HOLE)
    assert early.p.cursor == 5 and early.p.evaluate("NFACES(flange)") == 3
    out = Sandbox(p).run("EXPORT, STEP, \"x.step\"")
    assert out["ok"] is False and "sandbox" in out["refused"][0]["msg"]
    out = Sandbox(p).run("BOX, 1\nBLOCK, 0,0,0, 1,1,1", stop_on_error=True)
    assert len(out["entries"]) == 1 and "hint" in out["entries"][0]
    out = Sandbox(p).run("K = 0\n*WHILE, K >= 0\n  K = K + 1\n*ENDWHILE", time_limit=0.2)
    assert out["ok"] is False and "time limit" in out["entries"][-1]["msg"]


# ---- the tool list -------------------------------------------------------------------------------


def test_tool_definitions_are_well_formed(p):
    box = Toolbox(p)
    defs = box.definitions()
    names = [d["name"] for d in defs]
    assert len(names) == len(set(names))
    for d in defs:
        schema = d["input_schema"]
        assert schema["type"] == "object" and set(schema["required"]) <= set(schema["properties"])
        assert d["description"]
    json.dumps(defs)


def test_the_flange_request_without_a_picture(p):
    """The worked example of docs/M9-ai-tools.md section 4, step by step."""
    box = Toolbox(p)
    assert box.call("model_summary")["bodies"] == []
    assert box.call("lint", {"script": "N = 6\n" + FLANGE})["ok"]
    assert box.call("sandbox", {"start": "empty"})["history"] == 0
    run = box.call("run", {"script": "N = 6\n" + FLANGE + "SEL, S, EDGE, RADIUS, EQ, D/2\nFILLET, 2"})
    assert run["ok"], run
    checks = box.call("check", {"expectations": [
        "BBOX(flange).dx, EQ, 100, 0.001", "BBOX(flange).dz, EQ, 12, 0.001", "HOLES(flange, 8), EQ, 6",
        "HOLES(flange, 30), EQ, 1", "VALID(flange)", "PIECES(flange), EQ, 1", "SYMMETRIC(flange, \"YZ\")"]})
    assert checks["failed"] == 0, checks
    assert box.call("diff")["added"][0]["name"] == "flange"
    assert box.call("sandbox_script")["entries"] == 9
    assert p.model.bodies == {} and p.history == []  # the user's model is untouched


def test_tool_errors_are_answers(p):
    box = Toolbox(p)
    assert "hint" in box.call("nope")
    assert box.call("describe_body", {})["error"] == "describe_body needs body"
    assert "no argument" in box.call("model_summary", {"x": 1})["error"]
    assert box.call("describe_body", {"body": "x"})["error"] == "no body named 'x'"
    assert box.call("undo")["hint"] == "call sandbox first"
    assert box.call("command_help", {"name": "hole"})["name"] == "HOLE"
    assert box.call("find_commands", {"query": "fillet"})["commands"][0].startswith("FILLET")


def test_tool_command_line(capsys, tmp_path):
    script = tmp_path / "f.cmd"
    script.write_text("N = 6\n" + FLANGE)
    assert main(["tool", "--script", str(script), "describe_body", '{"body": "flange"}']) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["holes"][0]["n"] == 6
    assert main(["tools"]) == 0
    assert any(t["name"] == "run" for t in json.loads(capsys.readouterr().out))
