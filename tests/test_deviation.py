"""Scan to CAD with numbers (PLAN item 55): DEVIATION from a scan to its model, overall and per
face, with outliers, holes and low-confidence faces; the colours; RECONSTRUCT checks itself."""

import json

import numpy as np
import pytest

from modeler.commands import Processor
from modeler.geometry import deviation as dv
from modeler.geometry import meshbody as mb


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    res = p.run_script(text)
    bad = [r for r in res if not r.ok]
    assert not bad, f"{bad[0].line}: {bad[0].message}"
    return res[-1]


def scan_of_block(p, noise=0.0, lift_top=0.0, hole=False, stray=0, seed=0):
    """Body 1: the model (a 20 x 10 x 5 block). Body 2: a 'scan' of it, as a mesh body, with noise,
    the top face lifted, a hole cut in the mesh and stray points if asked."""
    ok(p, "BLOCK, 0,0,0, 20,10,5\nBLOCK, 0,0,0, 20,10,5\nTOMESH, 2, 0.01\nREMESH, 2, 0.5")
    pts, t = mb.arrays(p.model.bodies[2].shape)
    pts, t = np.array(pts, float), np.array(t)
    rng = np.random.default_rng(seed)
    q = pts + rng.normal(0, noise, pts.shape) if noise else pts.copy()
    q[pts[:, 2] > 4.99, 2] += lift_top
    if hole:  # take the triangles round the middle of the front face away
        c = q[t].mean(axis=1)
        t = t[~((np.abs(c[:, 1]) < 1e-6) & (np.abs(c[:, 0] - 10) < 2) & (np.abs(c[:, 2] - 2.5) < 1.5))]
    if stray:
        far = np.array([[10, 5, 12.0]]) + rng.normal(0, 0.1, (stray, 3))
        base = len(q)
        q = np.vstack([q, far, far + [0.3, 0, 0], far + [0, 0.3, 0]])
        t = np.vstack([t, np.stack([base + np.arange(stray), base + stray + np.arange(stray),
                                    base + 2 * stray + np.arange(stray)], 1)])
    from modeler.commands.mesh_handlers import _swap

    _swap(p, 2, q, t, "test scan")
    return q, t


def test_an_exact_scan_is_within_tolerance(p):
    scan_of_block(p)
    d = json.loads(p.run("DEVIATION, 2, 1, 0.01, JSON").message)
    assert d["met"] and d["within"] == 1.0 and d["rms"] < 1e-6
    assert d["outliers"] == 0 and d["holes"] == [] and d["low_confidence"] == []
    assert len(d["faces"]) == 6 and all(f["covered"] > 0.95 for f in d["faces"])
    assert "tolerance met" in p.run("DEVIATION, 2, 1, 0.01").message


def test_a_face_that_is_off_shows_by_name(p):
    scan_of_block(p, noise=0.005, lift_top=0.08)
    d = json.loads(p.run("DEVIATION, 2, 1, 0.05, JSON").message)
    assert not d["met"]
    assert d["largest_out"] == pytest.approx(0.08, abs=0.03) and d["largest_in"] > -0.03
    rows = {f["face"]: f for f in d["faces"]}
    top = max(rows.values(), key=lambda f: abs(f["worst"]) * (1 - f["within"]))
    # the top face (z = 5) is the one off, and it is off outward
    assert top["within"] < 0.1 and top["worst"] > 0
    assert sum(1 for f in rows.values() if f["within"] > 0.9) >= 5
    msg = p.run("DEVIATION, 2, 1, 0.05").message
    assert f"face {top['face']}:" in msg and "faces off the tolerance" in msg
    # the rest of the numbers
    assert 0 < d["rms"] < 0.08 and d["points"] > 1000


def test_outliers_holes_and_low_confidence(p):
    scan_of_block(p, hole=True, stray=30)
    d = json.loads(p.run("DEVIATION, 2, 1, 0.02, JSON").message)
    assert d["outliers"] == 90 and d["outlier_worst"][3] > 5
    assert d["met"]  # stray points are left out of the numbers
    assert len(d["holes"]) == 1 + 30  # the hole, and each stray triangle's rim
    big = d["holes"][0]
    assert big["centre"][1] == pytest.approx(0, abs=1e-6) and big["length"] > 6
    msg = p.run("DEVIATION, 2, 1, 0.02").message
    assert "outliers: 90 points" in msg and "holes in the scan" in msg


def test_a_face_the_scan_misses_is_low_confidence(p):
    q, t = scan_of_block(p)
    c = q[t].mean(axis=1)
    from modeler.commands.mesh_handlers import _swap

    _swap(p, 2, q, t[c[:, 2] < 4.99], "no top")  # the scan never saw the top
    d = json.loads(p.run("DEVIATION, 2, 1, 0.02, JSON").message)
    rows = {f["face"]: f for f in d["faces"]}
    assert len(d["low_confidence"]) == 1
    top = rows[d["low_confidence"][0]]
    assert top["covered"] < 0.2
    assert "low confidence" in p.run("DEVIATION, 2, 1, 0.02").message


def test_signed_distances_are_right():
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere

    ball = BRepPrimAPI_MakeSphere(10.0).Shape()
    tg = dv.target(ball, 0.002)
    q = np.array([[10.5, 0, 0], [0, 9.7, 0], [0, 0, -12.0], [3, 4, 0]])
    d, _ = dv.distances(tg, q)
    assert d == pytest.approx([0.5, -0.3, 2.0, -5.0], abs=0.003)


def test_colours_follow_the_bands():
    c = dv.band_colours(np.array([0.0, 0.009, 0.02, -0.02, 0.05, -0.05]), 0.01)
    green = (0.25, 0.75, 0.3)
    assert tuple(c[0]) == green and tuple(c[1]) == green
    assert c[2][0] > 0.8 and c[2][2] < 0.3  # out: yellow to red
    assert c[3][2] > 0.8 and c[3][0] < 0.3  # in: cyan to blue
    assert tuple(c[4]) == (0.85, 0.2, 0.85) and tuple(c[5]) == (0.1, 0.1, 0.45)


def test_deviation_colours_the_scan_in_the_view(p):
    scan_of_block(p, lift_top=0.05)
    shown = []

    class View:
        def show_analysis(self, a):
            shown.append(a)

    p.view = View()
    ok(p, "DEVIATION, 2, 1, 0.02")
    a = shown[-1]
    assert a.body == 2 and a.mode == "DEVIATION" and a.scale == 0.02
    from modeler.geometry import analysis as an

    m = an.mesh(p.model.bodies[2].shape)
    rgb = an.colours(m, a.mode, field=a.field, scale=a.scale)
    top = m.nodes[:, 2] > 5.04
    assert (rgb[top][:, 0] > 0.8).all() and (rgb[~top] == (0.25, 0.75, 0.3)).all(axis=1).mean() > 0.9


def test_deviation_refuses_what_it_cannot_measure(p):
    ok(p, "BLOCK, 0,0,0, 1,1,1\nSPHERE, 5,0,0, 1\nTOMESH, 2")
    assert "same body" in p.run("DEVIATION, 1, 1").message
    assert "mesh body" in p.run("DEVIATION, 1, 2").message


def test_reconstruct_says_how_close_it_came(p):
    ok(p, "BLOCK, 0,0,0, 20,10,5\nCYL, 10,5,5, 2, 3\nUNION, 1, 2\nTOMESH, LAST, 0.01")
    r = ok(p, "RECONSTRUCT, LAST")
    assert "the mesh is within" in r.message and "100.0% of its points" in r.message
