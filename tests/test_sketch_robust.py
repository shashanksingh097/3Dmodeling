"""Sketcher robustness (PLAN item 52): tangent and many-crossing trims, offsets that cut away their
own loops, constraints kept through a turn, SCHECK, and a big sketch through edit cycles."""

import json
import time

import pytest

from modeler.commands import Processor


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    res = p.run_script(text)
    bad = [r for r in res if not r.ok]
    assert not bad, f"{bad[0].line}: {bad[0].message}"
    return res[-1]


def vol(p):
    return p.evaluate(f"VOL({max(p.model.bodies)})")


# ---- trims at tangent and near-tangent touches ---------------------------------------------------

@pytest.mark.parametrize("gap", [0.0, 1e-7, -1e-7])
def test_trim_at_a_tangent_touch(p, gap):
    r = ok(p, f"SKETCH, s, XY\nSCIRCLE, 0, 0, 10\nSLINE, -20, {10 + gap}, 20, {10 + gap}\nSTRIM, 2, -15, 10")
    assert "trimmed line 2 back to 1" in r.message
    sk = p.model.sketches["S"]
    a, b = sk.pt(sk.geos[2].pts["S"]), sk.pt(sk.geos[2].pts["E"])
    assert min(a[0], b[0]) == pytest.approx(0, abs=1e-5) and max(a[0], b[0]) == pytest.approx(20)


def test_a_line_that_misses_a_circle_is_not_cut(p):
    r = ok(p, "SKETCH, s, XY\nSCIRCLE, 0, 0, 10\nSLINE, -20, 10.01, 20, 10.01\nSTRIM, 2, -15, 10")
    assert "nothing crosses it" in r.message


def test_trim_at_circles_touching(p):
    r = ok(p, "SKETCH, s, XY\nSCIRCLE, 0, 0, 10\nSARC, 20.0000001, 0, 10, 90, 270\nSTRIM, 2, 20, 9.5")
    assert "trimmed arc 2 back to 1" in r.message


def test_trims_between_many_crossings(p):
    circles = "".join(f"SCIRCLE, {10 + 15 * i}, 0, 5\n" for i in range(6))
    r = ok(p, "SKETCH, s, XY\nSLINE, 0, 0, 100, 0\n" + circles + "STRIM, 1, 32, 0")
    assert "cut line 1 between 3 and 4: 1 and 8 are left" in r.message
    ok(p, "STRIM, 8, 47.5, 0")
    sk = p.model.sketches["S"]
    lines = [g for g in sk.geos.values() if g.kind == "LINE"]
    spans = sorted(tuple(sorted((sk.pt(g.pts["S"])[0], sk.pt(g.pts["E"])[0]))) for g in lines)
    # the pieces between the second and third circles, and inside the third's right side, are gone
    assert spans == [pytest.approx((0, 30)), pytest.approx((35, 45)), pytest.approx((50, 100))]


# ---- offsets that would cross themselves ------------------------------------------------------

U_SHAPE = ("SKETCH, s, XY\nSPOLY, 0,0, 100,0, 100,60, 55,60, 55,10, 45,10, 45,60, 0,60, 0,0\n"
           + "".join(f"SCONSTRUCT, {i}\n" for i in range(1, 9)))


def test_small_offset_stays_linked(p):
    r = ok(p, U_SHAPE + "SOFFSET, -3, 1, 2, 3, 4, 5, 6, 7, 8")
    assert "not linked" not in r.message


def test_inward_offset_that_splits_the_outline(p):
    r = ok(p, U_SHAPE + "SOFFSET, -8, 1, 2, 3, 4, 5, 6, 7, 8\nENDSKETCH\nEXTRUDE, s, 1")
    assert "2 profiles" in r.message
    # two prongs, each 8 in from every side (plus a little round the slot's corners)
    assert 2 * 29 * 44 < vol(p) < 2 * 29 * 44 * 1.001
    assert "loops were cut away" in p.history[-3].message


def test_outward_offset_that_closes_a_slot(p):
    ok(p, U_SHAPE + "SOFFSET, 30, 1, 2, 3, 4, 5, 6, 7, 8\nENDSKETCH\nEXTRUDE, s, 1")
    # the slot (10 wide) is closed; the outline is the rectangle grown by 30 with round corners
    full = 160 * 120 - (4 - 3.141592653589793) * 30 ** 2
    assert vol(p) == pytest.approx(full, rel=2e-3)


def test_offset_that_leaves_nothing_says_so(p):
    res = p.run_script(U_SHAPE + "SOFFSET, -40, 1, 2, 3, 4, 5, 6, 7, 8")
    assert not res[-1].ok and "closes up completely" in res[-1].message


# ---- constraints through a turn ------------------------------------------------------------------

@pytest.mark.parametrize("copy", ["", ", COPY"])
def test_turned_rectangle_stays_a_rectangle(p, copy):
    ok(p, "SKETCH, s, XY\nSRECT, 0, 0, 40, 20\nSDIM, LENGTH, 1, 40\nSDIM, LENGTH, 2, 20")
    before = p.model.sketches["S"].dof
    ok(p, f"STRANSFORM, ROTATE, 30, O, 1, 2, 3, 4{copy}")
    sk = p.model.sketches["S"]
    assert sk.dof == (2 * before if copy else before)  # nothing came loose
    first = 5 if copy else 1
    kinds = sorted(c.kind for c in sk.cons.values()
                   if c.kind != "COINCIDENT" and all(r.split(".")[0] in {str(first + i) for i in range(4)}
                                                      for r in c.refs))
    assert kinds == ["ANGLE", "LENGTH", "LENGTH", "PARALLEL", "PERPENDICULAR", "PERPENDICULAR"]
    # change a size: it is still a rectangle, turned 30 degrees
    n = next(c.n for c in sk.cons.values() if c.kind == "LENGTH" and c.refs == (str(first),))
    sk2 = sk.copy()
    sk2.set_value(n, 50)
    sk2.solve()
    g1, g2 = sk2.geos[first], sk2.geos[first + 1]
    d1 = [b - a for a, b in zip(sk2.pt(g1.pts["S"]), sk2.pt(g1.pts["E"]))]
    d2 = [b - a for a, b in zip(sk2.pt(g2.pts["S"]), sk2.pt(g2.pts["E"]))]
    assert d1[0] * d2[0] + d1[1] * d2[1] == pytest.approx(0, abs=1e-6)
    assert (d1[0] ** 2 + d1[1] ** 2) ** 0.5 == pytest.approx(50)
    assert abs(d1[1] / d1[0]) == pytest.approx(0.5773502691896257)  # tan 30


# ---- SCHECK -----------------------------------------------------------------------------------

def test_scheck_names_repeats_duplicates_and_loose_geometry(p):
    ok(p, "SKETCH, s, XY\nSRECT, 0, 0, 40, 20\nSDIM, LENGTH, 1, 40\nSDIM, LENGTH, 3, 40\n"
          "SCIRCLE, 20, 10, 5\nSLINE, 50, 0, 60, 0\nSLINE, 50, 0, 60, 0")
    msg = p.run("SCHECK").message
    assert "C10 (length 3) only repeats C9" in msg
    assert "line 7 is drawn twice (the same as 6)" in msg
    assert "circle 5: not held in place (all of it can move); radius is free" in msg
    res = json.loads(p.run("SCHECK, s, JSON").message)
    assert res["repeats"][0]["con"] == 10 and res["duplicates"][0]["geo"] == 7
    p.run("SCHECK, , SEL")
    assert "7" in p.model.sketch_selection and "5" in p.model.sketch_selection


def test_scheck_on_a_fully_defined_sketch(p):
    ok(p, "SKETCH, s, XY\nSRECT, 0, 0, 40, 20\nSCON, FIX, 1.S\nSDIM, LENGTH, 1, 40\nSDIM, LENGTH, 2, 20\nENDSKETCH")
    msg = p.run("SCHECK, s").message
    assert msg.splitlines()[0] == "sketch s: fully defined; no problems"
    assert "can still move" not in msg and "1 profile ready" in msg


# ---- a big sketch through edit cycles -----------------------------------------------------------

def big_sketch(rows: int) -> str:
    lines = ["W = 6", "SKETCH, s, XY"]
    k = 0
    for i in range(rows):
        for j in range(10):
            x, y = i * 20, j * 20
            lines += [f"SRECT, {x}, {y}, {x + 10}, {y + 10}", f"SDIM, LENGTH, {k + 1}, W + {i % 3}",
                      f"SCIRCLE, {x + 15}, {y + 15}, 2", f"SDIM, RADIUS, {k + 5}, W/4"]
            k += 5
    return "\n".join(lines + ["ENDSKETCH", "EXTRUDE, s, 3"])


def test_big_sketch_stays_right_through_edit_cycles(p):
    """500 curves and 1,000 constraints, edited and rebuilt again and again. The time limit is
    loose (CI machines are slow): before item 52 one cycle took about 22 s here, now about 5."""
    ok(p, big_sketch(10))
    sk = p.model.sketches["S"]
    assert len(sk.geos) == 500 and len(sk.cons) == 1000
    want = None
    for n in range(4):
        w = 6 + (n % 2)
        t = time.perf_counter()
        r = p.run(f'HIST, EDIT, 1, "W = {w}"')
        took = time.perf_counter() - t
        assert r.ok and all(e.ok for e in p.history), r.message
        assert took < 60, f"cycle {n} took {took:.1f} s"
        if n == 0:
            want = vol(p)
        elif n == 2:
            assert vol(p) == pytest.approx(want)
