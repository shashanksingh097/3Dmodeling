"""Skill files (ai/skills.py), the new read tools (ai/knowledge.py), reports as data and the
analysis queries (docs/M12-assistant-skills.md, PLAN items 43 to 45)."""

from __future__ import annotations

import io
import json
import os

import pytest

from modeler.ai import knowledge as kn
from modeler.ai import skills as sk
from modeler.ai.mcp_server import Server
from modeler.ai.tools import Toolbox
from modeler.commands import Processor

SKILL = """---
name: {name}
description: A test skill. Use for testing.
commands: BLOCK, ASSERT
---
# A test

```cmd
BLOCK, 0, 0, 0, 1, 1, 1
```
"""


def write_skill(root, name, text=None, example="BLOCK, 0, 0, 0, 1, 1, 1\nASSERT, VALID(1)\n"):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(text if text is not None else SKILL.format(name=name), encoding="utf-8")
    if example is not None:
        (d / "example.cmd").write_text(example, encoding="utf-8")
    return d


@pytest.fixture(autouse=True)
def _clean_config():
    sk.configure([], [])
    yield
    sk.configure([], [])


# ---- the built-in skills ----------------------------------------------------------------
def test_every_builtin_skill_is_sound_and_its_example_passes():
    found = sk.discover()
    assert len(found) >= 17
    assert {"modeling-basics", "sheet-metal", "fixing-failed-steps", "strength-and-weight"} <= set(found)
    problems = sk.check_all(run_example=True)
    assert {k: v for k, v in problems.items() if v} == {}


def test_parse_front_matter_and_title():
    s = sk.parse(SKILL.format(name="abc"), "x/abc/SKILL.md")
    assert (s.name, s.title, s.commands) == ("abc", "A test", ["BLOCK", "ASSERT"])
    assert s.description.startswith("A test skill")
    with pytest.raises(sk.SkillError, match="front matter"):
        sk.parse("# no front matter")
    with pytest.raises(sk.SkillError, match="description"):
        sk.parse("---\nname: x\n---\nbody")


def test_check_finds_mistakes(tmp_path):
    sk.configure([str(tmp_path)], [])
    write_skill(tmp_path, "wrong-folder", SKILL.format(name="other-name"))
    write_skill(tmp_path, "bad-cmd", SKILL.format(name="bad-cmd").replace("BLOCK, ASSERT", "BLOCK, NOSUCH"))
    write_skill(tmp_path, "secret", SKILL.format(name="secret") + "\nkey ghp_" + "a" * 36 + "\n")
    write_skill(tmp_path, "bad-lint", SKILL.format(name="bad-lint").replace("BLOCK, 0", "BLOKK, 0"))
    write_skill(tmp_path, "fails", example="BLOCK, 0, 0, 0, 1, 1, 1\nASSERT, VOL(1), EQ, 5\n")
    # a history edit that leaves an earlier check failing is caught too
    write_skill(tmp_path, "edit-breaks", example="W = 1\nBLOCK, 0, 0, 0, W, 1, 1\nASSERT, VOL(1), EQ, 1\n"
                                                 'HIST, EDIT, 1, "W = 2"\n')
    write_skill(tmp_path, "unreadable", "no front matter")
    got = sk.check_all()
    assert any("differs from its folder" in p for p in got["other-name"])
    assert any("NOSUCH" in p for p in got["bad-cmd"])
    assert any("key or token" in p for p in got["secret"])
    assert any("BLOKK" in p for p in got["bad-lint"])
    assert any("ASSERT" in p for p in got["fails"])
    assert any("now fails" in p for p in got["edit-breaks"])
    assert any("front matter" in p for p in got["unreadable"])


def test_user_and_project_skills_override_and_switch_off(tmp_path):
    user = tmp_path / "user"
    proj = tmp_path / "proj"
    write_skill(user / "", "sheet-metal", SKILL.format(name="sheet-metal").replace("A test skill", "Ours"))
    write_skill(proj / "skills", "our-bracket")
    sk.configure([str(user)], [])
    found = sk.discover(str(proj))
    assert found["sheet-metal"].source == "user" and found["sheet-metal"].description.startswith("Ours")
    assert found["our-bracket"].source == "project"
    sk.configure(None, ["our-bracket"])
    assert "our-bracket" not in sk.discover(str(proj))
    assert "our-bracket" in sk.discover(str(proj), include_disabled=True)
    assert "our-bracket" not in sk.index_text(str(proj))


def test_env_folder(tmp_path, monkeypatch):
    write_skill(tmp_path, "from-env")
    monkeypatch.setenv("MODELER_SKILLS", str(tmp_path))
    assert sk.discover()["from-env"].source == "user"


def test_export_and_command_line(tmp_path, capsys):
    out = tmp_path / "agent-skills"
    written = sk.export(str(out), ["sheet-metal", "enclosure"])
    assert len(written) == 2
    text = (out / "sheet-metal" / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: sheet-metal") and "python -m modeler mcp" in text
    assert (out / "sheet-metal" / "example.cmd").is_file()
    with pytest.raises(sk.SkillError):
        sk.export(str(out), ["no-such-skill"])
    assert sk.main(["list"]) == 0
    assert "sheet-metal [built-in]" in capsys.readouterr().out
    assert sk.main(["show", "sheet-metal"]) == 0
    assert "FLANGE" in capsys.readouterr().out
    assert sk.main(["export", "--to", str(tmp_path / "all")]) == 0
    assert len(os.listdir(tmp_path / "all")) == len(sk.discover())
    assert sk.main(["nonsense"]) == 2


# ---- the assistant's tools and first prompt ---------------------------------------------
def test_tools_list_and_load_skills():
    box = Toolbox(Processor())
    rows = box.call("list_skills")["skills"]
    assert any(r["name"] == "enclosure" and "LIP" in r["commands"] for r in rows)
    got = box.call("load_skill", {"name": "Sheet metal"})
    assert got["name"] == "sheet-metal" and "FLANGE" in got["text"] and "UNFOLD" in got["example"]
    bad = box.call("load_skill", {"name": "nope"})
    assert "no skill" in bad["error"] and bad["hint"]


def test_first_prompt_carries_the_skill_index():
    from modeler.ai.copilot import first_prompt

    text = first_prompt("/tmp/x")
    assert "Skills (load_skill" in text
    assert "- sheet-metal: " in text and "- fixing-failed-steps: " in text


def test_mcp_prompts_and_resources():
    s = Server(Toolbox(Processor()), io.StringIO(), "test")

    def req(mid, method, params=None):
        return s.handle(json.dumps({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}))

    caps = req(1, "initialize", {"protocolVersion": "2025-06-18"})["result"]["capabilities"]
    assert "prompts" in caps and "resources" in caps
    prompts = req(2, "prompts/list")["result"]["prompts"]
    assert any(p["name"] == "sheet-metal" for p in prompts)
    got = req(3, "prompts/get", {"name": "sheet-metal", "arguments": {"request": "a 2 mm cover"}})["result"]
    text = got["messages"][0]["content"]["text"]
    assert "FLANGE" in text and "Example script" in text and "a 2 mm cover" in text
    assert req(4, "prompts/get", {"name": "nope"})["error"]["code"] == -32602
    res = req(5, "resources/list")["result"]["resources"]
    uris = {r["uri"] for r in res}
    assert {"skill://sheet-metal", "skill://sheet-metal/example.cmd"} <= uris
    md = req(6, "resources/read", {"uri": "skill://sheet-metal"})["result"]["contents"][0]
    assert md["mimeType"] == "text/markdown" and md["text"].startswith("---")
    ex = req(7, "resources/read", {"uri": "skill://sheet-metal/example.cmd"})["result"]["contents"][0]
    assert "SHEET" in ex["text"]
    assert "error" in req(8, "resources/read", {"uri": "file:///etc/passwd"})
    assert req(9, "resources/templates/list")["result"] == {"resourceTemplates": []}


# ---- search_docs, parameters, sketch_state ----------------------------------------------
def test_search_docs():
    got = kn.search_docs("sheet metal flange bend radius", 3)
    assert got["results"] and any(r["source"] in ("skill", "LANGUAGE.md") for r in got["results"])
    assert all(len(r["text"]) <= 1800 for r in got["results"])
    only = kn.search_docs("snap hook boss", 5, ["skill"])
    assert {r["source"] for r in only["results"]} == {"skill"}
    assert only["results"][0]["ref"] == "enclosure"
    with pytest.raises(ValueError):
        kn.search_docs("the of and")
    box = Toolbox(Processor())
    assert box.call("search_docs", {"query": "HIST EDIT", "sources": ["docs"]})["results"][0]["source"].endswith(".md")


SCRIPT = """! a plate
W = 80
T = 6
SKETCH, s1, XY
SRECT, 0, 0, W, 40
SDIM, LENGTH, 1, W
ENDSKETCH
EXTRUDE, s1, T
"""


def test_parameters_set_and_read():
    p = Processor()
    assert all(r.ok for r in p.run_script(SCRIPT))
    rows = {r["name"]: r for r in kn.parameters(p)["parameters"]}
    assert rows["W"]["set_by"] == [1] and rows["W"]["value"] == "80"
    assert rows["W"]["read_by"] == [4, 5]
    assert rows["T"]["read_by"] == [7]
    assert rows["W"]["edit"].startswith('HIST, EDIT, 1, "! a plate\\nW = 80')
    # the edit line given works as it is
    assert p.run(rows["W"]["edit"].replace("W = 80", "W = 90")).ok
    assert p.params["W"] == 90


def test_sketch_state():
    p = Processor()
    p.run_script(SCRIPT)
    st = kn.sketch_state(p, "s1")
    assert st["name"] == "s1" and not st["open"]
    assert len(st["geometry"]) == 4 and st["profiles"] and st["profiles"][0]["area"] == pytest.approx(3200)
    assert any(c["kind"] == "LENGTH" and c["value"] == 80 for c in st["constraints"])
    assert st["dof"] > 0 and any(g.get("free") for g in st["geometry"])
    every = kn.sketch_state(p)
    assert every["sketches"][0]["name"] == "s1"
    with pytest.raises(ValueError):
        kn.sketch_state(p, "nope")
    assert "error" in Toolbox(Processor()).call("sketch_state")


# ---- reports as data and the queries ----------------------------------------------------
BRACKET = """BLOCK, 0, 0, 0, 60, 40, 6
NAME, LAST, bracket
BLOCK, 0, 0, 0, 6, 40, 50
UNION, bracket, LAST
MATERIAL, bracket, ALUMINIUM
SEL, S, FACE, NORMAL, -1, 0, 0
CM, wall, FACE
SEL, S, FACE, NORMAL, 1, 0, 0
SEL, R, FACE, LOC, X, 60
CM, tip, FACE
SEL, NONE
"""


def test_reports_from_checks():
    p = Processor()
    assert all(r.ok for r in p.run_script(BRACKET))
    r = p.run("STRESS, bracket, wall, tip, FORCE, 0, 0, -400")
    assert r.ok and r.report["material"] == "aluminium"
    assert r.report["safety_factor"] > 1 and r.report["max_deflection_mm"] > 0
    assert p.reports["STRESS"] is r.report
    r = p.run("PRINTCHECK, bracket")
    assert r.report["ready"] in (True, False) and "overhang_area" in r.report
    r = p.run("MASSPROP, bracket")
    assert r.report["mass_kg"] == pytest.approx(r.report["volume"] * 2700e-9, rel=1e-6)
    r = p.run("GRAVITY")
    assert r.report["parts"][0]["state"] in ("sits", "held") and r.report["floating"] == []
    r = p.run("BOM")
    assert r.report["rows"][0]["name"] == "bracket" and r.report["pieces"] == 1
    r = p.run("STACKUP, +20.2 ±0.05, -20 ±0.05, MIN=0.05, MAX=0.4")
    assert r.report["worst"] == [pytest.approx(0.1), pytest.approx(0.3)] and r.report["worst_ok"]
    assert p.run("ECHO, 1").report is None  # a line without a report has none


def test_sandbox_rows_carry_reports():
    box = Toolbox(Processor())
    out = box.call("run", {"script": BRACKET + "MASSPROP, bracket\nBOM"})
    rows = [r for r in out["entries"] if r.get("report")]
    assert {tuple(sorted(r["report"]))[:1] for r in rows}
    assert any("mass_kg" in r["report"] for r in rows) and any("rows" in r["report"] for r in rows)


def test_analysis_queries_in_assert():
    p = Processor()
    script = BRACKET + """
ASSERT, MASS(bracket), BETWEEN, 0.06, 0.08
ASSERT, SAFETY(bracket, "wall", "tip", 0, 0, -400), GE, 2
ASSERT, MAXSTRESS(bracket, "wall", "tip", 0, 0, -400), LT, 200
ASSERT, DEFLECT(bracket, "wall", "tip", 0, 0, -400), LT, 1
ASSERT, OVERHANGS(bracket), EQ, 0, 1
ASSERT, FLOATING(), EQ, 0
ASSERT, TIPANGLE(), GT, 5
ASSERT, QTY("bracket"), EQ, 1
"""
    res = p.run_script(script)
    assert all(r.ok for r in res), [r.message for r in res if not r.ok]
    # the queries leave no colours or reports of their own behind
    assert "STRESS" not in p.reports and getattr(p, "analysis", None) is None
    bad = p.run('ECHO, SAFETY(bracket, "nope", "tip", 0, 0, -400)')
    assert not bad.ok
    p2 = Processor()
    p2.run("BLOCK, 0, 0, 0, 1, 1, 1")
    assert "no material" in p2.run("ECHO, MASS(1)").message
