"""Two revisions of a body, face by face: what was added, removed, moved or changed, and how far
the new surface lies from the old one.

Faces are matched by what they are, not by their IDs (a project opened again, or rebuilt, numbers
them anew): the same kind of surface, the same size and the same place is the same face; the same
kind and size in another place has moved; the same kind of surface in about the same place with
another size has changed (a hole made bigger, a face cut by a new pocket). What is left over was
added (in the new revision) or removed (from the old one).

The distances (new surface to old, signed: positive outside the old body) colour the new body in
the view and give the size of each change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..core.refs import _describe


SAMPLES = 12000  # points of the new surface measured against the old


@dataclass
class FaceInfo:
    index: int  # in face order
    fid: int  # the face's ID in its model
    kind: str  # PLANE, CYLINDER ...
    centre: np.ndarray
    area: float
    direction: tuple | None
    radius: float | None


def faces_of(shape, ids: list[int] | None) -> list[FaceInfo]:
    from . import healing

    out = []
    from OCP.TopAbs import TopAbs_FACE

    for i, f in enumerate(healing._indexed(shape, TopAbs_FACE)):
        d = _describe("FACE", f)
        fid = ids[i] if ids is not None and i < len(ids) else i + 1
        out.append(FaceInfo(i, fid, d["type"], np.array(d["c"], float), float(d["size"]),
                            tuple(d["dir"]) if d["dir"] else None, d["r"]))
    return out


def _same_dir(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return float(np.dot(a, b)) >= 1 - 1e-6


def _same_shape(a: FaceInfo, b: FaceInfo, tol: float) -> bool:
    """Same kind, size, direction and radius (not place)."""
    if a.kind != b.kind:
        return False
    if abs(a.area - b.area) > max(1e-6 * max(a.area, b.area), tol * tol):
        return False
    if (a.radius is None) != (b.radius is None) or (a.radius is not None and abs(a.radius - b.radius) > tol):
        return False
    return _same_dir(a.direction, b.direction)


def _same_surface(a: FaceInfo, b: FaceInfo, tol: float) -> bool:
    """The same kind of surface lying in the same place (a plane at the same level, a cylinder
    round the same axis), whatever its size."""
    if a.kind != b.kind or not _same_dir(a.direction, b.direction):
        return False
    if a.kind == "PLANE" and a.direction is not None:
        n = np.asarray(a.direction)
        return abs(float(np.dot(a.centre - b.centre, n))) <= tol
    if a.radius is not None and b.radius is not None and a.direction is not None:
        # same axis line (the radius may have changed: a bigger hole)
        n = np.asarray(a.direction)
        d = a.centre - b.centre
        return float(np.linalg.norm(d - np.dot(d, n) * n)) <= max(tol, 0.5 * max(a.radius, b.radius))
    size = max(np.sqrt(a.area), np.sqrt(b.area))
    return float(np.linalg.norm(a.centre - b.centre)) <= 0.5 * size


@dataclass
class BodyDiff:
    old_id: int | None
    new_id: int | None
    name: str
    unchanged: int = 0
    moved: list[dict] = field(default_factory=list)
    changed: list[dict] = field(default_factory=list)
    added: list[dict] = field(default_factory=list)
    removed: list[dict] = field(default_factory=list)
    volume: tuple[float, float] | None = None
    largest_out: float = 0.0
    largest_in: float = 0.0
    off: float = 0.0  # share of the new surface more than tol from the old
    regions: list[dict] = field(default_factory=list)  # new faces that moved away from the old surface

    @property
    def same(self) -> bool:
        return not (self.moved or self.changed or self.added or self.removed) and self.off == 0

    def as_dict(self) -> dict:
        r = lambda x: round(float(x), 6)  # noqa: E731
        out = {"old": self.old_id, "new": self.new_id, "name": self.name, "same": self.same,
               "unchanged_faces": self.unchanged, "moved": self.moved, "changed": self.changed,
                "added": self.added, "removed": self.removed,
               "largest_out": r(self.largest_out), "largest_in": r(self.largest_in), "off": r(self.off),
               "regions": self.regions}
        if self.volume is not None:
            out["volume"] = [r(self.volume[0]), r(self.volume[1])]
        return out


def _row(f: FaceInfo) -> dict:
    return {"face": f.fid, "type": f.kind.lower(), "area": round(f.area, 6), "at": [round(float(x), 6) for x in f.centre]}


def compare_body(old_shape, new_shape, old_ids, new_ids, tol: float) -> BodyDiff:
    """Face by face, and the distances of the new surface from the old."""
    from . import deviation as dv
    from . import robust

    d = BodyDiff(None, None, "")
    a, b = faces_of(old_shape, old_ids), faces_of(new_shape, new_ids)
    left_a, left_b = set(range(len(a))), set(range(len(b)))
    # 1. the same face in the same place
    for j in sorted(left_b):
        for i in sorted(left_a):
            if _same_shape(a[i], b[j], tol) and np.linalg.norm(a[i].centre - b[j].centre) <= tol:
                left_a.discard(i)
                left_b.discard(j)
                d.unchanged += 1
                break
    # 2. changed: the same surface, another size (before moved, so a resized face is not called moved)
    for j in sorted(left_b):
        best, gap = None, float("inf")
        for i in sorted(left_a):
            if _same_surface(a[i], b[j], tol) and not _same_shape(a[i], b[j], tol):
                g = float(np.linalg.norm(a[i].centre - b[j].centre))
                if g < gap:
                    best, gap = i, g
        if best is not None:
            left_a.discard(best)
            left_b.discard(j)
            row = _row(b[j])
            row.update({"was": a[best].fid, "area_was": round(a[best].area, 6)})
            if a[best].radius is not None and b[j].radius is not None and abs(a[best].radius - b[j].radius) > tol:
                row.update({"radius_was": round(a[best].radius, 6), "radius": round(b[j].radius, 6)})
            d.changed.append(row)
    # 3. moved: the same face somewhere else
    for j in sorted(left_b):
        for i in sorted(left_a):
            if _same_shape(a[i], b[j], tol):
                left_a.discard(i)
                left_b.discard(j)
                row = _row(b[j])
                row.update({"was": a[i].fid, "by": [round(float(x), 6) for x in b[j].centre - a[i].centre]})
                d.moved.append(row)
                break
    d.added = [_row(b[j]) for j in sorted(left_b)]
    d.removed = [_row(a[i]) for i in sorted(left_a)]
    if robust.solids(old_shape) and robust.solids(new_shape):
        d.volume = (robust.volume(old_shape), robust.volume(new_shape))
    # distances of the new surface from the old
    if robust.count(old_shape, robust.TopAbs_FACE) and robust.count(new_shape, robust.TopAbs_FACE):
        diag = robust.diagonal(old_shape)
        tg_old = dv.target(old_shape, min(tol / 4, diag / 1000))
        # the new surface is sampled more coarsely: at most SAMPLES points, weighted by area
        tg_new = dv.target(new_shape, max(tol, diag / 400))
        pick = np.arange(len(tg_new.centres))
        if len(pick) > SAMPLES:
            pick = np.random.default_rng(0).choice(pick, SAMPLES, replace=False)
        s_pick, _w = dv.distances(tg_old, tg_new.centres[pick])
        s = np.zeros(len(tg_new.centres))
        s[pick] = s_pick
        area = np.zeros(len(tg_new.centres))
        area[pick] = tg_new.areas[pick]
        off = np.abs(s) > tol
        d.off = float(area[off].sum() / max(area.sum(), 1e-300))
        d.largest_out = float(max(s.max(), 0.0))
        d.largest_in = float(min(s.min(), 0.0))
        for fi in range(tg_new.nfaces):
            on = (tg_new.face_of_tri == fi) & off
            if on.any():
                k = int(np.argmax(np.abs(np.where(on, s, 0))))
                fid = new_ids[fi] if new_ids is not None and fi < len(new_ids) else fi + 1
                d.regions.append({"face": fid, "area": round(float(area[on].sum()), 6),
                                  "worst": round(float(s[k]), 6),
                                  "at": [round(float(x), 6) for x in tg_new.centres[k]]})
        d.regions.sort(key=lambda r: -abs(r["worst"]))
    return d
