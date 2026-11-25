"""Sizes, tolerances and datums in STEP files (AP242 semantic PMI, PLAN item 73).

Other CAD and inspection programs read the sizes and tolerances of a part
from its STEP file when they are written as AP242 "semantic" annotations:
each one tied to the faces it is about, with its value, limits, kind and
datums. This module turns plain records into the kernel's document form of
those annotations and back:

* ``SIZE``: a distance between two points (a linear location size), tied to
  the faces nearest each end, with plus/minus limits when it has them;
* ``DIAMETER``: a hole's or shaft's diameter, tied to its round face, with
  limits (an ISO fit such as H7 is written as its limits and found again
  when read);
* ``GDT``: a geometric tolerance (flatness, position ...) on a face, its
  zone (round or not) and up to three datums in order;
* ``DATUM``: a datum letter on a face, written with each tolerance that
  refers to it, in its place in the frame. (A datum no tolerance uses is
  written too, but the kernel's reader does not give it back.)

The records carry points in model space, not faces, so the same record works
for the model written and for the model read back: the face is the one
nearest the point.
"""

from __future__ import annotations

import numpy as np
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.gp import gp_Pnt
from OCP.TCollection import TCollection_HAsciiString
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.XCAFDimTolObjects import (
    XCAFDimTolObjects_DatumObject,
    XCAFDimTolObjects_DimensionObject,
    XCAFDimTolObjects_DimensionType_Location_LinearDistance,
    XCAFDimTolObjects_DimensionType_Size_Diameter,
    XCAFDimTolObjects_GeomToleranceObject,
    XCAFDimTolObjects_GeomToleranceTypeValue_Diameter,
    XCAFDimTolObjects_GeomToleranceTypeValue_None,
)
from OCP.XCAFDoc import XCAFDoc_Datum, XCAFDoc_DimTolTool, XCAFDoc_Dimension, XCAFDoc_DocumentTool, XCAFDoc_GeomTolerance

from . import recognize as rc

try:
    from OCP.collections import Sequence_TDF_Label as _Labels
except ImportError:  # OCP 7.x
    from OCP.TDF import TDF_LabelSequence as _Labels  # type: ignore[no-redef]

import OCP.XCAFDimTolObjects as _X

# the app's tolerance names and the kernel's
KINDS = {
    "STRAIGHTNESS": "Straightness", "FLATNESS": "Flatness", "CIRCULARITY": "CircularityOrRoundness",
    "CYLINDRICITY": "Cylindricity", "LINEPROFILE": "ProfileOfLine", "PROFILE": "ProfileOfSurface",
    "PARALLELISM": "Parallelism", "PERPENDICULARITY": "Perpendicularity", "ANGULARITY": "Angularity",
    "POSITION": "Position", "CONCENTRICITY": "Concentricity", "SYMMETRY": "Symmetry",
    "RUNOUT": "CircularRunout", "TOTALRUNOUT": "TotalRunout",
}
_BACK = {v: k for k, v in KINDS.items()}
_BACK["Coaxiality"] = "CONCENTRICITY"


def _kind(name: str):
    return getattr(_X, f"XCAFDimTolObjects_GeomToleranceType_{KINDS[name]}")


def _faces(shape) -> list:
    out = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def _dist(shape, q) -> float:
    v = BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, q))).Vertex()
    d = BRepExtrema_DistShapeShape(v, shape)
    return d.Value() if d.IsDone() else float("inf")


def _nearest_face(parts: list[tuple], q, round_only: bool = False):
    """(part index, face) of the face nearest point q, over all parts; round faces only if asked."""
    best = None
    for i, (_label, shape) in enumerate(parts):
        for f in _faces(shape):
            if round_only and rc._cylinder_info(rc.as_face(f)) is None:
                continue
            d = _dist(f, q)
            if best is None or d < best[0]:
                best = (d, i, f)
    return None if best is None else (best[1], best[2])


# ---- writing ------------------------------------------------------------------------------------

def add(doc, st, parts: list[tuple], records: list[dict], unit_mm: float = 1.0) -> int:
    """Put the records into the document as AP242 annotations on the parts ((label, shape) each).
    ``unit_mm``: the model's unit in mm. Returns how many went in."""
    dt = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
    face_labels: dict[tuple[int, int], object] = {}

    def face_label(pi: int, face):
        key = (pi, hash(face))
        for (i, _h), lab in face_labels.items():
            if i == pi and lab[0].IsSame(face):
                return lab[1]
        lab = st.AddSubShape(parts[pi][0], face)
        face_labels[key] = (face, lab)
        return lab

    def seq(*labels):
        s = _Labels()
        for lab in labels:
            s.Append(lab)
        return s

    datum_faces: dict[str, object] = {}
    n = 0
    for r in records:
        if r["kind"] == "DATUM":
            hit = _nearest_face(parts, r["point"])
            if hit is None:
                continue
            datum_faces[r["letter"]] = face_label(*hit)
    for r in records:
        kind = r["kind"]
        if kind == "SIZE":
            ha, hb = _nearest_face(parts, r["a"]), _nearest_face(parts, r["b"])
            if ha is None or hb is None:
                continue
            obj = XCAFDimTolObjects_DimensionObject()
            obj.SetType(XCAFDimTolObjects_DimensionType_Location_LinearDistance)
            obj.SetValue(float(r["value"]))
            obj.SetPoint(gp_Pnt(*map(float, r["a"])))
            obj.SetPoint2(gp_Pnt(*map(float, r["b"])))
            _limits(obj, r)
            lab = dt.AddDimension()
            XCAFDoc_Dimension.Set_s(lab).SetObject(obj)
            dt.SetDimension(seq(face_label(*ha)), seq(face_label(*hb)), lab)
            n += 1
        elif kind == "DIAMETER":
            hit = _nearest_face(parts, r["point"], round_only=True)
            if hit is None:
                continue
            obj = XCAFDimTolObjects_DimensionObject()
            obj.SetType(XCAFDimTolObjects_DimensionType_Size_Diameter)
            obj.SetValue(float(r["value"]))
            _limits(obj, r)
            lab = dt.AddDimension()
            XCAFDoc_Dimension.Set_s(lab).SetObject(obj)
            dt.SetDimension(seq(face_label(*hit)), seq(), lab)
            n += 1
    # the kernel's writer gives tolerance zones the unit of the sizes already written, or metres
    # when there are none (and reads both back in mm)
    zone_scale = 1.0 if n else unit_mm / 1000.0
    for r in records:
        if r["kind"] == "GDT":
            hit = _nearest_face(parts, r["point"])
            if hit is None:
                continue
            # each place a datum is used gets its own datum record, holding its order in the frame
            # (made before the tolerance, as the kernel's writer expects)
            dls = []
            for k, letter in enumerate(r.get("datums", ())):
                on = datum_faces.get(letter)
                dls.append(_datum(dt, seq(on) if on is not None else seq(), letter, k + 1))
            obj = XCAFDimTolObjects_GeomToleranceObject()
            obj.SetType(_kind(r["type"]))
            obj.SetValue(float(r["value"]) * zone_scale)
            obj.SetTypeOfValue(XCAFDimTolObjects_GeomToleranceTypeValue_Diameter if r.get("dia")
                               else XCAFDimTolObjects_GeomToleranceTypeValue_None)
            lab = dt.AddGeomTolerance()
            XCAFDoc_GeomTolerance.Set_s(lab).SetObject(obj)
            dt.SetGeomTolerance(face_label(*hit), lab)
            for dl in dls:
                dt.SetDatumToGeomTol(dl, lab)
            n += 1
    used = {d for r in records if r["kind"] == "GDT" for d in r.get("datums", ())}
    for letter, flab in datum_faces.items():
        if letter not in used:  # a datum no tolerance uses yet: written on its own
            _datum(dt, seq(flab), letter, 1)
            n += 1
    return n


def _limits(obj, r: dict) -> None:
    up, lo = r.get("upper"), r.get("lower")
    if up is None or lo is None or (up == 0 and lo == 0):
        return
    obj.SetUpperTolValue(float(up))
    obj.SetLowerTolValue(float(lo))


def _datum(dt, faces, letter: str, position: int):
    lab = dt.AddDatum()
    obj = XCAFDimTolObjects_DatumObject()
    obj.SetName(TCollection_HAsciiString(letter))
    obj.SetPosition(position)
    XCAFDoc_Datum.Set_s(lab).SetObject(obj)
    if faces.Length():
        dt.SetDatum(faces, lab)
    return lab


# ---- reading ------------------------------------------------------------------------------------

def _face_point(st, label):
    """A point on the face (or shape) a label holds: its middle."""
    shape = st.GetShape_s(label)
    if shape is None or shape.IsNull():
        return None
    faces = _faces(shape)
    if not faces:
        return None
    p, _n = rc.face_normal_at_middle(rc.as_face(faces[0]))
    return tuple(float(c) for c in p)


def _shape_points(dt, st, label) -> tuple[list, list]:
    first, second = _Labels(), _Labels()
    XCAFDoc_DimTolTool.GetRefShapeLabel_s(label, first, second)
    a = [q for q in (_face_point(st, first.Value(i)) for i in range(1, first.Length() + 1)) if q is not None]
    b = [q for q in (_face_point(st, second.Value(i)) for i in range(1, second.Length() + 1)) if q is not None]
    return a, b


def _xyz(p) -> tuple:
    return (p.X(), p.Y(), p.Z())


def read(doc) -> list[dict]:
    """The annotations in a document read from a STEP file, as records."""
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    dt = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
    out: list[dict] = []
    labels = _Labels()
    dt.GetDimensionLabels(labels)
    for i in range(1, labels.Length() + 1):
        lab = labels.Value(i)
        obj = XCAFDoc_Dimension.Set_s(lab).GetObject()
        typ = obj.GetType()
        a, b = _shape_points(dt, st, lab)
        rec = {"value": float(obj.GetValue())}
        if obj.IsDimWithPlusMinusTolerance():
            up, lo = float(obj.GetUpperTolValue()), float(obj.GetLowerTolValue())
            rec["upper"], rec["lower"] = up, -abs(lo) if lo > 0 else lo
        if typ == XCAFDimTolObjects_DimensionType_Size_Diameter:
            if not a:
                continue
            out.append({"kind": "DIAMETER", "point": a[0], **rec})
        elif typ == XCAFDimTolObjects_DimensionType_Location_LinearDistance or obj.HasPoint():
            pa = _xyz(obj.GetPoint()) if obj.HasPoint() else (a[0] if a else None)
            pb = _xyz(obj.GetPoint2()) if obj.HasPoint2() else (b[0] if b else None)
            if pa is None or pb is None:
                continue
            out.append({"kind": "SIZE", "a": pa, "b": pb, **rec})
    seen: set[tuple] = set()
    labels = _Labels()
    dt.GetDatumLabels(labels)
    for i in range(1, labels.Length() + 1):
        lab = labels.Value(i)
        name = XCAFDoc_Datum.Set_s(lab).GetObject().GetName()
        letter = name.ToCString().strip().upper() if name is not None else ""
        shapes, _none = _Labels(), _Labels()
        XCAFDoc_DimTolTool.GetRefShapeLabel_s(lab, shapes, _none)
        if not letter or not shapes.Length():
            continue
        pt = _face_point(st, shapes.Value(1))
        key = (letter, tuple(round(c, 6) for c in pt) if pt else None)
        if pt is None or key in seen or any(k[0] == letter for k in seen):
            continue
        seen.add(key)
        out.append({"kind": "DATUM", "letter": letter, "point": pt})
    labels = _Labels()
    dt.GetGeomToleranceLabels(labels)
    for i in range(1, labels.Length() + 1):
        lab = labels.Value(i)
        obj = XCAFDoc_GeomTolerance.Set_s(lab).GetObject()
        name = str(obj.GetType()).rsplit("_", 1)[-1]
        kind = _BACK.get(name)
        a, _b = _shape_points(dt, st, lab)
        if kind is None or not a:
            continue
        ds = _Labels()
        XCAFDoc_DimTolTool.GetDatumOfTolerLabels_s(lab, ds)
        refs = []
        for j in range(1, ds.Length() + 1):
            dobj = XCAFDoc_Datum.Set_s(ds.Value(j)).GetObject()
            nm = dobj.GetName()
            refs.append((dobj.GetPosition(), nm.ToCString().strip().upper() if nm is not None else ""))
        datums = [n for _p, n in sorted(refs) if n]
        out.append({"kind": "GDT", "type": kind, "value": float(obj.GetValue()), "point": a[0],
                    "dia": obj.GetTypeOfValue() == XCAFDimTolObjects_GeomToleranceTypeValue_Diameter,
                    "datums": list(dict.fromkeys(datums))})
    return out


def summary(records: list[dict]) -> str:
    """'2 sizes, 1 diameter, 1 tolerance, 1 datum'."""
    names = (("SIZE", "size"), ("DIAMETER", "diameter"), ("GDT", "tolerance"), ("DATUM", "datum"))
    bits = []
    for k, word in names:
        c = sum(1 for r in records if r["kind"] == k)
        if c:
            bits.append(f"{c} {word}{'s' if c != 1 else ''}")
    return ", ".join(bits) or "nothing"


def as_array(p) -> np.ndarray:
    return np.asarray(p, float)
