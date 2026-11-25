"""PLAN item 73: sizes, fits, geometric tolerances and datums written to STEP (AP242) and read back."""

import re

import pytest

from modeler.commands import Processor

PLATE = """BLOCK, 0,0,0, 100, 60, 10
NAME, LAST, plate
HOLE, plate, 30, 30, 10, 20
SEL, S, FACE, LOC, Z, 0
NOTE, DATUM, A
SEL, S, FACE, LOC, X, 0
NOTE, DATUM, B
SEL, S, FACE, LOC, Z, 10
NOTE, GDT, FLATNESS, 0.05
NOTE, GDT, PARALLELISM, 0.02, A
SEL, NONE
NOTE, SIZE, 0,60,10, 100,60,10
NOTE, "Paint black", 50, 30, 20
"""


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def _hole_face(p):
    r = p.run("FEATURES, plate")
    assert r.ok, r.message
    return re.search(r"faces (\d+)", r.message).group(1)


@pytest.fixture
def plate():
    p = Processor()
    ok(p, PLATE)
    gid = _hole_face(p)
    ok(p, f"PICK, FACE, {gid}\nNOTE, FIT, H7\nNOTE, GDT, POSITION, D0.1, A, B\nSEL, NONE")
    return p


def _texts(p):
    return sorted(n.text for n in p.model.notes)


def test_round_trip(plate, tmp_path):
    path = tmp_path / "plate.step"
    r = plate.run(f'EXPORT, STEP, "{path}"')
    assert r.ok, r.message
    assert "AP242 with 1 size, 1 diameter, 3 tolerances, 2 datums" in r.message
    text = path.read_text(errors="replace")
    assert "AP242" in text.upper() or "1 0 10303 442" in text
    for word in ("FLATNESS_TOLERANCE", "PARALLELISM_TOLERANCE", "POSITION_TOLERANCE", "DATUM_FEATURE",
                 "DIMENSIONAL_SIZE", "DIMENSIONAL_LOCATION"):
        assert word in text, word
    before = [t for t in _texts(plate) if t != "Paint black"]
    p2 = Processor()
    r = p2.run(f'IMPORT, STEP, "{path}"')
    assert r.ok, r.message
    assert "7 notes from the file's annotations" in r.message
    assert _texts(p2) == before  # the plain text note stays in the project only
    pos = next(n for n in p2.model.notes if n.frame is not None and n.frame.kind == "POSITION")
    assert pos.frame.tol == "ø0.1" and pos.frame.datums == ("A", "B")
    size = next(n for n in p2.model.notes if n.span is not None)
    assert size.text == "100"
    fit = next(n for n in p2.model.notes if n.text.startswith("ø20"))
    assert "H7" in fit.text  # the fit found again from its limits


def test_zone_sizes_are_right_in_the_file(plate, tmp_path):
    """The flatness zone (no datums) must be 0.05 mm in the file, whatever unit it is written in."""
    path = tmp_path / "plate.step"
    ok(plate, f'EXPORT, STEP, "{path}"')
    assert _zones(path) == [0.02, 0.05, 0.1]


def _zones(path):
    """The tolerance zones in a STEP file, in mm."""
    text = path.read_text(errors="replace")
    units = dict(re.findall(r"#(\d+) = \( LENGTH_UNIT\(\) NAMED_UNIT\(\*\) SI_UNIT\(([^)]*)\) \);", text))
    found = []
    for value, ref in re.findall(r"LENGTH_MEASURE_WITH_UNIT\(LENGTH_MEASURE\(([^)]+)\),#(\d+)\)", text):
        scale = 1.0 if units.get(ref, "").startswith(".MILLI.") else 1000.0
        found.append(round(float(value) * scale, 9))
    return sorted(found)


def test_no_notes_keeps_plain_step(tmp_path):
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 10, 10, 10")
    path = tmp_path / "b.step"
    r = p.run(f'EXPORT, STEP, "{path}"')
    assert r.ok and "AP242" not in r.message
    assert "AUTOMOTIVE_DESIGN" in path.read_text(errors="replace")  # the usual schema when there is nothing to add


def test_only_notes_on_exported_bodies(plate, tmp_path):
    ok(plate, "BLOCK, 200,0,0, 10, 10, 10\nNAME, LAST, other\nSEL, S, FACE, LOC, X, 210\nNOTE, GDT, FLATNESS, 0.1\nSEL, NONE")
    path = tmp_path / "other.step"
    r = plate.run(f'EXPORT, STEP, "{path}", other')
    assert r.ok and "AP242 with 1 tolerance" in r.message
    assert _zones(path) == [0.1]  # with no sizes in the file the zone is written in metres, still 0.1 mm
    p2 = Processor()
    ok(p2, f'IMPORT, STEP, "{path}"')
    assert [n.frame.tol for n in p2.model.notes] == ["0.1"]


def test_writer_settings_restored(plate, tmp_path):
    from OCP.Interface import Interface_Static

    get = getattr(Interface_Static, "CVal_s", None) or Interface_Static.CVal
    before = get("write.step.schema")
    ok(plate, f'EXPORT, STEP, "{tmp_path / "a.step"}"')
    assert get("write.step.schema") == before
