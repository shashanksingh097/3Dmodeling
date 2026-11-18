"""The assistant's benchmark: every task's checks pass with its reference script and fail without
it, and the scoring follows what was proposed (no network)."""

import asyncio

import pytest

from modeler.ai import bench


def _reply(proposals=(), text="", tools=(), error=""):
    from modeler.ai.copilot import Proposal, Reply

    return Reply(text=text, tools=list(tools), proposals=[Proposal(s, "") for s in proposals], error=error,
                 turns=2, input_tokens=1000, output_tokens=100)


@pytest.mark.parametrize("task", [t for t in bench.TASKS if not t.refuse], ids=lambda t: t.name)
def test_reference_passes(task):
    async def ask(t, p):
        return _reply([task.reference], "done", ["sandbox", "run", "propose_commands"])

    r = asyncio.run(bench.run_task(task, ask))
    assert r.passed, (r.note, [c for c in r.checks if not c.get("pass")])
    assert r.turns == 2 and r.tool_calls == 3 and r.pictures == 0


@pytest.mark.parametrize("task", [t for t in bench.TASKS if not t.refuse], ids=lambda t: t.name)
def test_nothing_fails(task):
    async def ask(t, p):
        return _reply([], "I could not do it")

    assert not asyncio.run(bench.run_task(task, ask)).passed


def test_impossible_task():
    task = next(t for t in bench.TASKS if t.refuse)

    async def says(t, p):
        return _reply([], "A 30 mm radius is too large for a 10 mm thick plate; at most just under 5 mm works.")

    async def tries(t, p):
        return _reply(["SEL, S, BODY, ID, plate\nFILLET, 30"], "Done")

    async def silent(t, p):
        return _reply([], "Okay.")

    assert asyncio.run(bench.run_task(task, says)).passed
    assert not asyncio.run(bench.run_task(task, tries)).passed
    assert not asyncio.run(bench.run_task(task, silent)).passed


def test_a_failing_proposal_and_errors_are_reported():
    task = bench.TASKS[0]

    async def bad(t, p):
        return _reply(["CYL, 0,0,0, -5, 12"])

    r = asyncio.run(bench.run_task(task, bad))
    assert not r.passed and r.note.startswith("the proposal failed")

    async def err(t, p):
        return _reply(error="quota exhausted")

    assert asyncio.run(bench.run_task(task, err)).note == "error: quota exhausted"


def test_run_summary_and_save(tmp_path):
    async def ask(t, p):
        return _reply([t.reference] if t.reference else [], "it is too large", ["render"] if t.name == "spring"
                      else [])

    lines = []
    results = asyncio.run(bench.run(ask, only=["flange", "spring", "impossible_fillet"], log=lines.append))
    s = bench.summary(results)
    assert s["tasks"] == 3 and s["passed"] == 3 and s["without_pictures"] == 2 and s["goal_met"]
    assert any("PASS" in x for x in lines)
    bench.save(results, str(tmp_path / "r.json"), {"model": "test"})
    import json
    data = json.loads((tmp_path / "r.json").read_text())
    assert data["summary"]["pictures"] == 1 and data["about"]["model"] == "test"
