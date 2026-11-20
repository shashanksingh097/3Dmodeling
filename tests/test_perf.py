"""Speed (PLAN item 63): the benchmark runs and stays within its budgets, and the two speedups
it led to keep giving the same answers."""

import json

import pytest

from modeler import perf
from modeler.commands import Processor
from modeler.core.model import Model


def test_the_quick_benchmark_is_within_its_budgets():
    result = perf.run(quick=True, out=lambda *_: None)
    assert set(result["cases"]) == {"build plate", "import STEP", "pick faces", "drawing", "save", "open",
                                    "long history", "rebuild after edit"}
    assert all(r["memory_mb"] > 0 for r in result["cases"].values())
    with open(perf.BUDGETS, encoding="utf-8") as f:
        budgets = json.load(f)
    assert perf.check(result, budgets) == []
    assert set(budgets["full"]) == set(budgets["quick"]) == set(result["cases"])


def test_a_slow_case_is_reported():
    result = {"quick": True, "cases": {"open": {"seconds": 9.0, "memory_mb": 400.0}}}
    assert perf.check(result, {"quick": {"open": {"seconds": 2, "memory_mb": 300}}}) == [
        "open: 9.00 s, over its budget of 2 s", "open: 400 MB held, over its budget of 300 MB"]


def test_the_command_line(tmp_path, capsys):
    from modeler.__main__ import main

    out = tmp_path / "perf.json"
    assert main(["perf", "--quick", "--check", "--json", str(out)]) == 0
    assert "all cases within their budgets" in capsys.readouterr().out
    assert json.loads(out.read_text())["cases"]["open"]["seconds"] >= 0


def test_each_step_shares_the_state_before_it():
    """A long history keeps one copy of each state: what a step started from is the snapshot
    taken after the step before (it used to be a second copy)."""
    p = Processor()
    p.run_script("BLOCK, 0,0,0, 100, 10, 10\n" + "\n".join(f"SPHERE, {i * 3}, 5, 10, 1" for i in range(30)))
    assert all(e.before is p._snaps[i] for i, e in enumerate(p.history))
    p.run('HIST, EDIT, 1, "BLOCK, 0,0,0, 120, 10, 10"')  # and after a rebuild too
    assert all(e.before is p._snaps[i] for i, e in enumerate(p.history))
    # a change made between steps outside the history (the view picks a body): then the step
    # keeps its own copy of where it started
    p.model.selection_kind, p.model.selection = "BODY", [1]
    p.run("SPHERE, 0, 0, 30, 1")
    assert p.history[-1].before is not p._snaps[-2] and p.history[-1].before["model"]["selection"] == [1]


@pytest.mark.parametrize("script", [
    perf.plate_script(4),
    perf.history_script(12),
    "BLOCK, 0,0,0, 40,40,20\nNAME, LAST, a\nSPHERE, 20,20,20, 12\nUNION, a, LAST\nBLOCK, 5,5,-5, 10,10,30\n"
    "SUBTRACT, a, LAST\nBLOCK, -10,-10,-10, 45, 35, 40\nINTERSECT, a, LAST",
])
def test_skipping_untouched_entities_finds_the_same_parents(script, monkeypatch):
    """Booleans no longer ask the kernel what each untouched face, edge and vertex made
    (nothing: it would have been split). The parents found are the same as before."""
    got = []
    for skip in (False, True):
        monkeypatch.setattr(Model, "SKIP_UNTOUCHED", skip)
        p = Processor()
        res = p.run_script(script)
        assert all(r.ok for r in res), [r.message for r in res if not r.ok]
        got.append({k: dict(v) for k, v in p.model._parent.items()})
    assert got[0] == got[1] and any(got[0].values())
