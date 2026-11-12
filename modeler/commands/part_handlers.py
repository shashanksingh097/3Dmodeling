"""Parts and instances: reusable shape recipes, placed many times.

A part is a block of commands with parameters::

    *PART, bolt, D=8, L=30
      CYL, 0, 0, 0, D/2, L
      ...
    *ENDPART

It runs in a model of its own and sees only its own parameters (pass a
value from outside with ``INST, bolt, x,y,z, D=D2``). ``INST`` builds the
part with the values given and places a copy. The definition is a history
entry like any other, so editing it, or a parameter that an ``INST``
passes, re-runs everything after it and every instance follows.

Built shapes are kept by (definition text, values given), so placing the
same bolt fifty times builds it once.

The part library is a folder of ``.cmd`` files holding ``*PART`` blocks
(``MODELER_LIBRARY``, default ``~/.modeler/parts``). ``LIB, LOAD`` reads
one into the session; a saved project keeps a copy of every file it loaded.
"""

from __future__ import annotations

import math
import os

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS_Compound, TopoDS_Shape

from ..lang.expr import ExprError, Vec, format_value
from ..lang.script import PartDef, ScriptError, first_code_line, is_ident, parse
from .processor import REGISTRY, Arg, BodyRef, CommandError, Path, Processor, Raw, Text, command

_N_ARGS = 24
_building: list[str] = []  # parts being built right now (a part placing itself is an error)
MAX_NESTING = 8


def library_dir() -> str:
    return os.environ.get("MODELER_LIBRARY") or os.path.join(os.path.expanduser("~"), ".modeler", "parts")


def _signature(part: PartDef) -> str:
    return ", ".join(n if d is None else f"{n}={d}" for n, d in part.params)


def _freeze(v):
    return tuple(v) if isinstance(v, (list, tuple)) else v


def _solids(shape: TopoDS_Shape) -> list[TopoDS_Shape]:
    out = []
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        out.append(exp.Current())
        exp.Next()
    return out


def _compound(shapes: list[TopoDS_Shape]) -> TopoDS_Shape:
    if len(shapes) == 1:
        return shapes[0]
    comp = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(comp)
    for s in shapes:
        builder.Add(comp, s)
    return comp


# ---- defining and building ----------------------------------------------------

def define_part(p: Processor, st: PartDef) -> str:
    if st.name in REGISTRY:
        raise CommandError(f"*PART: {st.name} is a built-in command; pick another name")
    if st.name in p.macros:
        raise CommandError(f"*PART: {st.name} is already a macro; pick another name")
    if p._scopes:
        raise CommandError("*PART: parts are defined at the top level, not inside a macro")
    p.parts[st.name] = st
    sig = _signature(st)
    if any(d is None for _, d in st.params):
        return f"part {st.name.lower()}({sig}) defined (it is built when placed: some values have no default)"
    shape = build(p, st, {})  # a trial build with the defaults, so mistakes show here
    n = len(_solids(shape))
    return f"part {st.name.lower()}({sig}) defined: " + (f"{n} solid" + ("s" if n != 1 else "") if n else "no solids")


def build(p: Processor, part: PartDef, given: dict) -> TopoDS_Shape:
    """The part's shape for these values (cached). ``given`` maps upper-case
    parameter names to values; the others take their defaults."""
    # a value equal to a plain-number default is the default: one build for both
    plain = {}
    for n, d in part.params:
        try:
            plain[n] = float(d) if d is not None else None
        except ValueError:
            plain[n] = None
    given = {k: v for k, v in given.items()
             if not (plain.get(k) is not None and isinstance(v, (int, float)) and float(v) == plain[k])}
    key = (part.source, tuple(sorted((k, _freeze(v)) for k, v in given.items())))
    if key in p.part_cache:
        return p.part_cache[key]
    if part.name in _building:
        raise CommandError(f"part {part.name.lower()} places itself (through {' -> '.join(_building)})")
    if len(_building) >= MAX_NESTING:
        raise CommandError(f"parts nested more than {MAX_NESTING} deep")
    names = {n for n, _ in part.params}
    missing = [n.lower() for n, d in part.params if d is None and n not in given]
    if missing:
        raise CommandError(f"part {part.name.lower()} needs a value for {', '.join(missing)}")
    sub = Processor()
    sub.parts = dict(p.parts)
    sub.part_cache = p.part_cache
    sub.model.units = p.model.units
    for k, v in given.items():
        sub.params[k] = v
    # parameters left out take their defaults, in order, so a default can use an earlier one
    head = [f"{n} = {d}" for n, d in part.params if n not in given and d is not None]
    _building.append(part.name)
    try:
        results = sub.run_script("\n".join(head + [part.body_text]))
    finally:
        _building.pop()
    bad = [r for r in results if not r.ok]
    if bad:
        r = bad[0]
        msg = r.message
        if "unknown name" in msg or "no body or parameter" in msg:
            msg += f" (a part sees only its own parameters: {', '.join(sorted(names)).lower() or 'none'}; " \
                   "pass others with INST, part, x,y,z, NAME=value)"
        raise CommandError(f"part {part.name.lower()}, at '{first_code_line(r.line)}': {msg}")
    m = sub.model
    shown = [b for bid, b in sorted(m.bodies.items()) if bid not in m.hidden]
    if not shown:
        raise CommandError(f"part {part.name.lower()} makes no bodies")
    solid = [b.shape for b in shown if _solids(b.shape)]
    shape = _compound(solid or [b.shape for b in shown])
    p.part_cache[key] = shape
    return shape


# ---- reading INST arguments -----------------------------------------------------

def _split(p: Processor, raws: list[str], part: PartDef) -> tuple[list[float], dict]:
    """Numbers (points spread out) and NAME=value parameter values."""
    nums: list[float] = []
    given: dict = {}
    names = [n for n, _ in part.params]
    raws = list(raws)
    while raws and not raws[-1].strip():
        raws.pop()
    for raw in raws:
        s = raw.strip()
        name, eq, expr = s.partition("=")
        if eq and is_ident(name.strip()) and not expr.startswith("="):
            key = name.strip().upper()
            if key not in names:
                raise CommandError(f"INST: part {part.name.lower()} has no parameter {name.strip()} "
                                   f"(it has {', '.join(names) or 'none'})")
            try:
                given[key] = p.evaluate(expr.strip())
            except ExprError as exc:
                raise CommandError(f"INST: {name.strip()}: {exc}") from None
            continue
        if not s:
            nums.append(math.nan)  # left empty: its default
            continue
        try:
            v = p.evaluate(s)
        except ExprError as exc:
            raise CommandError(f"INST: {exc}") from None
        if isinstance(v, Vec):
            nums.extend(float(c) for c in v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            nums.append(float(v))
        else:
            raise CommandError(f"INST: expected a number, a point or NAME=value, got {format_value(v)}")
    return nums, given


def placement(nums: list[float]) -> gp_Trsf:
    defaults = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    if len(nums) > len(defaults):
        raise CommandError("INST: give at most x, y, z, angle, dx, dy, dz before the NAME=value parameters")
    vals = [d if i >= len(nums) or math.isnan(nums[i]) else nums[i] for i, d in enumerate(defaults)]
    x, y, z, angle, dx, dy, dz = vals
    t = gp_Trsf()
    if angle:
        if dx == dy == dz == 0:
            raise CommandError("INST: the turning axis cannot be (0, 0, 0)")
        t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(dx, dy, dz)), math.radians(angle))
    move = gp_Trsf()
    move.SetTranslation(gp_Vec(x, y, z))
    return move.Multiplied(t)


def _part(p: Processor, name: str, what: str) -> PartDef:
    part = p.parts.get(name.strip().upper())
    if part is None:
        known = ", ".join(n.lower() for n in p.parts) or "none yet (define one with *PART, or LIB, LOAD)"
        raise CommandError(f"{what}: no part named {name.strip().lower()!r}; parts: {known}")
    return part


# ---- commands ----------------------------------------------------------------------

@command(
    "INST",
    Arg("part", str, help="the part to place"),
    *[Arg(f"a{i}", Raw, "") for i in range(1, _N_ARGS + 1)],
    help="Place a copy of a part: INST, bolt, x, y, z [, angle [, dx, dy, dz]] [, D=10, L=40 ...]. The part is "
         "turned by angle (degrees) about the axis (dx,dy,dz) (default Z), then moved to (x,y,z), on the work plane "
         "if one is set. NAME=value sets the part's parameters for this copy; the rest keep their defaults. "
         "Editing the *PART block, or a parameter used here, updates every copy.",
)
def inst(p: Processor, part, **raws):
    pd = _part(p, part, "INST")
    nums, given = _split(p, [raws[f"a{i}"] for i in range(1, _N_ARGS + 1)], pd)
    shape = build(p, pd, given)
    mk = BRepBuilderAPI_Transform(shape, placement(nums), True)
    from .feature_handlers import place

    placed = place(p, mk.Shape())
    m = p.model
    body = m.add_body(placed)
    m.instances[body.id] = (pd.name, tuple(sorted(given.items())))
    from .handlers import _added

    vals = ", ".join(f"{k}={format_value(v)}" for k, v in sorted(given.items()))
    return _added(p, body, f"INST {pd.name.lower()}" + (f" ({vals})" if vals else ""))


@command(
    "EXPLODE",
    Arg("b", BodyRef, help="a body (an instance, or any body made of several solids)"),
    help="Split a body into one body per solid: EXPLODE, b. An instance becomes plain geometry that no longer "
         "follows its part.",
)
def explode(p: Processor, b):
    m = p.model
    bid = b
    body = m.body(bid)
    solids = _solids(body.shape)
    was = m.instances.get(bid)
    if len(solids) <= 1:
        if not was:
            raise CommandError(f"EXPLODE: body {bid} is one solid already and not an instance")
        m.instances.pop(bid, None)
        return f"body {bid} is now plain geometry (no longer an instance of {was[0].lower()})"
    named = not body.name.lower().startswith("body")
    m.remove_body(bid)
    new = []
    for i, s in enumerate(solids, 1):
        nb = m.add_body(s, f"{body.name}_{i}" if named else "")
        new.append(str(nb.id))
    return f"body {bid} split into {len(solids)} bodies: {', '.join(new)}"


def resolve_library(p: Processor, name: str) -> str:
    """The file a LIB, LOAD name means: one inside an opened project, a path,
    or <name>.cmd in the part library folder."""
    if name in p.file_map:
        return p.file_map[name]
    if os.path.isfile(name):
        return name
    cand = os.path.join(library_dir(), name if name.lower().endswith(".cmd") else name + ".cmd")
    if os.path.isfile(cand):
        return cand
    raise CommandError(f"LIB: no part file {name!r} (looked for it as a path and in {library_dir()})")


@command(
    "LIB",
    Arg("action", str, help="LOAD"),
    Arg("file", Path, help="a part name in the library folder, or a .cmd file"),
    help="Load parts from the part library: LIB, LOAD, bolt reads bolt.cmd from the library folder "
         "(MODELER_LIBRARY, default ~/.modeler/parts), or LIB, LOAD, \"path/parts.cmd\". The file holds *PART "
         "blocks. A saved project keeps a copy of every file it loaded. Save a part there with LIBSAVE.",
)
def lib(p: Processor, action, file):
    if action != "LOAD":
        raise CommandError("LIB: use LIB, LOAD, name (save with LIBSAVE, list with LIST, PARTS)")
    path = resolve_library(p, file)
    p.lib_files[file] = path
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        stmts = parse(text)
    except ScriptError as exc:
        raise CommandError(f"LIB: {path}: {exc}") from None
    parts = [st for st in stmts if isinstance(st, PartDef)]
    if len(parts) != len(stmts) or not parts:
        raise CommandError(f"LIB: {path} must hold only *PART blocks (and comments)")
    msgs = [define_part(p, st) for st in parts]
    return f"loaded {len(parts)} part{'s' if len(parts) != 1 else ''} from {path}\n  " + "\n  ".join(msgs)


@command(
    "LIBSAVE",
    Arg("part", Text, help="the part to save"),
    Arg("file", Path, "", "where (default: <part>.cmd in the library folder)"),
    logged=False,
    help="Save a part's definition to the part library, for other projects: LIBSAVE, bolt. Runs when given; "
         "not kept in the history.",
)
def libsave(p: Processor, part, file):
    pd = _part(p, part, "LIBSAVE")
    path = file or os.path.join(library_dir(), pd.name.lower() + ".cmd")
    if not path.lower().endswith(".cmd"):
        path += ".cmd"
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(pd.source.rstrip() + "\n")
    return f"saved part {pd.name.lower()} to {path}"


def parts_listing(p: Processor) -> list[str]:
    m = p.model
    lines = []
    for name, pd in p.parts.items():
        count = sum(1 for bid, (pn, _) in m.instances.items() if pn == name and bid in m.bodies)
        lines.append(f"  {name.lower()}({_signature(pd)}): {count} instance{'s' if count != 1 else ''}")
    return lines


def instance_of(p: Processor, bid: int) -> str:
    """'bolt (D=10)' for an instance body, or ''."""
    got = p.model.instances.get(bid)
    if not got:
        return ""
    name, vals = got
    extra = ", ".join(f"{k}={format_value(v)}" for k, v in vals)
    return name.lower() + (f" ({extra})" if extra else "")

