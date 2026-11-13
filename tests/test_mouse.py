"""The M5 exit test: a computer mouse shell from curves, G2 blends, shelled to
2 mm, with a text flowed along a curve (scripts/mouse.cmd); and BLEND between
two closed loops, which the mouse needs."""

import pytest

from modeler.commands import Processor


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs


def test_mouse_exit_test():
    p = Processor()
    with open("scripts/mouse.cmd") as f:
        rs = ok(p, f.read())
    zebra = next(r.message for r in rs if r.message.startswith("ANALYZE"))
    # the blend meets the side wall and the top without a jump in curvature; only the foot is sharp
    assert "2 smooth in curvature (G2)" in zebra and "0 tangent only" in zebra and "1 creased" in zebra
    assert p.evaluate("VALID(mouse)") == 1 and p.evaluate("PIECES(mouse)") == 1
    assert p.evaluate("T_SHELL") == pytest.approx(2.0, abs=0.01)  # measured right after SHELL
    assert p.evaluate("BBOX(mouse).dx") == pytest.approx(110, abs=0.5)
    assert p.evaluate("BBOX(mouse).zmin") == pytest.approx(0, abs=1e-3)
    # the shell is open at the bottom: much less than the solid it was made from
    assert 20000 < p.evaluate("VOL(mouse)") < 60000
    assert sorted(b.name for b in p.model.bodies.values()) == ["mouse", "wheel"]


def _loops(p, start_angle, reverse):
    """An open tube (its top a closed loop at z = 10) and a disc above it, smaller (its rim at
    z = 16); the disc's circle starts at start_angle and may run the other way round."""
    d = "0, 0, -1" if reverse else "0, 0, 1"
    ok(p, f"""CIRCLE, 0, 0, 0, 20
CIRCLE, 0, 0, 10, 20
LOFT, LAST - 1, LAST, SURFACE
NAME, LAST, tube
CIRCLE, 0, 0, 16, 12, {d}, {start_angle}
NAME, LAST, ring
FILL, G0, ring
NAME, LAST, lid""")


@pytest.mark.parametrize("start_angle, reverse", [(0, False), (130, False), (75, True)])
def test_blend_between_two_loops_closes(start_angle, reverse):
    p = Processor()
    _loops(p, start_angle, reverse)
    ok(p, """SEL, S, EDGE, BODY, tube
SEL, R, EDGE, BOX, -21, -21, 9.9, 21, 21, 10.1
E1 = SELID(1)
SEL, S, EDGE, BODY, lid
E2 = SELID(1)
SEL, NONE""")
    rs = ok(p, "BLEND, G2, E1, E2")
    assert "meets within" in rs[-1].message
    # the blend's seam closes and it meets both loops, so only the tube's open bottom is left free
    rs = ok(p, "SEW, tube, LAST, lid")
    assert "1 free edge" in rs[-1].message, rs[-1].message
    assert p.evaluate("NFACES(LAST)") == 3
