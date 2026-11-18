"""Sending a processor's whole state to another process and back (core/transfer.py),
and the rebuild helper process (core/helper.py) without a window."""

import pytest

from modeler.commands import Processor
from modeler.core import helper as hp
from modeler.core import transfer as tr

FLANGE = """W = 40
BLOCK, 0,0,0, W, 30, 10
CYL, 20, 15, 0, 6, 10
SUBTRACT, 1, 2
"""


def _flange():
    p = Processor()
    for r in p.run_script(FLANGE):
        assert r.ok, r.message
    return p


def _vol(p):
    return p.evaluate("VOL(LAST)")


def test_state_round_trip_keeps_model_history_and_undo():
    p = _flange()
    q = Processor()
    tr.set_processor_state(q, tr.loads(tr.dumps(tr.processor_state(p))))
    assert len(q.history) == len(p.history)
    assert _vol(q) == pytest.approx(_vol(p))
    for proc in (p, q):
        assert proc.run('HIST, EDIT, 1, "W = 60"').ok
    assert _vol(q) == pytest.approx(_vol(p))
    for proc in (p, q):
        assert proc.run("UNDO").ok
    assert _vol(q) == pytest.approx(_vol(p))


def test_entries_remember_how_long_they_took():
    p = _flange()
    assert all(e.seconds >= 0 for e in p.history)
    assert sum(e.seconds for e in p.history) > 0


def test_helper_rebuilds_in_another_process_and_cancel_leaves_nothing():
    p = _flange()
    before = _vol(p)
    h = hp.Helper()
    try:
        h.submit(tr.processor_state(p), 'HIST, EDIT, 1, "W = 60"')
        steps = 0
        while True:
            m = h.wait(120)
            if m[0] != "progress":
                break
            steps += 1
        assert m[0] == "done", m
        ok, _line, msg, _warn, state = m[1:]
        assert ok, msg
        assert steps >= len(p.history) - 1
        assert _vol(p) == pytest.approx(before)  # nothing here changed yet
        tr.set_processor_state(p, state)
        assert _vol(p) > before
        h.cancel()
        assert not h.alive()
        h.submit(tr.processor_state(p), "HIST, REPLAY")  # starts a fresh helper
        assert h.wait(120)[0] in ("progress", "done")
    finally:
        h.close()
