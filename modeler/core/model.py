"""The model: bodies, global entity IDs, names and the current selection.

This module knows nothing about Qt. It only uses OCCT (through OCP), so the
whole model can run headless in tests and batch scripts.

Entity IDs
----------
Every body gets a permanent ID. Every face, edge and vertex of every body gets
a global ID per kind (FACE 1, 2, 3 ... across all bodies). That is what lets a
viewport click be written as ``PICK, FACE, 12`` and replayed later.

IDs are kept stable in three ways:

1. **Through operations.** When a body is made from other bodies (boolean,
   fillet, move ...), the operation's OCCT history says which old faces,
   edges and vertices became which new ones. Those keep their IDs; a split
   face keeps its ID on its largest piece. Only truly new entities get new IDs.
2. **Through history edits.** Each history entry remembers the IDs it handed
   out. When the history is replayed after an edit, the entry asks for the
   same IDs again (see :class:`IdPins`), so inserting or changing an earlier
   step does not renumber later ones.
3. **By name.** Bodies can be named, and a body made from a named body (the
   first input of a boolean, say) inherits the name. Selections can be saved
   as named sets.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable

from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS_Shape

try:  # OCP 7.x
    from OCP.TopTools import TopTools_IndexedMapOfShape
except ImportError:  # OCP 8.x dropped the typedef names
    from OCP.collections import (  # type: ignore[no-redef]
        IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape,
    )

ENTITY_KINDS = ("FACE", "EDGE", "VERTEX")
ID_KINDS = ("BODY",) + ENTITY_KINDS
_TOPABS = {"FACE": TopAbs_FACE, "EDGE": TopAbs_EDGE, "VERTEX": TopAbs_VERTEX}

# Selection kinds: whole bodies plus the three entity kinds.
SELECT_KINDS = ("BODY",) + ENTITY_KINDS

UNITS = {"MM": 1.0, "CM": 10.0, "M": 1000.0, "IN": 25.4}


class ModelError(Exception):
    """Raised for invalid requests against the model (unknown IDs, etc.)."""


@dataclass
class Body:
    """One shape in the model. Treated as immutable once added."""

    id: int
    name: str
    shape: TopoDS_Shape
    # kind -> OCCT indexed map of sub-shapes (1-based, in OCCT order)
    maps: dict[str, TopTools_IndexedMapOfShape] = field(default_factory=dict)
    # kind -> global IDs, position i matches map index i+1
    entity_ids: dict[str, list[int]] = field(default_factory=dict)


@dataclass(frozen=True)
class Event:
    """A change notification sent to listeners (the viewport, the GUI)."""

    kind: str  # "body_added", "body_removed", "cleared", "selection", "restored", "visibility"
    body_id: int | None = None


class IdPins:
    """IDs that one history entry handed out last time it ran.

    While the entry runs again, each new ID of a kind is taken from this list
    in order (if that ID is free), so the entry reproduces its old numbering.
    Whatever it actually hands out is recorded in ``used`` for next time.
    """

    def __init__(self, previous: dict[str, list[int]] | None = None, owner: int = 0) -> None:
        self.owner = owner  # the history entry these IDs belong to (its uid)
        self.previous = {k: list(v) for k, v in (previous or {}).items()}
        self._pos = {k: 0 for k in ID_KINDS}
        self.used: dict[str, list[int]] = {k: [] for k in ID_KINDS}

    def take(self, kind: str) -> int | None:
        seq = self.previous.get(kind, [])
        i = self._pos[kind]
        if i < len(seq):
            self._pos[kind] = i + 1
            return seq[i]
        return None

    def merged(self) -> dict[str, list[int]]:
        """What to remember for next time: the IDs this run handed out, then
        the older ones it did not reach. A run that makes fewer entities (a
        loop count went down) must not forget the IDs of the longer run, or
        they could not come back when the count goes up again."""
        out = {}
        for kind in ID_KINDS:
            used = self.used[kind]
            seen = set(used)
            out[kind] = used + [i for i in self.previous.get(kind, [])[len(used):] if i not in seen]
        return out


class Model:
    def __init__(self) -> None:
        self._listeners: list[Callable[[Event], None]] = []
        self.revision = 0  # bumps on every change event
        self.pins: IdPins | None = None
        # Fresh IDs never go below this (set while replaying history so new
        # steps do not take IDs that later steps have pinned).
        self.id_floor: dict[str, int] = {k: 1 for k in ID_KINDS}
        self._reset()

    def _reset(self) -> None:
        self.bodies: dict[int, Body] = {}
        self._next = {k: 1 for k in ID_KINDS}
        # global entity id -> (body id, 1-based index in that body's map)
        self._entities: dict[str, dict[int, tuple[int, int]]] = {k: {} for k in ENTITY_KINDS}
        # ID -> uid of the history entry that handed it out. Two entities with
        # the same ID but different makers are not the same thing: that is
        # how a pick notices that "its" ID now belongs to something else.
        self._origin: dict[str, dict[int, int]] = {k: {} for k in ID_KINDS}
        self.selection_kind: str = "FACE"
        self.selection: list[int] = []  # body IDs or entity IDs of selection_kind
        self.named_sets: dict[str, tuple[str, list[int]]] = {}  # NAME -> (kind, ids)
        self.last_body: int = 0
        self.units: str = "MM"
        self.tolerance: float = 0.0  # extra fuzzy tolerance for booleans (0 = exact)
        self.hidden: set[int] = set()  # body IDs not drawn in the viewport
        self.keep: bool = False  # KEEP, ON: boolean inputs stay as hidden bodies

    # ---- listeners -------------------------------------------------------
    def subscribe(self, fn: Callable[[Event], None]) -> None:
        self._listeners.append(fn)

    def _emit(self, event: Event) -> None:
        self.revision += 1
        for fn in list(self._listeners):
            fn(event)

    # ---- snapshots (undo, history replay) ---------------------------------
    def snapshot(self) -> dict:
        """Everything needed to come back to this exact state.

        Bodies are immutable, so the snapshot shares them; only the
        containers are copied. This is cheap enough to take after every
        history entry.
        """
        return {
            "bodies": dict(self.bodies),
            "next": dict(self._next),
            "entities": {k: dict(v) for k, v in self._entities.items()},
            "origin": {k: dict(v) for k, v in self._origin.items()},
            "selection_kind": self.selection_kind,
            "selection": list(self.selection),
            "named_sets": copy.deepcopy(self.named_sets),
            "last_body": self.last_body,
            "units": self.units,
            "tolerance": self.tolerance,
            "hidden": set(self.hidden),
            "keep": self.keep,
        }

    def restore(self, snap: dict) -> None:
        self.bodies = dict(snap["bodies"])
        self._next = dict(snap["next"])
        self._entities = {k: dict(v) for k, v in snap["entities"].items()}
        self._origin = {k: dict(snap.get("origin", {}).get(k, {})) for k in ID_KINDS}
        self.selection_kind = snap["selection_kind"]
        self.selection = list(snap["selection"])
        self.named_sets = copy.deepcopy(snap["named_sets"])
        self.last_body = snap["last_body"]
        self.units = snap["units"]
        self.tolerance = snap["tolerance"]
        self.hidden = set(snap.get("hidden", ()))
        self.keep = snap.get("keep", False)
        self._emit(Event("restored"))

    # ---- IDs ---------------------------------------------------------------
    def _in_use(self, kind: str, i: int) -> bool:
        return i in self.bodies if kind == "BODY" else i in self._entities[kind]

    def _alloc(self, kind: str, claimed: set[int] = frozenset()) -> int:
        want = self.pins.take(kind) if self.pins else None
        if want is not None and not self._in_use(kind, want) and want not in claimed:
            gid = want
        else:
            gid = max(self._next[kind], self.id_floor[kind])
            while self._in_use(kind, gid) or gid in claimed:
                gid += 1
        self._next[kind] = max(self._next[kind], gid + 1)
        if self.pins:
            self.pins.used[kind].append(gid)
        self._origin[kind][gid] = self.pins.owner if self.pins else 0
        return gid

    def origin(self, kind: str, gid: int) -> int:
        """uid of the history entry that made this entity (0: made outside the history)."""
        return self._origin[kind].get(gid, 0)

    # ---- bodies ----------------------------------------------------------
    def add_body(self, shape: TopoDS_Shape, name: str = "", made_from=None, keep_id: int | None = None) -> Body:
        """Add a body.

        made_from: optional ``(maker, [input bodies])``. ``maker`` is the OCCT
        builder that made ``shape`` (it has ``Modified``/``IsDeleted``); the
        inputs' entity IDs are carried over to the matching new entities.
        The inputs must already have been removed from the model.
        keep_id: reuse this body ID (for operations that change a body in place).
        """
        if name:
            self._check_name_free(name)
        bid = keep_id if keep_id is not None else self._alloc("BODY")
        body = Body(id=bid, name=name or f"body{bid}", shape=shape)
        for kind in ENTITY_KINDS:
            m = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(shape, _TOPABS[kind], m)
            ids: list[int | None] = [None] * m.Extent()
            if made_from is not None:
                _carry_ids(kind, m, ids, *made_from)
            claimed = {i for i in ids if i is not None}
            for i in range(len(ids)):
                if ids[i] is None:
                    ids[i] = self._alloc(kind, claimed)
                    claimed.add(ids[i])
                self._entities[kind][ids[i]] = (bid, i + 1)
            body.maps[kind] = m
            body.entity_ids[kind] = ids  # type: ignore[assignment]
        self.bodies[bid] = body
        self.last_body = bid
        self._emit(Event("body_added", bid))
        return body

    def remove_body(self, bid: int, emit: bool = True) -> Body:
        body = self.body(bid)
        for kind in ENTITY_KINDS:
            for gid in body.entity_ids[kind]:
                self._entities[kind].pop(gid, None)
        del self.bodies[bid]
        self.hidden.discard(bid)
        if emit:
            self._drop_stale_selection()
            self._emit(Event("body_removed", bid))
        return body

    def replace(self, inputs: list[int], shape: TopoDS_Shape, maker, what_name: str = "", same_id: bool = False) -> Body:
        """Remove ``inputs`` and add ``shape`` made from them by ``maker``.

        The new body inherits the first input's name (so a name keeps pointing
        at "the same part" as it evolves) and, with ``same_id``, its ID.
        Entity IDs carry over through the maker's history.
        """
        olds = [self.remove_body(b, emit=False) for b in inputs]
        for b in olds:
            self._emit(Event("body_removed", b.id))
        first = olds[0]
        inherit = first.name if not _is_default_name(first) else ""
        body = self.add_body(shape, what_name or inherit, (maker, olds), keep_id=first.id if same_id else None)
        self._remap_selection()
        return body

    def set_hidden(self, bid: int, hidden: bool) -> None:
        self.body(bid)
        if hidden == (bid in self.hidden):
            return
        (self.hidden.add if hidden else self.hidden.discard)(bid)
        self._emit(Event("visibility", bid))

    def clear(self) -> None:
        """Remove everything. IDs restart, as in a fresh session."""
        self._reset()
        self._emit(Event("cleared"))

    def body(self, bid: int) -> Body:
        try:
            return self.bodies[bid]
        except KeyError:
            raise ModelError(f"no body with ID {bid}") from None

    # ---- names -------------------------------------------------------------
    def body_by_name(self, name: str) -> Body | None:
        key = name.upper()
        for b in self.bodies.values():
            if b.name.upper() == key:
                return b
        return None

    def _check_name_free(self, name: str, except_id: int | None = None) -> None:
        other = self.body_by_name(name)
        if other is not None and other.id != except_id:
            raise ModelError(f"name {name!r} is already used by body {other.id}")

    def rename(self, bid: int, name: str) -> None:
        body = self.body(bid)
        self._check_name_free(name, bid)
        self.bodies[bid] = Body(body.id, name, body.shape, body.maps, body.entity_ids)

    # ---- entities --------------------------------------------------------
    def entity_count(self, kind: str) -> int:
        return len(self._entities[kind])

    def entity_ids(self, kind: str) -> list[int]:
        kind = check_kind(kind, SELECT_KINDS)
        if kind == "BODY":
            return sorted(self.bodies)
        return sorted(self._entities[kind])

    def entity_shape(self, kind: str, gid: int) -> TopoDS_Shape:
        kind = check_kind(kind, SELECT_KINDS)
        if kind == "BODY":
            return self.body(gid).shape
        bid, idx = self.entity_owner(kind, gid)
        return self.bodies[bid].maps[kind].FindKey(idx)

    def entity_owner(self, kind: str, gid: int) -> tuple[int, int]:
        """Return (body id, local 1-based index) for a global entity ID."""
        kind = check_kind(kind, ENTITY_KINDS)
        try:
            return self._entities[kind][gid]
        except KeyError:
            raise ModelError(f"no {kind} with ID {gid}") from None

    def find_entity(self, bid: int, kind: str, sub_shape: TopoDS_Shape) -> int:
        """Global ID of ``sub_shape`` (a face/edge/vertex) inside body ``bid``."""
        body = self.body(bid)
        kind = check_kind(kind, ENTITY_KINDS)
        idx = body.maps[kind].FindIndex(sub_shape)
        if idx == 0:
            raise ModelError(f"shape is not a {kind} of body {bid}")
        return body.entity_ids[kind][idx - 1]

    # ---- selection -------------------------------------------------------
    def select(self, kind: str, ids: list[int], mode: str = "S") -> None:
        """Change the selection.

        mode: S = new set, A = add, U = unselect (remove), R = reselect
        (keep only those of the current set that are also in ids).
        Selecting a different kind than the current one starts a new set.
        """
        kind = check_kind(kind, SELECT_KINDS)
        for i in ids:
            if kind == "BODY":
                self.body(i)
            else:
                self.entity_owner(kind, i)
        current = [] if (mode == "S" or kind != self.selection_kind) else list(self.selection)
        if mode in ("S", "A"):
            current += [i for i in ids if i not in current]
        elif mode == "U":
            current = [i for i in current if i not in ids]
        elif mode == "R":
            keep = set(ids)
            current = [i for i in current if i in keep]
        else:
            raise ModelError(f"unknown selection mode {mode!r} (use S, R, A or U)")
        self.selection_kind = kind
        self.selection = current
        self._emit(Event("selection"))

    def select_none(self) -> None:
        self.selection = []
        self._emit(Event("selection"))

    def _drop_stale_selection(self) -> None:
        self.selection = [i for i in self.selection if self._in_use(self.selection_kind, i)]

    def _remap_selection(self) -> None:
        """After an operation: keep selected IDs that still exist (they carried over)."""
        before = list(self.selection)
        self._drop_stale_selection()
        if before != self.selection:
            self._emit(Event("selection"))

    # ---- named sets --------------------------------------------------------
    def save_set(self, name: str, kind: str, ids: list[int]) -> None:
        self.named_sets[name.upper()] = (check_kind(kind, SELECT_KINDS), list(ids))

    def named_set(self, name: str) -> tuple[str, list[int]]:
        try:
            kind, ids = self.named_sets[name.upper()]
        except KeyError:
            raise ModelError(f"no named set {name!r}") from None
        return kind, [i for i in ids if self._in_use(kind, i)]


def _is_default_name(body: Body) -> bool:
    return body.name == f"body{body.id}"


def _measure(kind: str, shape: TopoDS_Shape) -> float:
    if kind == "VERTEX":
        return 0.0
    g = GProp_GProps()
    if kind == "FACE":
        BRepGProp.SurfaceProperties_s(shape, g)
    else:
        BRepGProp.LinearProperties_s(shape, g)
    return g.Mass()


def _carry_ids(kind: str, new_map, ids: list, maker, inputs: list[Body]) -> None:
    """Fill ``ids`` (per new entity) with the IDs of the input entities they came from."""
    sizes: dict[int, float] = {}
    leftovers: list = []
    for body in inputs:
        old_map = body.maps[kind]
        for i, gid in enumerate(body.entity_ids[kind]):
            old = old_map.FindKey(i + 1)
            same = new_map.FindIndex(old)
            if same > 0:  # untouched: the very same sub-shape is in the result
                if ids[same - 1] is None:
                    ids[same - 1] = gid
                continue
            try:
                # (checked after the lookup above: fillet makers report every
                # input entity as deleted, even the ones they keep)
                if maker.IsDeleted(old):
                    continue
                pieces = [s for s in maker.Modified(old)]
            except Exception:  # some makers do not track every kind
                pieces = []
            targets = [new_map.FindIndex(s) for s in pieces] if pieces else [new_map.FindIndex(old)]
            targets = [t for t in targets if t > 0 and ids[t - 1] is None]
            if not targets:
                if not pieces:
                    leftovers.append((gid, old))
                continue
            if len(targets) > 1:
                targets.sort(key=lambda t: -sizes.setdefault(t, _measure(kind, new_map.FindKey(t))))
            ids[targets[0] - 1] = gid
    if leftovers:
        _carry_by_geometry(kind, new_map, ids, leftovers)


def _signature(kind: str, shape) -> tuple:
    """Where an entity is and how big it is, rounded: equal for copies of the same geometry."""
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS

    if kind == "VERTEX":
        to_vertex = getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex
        p = BRep_Tool.Pnt_s(to_vertex(shape))
        c, size = (p.X(), p.Y(), p.Z()), 0.0
    else:
        g = GProp_GProps()
        if kind == "FACE":
            BRepGProp.SurfaceProperties_s(shape, g)
        else:
            BRepGProp.LinearProperties_s(shape, g)
        q = g.CentreOfMass()
        c, size = (q.X(), q.Y(), q.Z()), g.Mass()
    return tuple(round(v, 5) + 0.0 for v in (*c, size))


def _carry_by_geometry(kind: str, new_map, ids: list, leftovers: list) -> None:
    """Some builders (fillets, chamfers) rebuild untouched faces and edges as
    new topology without reporting them as modified. Match those by geometry:
    same centre and same size means the same entity."""
    free: dict[tuple, list[int]] = {}
    for t in range(1, new_map.Extent() + 1):
        if ids[t - 1] is None:
            free.setdefault(_signature(kind, new_map.FindKey(t)), []).append(t)
    for gid, old in leftovers:
        cands = free.get(_signature(kind, old))
        if cands:
            ids[cands.pop(0) - 1] = gid


def check_kind(kind: str, allowed: tuple[str, ...] = SELECT_KINDS) -> str:
    k = kind.upper()
    if k in ("KP", "POINT", "VERT"):
        k = "VERTEX"
    elif k in ("LINE",):
        k = "EDGE"
    elif k in ("AREA",):
        k = "FACE"
    elif k in ("VOLU", "SOLID", "BODIES"):
        k = "BODY"
    elif k.endswith("S") and k[:-1] in allowed:
        k = k[:-1]
    if k not in allowed:
        raise ModelError(f"unknown entity kind {kind!r} (use {', '.join(allowed)})")
    return k


_check_kind = check_kind  # old name
