"""Help when a step fails (ai/diagnose.py), features found from faces (geometry/feature_finder.py),
around and outline (ai/describe.py), the small first prompt and the bigger benchmark (PLAN items 46, 47)."""

from __future__ import annotations

import asyncio
import json

import pytest

from modeler.ai import bench
from modeler.ai import describe as ds
from modeler.ai import diagnose as dg
from modeler.ai.tools import Toolbox
from modeler.commands import Processor

FILLET_AFTER_SHELL = """R = 0.3 ! edge radius
BLOCK, 0,0,0, 20,20,10
NAME, LAST, box
SEL, S, FACE, NORMAL, 0, 0, 1
SHELL, 1
SEL, S, EDGE, BODY, box
FILLET, R
"""


def broken() -> Processor:
    p = Processor()
    assert all(r.ok for r in p.run_script(FILLET_AFTER_SHELL))
    assert p.run('HIST, EDIT, 1, "R = 3 ! edge radius"').ok
    assert not p.history[6].ok
    return p


# ---- diagnose ---------------------------------------------------------------------------
def test_diagnose_a_failed_history_step_and_its_fixes_work():
    p = broken()
    d = dg.diagnose(p)
    assert d["step"] == 7 and d["failed"] and "largest radius" in d["message"]
    assert d["command"] == "FILLET" and "fixing-failed-steps" in d["guides"] and "enclosure" in d["guides"]
    fixes = d["fixes"]
    assert fixes and fixes[0]["run"].startswith('HIST, EDIT, 1, "R = 0.')
    assert "! edge radius" in fixes[0]["run"]  # the comment is kept
    assert any(f["run"].startswith("HIST, EDIT, 7") for f in fixes)
    # the user's model is untouched, and the first fix really works on it
    assert not p.history[6].ok
    assert p.run(fixes[0]["run"]).ok
    assert all(e.ok for e in p.history[:p.cursor])
    text = dg.why_text(d)
    assert text.startswith("Step 7: FILLET, R") and "Fixes (tried on a copy" in text


def test_diagnose_a_shell_after_a_fillet_suggests_moving_it():
    p = Processor()
    for line in ["BLOCK, 0,0,0, 40,30,20", "NAME, LAST, box", "SEL, S, FACE, NORMAL, 0, 0, 1", "SHELL, 2"]:
        assert p.run(line).ok
    p.run('HIST, INSERT, 3, "SEL, S, EDGE, BODY, box"')
    p.run('HIST, INSERT, 4, "FILLET, 5"')
    assert not p.history[5].ok
    d = dg.diagnose(p, 6)
    rows = d.get("fixes", []) + d.get("tried", [])
    move = next(r for r in rows if "shell before rounding" in r["fix"])
    assert "steps 5-6 to 3" in move["fix"]
    assert "HIST, MOVE" in (move.get("run") or "HIST, MOVE")


def test_diagnose_typed_lines_and_names():
    p = Processor()
    p.run("BLOCK, 0,0,0, 10,10,10")
    p.run("NAME, LAST, box")
    d = dg.diagnose(p, line="FILET, 2")
    assert d["fixes"][0]["fix"] == "FILLET instead of FILET" and d["fixes"][0]["run"] == "FILLET, 2"
    assert "then" in d["fixes"][0]  # the name is right; the step then says what else is missing
    d = dg.diagnose(p, line="SUBTRACT, bx, 2")
    assert d["fixes"][0]["run"] == "SUBTRACT, box, 2"
    assert dg.diagnose(p, line="ECHO, 1")["ok"]
    # the last typed line that failed is what a bare diagnose looks at
    assert not p.run("FILLET, 99").ok
    assert dg.diagnose(p)["line"] == "FILLET, 99"
    with pytest.raises(dg.DiagnoseError):
        dg.diagnose(Processor())
    with pytest.raises(dg.DiagnoseError):
        dg.diagnose(p, 9)


def test_diagnose_and_history_tools():
    p = broken()
    box = Toolbox(p)
    out = box.call("diagnose", {"step": 7})
    assert out["step"] == 7 and out["fixes"]
    rows = box.call("history")["entries"]
    assert rows[6]["status"] == "failed" and "largest radius" in rows[6]["error"]
    assert "error" in box.call("diagnose", {"step": 99})


# ---- features, around, outline ----------------------------------------------------------
PLATE = """BLOCK, 0,0,0, 80,60,20
NAME, LAST, plate
SEL, S, EDGE, BOX, -1,-1,-1, 81,61,0.5
FILLET, 3
SEL, S, EDGE, BOX, -1,-1,19.5, 81,61,21
CHAMFER, 1.5
BLOCK, 10,10,10, 20,20,10
SUBTRACT, plate, LAST
BLOCK, 40,25,14, 30,6,6
SUBTRACT, plate, LAST
CYL, 60, 45, 20, 4, 8
UNION, plate, LAST
SEL, NONE
"""


@pytest.fixture(scope="module")
def plate():
    p = Processor()
    assert all(r.ok for r in p.run_script(PLATE))
    return p


def test_features_in_describe_body(plate):
    feats = ds.describe_body(plate, "plate")["features"]
    kinds = {f["kind"]: f for f in feats}
    assert kinds["round"]["r"] == 3.0 and kinds["round"]["n"] == 4
    assert kinds["chamfer"]["d"] == 1.5 and kinds["chamfer"]["n"] == 4
    assert kinds["boss"]["d"] == 8.0 and kinds["boss"]["height"] == 8.0 and kinds["boss"]["axis"] == "+Z"
    assert kinds["pocket"]["depth"] == 10.0 and kinds["pocket"]["size"] == [20.0, 20.0]
    assert kinds["slot"]["depth"] == 6.0 and kinds["slot"]["size"] == [30.0, 6.0]
    assert kinds["pocket"]["open_to"] == "+Z" and kinds["pocket"]["floor"] in kinds["pocket"]["faces"]


def test_no_false_features():
    p = Processor()
    p.run_script("CYL, 0,0,0, 50, 12\nCYL, 0,0,-1, 15, 14\nSUBTRACT, 1, 2\nBLOCK, 100,0,0, 10,10,10")
    for b in p.model.bodies.values():
        assert ds.feature_groups(p, b) == []  # a disc is no boss, a bore is a hole, a block has nothing
    p = Processor()
    p.run("GEAR, 0, 0, 0, 2, 20, 10")
    assert not [g for g in ds.feature_groups(p, next(iter(p.model.bodies.values())))
                if g["kind"] in ("fillet", "round")]  # tooth flanks are not blends


def test_around(plate):
    floor = next(f for f in ds.describe_body(plate, "plate")["features"] if f["kind"] == "pocket")["floor"]
    a = ds.around(plate, "FACE", floor)
    assert a["of"]["part_of"] == "pocket depth 10 (floor)"
    walls = a["rings"][0]["faces"]
    assert len(walls) == 4 and {w["facing"] for w in walls} == {"+X", "-X", "+Y", "-Y"}
    assert a["features_nearby"] == ["pocket depth 10"]
    edge = ds.describe_body(plate, "plate", "edges")["edges"][0]["id"]
    two = ds.around(plate, "EDGE", edge, 2)
    assert len(two["rings"]) == 2 and len(two["rings"][0]["faces"]) == 2
    with pytest.raises(ds.DescribeError):
        ds.around(plate, "FACE", 9999)
    assert Toolbox(plate).call("around", {"kind": "FACE", "id": floor})["rings"]


def test_outline(plate):
    o = ds.outline(plate, "plate", "TOP")
    assert (o["x_is"], o["y_is"], o["width"], o["height"]) == ("X", "Y", 80.0, 60.0)
    assert o["circles"] == [{"centre": [60.0, 45.0], "r": 4.0}]
    assert o["points"] <= 400 and o["svg_path"].startswith("M ")
    pts = {tuple(q) for line in o["lines"] for q in line}
    assert (10.0, 10.0) in pts and (30.0, 30.0) in pts  # the pocket's corners
    iso = ds.outline(plate, "plate", "ISO", hidden=True)
    assert iso["hidden_lines"] and iso["x_is"] == "screen right"
    assert len(json.dumps(iso)) < 6000
    with pytest.raises(ds.DescribeError):
        ds.outline(plate, "plate", "SIDEWAYS")


# ---- the first prompt and the picture tools --------------------------------------------
def test_small_first_prompt_and_skills_off():
    from modeler.ai.copilot import SKILL_LINE, first_prompt

    full, small = first_prompt("/tmp/x"), first_prompt("/tmp/x", small=True)
    assert len(small.encode()) < 0.5 * len(full.encode())
    assert "Every command by family" in small and "Sheet metal: SHEET, FLANGE" in small
    assert "Inside a sketch: " in small and "SLINE" in small
    assert "- sheet-metal: " in small
    off = first_prompt("/tmp/x", skills=False)
    assert "load_skill" not in off and SKILL_LINE not in off


def test_skills_off_drops_the_skill_tools():
    from modeler.ai import copilot as cp

    if not cp.sdk_available():
        pytest.skip("the Copilot SDK is not installed")
    a = cp.CopilotAssistant(Processor())
    assert "load_skill" in [t.name for t in a.sdk_tools()]
    a.use_skills = False
    names = [t.name for t in a.sdk_tools()]
    assert "load_skill" not in names and "list_skills" not in names and "diagnose" in names


def test_render_detail_and_compare_with_a_fake_view(plate):
    from modeler.ai import copilot as cp

    if not cp.sdk_available():
        pytest.skip("the Copilot SDK is not installed")

    calls = []
    a = cp.CopilotAssistant(plate)
    a.render_view = lambda *args, **kw: calls.append((args, kw)) or b"PNG"
    out = a._render_detail({"kind": "FACE", "ids": [3]})
    assert out["_png"] == b"PNG" and calls[-1][1] == {"focus": True} and "close-up" in out["shows"]
    assert "error" in a._render_detail({"kind": "FACE", "ids": [99999]})
    assert "no sandbox" in a._render_compare({})["error"]
    a.toolbox.call("run", {"script": "MOVE, plate, 0, 0, 5"})
    out = a._render_compare({"view": "ISO"})
    assert out["changed"] and len(calls[-1][1]["shapes"]) == 1


# ---- the benchmark ----------------------------------------------------------------------
def test_every_skill_area_has_a_task():
    from modeler.ai import skills as sk

    want = set(sk.discover()) - {"sculpting", "drawings-and-tolerances"}  # no exact check for looks or paper
    assert want <= set(bench.AREAS), want - set(bench.AREAS)
    assert len(bench.TASKS) >= 24 and len({t.name for t in bench.TASKS}) == len(bench.TASKS)


def test_the_impossible_shell_is_impossible():
    task = next(t for t in bench.TASKS if t.name == "impossible_shell")
    p = bench.fresh(task)
    assert not p.run("SEL, S, FACE, NORMAL, 0, 0, 1").ok or not p.run("SHELL, 12").ok


def test_modes_compared_and_saved(tmp_path):
    from modeler.ai.copilot import Proposal, Reply

    async def good(t, p):
        return Reply(text="done", tools=["run"], proposals=[Proposal(t.reference, "")], turns=1, input_tokens=9000)

    async def none(t, p):
        return Reply(text="no", tools=["render"], proposals=[], turns=1, input_tokens=3000)

    only = ["flange", "gear_pair"]
    runs = {"full": asyncio.run(bench.run(good, only, log=lambda s: None)),
            "small": asyncio.run(bench.run(none, only, log=lambda s: None))}
    text = bench.compare_text(runs)
    assert "full" in text and "small" in text and "gear_pair" in text and "PASS 9k" in text and "fail 3k" in text
    assert bench.by_area(runs["full"]) == {"gears-and-cams": [1, 1], "holes-and-patterns": [1, 1]}
    path = tmp_path / "b.json"
    bench.save_modes(runs, str(path), {"model": "x"})
    data = json.loads(path.read_text())
    assert data["modes"]["small"]["settings"] == {"small_prompt": True, "skills": True}
    assert data["modes"]["full"]["summary"]["passed"] == 2 and data["modes"]["small"]["summary"]["pictures"] == 2
