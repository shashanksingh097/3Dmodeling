"""PLAN items 92-94 without a window: numbers with units, view names and turns,
tutorials (every built-in one is done to the end), LAYOUT's list, the new
queries, tooltip pictures and the assistant's tools."""

import json
import math
import os

import pytest

from modeler.ai import expect
from modeler.ai.tools import Toolbox
from modeler.commands import tutorial_handlers as th
from modeler.commands.processor import Processor
from modeler.core import units, views


def run(p, text):
    out = []
    for line in text.strip().splitlines():
        r = p.run(line)
        assert r.ok, f"{line}: {r.message}"
        out.append(r)
    return out[-1] if out else None


def fails(p, line, *words):
    r = p.run(line)
    assert not r.ok, f"{line} should fail: {r.message}"
    for w in words:
        assert w in r.message, r.message
    return r.message


# ---- item 92: numbers with units ------------------------------------------------------------
@pytest.mark.parametrize("text, want", [
    ("25 mm", "(25*MM)"),
    ("25mm + 2", "(25*MM) + 2"),
    ("1/4 in", "((1/4)*INCH)"),
    ("0.5 m", "(0.5*METER)"),
    ("2 ft", "(2*(12*INCH))"),
    ("30 deg", "(30*1)"),
    ("1.5e1 cm", "(1.5e1*CM)"),
    ("(W/4) in", "((W/4)*INCH)"),
    ("MAX(1, 2) in", "(MAX(1, 2)*INCH)"),
    ('"25 mm"', '"25 mm"'),
    ("W/4 in", "W/4 in"),  # unclear: left to fail
    ("W1 + 2", "W1 + 2"),
    ("item", "item"),
    ("M8", "M8"),
])
def test_expand(text, want):
    assert units.expand(text) == want


def test_has_unit_ignores_quotes():
    assert units.has_unit("BLOCK, 0,0,0, 1 in, 2, 3")
    assert not units.has_unit('ECHO, "1 in"')
    assert not units.has_unit("BLOCK, 0,0,0, 1, 2, 3")


def test_units_in_commands_and_parameters_mm_project():
    p = Processor()
    run(p, "W = 1 in\nBLOCK, 0,0,0, W, 1/2 in, 1 cm\nNAME, LAST, b")
    assert p.params["W"] == pytest.approx(25.4)
    assert expect.check(p, "BBOX(b).dx, EQ, 25.4, 1e-9").passed
    assert expect.check(p, "BBOX(b).dy, EQ, 12.7, 1e-9").passed
    assert expect.check(p, "BBOX(b).dz, EQ, 10, 1e-9").passed
    assert p.evaluate("90 deg") == 90 and p.evaluate("(W/2) mm") == pytest.approx(12.7)
    assert p.evaluate("1 rad") == pytest.approx(180 / math.pi)
    assert p.evaluate("2 ft") == pytest.approx(609.6)


def test_units_in_an_inch_project():
    p = Processor()
    run(p, "/UNITS, IN\nBLOCK, 0,0,0, 25.4 mm, 1, 2 ft\nNAME, LAST, b")
    assert expect.check(p, "BBOX(b).dx, EQ, 1, 1e-9").passed
    assert expect.check(p, "BBOX(b).dz, EQ, 24, 1e-9").passed


def test_show_units_changes_only_what_is_shown():
    p = Processor()
    r = run(p, "/UNITS")
    assert "units MM" in r.message and "25 mm" in r.message
    run(p, "BLOCK, 0,0,0, 25.4, 50.8, 10\nNAME, LAST, b")
    r = run(p, "/UNITS, IN, SHOW")
    assert "inches" in r.message and p.model.units == "MM" and p.model.show_units == "IN"
    from modeler.commands import selinfo as si

    info = si.selection_info(p, "BODY", [1])
    item = info["items"][0]
    assert info["unit"] == "in" and item["size"][:2] == pytest.approx([1.0, 2.0])
    assert item["volume"] == pytest.approx(25.4 * 50.8 * 10 / 25.4 ** 3, rel=1e-5)
    assert "size 1 x 2 x 0.3937 in" in si.line(info) and "in³" in si.line(info)
    # the Properties table shows and reads plain numbers in the shown units
    d = json.loads(p.run("PROPS, b, JSON").message)
    rows = {r["key"]: r for r in d["rows"]}
    assert d["units"] == "in" and rows["x"]["value"] == pytest.approx(0.5)
    run(p, "PROPS, b, x, 2")  # 2 inches
    assert expect.check(p, "CENT(b)[0], EQ, 50.8, 1e-6").passed
    n = len(p.history)
    r = run(p, "/UNITS")
    assert "shown in inches" in r.message and len(p.history) == n  # a question, not a step
    run(p, "UNDO")
    assert expect.check(p, "CENT(b)[0], EQ, 12.7, 1e-6").passed


def test_units_and_lessons_are_not_repeated():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 1,1,1\n/UNITS, IN, SHOW\nLAYOUT")
    assert p.last_tool == "BLOCK, 0,0,0, 1,1,1"


def test_repeat_works_in_a_script():
    """The REPEAT command example runs as a script (the user guide builds it so)."""
    p = Processor()
    rs = p.run_script("BLOCK, 0,0,0, 40, 20, 10\nPICK, EDGE, 1\nFILLET, 2\nREPEAT, EDGE, 3\nREPEAT, SHOW")
    assert all(r.ok for r in rs), [r.message for r in rs if not r.ok]
    assert "FILLET, 2" in rs[-1].message


def test_show_units_go_with_undo_and_snapshots():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 1,1,1\n/UNITS, IN, SHOW")
    snap = p.model.snapshot()
    p.model.show_units = ""
    p.model.restore(snap)
    assert p.model.show_units == "IN"


def test_form_fields_know_their_unit():
    from modeler.gui import forms

    def fields(cmd):
        return [f for v in forms.spec(cmd).variants for f in v.fields]

    block = fields("BLOCK")
    assert {forms.field_unit(f, "mm") for f in block if f.kind in ("num", "point")} == {"mm"}
    assert "deg" in {forms.field_unit(f) for f in fields("ROTATE")}
    assert "in" in {forms.field_unit(f, "in") for f in fields("CYL")}
    assert all(forms.field_unit(f) == "" for f in block if f.kind not in ("num", "point"))


# ---- item 93: view names and turns ------------------------------------------------------------
def test_view_names():
    assert views.canonical("front-top") == "TOP FRONT"
    assert views.canonical("iso") == "TOP FRONT RIGHT"
    assert views.canonical("top bottom") == "" and views.canonical("sideways") == ""
    assert views.direction("TOP FRONT RIGHT") == (1.0, -1.0, 1.0)
    assert views.direction("LEFT LEFT") is None
    assert views.up_for((0, 0, 1)) == (0.0, 1.0, 0.0) and views.up_for((1, 0, 0)) == (0.0, 0.0, 1.0)
    assert views.name_of("V3d_XposYnegZpos") == "TOP FRONT RIGHT"
    assert views.name_of("V3d_Zpos") == "TOP"
    assert views.name_of("V3d_XnegYpos") == "BACK LEFT"


def test_turns_go_round_and_back():
    eye, up = (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)  # FRONT
    e, u = views.turned(eye, up, "LEFT")
    assert views.nearest_name(e) in ("LEFT", "RIGHT")
    for how, back in (("LEFT", "RIGHT"), ("UP", "DOWN"), ("CW", "CCW")):
        e, u = views.turned(eye, up, how)
        e2, u2 = views.turned(e, u, back)
        assert e2 == pytest.approx(eye, abs=1e-9) and u2 == pytest.approx(up, abs=1e-9)
    e = eye
    u = up
    for _ in range(4):
        e, u = views.turned(e, u, "LEFT")
    assert e == pytest.approx(eye, abs=1e-9)
    e, _ = views.turned(eye, up, "UP")
    assert views.nearest_name(e) == "TOP"
    with pytest.raises(ValueError):
        views.turned(eye, up, "SIDEWAYS")


def test_view_command_without_a_window():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 1,1,1")
    assert "TOP FRONT" in run(p, "VIEW, front top").message
    assert "turned left" in run(p, "VIEW, TURN, LEFT").message
    assert "home" in run(p, "VIEW, HOME").message
    fails(p, "VIEW, TURN, SIDEWAYS", "LEFT")
    fails(p, "VIEW, NOWHERE")
    assert len(p.history) == 1  # VIEW is not a history step


def test_view_state_tool_without_a_view():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 1,1,1\nHIDE, 1")
    out = Toolbox(p).call("view_state", {})
    assert "no 3D view" in json.dumps(out)


# ---- item 94: tutorials -------------------------------------------------------------------------
def test_built_in_tutorials_are_listed_in_order():
    tuts = th.available()
    names = [t.name for t in tuts]
    assert names[:3] == ["first_part", "sketch_to_solid", "fix_a_step"]
    for t in tuts:
        assert t.title and t.about and t.steps
        for s in t.steps:
            assert s.title and s.text
            assert len(s.labels) == len(s.checks)
            assert all(s.labels), f"{t.name}: {s.title}: every check has words"
        assert not t.steps[-1].checks  # the last step is to read


@pytest.mark.parametrize("name", ["first_part", "sketch_to_solid", "fix_a_step"])
def test_each_tutorial_can_be_done_with_show_me(name):
    p = Processor()
    r = run(p, f"TUTORIAL, {name}")
    t = p.tutorial.tut
    assert f"step 1 of {len(t.steps)}" in r.message
    for i, s in enumerate(t.steps):
        assert p.tutorial.index == i
        if s.checks:
            # not done before Show me (each step needs work)
            fails(p, "TUTORIAL, NEXT", "not done yet", "TUTORIAL, HINT")
            assert p.tutorial.index == i
            hint = run(p, "TUTORIAL, HINT").message
            assert s.hints[0] in hint
            out = run(p, "TUTORIAL, SHOW").message
            assert "✓" in out
            assert th._passed(p.tutorial)
        r = run(p, "TUTORIAL, NEXT")
    assert "finished" in r.message and p.tutorial is None
    assert expect.check(p, "FAILED(), EQ, 0").passed


def test_first_part_by_hand_with_units():
    """The checks look at the model, not at the lines: other ways of doing a step pass too."""
    p = Processor()
    run(p, "TUTORIAL, first_part")
    run(p, "BLOCK, 10, 10, 0, 8 cm, 50 mm, 1 cm")  # not the hint's numbers
    run(p, "TUTORIAL, NEXT")
    run(p, "NAME, 1, plate")
    run(p, "TUTORIAL, NEXT")
    assert th._passed(p.tutorial)  # already 80 x 50 x 10
    run(p, "TUTORIAL, NEXT")
    run(p, "HOLE, plate, 30, 35, 10, 8\nHOLE, plate, 70, 35, 10, 8")
    st = json.loads(run(p, "TUTORIAL, JSON").message)
    assert st["passed"] and st["step"] == 4 and st["checks"][0]["label"] == "two holes of 8 in the plate"


def test_check_says_what_is_missing():
    p = Processor()
    run(p, "TUTORIAL, first_part")
    run(p, "BLOCK, 0,0,0, 60, 40, 10\nTUTORIAL, NEXT\nNAME, LAST, plate\nTUTORIAL, NEXT")
    out = run(p, "TUTORIAL, CHECK").message
    assert "80 long (now: BBOX(plate).dx is 60, expected EQ 80" in out
    assert "✓ 10 thick" in out
    msg = fails(p, "TUTORIAL, NEXT", "80 long")
    assert "50 wide" in msg and "10 thick" not in msg


def test_unknown_names_read_as_not_yet():
    p = Processor()
    run(p, "TUTORIAL, first_part\nTUTORIAL, SHOW\nTUTORIAL, NEXT")
    out = run(p, "TUTORIAL, CHECK").message
    assert "a body called plate (now: not yet: nothing is called plate)" in out


def test_back_stop_and_errors():
    p = Processor()
    fails(p, "TUTORIAL, NEXT", "no tutorial is running")
    fails(p, "TUTORIAL, nonesuch", "no tutorial", "first_part")
    run(p, "TUTORIAL, sketch_to_solid")
    fails(p, "TUTORIAL, BACK", "first step")
    run(p, "TUTORIAL, SHOW\nTUTORIAL, NEXT")
    assert p.tutorial.index == 1
    run(p, "TUTORIAL, BACK")
    assert p.tutorial.index == 0 and 0 in p.tutorial.done
    out = run(p, "TUTORIAL").message
    assert "following: sketch_to_solid, step 1 of" in out
    assert "stopped" in run(p, "TUTORIAL, STOP").message and p.tutorial is None
    assert len(p.history) == 1  # the model stays
    st = json.loads(run(p, "TUTORIAL, JSON").message)
    assert st["tutorial"] is None and len(st["available"]) >= 3


def test_starting_refuses_to_lose_unsaved_work(tmp_path):
    p = Processor()
    run(p, "BLOCK, 0,0,0, 1,1,1")
    fails(p, "TUTORIAL, first_part", "unsaved changes", "TUTORIAL, first_part, NEW")
    assert len(p.history) == 1 and p.tutorial is None
    run(p, f"SAVE, {tmp_path / 'mine.m3d'}")
    run(p, "TUTORIAL, first_part")  # saved: nothing to lose
    assert p.history == [] and p.tutorial is not None
    run(p, "TUTORIAL, fix_a_step")  # nothing done in the lesson yet: nothing to lose
    run(p, "TUTORIAL, NEXT\nTUTORIAL, SHOW")
    fails(p, "TUTORIAL, first_part", "unsaved")  # its own steps were done
    run(p, "TUTORIAL, first_part, new")
    assert p.tutorial.tut.name == "first_part" and p.history == []


def test_a_lesson_starts_with_its_own_steps():
    p = Processor()
    run(p, "TUTORIAL, fix_a_step")
    assert p.params["H"] == 4
    assert expect.check(p, "FAILED(), EQ, 1").passed  # the fillet that no longer fits
    assert p.saved_script == p.script()  # nothing of the user's to lose yet


def test_your_own_tutorials(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELER_TUTORIALS", str(tmp_path))
    (tmp_path / "bracket.tut").write_text(
        "! tutorial: bracket\n! title: An angle bracket\n! about: a test\n! order: 0\n! start: W = 40\n\n"
        "## Base\nMake the **base**.\nhint: BLOCK, 0, 0, 0, W, 30, 5\n"
        "check: BBOX(LAST).dx, EQ, 40 ! 40 long\n\n## Done\nGood.\n", encoding="utf-8")
    (tmp_path / "broken.tut").write_text("text before any step\n", encoding="utf-8")
    assert th.available()[0].name == "bracket"
    assert "broken" not in [t.name for t in th.available()]
    p = Processor()
    run(p, "TUTORIAL, An angle bracket")  # by title too
    assert p.params["W"] == 40
    out = run(p, "TUTORIAL, CHECK").message
    assert "· 40 long (now:" in out
    run(p, "TUTORIAL, SHOW\nTUTORIAL, NEXT\nTUTORIAL, NEXT")
    assert p.tutorial is None


def test_parse_errors():
    from modeler.commands.processor import CommandError

    with pytest.raises(CommandError, match="before the first"):
        th.parse("! tutorial: x\nloose text\n## a\n")
    with pytest.raises(CommandError, match="no steps"):
        th.parse("! tutorial: x\n")
    t = th.parse("! tutorial: x\n! order: soon\n## A\nline one\n\n\n\nline two\ncheck: VALID(1)\n")
    assert t.order == 99 and t.steps[0].text == "line one\n\nline two" and t.steps[0].labels == [""]


def test_a_panel_is_told(monkeypatch):
    p = Processor()
    calls = []

    class UI:
        def tutorial_changed(self):
            calls.append(p.tutorial.index if p.tutorial else None)

    p.ui = UI()
    run(p, "TUTORIAL, first_part\nTUTORIAL, SHOW\nTUTORIAL, NEXT\nTUTORIAL, STOP")
    assert calls[0] == 0 and calls[-1] is None and 1 in calls


def test_tutorial_tool():
    p = Processor()
    tb = Toolbox(p)
    out = tb.call("tutorial", {})
    assert out["tutorial"] is None and {"first_part", "fix_a_step"} <= {t["name"] for t in out["available"]}
    run(p, "TUTORIAL, first_part")
    out = tb.call("tutorial", {})
    assert out["step"] == 1 and out["hints"] == ["BLOCK, 0, 0, 0, 60, 40, 10"] and not out["passed"]
    run(p, "BLOCK, 0,0,0, 2,2,2")
    out = tb.call("tutorial", {})  # checks again
    assert out["passed"] and out["checks"][0]["pass"]


def test_tutor_skill_is_found():
    from modeler.ai import skills as sk

    found = sk.discover()
    assert "tutor" in found
    text = open(os.path.join(os.path.dirname(th.__file__), "..", "skills", "tutor", "SKILL.md"),
                encoding="utf-8").read()
    assert "`tutorial`" in text and "TUTORIAL, SHOW" in text


# ---- the new queries ------------------------------------------------------------------------------
def test_failed_steps_and_sketched():
    p = Processor()
    run(p, "R = 1\nBLOCK, 0,0,0, 10,10,2\nNAME, LAST, b\nSEL, S, EDGE, AT, 5, 0, 2\nFILLET, R\nSEL, NONE")
    assert p.evaluate("FAILED()") == 0
    assert p.evaluate('STEPS("FILLET")') == 1 and p.evaluate('STEPS("fillet")') == 1
    assert p.evaluate("STEPS()") == len(p.history)
    run(p, 'HIST, EDIT, 1, "R = 5"')
    assert p.evaluate("FAILED()") == 1
    assert p.evaluate('SKETCHED("nope")') == 0
    run(p, "SKETCH, s, XY\nSRECT, 0, 0, 10, 5\nSCIRCLE, 5, 2, 1\nSLINE, 0, 0, 10, 5, CONSTR")
    assert p.evaluate('SKETCHED("s")') == 5  # the construction line does not count
    assert p.evaluate('SKETCHED("s", "line")') == 4 and p.evaluate('SKETCHED("s", "circle")') == 1


# ---- LAYOUT without a window ----------------------------------------------------------------------
def test_layout_lists_without_a_window():
    p = Processor()
    out = run(p, "LAYOUT").message
    for name in ("modelling", "sketch", "assembly", "drawing", "sculpt"):
        assert name in out
    d = json.loads(run(p, "LAYOUT, JSON").message)
    assert set(d["built_in"]) == {"modelling", "sketch", "assembly", "drawing", "sculpt"} and d["saved"] == []
    fails(p, "LAYOUT, sketch", "no window")
    fails(p, "LAYOUT, SAVE", "give it a name")
    fails(p, "LAYOUT, SAVE, sketch", "built-in")
    assert p.history == []


def test_layout_talks_to_the_window():
    from modeler.commands import layout_handlers as lh

    seen = []

    class Layouts:
        current = ""

        def saved_names(self):
            return ["mine"]

        def apply(self, key, spec):
            seen.append(("apply", key, spec["tab"]))

        def restore(self, name):
            seen.append(("restore", name))
            return name.lower() == "mine"

        def save(self, name):
            seen.append(("save", name))

        def delete(self, name):
            return name == "mine"

        def reset(self):
            seen.append(("reset",))

    class UI:
        layouts = Layouts()

    p = Processor()
    p.ui = UI()
    run(p, "LAYOUT, Modeling\nLAYOUT, sculpt\nLAYOUT, mine\nLAYOUT, SAVE, other\nLAYOUT, RESET\nLAYOUT, DELETE, mine")
    assert seen[:2] == [("apply", "modelling", "Model"), ("apply", "sculpt", "Sculpt")]
    assert ("restore", "mine") in seen and ("save", "other") in seen and ("reset",) in seen
    fails(p, "LAYOUT, DELETE, other", "no saved layout")
    fails(p, "LAYOUT, elsewhere", "no layout", "mine")
    assert "saved: mine" in run(p, "LAYOUT").message
    assert lh.canonical("SCULPTING") == "sculpt"


# ---- picture tooltips (no Qt needed) ----------------------------------------------------------------
def test_tooltip_pictures():
    from modeler.gui import picture_tips as pt

    assert pt.command_of("Add a block: opens its form\nRuns: BLOCK, ...") == "BLOCK"
    assert pt.command_of("Leave sketch mode\nRuns: ENDSKETCH") == "ENDSKETCH"
    assert pt.command_of("no command here") == ""
    for cmd in ("BLOCK", "CYL", "HOLE", "FILLET", "EXTRUDE", "SHELL", "GEAR"):
        path = pt.picture_for(cmd)
        assert path and os.path.getsize(path) < 12000, cmd
    assert pt.picture_for("SAVE") == "" and pt.picture_for("NOSUCH") == ""
    html = pt.rich_tip("Round <edges>\nRuns: FILLET", pt.picture_for("FILLET"))
    assert "&lt;edges&gt;<br>Runs" in html and "<img src=" in html and "width='240'" in html


def test_tooltip_pictures_are_packaged():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as f:
        text = f.read()
    assert '"modeler.tutorials" = ["*.tut"]' in text and "tip_pictures/*.png" in text
    with open(os.path.join(root, "packaging", "3Dmodeling.spec"), encoding="utf-8") as f:
        spec = f.read()
    assert "tip_pictures" in spec and '"tutorials"' in spec
