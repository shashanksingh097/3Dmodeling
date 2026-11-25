"""Named face sets for the analysis app (PLAN item 95): CM sets go to STEP by name, IMPORT reads them
back, FLUIDVOLUME and ENCLOSURE make their own sets, CMRENAME, the model tree menu and DESCRIBE."""

import pytest

from modeler.ai import describe
from modeler.commands.processor import Processor
from modeler.core.model import Model


def run(p, text):
    for line in text.strip().splitlines():
        r = p.run(line.strip())
        assert r.ok, (line, r.message)
    return r


@pytest.fixture
def p():
    return Processor(Model())


def test_sets_round_trip_through_step(p, tmp_path):
    f = tmp_path / "named.step"
    run(p, f"""BLOCK, 0,0,0, 10,20,30
SEL, S, FACE, NORMAL, 0,0,1
CM, Inlet_Face, FACE
SEL, S, EDGE, LOC, Z, 0
CM, rim, EDGE
EXPORT, STEP, "{f}" """)
    text = f.read_text(errors="replace")
    assert "ADVANCED_FACE('Inlet_Face'" in text and text.count("EDGE_CURVE('rim'") == 4
    q = Processor(Model())
    r = run(q, f'IMPORT, STEP, "{f}"')
    assert "2 named sets from the file" in r.message and "bodies" not in r.message
    m = q.model
    assert m.named_set("inlet_face")[0] == "FACE" and len(m.named_set("inlet_face")[1]) == 1
    assert m.set_label("INLET_FACE") == "Inlet_Face"
    kind, edges = m.named_set("rim")
    assert kind == "EDGE" and len(edges) == 4
    # the face read back is the top one
    run(q, "SEL, S, FACE, NORMAL, 0,0,1")
    assert list(m.selection) == m.named_set("inlet_face")[1]


def test_a_face_in_two_sets_keeps_both_names(p, tmp_path):
    f = tmp_path / "two.step"
    run(p, f"""BLOCK, 0,0,0, 10,10,10
SEL, S, FACE, NORMAL, 0,0,1
CM, fixed, FACE
SEL, A, FACE, NORMAL, 1,0,0
CM, outside, FACE
EXPORT, STEP, "{f}" """)
    assert "'fixed; outside'" in f.read_text(errors="replace")
    q = Processor(Model())
    run(q, f'IMPORT, STEP, "{f}"')
    assert len(q.model.named_set("fixed")[1]) == 1 and len(q.model.named_set("outside")[1]) == 2


def test_cmrename_and_undo(p):
    run(p, "BLOCK, 0,0,0, 10,10,10\nSEL, S, FACE, NORMAL, 0,0,1\nCM, top, FACE\nCMRENAME, top, Inlet")
    assert "INLET" in p.model.named_sets and "TOP" not in p.model.named_sets
    assert describe.model_summary(p)["sets"]["Inlet"]["kind"] == "FACE"
    assert not p.run("CMRENAME, nothing, x").ok
    run(p, "CM, other, FACE")
    assert not p.run("CMRENAME, other, inlet").ok  # taken
    run(p, "UNDO")
    assert "OTHER" not in p.model.named_sets
    run(p, "UNDO")
    assert "TOP" in p.model.named_sets and "INLET" not in p.model.named_sets


def test_fluid_volume_and_enclosure_save_sets(p):
    run(p, """CYL, 0,0,0, 10, 80
NAME, LAST, pipe
CYL, 0,0,0, 8, 80
SUBTRACT, pipe, LAST
FLUIDVOLUME, pipe""")
    sets = {p.model.set_label(k): v for k, v in p.model.named_sets.items()}
    assert sets["pipe_fluid_opening_1"][0] == "FACE" and sets["pipe_fluid_opening_2"][0] == "FACE"
    run(p, 'BLOCK, 100,0,0, 30,20,10\nNAME, LAST, part\nENCLOSURE, part, BOX, 10')
    sets = {p.model.set_label(k): v for k, v in p.model.named_sets.items()}
    for side in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax", "walls"):
        assert sets[f"enclosure_{side}"][0] == "FACE" and sets[f"enclosure_{side}"][1]


def test_tree_menu_of_a_set(p):
    try:  # the tree's menu needs Qt's GUI library, which needs libEGL; CI's plain Linux runners lack it
        from modeler.gui import model_tree, tree_model
    except ImportError as exc:
        pytest.skip(f"needs Qt's GUI library here: {exc}")

    run(p, "BLOCK, 0,0,0, 10,10,10\nSEL, S, FACE, NORMAL, 0,0,1\nCM, Inlet, FACE")
    nodes = tree_model.tree_nodes(p)
    row = tree_model.find(nodes, "set:INLET")
    assert row is not None and row.label.startswith("Inlet") and "STEP" in row.tip
    items = model_tree.set_items(p.model, "INLET")
    labels = [i.label for i in items]
    assert labels[:2] == ["Set Inlet", "Select"] and "Rename…" in labels and "Delete" in labels
    rename = next(i for i in items if i.label == "Rename…")
    assert rename.ask and rename.commands == ["CMRENAME, Inlet, {}"]
    for i in items:
        for c in i.commands:
            if "{}" not in c:
                assert p.run(c).ok, c
