"""Design tables (PLAN item 59): configurations from a CSV file, steps turned off per
configuration, every variant built and compared, parts list and drawing per configuration; all of
it kept through save and open."""

import json
import math
import os

import pytest

from modeler.commands import Processor

# steps 1-2 values, 3-4 the plate, 5-6 a hole (step 6 cuts it)
MODEL = """W = 40
H = 10
BLOCK, 0,0,0, W, 20, H
NAME, LAST, plate
CYL, 10,10,-1, 3, H+2
SUBTRACT, plate, LAST"""


@pytest.fixture
def p():
    q = Processor()
    ok(q, MODEL)
    return q


def ok(p, text):
    res = p.run_script(text)
    bad = [r for r in res if not r.ok]
    assert not bad, f"{bad[0].line}: {bad[0].message}"
    return res[-1]


def vol(p):
    return p.evaluate("VOL(plate)")


def table(tmp_path, text):
    f = tmp_path / "sizes.csv"
    f.write_text(text, encoding="utf-8")
    return str(f)


HOLE = math.pi * 9


def test_a_design_table_makes_configurations(p, tmp_path):
    f = table(tmp_path, "config, W, H, off\nsmall, 30, 5, 5 6\nbig, 60, 20,\n")
    msg = p.run(f'DESIGNTABLE, "{f}"').message
    assert "2 configurations (2 new, 0 changed)" in msg and "steps off: 5, 6" in msg
    assert set(p.configs) == {"SMALL", "BIG"}
    assert [e.text for e in p.history[-2:]] == ['CONFIG, small, "W = 30, H = 5"', 'CONFIG, big, "W = 60, H = 20"']
    ok(p, "USECONFIG, small")
    assert vol(p) == pytest.approx(30 * 20 * 5)  # no hole in the small one
    assert p.history[5].message == "off in configuration SMALL"
    ok(p, "USECONFIG, big")
    assert vol(p) == pytest.approx(60 * 20 * 20 - HOLE * 20)
    # reading it again changes the CONFIG steps in place
    table(tmp_path, "config, W, H, off\nsmall, 32, 5, 5 6\nbig, 60, 20,\n")
    msg = p.run(f'DESIGNTABLE, "{f}"').message
    assert "(0 new, 1 changed)" in msg and len([e for e in p.history if e.text.startswith("CONFIG")]) == 2


def test_steps_off_follow_their_steps_and_survive_save_and_open(p, tmp_path):
    ok(p, 'CONFIG, plain, "W = 50"')
    assert "steps 5, 6 are off" in p.run('CONFIGOFF, plain, "5 6"').message
    ok(p, "USECONFIG, plain")
    assert vol(p) == pytest.approx(50 * 20 * 10)
    # a step added before them: the same steps stay off
    p.run('HIST, INSERT, 1, "D = 1"')
    assert "steps 6, 7 are off" in p.run("CONFIGOFF, plain").message
    assert vol(p) == pytest.approx(50 * 20 * 10)
    path = str(tmp_path / "t.m3d")
    ok(p, f'SAVE, "{path}"')
    q = Processor()
    ok(q, f'OPEN, "{path}"')
    assert q.config == "PLAIN" and vol(q) == pytest.approx(50 * 20 * 10)
    ok(q, "USECONFIG, DEFAULT")
    assert vol(q) == pytest.approx(40 * 20 * 10 - HOLE * 10)
    assert "every step is on" in q.run('CONFIGOFF, plain, "6 7", ON').message


def test_variants_are_built_on_their_own_and_compared(p, tmp_path):
    f = table(tmp_path, "config, W, H, off\nsmall, 30, 5, 5 6\nbig, 60, 20,\n")
    ok(p, f'DESIGNTABLE, "{f}"')
    before = vol(p)
    rows = json.loads(p.run("VARIANTS, JSON").message)["variants"]
    by = {r["config"]: r for r in rows}
    assert set(by) == {"DEFAULT", "SMALL", "BIG"}
    assert by["SMALL"]["volume"] == pytest.approx(3000) and by["SMALL"]["off"] == [5, 6]
    assert by["BIG"]["size"] == pytest.approx([60, 20, 20])
    assert by["BIG"]["volume_change"] == pytest.approx((by["BIG"]["volume"] - by["DEFAULT"]["volume"])
                                                       / by["DEFAULT"]["volume"])
    assert by["DEFAULT"]["ok"] and by["SMALL"]["ok"] and by["BIG"]["ok"]
    assert vol(p) == pytest.approx(before) and p.config == ""  # the model in use is untouched
    msg = p.run("VARIANTS").message
    assert "SMALL: builds" in msg and "steps off: 5, 6" in msg and "3 variants" in msg


def test_a_variant_that_fails_says_where(p):
    ok(p, 'CONFIG, broken, "W = 0"')
    rows = json.loads(p.run("VARIANTS, JSON").message)["variants"]
    bad = next(r for r in rows if r["config"] == "BROKEN")
    assert not bad["ok"] and bad["failed"][0]["step"] == 3
    assert "FAILS at step 3" in p.run("VARIANTS").message


def test_parts_list_and_drawing_per_configuration(p, tmp_path):
    f = table(tmp_path, "config, W, H, off\nsmall, 30, 5, 5 6\nbig, 60, 20,\n")
    ok(p, f'DESIGNTABLE, "{f}"')
    out = str(tmp_path / "out")
    msg = p.run(f'VARIANTS, TEXT, "{out}"').message
    assert "wrote small_bom.csv, small.svg" in msg
    assert sorted(os.listdir(out)) == ["big.svg", "big_bom.csv", "default.svg", "default_bom.csv",
                                       "small.svg", "small_bom.csv"]
    msg = p.run("BOM, , small").message
    assert msg.startswith("configuration SMALL:") and "3,000 mm3" in msg
    assert "no configuration nope" in p.run("BOM, , nope").message.lower()


def test_export_writes_a_table_that_reads_back(p, tmp_path):
    ok(p, 'CONFIG, a, "W = 30"\nCONFIG, b, "W = 50, H = 12"')
    ok(p, 'CONFIGOFF, a, "5 6"')
    path = str(tmp_path / "out.csv")
    ok(p, f'DESIGNTABLE, "{path}", EXPORT')
    text = (tmp_path / "out.csv").read_text(encoding="utf-8").splitlines()
    assert text[0] == "config,W,H,off" and text[1] == "a,30,,5 6" and text[2] == "b,50,12,"
    q = Processor()
    ok(q, MODEL)
    ok(q, f'DESIGNTABLE, "{path}"')
    assert q.configs == p.configs and q.run("CONFIGOFF, a").message == "A: steps 5, 6 are off"


def test_bad_tables_are_refused(p, tmp_path):
    def read(text):
        return p.run(f'DESIGNTABLE, "{table(tmp_path, text)}"').message

    assert "no configuration" in p.run('CONFIGOFF, nope, "1"').message
    assert "at least one configuration" in read("config, W\n")
    assert "no step 99" in read("config, W, off\na, 3, 99\n")
    assert "comes twice" in read("config, W\na, 3\na, 4\n")
    assert "not a parameter name" in read("config, 2W\na, 3\n")
    assert "no configurations" in Processor().run("VARIANTS").message
