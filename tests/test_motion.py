"""Assemblies that move: DRIVE and MOTION (commands/motion_handlers.py), picture sequences."""

from __future__ import annotations

import pytest

from modeler.commands import Processor
from modeler.commands.queries import bbox
from modeler.render import motion_shots

LID = ["A = 0", "BLOCK, 0, 0, 0, 40, 30, 5", "BLOCK, 0, 0, 5, 40, 30, 2", "NAME, LAST, lid",
       "ROTATE, lid, -A, 0, 0, 5, 0, 1, 0", "CYL, -20, 15, 0, 3, 30"]


def lid():
    p = Processor()
    for line in LID:
        assert p.run(line).ok, line
    return p


def test_drive_moves_without_touching_the_history():
    p = lid()
    n, text = len(p.history), [e.text for e in p.history]
    r = p.run("DRIVE, A, 90")
    assert r.ok and "unchanged, reused" in r.message  # only the steps that read A ran
    assert bbox(p.model.body(2).shape)[2] == pytest.approx(5)  # stood up: x from -2 to 0, z 5 to 45
    assert bbox(p.model.body(2).shape)[5] == pytest.approx(45)
    assert [e.text for e in p.history] == text and len(p.history) == n
    assert p.params["A"] == 90 and "A = 90" in p.run("DRIVE").message
    r = p.run("DRIVE, A")
    assert r.ok and p.params["A"] == 0 and not p.drive
    assert bbox(p.model.body(2).shape)[5] == pytest.approx(7)


def test_drive_wants_a_parameter_the_history_sets():
    p = lid()
    r = p.run("DRIVE, B, 3")
    assert not r.ok and "not set by the history" in r.message


def test_undo_after_drive_keeps_the_driven_value_out_of_history():
    p = lid()
    assert p.run("DRIVE, A, 45").ok
    assert p.run("BLOCK, 100, 0, 0, 1, 1, 1").ok
    assert p.run("UNDO").ok
    assert p.params["A"] == 45  # still driven: undo is about history steps


def test_motion_finds_where_the_lid_hits_the_post():
    p = lid()
    r = p.run("MOTION, A, 0, 180, 12")
    assert r.ok
    assert "bodies 2 and 3 run into each other from A = 135 to 180" in r.message
    first = float(r.message.split("first meet at A = ")[1].split(")")[0])
    assert first == pytest.approx(120.4, abs=0.1)  # the lid's top face reaches the post's top edge
    assert p.params["A"] == 0 and not p.drive  # put back
    assert bbox(p.model.body(2).shape)[5] == pytest.approx(7)


def test_motion_clear_range_reports_the_smallest_gap():
    p = lid()
    r = p.run("MOTION, A, 0, 90, 3")
    assert "no parts run into each other" in r.message
    r = p.run("MOTION, A, 100, 120, 2")  # close by: the gap is measured
    assert "smallest gap is" in r.message and "at A = 120" in r.message


def test_motion_shots_fit_once_and_let_go():
    shots = motion_shots("A", 0, 90, 3)
    assert [s.file for s in shots] == ["a_000.png", "a_001.png", "a_002.png", "a_003.png", ""]
    assert shots[0].prefit and len(shots[0].prefit) == 4
    assert not any(s.fit for s in shots)
    assert shots[-1].commands == ["DRIVE, A"]
