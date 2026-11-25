"""PLAN item 77: point clouds: files, thinning, FITPOINTS fits, DEVIATION on points."""

import json
import math
import struct

import numpy as np
import pytest

from modeler.commands import Processor
from modeler.geometry import pointcloud as pc


def ok(p, line):
    r = p.run(line)
    assert r.ok, r.message
    return r


def _cyl(n=3000, seed=1, arc=2.1, noise=0.01):
    rng = np.random.default_rng(seed)
    u, h = rng.uniform(0, arc, n), rng.uniform(0, 30, n)
    return np.c_[10 * np.cos(u), 10 * np.sin(u), h] + rng.normal(0, noise, (n, 3))


# ---- files ------------------------------------------------------------------------------------
def test_xyz_pts_and_csv(tmp_path):
    pts = _cyl(50)
    (tmp_path / "a.xyz").write_text("# x y z\n" + "\n".join(f"{x} {y} {z} 255 0 0" for x, y, z in pts))
    (tmp_path / "a.pts").write_text(f"{len(pts)}\n" + "\n".join(f"{x} {y} {z} 12" for x, y, z in pts))
    (tmp_path / "a.csv").write_text("x,y,z\n" + "\n".join(f"{x},{y},{z}" for x, y, z in pts))
    for name in ("a.xyz", "a.pts", "a.csv"):
        assert np.allclose(pc.read(str(tmp_path / name)), pts)


def test_ply_ascii_and_binary(tmp_path):
    pts = _cyl(40)
    head = "ply\nformat {}\nelement vertex {}\nproperty float x\nproperty float y\nproperty float z\n" \
           "property uchar red\nend_header\n"
    (tmp_path / "a.ply").write_text(head.format("ascii 1.0", len(pts)) + "\n".join(f"{x} {y} {z} 7" for x, y, z in pts))
    body = b"".join(struct.pack("<fffB", *map(float, q), 7) for q in pts)
    (tmp_path / "b.ply").write_bytes(head.format("binary_little_endian 1.0", len(pts)).encode() + body)
    for name in ("a.ply", "b.ply"):
        got, faces = pc.read_ply(str(tmp_path / name))
        assert faces == 0 and np.allclose(got, pts, atol=1e-4)


def test_e57_floats_scaled_and_pose(tmp_path):
    pts = _cyl(4500)
    pc.write_e57(str(tmp_path / "a.e57"), pts)
    assert np.allclose(pc.read(str(tmp_path / "a.e57")), pts)
    w, z = math.cos(0.5), math.sin(0.5)  # 1 radian about Z, then moved
    pc.write_e57(str(tmp_path / "b.e57"), pts[:500], scaled=0.001, pose=((w, 0, 0, z), (1, 2, 3)))
    got = pc.read(str(tmp_path / "b.e57"))
    c, s = math.cos(1), math.sin(1)
    want = pts[:500] @ np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]).T + [1, 2, 3]
    assert np.abs(got - want).max() < 1e-3


def test_bad_files(tmp_path):
    (tmp_path / "x.xyz").write_text("1 2 3\nhello there\n")
    with pytest.raises(pc.CloudError):
        pc.read(str(tmp_path / "x.xyz"))
    (tmp_path / "x.e57").write_bytes(b"not e57" * 100)
    with pytest.raises(pc.CloudError):
        pc.read(str(tmp_path / "x.e57"))


def test_thin_keeps_an_even_spread():
    rng = np.random.default_rng(0)
    pts = np.c_[rng.uniform(0, 100, (300_000, 2)), np.zeros(300_000)]
    got = pc.thin(pts, 50_000)
    assert 20_000 < len(got) <= 50_000
    assert np.allclose(got.min(axis=0)[:2], 0, atol=2) and np.allclose(got.max(axis=0)[:2], 100, atol=2)


# ---- fits -------------------------------------------------------------------------------------
def test_each_kind_of_fit():
    rng = np.random.default_rng(2)
    cyl = _cyl()
    f = pc.fit(cyl, "AUTO", 0.05)
    assert f.kind == "CYLINDER" and abs(f.params["radius"] - 10) < 0.01
    assert abs(abs(f.params["axis"][2]) - 1) < 1e-3
    u, h = rng.uniform(0, 3, 3000), rng.uniform(0, 30, 3000)
    r = 5 + h * math.tan(math.radians(15))
    f = pc.fit(np.c_[r * np.cos(u), r * np.sin(u), h], "AUTO", 0.05)
    assert f.kind == "CONE" and abs(f.params["angle"] - 15) < 0.05
    v = rng.normal(size=(3000, 3))
    v = v / np.linalg.norm(v, axis=1)[:, None]
    f = pc.fit(v[v[:, 2] > 0.3] * 7 + [1, 2, 3], "AUTO", 0.05)
    assert f.kind == "SPHERE" and abs(f.params["radius"] - 7) < 1e-6
    f = pc.fit(np.c_[rng.uniform(0, 50, 2000), rng.uniform(0, 20, 2000), rng.normal(0, 0.01, 2000)], "AUTO", 0.05)
    assert f.kind == "PLANE" and f.rms < 0.02
    x, y = rng.uniform(-10, 10, (2, 3000))
    f = pc.fit(np.c_[x, y, 0.02 * (x * x - y * y)], "FREEFORM", 0.01)
    assert f.kind == "FREEFORM" and f.worst < 0.02


def test_too_few_points():
    with pytest.raises(pc.CloudError, match="too few"):
        pc.fit(np.zeros((3, 3)), "PLANE", 0.1)


# ---- commands ---------------------------------------------------------------------------------
@pytest.fixture
def scan():
    p = Processor()
    ok(p, "CYL, 0,0,0, 10, 30")
    ok(p, "NAME, LAST, part")
    r = ok(p, "TOPOINTS, part, 20000, 0.01")
    assert "(20,000 points)" in r.message
    ok(p, "NAME, LAST, scan")
    return p


def test_fitpoints_patch_and_report(scan):
    p = scan
    r = ok(p, "FITPOINTS, scan, CYLINDER, 10, 0, 15, 8")
    assert "cylinder, radius 9.99" in r.message or "cylinder, radius 10" in r.message
    assert "tolerance met" in r.message
    new = p.model.bodies[max(p.model.bodies)]
    assert len(new.entity_ids["FACE"]) == 1
    d = json.loads(ok(p, "FITPOINTS, scan, AUTO, 0, 0, 30, 6, 0, JSON").message)
    assert d["kind"] == "PLANE" and d["met"] and abs(d["fit"]["origin"][2] - 30) < 0.01
    assert p.reports["FITPOINTS"]["kind"] == "PLANE"


def test_fitpoints_refusals(scan):
    p = scan
    assert "not a point body" in p.run("FITPOINTS, part").message
    assert "only 0 points" in p.run("FITPOINTS, scan, AUTO, 100, 100, 100, 1").message
    assert "kind is one of" in p.run("FITPOINTS, scan, BOX").message


def test_deviation_of_points(scan):
    r = ok(scan, "DEVIATION, scan, part, 0.02")
    assert "tolerance met" in r.message and "low confidence" not in r.message


def test_import_points_save_and_open(scan, tmp_path):
    p = scan
    pts = pc.arrays(p.model.body_by_name("scan").shape)
    pc.write_e57(str(tmp_path / "s.e57"), pts[:3000])
    np.savetxt(tmp_path / "s.xyz", pts[:2000])
    assert "(3,000 points)" in ok(p, f'IMPORT, E57, "{tmp_path / "s.e57"}", e').message
    assert "(2,000 points)" in ok(p, f'IMPORT, XYZ, "{tmp_path / "s.xyz"}"').message
    ok(p, f'SAVE, "{tmp_path / "p.m3d"}"')
    q = Processor()
    ok(q, f'OPEN, "{tmp_path / "p.m3d"}"')
    assert len(q.model.body_by_name("e").entity_ids["VERTEX"]) == 3000
    assert pc.is_points(q.model.body_by_name("e").shape)


def test_import_thins_big_clouds(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "MOST_POINTS", 1000)
    p = Processor()
    np.savetxt(tmp_path / "big.xyz", _cyl(5000))
    r = ok(p, f'IMPORT, XYZ, "{tmp_path / "big.xyz"}"')
    assert "thinned evenly" in r.message
    assert len(next(iter(p.model.bodies.values())).entity_ids["VERTEX"]) <= 1000


def test_describe_and_menu_know_point_bodies(scan):
    from modeler.ai import describe
    from modeler.gui import body_menu as bm

    p = scan
    bid = p.model.body_by_name("scan").id
    d = describe.describe_body(p, "scan")
    assert d["kind"] == "points" and d["representation"] == "points" and d["points"]["count"] == 20000
    labels = [i.label for i in bm.body_items(p.model, bid)]
    assert "Fit a shape to all the points…" in labels
    vid = sorted(p.model.bodies[bid].entity_ids["VERTEX"])[0]
    p.model.selection_kind, p.model.selection = "VERTEX", [vid]
    items = {i.label: i for i in bm.body_items(p.model, bid)}
    cmd = items["Fit a shape to the points around the pick…"].commands[0]
    assert cmd.startswith(f"FITPOINTS, {bid}, AUTO, ")
    assert ok(p, cmd).ok
