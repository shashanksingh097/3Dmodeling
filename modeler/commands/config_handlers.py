"""Configurations (CONFIG, USECONFIG) and the parts list (BOM).

A configuration is a named set of parameter values for one model: the sizes
of a family of parts. ``CONFIG, big, "W = 60, H = 20"`` is a history entry that
defines (or redefines) one. ``USECONFIG, big`` makes the model use it: those
parameters keep the configuration's values whatever their own assignments
say (the way ``-D`` does in the batch runner) and the whole history runs
again. ``USECONFIG, DEFAULT`` goes back to the history's own values. Which
configuration is in use is not a history step: it is saved with the project
and the batch runner takes it as ``-C name``.

``BOM`` lists the parts of the model: one row per part (instances of the same
part with the same parameter values counted together) and one row per named
solid body, with material, volume and mass. ``BOM, file.csv`` writes it as CSV.
"""

from __future__ import annotations

import csv
import os

from ..core.model import UNITS
from ..lang.expr import format_value
from ..lang.script import ScriptError, split_args
from .processor import Arg, CommandError, Path, Processor, Text, command

RESERVED_CONFIG = {"DEFAULT", "NONE", "LIST"}


def parse_values(p: Processor, text: str, what: str) -> dict:
    """'W = 60, H = 20' (or 'W=60 H=20' over lines) -> {"W": 60, "H": 20}, values evaluated now."""
    out = {}
    parts = []
    for line in text.replace(";", "\n").splitlines():
        try:
            parts += [s for s in split_args(line) if s.strip()]
        except ScriptError as exc:
            raise CommandError(f"{what}: {exc}") from None
    for item in parts:
        name, eq, expr = item.partition("=")
        name = name.strip().upper()
        if not eq or not name or not expr.strip():
            raise CommandError(f"{what}: {item.strip()!r} is not NAME = value")
        if not name.replace("_", "").isalnum() or name[0].isdigit():
            raise CommandError(f"{what}: {name!r} is not a parameter name")
        try:
            out[name] = p.evaluator.eval(expr.strip())
        except Exception as exc:  # noqa: BLE001 - an expression error, said plainly
            raise CommandError(f"{what}: {name}: {exc}") from None
    if not out:
        raise CommandError(f'{what}: give the values, e.g. "W = 60, H = 20"')
    return out


def describe_config(values: dict) -> str:
    return ", ".join(f"{k} = {format_value(v)}" for k, v in values.items())


def config_list(p: Processor) -> str:
    if not p.configs:
        return 'no configurations (CONFIG, name, "W = 60, H = 20" makes one)'
    lines = []
    for name, vals in p.configs.items():
        mark = "*" if name == p.config else " "
        lines.append(f"{mark} {name}: {describe_config(vals)}")
    if not p.config:
        lines.append("(in use: DEFAULT, the history's own values)")
    return "\n".join(lines)


@command(
    "CONFIG",
    Arg("name", str, help="the configuration's name"),
    Arg("values", Text, "", 'its parameter values, e.g. "W = 60, H = 20"'),
    help='Define a configuration, a named set of parameter values for a family of sizes: CONFIG, big, '
         '"W = 60, H = 20" · USECONFIG, big switches to it and rebuilds; USECONFIG, DEFAULT goes back; '
         'USECONFIG alone lists them',
)
def config(p: Processor, name, values):
    key = name.upper()
    if key in RESERVED_CONFIG:
        raise CommandError(f"CONFIG: {name} is reserved; pick another name")
    if not values.strip():
        if key in p.configs:
            return f"{key}: {describe_config(p.configs[key])}"
        raise CommandError(f'CONFIG: no configuration {name}; give its values: CONFIG, {name}, "W = 60"')
    vals = parse_values(p, values, "CONFIG")
    unknown = [k for k in vals if k not in p.params]
    p.configs[key] = vals
    if key == p.config and vals != p.config_values:  # the one in use changed: from the next rebuild
        p.config_values = dict(vals)
        p.warn(f"CONFIG: {key} is in use; USECONFIG, {key} rebuilds the model with the new values")
    note = f" ({', '.join(unknown)} not set yet in the history)" if unknown else ""
    return f"configuration {key}: {describe_config(vals)}{note}"


def use_config(p: Processor, name: str) -> str:
    """Switch configuration and rebuild the whole history (a fixed parameter changes what the
    assignments give, which the skip-unchanged rebuild cannot see)."""
    key = name.upper()
    if key in ("DEFAULT", "NONE", ""):
        key, vals = "", {}
    elif key not in p.configs:
        raise CommandError(f"USECONFIG: no configuration {name} (CONFIG lists them)")
    else:
        vals = dict(p.configs[key])
    old = (p.config, dict(p.config_values))
    p.config, p.config_values = key, vals
    if not p.history:
        return f"using {key or 'DEFAULT'}"
    saved = p.history_backup()
    try:
        msg = p.rebuild(0, skip=False)
    except Exception:
        p.history_restore(saved)
        p.config, p.config_values = old
        raise
    return f"using {key or 'DEFAULT'}" + (f" ({describe_config(vals)})" if vals else "") + f": {msg}"


@command(
    "USECONFIG",
    Arg("name", str, "", "a configuration made with CONFIG, or DEFAULT for the history's own values (none: list)"),
    session=True,
    help="Use a configuration: its parameters keep its values and the whole model rebuilds: USECONFIG, big · "
         "USECONFIG, DEFAULT goes back to the values in the history · USECONFIG alone lists the configurations "
         "(* marks the one in use). Not a history step; saved with the project",
)
def useconfig(p: Processor, name):
    if not name:
        return config_list(p)
    return use_config(p, name)


# ---- the parts list -------------------------------------------------------------------
def bom_rows(p: Processor) -> list[dict]:
    """One row per part (instances with the same values together) and per other solid body."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    from ..geometry import meshbody as mb
    from ..geometry import robust

    m = p.model
    scale_mm = UNITS[m.units]
    groups: dict[tuple, dict] = {}
    order = []
    for bid in sorted(m.bodies):
        if bid in m.hidden:
            continue  # used up or kept by the history, not part of the result
        body = m.bodies[bid]
        shape = body.shape
        if mb.is_mesh(shape):
            pts, t = mb.arrays(shape)
            if not mb.closed(t):
                continue
            vol = abs(mb.volume(pts, t))
        elif robust.solids(shape):
            g = GProp_GProps()
            (getattr(BRepGProp, "VolumeProperties_s", None) or BRepGProp.VolumeProperties)(shape, g)
            vol = abs(g.Mass())
        else:
            continue  # curves and open surfaces are not parts
        inst = m.instances.get(bid)
        if inst is not None:
            part, given = inst
            values = _part_values(p, part, dict(given))
            key = ("part", part.upper(), tuple(values.items()), body.material.upper())
            pd = p.parts.get(part.upper())
            label = pd.name if pd is not None else part
            detail = ", ".join(f"{k} = {format_value(v)}" for k, v in values.items())
        else:
            named = not body.name.lower().startswith("body")
            key = ("body", body.name.upper() if named else bid, body.material.upper())
            label = body.name
            detail = ""
        row = groups.get(key)
        if row is None:
            dens = m.density(bid)
            row = {"item": 0, "name": label, "values": detail, "qty": 0, "material": body.material or "",
                   "volume": vol, "mass": dens * vol * scale_mm ** 3 * 1e-9 if dens else None, "bodies": []}
            groups[key] = row
            order.append(key)
        row["qty"] += 1
        row["bodies"].append(bid)
    rows = [groups[k] for k in order]
    for i, r in enumerate(rows, 1):
        r["item"] = i
    return rows


def _part_values(p: Processor, part: str, given: dict) -> dict:
    """Every parameter of a placed part: the ones given to INST, else the part's defaults."""
    pd = p.parts.get(part.upper())
    if pd is None:
        return dict(sorted(given.items()))
    out = {}
    for name, default in pd.params:
        key = name.upper()
        if key in given:
            out[key] = given[key]
        elif default is not None:
            try:
                out[key] = p.evaluator.eval(default)
            except Exception:  # noqa: BLE001 - a default that needs other values: show it as written
                out[key] = default
    for k, v in given.items():
        out.setdefault(k, v)
    return out


def _num(v: float) -> str:
    """4 significant digits, without an exponent for everyday sizes: 48,000 · 0.03241."""
    r = float(f"{v:.4g}")
    return f"{r:,.10g}" if r == 0 or 1e-4 <= abs(r) < 1e12 else f"{v:.4g}"


def bom_text(p: Processor, rows: list[dict]) -> str:
    if not rows:
        return "no solid bodies: the parts list is empty"
    u = p.model.units.lower()
    lines = [f"{'#':>3}  {'qty':>3}  part", "-" * 40]
    total = 0.0
    any_mass = False
    for r in rows:
        bits = [f"{r['item']:>3}  {r['qty']:>3}  {r['name']}"]
        if r["values"]:
            bits.append(f"({r['values']})")
        if r["material"]:
            bits.append(r["material"].lower())
        bits.append(f"{_num(r['volume'])} {u}3")
        if r["mass"] is not None:
            bits.append(f"{_num(r['mass'])} kg")
            total += r["mass"] * r["qty"]
            any_mass = True
        bits.append("bodies " + ", ".join(map(str, r["bodies"][:8])) + ("..." if len(r["bodies"]) > 8 else ""))
        lines.append("  ".join(bits))
    count = sum(r["qty"] for r in rows)
    lines.append(f"{len(rows)} kinds, {count} pieces" + (f", {_num(total)} kg in all (bodies with a material)"
                                                          if any_mass else ""))
    return "\n".join(lines)


def write_bom_csv(p: Processor, rows: list[dict], path: str) -> None:
    u = p.model.units.lower()
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["item", "qty", "part", "parameters", "material", f"volume ({u}3)", "mass (kg)", "bodies"])
        for r in rows:
            w.writerow([r["item"], r["qty"], r["name"], r["values"], r["material"], f"{r['volume']:.6g}",
                        "" if r["mass"] is None else f"{r['mass']:.6g}", " ".join(map(str, r["bodies"]))])


@command(
    "BOM",
    Arg("file", Path, "", "a .csv file to write it to (none: just show it)"),
    Arg("config", str, "", "the configuration to list (default: the one in use)"),
    logged=False,
    help="The parts list: one row per part (instances of a part with the same values counted together) and per "
         "named solid, with quantity, material, volume and mass: BOM · BOM, parts.csv also writes it as CSV · "
         "BOM, , big lists configuration big without switching to it",
)
def bom(p: Processor, file, config):
    q = p
    if config and config.upper() != (p.config or "DEFAULT"):
        from .variant_handlers import variant

        try:
            q = variant(p, config)
        except CommandError as exc:
            raise CommandError(f"BOM: {exc}") from None
    rows = bom_rows(q)
    text = bom_text(q, rows)
    if q is not p:
        text = f"configuration {config.upper()}:\n" + text
        for f in getattr(q, "variant_failed", [])[:1]:
            p.warn(f"configuration {config.upper()} does not build: step {f['step']}: {f['message']}")
    p.give_report("BOM", {"rows": [{**r, "volume": round(float(r["volume"]), 4),
                                    "mass": None if r["mass"] is None else round(float(r["mass"]), 6)}
                                   for r in rows],
                          "kinds": len(rows), "pieces": sum(r["qty"] for r in rows)})
    if file:
        path = file if os.path.splitext(file)[1] else file + ".csv"
        try:
            write_bom_csv(p, rows, path)
        except OSError as exc:
            raise CommandError(f"BOM: cannot write {path} ({exc})") from None
        text += f"\nwritten to {path}"
    return text
