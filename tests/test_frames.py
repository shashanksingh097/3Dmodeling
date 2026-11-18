"""Frames and weldments: MEMBER and CUTLIST (geometry/frames.py)."""

import pytest

from modeler.commands import Processor
from modeler.geometry import frames as fr
from modeler.geometry import robust

RECT = [(0, 0, 0), (100, 0, 0), (100, 60, 0), (0, 60, 0)]


def run(p, *lines):
    for line in lines:
        r = p.run(line)
        assert r.ok, (line, r.message)
    return r


@pytest.mark.parametrize("profile, size", [("SQUARE", (40, 3)), ("RECT", (40, 20, 2)), ("ROUND", (30, 2)),
                                           ("FLAT", (40, 5)), ("ANGLE", (30, 30, 3)), ("CHANNEL", (40, 30, 3)),
                                           ("IBEAM", (40, 60, 4))])
def test_mitred_rectangle_frame(profile, size):
    ms = fr.members(RECT, True, profile, size)
    assert len(ms) == 4
    for shape, rec in ms:
        assert robust.checked_ok(shape, True)
        assert rec.end_angles() == (45.0, 45.0)
    # the outside length of each mitred piece is the side plus the profile's width across the corner
    xs = [u for u, _v in fr.outline(profile, size)[0]] if profile != "ROUND" else [-size[0] / 2, size[0] / 2]
    w = max(xs) - min(xs)
    assert sorted(round(rec.length, 6) for _s, rec in ms) == pytest.approx([60 + w, 60 + w, 100 + w, 100 + w])


def test_mitred_square_tube_volume():
    ms = fr.members(RECT, True, "SQUARE", (40, 3))
    area = 40 * 40 - 34 * 34
    # mitred corners: each piece is a trapezoid prism, together exactly the centre line's length
    assert sum(robust.volume(s) for s, _r in ms) == pytest.approx(area * 320, rel=1e-9)


@pytest.mark.parametrize("profile, size, half", [("SQUARE", (40, 3), 20), ("IBEAM", (40, 60, 4), 20),
                                                 ("ROUND", (30, 2), 15)])
def test_butt_corners_run_through_and_stop(profile, size, half):
    ms = fr.members(RECT[:3], False, profile, size, "BUTT")
    (s1, r1), (s2, r2) = ms
    assert r1.length == pytest.approx(100 + half, abs=0.05)  # runs past the corner to the far side of the next
    if profile == "ROUND":
        assert r2.length == pytest.approx(60, abs=0.05)  # coped: the saddle's tips reach back to the joint
    else:
        assert r2.length == pytest.approx(60 - half, abs=1e-6)  # stops at the first one's side
    assert robust.checked_ok(s1, True) and robust.checked_ok(s2, True)
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common

    assert robust.volume(BRepAlgoAPI_Common(s1, s2).Shape()) == pytest.approx(0, abs=1e-6)  # no overlap


def test_sizes_are_checked():
    with pytest.raises(fr.FrameError):
        fr.parse_size("SQUARE", "40x30x3")
    with pytest.raises(fr.FrameError):
        fr.parse_size("SQUARE", "40x25")
    with pytest.raises(fr.FrameError):
        fr.parse_size("TEE", "40x3")
    assert fr.parse_size("RECT", "60 x 40 x 0") == (60, 40, 0)


def test_member_and_cutlist_commands(tmp_path):
    p = Processor()
    run(p, "POLYLINE, (0,0,0), (100,0,0), (100,60,0), (0,60,0), CLOSE", "NAME, LAST, frame",
        "MEMBER, frame, SQUARE, 40x3", "POLYLINE, (0,0,0), (0,0,80), (60,0,80)",
        "MEMBER, LAST, IBEAM, 30x50x4, BUTT, post, 90")
    names = {b.name for b in p.model.bodies.values()}
    assert {"member_1", "member_4", "post_1", "post_2"} <= names
    f = tmp_path / "cuts.csv"
    msg = run(p, f'CUTLIST, "{f}"').message
    assert "2  SQUARE   40x3" in msg and "140.0" in msg and "45° / 45°" in msg
    assert "post_1" in msg
    rows = f.read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("qty,profile") and len(rows) == 5
    # a hole drilled in a member keeps it on the cut list
    run(p, "CYL, 50, 0, -30, 5, 60", "SUBTRACT, member_1, LAST")
    assert "member_1" in run(p, "CUTLIST").message
    # turn 90: the I-beam's 50 height lies in the frame's plane, so the post stops 25 short
    post2 = p.model.members[p.model.body_by_name("post_2").id]
    assert post2.length == pytest.approx(60 - 25, abs=1e-6)


def test_member_errors():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 1,1,1")
    assert "not a path" in p.run("MEMBER, 1, SQUARE, 40x3").message
    run(p, "CURVE, PARAM, 10*cos(t), 10*sin(t), 0, 0, 3")
    assert "straight" in p.run("MEMBER, LAST, SQUARE, 4x1").message
    assert not p.run("MEMBER, 2, SQUARE, 4x1, ROUNDED").ok
