"""The regression corpus: hard cases and the example scripts, checked in CI.

* ``tests/corpus/hard/*.cmd``: shapes the kernel gets wrong without
  complaint (a pipe too fat for its bend, a loft through itself ...). The
  second line says what must happen: ``! expect: refused "words"`` (the last
  command fails with a message containing the words) or ``! expect: ok
  [volume=V]`` (it works, the result is a valid closed solid, and its volume
  is V within 0.5%).
* ``scripts/*.cmd``: every example must run without errors, every body in it
  must pass CHECK, and its bodies, faces and volume must match
  ``tests/corpus/scripts.json``, so a kernel upgrade cannot change a model
  unnoticed. After a deliberate change, update the numbers with
  ``python tests/test_corpus.py --update`` and look at the diff.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HARD = sorted((ROOT / "tests" / "corpus" / "hard").glob("*.cmd"))
SCRIPTS = sorted((ROOT / "scripts").glob("*.cmd"))
NUMBERS = ROOT / "tests" / "corpus" / "scripts.json"


def _processor():
    from modeler.commands import Processor

    return Processor()


@pytest.mark.parametrize("path", HARD, ids=[p.stem for p in HARD])
def test_hard_case(path):
    from modeler.geometry import robust

    text = path.read_text()
    m = re.search(r"^! expect: (refused \"(.*)\"|ok(?: volume=([\d.]+))?)\s*$", text, re.M)
    assert m, f"{path.name}: no '! expect:' line"
    p = _processor()
    results = p.run_script(text)
    last = results[-1]
    assert all(r.ok for r in results[:-1]), [r.message for r in results if not r.ok]
    if m.group(2) is not None:
        assert not last.ok, f"{path.name}: should be refused, but made: {last.message}"
        assert m.group(2) in last.message, f"{path.name}: message was: {last.message}"
        return
    assert last.ok, f"{path.name}: {last.message}"
    rep = robust.report(p.model.bodies[p.model.last_body].shape)
    assert rep["ok"] and rep["solids"] == 1, rep
    if m.group(3):
        assert rep["volume"] == pytest.approx(float(m.group(3)), rel=5e-3)


def measure(path: Path) -> dict:
    from modeler.geometry import robust

    p = _processor()
    results = p.run_script(path.read_text())
    errors = [f"{r.line.splitlines()[0]}: {r.message}" for r in results if not r.ok]
    bodies = list(p.model.bodies.values())
    bad = [b.id for b in bodies if b.entity_ids["FACE"] and not robust.report(b.shape)["ok"]]
    solids = [b for b in bodies if robust.solids(b.shape)]
    return {
        "errors": errors,
        "bad_bodies": bad,
        "bodies": len(bodies),
        "faces": sum(len(b.entity_ids["FACE"]) for b in bodies),
        "volume": round(sum(robust.volume(b.shape) for b in solids), 3),
    }


@pytest.mark.parametrize("path", SCRIPTS, ids=[p.stem for p in SCRIPTS])
def test_example_script(path):
    got = measure(path)
    assert got["errors"] == [], got["errors"]
    assert got["bad_bodies"] == [], f"bodies that fail CHECK: {got['bad_bodies']}"
    want = json.loads(NUMBERS.read_text()).get(path.name)
    assert want is not None, f"{path.name} is not in {NUMBERS.name}: run python tests/test_corpus.py --update"
    assert got["bodies"] == want["bodies"]
    assert got["faces"] == want["faces"]
    assert got["volume"] == pytest.approx(want["volume"], rel=1e-4, abs=1e-3)


if __name__ == "__main__" and "--update" in sys.argv:
    sys.path.insert(0, str(ROOT))
    table = {}
    for path in SCRIPTS:
        got = measure(path)
        if got["errors"] or got["bad_bodies"]:
            raise SystemExit(f"{path.name}: {got['errors'] or got['bad_bodies']}")
        table[path.name] = {k: got[k] for k in ("bodies", "faces", "volume")}
        print(path.name, table[path.name])
    NUMBERS.write_text(json.dumps(table, indent=1, sort_keys=True) + "\n")
