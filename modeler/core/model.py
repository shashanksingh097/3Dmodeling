"""The model: bodies, global entity IDs and the current selection.

This module knows nothing about Qt. It only uses OCCT (through OCP), so the
whole model can run headless in tests and batch scripts.

Entity IDs
----------
Every body gets a permanent ID. Every face, edge and vertex of every body gets
a global ID per kind (FACE 1, 2, 3 ... across all bodies), assigned when the
body is added and never reused within a session. That is what lets a viewport
click be written as ``PICK, FACE, 12`` and replayed later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

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
_TOPABS = {"FACE": TopAbs_FACE, "EDGE": TopAbs_EDGE, "VERTEX": TopAbs_VERTEX}

# Selection kinds: whole bodies plus the three entity kinds.
SELECT_KINDS = ("BODY",) + ENTITY_KINDS


class ModelError(Exception):
    """Raised for invalid requests against the model (unknown IDs, etc.)."""


@dataclass
class Body:
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

    kind: str  # "body_added", "body_removed", "cleared", "selection"
    body_id: int | None = None


class Model:
    def __init__(self) -> None:
        self._listeners: list[Callable[[Event], None]] = []
        self._reset()

    def _reset(self) -> None:
        self.bodies: dict[int, Body] = {}
        self._next_body = 1
        self._next_entity = {k: 1 for k in ENTITY_KINDS}
        # global entity id -> (body id, 1-based index in that body's map)
        self._entities: dict[str, dict[int, tuple[int, int]]] = {k: {} for k in ENTITY_KINDS}
        self.selection_kind: str = "FACE"
        self.selection: list[int] = []  # body IDs or entity IDs of selection_kind

    # ---- listeners -------------------------------------------------------
    def subscribe(self, fn: Callable[[Event], None]) -> None:
        self._listeners.append(fn)

    def _emit(self, event: Event) -> None:
        for fn in list(self._listeners):
            fn(event)

    # ---- bodies ----------------------------------------------------------
    def add_body(self, shape: TopoDS_Shape, name: str = "") -> Body:
        bid = self._next_body
        self._next_body += 1
        body = Body(id=bid, name=name or f"body{bid}", shape=shape)
        for kind in ENTITY_KINDS:
            m = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(shape, _TOPABS[kind], m)
            ids = []
            for i in range(1, m.Extent() + 1):
                gid = self._next_entity[kind]
                self._next_entity[kind] += 1
                self._entities[kind][gid] = (bid, i)
                ids.append(gid)
            body.maps[kind] = m
            body.entity_ids[kind] = ids
        self.bodies[bid] = body
        self._emit(Event("body_added", bid))
        return body

    def remove_body(self, bid: int) -> None:
        body = self.body(bid)
        for kind in ENTITY_KINDS:
            for gid in body.entity_ids[kind]:
                self._entities[kind].pop(gid, None)
        del self.bodies[bid]
        self._drop_stale_selection()
        self._emit(Event("body_removed", bid))

    def clear(self) -> None:
        """Remove everything. IDs restart, as in a fresh session."""
        self._reset()
        self._emit(Event("cleared"))

    def body(self, bid: int) -> Body:
        try:
            return self.bodies[bid]
        except KeyError:
            raise ModelError(f"no body with ID {bid}") from None

    # ---- entities --------------------------------------------------------
    def entity_count(self, kind: str) -> int:
        return len(self._entities[kind])

    def entity_shape(self, kind: str, gid: int) -> TopoDS_Shape:
        bid, idx = self.entity_owner(kind, gid)
        return self.bodies[bid].maps[kind].FindKey(idx)

    def entity_owner(self, kind: str, gid: int) -> tuple[int, int]:
        """Return (body id, local 1-based index) for a global entity ID."""
        kind = _check_kind(kind, ENTITY_KINDS)
        try:
            return self._entities[kind][gid]
        except KeyError:
            raise ModelError(f"no {kind} with ID {gid}") from None

    def find_entity(self, bid: int, kind: str, sub_shape: TopoDS_Shape) -> int:
        """Global ID of ``sub_shape`` (a face/edge/vertex) inside body ``bid``."""
        body = self.body(bid)
        kind = _check_kind(kind, ENTITY_KINDS)
        idx = body.maps[kind].FindIndex(sub_shape)
        if idx == 0:
            raise ModelError(f"shape is not a {kind} of body {bid}")
        return body.entity_ids[kind][idx - 1]

    # ---- selection -------------------------------------------------------
    def select(self, kind: str, ids: list[int], mode: str = "S") -> None:
        """Change the selection.

        mode: S = new set, A = add, U = unselect (remove).
        Selecting a different kind than the current one starts a new set.
        """
        kind = _check_kind(kind, SELECT_KINDS)
        for i in ids:
            if kind == "BODY":
                self.body(i)
            else:
                self.entity_owner(kind, i)
        if mode == "S" or kind != self.selection_kind:
            current: list[int] = []
        else:
            current = list(self.selection)
        if mode in ("S", "A"):
            current += [i for i in ids if i not in current]
        elif mode == "U":
            current = [i for i in current if i not in ids]
        else:
            raise ModelError(f"unknown selection mode {mode!r} (use S, A or U)")
        self.selection_kind = kind
        self.selection = current
        self._emit(Event("selection"))

    def select_none(self) -> None:
        self.selection = []
        self._emit(Event("selection"))

    def _drop_stale_selection(self) -> None:
        if self.selection_kind == "BODY":
            self.selection = [i for i in self.selection if i in self.bodies]
        else:
            ents = self._entities[self.selection_kind]
            self.selection = [i for i in self.selection if i in ents]


def _check_kind(kind: str, allowed: tuple[str, ...]) -> str:
    k = kind.upper()
    if k in ("KP", "POINT"):
        k = "VERTEX"
    elif k in ("LINE",):
        k = "EDGE"
    elif k in ("AREA",):
        k = "FACE"
    elif k in ("VOLU", "SOLID"):
        k = "BODY"
    if k not in allowed:
        raise ModelError(f"unknown entity kind {kind!r} (use {', '.join(allowed)})")
    return k
