"""What changed between two saved states of the model.

States are the processor's snapshots (one after every history entry), so
``diff_states(p, p._snaps[3], p._snaps[7])`` says what entries 4 to 7 did.
Bodies are immutable and shared between snapshots, so an unchanged body is
the very same object in both and costs nothing to compare.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..commands.queries import bbox
from ..geometry import robust
from .describe import _value, num, vec

if TYPE_CHECKING:
    from ..commands.processor import Processor


def _vol(body) -> float | None:
    return num(robust.volume(body.shape)) if robust.solids(body.shape) else None


def _brief(body) -> dict[str, Any]:
    row: dict[str, Any] = {"id": body.id, "name": body.name}
    v = _vol(body)
    if v is not None:
        row["volume"] = v
    row["bbox"] = vec(bbox(body.shape))
    row["faces"] = len(body.entity_ids["FACE"])
    return row


def diff_states(a: dict, b: dict, limit: int = 50) -> dict[str, Any]:
    """Changes from state a to state b (processor states: model, params ...)."""
    ma, mb = a["model"], b["model"]
    ba, bb = ma["bodies"], mb["bodies"]
    out: dict[str, Any] = {}
    added = [_brief(bb[i]) for i in sorted(set(bb) - set(ba))]
    removed = [{"id": i, "name": ba[i].name} for i in sorted(set(ba) - set(bb))]
    changed = []
    for i in sorted(set(ba) & set(bb)):
        x, y = ba[i], bb[i]
        if x is y:
            continue
        row: dict[str, Any] = {"id": i, "name": y.name}
        if x.name != y.name:
            row["was_named"] = x.name
        if x.shape is not y.shape:
            va, vb = _vol(x), _vol(y)
            if va is not None or vb is not None:
                row["volume"] = [va, vb]
            box_a, box_b = vec(bbox(x.shape)), vec(bbox(y.shape))
            if box_a != box_b:
                row["bbox"] = [box_a, box_b]
            fa, fb = set(x.entity_ids["FACE"]), set(y.entity_ids["FACE"])
            if fa != fb:
                gone, new = sorted(fa - fb), sorted(fb - fa)
                row["faces"] = {"kept": len(fa & fb), "removed": gone[:limit], "added": new[:limit]}
                if len(gone) > limit or len(new) > limit:
                    row["faces"]["more"] = max(len(gone), len(new)) - limit
        for key in ("layer", "color", "material"):
            if getattr(x, key) != getattr(y, key):
                row[key] = [getattr(x, key), getattr(y, key)]
        if len(row) > 2 or "was_named" in row:
            changed.append(row)
    if added:
        out["added"] = added[:limit]
    if removed:
        out["removed"] = removed[:limit]
    if changed:
        out["changed"] = changed[:limit]
    pa, pb = a.get("params", {}), b.get("params", {})
    params = {k: [_value(pa[k]) if k in pa else None, _value(pb[k]) if k in pb else None]
              for k in sorted(set(pa) | set(pb)) if pa.get(k) != pb.get(k)}
    if params:
        out["params"] = params
    da, db = ma.get("datums", {}), mb.get("datums", {})
    if set(da) != set(db) or any(da[k] != db[k] for k in set(da) & set(db)):
        out["datums"] = {"added": sorted(db[k].name for k in set(db) - set(da)),
                         "removed": sorted(da[k].name for k in set(da) - set(db)),
                         "changed": sorted(db[k].name for k in set(da) & set(db) if da[k] != db[k])}
    sa, sb = ma.get("sketches", {}), mb.get("sketches", {})
    if set(sa) != set(sb) or any(sa[k] is not sb[k] for k in set(sa) & set(sb)):
        out["sketches"] = {"added": sorted(sb[k].name for k in set(sb) - set(sa)),
                           "removed": sorted(sa[k].name for k in set(sa) - set(sb)),
                           "changed": sorted(sb[k].name for k in set(sa) & set(sb) if sa[k] is not sb[k])}
    if ma.get("selection") != mb.get("selection") or ma.get("selection_kind") != mb.get("selection_kind"):
        out["selection"] = {"kind": mb.get("selection_kind"), "ids": list(mb.get("selection", []))[:limit]}
    if ma.get("units") != mb.get("units"):
        out["units"] = [ma.get("units"), mb.get("units")]
    return out


def diff_entries(p: "Processor", first: int, last: int) -> dict[str, Any]:
    """Changes made by history entries first+1 .. last (0 is the empty start)."""
    n = p.cursor
    if not (0 <= first <= n and 0 <= last <= n):
        raise ValueError(f"positions go from 0 (the empty start) to {n} (now)")
    out = {"from": first, "to": last}
    out.update(diff_states(p._snaps[first], p._snaps[last]))
    return out


def _val(v) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, list):
        return "(" + ", ".join(_val(x) for x in v) + ")"
    return repr(v) if isinstance(v, str) else str(v)


def diff_text(d: dict[str, Any]) -> str:
    """The same changes as short lines, for the command line."""
    lines = []
    for row in d.get("added", []):
        v = f", volume {row['volume']:g}" if "volume" in row else ""
        lines.append(f"+ body {row['id']} {row['name']}: {row['faces']} faces{v}")
    for row in d.get("removed", []):
        lines.append(f"- body {row['id']} {row['name']}")
    for row in d.get("changed", []):
        bits = []
        if "was_named" in row:
            bits.append(f"renamed from {row['was_named']}")
        if "volume" in row:
            va, vb = row["volume"]
            bits.append(f"volume {va:g} -> {vb:g}" if va is not None and vb is not None else "volume changed")
        if "faces" in row:
            f = row["faces"]
            bits.append(f"faces +{len(f['added'])} -{len(f['removed'])}")
        if "bbox" in row and "volume" not in row:
            bits.append("moved or resized")
        for key in ("layer", "color", "material"):
            if key in row:
                bits.append(f"{key} changed")
        lines.append(f"~ body {row['id']} {row['name']}: " + ", ".join(bits))
    for k, (va, vb) in d.get("params", {}).items():
        if va is None:
            lines.append(f"  {k} = {_val(vb)} (new)")
        elif vb is None:
            lines.append(f"  {k} removed (was {_val(va)})")
        else:
            lines.append(f"  {k}: {_val(va)} -> {_val(vb)}")
    for what in ("datums", "sketches"):
        if what in d:
            parts = [f"{key} {', '.join(v)}" for key, v in d[what].items() if v]
            lines.append(f"  {what}: " + "; ".join(parts))
    if "selection" in d:
        lines.append(f"  selection: {d['selection']['kind']} {', '.join(map(str, d['selection']['ids']))}")
    return "\n".join(lines) if lines else "no changes"
