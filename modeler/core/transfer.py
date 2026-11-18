"""Sending model state to another process and back (the rebuild helper).

``dumps(obj)`` pickles anything the processor keeps (snapshots, bodies,
sketches ...). OCCT shapes cannot be pickled one by one without losing
what they share (a face picked by ID must stay the same face as the one in
its body), so every shape met is collected, the lot written once as one
compound with OCCT's binary format (which keeps shared parts shared), and
put back by position on load. Other OCCT values used in the model (points,
directions, axes, placements) are rebuilt from their numbers.
"""

from __future__ import annotations

import io
import pickle

_SHAPE_TAG = "occt-shape"


def _shape_types():
    from OCP.TopoDS import TopoDS_Shape

    return (TopoDS_Shape,)


class _Pickler(pickle.Pickler):
    def __init__(self, f):
        super().__init__(f, protocol=pickle.HIGHEST_PROTOCOL)
        self.shapes: list = []
        self._ids: dict = {}
        self._types = _shape_types()

    def persistent_id(self, obj):
        if isinstance(obj, self._types):
            key = id(obj)
            i = self._ids.get(key)
            if i is None:
                i = self._ids[key] = len(self.shapes)
                self.shapes.append(obj)
            return (_SHAPE_TAG, i)
        return None

    def reducer_override(self, obj):
        if type(obj).__name__ == "FieldDef" and getattr(obj, "fn", None) is not None:
            # an implicit field: its compiled function is rebuilt from the text on the other side
            return (_field_def, (obj.name, obj.text, obj.box))
        red = _reduce_occt(obj)
        return red if red is not None else NotImplemented


class _Unpickler(pickle.Unpickler):
    def __init__(self, f, shapes):
        super().__init__(f)
        self.shapes = shapes

    def persistent_load(self, pid):
        tag, i = pid
        if tag != _SHAPE_TAG:
            raise pickle.UnpicklingError(f"unknown reference {tag}")
        return self.shapes[i]


def _write_shapes(shapes: list) -> bytes:
    from OCP.BinTools import BinTools
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    if not shapes:
        return b""
    comp = TopoDS_Compound()
    bld = BRep_Builder()
    bld.MakeCompound(comp)
    for s in shapes:
        bld.Add(comp, s)
    buf = io.BytesIO()
    BinTools.Write_s(comp, buf)  # with triangulations: mesh bodies are triangles only
    return buf.getvalue()


def _read_shapes(data: bytes) -> list:
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Iterator, TopoDS_Shape

    if not data:
        return []
    comp = TopoDS_Shape()
    BinTools.Read_s(comp, io.BytesIO(data))
    out = []
    it = TopoDS_Iterator(comp, True, True)
    while it.More():
        out.append(it.Value())
        it.Next()
    return out


def _reduce_occt(obj):
    """Small OCCT values, rebuilt from their numbers."""
    mod = type(obj).__module__
    if not mod.startswith("OCP"):
        return None
    name = type(obj).__name__
    if name.startswith("IndexedMap_TopoDS_Shape"):  # a body's numbered faces/edges: its shapes in order
        return (_make_map, (type(obj), [obj.FindKey(i) for i in range(1, obj.Extent() + 1)]))
    if name in ("gp_Pnt", "gp_Dir", "gp_Vec", "gp_XYZ"):
        return (_make, (name, (obj.X(), obj.Y(), obj.Z())))
    if name in ("gp_Pnt2d", "gp_Dir2d", "gp_Vec2d"):
        return (_make, (name, (obj.X(), obj.Y())))
    if name == "gp_Ax3":
        return (_make_ax3, (_xyz(obj.Location()), _xyz(obj.Direction()), _xyz(obj.XDirection())))
    if name == "gp_Ax2":
        return (_make_ax2, (_xyz(obj.Location()), _xyz(obj.Direction()), _xyz(obj.XDirection())))
    if name == "gp_Ax1":
        return (_make_ax1, (_xyz(obj.Location()), _xyz(obj.Direction())))
    if name == "gp_Pln":
        a = obj.Position()
        return (_make_pln, (_xyz(a.Location()), _xyz(a.Direction()), _xyz(a.XDirection())))
    if name == "gp_Trsf":
        rows = [[obj.Value(r, c) for c in range(1, 5)] for r in range(1, 4)]
        return (_make_trsf, (rows,))
    raise TypeError(f"cannot send a {name} to the rebuild helper")


def _field_def(name, text, box):
    """A FieldDef sent without its function; ``fn`` compiles on first use."""
    from ..geometry.implicit import FieldDef

    return FieldDef(name, text, box, None)


def _make_map(cls, shapes):
    m = cls()
    for s in shapes:
        m.Add(s)
    return m


def _xyz(p):
    return (p.X(), p.Y(), p.Z())


def _make(name, vals):
    from OCP import gp

    return getattr(gp, name)(*vals)


def _make_ax2(loc, z, x):
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    return gp_Ax2(gp_Pnt(*loc), gp_Dir(*z), gp_Dir(*x))


def _make_ax3(loc, z, x):
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt

    return gp_Ax3(gp_Pnt(*loc), gp_Dir(*z), gp_Dir(*x))


def _make_ax1(loc, z):
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt

    return gp_Ax1(gp_Pnt(*loc), gp_Dir(*z))


def _make_pln(loc, z, x):
    from OCP.gp import gp_Pln

    return gp_Pln(_make_ax3(loc, z, x))


def _make_trsf(rows):
    from OCP.gp import gp_Trsf

    t = gp_Trsf()
    t.SetValues(*[v for r in rows for v in r])
    return t


def dumps(obj) -> bytes:
    buf = io.BytesIO()
    pk = _Pickler(buf)
    pk.dump(obj)
    shapes = _write_shapes(pk.shapes)
    body = buf.getvalue()
    return len(body).to_bytes(8, "little") + body + shapes


def loads(data: bytes):
    n = int.from_bytes(data[:8], "little")
    body, shapes = data[8:8 + n], data[8 + n:]
    return _Unpickler(io.BytesIO(body), _read_shapes(shapes)).load()


# ---- a whole processor ---------------------------------------------------------------
# what stays with each side: callbacks, the GUI's hooks, and what is rebuilt on demand
_P_LOCAL = {"model", "view", "listeners", "history_listeners", "progress", "evaluator", "refs", "deadline",
            "autosave_path"}
_M_LOCAL = {"_listeners", "lineage"}


def processor_state(p) -> dict:
    """Everything a processor holds that a rebuild reads or changes."""
    return {"p": {k: v for k, v in vars(p).items() if k not in _P_LOCAL},
            "m": {k: v for k, v in vars(p.model).items() if k not in _M_LOCAL}}


def set_processor_state(p, state: dict) -> None:
    """Make processor ``p`` hold ``state`` (from processor_state, maybe through dumps/loads)."""
    for k, v in state["m"].items():
        setattr(p.model, k, v)
    for k, v in state["p"].items():
        setattr(p, k, v)
