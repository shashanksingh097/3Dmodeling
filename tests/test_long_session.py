"""A long session (PLAN item 63): hours of modelling squeezed into a minute. Building, undoing
and redoing, editing early steps, saving, opening and drawing, over and over in one process,
must not leak memory, grow the undo list without end or slow down."""

import gc
import time

from modeler.commands import Processor
from modeler.perf import plate_script, rss_mb


def ok(p, text):
    for r in p.run_script(text):
        assert r.ok, f"{r.line}: {r.message}"


def test_a_long_session_holds_steady(tmp_path):
    p = Processor()
    path = str(tmp_path / "long.m3d")
    svg = str(tmp_path / "long.svg")
    marks, times = [], []
    for cycle in range(10):
        t0 = time.perf_counter()
        ok(p, "NEW")
        ok(p, plate_script(3))
        for i in range(8):
            ok(p, f"SPHERE, {6 + i * 5}, 6, 10, 2\nUNION, plate, LAST")
            ok(p, "UNDO")
            ok(p, "REDO")
        ok(p, f'HIST, EDIT, 1, "N = {3 + cycle % 2}"')
        ok(p, f'SAVE, "{path}"\nNEW')
        ok(p, f'OPEN, "{path}"')
        ok(p, f'DRAWING, "{svg}", STANDARD')
        gc.collect()
        marks.append(rss_mb())
        times.append(time.perf_counter() - t0)
        assert len(p._undo) <= 40 and len(p.history) <= 40
    # after the first cycles have loaded everything, memory stays flat ...
    assert max(marks[3:]) - marks[2] < 60, [round(m) for m in marks]
    # ... and the last cycles are not slower than the early ones
    assert sum(times[-3:]) < 2.5 * sum(times[1:4]) + 1, [round(t, 2) for t in times]


def test_a_long_history_grows_its_memory_slowly():
    """400 steps, with an undo and redo every third: each step adds a little, and no step
    keeps a second copy of the whole state."""
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 400, 40, 10")
    gc.collect()
    start = rss_mb()
    t0 = time.perf_counter()
    for i in range(400):
        ok(p, f"SPHERE, {i}, 20, 10, 0.4")
        if i % 3 == 0:
            ok(p, "UNDO\nREDO")
    took = time.perf_counter() - t0
    gc.collect()
    grew = rss_mb() - start
    assert len(p.history) == 401
    assert all(e.before is p._snaps[i] for i, e in enumerate(p.history))
    assert grew < 150, f"{grew:.0f} MB for 400 steps"
    assert took < 30, f"{took:.1f} s for 400 steps"
