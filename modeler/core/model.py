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
from dataclasses import dataclass, field, replace
from typing import Callable

from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS_Shape

from .datum import Datum

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
    # how the body is organised and drawn (see :class:`Layer`). A body made
    # from other bodies takes these from its first input.
    layer: str = "DEFAULT"
    color: tuple[float, float, float] | None = None  # own colour (0..1 RGB); None: by layer, then material
    material: str = ""  # upper-case key of Model.materials, or ""


DEFAULT_LAYER = "DEFAULT"


@dataclass(frozen=True)
class Layer:
    """A named group of bodies that is shown, hidden, locked or coloured together.

    Every body is on exactly one layer. New bodies go on the current layer.
    A locked layer's bodies cannot be changed, used up or deleted.
    """

    name: str  # as the user wrote it; the key in Model.layers is upper case
    color: tuple[float, float, float] | None = None
    visible: bool = True
    locked: bool = False


@dataclass(frozen=True)
class Material:
    name: str
    density: float  # kg/m3
    color: tuple[float, float, float] | None = None
    transparency: float = 0.0  # 0 solid ... 1 invisible; glass is drawn see-through


def _rgb255(r: int, g: int, b: int) -> tuple[float, float, float]:
    return (r / 255.0, g / 255.0, b / 255.0)


# Built-in materials: density in kg/m3 and a colour to draw them in.
MATERIALS: dict[str, Material] = {m.name: m for m in (
    Material("STEEL", 7850, _rgb255(158, 166, 178)),
    Material("STAINLESS", 8000, _rgb255(196, 200, 206)),
    Material("CASTIRON", 7200, _rgb255(92, 96, 102)),
    Material("ALUMINIUM", 2700, _rgb255(214, 218, 224)),
    Material("TITANIUM", 4430, _rgb255(150, 146, 140)),
    Material("COPPER", 8960, _rgb255(196, 112, 72)),
    Material("BRASS", 8500, _rgb255(212, 175, 90)),
    Material("ABS", 1050, _rgb255(236, 236, 228)),
    Material("NYLON", 1150, _rgb255(240, 236, 220)),
    Material("PLA", 1240, _rgb255(90, 160, 220)),
    Material("RUBBER", 1100, _rgb255(48, 48, 52)),
    Material("WOOD", 600, _rgb255(178, 128, 76)),
    Material("GLASS", 2500, _rgb255(170, 210, 220), 0.6),
)}
MATERIAL_ALIASES = {"ALUMINUM": "ALUMINIUM", "AL": "ALUMINIUM", "SS": "STAINLESS", "IRON": "CASTIRON",
                    "CU": "COPPER", "TI": "TITANIUM", "PLASTIC": "ABS"}


@dataclass(frozen=True)
class Event:
    """A change notification sent to listeners (the viewport, the GUI)."""

    kind: str  # "body_added", "body_removed", "cleared", "selection", "restored", "visibility", "datums",
    #            "style" (one body's layer/colour/material), "layers" (any layer or material changed)
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
        # The view's own changes (DISPLAY, FADE): saved with the project but
        # not history entries and not in snapshots, so undo, redo and
        # rebuilds keep them. They are keyed by body ID, which survives edits.
        self.view_hidden: set[int] = set()  # hidden by the view although the history shows them
        self.view_shown: set[int] = set()  # shown by the view although the history hid them
        self.faded: dict[int, float] = {}  # body ID -> how see-through it is drawn (0..1)
        # layers by upper-case name; there is always the DEFAULT layer
        self.layers: dict[str, Layer] = {DEFAULT_LAYER: Layer(DEFAULT_LAYER)}
        self.current_layer: str = DEFAULT_LAYER
        # materials by upper-case name: the built-in ones plus any MATERIAL, NEW
        self.materials: dict[str, Material] = dict(MATERIALS)
        # datum planes, axes and points by upper-case name (see core/datum.py)
        self.datums: dict[str, Datum] = {}
        self.workplane: Datum | None = None  # WORKPLANE: where new shapes are drawn
        # 2D sketches by upper-case name (see sketch/sketch.py). A sketch is
        # never changed in place: edit_sketch() swaps in a copy, so snapshots
        # can share them.
        self.sketches: dict = {}
        # body ID -> (part name, ((PARAM, value), ...)) for bodies placed by INST;
        # moving or copying keeps it, any other change makes plain geometry
        self.instances: dict[int, tuple] = {}
        self.active_sketch: str | None = None  # the open sketch (between SKETCH and ENDSKETCH)
        self.sketch_selection: list[str] = []  # SSEL: GUI helper only, not history, not in snapshots

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
            "layers": dict(self.layers),
            "current_layer": self.current_layer,
            "materials": dict(self.materials),
            "datums": dict(self.datums),
            "workplane": self.workplane,
            "sketches": dict(self.sketches),
            "active_sketch": self.active_sketch,
            "instances": dict(self.instances),
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
        self.layers = dict(snap.get("layers", {DEFAULT_LAYER: Layer(DEFAULT_LAYER)}))
        self.current_layer = snap.get("current_layer", DEFAULT_LAYER)
        self.materials = dict(snap.get("materials", MATERIALS))
        self.datums = dict(snap.get("datums", {}))
        self.workplane = snap.get("workplane")
        self.sketches = dict(snap.get("sketches", {}))
        self.active_sketch = snap.get("active_sketch")
        self.instances = dict(snap.get("instances", {}))
        self.sketch_selection = []
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
    def add_body(self, shape: TopoDS_Shape, name: str = "", made_from=None, keep_id: int | None = None,
                 like: Body | None = None) -> Body:
        """Add a body.

        made_from: optional ``(maker, [input bodies])``. ``maker`` is the OCCT
        builder that made ``shape`` (it has ``Modified``/``IsDeleted``); the
        inputs' entity IDs are carried over to the matching new entities.
        The inputs must already have been removed from the model.
        keep_id: reuse this body ID (for operations that change a body in place).
        like: take layer, colour and material from this body (copies). Without
        it a body made from others takes them from its first input, and a new
        body goes on the current layer.
        """
        if name:
            self._check_name_free(name)
        bid = keep_id if keep_id is not None else self._alloc("BODY")
        style = like if like is not None else (made_from[1][0] if made_from is not None and made_from[1] else None)
        if style is not None and style.layer.upper() in self.layers:
            look = {"layer": style.layer, "color": style.color, "material": style.material}
        else:
            look = {"layer": self.layers[self.current_layer].name}
        body = Body(id=bid, name=name or f"body{bid}", shape=shape, **look)
        for kind in ENTITY_KINDS:
            m = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(shape, _TOPABS[kind], m)
            ids: list[int | None] = [None] * m.Extent()
            if made_from is not None:
                _carry_ids(kind, m, ids, *made_from)
                # an ID already held by another body (one piece of a split
                # carried it first) cannot be shared: the entity gets a new one
                ids = [None if i is not None and i in self._entities[kind] else i for i in ids]
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
        self.check_unlocked(bid)
        for kind in ENTITY_KINDS:
            for gid in body.entity_ids[kind]:
                self._entities[kind].pop(gid, None)
        del self.bodies[bid]
        self.hidden.discard(bid)
        self.instances.pop(bid, None)
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
        for b in inputs:  # all or nothing: never use up some inputs and then stop
            self.check_unlocked(b)
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

    def is_shown(self, bid: int) -> bool:
        """Drawn in the viewport: not hidden (by the history or the view), and its layer is on."""
        if bid in self.view_hidden:
            return False
        if bid in self.hidden and bid not in self.view_shown:
            return False
        lay = self.layers.get(self.bodies[bid].layer.upper())
        return lay is None or lay.visible

    def shown_ids(self) -> list[int]:
        return [i for i in self.bodies if self.is_shown(i)]

    # ---- the view's own changes (DISPLAY, FADE) ------------------------------
    def set_view_shown(self, bid: int, shown: bool) -> None:
        """Show or hide a body for the view only (not a history entry)."""
        self.body(bid)
        before = self.is_shown(bid)
        if shown:
            self.view_hidden.discard(bid)
            if bid in self.hidden:
                self.view_shown.add(bid)
        else:
            self.view_shown.discard(bid)
            self.view_hidden.add(bid)
        if self.is_shown(bid) != before:
            self._emit(Event("visibility", bid))

    def set_fade(self, bid: int, amount: float) -> None:
        """Draw a body see-through by ``amount`` (0 = solid again)."""
        self.body(bid)
        old = self.faded.get(bid, 0.0)
        if amount > 0:
            self.faded[bid] = amount
        else:
            self.faded.pop(bid, None)
        if self.faded.get(bid, 0.0) != old:
            self._emit(Event("style", bid))

    def forget_view(self, bid: int) -> None:
        """Drop the view's show/hide override of one body (a HIDE or SHOW step now decides)."""
        self.view_hidden.discard(bid)
        self.view_shown.discard(bid)

    def has_view_changes(self) -> bool:
        live = self.bodies.keys()
        return bool((self.view_hidden | self.view_shown | set(self.faded)) & live)

    def view_state(self) -> dict:
        """The view's changes as plain data (for the project file), only for bodies that exist."""
        live = self.bodies.keys()
        return {
            "hidden": sorted(self.view_hidden & live),
            "shown": sorted(self.view_shown & live),
            "faded": {str(b): a for b, a in sorted(self.faded.items()) if b in live},
        }

    def set_view_state(self, state: dict | None, emit: bool = True) -> None:
        """Put back what view_state() gave (unknown bodies are ignored)."""
        state = state or {}
        old = {b: (self.is_shown(b), self.display_transparency(b)) for b in self.bodies}
        self.view_hidden = {int(b) for b in state.get("hidden", ())}
        self.view_shown = {int(b) for b in state.get("shown", ())}
        self.faded = {int(b): float(a) for b, a in (state.get("faded") or {}).items()}
        if emit:
            for b, (shown, see) in old.items():
                if (self.is_shown(b), self.display_transparency(b)) != (shown, see):
                    self._emit(Event("visibility", b))

    # ---- layers, colours, materials ------------------------------------------
    def layer(self, name: str) -> Layer:
        lay = self.layers.get(name.strip().upper())
        if lay is None:
            raise ModelError(f"no layer named {name.strip()!r} (layers: {', '.join(l.name for l in self.layers.values())})")
        return lay

    def layer_of(self, bid: int) -> Layer:
        return self.layers.get(self.body(bid).layer.upper()) or Layer(self.body(bid).layer)

    def check_unlocked(self, bid: int) -> None:
        lay = self.layer_of(bid)
        if lay.locked:
            raise ModelError(f"body {bid} is on locked layer {lay.name} (LAYER, {lay.name}, UNLOCK to change it)")

    def put_layer(self, lay: Layer) -> None:
        """Add a layer or change one (its colour, visibility or lock)."""
        self.layers[lay.name.upper()] = lay
        self._emit(Event("layers"))

    def rename_layer(self, old: str, new: str) -> None:
        lay = self.layer(old)
        if new.upper() in self.layers and new.upper() != lay.name.upper():
            raise ModelError(f"layer {new} already exists")
        if lay.name.upper() == DEFAULT_LAYER:
            raise ModelError("the DEFAULT layer cannot be renamed")
        del self.layers[lay.name.upper()]
        self.layers[new.upper()] = replace(lay, name=new)
        for bid, b in list(self.bodies.items()):
            if b.layer.upper() == lay.name.upper():
                self.bodies[bid] = replace(b, layer=new)
        if self.current_layer == lay.name.upper():
            self.current_layer = new.upper()
        self._emit(Event("layers"))

    def delete_layer(self, name: str) -> int:
        """Remove a layer; its bodies move to DEFAULT. Returns how many moved."""
        lay = self.layer(name)
        if lay.name.upper() == DEFAULT_LAYER:
            raise ModelError("the DEFAULT layer cannot be deleted")
        if lay.locked:
            raise ModelError(f"layer {lay.name} is locked (LAYER, {lay.name}, UNLOCK first)")
        moved = 0
        for bid, b in list(self.bodies.items()):
            if b.layer.upper() == lay.name.upper():
                self.bodies[bid] = replace(b, layer=DEFAULT_LAYER)
                moved += 1
        del self.layers[lay.name.upper()]
        if self.current_layer == lay.name.upper():
            self.current_layer = DEFAULT_LAYER
        self._emit(Event("layers"))
        return moved

    def set_current_layer(self, name: str) -> None:
        self.current_layer = self.layer(name).name.upper()
        self._emit(Event("layers"))

    def set_style(self, bid: int, **changes) -> None:
        """Change a body's layer, colour or material (keys of :class:`Body`)."""
        body = self.body(bid)
        self.check_unlocked(bid)
        if "layer" in changes:
            changes["layer"] = self.layer(changes["layer"]).name
        new = replace(body, **changes)
        if new != body:
            self.bodies[bid] = new
            self._emit(Event("style", bid))

    def material(self, name: str) -> Material:
        key = name.strip().upper()
        key = MATERIAL_ALIASES.get(key, key)
        mat = self.materials.get(key)
        if mat is None:
            raise ModelError(f"no material named {name.strip()!r} (materials: {', '.join(self.materials)}; "
                             "or MATERIAL, NEW, name, density)")
        return mat

    def put_material(self, mat: Material) -> None:
        self.materials[mat.name.upper()] = mat
        self._emit(Event("layers"))  # bodies of that material may change colour

    def display_color(self, bid: int) -> tuple[float, float, float] | None:
        """The colour a body is drawn in: its own, else its layer's, else its
        material's; None means the plain default."""
        body = self.body(bid)
        if body.color is not None:
            return body.color
        lay = self.layers.get(body.layer.upper())
        if lay is not None and lay.color is not None:
            return lay.color
        if body.material:
            mat = self.materials.get(body.material.upper())
            if mat is not None:
                return mat.color
        return None

    def display_transparency(self, bid: int) -> float:
        """How see-through a body is drawn: the more of its material's (glass)
        and the view's fade (FADE), else 0."""
        body = self.body(bid)
        see = self.faded.get(bid, 0.0)
        if body.material:
            mat = self.materials.get(body.material.upper())
            if mat is not None:
                return max(see, mat.transparency)
        return see

    def density(self, bid: int) -> float:
        """kg/m3 from the body's material, 0 if it has none."""
        mat = self.materials.get(self.body(bid).material.upper()) if self.body(bid).material else None
        return mat.density if mat else 0.0

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
        if name.upper() in self.datums:
            raise ModelError(f"name {name!r} is already used by datum {self.datums[name.upper()].kind.lower()} {name}")
        if name.upper() in self.sketches:
            raise ModelError(f"name {name!r} is already used by sketch {self.sketches[name.upper()].name}")

    def rename(self, bid: int, name: str) -> None:
        body = self.body(bid)
        self._check_name_free(name, bid)
        self.bodies[bid] = replace(body, name=name)

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

    # ---- datums ------------------------------------------------------------
    def add_datum(self, d: Datum) -> None:
        key = d.name.upper()
        if self.body_by_name(d.name) is not None:
            raise ModelError(f"name {d.name!r} is already used by body {self.body_by_name(d.name).id}")
        self.datums[key] = d
        self._emit(Event("datums"))

    def datum(self, name: str, kind: str | None = None) -> Datum:
        d = self.datums.get(name.upper())
        if d is None:
            raise ModelError(f"no datum named {name!r}" + (f" (datums: {', '.join(x.name for x in self.datums.values())})"
                                                          if self.datums else ""))
        if kind and d.kind != kind:
            raise ModelError(f"{name} is a datum {d.kind.lower()}, not a {kind.lower()}")
        return d

    def remove_datum(self, name: str) -> Datum:
        d = self.datum(name)
        del self.datums[name.upper()]
        if self.workplane is not None and self.workplane.name.upper() == name.upper():
            self.workplane = None
        self._emit(Event("datums"))
        return d

    def set_workplane(self, d: Datum | None) -> None:
        self.workplane = d
        self._emit(Event("datums"))

    # ---- sketches ----------------------------------------------------------
    def sketch(self, name: str):
        sk = self.sketches.get(name.strip().upper())
        if sk is None:
            have = ", ".join(s.name for s in self.sketches.values())
            raise ModelError(f"no sketch named {name.strip()!r}" + (f" (sketches: {have})" if have else ""))
        return sk

    def put_sketch(self, sk) -> None:
        """Store a (new or changed) sketch object and tell the views."""
        self.sketches[sk.name.upper()] = sk
        self._emit(Event("sketch"))

    def edit_sketch(self, name: str):
        """A copy of the sketch to change; store it back with put_sketch()."""
        return self.sketch(name).copy()

    def remove_sketch(self, name: str):
        sk = self.sketch(name)
        del self.sketches[sk.name.upper()]
        if self.active_sketch == sk.name.upper():
            self.active_sketch = None
        self._emit(Event("sketch"))
        return sk

    def set_active_sketch(self, name: str | None) -> None:
        self.active_sketch = name.upper() if name else None
        self._emit(Event("sketch"))

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
