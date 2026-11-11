"""The command language: expressions, parameters, blocks and macros (headless)."""

import math

import pytest

from modeler.commands import Processor
from modeler.lang.expr import Evaluator, ExprError, Vec
from modeler.lang.script import Incomplete, ScriptError, parse, split_args, split_entries, strip_comment


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    results = p.run_script(text)
    bad = [r for r in results if not r.ok]
    assert not bad, bad[0].message
    return results


def fail(p, text):
    r = p.run_script(text)[-1]
    assert not r.ok
    return r.message


# ---- text helpers ---------------------------------------------------------------

def test_split_args_respects_parentheses_and_quotes():
    assert split_args("CYL, max(1, 2), (1,2,3), 'a,b', \"c,d\", , x") == [
        "CYL", "max(1, 2)", "(1,2,3)", "'a,b'", '"c,d"', "", "x",
    ]


def test_comments_and_not_equal():
    assert strip_comment("BLOCK, 1 ! box") == "BLOCK, 1 "
    assert strip_comment("*IF, a != 2") == "*IF, a != 2"
    assert strip_comment('*MSG, "hi! there" ! c') == '*MSG, "hi! there" '


def test_split_entries_keeps_blocks_and_comments_together():
    text = """
! size
W = 1

*DO, i, 1, 2
  *IF, i, EQ, 1
    BLOCK, 0,0,0, 1,1,1
  *ENDIF
*ENDDO
FIT
"""
    entries = split_entries(text)
    assert entries == [
        "! size\nW = 1",
        "*DO, i, 1, 2\n  *IF, i, EQ, 1\n    BLOCK, 0,0,0, 1,1,1\n  *ENDIF\n*ENDDO",
        "FIT",
    ]
    with pytest.raises(Incomplete):
        split_entries("*DO, i, 1, 2\nFIT")
    with pytest.raises(ScriptError):
        parse("*ENDDO")
    with pytest.raises(ScriptError, match="does not close"):
        parse("*DO, i, 1, 2\n*ENDIF")


# ---- expressions ------------------------------------------------------------------

def test_expressions():
    ev = Evaluator({"W": 40, "P": Vec((1, 2, 3))}.__getitem__)
    assert ev.eval("w/2 + 1") == 21
    assert ev.eval("sqrt(W**2 + 9**2)") == pytest.approx(math.hypot(40, 9))
    assert ev.eval("cos(60)") == pytest.approx(0.5)  # degrees
    assert ev.eval("atan2(1, 1)") == pytest.approx(45)
    assert ev.eval("max(1, W, 3)") == 40
    assert ev.eval("PI") == pytest.approx(math.pi)
    assert ev.eval("P.z + P[0]") == 4
    assert ev.eval("P * 2 + (1, 1, 1)") == (3, 5, 7)
    assert ev.eval("1 if W > 30 and W < 50 else 0") == 1
    assert ev.eval('"part" + STR(3)') == "part3"
    assert ev.eval("W % 7") == 5


@pytest.mark.parametrize(
    "expr, msg",
    [
        ("1/0", "division by zero"),
        ("2^3", r"use \*\*"),
        ("nope + 1", "unknown name"),
        ("__import__('os')", "unknown function"),
        ("(1).real", "has no field"),
        ("[1, 2]", "not allowed"),
        ("lambda: 1", "not allowed"),
        ("sqrt(-1)", "sqrt"),
        ("'a' * 3", "joined with +"),
        ("10 ** 100000", "too large"),
        ("SIN", "is a function"),
    ],
)
def test_bad_expressions_are_errors_not_crashes(expr, msg):
    with pytest.raises(ExprError, match=msg):
        Evaluator({}.__getitem__).eval(expr)


# ---- parameters ---------------------------------------------------------------------

def test_parameters_drive_commands(p):
    ok(p, "W = 40\nh = w/2\nBLOCK, 0,0,0, W, H, 5")
    assert p.params == {"W": 40, "H": 20}
    assert p.evaluate("VOL(1)") == pytest.approx(40 * 20 * 5)
    assert p.evaluate("BBOX(1).ymax") == pytest.approx(20)


def test_a_point_fills_three_arguments(p):
    ok(p, "C = (5, 6, 7)\nSPHERE, C, 2\nCYL, C + (10, 0, 0), 1, 3")
    assert p.evaluate("CENT(1)") == pytest.approx((5, 6, 7))
    assert p.evaluate("CENT(2).x") == pytest.approx(15)
    assert "does not fit" in fail(p, "SPHERE, 0, 0, C")


def test_builtin_names_cannot_be_parameters(p):
    assert "built-in" in fail(p, "PI = 3")
    assert "built-in" in fail(p, "LAST = 3")
    assert "built-in" in fail(p, "sqrt = 3")


def test_unit_constants(p):
    ok(p, "L = 2*INCH")
    assert p.params["L"] == pytest.approx(50.8)
    ok(p, "/UNITS, IN\nL2 = 25.4*MM")
    assert p.params["L2"] == pytest.approx(1)


# ---- blocks -------------------------------------------------------------------------

def test_do_loop_with_step_exit_and_cycle(p):
    ok(p, """
*DO, i, 0, 10, 2
  *IF, i, EQ, 4
    *CYCLE
  *ENDIF
  *IF, i > 7
    *EXIT
  *ENDIF
  SPHERE, i*10, 0, 0, 1
*ENDDO
""")
    xs = sorted(round(p.evaluate(f"CENT({b}).x")) for b in p.model.bodies)
    assert xs == [0, 20, 60]
    assert p.params["I"] == 8


def test_do_loop_counting_down_and_empty(p):
    ok(p, "N = 0\n*DO, i, 3, 1, -1\n  N = N*10 + i\n*ENDDO")
    assert p.params["N"] == 321
    ok(p, "*DO, j, 1, 0\n  N = 0\n*ENDDO")
    assert p.params["N"] == 321


def test_if_elseif_else(p):
    script = """
*IF, W, LT, 10
  K = 1
*ELSEIF, W < 20
  K = 2
*ELSE
  K = 3
*ENDIF
"""
    for w, k in ((5, 1), (15, 2), (25, 3)):
        ok(p, f"W = {w}\n{script}")
        assert p.params["K"] == k


def test_while_and_runaway_protection(p):
    ok(p, "X = 1\n*WHILE, X < 100\n  X = X*2\n*ENDWHILE")
    assert p.params["X"] == 128
    assert "endless" in fail(p, "*WHILE, 1\n  Y = 1\n*ENDWHILE")
    assert "limit" in fail(p, "*DO, i, 1, 1e9\n*ENDDO")


def test_msg_and_del(p):
    r = ok(p, 'W = 3\n*MSG, "W is ", W, " and twice is ", 2*W')[-1]
    assert r.message == "W is 3 and twice is 6"
    ok(p, "*DEL, W")
    assert "W" not in p.params


def test_control_words_out_of_place(p):
    assert "outside a loop" in fail(p, "*EXIT")
    assert "outside a macro" in fail(p, "*RETURN")
    assert "unknown block word" in fail(p, "*FOO")


# ---- macros -------------------------------------------------------------------------

def test_macro_is_a_new_command_with_defaults_and_locals(p):
    ok(p, """
T = 5
BLOCK, 0,0,0, 40,20,T
NAME, LAST, plate
*MACRO, hole, x, y, d=6
  DEPTH = T + 2          ! local to the macro
  CYL, x, y, -1, d/2, DEPTH
  SUBTRACT, plate, LAST
*END
hole, 10, 10
hole, 30, 10, 4
""")
    assert "DEPTH" not in p.params
    v = 40 * 20 * 5 - math.pi * (9 + 4) * 5
    assert p.evaluate("VOL(plate)") == pytest.approx(v, rel=1e-6)
    assert "required" in fail(p, "hole")
    assert "at most 3" in fail(p, "hole, 1, 2, 3, 4")
    assert "built-in command" in fail(p, "*MACRO, block\n*END")
    assert run_help(p, "HOLE").startswith("macro HOLE")


def run_help(p, name):
    return p.run(f"HELP, {name}").message


def test_macro_return_and_word_arguments(p):
    ok(p, """
BLOCK, 0,0,0, 1,1,1
*MACRO, pickall, kind
  *IF, kind == "EDGE"
    SEL, ALL, kind
    *RETURN
  *ENDIF
  SEL, NONE
*END
pickall, EDGE
""")
    assert p.model.selection_kind == "EDGE" and len(p.model.selection) == 12
    ok(p, "pickall, FACE")
    assert p.model.selection == []


def test_recursive_macro_is_limited(p):
    msg = fail(p, "*MACRO, forever\n  forever\n*END\nforever")
    assert "nested more than" in msg


def test_errors_inside_blocks_name_the_line(p):
    msg = fail(p, "*DO, i, 1, 3\n  SPHERE, 0, 0, 0, 1\n  SPHERE, 0, 0, 0, -i\n*ENDDO")
    assert "line 3:" in msg and "positive" in msg
    assert p.model.bodies == {}  # the whole block was rolled back


# ---- interactive input --------------------------------------------------------------

def test_typed_block_waits_for_its_end(p):
    assert p.run("*DO, i, 1, 3").pending
    assert p.run("  SPHERE, i*10, 0, 0, 1").pending
    r = p.run("*ENDDO")
    assert r.ok and not r.pending
    assert len(p.model.bodies) == 3
    assert len(p.history) == 1


def test_command_arguments_are_case_insensitive_words(p):
    ok(p, "block, 0,0,0, 1,1,1\npick, face, 1, s\nKIND = \"edge\"\nSEL, S, KIND, ID, 1")
    assert p.model.selection_kind == "EDGE"
