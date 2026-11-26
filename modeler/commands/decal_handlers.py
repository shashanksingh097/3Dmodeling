"""TEXTURE and DECAL: pictures on bodies and faces, shown live in the view and in RENDER (PLAN item 116).

``TEXTURE, desk, oak.jpg, 80`` draws the picture over every face of the body, one tile 80 mm wide;
``TEXTURE, WOOD, oak.jpg, 80`` gives it to the material, so every body of WOOD shows it;
``TEXTURE, desk, OFF`` takes it off. ``DECAL, logo, 12, acme.png, 40`` puts a picture 40 mm wide in
the middle of face 12 (a flat or a round face), ``DECAL, logo, 12, acme.png, 40, 10, -5, 30`` moves it
10 along the face's x and -5 along its y and turns it 30 degrees. A decal follows its face through
edits (face IDs stay with their faces). Both are history steps; ``DECAL`` lists the decals as data
(report "decals"), ``DECAL, DELETE, logo`` and ``DECAL, CLEAR`` remove them.
"""

from __future__ import annotations

import os
from dataclasses import replace

from ..core.model import ModelError
from ..geometry import decal as dc
from ..lang.expr import fmt_num
from ..lang.script import is_ident
from .layer_handlers import _ids_text, target_bodies
from .processor import REGISTRY, Arg, CommandError, Path, Processor, Raw, command


def _n(v: float) -> str:
    return fmt_num(round(float(v), 4) + 0.0)


def _picture(p: Processor, file: str, what: str) -> str:
    path = p.file_map.get(file, file)
    if not os.path.isfile(path) and p.project_dir and not os.path.isabs(path):
        near = os.path.join(p.project_dir, path)
        path = near if os.path.isfile(near) else path
    if not os.path.isfile(path):
        raise CommandError(f"{what}: no such file: {file}")
    if os.path.splitext(path)[1].lower() not in dc.PICTURE_TYPES:
        raise CommandError(f"{what}: the picture is a {', '.join(dc.PICTURE_TYPES)} file")
    try:
        dc.image_size(path)
    except dc.DecalError as exc:
        raise CommandError(f"{what}: {exc}") from None
    return os.path.abspath(path)


# ---- TEXTURE ------------------------------------------------------------------------------

@command(
    "TEXTURE",
    Arg("target", Raw, help="a body, SEL, ALL or a material name (every body of that material)"),
    Arg("file", Path, help="the picture (.png, .jpg ...), or OFF to take the texture off"),
    Arg("size", float, 0.0, "one tile of the picture, mm (default: a quarter of the body's biggest side)"),
    help="A picture over every face, tiled: TEXTURE, desk, oak.jpg, 80 (tiles 80 mm wide) · TEXTURE, WOOD, "
         "oak.jpg, 80 (every body of the material WOOD) · TEXTURE, SEL, OFF. Shown in the view and by RENDER.",
)
def texture(p: Processor, target, file, size):
    m = p.model
    off = file.strip().strip('"').upper() == "OFF"
    if size < 0:
        raise CommandError("TEXTURE: the tile size cannot be negative")
    word = target.strip()
    mat = None
    if word.upper() not in ("SEL", "ALL", "LAST"):
        try:
            m.body(p._body_ref(REGISTRY["TEXTURE"], word))
        except (CommandError, ModelError):
            key = word.upper()
            try:
                mat = m.material(key)
            except ModelError:
                mat = None
            if mat is None:
                raise CommandError(f"TEXTURE: {word!r} is neither a body nor a material") from None
    if mat is not None:
        if off:
            m.put_material(replace(mat, texture="", texture_size=0.0))
            return f"material {mat.name}: no texture"
        if size <= 0:
            raise CommandError("TEXTURE: give a material's texture a tile size in mm (TEXTURE, WOOD, oak.jpg, 80)")
        path = _picture(p, file, "TEXTURE")
        m.put_material(replace(mat, texture=path, texture_size=float(size)))
        users = [b for b in m.bodies.values() if b.material.upper() == mat.name.upper()]
        return (f"material {mat.name}: texture {os.path.basename(path)}, tiles {_n(size)} mm"
                f" ({len(users)} bod{'y' if len(users) == 1 else 'ies'} of it)")
    ids = target_bodies(p, "TEXTURE", target)
    if off:
        for bid in ids:
            # ("", 0): no texture, even when its material has one
            m.set_style(bid, texture=("", 0.0) if m.body(bid).material else None)
        return f"{_ids_text(ids)}: no texture"
    path = _picture(p, file, "TEXTURE")
    sizes = []
    for bid in ids:
        s = float(size)
        if s <= 0:
            s = _auto_size(m.body(bid).shape)
        m.set_style(bid, texture=(path, s))
        sizes.append(s)
    many = len(set(round(s, 6) for s in sizes)) > 1
    size_text = "tiles a quarter of each body" if many else f"tiles {_n(sizes[0])} mm"
    big = [bid for bid in ids if len(dc.faces(m.body(bid).shape)) > dc.MAX_TEXTURED_FACES]
    note = (f"; {_ids_text(big)} ha{'s' if len(big) == 1 else 've'} more than {dc.MAX_TEXTURED_FACES} faces and "
            "is drawn without it") if big else ""
    return f"{_ids_text(ids)}: texture {os.path.basename(path)}, {size_text}{note}"


def _auto_size(shape) -> float:
    return round(dc.size_of(shape) / 4, 3) or 10.0


# ---- DECAL ------------------------------------------------------------------------------------

def _face_of(p: Processor, raw: str) -> int:
    m = p.model
    s = str(raw).strip()
    if not s or s.upper() == "SEL":
        if m.selection_kind != "FACE" or len(m.selection) != 1:
            raise CommandError("DECAL: pick one face first, or give its ID (DECAL, logo, 12, acme.png, 40)")
        return int(m.selection[0])
    try:
        gid = int(round(float(p.evaluate(s))))
    except Exception:  # noqa: BLE001
        raise CommandError(f"DECAL: the face is a face ID or SEL, not {s!r}") from None
    try:
        m.entity_owner("FACE", gid)
    except ModelError as exc:
        raise CommandError(f"DECAL: {exc}") from None
    return gid


def place(model, d: dict):
    """A decal's patch now (TopoDS_Face) and whether it hangs over its face; DecalError/ModelError when its
    face is gone or is not flat or round any more."""
    face = dc._as_face(model.entity_shape("FACE", int(d["face"])))
    shape = model.body(model.entity_owner("FACE", int(d["face"]))[0]).shape
    size = dc.size_of(shape)
    f = dc.frame(face)
    lift = max(1e-4 * size, 4e-3 * f["radius"]) if f["kind"] == "ROUND" else 2e-4 * size
    pf = dc.patch(face, d["width"], d["height"], d.get("dx", 0.0), d.get("dy", 0.0), d.get("angle", 0.0), lift)
    return pf, dc.overhangs(face, pf)


def report(model) -> list[dict]:
    out = []
    for d in model.decals:
        row = {k: d[k] for k in ("name", "face", "file", "width", "height", "dx", "dy", "angle")}
        try:
            bid = model.entity_owner("FACE", int(d["face"]))[0]
            row["body"] = model.body(bid).name
            _pf, over = place(model, d)
            row["overhangs"] = over
            row["error"] = ""
        except (ModelError, dc.DecalError) as exc:
            row["error"] = str(exc)
        out.append(row)
    return out


def _line(row: dict) -> str:
    where = f"face {row['face']}" + (f" of {row['body']}" if row.get("body") else "")
    state = f": {row['error']}" if row.get("error") else (" (hangs over the face's edge)" if row.get("overhangs") else "")
    extra = "".join(f", {k} {_n(row[k])}" for k in ("dx", "dy", "angle") if row.get(k))
    return (f"  {row['name']}: {os.path.basename(row['file'])} on {where}, {_n(row['width'])} x {_n(row['height'])}"
            f"{extra}{state}")


@command(
    "DECAL",
    Arg("name", Raw, "", "the decal's name; DELETE, CLEAR or nothing (list them)"),
    Arg("face", Raw, "", "the face (an ID, or SEL); with DELETE: the decal's name"),
    Arg("file", Path, "", "the picture (.png with a see-through background works best)"),
    Arg("width", float, 0.0, "how wide, mm (the height follows the picture)"),
    Arg("dx", float, 0.0, "move it along the face's x from the face's middle"),
    Arg("dy", float, 0.0, "move it along the face's y"),
    Arg("angle", float, 0.0, "turn it, degrees (on a round face 0 or 180)"),
    help="A picture on a face, like a sticker: DECAL, logo, 12, acme.png, 40 (40 mm wide, in the middle of face "
         "12) · DECAL, logo, SEL, acme.png, 40, 10, -5, 30 (moved 10, -5 and turned 30 degrees). Flat and round "
         "faces; it follows the face through edits. DECAL alone lists them; DECAL, DELETE, logo · DECAL, CLEAR.",
)
def decal(p: Processor, name, face, file, width, dx, dy, angle):
    m = p.model
    word = str(name).strip()
    up = word.upper()
    if not word:
        rows = report(m)
        p.give_report("decals", {"decals": rows})
        if not rows:
            return "no decals (DECAL, name, face, picture, width adds one)"
        return "\n".join([f"{len(rows)} decal{'s' if len(rows) != 1 else ''}:"] + [_line(r) for r in rows])
    if up == "CLEAR":
        n = len(m.decals)
        m.set_decals([])
        return f"removed {n} decal{'s' if n != 1 else ''}"
    if up == "DELETE":
        target = str(face).strip().upper()
        left = [d for d in m.decals if d["name"].upper() != target]
        if len(left) == len(m.decals):
            raise CommandError(f"DECAL: there is no decal {str(face).strip()!r} "
                               f"(decals: {', '.join(d['name'] for d in m.decals) or 'none'})")
        m.set_decals(left)
        return f"removed decal {str(face).strip()}"
    if not is_ident(word):
        raise CommandError(f"DECAL: {word!r} is not a valid name (letters, digits, _)")
    if not str(file).strip():
        raise CommandError("DECAL: which picture? (DECAL, logo, 12, acme.png, 40)")
    if width <= 0:
        raise CommandError("DECAL: the width must be more than 0")
    gid = _face_of(p, face)
    path = _picture(p, file, "DECAL")
    w_px, h_px = dc.image_size(path)
    new = {"name": word, "face": gid, "file": path, "width": float(width), "height": float(width) * h_px / w_px,
           "dx": float(dx), "dy": float(dy), "angle": float(angle)}
    try:
        place(m, new)
    except (ModelError, dc.DecalError) as exc:
        raise CommandError(f"DECAL: {exc}") from None
    decals = [d for d in m.decals if d["name"].upper() != up]
    replaced = len(decals) != len(m.decals)
    m.set_decals(decals + [new])
    p.give_report("decals", {"decals": report(m)})
    row = next(r for r in report(m) if r["name"] == word)
    return f"{'changed' if replaced else 'added'} decal {_line(row).strip()}"
