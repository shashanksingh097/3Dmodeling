"""Exploded views: XSTEP records the steps, XSHOW shows them and puts the parts back."""

import pytest

from modeler.commands import Processor
from modeler.commands.xview_handlers import _centre, offsets, trail_points


def run(p, *lines):
    for line in lines:
        r = p.run(line)
        assert r.ok, (line, r.message)
    return r


def build():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 40,30,5", "NAME, LAST, base", "BLOCK, 0,0,5, 40,30,2", "NAME, LAST, lid",
        "CYL, 5,5,0, 1.5, 12", "NAME, LAST, pin",
        "XSTEP, apart, lid, 0,0,20", "XSTEP, apart, \"pin lid\", 0,0,40", "XSTEP, apart, pin, -15,0,0")
    return p


def test_offsets_sum_the_steps():
    steps = [((2,), (0, 0, 20)), ((3, 2), (0, 0, 40)), ((3,), (-15, 0, 0))]
    assert offsets(steps) == {2: (0, 0, 60), 3: (-15, 0, 40)}
    assert offsets(steps, 0.5)[3] == (-7.5, 0, 20)
    assert trail_points(steps, (0, 0, 0), 3, 1) == [(0, 0, 0), (0, 0, 40), (-15, 0, 40)]


def test_xstep_changes_nothing_and_is_history():
    p = build()
    assert _centre(p.model.body(2).shape) == pytest.approx((20, 15, 6))
    assert len(p.model.xviews["APART"]) == 3
    assert any("XSTEP" in e.text for e in p.history)


def test_xshow_moves_and_puts_back():
    p = build()
    r = run(p, "XSHOW, apart")
    assert "2 bodies moved, 2 trails" in r.message
    assert _centre(p.model.body(2).shape) == pytest.approx((20, 15, 66))
    assert _centre(p.model.body(3).shape) == pytest.approx((-10, 5, 46))
    names = {b.name for b in p.model.bodies.values()}
    assert {"trail_2", "trail_3"} <= names
    n = len(p.history)
    run(p, "FIT")  # viewing keeps it shown
    assert p.exploded is not None
    run(p, "XSHOW, apart, 0.5")
    assert _centre(p.model.body(2).shape) == pytest.approx((20, 15, 36))
    run(p, "XSHOW")
    assert _centre(p.model.body(2).shape) == pytest.approx((20, 15, 6))
    assert sorted(p.model.bodies) == [1, 2, 3] and len(p.history) == n


def test_next_command_puts_parts_back_first():
    p = build()
    run(p, "XSHOW, apart", "MOVE, lid, 1, 0, 0")
    assert p.exploded is None
    assert _centre(p.model.body(2).shape) == pytest.approx((21, 15, 6))
    assert sorted(p.model.bodies) == [1, 2, 3]
    run(p, "XSHOW, apart", "UNDO")
    assert _centre(p.model.body(2).shape) == pytest.approx((20, 15, 6))


def test_views_survive_a_rebuild_and_save(tmp_path):
    p = build()
    f = tmp_path / "a.m3d"
    run(p, "XSHOW, apart", f'SAVE, "{f}"')
    q = Processor()
    run(q, f'OPEN, "{f}"')
    assert len(q.model.xviews["APART"]) == 3
    assert sorted(q.model.bodies) == [1, 2, 3]
    run(q, "XSHOW, apart")


def test_errors():
    p = build()
    assert not p.run("XSHOW, nope").ok
    assert not p.run("XSTEP, apart, lid, 0, 0, 0").ok
    assert not p.run("XSTEP, apart, nobody, 0, 0, 1").ok
    assert "APART" in run(p, "XSHOW, LIST").message
    run(p, "XSTEP, apart, CLEAR")
    assert "APART" not in p.model.xviews
