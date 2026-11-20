"""Design tables and variants: configurations from a CSV file (DESIGNTABLE), steps turned off in a
configuration (CONFIGOFF), every configuration built and compared (VARIANTS), and the parts list
of one configuration (BOM, file, config).

A design table is a CSV file, one row per configuration::

    config, W,  H,  off
    small,  30, 10,
    big,    60, 20, 5 7

The first column names the configuration; the others are parameter values; an optional ``off``
column lists the steps (history numbers, space- or semicolon-separated) that this configuration
leaves out (a hole the small size does not have). ``DESIGNTABLE, "sizes.csv"`` writes one
``CONFIG`` step per row (or changes the one already there), so the values are kept in the history;
the steps turned off are kept with the project, by step, so they stay right when steps are added
before them. ``DESIGNTABLE, "sizes.csv", EXPORT`` writes the configurations back out.

``VARIANTS`` builds every configuration on its own (the model in use is not touched) and lists
for each one whether it builds, the steps that fail, the solids, volume, mass and size, and how far
each is from the history's own values. ``VARIANTS, , folder`` also writes each one's parts list
(CSV) and drawing (SVG) there.
"""

from __future__ import annotations

import copy
import csv
import os

from ..lang.expr import format_value
from .config_handlers import bom_rows, describe_config
from .processor import Arg, CommandError, Path, Processor, command

# ---- one configuration on its own ------------------------------------------------------------------

def variant(p: Processor, name: str) -> Processor:
    """A separate processor holding the model built with configuration ``name`` ("" or DEFAULT: the
    history's own values). The model in use is not touched."""
    key = name.upper()
    if key in ("", "DEFAULT", "NONE"):
        key = ""
    elif key not in p.configs:
        raise CommandError(f"no configuration {name} (USECONFIG lists them)")
    q = Processor()
    q.project_dir, q.file_map, q.link_paths = p.project_dir, dict(p.file_map), dict(p.link_paths)
    q.strokes, q.taken = dict(p.strokes), copy.deepcopy(p.taken)
    q.config_off = {k: set(v) for k, v in p.config_off.items()}
    q.config, q.config_values = key, dict(p.configs.get(key, {}))
    q.model.units = p.model.units
    seeds = [{"text": e.text, "uid": e.uid, "pins": e.pins, "refs": e.refs}
             for e in p.history[: p.cursor] if not e.suppressed]
    results = q.run_script(p.script(), seeds)
    # a step that fails is not added to the history: keep where the build stopped
    q.variant_failed = [{"step": i + 1, "text": r.line, "message": r.message}
                        for i, r in enumerate(results) if not r.ok]
    return q


def _numbers(text: str) -> list[int]:
    out = []
    for bit in text.replace(";", " ").replace(",", " ").split():
        try:
            out.append(int(bit))
        except ValueError:
            raise CommandError(f"{bit!r} is not a step number") from None
    return out


def _uids(p: Processor, steps: list[int], what: str) -> set[int]:
    out = set()
    for n in steps:
        if not 1 <= n <= p.cursor:
            raise CommandError(f"{what}: there is no step {n} (steps go from 1 to {p.cursor})")
        e = p.history[n - 1]
        if not e.uid:
            p._uid += 1
            e.uid = p._uid
        out.add(e.uid)
    return out


def off_steps(p: Processor, name: str) -> list[int]:
    """The step numbers turned off in a configuration, as the history stands now."""
    uids = p.config_off.get(name.upper(), set())
    return [i + 1 for i, e in enumerate(p.history[: p.cursor]) if e.uid and e.uid in uids]


def _off_text(p: Processor, key: str) -> str:
    off = off_steps(p, key)
    if not off:
        return f"{key}: every step is on"
    return f"{key}: step{'s' if len(off) > 1 else ''} {', '.join(map(str, off))} " + ("are" if len(off) > 1 else "is") + " off"


def _rebuild_if_used(p: Processor, key: str) -> str:
    if key and key == p.config and p.history:
        return "\n" + p.rebuild(0, skip=False)
    return ""


@command(
    "CONFIGOFF",
    Arg("config", str, help="the configuration"),
    Arg("steps", str, "", 'step numbers, e.g. "5 7" (none: list the ones turned off)'),
    Arg("state", str, "OFF", "OFF (default) or ON to turn them back on"),
    session=True,
    help='Leave steps out of one configuration: CONFIGOFF, small, "5 7" (a hole the small size does not have). '
         'CONFIGOFF, small, "5", ON puts one back; CONFIGOFF, small lists them. Kept with the project, by step, '
         "so the right steps stay off when others are added; the model rebuilds when the configuration is in use.",
)
def configoff(p: Processor, config, steps, state):
    key = config.upper()
    if key not in p.configs:
        raise CommandError(f"CONFIGOFF: no configuration {config} (make it with CONFIG first)")
    if not steps.strip():
        return _off_text(p, key)
    if state not in ("OFF", "ON"):
        raise CommandError("CONFIGOFF: the state is OFF or ON")
    try:
        nums = _numbers(steps)
    except CommandError as exc:
        raise CommandError(f"CONFIGOFF: {exc}") from None
    uids = _uids(p, nums, "CONFIGOFF")
    have = p.config_off.setdefault(key, set())
    if state == "OFF":
        have |= uids
    else:
        have -= uids
    return _off_text(p, key) + _rebuild_if_used(p, key)


# ---- design tables ---------------------------------------------------------------------------------

def read_table(path: str) -> list[tuple[str, dict[str, str], list[int]]]:
    """(configuration, {PARAM: value text}, steps off) per row of a CSV design table."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = [r for r in csv.reader(fh) if any(c.strip() for c in r)]
    except OSError as exc:
        raise CommandError(f"DESIGNTABLE: cannot read {path} ({exc.strerror or exc})") from None
    if len(rows) < 2:
        raise CommandError("DESIGNTABLE: the table needs a header row and at least one configuration")
    head = [h.strip() for h in rows[0]]
    cols = [h.upper() for h in head[1:]]
    for h in cols:
        if h != "OFF" and (not h or not h.replace("_", "").isalnum() or h[0].isdigit()):
            raise CommandError(f"DESIGNTABLE: column {h!r} is not a parameter name")
    out, seen = [], set()
    for line, row in enumerate(rows[1:], 2):
        name = row[0].strip().upper() if row else ""
        if not name or not name.replace("_", "").isalnum() or name[0].isdigit():
            raise CommandError(f"DESIGNTABLE: row {line}: {row[0] if row else ''!r} is not a configuration name")
        if name in seen:
            raise CommandError(f"DESIGNTABLE: row {line}: configuration {name} comes twice")
        seen.add(name)
        vals, off = {}, []
        for h, cell in zip(cols, row[1:]):
            cell = cell.strip()
            if not cell:
                continue
            if h == "OFF":
                try:
                    off = _numbers(cell)
                except CommandError as exc:
                    raise CommandError(f"DESIGNTABLE: row {line}: {exc}") from None
            else:
                vals[h] = cell
        if not vals:
            raise CommandError(f"DESIGNTABLE: row {line}: configuration {name} has no values")
        out.append((name, vals, off))
    return out


def _config_rows(p: Processor) -> dict[str, int]:
    """CONFIG steps in the history: configuration name -> step index (0-based)."""
    out = {}
    for i, e in enumerate(p.history[: p.cursor]):
        words = [w.strip() for w in e.text.split(",", 2)]
        if len(words) >= 2 and words[0].upper() == "CONFIG" and not e.suppressed:
            out[words[1].upper()] = i
    return out


def write_table(p: Processor, path: str) -> int:
    names = list(p.configs)
    params: list[str] = []
    for n in names:
        for k in p.configs[n]:
            if k not in params:
                params.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["config", *params, "off"])
        for n in names:
            vals = p.configs[n]
            w.writerow([n.lower(), *[format_value(vals[k]) if k in vals else "" for k in params],
                        " ".join(map(str, off_steps(p, n)))])
    return len(names)


@command(
    "DESIGNTABLE",
    Arg("file", Path, help="the CSV design table"),
    Arg("action", str, "READ", "READ (default: make the configurations) or EXPORT (write them to the file)"),
    session=True,
    help='Configurations from a CSV design table: DESIGNTABLE, "sizes.csv". One row per configuration: its '
         "name, then parameter values by column (W, H ...), and an optional off column with steps to leave out. "
         "Each row becomes a CONFIG step (or changes the one there). DESIGNTABLE, file, EXPORT writes the "
         "configurations out as such a table.",
)
def designtable(p: Processor, file, action):
    if action == "EXPORT":
        n = write_table(p, file)
        return f"wrote {n} configuration{'s' if n != 1 else ''} to {file}"
    if action != "READ":
        raise CommandError("DESIGNTABLE: the action is READ or EXPORT")
    table = read_table(file)
    for _name, _vals, off in table:
        for n in off:
            if not 1 <= n <= p.cursor:
                raise CommandError(f"DESIGNTABLE: configuration {_name}: there is no step {n} "
                                   f"(steps go from 1 to {p.cursor})")
    # the steps to turn off are fixed now, before CONFIG steps are added
    offs = {name: _uids(p, off, "DESIGNTABLE") for name, _vals, off in table}
    made, changed = [], []
    rows = _config_rows(p)
    for name, vals, _off in table:
        text = f'CONFIG, {name.lower()}, "{", ".join(f"{k} = {v}" for k, v in vals.items())}"'
        if name in rows:
            if p.history[rows[name]].text.strip() != text:
                p.edit_entry(rows[name] + 1, text)
                changed.append(name)
        else:
            r = p.run(text)
            if not r.ok:
                raise CommandError(f"DESIGNTABLE: configuration {name}: {r.message}")
            made.append(name)
            rows = _config_rows(p)
    for name, uids in offs.items():
        if uids:
            p.config_off[name] = uids
        else:
            p.config_off.pop(name, None)
    lines = [f"design table {os.path.basename(file)}: {len(table)} configuration{'s' if len(table) != 1 else ''}"
             + (f" ({len(made)} new, {len(changed)} changed)" if made or changed else " (unchanged)")]
    for name, _vals, _off in table:
        off = off_steps(p, name)
        lines.append(f"  {name}: {describe_config(p.configs.get(name, {}))}"
                     + (f"; steps off: {', '.join(map(str, off))}" if off else ""))
    if p.config in offs and p.history:
        lines.append(p.rebuild(0, skip=False))
    return "\n".join(lines)


# ---- every configuration, compared -----------------------------------------------------------------

def _box(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, True)
    lo, hi = box.CornerMin(), box.CornerMax()
    return (lo.X(), lo.Y(), lo.Z()), (hi.X(), hi.Y(), hi.Z())


def _summary(q: Processor) -> dict:
    from ..geometry import robust

    rows = bom_rows(q)
    vol = sum(float(r["volume"]) * r["qty"] for r in rows)
    masses = [r["mass"] * r["qty"] for r in rows if r["mass"] is not None]
    lo, hi = None, None
    m = q.model
    for bid, b in m.bodies.items():
        if not m.is_shown(bid) or not robust.solids(b.shape):
            continue
        a, z = _box(b.shape)
        lo = list(a) if lo is None else [min(x, y) for x, y in zip(lo, a)]
        hi = list(z) if hi is None else [max(x, y) for x, y in zip(hi, z)]
    failed = list(getattr(q, "variant_failed", [])) or [
        {"step": i + 1, "text": e.label, "message": e.message} for i, e in enumerate(q.history[: q.cursor]) if not e.ok]
    return {"ok": not failed, "failed": failed, "pieces": sum(r["qty"] for r in rows), "kinds": len(rows),
            "volume": round(vol, 6), "mass": round(sum(masses), 6) if masses else None,
            "size": [round(b - a, 6) for a, b in zip(lo, hi)] if lo is not None else None}


def variants(p: Processor, folder: str = "") -> list[dict]:
    from .config_handlers import write_bom_csv

    out = []
    for name in ["", *p.configs]:
        q = variant(p, name)
        row = {"config": name or "DEFAULT", "values": {k: v for k, v in p.configs.get(name, {}).items()},
               "off": off_steps(p, name) if name else []}
        row.update(_summary(q))
        if folder:
            os.makedirs(folder, exist_ok=True)
            stem = os.path.join(folder, (name or "default").lower())
            write_bom_csv(q, bom_rows(q), stem + "_bom.csv")
            r = q.run(f'DRAWING, "{stem}.svg"')
            row["files"] = [stem + "_bom.csv"] + ([stem + ".svg"] if r.ok else [])
        out.append(row)
    base = out[0]["volume"] if out else 0
    for row in out:
        row["volume_change"] = round((row["volume"] - base) / base, 6) if base else None
    return out


def variants_text(p: Processor, rows: list[dict]) -> str:
    from .config_handlers import _num

    u = p.model.units.lower()
    lines = []
    for r in rows:
        state = "builds" if r["ok"] else f"FAILS at step {r['failed'][0]['step']}: {r['failed'][0]['message']}"
        vals = describe_config(r["values"]) if r["values"] else "the history's own values"
        bits = [f"{r['config']}: {state}", f"  values: {vals}" + (f"; steps off: {', '.join(map(str, r['off']))}"
                                                                    if r["off"] else "")]
        size = " x ".join(_num(x) for x in r["size"]) + f" {u}" if r["size"] else "no solids"
        meas = f"  {r['pieces']} piece{'s' if r['pieces'] != 1 else ''}, {_num(r['volume'])} {u}3, {size}"
        if r["mass"] is not None:
            meas += f", {_num(r['mass'])} kg"
        if r["volume_change"] is not None and r["config"] != "DEFAULT":
            meas += f" (volume {r['volume_change'] * 100:+.1f}% from DEFAULT)"
        bits.append(meas)
        if r.get("files"):
            bits.append("  wrote " + ", ".join(os.path.basename(f) for f in r["files"]))
        lines += bits
    bad = sum(1 for r in rows if not r["ok"])
    lines.append(f"{len(rows)} variant{'s' if len(rows) != 1 else ''}"
                 + (f", {bad} fail{'s' if bad == 1 else ''} to build" if bad else ", all build"))
    return "\n".join(lines)


@command(
    "VARIANTS",
    Arg("fmt", str, "TEXT", "TEXT or JSON"),
    Arg("folder", Path, "", "a folder to write each configuration's parts list (CSV) and drawing (SVG) to"),
    logged=False,
    help="Build every configuration on its own and compare them: whether each builds (and the step that fails), "
         "pieces, volume, mass, overall size and the change from the history's own values. VARIANTS, TEXT, folder "
         "also writes each one's parts list and drawing. The model in use is not changed.",
)
def variants_cmd(p: Processor, fmt, folder):
    if not p.configs:
        raise CommandError('VARIANTS: there are no configurations (CONFIG, name, "W = 60" or DESIGNTABLE makes them)')
    rows = variants(p, folder)
    p.give_report("variants", {"variants": rows})
    if fmt == "JSON":
        import json

        return json.dumps({"variants": rows})
    return variants_text(p, rows)
