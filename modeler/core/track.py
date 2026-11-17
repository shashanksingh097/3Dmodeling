"""Read tracking for one history entry, so a re-run can skip entries whose
inputs did not change.

While an entry runs, the model's body table, its entity tables and the
parameters are swapped for :class:`Track` dicts. A Track works exactly like
a dict and also notes which keys were looked at. Anything that looks at the
whole table (iterating, ``len``, comparing, copying) sets ``all``, and then
the whole table counts as read. Writes are not reads.

``Processor.rebuild`` uses what was read: if none of it differs from the
last run, the entry would do exactly what it did last time, so its changes
are copied over instead of running it again (see Processor._can_skip).
"""

from __future__ import annotations

from typing import Any

MISSING = object()


class Track(dict):
    __slots__ = ("read", "all", "names", "on")

    def __init__(self, data: dict) -> None:
        super().__init__(data)
        self.read: set = set()
        self.all = False
        self.names = False  # only for bodies: every body's name was looked at
        self.on = True

    # ---- key reads ----------------------------------------------------
    def __getitem__(self, key):
        if self.on:
            self.read.add(key)
        return dict.__getitem__(self, key)

    def get(self, key, default=None):
        if self.on:
            self.read.add(key)
        return dict.get(self, key, default)

    def __contains__(self, key) -> bool:
        if self.on:
            self.read.add(key)
        return dict.__contains__(self, key)

    def pop(self, key, *default):
        if self.on:
            self.read.add(key)
        return dict.pop(self, key, *default)

    def __delitem__(self, key) -> None:
        if self.on:
            self.read.add(key)
        dict.__delitem__(self, key)

    def setdefault(self, key, default=None):
        if self.on:
            self.read.add(key)
        return dict.setdefault(self, key, default)

    # ---- whole-table reads --------------------------------------------
    def _whole(self) -> None:
        if self.on:
            self.all = True

    def __iter__(self):
        self._whole()
        return dict.__iter__(self)

    def keys(self):
        self._whole()
        return dict.keys(self)

    def values(self):
        self._whole()
        return dict.values(self)

    def items(self):
        self._whole()
        return dict.items(self)

    def __len__(self) -> int:
        self._whole()
        return dict.__len__(self)

    def __bool__(self) -> bool:
        self._whole()
        return dict.__len__(self) > 0

    def __eq__(self, other) -> bool:
        self._whole()
        return dict.__eq__(self, other)

    __hash__ = None  # type: ignore[assignment]

    def __reversed__(self):
        self._whole()
        return dict.__reversed__(self)

    def copy(self) -> dict:
        self._whole()
        return dict(dict.items(self))

    def popitem(self):
        self._whole()
        return dict.popitem(self)

    def clear(self) -> None:
        self._whole()
        dict.clear(self)

    def update(self, *args, **kw) -> None:  # a write, but it may overwrite anything
        dict.update(self, *args, **kw)

    def __reduce__(self):  # pickling/copying gives a plain dict
        return (dict, (dict(dict.items(self)),))

    def plain(self) -> dict:
        return dict(dict.items(self))


class Reads:
    """What one entry looked at the last time it ran (``None`` fields: nothing)."""

    def __init__(self) -> None:
        self.params: set | None = set()  # None: all of them
        self.bodies: set | None = set()
        self.names = False
        self.entities: dict[str, set | None] = {}
        self.origin: dict[str, set | None] = {}

    @staticmethod
    def of(t: Track) -> set | None:
        return None if t.all else set(t.read)


def same(a: Any, b: Any) -> bool:
    """True when two saved values are certainly equal (identity first, then ==;
    anything that cannot be compared counts as different)."""
    if a is b:
        return True
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(v, b[k]) for k, v in a.items())
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float, str, bool, frozenset, set, type(None))):
        return a == b
    try:
        r = a == b
        return r is True
    except Exception:
        return False


def same_keys(old: dict, new: dict, keys: set | None, identity: bool = False) -> bool:
    """Do ``old`` and ``new`` agree on ``keys`` (None: on everything)?"""
    if keys is None:
        if old.keys() != new.keys():
            return False
        keys = set(old)
    for k in keys:
        a, b = old.get(k, MISSING), new.get(k, MISSING)
        if identity:
            if a is not b:
                return False
        elif not same(a, b):
            return False
    return True


def apply_delta(now: dict, before: dict, after: dict, identity: bool = False) -> dict:
    """``now`` with the changes that turned ``before`` into ``after``."""
    out = dict(now)
    for k in set(before) | set(after):
        a, b = before.get(k, MISSING), after.get(k, MISSING)
        if (a is b) if identity else same(a, b):
            continue
        if b is MISSING:
            out.pop(k, None)
        else:
            out[k] = b
    return out
