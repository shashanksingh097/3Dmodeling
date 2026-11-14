"""Linked part files (LIB, LINK): the assembly reads the part file itself, so
the copies follow it; RELOAD; the saved copy when the file is missing."""

import math
import os
import shutil

import pytest

from modeler.commands import Processor
from modeler.commands.part_handlers import links_changed

BOLT = """*PART, bolt, D=8, L={L}
  CYL, 0, 0, 0, D, 5        ! head
  CYL, 0, 0, -L, D/2, L     ! shank
  UNION, 1, 2
*ENDPART
"""


def bolt_volume(length, d=8):
    return math.pi * d * d * 5 + math.pi * (d / 2) ** 2 * length


def write_bolt(path, length):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(BOLT.format(L=length))
    # a new mtime is not what is compared (the text is), but keep it moving anyway
    st = os.stat(path)
    os.utime(path, (st.st_atime, st.st_mtime + 1))


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def assembly(p, f, n=3):
    lines = [f'LIB, LINK, "{f}"'] + [f"INST, bolt, {20 * i}, 0, 0" for i in range(n)]
    return ok(p, "\n".join(lines))


def volumes(p):
    return sorted(round(p.evaluate(f"VOL({b})"), 3) for b in p.model.instances)


@pytest.fixture
def bolt_file(tmp_path):
    f = tmp_path / "parts" / "bolt.cmd"
    f.parent.mkdir()
    write_bolt(f, 30)
    return f


def test_link_follows_the_file_and_reload_updates_every_copy(bolt_file):
    p = Processor()
    assembly(p, bolt_file)
    assert volumes(p) == [round(bolt_volume(30), 3)] * 3
    assert p.run("RELOAD").message == "linked part files are unchanged"
    write_bolt(bolt_file, 50)
    assert links_changed(p) == [str(bolt_file)]
    r = p.run("RELOAD")
    assert r.ok, r.message
    assert r.message.startswith("bolt updated from bolt.cmd: 3 copies")
    assert volumes(p) == [round(bolt_volume(50), 3)] * 3
    assert links_changed(p) == []
    # RELOAD is not a history entry; UNDO goes back past the last INST, not the reload
    assert len(p.history) == 4
    # a later rebuild from the start reads the file again too
    write_bolt(bolt_file, 40)
    p.rebuild(0)
    assert volumes(p) == [round(bolt_volume(40), 3)] * 3


def test_load_keeps_its_version(bolt_file):
    p = Processor()
    ok(p, f'LIB, LOAD, "{bolt_file}"\nINST, bolt, 0, 0, 0')
    write_bolt(bolt_file, 50)
    assert p.run("RELOAD").message.startswith("no linked part files")
    assert volumes(p) == [round(bolt_volume(30), 3)]


def test_list_parts_says_linked_or_loaded(bolt_file, tmp_path):
    p = Processor()
    assembly(p, bolt_file, 2)
    other = tmp_path / "nut.cmd"
    other.write_text("*PART, nut, D=8\n  CYL, 0, 0, 0, D, 4\n*ENDPART\n", encoding="utf-8")
    ok(p, f'LIB, LOAD, "{other}"\n*PART, pin\n  CYL, 0, 0, 0, 2, 10\n*ENDPART')
    text = p.run("LIST, PARTS").message
    assert f"bolt(D=8, L=30): 2 instances, linked to {bolt_file}" in text
    assert f"nut(D=8): 0 instances, loaded from {other}" in text
    assert "pin(): 0 instances, defined in this project" in text
    assert p.part_files["BOLT"] == (str(bolt_file), "linked")


def test_project_reopens_with_the_live_file(bolt_file, tmp_path):
    p = Processor()
    assembly(p, bolt_file)
    proj = tmp_path / "asm" / "frame.m3d"
    ok(p, f'SAVE, "{proj}"')
    write_bolt(bolt_file, 60)  # changed while the project was closed
    q = Processor()
    r = q.run(f'OPEN, "{proj}"')
    assert r.ok, r.message
    assert volumes(q) == [round(bolt_volume(60), 3)] * 3
    assert q.history[0].message.startswith("linked 1 part")


def test_missing_file_falls_back_to_the_saved_copy(bolt_file, tmp_path):
    p = Processor()
    assembly(p, bolt_file)
    proj = tmp_path / "frame.m3d"
    ok(p, f'SAVE, "{proj}"')
    moved = tmp_path / "bolt_moved.cmd"
    shutil.move(bolt_file, moved)
    q = Processor()
    r = q.run(f'OPEN, "{proj}"')
    assert r.ok, r.message
    assert volumes(q) == [round(bolt_volume(30), 3)] * 3
    e = q.history[0]
    assert e.ok and "is missing; using the copy saved in the project" in e.warning
    assert "which is missing" in q.run("LIST, PARTS").message
    # the file comes back (changed): RELOAD reads it and the warning goes
    write_bolt(bolt_file, 45)
    r = q.run("RELOAD")
    assert r.ok and "bolt updated from bolt.cmd" in r.message, r.message
    assert volumes(q) == [round(bolt_volume(45), 3)] * 3
    assert not q.history[0].warning
    # saving keeps the live file's text as the copy
    ok(q, f'SAVE, "{proj}"')
    os.remove(bolt_file)
    z = Processor()
    assert z.run(f'OPEN, "{proj}"').ok
    assert volumes(z) == [round(bolt_volume(45), 3)] * 3


def test_project_and_parts_moved_together(tmp_path):
    """Moved to another PC: the absolute path is gone, the one next to the project is found."""
    src = tmp_path / "a"
    (src / "parts").mkdir(parents=True)
    write_bolt(src / "parts" / "bolt.cmd", 30)
    p = Processor()
    assembly(p, src / "parts" / "bolt.cmd", 2)
    ok(p, f'SAVE, "{src / "frame.m3d"}"')
    dst = tmp_path / "b"
    shutil.move(str(src), str(dst))
    write_bolt(dst / "parts" / "bolt.cmd", 70)
    q = Processor()
    assert q.run(f'OPEN, "{dst / "frame.m3d"}"').ok
    assert volumes(q) == [round(bolt_volume(70), 3)] * 2
    assert not q.history[0].warning
    assert q.part_files["BOLT"][1] == "linked"


def test_undo_of_the_link_is_not_reloaded(bolt_file):
    p = Processor()
    ok(p, f'LIB, LINK, "{bolt_file}"')
    p.run("UNDO")
    write_bolt(bolt_file, 50)
    assert p.run("RELOAD").message.startswith("no linked part files")
