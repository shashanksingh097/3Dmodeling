"""Triangle-mesh files: write OBJ, 3MF and glTF, read mesh files of many kinds.

The modeler works on exact B-rep bodies. Mesh formats carry triangles only,
so:

* **Export** meshes each body (the same fineness as STL export) and writes
  its triangles, one object per body, with the body's colour and name where
  the format has a place for them.
* **Import** turns the triangles into faceted bodies, one per connected
  piece: a solid when the piece is closed, an open shell otherwise. Each
  triangle becomes a flat face, with edges shared between neighbours.
  Volume meshes from simulation tools (tetrahedra, hexahedra, wedges,
  pyramids) keep only their outer skin: the cell faces that no other cell
  shares.

OBJ, VTK, PLY, OFF, Gmsh and the other simulation formats are read with
meshio; 3MF and glTF are read and written here, with numpy only.
"""

from __future__ import annotations

import base64
import json
import os
import struct
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS

_as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face


class MeshFileError(Exception):
    """A mesh file could not be read or written; the message says why."""


@dataclass
class Mesh:
    """Triangles of one body: ``points`` (n, 3) float, ``tris`` (m, 3) int."""

    name: str
    points: np.ndarray
    tris: np.ndarray
    color: tuple[float, float, float] | None = None


# ---- B-rep to triangles -----------------------------------------------------------
def triangulate(shape, deflection: float, name: str = "", color=None) -> Mesh:
    """The faces of ``shape`` as one triangle mesh, normals pointing outwards.

    Meshes a copy, so the model's own shape is not changed."""
    shape = BRepBuilderAPI_Copy(shape).Shape()
    BRepMesh_IncrementalMesh(shape, deflection, False, 0.3, True)
    pts: list[np.ndarray] = []
    tris: list[np.ndarray] = []
    base = 0
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        face = _as_face(ex.Current())
        ex.Next()
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None or tri.NbTriangles() == 0:
            continue
        trsf = loc.Transformation()
        n = tri.NbNodes()
        p = np.empty((n, 3))
        for i in range(1, n + 1):
            q = tri.Node(i).Transformed(trsf)
            p[i - 1] = (q.X(), q.Y(), q.Z())
        t = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)], dtype=np.int64) - 1
        if face.Orientation() == TopAbs_REVERSED:
            t = t[:, [0, 2, 1]]
        pts.append(p)
        tris.append(t + base)
        base += n
    if not tris:
        return Mesh(name, np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), color)
    points, t = np.vstack(pts), np.vstack(tris)
    points, t = _merge_points(points, t, deflection * 1e-3)
    return Mesh(name, points, t, color)


def _merge_points(points: np.ndarray, tris: np.ndarray, tol: float):
    """Join points closer than ``tol`` (faces share their edge nodes after this)."""
    if len(points) == 0:
        return points, tris
    tol = max(tol, 1e-12)
    keys = np.round(points / tol).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.reshape(-1)
    tris = inverse[tris]
    good = (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])
    return points[first], tris[good]


# ---- writers ------------------------------------------------------------------------
def write_obj(path: str, meshes: list[Mesh], scale: float = 1.0) -> None:
    """Wavefront OBJ, one ``o`` group per body; colours go to a .mtl beside it."""
    mtl_name = os.path.splitext(os.path.basename(path))[0] + ".mtl"
    with_color = [m for m in meshes if m.color is not None]
    lines = ["# written by 3Dmodeling"]
    if with_color:
        lines.append(f"mtllib {mtl_name}")
    base = 1
    for k, m in enumerate(meshes):
        lines.append(f"o {_safe_name(m.name, k)}")
        if m.color is not None:
            lines.append(f"usemtl mat{k}")
        lines.extend(f"v {x:.9g} {y:.9g} {z:.9g}" for x, y, z in m.points * scale)
        lines.extend(f"f {a + base} {b + base} {c + base}" for a, b, c in m.tris)
        base += len(m.points)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    if with_color:
        mtl = []
        for k, m in enumerate(meshes):
            if m.color is not None:
                r, g, b = m.color
                mtl += [f"newmtl mat{k}", f"Kd {r:.4f} {g:.4f} {b:.4f}", ""]
        with open(os.path.join(os.path.dirname(path), mtl_name), "w", encoding="utf-8") as f:
            f.write("\n".join(mtl))


_3MF_UNITS = {"MM": "millimeter", "CM": "centimeter", "M": "meter", "IN": "inch"}
_3MF_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"


def write_3mf(path: str, meshes: list[Mesh], units: str = "MM") -> None:
    """3MF (the 3D printing package): one object per body, in the model's units."""
    root = ET.Element("model", {"unit": _3MF_UNITS.get(units, "millimeter"), "xml:lang": "en-US",
                                "xmlns": _3MF_NS})
    res = ET.SubElement(root, "resources")
    colored = [m for m in meshes if m.color is not None]
    if colored:
        bm = ET.SubElement(res, "basematerials", {"id": "1"})
        for m in colored:
            r, g, b = (max(0, min(255, round(c * 255))) for c in m.color)
            ET.SubElement(bm, "base", {"name": m.name or "body", "displaycolor": f"#{r:02X}{g:02X}{b:02X}"})
    build = ET.Element("build")
    ci = 0
    for k, m in enumerate(meshes):
        oid = str(k + 2)
        attrs = {"id": oid, "type": "model", "name": m.name or f"body{k + 1}"}
        if m.color is not None:
            attrs.update(pid="1", pindex=str(ci))
            ci += 1
        obj = ET.SubElement(res, "object", attrs)
        mesh = ET.SubElement(obj, "mesh")
        verts = ET.SubElement(mesh, "vertices")
        for x, y, z in m.points:
            ET.SubElement(verts, "vertex", {"x": f"{x:.9g}", "y": f"{y:.9g}", "z": f"{z:.9g}"})
        tris = ET.SubElement(mesh, "triangles")
        for a, b, c in m.tris:
            ET.SubElement(tris, "triangle", {"v1": str(a), "v2": str(b), "v3": str(c)})
        ET.SubElement(build, "item", {"objectid": oid})
    root.append(build)
    model_xml = b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")
    types = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
             '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model_xml)


def write_gltf(path: str, meshes: list[Mesh], scale: float = 1.0) -> None:
    """glTF 2.0: a binary ``.glb``, or a ``.gltf`` with the data inside it.

    glTF is in metres with Y up; ``scale`` converts model units to metres and
    the model's Z-up axes are turned to Y-up, as viewers expect."""
    to_y_up = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=float)
    blob = bytearray()
    views, accessors, gl_meshes, nodes, materials = [], [], [], [], []

    def add_view(data: bytes, target: int) -> int:
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": target})
        blob.extend(data)
        return len(views) - 1

    for k, m in enumerate(meshes):
        if len(m.tris) == 0:
            continue
        p = (m.points * scale @ to_y_up.T).astype(np.float32)
        idx = m.tris.astype(np.uint32).reshape(-1)
        pv = add_view(p.tobytes(), 34962)
        accessors.append({"bufferView": pv, "componentType": 5126, "count": len(p), "type": "VEC3",
                          "min": p.min(axis=0).tolist(), "max": p.max(axis=0).tolist()})
        iv = add_view(idx.tobytes(), 34963)
        accessors.append({"bufferView": iv, "componentType": 5125, "count": len(idx), "type": "SCALAR"})
        prim = {"attributes": {"POSITION": len(accessors) - 2}, "indices": len(accessors) - 1}
        if m.color is not None:
            materials.append({"name": f"{m.name or 'body'}",
                              "pbrMetallicRoughness": {"baseColorFactor": [*map(float, m.color), 1.0],
                                                       "metallicFactor": 0.0, "roughnessFactor": 0.6}})
            prim["material"] = len(materials) - 1
        gl_meshes.append({"name": m.name or f"body{k + 1}", "primitives": [prim]})
        nodes.append({"name": m.name or f"body{k + 1}", "mesh": len(gl_meshes) - 1})
    while len(blob) % 4:
        blob.append(0)
    doc = {"asset": {"version": "2.0", "generator": "3Dmodeling"}, "scene": 0,
           "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": gl_meshes,
           "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    if materials:
        doc["materials"] = materials
    if path.lower().endswith(".gltf"):
        doc["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(bytes(blob)).decode()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        return
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))


def _safe_name(name: str, k: int) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name) or f"body{k + 1}"


# ---- readers ------------------------------------------------------------------------
# faces of each volume cell, ordered so their normals point out of the cell
_CELL_FACES = {
    "tetra": [(0, 2, 1), (0, 1, 3), (1, 2, 3), (0, 3, 2)],
    "hexahedron": [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    "wedge": [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)],
    "pyramid": [(0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)],
}
# higher-order cells keep their corner nodes (they come first)
_CORNERS = {"tetra": 4, "tetra10": 4, "hexahedron": 8, "hexahedron20": 8, "hexahedron27": 8,
            "wedge": 6, "wedge15": 6, "wedge18": 6, "pyramid": 5, "pyramid13": 5, "pyramid14": 5}
_SURFACE = {"triangle": 3, "triangle6": 3, "triangle7": 3, "quad": 4, "quad8": 4, "quad9": 4}


def surface_of(points: np.ndarray, cells: list[tuple[str, np.ndarray]]) -> np.ndarray:
    """Triangles of a mesh's surface: its surface cells plus the outer skin of
    its volume cells. Lines, vertices and unknown cells are skipped."""
    tris: list[np.ndarray] = []
    vol_faces: list[np.ndarray] = []
    for kind, data in cells:
        data = np.asarray(data, dtype=np.int64)
        if data.size == 0:
            continue
        if kind in _SURFACE:
            corners = data[:, : _SURFACE[kind]]
            tris.append(_fan(corners))
        elif kind == "polygon" or (kind.startswith("polygon") and data.ndim == 2):
            tris.append(_fan(data))
        elif kind in _CORNERS:
            base = kind.rstrip("0123456789")
            corners = data[:, : _CORNERS[kind]]
            for face in _CELL_FACES[base]:
                f = corners[:, list(face)]
                if f.shape[1] == 3:
                    f = np.hstack([f, np.full((len(f), 1), -1)])
                vol_faces.append(f)
    if vol_faces:
        faces = np.vstack(vol_faces)
        key = np.sort(faces, axis=1)
        _, inverse, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
        outer = faces[counts[inverse.reshape(-1)] == 1]
        tri_f = outer[outer[:, 3] < 0][:, :3]
        quad_f = outer[outer[:, 3] >= 0]
        tris.append(tri_f)
        if len(quad_f):
            tris.append(_fan(quad_f))
    if not tris:
        return np.zeros((0, 3), dtype=np.int64)
    return np.vstack(tris)


def _fan(polys: np.ndarray) -> np.ndarray:
    """Split polygons (rows of corner indices) into triangles."""
    n = polys.shape[1]
    return np.vstack([polys[:, [0, i, i + 1]] for i in range(1, n - 1)])


def read_with_meshio(path: str, file_format: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Points and surface triangles of any file meshio reads (by extension, or ``file_format``)."""
    try:
        import meshio
    except ImportError:  # pragma: no cover - meshio is a dependency
        raise MeshFileError("reading this format needs the meshio package (pip install meshio)") from None
    try:
        m = meshio.read(path, file_format=file_format)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - meshio raises many kinds, and exits on some bad files
        why = str(exc) if not isinstance(exc, SystemExit) and str(exc) else "not a mesh file of this kind"
        raise MeshFileError(f"could not read {os.path.basename(path)}: {why}") from None
    pts = np.asarray(m.points, dtype=float)
    if pts.ndim != 2 or len(pts) == 0:
        raise MeshFileError(f"{os.path.basename(path)} holds no points")
    if pts.shape[1] == 2:
        pts = np.hstack([pts, np.zeros((len(pts), 1))])
    cells = [(c.type, c.data) for c in m.cells]
    return pts[:, :3], surface_of(pts, cells)


def read_stl(path: str) -> tuple[np.ndarray, np.ndarray]:
    """An STL file (text or binary), read by the kernel's own reader."""
    from OCP.RWStl import RWStl

    read = getattr(RWStl, "ReadFile_s", None) or RWStl.ReadFile
    tri = read(path)
    if tri is None or tri.NbTriangles() == 0:
        raise MeshFileError(f"could not read STL file {os.path.basename(path)}")
    pts = np.array([(q.X(), q.Y(), q.Z()) for q in (tri.Node(i) for i in range(1, tri.NbNodes() + 1))])
    t = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)], dtype=np.int64) - 1
    return pts, t


def read_3mf(path: str) -> tuple[np.ndarray, np.ndarray]:
    """All mesh objects of a 3MF package, placed by its build items, in millimetres."""
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".model")]
            if not names:
                raise MeshFileError(f"{os.path.basename(path)} has no 3D model inside")
            root = ET.fromstring(z.read("3D/3dmodel.model" if "3D/3dmodel.model" in names else names[0]))
    except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise MeshFileError(f"could not read {os.path.basename(path)}: {exc}") from None
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    objects = {}
    for obj in root.iter(f"{ns}object"):
        mesh = obj.find(f"{ns}mesh")
        if mesh is None:
            continue
        v = np.array([[float(e.get("x")), float(e.get("y")), float(e.get("z"))]
                      for e in mesh.iter(f"{ns}vertex")]).reshape(-1, 3)
        t = np.array([[int(e.get("v1")), int(e.get("v2")), int(e.get("v3"))]
                      for e in mesh.iter(f"{ns}triangle")], dtype=np.int64).reshape(-1, 3)
        objects[obj.get("id")] = (v, t)
    items = [(i.get("objectid"), i.get("transform")) for i in root.iter(f"{ns}item")] or \
        [(k, None) for k in objects]
    pts, tris, base = [], [], 0
    for oid, tr in items:
        if oid not in objects:
            continue
        v, t = objects[oid]
        if tr:
            m = np.array([float(x) for x in tr.split()]).reshape(4, 3)
            v = v @ m[:3] + m[3]
        pts.append(v)
        tris.append(t + base)
        base += len(v)
    if not tris:
        raise MeshFileError(f"{os.path.basename(path)} holds no triangles")
    mm = {"micron": 0.001, "millimeter": 1.0, "centimeter": 10.0, "inch": 25.4, "foot": 304.8,
          "meter": 1000.0}.get(root.get("unit", "millimeter"), 1.0)
    return np.vstack(pts) * mm, np.vstack(tris)


_GL_TYPES = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_GL_SIZES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read_gltf(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Triangles of every mesh in a .glb or .gltf scene, in millimetres, turned back to Z up."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        if raw[:4] == b"glTF":
            jlen = struct.unpack_from("<I", raw, 12)[0]
            doc = json.loads(raw[20: 20 + jlen])
            off = 20 + jlen
            buffers = [raw[off + 8: off + 8 + struct.unpack_from("<I", raw, off)[0]]] if off < len(raw) else []
        else:
            doc = json.loads(raw)
            buffers = []
            for b in doc.get("buffers", []):
                uri = b.get("uri", "")
                if uri.startswith("data:"):
                    buffers.append(base64.b64decode(uri.split(",", 1)[1]))
                else:
                    with open(os.path.join(os.path.dirname(path), uri), "rb") as f:
                        buffers.append(f.read())
    except (OSError, ValueError, KeyError, struct.error) as exc:
        raise MeshFileError(f"could not read {os.path.basename(path)}: {exc}") from None

    def accessor(i):
        a = doc["accessors"][i]
        v = doc["bufferViews"][a["bufferView"]]
        dt = np.dtype(_GL_TYPES[a["componentType"]])
        n = _GL_SIZES[a["type"]]
        start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = v.get("byteStride", 0) or dt.itemsize * n
        buf = np.frombuffer(buffers[v["buffer"]], dtype=np.uint8)
        rows = buf[start: start + stride * a["count"]].reshape(a["count"], -1) if stride * a["count"] else buf[:0]
        return np.ascontiguousarray(rows[:, : dt.itemsize * n]).view(dt).reshape(a["count"], n)

    def node_matrix(node):
        if "matrix" in node:
            return np.array(node["matrix"], dtype=float).reshape(4, 4).T
        t = np.eye(4)
        if "scale" in node:
            t = np.diag([*node["scale"], 1.0]) @ t
        if "rotation" in node:
            x, y, z, w = node["rotation"]
            r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                          [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                          [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
            rt = np.eye(4)
            rt[:3, :3] = r
            t = rt @ t
        if "translation" in node:
            tt = np.eye(4)
            tt[:3, 3] = node["translation"]
            t = tt @ t
        return t

    pts, tris, base = [], [], 0

    def visit(ni, parent):
        nonlocal base
        node = doc["nodes"][ni]
        m = parent @ node_matrix(node)
        if "mesh" in node:
            for prim in doc["meshes"][node["mesh"]].get("primitives", []):
                if prim.get("mode", 4) != 4:
                    continue
                p = accessor(prim["attributes"]["POSITION"]).astype(float)
                idx = accessor(prim["indices"]).reshape(-1).astype(np.int64) if "indices" in prim \
                    else np.arange(len(p))
                p = (np.hstack([p, np.ones((len(p), 1))]) @ m.T)[:, :3]
                pts.append(p)
                tris.append(idx.reshape(-1, 3) + base)
                base += len(p)
        for c in node.get("children", []):
            visit(c, m)

    try:
        scene = doc.get("scenes", [{}])[doc.get("scene", 0)] if doc.get("scenes") else \
            {"nodes": list(range(len(doc.get("nodes", []))))}
        for ni in scene.get("nodes", []):
            visit(ni, np.eye(4))
    except (KeyError, IndexError, ValueError) as exc:
        raise MeshFileError(f"could not read {os.path.basename(path)}: {exc}") from None
    if not tris:
        raise MeshFileError(f"{os.path.basename(path)} holds no triangles")
    y_up_to_z_up = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=float)
    return np.vstack(pts) @ y_up_to_z_up.T * 1000.0, np.vstack(tris)


# ---- triangles to bodies --------------------------------------------------------------
@dataclass
class Piece:
    shape: object  # TopoDS_Solid or TopoDS_Shell
    triangles: int
    closed: bool


def clean(points: np.ndarray, tris: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Join coincident points, drop unused points, flat and repeated triangles."""
    points = np.asarray(points, dtype=float)
    tris = np.asarray(tris, dtype=np.int64).reshape(-1, 3)
    if len(tris) == 0:
        return points[:0], tris
    if tris.min() < 0 or tris.max() >= len(points):
        raise MeshFileError("a triangle refers to a point that is not in the file")
    diag = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0))) or 1.0
    points, tris = _merge_points(points, tris, diag * 1e-9)
    _, keep = np.unique(np.sort(tris, axis=1), axis=0, return_index=True)
    tris = tris[np.sort(keep)]
    used, tris = np.unique(tris, return_inverse=True)
    return points[used], tris.reshape(-1, 3)


def _components(nv: int, tris: np.ndarray) -> np.ndarray:
    """A label per triangle: triangles sharing a point have the same label."""
    lab = np.arange(nv)
    while True:
        m = lab[tris].min(axis=1)
        new = lab.copy()
        for k in range(3):
            np.minimum.at(new, tris[:, k], m)
        new = new[new]  # jump to the label's own label
        if np.array_equal(new, lab):
            break
        lab = new
    return lab[tris[:, 0]]


def _edge_state(tris: np.ndarray) -> tuple[bool, bool]:
    """(closed, consistent): every edge has two triangles; neighbours agree on which side is out."""
    directed = np.vstack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    und = np.sort(directed, axis=1)
    _, counts = np.unique(und, axis=0, return_counts=True)
    closed = bool(np.all(counts == 2))
    consistent = len(np.unique(directed, axis=0)) == len(directed)
    return closed, consistent


def mesh_to_pieces(points: np.ndarray, tris: np.ndarray) -> list[Piece]:
    """Triangles as faceted bodies, one per connected piece."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeShapeOnMesh, BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.gp import gp_Pnt
    from OCP.Poly import Poly_Triangle, Poly_Triangulation
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopoDS import TopoDS_Shell

    as_shell = getattr(TopoDS, "Shell_s", None) or TopoDS.Shell
    volume_props = getattr(BRepGProp, "VolumeProperties_s", None) or BRepGProp.VolumeProperties
    points, tris = clean(points, tris)
    if len(tris) == 0:
        return []
    labels = _components(len(points), tris)
    pieces = []
    for lab in np.unique(labels):
        t = tris[labels == lab]
        used, t = np.unique(t, return_inverse=True)
        t = t.reshape(-1, 3)
        p = points[used]
        tri = Poly_Triangulation(len(p), len(t), False)
        for i, (x, y, z) in enumerate(p, 1):
            tri.SetNode(i, gp_Pnt(float(x), float(y), float(z)))
        for i, (a, b, c) in enumerate(t, 1):
            tri.SetTriangle(i, Poly_Triangle(int(a) + 1, int(b) + 1, int(c) + 1))
        mk = BRepBuilderAPI_MakeShapeOnMesh(tri)
        mk.Build()
        faces = mk.Shape()
        closed, consistent = _edge_state(t)
        builder = BRep_Builder()
        shell = TopoDS_Shell()
        builder.MakeShell(shell)
        ex = TopExp_Explorer(faces, TopAbs_FACE)
        while ex.More():
            builder.Add(shell, ex.Current())
            ex.Next()
        if closed and not consistent:
            # some triangles face the wrong way: sewing puts them right (slow, so only here)
            sew = BRepBuilderAPI_Sewing(1e-9)
            sew.Add(shell)
            sew.Perform()
            sx = TopExp_Explorer(sew.SewedShape(), TopAbs_SHELL)
            if sx.More():
                shell = as_shell(sx.Current())
            else:
                closed = False
        if not closed:
            pieces.append(Piece(shell, len(t), False))
            continue
        shell.Closed(True)
        solid = BRepBuilderAPI_MakeSolid(shell).Solid()
        props = GProp_GProps()
        volume_props(solid, props)
        if props.Mass() < 0:  # the triangles faced inwards
            solid = solid.Reversed()
        pieces.append(Piece(solid, len(t), True))
    return pieces


def write_binary_stl(path: str, points: np.ndarray, tris: np.ndarray) -> None:
    rec = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    v = points[tris]
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    rec["n"] = np.divide(n, ln, out=np.zeros_like(n), where=ln > 0)
    rec["v"] = v
    with open(path, "wb") as f:
        f.write(b"3Dmodeling mesh import".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        f.write(rec.tobytes())
