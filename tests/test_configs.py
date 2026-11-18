"""Configurations (CONFIG, USECONFIG), the parts list (BOM), and parameter/body name clashes."""

import csv
import subprocess
import sys

import pytest

from modeler.commands import Processor

PLATE = """W = 40
H = 10
BLOCK, 0,0,0, W, 30, H
NAME, LAST, plate
MATERIAL, plate, ALUMINIUM
CONFIG, big, "W = 80, H = 20"
CONFIG, small, "W = 20"
"""


def _plate():
    p = Processor()
    for r in p.run_script(PLATE):
        assert r.ok, r.message
    return p


def vol(p):
    return p.evaluate("VOL(plate)")


def test_switching_configurations_rebuilds_with_their_values():
    p = _plate()
    assert vol(p) == pytest.approx(12000)
    n = len(p.history)
    assert p.run("USECONFIG, big").ok
    assert vol(p) == pytest.approx(80 * 30 * 20)
    assert p.params["W"] == 80
    assert len(p.history) == n  # not a history step
    assert p.run("USECONFIG, small").ok
    assert vol(p) == pytest.approx(20 * 30 * 10)  # H back to the history's own value
    assert p.run("USECONFIG, DEFAULT").ok
    assert vol(p) == pytest.approx(12000)
    res = p.run("USECONFIG")
    assert "BIG: W = 80, H = 20" in res.message


def test_bad_configurations_are_refused():
    p = _plate()
    assert not p.run("USECONFIG, huge").ok
    assert not p.run('CONFIG, default, "W = 1"').ok
    assert not p.run('CONFIG, odd, "W 5"').ok
    assert not p.run("CONFIG, empty").ok
    assert vol(p) == pytest.approx(12000)


def test_undo_takes_back_a_config_definition():
    p = _plate()
    assert p.run('CONFIG, tall, "H = 50"').ok
    assert "TALL" in p.configs
    assert p.run("UNDO").ok
    assert "TALL" not in p.configs


def test_the_configuration_in_use_is_saved_with_the_project(tmp_path):
    p = _plate()
    assert p.run("USECONFIG, big").ok
    path = tmp_path / "plate.m3d"
    assert p.run(f'SAVE, "{path}"').ok
    q = Processor()
    assert q.run(f'OPEN, "{path}"').ok
    assert q.config == "BIG"
    assert vol(q) == pytest.approx(80 * 30 * 20)


def test_batch_runner_takes_a_configuration(tmp_path):
    script = tmp_path / "plate.cmd"
    script.write_text(PLATE + "ECHO, VOL(plate)\n", encoding="utf-8")
    out = subprocess.run([sys.executable, "-m", "modeler", "run", str(script), "-C", "big"],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "using BIG" in out.stdout


def test_bom_counts_instances_and_named_bodies(tmp_path):
    p = Processor()
    script = """*PART, peg, D = 4, L = 10
CYL, 0,0,0, D/2, L
*ENDPART
INST, peg, 0,0,0
INST, peg, 10,0,0
INST, peg, 20,0,0, L = 20
BLOCK, 0,0,-5, 30, 10, 5
NAME, LAST, base
MATERIAL, base, STEEL
"""
    for r in p.run_script(script):
        assert r.ok, r.message
    res = p.run(f'BOM, "{tmp_path / "parts.csv"}"')
    assert res.ok, res.message
    assert "3 kinds, 4 pieces" in res.message
    rows = list(csv.DictReader(open(tmp_path / "parts.csv", encoding="utf-8")))
    qty = {(r["part"], r["parameters"]): int(r["qty"]) for r in rows}
    assert qty[("PEG", "D = 4, L = 10")] == 2
    assert qty[("PEG", "D = 4, L = 20")] == 1
    base = next(r for r in rows if r["part"] == "base")
    assert float(base["mass (kg)"]) == pytest.approx(7850 * 1500e-9, rel=1e-3)
    assert len(p.history) == len([ln for ln in script.splitlines() if ln and not ln.startswith(("CYL", "*END"))])


def test_parameter_and_body_names_cannot_clash():
    p = Processor()
    assert p.run("W = 10").ok
    assert p.run("BLOCK, 0,0,0, W, 5, 5").ok
    res = p.run("NAME, LAST, W")
    assert not res.ok and "is a parameter" in res.message
    assert p.run("NAME, LAST, plate").ok
    res = p.run("plate = 3")
    assert not res.ok and "name of a body" in res.message
    assert p.run("W = 12").ok  # changing a parameter that already exists is fine
