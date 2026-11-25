"""Point clouds (PLAN item 77): scanner points as a body, and exact shapes fitted to a patch of them.

A **point body** is a compound of vertices and nothing else, so the model, the tree, the views,
picking (each point is a vertex with an ID) and saving need nothing new. Clouds are thinned on
import to a most number of points (one point per small cube of space), which keeps them quick to
draw and to pick; the fits work just as well on a thinned cloud.

Files: .xyz / .txt / .csv (x y z per line, more columns ignored), .pts (the same, with a point
count on the first line), .ply (ASCII or binary; the vertices, faces ignored) and .e57 (the ASTM
scanner format: cartesian points of every scan in the file, float or scaled-integer, each scan
moved by its pose).

Fits (all least squares, refined with scipy): plane, sphere, cylinder, cone, and freeform (a
B-spline surface through meshfit.fit_patch over a Delaunay triangulation of the points seen from
their best plane). Each fit gives a face trimmed to the patch, which DEVIATION-style numbers then
measure the points against.
"""

from __future__ import annotations

import math
import re
import struct
import xml.etree.ElementTree as ET
from collections import OrderedDict
from dataclasses import dataclass, field

import numpy as np

MOST_POINTS = 200_000  # a point body keeps at most this many (thinned on import)
KINDS = ("AUTO", "PLANE", "SPHERE", "CYLINDER", "CONE", "FREEFORM")


class CloudError(Exception):
    """A point file that cannot be read, or a fit that cannot be made."""


# ---- the shape that holds a cloud -------------------------------------------------------------
_CACHE: OrderedDict = OrderedDict()


def make_shape(points: np.ndarray):
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.gp import gp_Pnt
    from OCP.TopoDS import TopoDS_Compound

    b = BRep_Builder()
    c = TopoDS_Compound()
    b.MakeCompound(c)
    for x, y, z in np.asarray(points, float):
        b.Add(c, BRepBuilderAPI_MakeVertex(gp_Pnt(float(x), float(y), float(z))).Vertex())
    _remember(c, np.asarray(points, float))
    return c


def _remember(shape, pts: np.ndarray) -> None:
    _CACHE[hash(shape)] = (shape, pts)
    _CACHE.move_to_end(hash(shape))
    while len(_CACHE) > 16:
        _CACHE.popitem(last=False)


def is_points(shape) -> bool:
    """A compound of loose vertices only (a point body)."""
    if shape is None or shape.IsNull():
        return False
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer

    if shape.ShapeType() != TopAbs_COMPOUND:
        return False
    return (TopExp_Explorer(shape, TopAbs_VERTEX).More() and not TopExp_Explorer(shape, TopAbs_EDGE).More()
            and not TopExp_Explorer(shape, TopAbs_FACE).More())


def arrays(shape) -> np.ndarray:
    """The points of a point body (n, 3), in the order of its vertices."""
    hit = _CACHE.get(hash(shape))
    if hit is not None and hit[0].IsSame(shape):
        return hit[1]
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    as_vertex = getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex
    pnt = getattr(BRep_Tool, "Pnt_s", None) or BRep_Tool.Pnt
    out = []
    ex = TopExp_Explorer(shape, TopAbs_VERTEX)
    while ex.More():
        q = pnt(as_vertex(ex.Current()))
        out.append((q.X(), q.Y(), q.Z()))
        ex.Next()
    pts = np.asarray(out, float).reshape(-1, 3)
    _remember(shape, pts)
    return pts


def thin(pts: np.ndarray, most: int) -> np.ndarray:
    """At most ``most`` points, one per small cube of space (evenly spread, not random)."""
    pts = np.asarray(pts, float)
    if len(pts) <= most:
        return pts
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    diag = float(np.linalg.norm(hi - lo)) or 1.0
    step = diag / math.sqrt(most) / 2  # scans are surfaces: points grow with the square of the size
    keep = pts
    for _ in range(40):
        keys = np.floor((pts - lo) / step).astype(np.int64)
        _u, first = np.unique(keys, axis=0, return_index=True)
        keep = pts[np.sort(first)]
        if len(keep) <= most:
            break
        step *= 1.3
    if len(keep) > most:  # pragma: no cover - only for odd, very dense clouds
        keep = keep[np.linspace(0, len(keep) - 1, most).astype(int)]
    return keep


def sample(shape, count: int, noise: float = 0.0, seed: int = 0) -> np.ndarray:
    """About ``count`` points spread evenly over a body's surface (a made-up scan), with noise
    along the surface normal of up to ±noise."""
    from . import analysis as an

    m = an.mesh(shape)
    p, t = np.asarray(m.nodes, float), np.asarray(m.tris)
    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    cross = np.cross(b - a, c - a)
    area = np.linalg.norm(cross, axis=1)
    rng = np.random.default_rng(seed)
    which = rng.choice(len(t), size=count, p=area / area.sum())
    r1, r2 = rng.random(count), rng.random(count)
    flip = r1 + r2 > 1
    r1[flip], r2[flip] = 1 - r1[flip], 1 - r2[flip]
    out = a[which] + r1[:, None] * (b - a)[which] + r2[:, None] * (c - a)[which]
    if noise:
        n = cross[which] / np.maximum(area[which], 1e-300)[:, None]
        out = out + n * rng.uniform(-noise, noise, count)[:, None]
    return out


# ---- files ------------------------------------------------------------------------------------
def read(path: str) -> np.ndarray:
    """The points of a .xyz, .txt, .csv, .pts, .ply or .e57 file."""
    low = path.lower()
    if low.endswith(".e57"):
        return read_e57(path)
    if low.endswith(".ply"):
        return read_ply(path)[0]
    return read_xyz(path)


def read_xyz(path: str) -> np.ndarray:
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        first = True
        for line in f:
            s = line.strip()
            if not s or s.startswith(("#", "//")):
                continue
            parts = re.split(r"[\s,;]+", s)
            if first and len(parts) == 1:  # .pts: the point count
                first = False
                continue
            first = False
            try:
                rows.append((float(parts[0]), float(parts[1]), float(parts[2])))
            except (ValueError, IndexError):
                if not rows:  # a header line (x,y,z,...)
                    continue
                raise CloudError(f"line {line.strip()[:40]!r} is not x y z") from None
    if not rows:
        raise CloudError("no points in the file")
    return np.asarray(rows, float)


_PLY_TYPES = {"char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1", "short": "i2", "int16": "i2",
              "ushort": "u2", "uint16": "u2", "int": "i4", "int32": "i4", "uint": "u4", "uint32": "u4",
              "float": "f4", "float32": "f4", "double": "f8", "float64": "f8"}


def read_ply(path: str) -> tuple[np.ndarray, int]:
    """(vertices, number of faces) of a PLY file."""
    with open(path, "rb") as f:
        if f.readline().strip() != b"ply":
            raise CloudError("not a PLY file")
        fmt = ""
        elements: list[tuple[str, int, list]] = []
        while True:
            line = f.readline()
            if not line:
                raise CloudError("the PLY header has no end_header")
            words = line.decode("ascii", "replace").split()
            if not words:
                continue
            if words[0] == "format":
                fmt = words[1]
            elif words[0] == "element":
                elements.append((words[1], int(words[2]), []))
            elif words[0] == "property" and elements:
                elements[-1][2].append(words[1:])
            elif words[0] == "end_header":
                break
        faces = sum(n for name, n, _ in elements if name == "face")
        if fmt == "ascii":
            text = f.read().decode("ascii", "replace").split("\n")
            at = 0
            for name, n, props in elements:
                if name == "vertex":
                    names = [pp[-1] for pp in props]
                    try:
                        ix = [names.index(k) for k in ("x", "y", "z")]
                    except ValueError:
                        raise CloudError("the PLY vertices have no x, y, z") from None
                    rows = [text[at + i].split() for i in range(n)]
                    return np.asarray([[float(r[i]) for i in ix] for r in rows], float).reshape(-1, 3), faces
                at += n
            raise CloudError("no vertices in the PLY file")
        order = {"binary_little_endian": "<", "binary_big_endian": ">"}.get(fmt)
        if order is None:
            raise CloudError(f"PLY format {fmt!r} is not known")
        for name, n, props in elements:
            if any(pp[0] == "list" for pp in props):
                if name == "vertex":
                    raise CloudError("PLY vertices with list properties cannot be read")
                break  # faces come after the vertices in every PLY seen; stop here
            dt = np.dtype([(pp[1], order + _PLY_TYPES[pp[0]]) for pp in props])
            data = np.frombuffer(f.read(dt.itemsize * n), dtype=dt, count=n)
            if name == "vertex":
                return np.stack([data[k].astype(float) for k in ("x", "y", "z")], axis=1), faces
        raise CloudError("no vertices in the PLY file")


# E57 (ASTM E2807): pages of 1024 bytes, the last 4 of each a checksum; an XML section says
# where each scan's points are; the points are in binary packets, one byte stream per field.
_PAGE = 1024


class _E57:
    def __init__(self, path: str):
        with open(path, "rb") as f:
            self.raw = f.read()
        if self.raw[:8] != b"ASTM-E57":
            raise CloudError("not an E57 file")
        (_major, _minor, _length, xml_off, xml_len, page) = struct.unpack_from("<IIQQQQ", self.raw, 8)
        self.page = page or _PAGE
        self.xml = self.logical(xml_off, xml_len)

    def logical(self, physical: int, n: int) -> bytes:
        """``n`` bytes of content from a physical offset, skipping each page's checksum."""
        out = bytearray()
        body = self.page - 4
        pos = physical
        while len(out) < n:
            in_page = pos % self.page
            if in_page >= body:
                pos += self.page - in_page
                continue
            take = min(body - in_page, n - len(out))
            out += self.raw[pos:pos + take]
            pos += take
        return bytes(out)

    def advance(self, physical: int, n: int) -> int:
        body = self.page - 4
        page, in_page = divmod(physical, self.page)
        logical = page * body + in_page + n
        p2, i2 = divmod(logical, body)
        return p2 * self.page + i2


def _tag(e) -> str:
    return e.tag.split("}")[-1]


def _child(e, name):
    for c in e:
        if _tag(c) == name:
            return c
    return None


def _num(e, name, default=0.0) -> float:
    c = _child(e, name)
    return float(c.text) if c is not None and c.text and c.text.strip() else default


def _unpack_bits(buf: bytes, bits: int, n: int) -> np.ndarray:
    if bits == 0:
        return np.zeros(n, np.int64)
    b = np.unpackbits(np.frombuffer(buf, np.uint8), bitorder="little")[: bits * n]
    b = b.reshape(n, bits).astype(np.int64)
    return (b << np.arange(bits, dtype=np.int64)).sum(axis=1)


def read_e57(path: str) -> np.ndarray:
    e = _E57(path)
    try:
        root = ET.fromstring(e.xml.rstrip(b"\0"))
    except ET.ParseError as exc:
        raise CloudError(f"the E57 XML section cannot be read: {exc}") from None
    scans = _child(root, "data3D")
    if scans is None or not len(scans):
        raise CloudError("the E57 file has no scans")
    out = []
    for scan in scans:
        pts_node = _child(scan, "points")
        if pts_node is None:
            continue
        proto = _child(pts_node, "prototype")
        fields = [(_tag(c), c) for c in proto]
        names = [n for n, _ in fields]
        if not {"cartesianX", "cartesianY", "cartesianZ"} <= set(names):
            raise CloudError("only cartesian E57 points can be read (this scan is spherical)")
        n = int(pts_node.get("recordCount", "0"))
        streams = _streams(e, int(pts_node.get("fileOffset")), len(fields))
        cols = {}
        for k, (name, node) in enumerate(fields):
            if name not in ("cartesianX", "cartesianY", "cartesianZ"):
                continue
            cols[name] = _decode(node, streams[k], n)
        p = np.stack([cols["cartesianX"], cols["cartesianY"], cols["cartesianZ"]], axis=1)
        pose = _child(scan, "pose")
        if pose is not None:
            p = _posed(p, pose)
        out.append(p)
    if not out:
        raise CloudError("the E57 file has no points")
    return np.vstack(out)


def _streams(e: _E57, offset: int, count: int) -> list[bytes]:
    head = e.logical(offset, 32)
    if head[0] != 1:
        raise CloudError("an E57 binary section is not where the XML says")
    length, data_off, _index_off = struct.unpack_from("<QQQ", head, 8)
    streams = [bytearray() for _ in range(count)]
    pos = data_off
    end_logical = length - 32
    done = 0
    while done < end_logical:
        h = e.logical(pos, 4)
        kind, _flags, size_m1 = h[0], h[1], struct.unpack_from("<H", h, 2)[0]
        size = size_m1 + 1
        packet = e.logical(pos, size)
        if kind == 1:  # data
            k = struct.unpack_from("<H", packet, 4)[0]
            lens = struct.unpack_from(f"<{k}H", packet, 6)
            at = 6 + 2 * k
            for i, ln in enumerate(lens):
                if i < count:
                    streams[i] += packet[at:at + ln]
                at += ln
        pos = e.advance(pos, size)
        done += size
    return [bytes(s) for s in streams]


def _decode(node, buf: bytes, n: int) -> np.ndarray:
    kind = node.get("type")
    if kind == "Float":
        single = node.get("precision") == "single"
        return np.frombuffer(buf, "<f4" if single else "<f8", count=n).astype(float)
    lo = int(float(node.get("minimum", "0")))
    hi = int(float(node.get("maximum", "0")))
    bits = max(0, int(hi - lo).bit_length())
    raw = _unpack_bits(buf, bits, n) + lo
    if kind == "ScaledInteger":
        return raw * float(node.get("scale", "1")) + float(node.get("offset", "0"))
    if kind == "Integer":
        return raw.astype(float)
    raise CloudError(f"E57 field type {kind!r} is not known")


def _posed(p: np.ndarray, pose) -> np.ndarray:
    rot = _child(pose, "rotation")
    tr = _child(pose, "translation")
    if rot is not None:
        w, x, y, z = (_num(rot, k, 1.0 if k == "w" else 0.0) for k in ("w", "x", "y", "z"))
        r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        p = p @ r.T
    if tr is not None:
        p = p + np.array([_num(tr, k) for k in ("x", "y", "z")])
    return p


def write_e57(path: str, points: np.ndarray, scaled: float = 0.0, pose: tuple | None = None) -> None:
    """A small E57 file with one scan (double floats, or scaled integers of step ``scaled``),
    for tests and for handing clouds to other programs."""
    pts = np.asarray(points, float)
    n = len(pts)
    fields = []
    streams = []
    for k, name in enumerate(("cartesianX", "cartesianY", "cartesianZ")):
        col = pts[:, k]
        if scaled:
            q = np.round(col / scaled).astype(np.int64)
            lo, hi = int(q.min()), int(q.max())
            bits = (hi - lo).bit_length()
            v = (q - lo).astype(np.uint64)
            bitarr = ((v[:, None] >> np.arange(bits, dtype=np.uint64)) & 1).astype(np.uint8).ravel()
            streams.append(np.packbits(bitarr, bitorder="little").tobytes())
            fields.append(f'<{name} type="ScaledInteger" minimum="{lo}" maximum="{hi}" scale="{scaled!r}" '
                          f'offset="0"/>')
        else:
            streams.append(col.astype("<f8").tobytes())
            fields.append(f'<{name} type="Float"/>')
    # binary section: a header, then data packets (each under 64 KB) holding a piece of every stream
    if scaled:
        pieces = [streams]  # bit streams do not split on byte edges: one packet
        if sum(map(len, streams)) > 60000:
            raise CloudError("write_e57: too many points for scaled integers (use floats)")
    else:
        step = 2000
        pieces = [[buf[s * 8:min(n, s + step) * 8] for buf in streams] for s in range(0, n, step)]
    packets = bytearray()
    for parts in pieces:
        body = struct.pack(f"<H{len(parts)}H", len(parts), *[len(x) for x in parts]) + b"".join(parts)
        size = 4 + len(body)
        pad = (-size) % 4
        packets += bytes([1, 0]) + struct.pack("<H", size + pad - 1) + body + b"\0" * pad
    header_len = 48
    sec_start_logical = header_len
    data_logical = sec_start_logical + 32
    sec_len = 32 + len(packets)
    phys = _phys
    section = bytes([1]) + b"\0" * 7 + struct.pack("<QQQ", sec_len, phys(data_logical), 0) + bytes(packets)
    pose_xml = ""
    if pose is not None:
        (w, x, y, z), (tx, ty, tz) = pose
        pose_xml = (f'<pose type="Structure"><rotation type="Structure"><w type="Float">{w}</w><x type="Float">{x}'
                    f'</x><y type="Float">{y}</y><z type="Float">{z}</z></rotation><translation type="Structure">'
                    f'<x type="Float">{tx}</x><y type="Float">{ty}</y><z type="Float">{tz}</z></translation></pose>')
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><e57Root type="Structure" xmlns="http://www.astm.org/COMMIT/E57/'
           f'2010-e57-v1.0"><formatName type="String">ASTM E57 3D Imaging Data File</formatName><data3D '
           f'type="Vector"><vectorChild type="Structure">{pose_xml}<points type="CompressedVector" '
           f'fileOffset="{phys(sec_start_logical)}" recordCount="{n}"><prototype type="Structure">'
           f'{"".join(fields)}</prototype><codecs type="Vector"/></points></vectorChild></data3D>'
           f'</e57Root>').encode()
    xml_logical = sec_start_logical + len(section)
    logical = bytearray(b"\0" * header_len) + section + xml
    total_pages = -(-len(logical) // (_PAGE - 4))
    struct.pack_into("<8sIIQQQQ", logical, 0, b"ASTM-E57", 1, 0, total_pages * _PAGE, phys(xml_logical), len(xml),
                     _PAGE)
    out = bytearray()
    for i in range(total_pages):
        part = logical[i * (_PAGE - 4):(i + 1) * (_PAGE - 4)]
        out += part + b"\0" * (_PAGE - 4 - len(part)) + b"\0\0\0\0"  # checksums are not checked on reading
    with open(path, "wb") as f:
        f.write(bytes(out))


def _phys(logical: int) -> int:
    page, at = divmod(logical, _PAGE - 4)
    return page * _PAGE + at


# ---- fitting ----------------------------------------------------------------------------------
@dataclass
class Fit:
    kind: str
    params: dict
    rms: float = 0.0
    worst: float = 0.0
    face: object = None  # the trimmed face
    extra: dict = field(default_factory=dict)

    def words(self) -> str:
        q = self.params

        def v(x):
            return "(" + ", ".join(f"{c:.4g}" for c in x) + ")"

        if self.kind == "PLANE":
            return f"plane through {v(q['origin'])}, normal {v(q['normal'])}"
        if self.kind == "SPHERE":
            return f"sphere, centre {v(q['centre'])}, radius {q['radius']:.4g}"
        if self.kind == "CYLINDER":
            return f"cylinder, radius {q['radius']:.4g} (diameter {2 * q['radius']:.4g}), axis {v(q['axis'])} " \
                   f"through {v(q['origin'])}"
        if self.kind == "CONE":
            return f"cone, half angle {q['angle']:.4g}°, radius {q['radius']:.4g} at {v(q['origin'])}, axis " \
                   f"{v(q['axis'])}"
        return f"freeform B-spline surface ({q.get('poles', '?')} poles)"


def normals(p: np.ndarray, k: int = 12) -> np.ndarray:
    from scipy.spatial import cKDTree

    k = min(k, len(p))
    _d, idx = cKDTree(p).query(p, k=k)
    nb = p[idx] - p[idx].mean(axis=1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", nb, nb)
    _w, vec = np.linalg.eigh(cov)
    return vec[:, :, 0]


def _frame(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = axis / np.linalg.norm(axis)
    x = np.cross(a, [1.0, 0, 0] if abs(a[0]) < 0.9 else [0, 1.0, 0])
    x /= np.linalg.norm(x)
    return x, np.cross(a, x)


def _dir(th: float, ph: float) -> np.ndarray:
    return np.array([math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th)])


def _angles(a: np.ndarray) -> tuple[float, float]:
    a = a / np.linalg.norm(a)
    return math.acos(max(-1.0, min(1.0, a[2]))), math.atan2(a[1], a[0])


def fit_plane(p: np.ndarray) -> Fit:
    c = p.mean(axis=0)
    _w, v = np.linalg.eigh((p - c).T @ (p - c))
    n = v[:, 0]
    d = (p - c) @ n
    return Fit("PLANE", {"origin": c, "normal": n}, float(np.sqrt(np.mean(d * d))), float(np.abs(d).max()))


def fit_sphere(p: np.ndarray) -> Fit:
    from scipy.optimize import least_squares

    a = np.c_[2 * p, np.ones(len(p))]
    sol, *_ = np.linalg.lstsq(a, (p * p).sum(axis=1), rcond=None)
    c0 = sol[:3]
    r0 = math.sqrt(max(sol[3] + c0 @ c0, 1e-12))
    res = least_squares(lambda q: np.linalg.norm(p - q[:3], axis=1) - q[3], np.r_[c0, r0])
    c, r = res.x[:3], abs(res.x[3])
    d = np.linalg.norm(p - c, axis=1) - r
    return Fit("SPHERE", {"centre": c, "radius": r}, float(np.sqrt(np.mean(d * d))), float(np.abs(d).max()))


def _axis_from_normals(nrm: np.ndarray) -> np.ndarray:
    m = nrm - nrm.mean(axis=0)
    _w, v = np.linalg.eigh(m.T @ m)
    return v[:, 0]


def _axis_point(p: np.ndarray, nrm: np.ndarray, a: np.ndarray) -> np.ndarray:
    """The point on the axis (in the plane through the centroid square to ``a``) closest to every
    normal line, seen along the axis."""
    x, y = _frame(a)
    c = p.mean(axis=0)
    q = np.c_[(p - c) @ x, (p - c) @ y]
    d = np.c_[nrm @ x, nrm @ y]
    ln = np.linalg.norm(d, axis=1)
    ok = ln > 1e-6
    d = d[ok] / ln[ok, None]
    q = q[ok]
    perp = np.c_[-d[:, 1], d[:, 0]]
    m = np.einsum("ni,nj->ij", perp, perp)
    rhs = np.einsum("ni,ni,nj->j", perp, q, perp)
    s = np.linalg.lstsq(m, rhs, rcond=None)[0]
    return c + s[0] * x + s[1] * y


def _cyl_dist(q, p):
    th, ph, ox, oy, oz, r = q
    a = _dir(th, ph)
    v = p - np.array([ox, oy, oz])
    w = v - np.outer(v @ a, a)
    return np.linalg.norm(w, axis=1) - r


def fit_cylinder(p: np.ndarray, nrm: np.ndarray | None = None) -> Fit:
    from scipy.optimize import least_squares

    nrm = normals(p) if nrm is None else nrm
    a = _axis_from_normals(nrm)
    o = _axis_point(p, nrm, a)
    v = p - o
    r0 = float(np.median(np.linalg.norm(v - np.outer(v @ a, a), axis=1)))
    th, ph = _angles(a)
    res = least_squares(_cyl_dist, np.r_[th, ph, o, r0], args=(p,))
    th, ph, ox, oy, oz, r = res.x
    a = _dir(th, ph)
    o = np.array([ox, oy, oz])
    o = o + ((p - o) @ a).mean() * a  # the origin at the middle of the patch along the axis
    d = _cyl_dist(res.x, p)
    return Fit("CYLINDER", {"origin": o, "axis": a, "radius": abs(r)}, float(np.sqrt(np.mean(d * d))),
               float(np.abs(d).max()))


def _cone_dist(q, p):
    th, ph, ox, oy, oz, r0, al = q
    a = _dir(th, ph)
    v = p - np.array([ox, oy, oz])
    h = v @ a
    rad = np.linalg.norm(v - np.outer(h, a), axis=1)
    return (rad - (r0 + h * math.tan(al))) * math.cos(al)


def fit_cone(p: np.ndarray, nrm: np.ndarray | None = None) -> Fit:
    from scipy.optimize import least_squares

    nrm = normals(p) if nrm is None else nrm
    a = _axis_from_normals(nrm)
    o = _axis_point(p, nrm, a)
    v = p - o
    h = v @ a
    rad = np.linalg.norm(v - np.outer(h, a), axis=1)
    k, r0 = np.polyfit(h, rad, 1)
    al = math.atan(k)
    th, ph = _angles(a)
    res = least_squares(_cone_dist, np.r_[th, ph, o, r0, al], args=(p,),
                        bounds=([-np.inf] * 6 + [-1.5], [np.inf] * 6 + [1.5]))
    th, ph, ox, oy, oz, r0, al = res.x
    a, o = _dir(th, ph), np.array([ox, oy, oz])
    if al < 0:  # widening along +axis
        a, al = -a, -al
    hm = float(((p - o) @ a).mean())  # move the origin to the middle of the patch
    o, r0 = o + hm * a, r0 + hm * math.tan(al)
    d = _cone_dist(np.r_[_angles(a), o, r0, al], p)
    if abs(math.degrees(al)) < 0.05:
        raise CloudError("the points are a cylinder, not a cone (half angle under 0.05°)")
    return Fit("CONE", {"origin": o, "axis": a, "radius": float(r0), "angle": math.degrees(al)},
               float(np.sqrt(np.mean(d * d))), float(np.abs(d).max()))


def fit_freeform(p: np.ndarray, tol: float) -> Fit:
    from scipy.spatial import Delaunay

    from . import meshfit

    pl = fit_plane(p)
    x, y = _frame(pl.params["normal"])
    q = np.c_[(p - pl.params["origin"]) @ x, (p - pl.params["origin"]) @ y]
    try:
        tri = Delaunay(q).simplices
    except Exception as exc:  # noqa: BLE001 - qhull errors on flat-in-a-line points
        raise CloudError(f"the points do not cover an area ({exc.__class__.__name__})") from None
    # drop long, thin triangles around the outside (the Delaunay hull bridges gaps)
    e = np.linalg.norm(q[tri] - q[np.roll(tri, 1, axis=1)], axis=2).max(axis=1)
    tri = tri[e <= 4 * np.median(e)]
    try:
        fit = meshfit.fit_patch(p, tri, tol, trim=False)  # the surface over the patch's box
    except meshfit.FitError as exc:
        raise CloudError(str(exc)) from None
    return Fit("FREEFORM", {"poles": f"{fit.poles[0]} x {fit.poles[1]}"}, 0.0, 0.0, face=fit.shape)


def fit(p: np.ndarray, kind: str, tol: float) -> Fit:
    """The best ``kind`` (AUTO: the simplest that fits nearly as well as any) through the points,
    with its trimmed face."""
    p = np.asarray(p, float)
    if len(p) < 6:
        raise CloudError(f"{len(p)} points are too few to fit (6 or more)")
    if kind == "FREEFORM":
        return _measured(fit_freeform(p, tol), p, tol)
    nrm = normals(p) if kind in ("AUTO", "CYLINDER", "CONE") else None
    makers = {"PLANE": lambda: fit_plane(p), "SPHERE": lambda: fit_sphere(p),
              "CYLINDER": lambda: fit_cylinder(p, nrm), "CONE": lambda: fit_cone(p, nrm)}
    if kind != "AUTO":
        f = makers[kind]()
    else:
        tried = []
        for k in ("PLANE", "CYLINDER", "SPHERE", "CONE"):  # the simplest first
            try:
                tried.append(makers[k]())
            except (CloudError, np.linalg.LinAlgError, ValueError):
                continue
        if not tried:
            raise CloudError("no shape fits these points")
        best = min(f.rms for f in tried)
        good = max(best * 1.5, tol / 4)
        f = next(f for f in tried if f.rms <= good)
        f.extra["tried"] = {t.kind: t.rms for t in tried}
    f.face = face_for(f, p)
    return f


def _measured(f: Fit, p: np.ndarray, tol: float) -> Fit:
    from . import deviation as dv

    tg = dv.target(f.face, min(tol / 4, 1e-3 * float(np.linalg.norm(np.ptp(p, axis=0)))))
    d, _ = dv.distances(tg, p)
    f.rms, f.worst = float(np.sqrt(np.mean(d * d))), float(np.abs(d).max())
    return f


def _arc(ang: np.ndarray) -> tuple[float, float]:
    """The smallest angle range (start, end) in radians covering every angle."""
    a = np.sort(np.mod(ang, 2 * math.pi))
    gaps = np.diff(np.r_[a, a[0] + 2 * math.pi])
    i = int(np.argmax(gaps))
    if gaps[i] < math.radians(10):  # all the way round
        return 0.0, 2 * math.pi
    start = a[(i + 1) % len(a)]
    end = a[i] if a[i] >= start else a[i] + 2 * math.pi
    return float(start), float(end)


def face_for(f: Fit, p: np.ndarray):
    """The fitted surface trimmed to the patch (with a 2% margin)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_ConicalSurface, Geom_CylindricalSurface, Geom_Plane, Geom_SphericalSurface
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt

    def ax3(o, z):
        x, _y = _frame(np.asarray(z))
        return gp_Ax3(gp_Pnt(*map(float, o)), gp_Dir(*map(float, z)), gp_Dir(*map(float, x)))

    q = f.params
    if f.kind == "PLANE":
        o, n = q["origin"], q["normal"]
        x, y = _frame(n)
        u, v = (p - o) @ x, (p - o) @ y
        m = 0.02 * max(np.ptp(u), np.ptp(v))
        surf = Geom_Plane(ax3(o, n))
        bounds = (u.min() - m, u.max() + m, v.min() - m, v.max() + m)
    elif f.kind == "SPHERE":
        c, r = q["centre"], q["radius"]
        w = p - c
        z = w.mean(axis=0)
        z = z / np.linalg.norm(z) if np.linalg.norm(z) > 1e-9 else np.array([0, 0, 1.0])
        x, y = _frame(z)
        lat = np.arcsin(np.clip((w @ z) / np.linalg.norm(w, axis=1), -1, 1))
        u0, u1 = _arc(np.arctan2(w @ y, w @ x))
        surf = Geom_SphericalSurface(ax3(c, z), float(r))
        bounds = (u0, u1, max(-math.pi / 2, lat.min() - 0.02), min(math.pi / 2, lat.max() + 0.02))
    elif f.kind in ("CYLINDER", "CONE"):
        o, a = q["origin"], q["axis"]
        x, y = _frame(a)
        w = p - o
        h = w @ a
        u0, u1 = _arc(np.arctan2(w @ y, w @ x))
        m = 0.02 * np.ptp(h)
        if f.kind == "CYLINDER":
            surf = Geom_CylindricalSurface(ax3(o, a), float(q["radius"]))
            bounds = (u0, u1, h.min() - m, h.max() + m)
        else:
            al = math.radians(q["angle"])
            surf = Geom_ConicalSurface(ax3(o, a), al, float(q["radius"]))
            bounds = (u0, u1, (h.min() - m) / math.cos(al), (h.max() + m) / math.cos(al))
    else:
        raise CloudError(f"no face for {f.kind}")
    mk = BRepBuilderAPI_MakeFace(surf, *map(float, bounds), 1e-7)
    if not mk.IsDone():
        raise CloudError(f"the {f.kind.lower()} face could not be made")
    return mk.Face()


def patch(pts: np.ndarray, centre, radius: float) -> np.ndarray:
    """The points within ``radius`` of ``centre`` (every point when radius is 0)."""
    if not radius:
        return pts
    d = np.linalg.norm(pts - np.asarray(centre, float), axis=1)
    return pts[d <= radius]
