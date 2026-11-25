"""PLAN item 71: sheet metal found in a bent part made elsewhere (TOSHEET)."""

import pytest

from modeler.commands import Processor

BRACKET = """SKETCH, base, XY
SRECT, 0, 0, 60, 40
ENDSKETCH
SHEET, base, 2, 3
NAME, LAST, bracket
SEL, S, EDGE, AT, 30, 0, 2
FLANGE, , 25
SEL, S, EDGE, AT, 60, 20, 0
FLANGE, , 15, 45
SEL, S, EDGE, AT, 0, 20, 2
FLANGE, , 10, 120, 4
"""


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def err(p, line):
    r = p.run(line)
    assert not r.ok, r.message
    return r.message


def _blank(msg):
    dims = msg.split("flat blank ")[1].split(" (")[0]
    return sorted(float(v) for v in dims.split(" × "))


def _through_step(p, tmp_path, b="bracket"):
    f = tmp_path / "part.step"
    ok(p, f'EXPORT, STEP, "{f}", {b}')
    q = Processor()
    ok(q, f'IMPORT, STEP, "{f}", part')
    return q


def test_imported_bracket_unfolds_like_the_original(tmp_path):
    p = Processor()
    ok(p, BRACKET)
    want = _blank(ok(p, "UNFOLD, bracket").message)
    q = _through_step(p, tmp_path)
    r = ok(q, "TOSHEET, part")
    assert "2 thick, 3 bends" in r.message
    rep = q.reports["TOSHEET"]
    assert rep["thickness"] == pytest.approx(2)
    assert sorted(round(b["angle"]) for b in rep["bends"]) == [45, 90, 120]
    assert sorted(round(b["wall"], 6) for b in rep["bends"]) == [10, 15, 25]
    assert sorted(round(b["radius"], 6) for b in rep["bends"]) == [3, 3, 4]
    got = _blank(ok(q, "UNFOLD, part").message)
    assert got == pytest.approx(want, abs=0.01)
    assert "3 flanges" in ok(q, "SHEETINFO, part").message


def test_k_factor_and_dxf(tmp_path):
    p = Processor()
    ok(p, BRACKET)
    q = _through_step(p, tmp_path)
    ok(q, "TOSHEET, part, 0.3")
    f = tmp_path / "blank.dxf"
    ok(q, f'UNFOLD, part, "{f}", NO')
    text = f.read_text()
    assert "BEND" in text and "OUTLINE" in text


def test_refuses_parts_it_cannot_explain(tmp_path):
    p = Processor()
    ok(p, BRACKET + "BLOCK, 20, 10, 2, 10, 10, 8\nUNION, bracket, LAST\n")
    q = _through_step(p, tmp_path)
    msg = err(q, "TOSHEET, part")
    assert "not all 2 thick" in msg
    assert "is sheet metal already" in err(p, "TOSHEET, bracket")
    ok(q, "SPHERE, 0,0,0, 5")
    assert "no flat faces" in err(q, "TOSHEET, LAST")
