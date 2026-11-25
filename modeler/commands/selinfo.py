"""The numbers of what is picked (PLAN item 86), without Qt.

``selection_info(p)`` answers, for the current selection (or any kind and IDs
given), the numbers people look up all day: a face's area and type (radius or
diameter for a round one), an edge's length (radius and arc angle for an arc),
a vertex's position, a body's volume, area, size and mass. Several picks get
a total (area, length or volume); two picks also get the distance between
them and, where both have a direction, the angle.

The GUI shows ``line(info)`` in the status bar, the hover tooltip uses
``hover_text``, SELINFO prints ``report_text`` and the assistant gets
``info`` itself in ``user_context``. Everything here only reads the model.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Iterable

from ..core.model import ModelError

if TYPE_CHECKING:
    from .processor import Processor

LIMIT = 50  # rows given one by one; totals still count everything
TOTAL_LIMIT = 2000  # past this many picks no totals (a box pick of a whole mesh)


def _n(v: float) -> str:
    """A short readable number: 12.5, 0.00785, 1.235e+06."""
    if v == 0:
        return "0"
    a = abs(v)
    if 1 <= a < 1e6:
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        if len(s.replace("-", "").replace(".", "")) > 6:  # 12345.6789 -> 12345.7
            s = f"{v:.6g}"
        return s
    return f"{v:.4g}"  # small (0.00785) or huge (1.235e+06): four figures


def _r(v: float, k: int = 6) -> float:
    return float(round(v, k))


def _vec(v: Iterable[float]) -> list[float]:
    return [_r(x) for x in v]


def _unit(p: "Processor") -> str:
    from ..core.units import unit_label

    return unit_label(p.model.show_units or p.model.units)


def shown(p: "Processor", d):
    """d (a row or an answer) with lengths, areas and volumes in the units numbers are shown in."""
    from ..core.units import factor, scale_info

    m = p.model
    if not m.show_units or m.show_units == m.units:
        return d
    return scale_info(d, factor(m.units, m.show_units))


# ---- one entity -------------------------------------------------------------------------
def face_numbers(p: "Processor", gid: int) -> dict[str, Any]:
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType as S

    from ..geometry import recognize as rc
    from .queries import centre, props

    m = p.model
    bid, _ = m.entity_owner("FACE", gid)
    f = rc.as_face(m.entity_shape("FACE", gid))
    s = BRepAdaptor_Surface(f)
    t = s.GetType()
    row: dict[str, Any] = {"id": gid, "body": bid, "type": rc.surface_type(f),
                           "area": _r(props("FACE", f).Mass()), "centre": _vec(centre("FACE", f))}
    if t == S.GeomAbs_Plane:
        row["normal"] = _vec(rc.face_normal_at_middle(f)[1])
    elif t == S.GeomAbs_Cylinder:
        row["r"] = _r(s.Cylinder().Radius())
    elif t == S.GeomAbs_Cone:
        c = s.Cone()
        row["r"] = _r(c.RefRadius())
        row["half_angle"] = _r(math.degrees(c.SemiAngle()))
    elif t == S.GeomAbs_Sphere:
        row["r"] = _r(s.Sphere().Radius())
    elif t == S.GeomAbs_Torus:
        tor = s.Torus()
        row["r"] = _r(tor.MinorRadius())
        row["R"] = _r(tor.MajorRadius())
    if "r" in row:
        row["d"] = _r(2 * row["r"])
    return row


def edge_numbers(p: "Processor", gid: int) -> dict[str, Any]:
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_CurveType as C

    from ..geometry import recognize as rc
    from .queries import props

    m = p.model
    bid, _ = m.entity_owner("EDGE", gid)
    e = rc.as_edge(m.entity_shape("EDGE", gid))
    row: dict[str, Any] = {"id": gid, "body": bid, "type": rc.curve_type(e),
                           "length": _r(props("EDGE", e).Mass())}
    if BRep_Tool.Degenerated_s(e):
        row["degenerate"] = True
        return row
    c = BRepAdaptor_Curve(e)
    t0, t1 = c.FirstParameter(), c.LastParameter()
    a, b = c.Value(t0), c.Value(t1)
    row["ends"] = [_vec((a.X(), a.Y(), a.Z())), _vec((b.X(), b.Y(), b.Z()))]
    if c.GetType() == C.GeomAbs_Circle:
        circ = c.Circle()
        row["r"] = _r(circ.Radius())
        row["d"] = _r(2 * circ.Radius())
        row["centre"] = _vec((circ.Location().X(), circ.Location().Y(), circ.Location().Z()))
        span = math.degrees(abs(t1 - t0))
        row["closed"] = span >= 360 - 1e-6
        if not row["closed"]:
            row["arc_deg"] = _r(span, 4)
    elif c.GetType() == C.GeomAbs_Line:
        d = c.Line().Direction()
        row["dir"] = _vec((d.X(), d.Y(), d.Z()))
    return row


def vertex_numbers(p: "Processor", gid: int) -> dict[str, Any]:
    from ..geometry import features as ft

    m = p.model
    bid, _ = m.entity_owner("VERTEX", gid)
    return {"id": gid, "body": bid, "at": _vec(ft.vertex_point(m.entity_shape("VERTEX", gid)))}


def body_numbers(p: "Processor", bid: int) -> dict[str, Any]:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    from ..core.model import UNITS
    from ..geometry import meshbody, robust
    from .queries import bbox

    m = p.model
    b = m.body(bid)
    name = b.name or ""
    row: dict[str, Any] = {"id": bid, "name": "" if name.lower() == f"body{bid}" else name}
    shape = b.shape
    if shape is None:
        return row
    bb = bbox(shape)
    row["size"] = _vec(bb[3 + i] - bb[i] for i in range(3))
    vol = None
    if meshbody.is_mesh(shape):
        inf = meshbody.info(shape)
        row["kind"] = "mesh"
        row["triangles"] = inf.triangles if hasattr(inf, "triangles") else None
        row["area"] = _r(inf.area)
        if inf.closed:
            vol = abs(inf.volume)
    else:
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(shape, g)
        row["area"] = _r(g.Mass())
        if robust.solids(shape):
            row["kind"] = "solid"
            gv = GProp_GProps()
            BRepGProp.VolumeProperties_s(shape, gv)
            vol = gv.Mass()
            c = gv.CentreOfMass()
            row["centre"] = _vec((c.X(), c.Y(), c.Z()))
        else:
            row["kind"] = "surface" if row["area"] > 0 else "wire"
    if row.get("triangles") is None:
        row.pop("triangles", None)
    if vol is not None:
        row["volume"] = _r(vol)
        dens = m.density(bid)
        if dens:
            scale = UNITS[m.units] / 1000.0  # model unit in metres
            row["mass_kg"] = _r(vol * scale ** 3 * dens, 9)
            row["material"] = b.material.lower()
    return row


_ROWS = {"FACE": face_numbers, "EDGE": edge_numbers, "VERTEX": vertex_numbers, "BODY": body_numbers}


def entity_numbers(p: "Processor", kind: str, gid: int) -> dict[str, Any]:
    return _ROWS[kind.upper()](p, int(gid))


# ---- two picks --------------------------------------------------------------------------
def _pair(p: "Processor", kind: str, a: int, b: int) -> dict[str, Any]:
    from ..geometry import features as ft
    from . import measure_handlers as mh

    m = p.model
    out: dict[str, Any] = {}
    try:
        if kind == "BODY":
            sa, sb = m.body(a).shape, m.body(b).shape
            ta = tb = None
        else:
            ta, tb = mh._entity(p, kind, a), mh._entity(p, kind, b)
            sa, sb = ta.get_shape(), tb.get_shape()
        d, pa, pb = ft.distance(sa, sb)
        out["distance"] = _r(d)
        out["from"], out["to"] = _vec(pa), _vec(pb)
        out["dx"], out["dy"], out["dz"] = (_r(pb[i] - pa[i]) for i in range(3))
    except Exception:  # noqa: BLE001 - a distance the kernel cannot measure: leave it out
        return out
    if kind in ("FACE", "EDGE") and ta is not None and tb is not None:
        da, db = ta.direction(), tb.direction()
        if da and db:
            (va, ka), (vb, kb) = da, db
            c = max(-1.0, min(1.0, sum(x * y for x, y in zip(va, vb))))
            between = math.degrees(math.acos(c))
            if ka == kb == "normal":  # two flat faces (or two circles): the angle between their normals
                out["angle"] = _r(between, 4)
                out["angle_between"] = "normals"
                if between < 1e-4:
                    out["parallel"] = "same way"
                elif between > 180 - 1e-4:
                    out["parallel"] = "facing away" if kind == "FACE" else "opposite"
            elif ka == kb == "line":  # straight edges, or the axes of round faces
                out["angle"] = _r(min(between, 180 - between), 4)
                out["angle_between"] = "lines" if kind == "EDGE" else "axes"
                if out["angle"] < 1e-4:
                    out["parallel"] = "parallel"
        _centres(kind, ta, tb, out)
    return out


def _centres(kind: str, ta, tb, out: dict[str, Any]) -> None:
    """Two holes, pins or round edges: how far apart their centres are (what a drawing
    dimensions), as well as the gap between their surfaces."""
    from ..geometry import features as ft

    if kind == "FACE":
        aa, ab = ft.face_axis(ta.shape), ft.face_axis(tb.shape)
        if not (aa and ab):
            return
        (p1, d1), (p2, d2) = aa, ab
        if abs(abs(sum(x * y for x, y in zip(d1, d2))) - 1) > 1e-6:
            return  # axes not parallel: no single centre distance
        w = [p2[i] - p1[i] for i in range(3)]
        along = sum(w[i] * d1[i] for i in range(3))
        off = [w[i] - along * d1[i] for i in range(3)]  # across the axes
        out["centres"] = _r(math.sqrt(sum(x * x for x in off)))
        out["cdx"], out["cdy"], out["cdz"] = (_r(x) for x in off)
    elif kind == "EDGE":
        ca, cb = ft.edge_circle(ta.shape), ft.edge_circle(tb.shape)
        if not (ca and cb):
            return
        off = [cb[0][i] - ca[0][i] for i in range(3)]
        out["centres"] = _r(math.sqrt(sum(x * x for x in off)))
        out["cdx"], out["cdy"], out["cdz"] = (_r(x) for x in off)


# ---- the whole selection ----------------------------------------------------------------
def selection_info(p: "Processor", kind: str | None = None, ids: list[int] | None = None,
                   limit: int = LIMIT) -> dict[str, Any]:
    """The numbers of the picked things (or of ``kind`` / ``ids``)."""
    m = p.model
    kind = (kind or m.selection_kind or "BODY").upper()
    ids = list(m.selection if ids is None else ids)
    out: dict[str, Any] = {"kind": kind, "ids": ids, "count": len(ids), "unit": _unit(p)}
    if not ids:
        return out
    rows: list[dict[str, Any]] = []
    total = {"area": 0.0, "length": 0.0, "volume": 0.0, "mass_kg": 0.0}
    have = {"volume": 0, "mass_kg": 0}
    counted = 0
    for i, gid in enumerate(ids):
        if i >= TOTAL_LIMIT:
            break
        try:
            row = entity_numbers(p, kind, gid)
        except (ModelError, Exception):  # noqa: BLE001 - a stale ID: skip it
            continue
        counted += 1
        if len(rows) < limit:
            rows.append(row)
        for k in ("area", "length"):
            total[k] += row.get(k, 0.0) if kind != "BODY" or k == "area" else 0.0
        for k in ("volume", "mass_kg"):
            if k in row:
                total[k] += row[k]
                have[k] += 1
    out["items"] = rows
    if len(ids) > limit:
        out["more"] = len(ids) - limit
    if len(ids) > 1 and counted:
        tot: dict[str, Any] = {}
        if kind == "FACE":
            tot["area"] = _r(total["area"])
        elif kind == "EDGE":
            tot["length"] = _r(total["length"])
        elif kind == "BODY":
            tot["area"] = _r(total["area"])
            if have["volume"]:
                tot["volume"] = _r(total["volume"])
            if have["mass_kg"]:
                tot["mass_kg"] = _r(total["mass_kg"], 9)
                if have["mass_kg"] < counted:
                    tot["mass_note"] = f"{counted - have['mass_kg']} of {counted} have no material"
        if len(ids) > TOTAL_LIMIT:
            tot["note"] = f"first {TOTAL_LIMIT} of {len(ids)} counted"
        out["total"] = tot
    if len(ids) == 2:
        pair = _pair(p, kind, ids[0], ids[1])
        if pair:
            out["pair"] = pair
    return shown(p, out)


# ---- as text ----------------------------------------------------------------------------
def _sq(u: str, pretty: bool) -> str:
    return f"{u}²" if pretty else f"{u}2"


def _cu(u: str, pretty: bool) -> str:
    return f"{u}³" if pretty else f"{u}3"


def _deg(pretty: bool) -> str:
    return "°" if pretty else " deg"


def _xyz(v) -> str:
    return f"({_n(v[0])}, {_n(v[1])}, {_n(v[2])})"


def row_text(kind: str, row: dict[str, Any], u: str, pretty: bool = True) -> str:
    """One entity's numbers on one line, e.g. ``face 6: cylinder r 5 (d 10), area 314.2 mm²``."""
    kind = kind.upper()
    head = f"{kind.lower()} {row['id']}"
    if kind == "BODY":
        if row.get("name"):
            head += f" ({row['name']})"
        bits = []
        if "volume" in row:
            bits.append(f"volume {_n(row['volume'])} {_cu(u, pretty)}")
        if "area" in row:
            bits.append(f"area {_n(row['area'])} {_sq(u, pretty)}")
        if "mass_kg" in row:
            bits.append(f"mass {_n(row['mass_kg'])} kg ({row['material']})")
        if "size" in row:
            s = row["size"]
            bits.append(f"size {_n(s[0])} x {_n(s[1])} x {_n(s[2])} {u}")
        if row.get("kind") in ("surface", "wire", "mesh"):
            bits.insert(0, row["kind"] + (f" of {row['triangles']} triangles" if row.get("triangles") else ""))
        return head + ": " + ", ".join(bits)
    if kind == "FACE":
        t = row["type"]
        if "R" in row:
            t += f" r {_n(row['r'])}, R {_n(row['R'])}"
        elif "r" in row:
            t += f" r {_n(row['r'])} (d {_n(row['d'])})"
        if "half_angle" in row:
            t += f", half angle {_n(row['half_angle'])}{_deg(pretty)}"
        return f"{head}: {t}, area {_n(row['area'])} {_sq(u, pretty)}"
    if kind == "EDGE":
        t = row["type"]
        if "r" in row:
            t = ("circle" if row.get("closed") else "arc") + f" r {_n(row['r'])} (d {_n(row['d'])})"
            if "arc_deg" in row:
                t += f", {_n(row['arc_deg'])}{_deg(pretty)}"
        return f"{head}: {t}, length {_n(row['length'])} {u}"
    return f"{head}: at {_xyz(row['at'])}"


def pair_text(info: dict[str, Any], pretty: bool = True) -> str:
    pr = info.get("pair") or {}
    u = info["unit"]
    bits = []
    if "distance" in pr:
        d = f"distance {_n(pr['distance'])} {u}"
        if pr["distance"] > 0:
            moves = [(k, pr[k]) for k in ("dx", "dy", "dz") if abs(pr[k]) > 1e-9]
            if 0 < len(moves) < 3 or info["kind"] == "VERTEX":
                d += " (" + ", ".join(f"{k} {_n(v)}" for k, v in moves) + ")"
        else:
            d += " (touching)"
        bits.append(d)
    if "centres" in pr:
        c = f"centres {_n(pr['centres'])} {u} apart"
        moves = [(k[1:], pr[k]) for k in ("cdx", "cdy", "cdz") if abs(pr[k]) > 1e-9]
        if 0 < len(moves) < 3:
            c += " (" + ", ".join(f"{k} {_n(v)}" for k, v in moves) + ")"
        bits.append(c)
    if pr.get("parallel"):
        par = pr["parallel"]
        if pr.get("angle_between") == "axes":
            bits.append("axes parallel")
        else:
            bits.append("parallel" + (f", {par}" if par != "parallel" else ""))
    elif "angle" in pr:
        bits.append(f"angle {_n(pr['angle'])}{_deg(pretty)}"
                    + (" between axes" if pr.get("angle_between") == "axes" else ""))
    return ", ".join(bits)


def total_text(info: dict[str, Any], pretty: bool = True) -> str:
    t = info.get("total") or {}
    u = info["unit"]
    bits = []
    if "length" in t:
        bits.append(f"total length {_n(t['length'])} {u}")
    if "volume" in t:
        bits.append(f"total volume {_n(t['volume'])} {_cu(u, pretty)}")
    if "area" in t:
        bits.append(f"total area {_n(t['area'])} {_sq(u, pretty)}")
    if "mass_kg" in t:
        bits.append(f"total mass {_n(t['mass_kg'])} kg" + (f" ({t['mass_note']})" if t.get("mass_note") else ""))
    return ", ".join(bits)


def line(info: dict[str, Any], pretty: bool = True) -> str:
    """The status-bar line: one pick's numbers, or the count, totals, distance and angle."""
    n = info.get("count", 0)
    if not n:
        return ""
    kind, u = info["kind"], info["unit"]
    rows = info.get("items") or []
    if n == 1 and rows:
        return row_text(kind, rows[0], u, pretty)
    noun = {"FACE": "faces", "EDGE": "edges", "VERTEX": "vertices", "BODY": "bodies"}[kind] if n != 1 \
        else kind.lower()
    bits = [f"{n} {noun}"]
    if n == 2 and info.get("pair"):
        bits.append(pair_text(info, pretty))
    tt = total_text(info, pretty)
    if tt:
        bits.append(tt)
    return ", ".join(b for b in bits if b)


def report_text(info: dict[str, Any]) -> str:
    """What SELINFO prints: a row per pick, then the totals, distance and angle."""
    n = info.get("count", 0)
    if not n:
        return "nothing is picked: pick faces, edges, vertices or bodies first (or give them: SELINFO, FACE, \"3 5\")"
    kind, u = info["kind"], info["unit"]
    lines = [row_text(kind, r, u, pretty=False) for r in info.get("items") or []]
    if info.get("more"):
        lines.append(f"... and {info['more']} more")
    if n == 2 and info.get("pair"):
        lines.append(pair_text(info, pretty=False))
        pr = info["pair"]
        if "from" in pr and pr.get("distance", 0) > 0:
            lines.append(f"  from {_xyz(pr['from'])} to {_xyz(pr['to'])}; "
                         f"dx {_n(pr['dx'])}, dy {_n(pr['dy'])}, dz {_n(pr['dz'])}")
    tt = total_text(info, pretty=False)
    if tt:
        lines.append(tt)
    return "\n".join(lines)


def hover_text(p: "Processor", kind: str, gid: int) -> str:
    """The tooltip for what the mouse rests on: its numbers, and the body it belongs to."""
    try:
        row = entity_numbers(p, kind, gid)
    except Exception:  # noqa: BLE001 - gone or not measurable
        return ""
    txt = row_text(kind, shown(p, row), _unit(p))
    if kind.upper() != "BODY":
        b = p.model.bodies.get(row.get("body"))
        if b is not None:
            named = b.name and b.name.lower() != f"body{row['body']}"
            txt += f"\non body {row['body']}" + (f" ({b.name})" if named else "")
    return txt
