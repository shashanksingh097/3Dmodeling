"""PLAN items 83-85 without a window: PREVIEW and preview_step, the SEL groups
(LOOP, CHAIN, TANGENT), PICK with several IDs, box and lasso picks with a pretend
camera, and the tools that fit a pick (TOOLS, the right-click menu, suggest_tools)."""

import json

import pytest

from modeler.ai.tools import Toolbox
from modeler.commands import Processor
from modeler.commands import preview_handlers as ph
from modeler.gui import body_menu as bm
from modeler.gui import region_pick as rp


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def fails(p, text):
    r = p.run_script(text)[-1]
    assert not r.ok
    return r.message


def sel(p):
    return list(p.model.selection)


# ---- item 83: previews ----------------------------------------------------------------
def test_preview_says_what_a_step_would_do_and_changes_nothing():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nNAME, LAST, plate\nSEL, S, EDGE, BODY, plate")
    before = (len(p.history), sorted(p.model.bodies), p.model.revision)
    pv = ph.preview_step(p, "FILLET, 2")
    assert pv.ok and not pv.added and not pv.removed
    (row,) = pv.changed
    assert row["name"] == "plate" and row["was"] == 1
    assert row["volume"][0] == pytest.approx(8000) and row["volume"][1] < 8000
    assert pv.text().startswith("changes plate, volume 8,000 -> ")
    assert [k for _s, k in pv.ghosts] == ["solid"]
    assert (len(p.history), sorted(p.model.bodies), p.model.revision) == before


def test_preview_of_a_failing_step_names_the_reason_and_the_edges():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nPICK, EDGE, 1 2")
    pv = ph.preview_step(p, "FILLET, 30")
    assert not pv.ok and "too large" in pv.message
    assert pv.fault == {"kind": "EDGE", "ids": [1, 2]}
    assert pv.text().startswith("Would fail: FILLET: radius 30 is too large") and "edges 1, 2" in pv.text()
    assert len(pv.ghosts) == 2 and {k for _s, k in pv.ghosts} == {"fault"}


def test_preview_names_entities_from_the_message_when_it_can():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 10,10,10")
    pv = ph.preview_step(p, "SEL, S, FACE, ID, 999")
    assert not pv.ok and pv.fault is None


def test_preview_adds_removes_and_skips():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nNAME, LAST, plate\nCYL, 10,10,0, 3, 10")
    pv = ph.preview_step(p, "SUBTRACT, plate, 2")
    assert [r["name"] for r in pv.changed] == ["plate"] and [r["id"] for r in pv.removed] == [2]
    assert "removes body 2" in pv.text()
    kinds = sorted(k for _s, k in pv.ghosts)
    assert kinds == ["removed", "solid"]
    assert ph.preview_step(p, "BLOCK, 0,0,30, 5,5,5").added[0]["volume"] == pytest.approx(125)
    assert ph.preview_step(p, "SAVE, x.m3d").skipped
    assert ph.preview_step(p, "EXPORT, STEP, x.step").skipped
    assert ph.preview_step(p, "").skipped
    assert ph.preview_step(p, "W = 3").text().startswith("Changes no bodies")


def test_preview_of_an_edited_entry_rebuilds_on_a_copy():
    p = Processor()
    ok(p, "H = 10\nBLOCK, 0,0,0, 40,20,H\nNAME, LAST, plate\nHOLE, plate, 20,10,H, 4")
    pv = ph.preview_step(p, "H = 30", edit_row=0)
    assert pv.ok
    vol = pv.changed[0]["volume"][1]
    assert vol == pytest.approx(40 * 20 * 30 - 3.14159265 * 4 * 30, rel=1e-3)  # the hole goes through the new height
    assert p.evaluate("VOL(plate)") == pytest.approx(40 * 20 * 10 - 3.14159265 * 4 * 10, rel=1e-3)


def test_the_preview_command_draws_and_clears():
    p = Processor()
    got = []
    p.model.subscribe(lambda ev: got.append(ev.kind))
    ok(p, "BLOCK, 0,0,0, 10,10,10")
    n = len(p.history)
    r = ok(p, 'PREVIEW, "HOLE, 1, 5,5,10, 4"')
    assert "changes body 1 (becomes body 2)" in r.message
    assert p.model.preview and p.model.preview_bodies == [1] and got[-1] == "preview"
    assert len(p.history) == n  # not a history step
    assert ok(p, "PREVIEW, OFF").message == "preview cleared"
    assert not p.model.preview and not p.model.preview_bodies
    assert "another PREVIEW" in fails(p, 'PREVIEW, "PREVIEW, OFF"')


def test_the_assistant_previews_and_reads_nothing_new():
    from modeler.ai import safeguards as sg

    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nNAME, LAST, plate\nSEL, S, EDGE, BODY, plate")
    box = Toolbox(p)
    before = sg.fingerprint(p)
    got = box.call("preview_step", {"step": "FILLET, 2"})
    assert got["ok"] and got["changed"][0]["name"] == "plate" and "text" in got
    bad = box.call("preview_step", {"step": "FILLET, 30"})
    assert not bad["ok"] and bad["fault"]["kind"] == "EDGE"
    edit = box.call("preview_step", {"step": "BLOCK, 0,0,0, 40,20,30", "entry": 1})
    assert edit["changed"][0]["volume"][1] == pytest.approx(24000)
    assert sg.fingerprint(p) == before
    assert not p.model.preview  # the assistant never draws on the user's view


# ---- item 84: groups, several IDs, regions ------------------------------------------------
def _rounded_plate(p):
    """A 40 x 20 x 10 plate with its four upright edges rounded: the top outline is
    four lines and four arcs, all joined smoothly."""
    ok(p, "BLOCK, 0,0,0, 40,20,10\nNAME, LAST, plate\nSEL, S, EDGE, BODY, plate\nSEL, R, EDGE, SIZE, EQ, 10\n"
          "FILLET, 3\nSEL, S, FACE, BODY, plate\nSEL, R, FACE, NORMAL, 0,0,1")
    top = sel(p)[0]
    ok(p, "SEL, S, EDGE, OF, FACE\nSEL, R, EDGE, TYPE, LINE")
    return top, sel(p)


def test_loop_chain_and_tangent_on_a_plain_block():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nSEL, S, FACE, NORMAL, 0,0,1")
    top = sel(p)[0]
    ok(p, "SEL, S, EDGE, OF, FACE")
    rim = sel(p)
    ok(p, f"SEL, S, EDGE, LOOP, {rim[0]}, {top}")
    assert sel(p) == sorted(rim)
    ok(p, f"SEL, S, EDGE, CHAIN, {rim[0]}")
    assert sel(p) == [rim[0]]  # square corners: the chain stops at once
    ok(p, f"SEL, S, FACE, TANGENT, {top}")
    assert sel(p) == [top]


def test_chain_follows_a_rounded_outline_and_loop_without_a_face_takes_the_flat_one():
    p = Processor()
    top, lines = _rounded_plate(p)
    ok(p, f"SEL, S, EDGE, CHAIN, {lines[0]}")
    chain = sel(p)
    assert len(chain) == 8  # 4 lines and 4 arcs
    ok(p, f"SEL, S, EDGE, LOOP, {lines[0]}")
    assert sel(p) == chain
    ok(p, f"SEL, S, EDGE, CHAIN, {lines[0]}, 0.001")  # a tight angle: still smooth (they are tangent)
    assert len(sel(p)) == 8


def test_tangent_faces_take_the_rounds_and_sides_but_not_the_top():
    p = Processor()
    top, _lines = _rounded_plate(p)
    ok(p, "SEL, S, FACE, BODY, plate\nSEL, R, FACE, TYPE, CYLINDER")
    rounds = sel(p)
    ok(p, f"SEL, S, FACE, TANGENT, {rounds[0]}")
    ring = sel(p)
    assert len(ring) == 8 and top not in ring and set(rounds) <= set(ring)


def test_group_errors_say_what_to_do():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 10,10,10")
    assert "picks edges" in fails(p, "SEL, S, FACE, LOOP, 1")
    assert "picks faces" in fails(p, "SEL, S, EDGE, TANGENT, 1")
    assert "no EDGE with ID 999" in fails(p, "SEL, S, EDGE, CHAIN, 999")
    far = next(f for f in p.model.bodies[1].entity_ids["FACE"]
               if f not in _faces_of_edge(p, 1))
    assert "not beside that edge" in fails(p, f"SEL, S, EDGE, LOOP, 1, {far}")


def _faces_of_edge(p, e):
    ok(p, f"SEL, S, EDGE, ID, {e}\nSEL, S, FACE, BODY, 1")
    from modeler.geometry import topo_select as ts

    m = p.model
    shape = m.bodies[1].shape
    return [m.find_entity(1, "FACE", f) for f in ts.edge_faces(shape, ts._cast[ts.TopAbs_EDGE](m.entity_shape("EDGE", e)))]


def test_pick_takes_several_ids_and_keeps_them_through_edits():
    p = Processor()
    ok(p, "W = 40\nBLOCK, 0,0,0, W,20,10\nNAME, LAST, plate\nPICK, FACE, 3 5 6")
    assert sel(p) == [3, 5, 6]
    ok(p, "PICK, FACE, 1, A\nPICK, FACE, 3 5, U")
    assert sel(p) == [6, 1]
    assert "whole numbers" in fails(p, "PICK, FACE, 3 x 5")
    # the picks follow the same faces when an earlier step changes
    p2 = Processor()
    ok(p2, "W = 40\nBLOCK, 0,0,0, W,20,10\nNAME, LAST, plate\nPICK, FACE, 3 5 6\nFILLET_R = 0")
    centres = [tuple(round(c, 6) for c in p2.evaluate(f'CENT({g}, "FACE")')) for g in sel(p2)]
    ok(p2, "HIST, EDIT, 1, \"W = 60\"")
    assert len(sel(p2)) == 3
    assert all(p2.history[i].ok for i in range(len(p2.history)))
    after = [p2.evaluate(f'CENT({g}, "FACE")') for g in sel(p2)]
    assert [round(c[2], 6) for c in after] == [c[2] for c in centres]  # same faces (z of each centre kept)


def _top_view(scale=10.0):
    return lambda q: (q[0] * scale, -q[1] * scale)


def test_a_box_left_to_right_picks_what_is_inside_and_right_to_left_what_it_touches():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 10,10,10\nBLOCK, 30,0,0, 10,10,10")
    to_px = _top_view()
    a, b = (-20, 20), (150, -150)  # round the first block only (pixels: y grows downwards)
    assert rp.box_mode(a, b) == rp.INSIDE and rp.box_mode(b, a) == rp.CROSSING
    poly = rp.box_polygon(a, b)
    assert rp.pick_region(p.model, "BODY", poly, rp.INSIDE, to_px) == [1]
    faces = rp.pick_region(p.model, "FACE", poly, rp.INSIDE, to_px)
    assert faces == p.model.bodies[1].entity_ids["FACE"]
    # a small box in the middle of the top face: inside picks nothing, crossing picks the faces seen there
    small = rp.box_polygon((40, -40), (60, -60))
    assert rp.pick_region(p.model, "FACE", small, rp.INSIDE, to_px) == []
    crossing = rp.pick_region(p.model, "FACE", small, rp.CROSSING, to_px)
    assert set(crossing) == {5, 6}  # the top and the bottom (hidden ones too)
    # a box over the gap between the two blocks touching both
    both = rp.box_polygon((350, 10), (50, -50))
    assert rp.pick_region(p.model, "BODY", both, rp.CROSSING, to_px) == [1, 2]
    edges = rp.pick_region(p.model, "EDGE", both, rp.CROSSING, to_px)
    assert edges and all(p.model.entity_owner("EDGE", e)[0] in (1, 2) for e in edges)
    verts = rp.pick_region(p.model, "VERTEX", rp.box_polygon((-5, 5), (5, -5)), rp.INSIDE, to_px)
    assert len(verts) == 2  # the two corners at x = y = 0 (top and bottom)
    assert rp.pick_region(p.model, "BODY", poly, rp.INSIDE, to_px, bodies=[2]) == []


def test_a_lasso_picks_what_lies_inside_the_loop():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 10,10,10\nBLOCK, 30,0,0, 10,10,10")
    to_px = _top_view()
    loop = [(-100, 50), (50, -400), (200, 50)]  # a triangle round the first block
    assert rp.inside((50, -50), loop)
    assert rp.pick_region(p.model, "BODY", loop, rp.INSIDE, to_px) == [1]
    assert rp.ids_text([3, 5, 7]) == "3 5 7"


def test_region_pick_writes_one_pick_that_replays():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 10,10,10")
    ids = rp.pick_region(p.model, "EDGE", rp.box_polygon((-20, 20), (120, -120)), rp.INSIDE, _top_view())
    assert len(ids) == 12
    ok(p, f"PICK, EDGE, {rp.ids_text(ids)}\nFILLET, 1")
    assert p.history[-1].ok and len(p.history) == 3


# ---- item 85: the tools that fit a pick -------------------------------------------------------
TOOL_CASES = [
    ("PICK, FACE, 6", ["Sketch on this face", "Pull…", "Hole…", "Fillet its edges…"]),
    ("PICK, FACE, 3 6", ["Pull 2 faces…", "Fillet their edges…"]),
    ("CYL, 60,0,0, 5, 20\nPICK, FACE, 7", ["Pull…", "Thread…"]),
    ("PICK, EDGE, 1", ["Fillet…", "Chamfer…", "Loop round its face", "Tangent chain"]),
    ("PICK, EDGE, 1 2", ["Fillet 2 edges…", "Chamfer 2 edges…", "Distance and angle"]),
    ("PICK, VERTEX, 1 2", ["Distance"]),
    ("PICK, VERTEX, 1 2 3", ["Work plane through the three"]),
    ("PICK, BODY, 1", ["Move…", "Rotate…", "Mirror…", "Array…"]),
    ("BLOCK, 5,5,5, 40,20,10\nPICK, BODY, 1\nPICK, BODY, 2, A", ["Move 2 bodies…", "Rotate…", "Mirror…", "Array…",
                                                               "Union of the 2", "Subtract the others from body 1",
                                                               "Intersect the 2"]),
]


@pytest.mark.parametrize("setup,first", TOOL_CASES)
def test_the_tools_fit_the_pick_and_every_direct_one_runs(setup, first):
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\n" + setup)
    items = bm.pick_tools(p)
    assert [i.label for i in items][: len(first)] == first
    from modeler.gui import forms as F

    try:
        from modeler.gui import icons  # Qt's GUI library: not on a runner without libEGL

        names = icons.NAMES
    except ImportError:
        names = None
    for it in items:
        assert names is None or it.icon in names, it.label
        assert it.short and len(it.short) <= 14, it.label
        if it.form:
            assert it.form in F.specs(), it.form
        else:
            q = Processor()
            ok(q, "BLOCK, 0,0,0, 40,20,10\n" + setup)
            ok(q, "\n".join(it.first + it.commands))
        for c in it.first:
            q = Processor()
            ok(q, "BLOCK, 0,0,0, 40,20,10\n" + setup)
            ok(q, c)


def test_nothing_picked_no_tools_and_the_menu_puts_them_first():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nBLOCK, 50,0,0, 5,5,5")
    assert bm.pick_tools(p) == []
    assert "nothing is picked" in ok(p, "TOOLS").message
    ok(p, "PICK, FACE, 6")
    items = bm.body_items(p.model, 1, p.part_files, p)
    assert items[0].title and items[0].label == "The picked face"
    assert items[1].label == "Sketch on this face"
    # a right click on another body: that body's menu only
    other = bm.body_items(p.model, 2, p.part_files, p)
    assert not any(i.label == "Sketch on this face" for i in other)
    # without the processor (older callers) the menu is as before
    assert bm.body_items(p.model, 1)[0].label.startswith("body 1")


def test_tools_command_and_the_assistant_agree():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nPICK, EDGE, 1")
    text = ok(p, "TOOLS").message
    assert text.startswith("1 edge picked") and "Loop round its face: SEL, S, EDGE, LOOP, 1" in text
    data = json.loads(ok(p, "TOOLS, JSON").message)
    got = Toolbox(p).call("suggest_tools", {})
    assert data["tools"] == got["tools"] and got["selection"] == {"kind": "EDGE", "ids": [1]}
    assert got["tools"][0] == {"label": "Fillet…", "form": "FILLET",
                               "runs": "FILLET, ... (its form opens, filled in from the pick)"}
    assert bm.tools_rows(Processor()) == []


def test_fillet_its_edges_picks_the_edges_first():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40,20,10\nPICK, FACE, 6")
    item = next(i for i in bm.pick_tools(p) if i.label == "Fillet its edges…")
    ok(p, item.first[0])
    assert p.model.selection_kind == "EDGE" and len(sel(p)) == 4
    ok(p, "FILLET, 2")
