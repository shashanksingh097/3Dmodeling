"""Mesh bodies (M6 part 1): TOMESH, TOSOLID, mesh booleans, SMOOTH, REMESH, SIMPLIFY."""

import math
import struct

import numpy as np
import pytest

from modeler.commands import Processor
from modeler.geometry import meshbody as mb


def run(p, text):
    out = p.run_script(text)
    bad = [r for r in out if not r.ok]
    assert not bad, bad[0].message
    return out[-1].message


def vol(p, b):
    return mb.info(p.model.body(b).shape).volume


def write_stl(path, pts, t):
    rec = np.zeros(len(t), dtype=[("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["v"] = pts[t]
    with open(path, "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(t)) + rec.tobytes())


def test_mesh_shape_round_trip():
    pts, t = mb.sphere(10, 64)
    shape = mb.make_shape(pts, t)
    assert mb.is_mesh(shape)
    mb._CACHE.clear()  # read back from the OCCT triangulation, not the cache
    p2, t2 = mb.arrays(shape)
    assert len(t2) == len(t) and mb.info(shape).closed
    assert mb.info(shape).volume == pytest.approx(4 / 3 * math.pi * 1000, rel=0.01)


def test_sharp_edges_are_split_for_shading_only():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 10,10,10\nTOMESH, 1")
    pts, t = mb.arrays(p.model.body(1).shape)
    assert len(pts) == 8  # the model's mesh is closed; only the drawn copy has 24 corners
    shown, _ = mb.split_sharp(pts, t)
    assert len(shown) == 24


def test_tomesh_keeps_id_and_volume_and_tosolid_goes_back():
    p = Processor()
    msg = run(p, "CYL, 0,0,0, 5, 20\nNAME, LAST, pin\nTOMESH, pin")
    assert "mesh" in msg and "triangles" in msg
    assert p.model.body_by_name("pin").id == 1
    assert len(p.model.body(1).entity_ids["FACE"]) == 1
    assert vol(p, 1) == pytest.approx(math.pi * 25 * 20, rel=0.005)
    run(p, "TOSOLID, pin")
    assert not mb.is_mesh(p.model.body(1).shape)
    assert len(p.model.body(1).entity_ids["FACE"]) > 20


def test_mesh_booleans_with_solids_and_meshes():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 40,40,40\nTOMESH, 1\nSPHERE, 20,20,40, 15\nSUBTRACT, 1, 2")
    b = p.model.last_body
    assert mb.is_mesh(p.model.body(b).shape)
    assert vol(p, b) == pytest.approx(64000 - 2 / 3 * math.pi * 15 ** 3, rel=0.01)
    run(p, f"BLOCK, 0,0,30, 10,10,20\nUNION, {b}, LAST")
    u = p.model.last_body
    assert mb.info(p.model.body(u).shape).closed
    run(p, f"BLOCK, 2,2,2, 10,10,10\nINTERSECT, {u}, LAST")
    assert vol(p, p.model.last_body) == pytest.approx(1000, rel=1e-6)


def test_mesh_boolean_errors_and_warnings():
    p = Processor()
    run(p, "SPHERE, 0,0,0, 5\nTOMESH, 1\nSPHERE, 100,0,0, 5")
    out = p.run_script("INTERSECT, 1, 2")[-1]
    assert not out.ok and "nothing is left" in out.message
    out = p.run_script("UNION, 1, 2")[-1]
    assert out.ok and "separate pieces" in out.warning


def test_commands_that_need_faces_refuse_a_mesh_body_with_advice():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 10,10,10\nTOMESH, 1")
    out = p.run_script("HOLE, 1, 5,5,10, 2")[-1]
    assert not out.ok and "mesh body" in out.message and "TOSOLID" in out.message
    # a picked face of a mesh body cannot be reached by a command that needs real faces
    fid = p.model.body(1).entity_ids["FACE"][0]
    run(p, f"PICK, FACE, {fid}")
    out = p.run_script("PUSHPULL, 2")[-1]
    assert not out.ok, out.message
    from modeler.core.model import ModelError

    p.model.mesh_entities_ok = False  # what the processor sets while such a command runs
    with pytest.raises(ModelError, match="surface of mesh body 1"):
        p.model.entity_shape("FACE", fid)
    p.model.mesh_entities_ok = True
    assert "OK (mesh body" in run(p, "CHECK, 1")


def test_clash_dist_and_probe_measure_mesh_bodies():
    p = Processor()
    run(p, "SPHERE, 0,0,0, 10\nTOMESH, 1\nBLOCK, 20,0,0, 5,5,5\nSPHERE, 5,0,0, 8\nTOMESH, 3")
    assert "OVERLAP" in run(p, "CLASH, 1, 3")  # two mesh bodies (the kernel's own boolean would crash here)
    assert "gap 10.0" in run(p, "CLASH, 1, 2")
    assert "distance 10.0" in run(p, "DIST, BODY, 1, BODY, 2")
    assert "inside body 1" in run(p, "PROBE, POINT, 0,0,0")


def test_transforms_and_deformers_keep_a_mesh_a_mesh():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 10,10,40\nTOMESH, 1\nREMESH, 1, 2\nMOVE, 1, 5\nCOPY, 1, 0, 30\n"
           "MIRROR, 1, 0,0,0, 1,0,0\nTWIST, 1, 90, Z")
    for b in p.model.bodies:
        assert mb.is_mesh(p.model.body(b).shape)
        assert vol(p, b) == pytest.approx(4000, rel=0.02)
    mirrored = mb.arrays(p.model.body(3).shape)[0]
    assert mirrored[:, 0].max() == pytest.approx(-5, abs=1e-6)


def test_smooth_keeps_size_and_splits_long_triangles():
    p = Processor()
    msg = run(p, "BLOCK, 0,0,0, 40,40,40\nTOMESH, 1\nSPHERE, 20,20,40, 15\nSUBTRACT, 1, 2\nSMOOTH, LAST")
    assert "split first" in msg
    b = p.model.last_body
    assert vol(p, b) == pytest.approx(64000 - 2 / 3 * math.pi * 15 ** 3, rel=0.02)
    # noise on a sphere goes away
    pts, t = mb.sphere(10, 128)
    noisy = pts + np.random.default_rng(1).normal(0, 0.2, pts.shape)
    smooth = mb.smooth(noisy, t, 10)
    err = lambda q: np.abs(np.linalg.norm(q, axis=1) - 10).max()  # noqa: E731
    assert err(smooth) < 0.5 * err(noisy)


def test_remesh_and_simplify():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 20,20,20\nTOMESH, 1")
    n0 = mb.info(p.model.body(1).shape).triangles
    run(p, "REMESH, 1, 1")
    n1 = mb.info(p.model.body(1).shape).triangles
    assert n1 > 50 * n0
    assert vol(p, 1) == pytest.approx(8000, rel=1e-9)
    run(p, "SIMPLIFY, 1, 0.01")
    assert mb.info(p.model.body(1).shape).triangles < n1 / 10
    assert vol(p, 1) == pytest.approx(8000, rel=1e-9)
    assert not p.run_script("REMESH, 1, 0.0001")[-1].ok  # far too many triangles: refused


def test_import_kind_mesh_and_auto(tmp_path):
    pts, t = mb.sphere(10, 64)
    path = tmp_path / "ball.stl"
    write_stl(str(path), pts, t)
    p = Processor()
    run(p, f'IMPORT, STL, "{path}", ball, MESH')
    assert mb.is_mesh(p.model.body_by_name("ball").shape)
    run(p, f'IMPORT, STL, "{path}"')  # small: a faceted solid as before
    assert not mb.is_mesh(p.model.body(p.model.last_body).shape)


def test_export_of_mesh_bodies(tmp_path):
    p = Processor()
    run(p, "SPHERE, 0,0,0, 10\nTOMESH, 1")
    run(p, f'EXPORT, STL, "{tmp_path / "a.stl"}", 1')
    run(p, f'EXPORT, OBJ, "{tmp_path / "a.obj"}", 1')
    assert (tmp_path / "a.stl").stat().st_size > 1000 and (tmp_path / "a.obj").stat().st_size > 1000
    out = p.run_script(f'EXPORT, STEP, "{tmp_path / "a.step"}", 1')[-1]
    assert not out.ok and "TOSOLID" in out.message


def test_massprop_and_describe_know_mesh_bodies():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 10,10,10\nTOMESH, 1")
    assert "volume 1000" in run(p, "MASSPROP, 1")
    assert "representation: mesh" in run(p, "DESCRIBE, 1")


def test_mesh_bodies_replay_after_a_history_edit():
    p = Processor()
    run(p, "R = 10\nSPHERE, 0,0,0, R\nTOMESH, 1\nBLOCK, -20,-20,0, 40,40,20\nSUBTRACT, 1, 2")
    v = vol(p, p.model.last_body)
    assert v == pytest.approx(2 / 3 * math.pi * 1000, rel=0.02)
    run(p, "HIST, EDIT, 1, R = 12")
    assert vol(p, p.model.last_body) == pytest.approx(2 / 3 * math.pi * 12 ** 3, rel=0.02)


def test_example_script_runs():
    import os

    here = os.path.join(os.path.dirname(__file__), "..", "scripts", "mesh_bodies.cmd")
    p = Processor()
    with open(here, encoding="utf-8") as f:
        run(p, f.read())
    assert {"shade", "pebble", "bar"} <= {b.name for b in p.model.bodies.values()}
