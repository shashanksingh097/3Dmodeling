"""Part documents: NEWPART, OPENPART, SAVEPART (M11a)."""

import pytest
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from modeler.commands import Processor
from modeler.commands.partdoc_handlers import part_blocks, part_inputs, part_text

SRC = open("scripts/threaded_bolts.cmd").read()


def ok(p, line):
    r = p.run(line)
    assert r.ok, r.message
    return r.message


def bad(p, line):
    r = p.run(line)
    assert not r.ok, f"{line} should fail, got: {r.message}"
    return r.message


def volume(p):
    total = 0.0
    for b in p.model.bodies.values():
        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(b.shape, g)
        total += g.Mass()
    return total


@pytest.fixture
def parts_file(tmp_path):
    f = tmp_path / "fasteners.cmd"
    f.write_text("! bolts and nuts\n\n" + "\n\n".join(b.source for b in part_blocks(SRC)) + "\n", encoding="utf-8")
    return f


def test_open_unwraps_a_part_into_steps(parts_file):
    p = Processor()
    assert "name the one" in bad(p, f'OPENPART, "{parts_file}"')
    msg = ok(p, f'OPENPART, "{parts_file}", nut')
    assert "part nut: 2 inputs" in msg
    assert p.part_doc.name == "nut" and p.part_doc.file == str(parts_file)
    assert part_inputs(p) == [("D", "8"), ("M", "0.8*D")]
    assert p.log[2].strip().startswith("POLYGON")
    assert p.model.bodies  # the profiles and the nut, as the steps made them


def test_round_trip_keeps_the_part_and_the_rest_of_the_file(parts_file):
    p = Processor()
    ok(p, f'OPENPART, "{parts_file}", bolt')
    v0 = volume(p)
    assert "replaced part bolt" in ok(p, "SAVEPART")
    text = parts_file.read_text(encoding="utf-8")
    assert text.startswith("! bolts and nuts") and "*PART, nut" in text
    q = Processor()
    ok(q, f'OPENPART, "{parts_file}", bolt')
    assert volume(q) == pytest.approx(v0, rel=1e-6)
    assert q.log == p.log  # same steps, comments included


def heights(parts_file):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    a = Processor()
    ok(a, f'LIB, LOAD, "{parts_file}"')
    ok(a, "INST, nut, 0,0,0")
    ok(a, "INST, nut, 30,0,0, D=10")
    out = []
    for bid in sorted(a.model.bodies):
        box = Bnd_Box()
        BRepBndLib.Add_s(a.model.bodies[bid].shape, box)
        out.append(box.CornerMax().Z() - box.CornerMin().Z())
    return out


def test_edit_a_step_save_and_every_copy_in_a_project_follows(parts_file):
    before = heights(parts_file)
    p = Processor()
    ok(p, f'OPENPART, "{parts_file}", nut')
    ok(p, 'HIST, EDIT, 2, "M = 1.2*D"')  # a taller nut
    ok(p, "SAVEPART")
    after = heights(parts_file)
    assert after[0] - before[0] == pytest.approx(0.4 * 8, abs=0.2)  # (thread ends make the boxes a little loose)
    assert after[1] - before[1] == pytest.approx(0.4 * 10, abs=0.2)


def test_new_part_saved_to_a_new_file_and_loaded(tmp_path):
    p = Processor()
    ok(p, "NEWPART, peg")
    assert "has no steps" in bad(p, f'SAVEPART, "{tmp_path / "x"}"')
    ok(p, "D = 4")
    ok(p, "H = 3*D")
    ok(p, "CYL, 0,0,0, D/2, H")
    ok(p, "R = D/4")
    ok(p, "SEL, S, EDGE, AT, D/2, 0, H")
    ok(p, "FILLET, R")
    assert part_text(p).splitlines()[0] == "*PART, peg, D=4, H=3*D"
    assert "  R = D/4" in part_text(p)  # only the leading values are inputs
    f = tmp_path / "pegs" / "peg"
    assert "wrote part peg" in ok(p, f'SAVEPART, "{f}"')
    assert (tmp_path / "pegs" / "peg.cmd").is_file() and p.part_doc.file.endswith("peg.cmd")
    q = Processor()
    ok(q, f'LIB, LOAD, "{tmp_path / "pegs" / "peg.cmd"}"')
    ok(q, "INST, peg, 0,0,0, D=6")
    assert len(q.model.bodies) == 1


def test_save_part_needs_a_part_document():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 1,1,1")
    assert "not a part document" in bad(p, "SAVEPART, a.cmd")
    ok(p, "NEWPART, thing")
    assert p.part_doc is not None
    ok(p, "NEW")
    assert p.part_doc is None
    assert "valid part name" in bad(p, "NEWPART, 2bad")


def test_sink_hands_the_block_back():
    got = []
    p = Processor()
    from modeler.commands.partdoc_handlers import open_part_text

    open_part_text(p, "*PART, peg, D=4\n  CYL, 0,0,0, D/2, 10\n*ENDPART", sink=lambda t: got.append(t) or "sent")
    ok(p, 'HIST, EDIT, 2, "CYL, 0,0,0, D/2, 20"')
    assert ok(p, "SAVEPART") == "sent"
    assert got == ["*PART, peg, D=4\n  CYL, 0,0,0, D/2, 20\n*ENDPART"]
