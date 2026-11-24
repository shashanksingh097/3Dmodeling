"""Clear messages for every kernel failure (PLAN item 63): the geometry kernel refusing values,
a bug, and counts that would take hours are each told in plain words, naming the command.

Every command's example in docs/site/command-examples.cmd was also run with extreme values
(0, -5 and a million in each number: 1530 runs) by tests/fuzz_examples.py; what it found is
fixed and pinned here. Run it again after big changes: python tests/fuzz_examples.py."""

import re

import pytest

from modeler.commands import Processor
from modeler.commands.processor import REGISTRY
from modeler.core.kernel_errors import explain

# what a message must never look like: a bare exception from inside the program
RAW = re.compile(r"^\w*(Error|Exception|Failure|NotDone)\b|^Standard_|^StdFail|object has no attribute|"
                 r"NoneType|not subscriptable|index out of range|unsupported operand|positional argument|"
                 r"unexpected keyword|invalid literal|could not convert|referenced before")


def _kernel_error(name):
    return type(name, (Exception,), {"__module__": "OCP.Standard"})


def test_kernel_failures_are_explained():
    msg = explain("FILLET", _kernel_error("StdFail_NotDone")("BRepFilletAPI_MakeFillet::Shape"))
    assert msg.startswith("FILLET: the geometry kernel could not make the shape from these values. Try ")
    assert msg.endswith("(kernel: StdFail_NotDone: BRepFilletAPI_MakeFillet::Shape)")
    msg = explain("ARC", _kernel_error("Standard_ConstructionError")(""))
    assert "points in a line" in msg and msg.endswith("(kernel: Standard_ConstructionError)")
    # an OCCT class this table does not know still reads as the kernel's failure
    assert "the geometry kernel failed on these values" in explain("X", _kernel_error("Foo_Bar")("x"))
    # macOS builds raise the base class for "not done": it reads the same
    msg = explain("ARC", _kernel_error("Standard_Failure")("GC_MakeArcOfCircle::Value() - no result"))
    assert msg.startswith("ARC: the geometry kernel could not make the shape")


def test_other_failures_are_explained():
    assert "is a bug and not your mistake" in explain("LOFT", KeyError(3))
    assert "Help > Report a problem" in explain("LOFT", KeyError(3))
    assert explain("EXPORT", PermissionError(13, "Permission denied", "/x/y.step")) == \
        "EXPORT: could not use the file /x/y.step: Permission denied"
    assert "works out as zero" in explain("ARRAY", ZeroDivisionError("float division by zero"))
    assert "square root of a negative number" in explain("GEAR", ValueError("math domain error"))
    # the program's own geometry errors already say what is wrong: kept as they are
    from modeler.geometry.gears import GearError

    assert explain("GEAR", GearError("GEAR: too few teeth")) == "GEAR: too few teeth"
    assert explain("GEAR", GearError("too few teeth")) == "GEAR: too few teeth"


def test_a_kernel_failure_names_the_command_and_leaves_the_model_alone():
    p = Processor()
    p.run("BLOCK, 0,0,0, 10,10,10")
    r = p.run("ARC, 0,0,0, 1e6,15,0, 50,0,0")  # all but in a line: the kernel finds no arc
    assert not r.ok and r.message.startswith("ARC: the geometry kernel could not make the shape")
    assert "(kernel: StdFail_NotDone" in r.message
    assert len(p.history) == 1 and list(p.model.bodies) == [1]


def test_a_bug_says_it_is_one(monkeypatch):
    p = Processor()
    p.run("BLOCK, 0,0,0, 10,10,10")

    def broken(p, **_):
        p.model.bodies[99]  # a bug: a body that is not there

    monkeypatch.setattr(REGISTRY["SPHERE"], "fn", broken)
    r = p.run("SPHERE, 0,0,0, 5")
    assert not r.ok and r.message.startswith("SPHERE: this failed inside the program, which is a bug")
    assert r.message.endswith("(details: KeyError: 99)")
    assert len(p.history) == 1


@pytest.mark.parametrize("line, limit", [
    ("GEAR, 0,0,0, 2, 1e6, 10", "teeth 1000000 is more than this command can make in a sensible time; at most 1000"),
    ("HELIX, 0,0,0, 10, 5, 1e6", "turns 1000000 is more"),
    ("SPRING, 0,0,0, 10, 6, 1e6, 1.5", "turns 1000000 is more"),
    ("POLYGON, 0,0,0, 10, 1e6", "sides 1000000 is more"),
    ("STAR, 0,0,0, 20, 8, 1e6", "points 1000000 is more"),
])
def test_counts_that_would_take_hours_are_refused(line, limit):
    r = Processor().run(line)
    assert not r.ok and r.message.startswith(line.split(",")[0] + ": " + limit.split(" is")[0])
    assert limit in r.message


def test_a_sketch_pattern_of_a_million_is_refused():
    p = Processor()
    p.run_script("SKETCH, s, XY\nSCIRCLE, 10, 0, 2")
    assert "at most 1000" in p.run("SPATTERN, POLAR, 1e6, 360, O, 1").message


def test_every_command_answers_in_plain_words():
    """Every command, with no arguments, a zero, ones and minus ones, in an empty model and
    with a body picked: whatever it says, it is never a bare exception or a bug."""
    skip = {"QUIT", "EXIT", "NEW", "MCP"}
    bad = []
    for setup in ("", "BLOCK, 0,0,0, 10,10,10\nPICK, FACE, 1"):
        for name in sorted(set(REGISTRY) - skip):
            p = Processor()
            if setup:
                p.run_script(setup)
            for line in (name, f"{name}, 0", f"{name}" + ", 1" * 9, f"{name}" + ", -1" * 6):
                r = p.run(line)
                text = r.message.split(": ", 1)[-1] if r.message.startswith(name) else r.message
                if not r.ok and (RAW.search(text) or "is a bug" in r.message):
                    bad.append(f"{line}  ->  {r.message[:160]}")
    assert not bad, "\n".join(bad)
