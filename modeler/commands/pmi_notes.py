"""The model's notes as STEP annotations and back (PLAN item 73).

``EXPORT, STEP`` writes the sizes (NOTE, SIZE), hole and fit diameters (NOTE, HOLE / FIT), geometric
tolerances (NOTE, GDT) and datums (NOTE, DATUM) on the exported bodies into the file as AP242
annotations (geometry/step_pmi.py), so other programs read them as sizes and tolerances, not as
pictures. ``IMPORT, STEP`` turns the annotations of a file back into notes on the new bodies.
Plain text notes stay in the project only.
"""

from __future__ import annotations

import re

import numpy as np

from .processor import Processor

DIA_RE = re.compile(r"^\s*[øØ⌀]\s*([0-9.]+)(?:\s+((?:js|JS|[A-Za-z])\d{1,2})\b)?")


def _near(shapes, q, tol: float) -> bool:
    from ..geometry import step_pmi

    return any(step_pmi._dist(s, q) <= tol for s in shapes)


def notes_to_records(p: Processor, bodies) -> list[dict]:
    """Records for the notes pinned to these bodies."""
    from ..geometry import fits as ft
    from ..geometry import robust

    m = p.model
    shapes = [b.shape for b in bodies if robust.solids(b.shape)]
    if not shapes or not m.notes:
        return []
    from .drawsheet_handlers import _tolerance

    tol = _tolerance(p, bodies) * 10
    out = []
    for n in m.notes:
        anchor = n.anchor if n.anchor is not None else n.at
        if n.frame is not None:
            if not _near(shapes, anchor, tol):
                continue
            if n.frame.kind == "DATUM":
                out.append({"kind": "DATUM", "letter": n.frame.tol, "point": tuple(anchor)})
            else:
                t = n.frame.tol
                dia = t[:1] in ("ø", "Ø", "⌀")
                out.append({"kind": "GDT", "type": n.frame.kind, "value": float(t[1:] if dia else t), "dia": dia,
                            "datums": list(n.frame.datums), "point": tuple(anchor)})
        elif n.span is not None:
            a, b = n.span
            if not (_near(shapes, a, tol) and _near(shapes, b, tol)):
                continue
            out.append({"kind": "SIZE", "a": tuple(a), "b": tuple(b),
                        "value": float(np.linalg.norm(np.subtract(b, a)))})
        elif n.anchor is not None:
            hit = DIA_RE.match(n.text)
            if not hit or not _near(shapes, n.anchor, tol):
                continue
            d = float(hit.group(1))
            rec = {"kind": "DIAMETER", "value": d, "point": tuple(n.anchor)}
            if hit.group(2):
                try:
                    lim = ft.limits(hit.group(2), d)
                    rec["upper"], rec["lower"] = lim.upper / 1000, lim.lower / 1000
                except ft.FitError:
                    pass
            out.append(rec)
    return out


def _fit_name(d: float, upper: float, lower: float, hole: bool) -> str:
    """The ISO fit whose limits these are (H7 ...), or ""."""
    from ..geometry import fits as ft

    letters = "ABCDEFGHJKMNPRSTUVXYZ" if hole else "abcdefghjkmnprstuvxyz"
    names = [f"{c}{g}" for c in letters for g in range(4, 13)] + [f"{'JS' if hole else 'js'}{g}" for g in range(4, 13)]
    for name in names:
        try:
            lim = ft.limits(name, d)
        except Exception:  # noqa: BLE001 - not every letter has every grade
            continue
        if abs(lim.upper / 1000 - upper) < 5e-7 and abs(lim.lower / 1000 - lower) < 5e-7:
            return name
    return ""


def records_to_notes(p: Processor, records: list[dict], body_ids: list[int]) -> int:
    """Notes on the new bodies for the records a STEP file gave. Returns how many were made."""
    from ..core.model import Note
    from ..geometry import step_pmi
    from ..geometry import tolerances as tl
    from . import note_handlers as nh
    from .drawsheet_handlers import touches

    m = p.model
    parts = [(None, m.body(b).shape) for b in body_ids]
    if not parts:
        return 0
    made = 0
    have = {n.frame.tol for n in m.notes if n.frame is not None and n.frame.kind == "DATUM"}
    order = {"DATUM": 0, "GDT": 1, "DIAMETER": 2, "SIZE": 3}
    for r in sorted(records, key=lambda r: order.get(r["kind"], 9)):
        try:
            if r["kind"] == "SIZE":
                a, b = np.asarray(r["a"], float), np.asarray(r["b"], float)
                txt = nh._num(float(np.linalg.norm(b - a)))
                m.add_note(Note(txt, tuple(map(float, (a + b) / 2)), None,
                                (tuple(map(float, a)), tuple(map(float, b))), ends=(touches(p, a), touches(p, b))))
            elif r["kind"] == "DIAMETER":
                hit = step_pmi._nearest_face(parts, r["point"], round_only=True)
                if hit is None:
                    continue
                face = hit[1]
                d = float(r["value"])
                txt = f"{nh.DIA}{nh._num(d)}"
                if r.get("upper") is not None:
                    _d, shaft = nh._round_dia("FACE", face)
                    name = _fit_name(d, r["upper"], r["lower"], not shaft) or _fit_name(d, r["upper"], r["lower"], shaft)
                    if name:
                        from ..geometry import fits as ft

                        txt += f" {name} ({ft.limits(name, d).text()})"
                    else:
                        txt += f" ({r['upper']:+.3f}/{r['lower']:+.3f})"
                at, anchor = nh._rim_placed(p, "FACE", face)
                m.add_note(Note(txt, nh._stacked(p, at, anchor), anchor))
            elif r["kind"] in ("GDT", "DATUM"):
                hit = step_pmi._nearest_face(parts, r["point"])
                if hit is None:
                    continue
                if r["kind"] == "DATUM":
                    if r["letter"] in have:
                        continue
                    fr = tl.datum(r["letter"])
                    have.add(fr.tol)
                else:
                    zone = ("ø" if r.get("dia") else "") + f"{r['value']:g}"
                    fr, _warn = tl.frame(r["type"], zone, list(r.get("datums", ())))
                at, anchor = nh._placed(p, "FACE", hit[1])
                m.add_note(Note(fr.text(), nh._stacked(p, at, anchor), anchor, None, fr))
            else:
                continue
            made += 1
        except Exception:  # noqa: BLE001 - one odd annotation must not stop the import
            continue
    return made
