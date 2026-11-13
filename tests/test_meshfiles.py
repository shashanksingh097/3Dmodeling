"""Import and export of mesh formats: OBJ, 3MF, glTF, PLY, OFF, VTK and simulation meshes; IGES export."""

import json
import zipfile

import meshio
import numpy as np
import pytest

from modeler.commands import Processor
from modeler.commands import project_handlers
from modeler.geometry import meshfiles


def ok(p, text):
    r = p.run(text)
    assert r.ok, r.message
    return r.message


def err(p, text):
    r = p.run(text)
    assert not r.ok, r.message
    return r.message


def vols(p):
    return [p.evaluate(f"VOL({b})") for b in p.model.bodies]


TWO = "BLOCK, 0,0,0, 10,20,30\nCOLOR, LAST, 200,30,30\nNAME, LAST, box\nBLOCK, 50,0,0, 4,4,4"


def _box_grid(nx=4, ny=3, nz=2):
    """Points and hexahedra of an nx by ny by nz box of unit cells."""
    def idx(i, j, k):
        return i + (nx + 1) * (j + (ny + 1) * k)

    pts = np.array([(i, j, k) for k in range(nz + 1) for j in range(ny + 1) for i in range(nx + 1)], float)
    hexes = np.array([[idx(i, j, k), idx(i + 1, j, k), idx(i + 1, j + 1, k), idx(i, j + 1, k),
                       idx(i, j, k + 1), idx(i + 1, j, k + 1), idx(i + 1, j + 1, k + 1), idx(i, j + 1, k + 1)]
                      for k in range(nz) for j in range(ny) for i in range(nx)])
    return pts, hexes


def _tets(hexes):
    out = []
    for a, b, c, d, e, f, g, h in hexes:
        out += [(a, b, c, g), (a, c, d, g), (a, d, h, g), (a, h, e, g), (a, e, f, g), (a, f, b, g)]
    return np.array(out)


# ---- round trips ----------------------------------------------------------------------
@pytest.mark.parametrize("fmt,ext", [("IGES", "igs"), ("STL", "stl"), ("OBJ", "obj"), ("3MF", "3mf"),
                                     ("GLTF", "glb"), ("GLTF", "gltf")])
def test_export_then_import_keeps_both_bodies(tmp_path, fmt, ext):
    p = Processor()
    f = tmp_path / f"two.{ext}"
    ok(p, f'{TWO}\nEXPORT, {fmt}, "{f}"')
    q = Processor()
    msg = ok(q, f'IMPORT, {fmt}, "{f}", part')
    assert "2 bodies" in msg
    assert sorted(vols(q)) == pytest.approx([64, 6000], rel=1e-6)
    assert q.model.body_by_name("part") is not None


def test_exact_sphere_comes_back_faceted_but_close(tmp_path):
    p = Processor()
    f = tmp_path / "ball.obj"
    ok(p, f'SPHERE, 0,0,0, 10\nEXPORT, OBJ, "{f}"')
    q = Processor()
    msg = ok(q, f'IMPORT, OBJ, "{f}", ball')
    assert "triangles" in msg and "open" not in msg
    assert q.evaluate("VOL(ball)") == pytest.approx(4 / 3 * np.pi * 1000, rel=0.03)  # facets cut inside
    # a faceted body still takes booleans
    ok(q, "BLOCK, 0,-20,-20, 20,40,40\nSUBTRACT, ball, LAST")
    assert q.evaluate("VOL(ball)") == pytest.approx(2 / 3 * np.pi * 1000, rel=0.03)


def test_export_one_body(tmp_path):
    p = Processor()
    f = tmp_path / "one.3mf"
    ok(p, f'{TWO}\nEXPORT, 3MF, "{f}", box')
    q = Processor()
    ok(q, f'IMPORT, 3MF, "{f}"')
    assert vols(q) == pytest.approx([6000])


def test_names_and_colours_are_written(tmp_path):
    p = Processor()
    ok(p, f'{TWO}\nEXPORT, OBJ, "{tmp_path}/m.obj"\nEXPORT, 3MF, "{tmp_path}/m.3mf"\n'
          f'EXPORT, GLTF, "{tmp_path}/m.gltf"')
    obj = (tmp_path / "m.obj").read_text()
    assert "o box" in obj and "mtllib m.mtl" in obj
    assert "Kd 0.7843 0.1176 0.1176" in (tmp_path / "m.mtl").read_text()
    model = zipfile.ZipFile(tmp_path / "m.3mf").read("3D/3dmodel.model").decode()
    assert 'unit="millimeter"' in model and 'name="box"' in model and "#C81E1E" in model
    doc = json.loads((tmp_path / "m.gltf").read_text())
    assert [n["name"] for n in doc["nodes"]][0] == "box"
    assert doc["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"][:3] == pytest.approx(
        [200 / 255, 30 / 255, 30 / 255])


def test_gltf_is_in_metres_and_y_up(tmp_path):
    p = Processor()
    f = tmp_path / "box.gltf"
    ok(p, f'BLOCK, 0,0,0, 10,20,30\nEXPORT, GLTF, "{f}"')
    acc = json.loads(f.read_text())["accessors"][0]
    assert acc["max"] == pytest.approx([0.010, 0.030, 0.0])  # z (30 mm) is up
    assert acc["min"] == pytest.approx([0.0, 0.0, -0.020])


def test_units_carry_over_in_3mf_and_gltf(tmp_path):
    p = Processor()
    ok(p, f'/UNITS, CM\nBLOCK, 0,0,0, 1,2,3\nEXPORT, 3MF, "{tmp_path}/c.3mf"\nEXPORT, GLTF, "{tmp_path}/c.glb"')
    for f, fmt in (("c.3mf", "3MF"), ("c.glb", "GLTF")):
        q = Processor()  # millimetres
        ok(q, f'IMPORT, {fmt}, "{tmp_path / f}"')
        assert vols(q) == pytest.approx([6000], rel=1e-5)


# ---- mesh files from other tools --------------------------------------------------------
@pytest.mark.parametrize("name,fmt,kind", [("hex.vtu", "VTK", "hexahedron"), ("tet.vtk", "VTK", "tetra"),
                                           ("tet.msh", "MESH", "tetra"), ("hex.inp", "MESH", "hexahedron")])
def test_volume_meshes_keep_their_outer_skin(tmp_path, name, fmt, kind):
    pts, hexes = _box_grid()
    cells = hexes if kind == "hexahedron" else _tets(hexes)
    f = tmp_path / name
    extra = {"file_format": "gmsh22", "binary": False} if name.endswith(".msh") else {}
    meshio.write(f, meshio.Mesh(pts, [(kind, cells)]), **extra)
    q = Processor()
    msg = ok(q, f'IMPORT, {fmt}, "{f}", block')
    assert "open" not in msg
    assert vols(q) == pytest.approx([24])
    assert q.model.body_by_name("block") is not None


@pytest.mark.parametrize("ext,fmt", [("ply", "PLY"), ("off", "OFF"), ("obj", "OBJ"), ("vtk", "VTK")])
def test_surface_meshes(tmp_path, ext, fmt):
    pts, hexes = _box_grid()
    tris = meshfiles.surface_of(pts, [("hexahedron", hexes)])
    f = tmp_path / f"skin.{ext}"
    meshio.write(f, meshio.Mesh(pts, [("triangle", tris)]))
    q = Processor()
    ok(q, f'IMPORT, {fmt}, "{f}"')
    assert vols(q) == pytest.approx([24])


def test_quads_and_inward_triangles(tmp_path):
    pts, hexes = _box_grid(2, 2, 2)
    tris = meshfiles.surface_of(pts, [("hexahedron", hexes)])
    f = tmp_path / "inside_out.obj"
    meshio.write(f, meshio.Mesh(pts, [("triangle", tris[:, [0, 2, 1]])]))
    q = Processor()
    ok(q, f'IMPORT, OBJ, "{f}"')
    assert vols(q) == pytest.approx([8])  # turned the right way out

    quads = np.array([[0, 1, 4, 3]])  # one quad of the bottom layer: an open surface
    g = tmp_path / "quad.ply"
    meshio.write(g, meshio.Mesh(pts, [("quad", quads)]))
    r = Processor()
    msg = ok(r, f'IMPORT, PLY, "{g}"')
    assert "open surface, not a solid" in msg and "2 triangles" in msg


def test_mixed_up_triangles_are_put_right(tmp_path):
    pts, hexes = _box_grid(2, 2, 2)
    tris = meshfiles.surface_of(pts, [("hexahedron", hexes)])
    tris[::3] = tris[::3][:, [0, 2, 1]]  # every third triangle faces in
    f = tmp_path / "mixed.off"
    meshio.write(f, meshio.Mesh(pts, [("triangle", tris)]))
    q = Processor()
    ok(q, f'IMPORT, OFF, "{f}"')
    assert vols(q) == pytest.approx([8])


def test_surface_of_shared_faces_is_dropped():
    pts, hexes = _box_grid(2, 1, 1)
    tris = meshfiles.surface_of(pts, [("hexahedron", hexes)])
    assert len(tris) == 2 * 10  # 10 outer quads (4 top and bottom, 4 front and back, 2 ends), 2 triangles each
    pts2, tris2 = meshfiles.clean(pts, tris)
    assert len(pts2) == 12


def test_mesh_import_errors(tmp_path, monkeypatch):
    p = Processor()
    assert "no such file" in err(p, f'IMPORT, PLY, "{tmp_path}/none.ply"')
    bad = tmp_path / "bad.vtk"
    bad.write_text("not a mesh")
    assert "could not read" in err(p, f'IMPORT, VTK, "{bad}"')
    lines = tmp_path / "lines.vtk"
    meshio.write(lines, meshio.Mesh(np.eye(3), [("line", np.array([[0, 1], [1, 2]]))]))
    assert "no surface triangles" in err(p, f'IMPORT, VTK, "{lines}"')
    ok(p, f'SPHERE, 0,0,0, 5\nEXPORT, STL, "{tmp_path}/s.stl"')
    monkeypatch.setattr(project_handlers, "MAX_MESH_TRIANGLES", 100)
    assert "Reduce the mesh" in err(Processor(), f'IMPORT, STL, "{tmp_path}/s.stl"')
    assert "format" in err(p, f'EXPORT, PLY, "{tmp_path}/x.ply"')


def test_project_keeps_a_copy_of_a_mesh_file(tmp_path):
    pts, hexes = _box_grid(2, 2, 2)
    f = tmp_path / "part.vtu"
    meshio.write(f, meshio.Mesh(pts, [("hexahedron", hexes)]))
    p = Processor()
    ok(p, f'IMPORT, VTK, "{f}", part')
    ok(p, f'SAVE, "{tmp_path}/job.m3d"')
    f.unlink()
    q = Processor()
    assert q.run(f'OPEN, "{tmp_path}/job.m3d"').ok
    assert q.evaluate("VOL(part)") == pytest.approx(8)
