"""MATLIB: the material library every project shares (core/matlib.py).

MATLIB, LIST shows every material the model knows and where it comes from; MATLIB, SET adds a
material to the library or changes one (also a built-in one, for this computer); DELETE takes
it out again; KEEP copies a material this project made (MATERIAL, NEW) into the library. The
library is a file outside the project, so MATLIB is not a history step: the changes count from
now on, in this and every other project, and a saved project keeps a copy of what it used.
"""

from __future__ import annotations

from ..core import matlib
from ..core.model import MATERIALS, Material
from ..lang.expr import fmt_num
from .layer_handlers import color_text, parse_color
from .processor import Arg, CommandError, Processor, Raw, Text, command

KINDS = ("LIST", "SHOW", "SET", "DELETE", "KEEP", "FILE")


def source(p: Processor, name: str) -> str:
    """Where a material in the model comes from: built in, library (or built in, changed by the
    library), project (MATERIAL, NEW, or brought by an opened project)."""
    from .project_handlers import _same

    key = name.upper()
    lib = matlib.library()
    now = p.model.materials.get(key)
    if key in p.model.pinned and not _same(p.model.pinned[key], lib.get(key)):
        return "kept with the project"
    if key in lib and _same(now, lib[key]):
        return "library (changes the built-in one)" if key in MATERIALS else "library"
    if key in MATERIALS and _same(now, MATERIALS[key]):
        return "built in"
    return "this project (MATERIAL, NEW)"


def describe(mat: Material) -> str:
    parts = [f"{fmt_num(mat.density)} kg/m3"]
    for label, val, unit in (("E", mat.E, " MPa"), ("nu", mat.nu, ""), ("yield", mat.yield_, " MPa"),
                             ("k", mat.k, " W/mK"), ("expansion", mat.cte, " um/mK"), ("cp", mat.cp, " J/kgK"),
                             ("up to", mat.tmax, " C")):
        if val is not None:
            parts.append(f"{label} {fmt_num(val)}{unit}")
    if mat.look:
        parts.append(f"looks {mat.look.lower()}" + (", shiny" if mat.shiny else ""))
    if mat.color is not None:
        parts.append(f"colour {color_text(mat.color)}")
    if mat.note:
        parts.append(repr(mat.note))
    return ", ".join(parts)


def apply_change(p: Processor, key: str, mat: Material | None) -> None:
    """Put a library change into the model now, and into the steps already run, so undo and a
    rebuild that reuses unchanged steps see it too. ``mat`` None: the library entry is gone."""
    m = p.model
    m.pinned.pop(key, None)
    new = mat if mat is not None else MATERIALS.get(key)
    if new is None:  # gone from the library and not built in: bodies that use it keep it for now
        return
    for snap in [*p._snaps, *(x for e in p.history for x in (getattr(e, "before", None), getattr(e, "after", None)))]:
        model = snap.get("model") if isinstance(snap, dict) else None
        mats = model.get("materials") if isinstance(model, dict) else None
        if isinstance(mats, dict) and (key in mats or mat is not None):  # a new one: every step knows it
            mats[key] = new
    m.put_material(new)


@command(
    "MATLIB",
    Arg("kind", Raw, "LIST", "LIST, SHOW, SET, DELETE, KEEP or FILE"),
    Arg("name", Raw, "", "the material (SET: a new name, or one to change)"),
    Arg("values", Text, "", "SET: name=value words: density=2700 E=69000 nu=0.33 yield=276 k=167 cte=23 "
                            "cp=900 tmax=200 color=SILVER look=ALUMINIUM shiny=yes note=\"6061-T6\""),
    logged=False,
    help=("The material library every project shares (stiffness, strength, heat values, looks): "
          "MATLIB lists the materials · MATLIB, SHOW, STEEL · "
          "MATLIB, SET, AL6061, density=2700 E=68900 nu=0.33 yield=276 k=167 cte=23.6 look=ALUMINIUM · "
          "MATLIB, SET, STEEL, yield=355 (your steel, for every project) · MATLIB, DELETE, AL6061 · "
          "MATLIB, KEEP, CFRP (a MATERIAL, NEW one into the library) · MATLIB, FILE. "
          "MATERIAL gives bodies a material; MASSPROP, STRESS, RENDER and drawings read its values."),
)
def matlib_cmd(p: Processor, kind, name, values):
    m = p.model
    k = (kind or "LIST").strip().upper()
    if k not in KINDS:
        raise CommandError(f"MATLIB: kind is one of {', '.join(KINDS)}")
    key = name.strip().upper()
    if key and k != "SET":
        from ..core.model import MATERIAL_ALIASES

        key = MATERIAL_ALIASES.get(key, key)
    err = matlib.problem()
    if err and k != "FILE":
        raise CommandError(f"MATLIB: {err} (fix the file, or move it away; MATLIB, FILE says where it is)")
    if k == "FILE":
        f = matlib.path()
        n = len(matlib.library())
        p.give_report("MATLIB", {"file": f, "count": n, "problem": err})
        return f"the material library is {f} ({n} material{'s' if n != 1 else ''})" + (f"; {err}" if err else "")
    if k == "LIST":
        rows = []
        lines = []
        used: dict[str, list[int]] = {}
        for bid, b in m.bodies.items():
            if b.material:
                used.setdefault(b.material.upper(), []).append(bid)
        for nm, mat in sorted(m.materials.items(), key=lambda kv: (kv[0] not in MATERIALS, kv[0])):
            d = mat.props()
            d["source"] = source(p, nm)
            d["bodies"] = sorted(used.get(nm, []))
            rows.append(d)
            lines.append(f"  {nm}: {describe(mat)} [{d['source']}]"
                         + (f", bodies {', '.join(map(str, d['bodies'][:8]))}" if d["bodies"] else ""))
        p.give_report("MATLIB", {"file": matlib.path(), "materials": rows})
        return f"{len(rows)} materials (library {matlib.path()}):\n" + "\n".join(lines)
    if not key:
        raise CommandError(f"MATLIB, {k}: name the material")
    if k == "SHOW":
        mat = m.materials.get(key)
        if mat is None:
            raise CommandError(f"MATLIB: no material {name.strip()} (MATLIB lists them)")
        d = mat.props()
        d["source"] = source(p, key)
        p.give_report("MATLIB", d)
        return f"{key}: {describe(mat)} [{d['source']}]"
    if k == "DELETE":
        if values.strip():
            raise CommandError("MATLIB, DELETE takes only a name")
        if not matlib.remove(key):
            where = "built in" if key in MATERIALS else "not in the library"
            raise CommandError(f"MATLIB: {key} is {where}; DELETE takes out what MATLIB, SET put in")
        apply_change(p, key, None)
        p.give_report("MATLIB", {"deleted": key, "file": matlib.path()})
        back = " (back to the built-in values)" if key in MATERIALS else ""
        users = [i for i, b in m.bodies.items() if b.material.upper() == key]
        keep = f"; bodies {', '.join(map(str, users[:8]))} keep it until the project is opened again" \
            if users and key not in MATERIALS else ""
        return f"{key} taken out of the material library{back}{keep}"
    if k == "KEEP":
        mat = m.materials.get(key)
        if mat is None:
            raise CommandError(f"MATLIB: no material {name.strip()} in this project")
        f = matlib.put(mat)
        apply_change(p, key, mat)
        p.give_report("MATLIB", {"kept": key, "file": f, **mat.props()})
        return f"{key} is in the material library now ({describe(mat)})"
    # SET
    if not values.strip():
        raise CommandError("MATLIB, SET: give values, e.g. MATLIB, SET, AL6061, density=2700 E=68900 yield=276")
    try:
        vals = matlib.parse_values(values)
    except matlib.LibraryError as exc:
        raise CommandError(f"MATLIB: {exc}") from None
    lib = matlib.read()
    base = lib.get(key) or m.materials.get(key)
    d = base.props() if base is not None else {"name": key}
    d["name"] = key
    for f, v in vals.items():
        if f == "color":
            col = parse_color(p, "MATLIB", v)
            if col is None:
                d.pop("color", None)
            else:
                d["color"] = list(col)
        elif v is None:
            d.pop(f, None)
        else:
            d[f] = v
    if "look" in vals and not vals["look"]:
        d.pop("look", None)
    try:
        mat = matlib.from_dict(d)
    except matlib.LibraryError as exc:
        raise CommandError(f"MATLIB: {exc}") from None
    f = matlib.put(mat)
    apply_change(p, key, mat)
    p.give_report("MATLIB", {"set": key, "file": f, **mat.props()})
    new = "added to" if base is None else "changed in"
    return f"{key} {new} the material library: {describe(mat)}"
