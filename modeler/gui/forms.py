"""Fill-in forms for commands: what a form shows, and the command text it sends.

A form never changes the model. It only builds the same command text a
person could type, and the window runs that text through
``MainWindow.execute``. Everything here is plain Python over the processor
(no Qt), so it is tested headless; ``gui/form_dialog.py`` draws it.

Most forms come straight from the command registry: each argument becomes a
field, with three numbers in a row (``x, y, z``, ``dx, dy, dz`` ...) shown as
one point field, bodies as a list to choose from, and keywords as a choice.
Commands whose arguments change with a keyword (``PLANE, name, FACE, id`` or
``PLANE, name, PN, x,y,z, nx,ny,nz``) have a short hand-written description
with one *variant* per keyword.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..commands import REGISTRY, Processor
from ..commands.processor import BodyRef, CommandError, Path, Raw, Text
from ..lang.expr import ExprError, fmt_num
from ..lang.script import ScriptError, first_code_line, is_ident, split_args, strip_comment
from . import assist

# ---- what a form is ------------------------------------------------------------

# Field kinds and what they write:
#   num     one expression (a number, a parameter, W/2 ...)
#   expr    one expression or law in t, written as typed
#   word    one word (a name) written as typed
#   text    free text, written as typed (quoted only when it needs it)
#   path    a file name, always quoted
#   choice  one keyword from a list
#   body    a body: name, ID, LAST or SEL
#   bodies  several bodies, one argument each
#   ids     several entity IDs (faces, edges ...), one argument each
#   point   three numbers (x, y, z), one argument each
#   points  a list of points, each written as (x, y, z)
#   flag    a check box that adds a word (FUSE, RULED, CLOSE ...)
#   bool    a check box that writes 1 or 0
#   datum   a datum plane or axis (or XY, YZ, ZX, X, Y, Z ...)
#   sketch  a sketch name
#   layer   a layer name (the list offers the layers there are)


@dataclass
class Field:
    key: str
    label: str
    kind: str = "num"
    default: str = ""  # the value the command uses when the argument is left out
    required: bool = False
    choices: tuple[str, ...] = ()
    help: str = ""
    word: str = ""  # flag: the word it adds
    pick: str = ""  # what "use selection" reads: BODY, FACE, EDGE, VERTEX, or "" (any)
    count: int = 1  # bodies / ids: how many arguments it may take at most (0: no limit)
    start: str = ""  # value the form opens with when nothing is picked

    def defaults(self) -> list[str]:
        """Per-argument defaults (a point has three)."""
        if self.kind == "point":
            parts = [s.strip() for s in self.default.split(",")] if self.default else ["", "", ""]
            return (parts + ["", "", ""])[:3]
        return [self.default]


@dataclass
class Variant:
    key: str  # the keyword the variant writes, or "" for the only one
    label: str
    fields: list[Field]
    head: tuple[str, ...] = ()  # fields written before the keyword (PLANE's name)
    help: str = ""


@dataclass
class FormSpec:
    command: str
    title: str
    help: str
    category: str
    variants: list[Variant]
    word_slot: int = -1  # where the variant keyword goes among the arguments (-1: none)

    def variant(self, key: str = "") -> Variant:
        for v in self.variants:
            if v.key.upper() == key.upper():
                return v
        return self.variants[0]


class FormError(Exception):
    pass


# ---- the menu: which commands, under which heading -------------------------------

# "=" is not a command: its form writes a parameter assignment, NAME = value.
PARAM = "="

CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("Parameters", (PARAM,)),
    ("Solids", ("BLOCK", "CYL", "TUBE", "SPHERE", "CONE", "TORUS", "WEDGE", "SPRING")),
    ("Sketch", ("SKETCH", "EXTRUDE", "REVOLVE")),
    ("Curves", ("LINE", "ARC", "POLYLINE", "SPLINE", "HELIX", "CURVE")),
    ("Profiles", ("CIRCLE", "ELLIPSE", "RECT", "POLYGON", "STAR", "SLOT", "AIRFOIL")),
    ("Shapes from curves", ("LOFT", "SPINELOFT", "SWEEP", "RAILSWEEP", "MORPH", "PIPE")),
    ("Text and surfaces", ("TEXT", "SURFACE")),
    ("Combine", ("UNION", "SUBTRACT", "INTERSECT", "KEEP")),
    ("Features", ("FILLET", "CHAMFER", "HOLE", "THREAD", "SHELL", "DRAFT", "OFFSET", "SPLIT")),
    ("Edit faces", ("PUSHPULL", "DELFACE")),
    ("Move and copy", ("MOVE", "ROTATE", "COPY", "MIRROR", "ARRAY", "PATTERN")),
    ("Bodies", ("NAME", "DELETE", "HIDE", "SHOW", "CHECK", "HEAL", "CLEAN", "CLEAR")),
    ("Layers, colours, materials", ("LAYER", "COLOR", "MATERIAL", "ISOLATE")),
    ("Datums", ("PLANE", "AXIS", "POINT", "DATUM", "WORKPLANE")),
    ("Select", ("SEL", "CM", "CMSEL", "CMDEL")),
    ("Measure", ("DIST", "ANGLE", "MASSPROP", "CLASH", "SECTION", "ECHO", "LIST")),
    ("Check", ("DESCRIBE", "ASSERT", "SELFOR", "DIFF", "LINT")),
    ("Parts", ("INST", "EXPLODE", "LIB", "LIBSAVE")),
    ("Settings and files", ("/UNITS", "/TOL", "IMPORT", "EXPORT")),
]

# Commands with no form, and why: the GUI already does them another way.
NO_FORM = {
    # history and session: toolbar buttons, the History panel, file dialogs
    "UNDO", "REDO", "HIST", "OPEN", "SAVE", "NEW", "RUN",
    # what clicks and view buttons send
    "PICK", "PICKMODE", "VIEW", "FIT", "HELP",
    # drawn by mouse in sketch mode (Sketch toolbar)
    "ENDSKETCH", "SPOINT", "SLINE", "SPOLY", "SRECT", "SCIRCLE", "SARC", "SARC3", "SSLOT",
    "SCON", "SDIM", "SDEL", "SMOVE", "SCONSTRUCT", "SSEL",
    # sketch editing: the Trim / Extend / Fillet tools and the Offset, Mirror, Pattern, Project buttons
    "STRIM", "SEXTEND", "SFILLET", "SOFFSET", "SMIRROR", "SPATTERN", "SPROJECT",
}

# What a form opens with, so pressing OK on a fresh form already makes something.
STARTS: dict[str, dict[str, str]] = {
    "BLOCK": {"x": "0, 0, 0", "dx": "20, 10, 5"},
    "CYL": {"x": "0, 0, 0", "r": "5", "h": "12"},
    "TUBE": {"x": "0, 0, 0", "ro": "6", "ri": "4", "h": "20"},
    "SPHERE": {"x": "0, 0, 0", "r": "6"},
    "CONE": {"x": "0, 0, 0", "r1": "6", "r2": "2", "h": "10"},
    "TORUS": {"x": "0, 0, 0", "r1": "10", "r2": "2"},
    "WEDGE": {"x": "0, 0, 0", "dx": "20, 10, 10", "ltx": "5"},
    "SPRING": {"x": "0, 0, 0", "r": "10", "pitch": "5", "turns": "8", "d": "1.5"},
    "LINE": {"x1": "0, 0, 0", "x2": "0, 0, 40"},
    "ARC": {"x1": "0, 0, 0", "x2": "20, 0, 10", "x3": "40, 0, 0"},
    "HELIX": {"x": "0, 0, 0", "r": "10", "pitch": "4", "turns": "5"},
    "CIRCLE": {"x": "0, 0, 0", "r": "5"},
    "ELLIPSE": {"x": "0, 0, 0", "a": "8", "b": "4"},
    "RECT": {"x": "0, 0, 0", "w": "20", "h": "10"},
    "POLYGON": {"x": "0, 0, 0", "r": "10", "sides": "6"},
    "STAR": {"x": "0, 0, 0", "ro": "10", "ri": "4", "points": "5"},
    "SLOT": {"x": "0, 0, 0", "length": "30", "width": "8"},
    "AIRFOIL": {"x": "0, 0, 0", "chord": "40"},
    "FILLET": {"r": "1"},
    "CHAMFER": {"d": "1"},
    "HOLE": {"d": "6"},
    "SHELL": {"t": "2"},
    "TEXT": {"text": "TEXT", "x": "0, 0, 0", "size": "10", "depth": "2"},
    "SURFACE": {"kind": "PARAM", "fx": "u", "fy": "v", "fz": "3*sin(6*u)*cos(6*v)", "u1": "60", "v1": "40"},
    "PUSHPULL": {"d": "2"},
    "DRAFT": {"angle": "3"},
    "OFFSET": {"d": "1"},
    "PIPE": {"r": "2"},
    "ROTATE": {"angle": "90"},
    "EXTRUDE": {"d": "10"},
    "KEEP": {"mode": "ON"},
    "/UNITS": {"unit": "MM"},
    "/TOL": {"tol": "0.001"},
}

# argument triples shown as one point field: first name -> (label, the three names)
_TRIPLES = {
    "x": ("Point", ("x", "y", "z")),
    "x1": ("Point 1", ("x1", "y1", "z1")),
    "x2": ("Point 2", ("x2", "y2", "z2")),
    "x3": ("Point 3", ("x3", "y3", "z3")),
    "dx": ("Direction", ("dx", "dy", "dz")),
    "nx": ("Normal", ("nx", "ny", "nz")),
}
_SIZES = {"BLOCK", "WEDGE"}  # their dx, dy, dz are sizes, not a direction
_LABELS = {
    "r": "Radius", "h": "Height", "d": "Diameter", "t": "Thickness", "angle": "Angle (degrees)",
    "ro": "Outer radius", "ri": "Inner radius", "r1": "Radius 1", "r2": "Radius 2", "ltx": "Top length",
    "b": "Body", "a": "Body", "name": "Name", "tol": "Tolerance", "pitch": "Pitch", "turns": "Turns",
    "taper": "Taper (degrees)", "hand": "Hand", "plaw": "Pitch law", "w": "Width", "sides": "Sides",
    "corner": "Corner radius", "points": "Points", "length": "Length", "width": "Width", "chord": "Chord",
    "code": "NACA code", "pivot": "Pivot (fraction of chord)", "profile": "Profile", "path": "Path",
    "twist": "Twist law (degrees)", "scale": "Scale law", "mode": "Mode", "sx": "Side scale law",
    "sy": "Up scale law", "ox": "Side offset law", "oy": "Up offset law", "n": "Sections",
    "solid": "Solid", "rlaw": "Radius law", "density": "Density", "unit": "Unit", "format": "Format",
    "file": "File", "copy": "Make a copy", "depth": "Depth (0 = through)", "kind": "Kind", "d2": "Diameter 2",
    "h2": "Depth or angle 2", "tip": "Drill point angle", "keep": "Keep", "by": "Split by", "side": "Side",
    "corners": "Corners", "sketch": "Sketch", "axis": "Axis", "back": "Back distance", "neutral": "Neutral plane",
    "expr": "Expression", "what": "What", "plane": "Plane", "fx": "x(t)", "fy": "y(t)", "fz": "z(t)",
    "t0": "t from", "t1": "t to", "closed": "Closed turns at each end", "finish": "Ends",
    "rail1": "Rail 1", "rail2": "Rail 2", "thick": "Thickness law", "fit": "Fit",
    "text": "Text", "size": "Font size", "align": "Align", "font": "Font", "style": "Style",
    "u0": "u from", "u1": "u to", "v0": "v from", "v1": "v to", "nu": "Grid points along u",
    "nv": "Grid points along v", "spine": "Spine",
}
# labels that differ for one command
_COMMAND_LABELS = {
    ("LAYER", "name"): "Layer",
    ("LAYER", "action"): "Do",
    ("LAYER", "value"): "Colour, bodies or new name",
    ("LAYER", "g"): "Green (if r, g, b)",
    ("LAYER", "b"): "Blue (if r, g, b)",
    ("COLOR", "target"): "Bodies",
    ("COLOR", "color"): "Colour (name, #rrggbb or red 0..255)",
    ("COLOR", "g"): "Green (if r, g, b)",
    ("COLOR", "b"): "Blue (if r, g, b)",
    ("MATERIAL", "target"): "Bodies",
    ("MATERIAL", "name"): "Material",
    ("MATERIAL", "density"): "Density kg/m3 (new material only)",
    ("MATERIAL", "color"): "Colour (new material only)",
    ("ISOLATE", "target"): "Bodies or layer",
    ("SPRING", "r"): "Coil radius",
    ("SPRING", "d"): "Wire diameter",
    ("RAILSWEEP", "path"): "Path, empty = along rail 1",
    ("THREAD", "pitch"): "Pitch, 0 = ISO coarse",
    ("THREAD", "length"): "Length, 0 = the whole face",
    ("TEXT", "depth"): "Depth, 0 = flat letters",
    ("SURFACE", "fx"): "x(u,v)",
    ("SURFACE", "fy"): "y(u,v)",
    ("SURFACE", "fz"): "z(u,v)",
    ("SURFACE", "thick"): "Wall thickness, 0 = surface only",
    ("PUSHPULL", "d"): "Distance (+ adds, - removes)",
}

_EXTRA_CHOICES = {
    ("EXTRUDE", "mode"): ("NEW", "ADD", "CUT"),
    ("REVOLVE", "mode"): ("NEW", "ADD", "CUT"),
    ("LIST", "what"): ("ALL", "BODIES", "PARAMS", "MACROS", "PARTS", "SETS", "DATUMS", "SKETCHES", "LAYERS", "MATERIALS"),
    ("MATERIAL", "name"): ("STEEL", "STAINLESS", "CASTIRON", "ALUMINIUM", "TITANIUM", "COPPER", "BRASS", "ABS",
                           "NYLON", "PLA", "RUBBER", "WOOD", "GLASS", "NONE"),
    ("COLOR", "color"): ("RED", "ORANGE", "YELLOW", "GREEN", "TEAL", "CYAN", "BLUE", "NAVY", "PURPLE", "MAGENTA",
                         "PINK", "BROWN", "WHITE", "GREY", "BLACK", "DEFAULT"),
}

# arguments whose plain type would mislead the form
_KINDS = {
    ("LIBSAVE", "part"): "part",
    ("MIRROR", "copy"): "bool",
    ("SWEEP", "solid"): "bool",
    ("RAILSWEEP", "solid"): "bool",
    ("SPLIT", "by"): "datum",
    ("WORKPLANE", "plane"): "datum",
    ("SECTION", "plane"): "datum",
    ("DRAFT", "neutral"): "datum",
    ("REVOLVE", "axis"): "datum",
    ("EXTRUDE", "sketch"): "sketch",
    ("REVOLVE", "sketch"): "sketch",
    ("SHOW", "b"): "body",
    ("COLOR", "target"): "body",
    ("MATERIAL", "target"): "body",
    ("ISOLATE", "target"): "body",
    ("LAYER", "name"): "layer",
    ("NAME", "name"): "word",
    ("CM", "name"): "word",
    ("CMSEL", "name"): "word",
    ("CMDEL", "name"): "word",
    ("DATUM", "name"): "datum",
}


def _label(name: str, cmd: str = "") -> str:
    return _COMMAND_LABELS.get((cmd, name)) or _LABELS.get(name, name)


def _choices(cmd: str, arg) -> tuple[str, ...]:
    got = _EXTRA_CHOICES.get((cmd, arg.name)) or assist._COMMAND_CHOICES.get((cmd, arg.name))
    if got:
        return tuple(got)
    if arg.type is str:
        return tuple(assist._CHOICES.get(arg.name, ()))
    return ()


def _default_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return fmt_num(v)
    return str(v)


def _generic(name: str) -> list[Field]:
    """Fields straight from a command's registered arguments."""
    cmd = REGISTRY[name]
    args = cmd.args
    out: list[Field] = []
    i = 0
    while i < len(args):
        a = args[i]
        trip = _TRIPLES.get(a.name)
        if trip and i + 2 < len(args) and tuple(x.name for x in args[i:i + 3]) == trip[1]:
            label = "Sizes" if (name in _SIZES and a.name == "dx") else trip[0]
            d = [_default_text(x.default) for x in args[i:i + 3]]
            out.append(Field(a.name, label, "point", ", ".join(d) if any(d) else "",
                             required=a.default is None, help=a.help))
            i += 3
            continue
        if a.type is BodyRef:
            # a run of optional body arguments after the first (t2..t8, s1..s8) is one list
            rest = [x for x in args[i + 1:] if x.type is BodyRef and x.default == 0]
            stem = a.name.rstrip("0123456789")
            if a.default == 0 and stem and a.name[len(stem):] and len(rest) == len(args) - i - 1:
                out.append(Field(a.name, "Profiles" if stem == "s" else "Bodies", "bodies",
                                 count=1 + len(rest), pick="BODY", help=a.help))
                break
            if rest and a.default is None and all(x.name.startswith("t") for x in rest):
                # UNION/SUBTRACT/INTERSECT: a, b, then more tools
                out.append(Field(a.name, "Body" if name != "SUBTRACT" else "Cut from", "body",
                                 required=True, pick="BODY", help=a.help))
                b = args[i + 1]
                out.append(Field(b.name, "Tools" if name == "SUBTRACT" else "With", "bodies", required=True,
                                 count=1 + len(rest), pick="BODY", help=b.help))
                break
        kind = _KINDS.get((name, a.name))
        choices = _choices(name, a)
        if kind is None:
            if a.type is BodyRef:
                kind = "body"
            elif choices:
                kind = "choice"
            elif a.type is Path:
                kind = "path"
            elif a.type is Text:
                kind = "text"
            elif a.type is Raw:
                kind = "expr"
            elif a.type is str:
                kind = "word"
            else:
                kind = "num"
        out.append(Field(a.name, _label(a.name, name), kind, _default_text(a.default), required=a.default is None,
                         choices=choices, help=a.help, pick="BODY" if kind == "body" else ""))
        i += 1
    return out


# ---- hand-written forms ----------------------------------------------------------

def _F(key, label, kind="num", default="", required=False, **kw) -> Field:
    return Field(key, label, kind, default, required, **kw)


_NAME = _F("name", "Name", "word", required=True)


def _datum_variants(cmd: str) -> list[Variant]:
    face = _F("id", "Face ID", "ids", required=True, pick="FACE")
    edge = _F("id", "Edge ID", "ids", required=True, pick="EDGE")
    if cmd == "PLANE":
        return [
            Variant("XY", "Parallel to XY", [_F("offset", "Offset")]),
            Variant("YZ", "Parallel to YZ", [_F("offset", "Offset")]),
            Variant("ZX", "Parallel to ZX", [_F("offset", "Offset")]),
            Variant("FACE", "On a flat face", [face, _F("offset", "Offset")]),
            Variant("OFFSET", "Offset from a plane", [_F("plane", "Plane", "datum", required=True),
                                                       _F("d", "Distance", required=True)]),
            Variant("PN", "Point and normal", [_F("p", "Point", "point", required=True, pick="ANY"),
                                                _F("n", "Normal", "point", required=True, start="0, 0, 1"),
                                                _F("angle", "Turn (degrees)")]),
            Variant("3P", "Through three points", [_F("p1", "Point 1", "expr", required=True),
                                                    _F("p2", "Point 2", "expr", required=True),
                                                    _F("p3", "Point 3", "expr", required=True)],
                    help="Each point as (x, y, z), or a datum point's name"),
            Variant("ANGLE", "Turned about an axis", [_F("plane", "Plane", "datum", required=True),
                                                       _F("axis", "Axis", "datum", required=True),
                                                       _F("deg", "Angle (degrees)", required=True)]),
            Variant("MID", "Half way between two faces", [_F("f", "Faces", "ids", required=True, pick="FACE", count=2)]),
            Variant("NORMAL", "Across an edge", [edge, _F("t", "At fraction t", default="0")]),
        ]
    if cmd == "AXIS":
        return [
            Variant("Z", "Along Z", []), Variant("X", "Along X", []), Variant("Y", "Along Y", []),
            Variant("EDGE", "Along an edge", [edge]),
            Variant("FACE", "Axis of a face", [face]),
            Variant("PD", "Point and direction", [_F("p", "Point", "point", required=True, pick="ANY"),
                                                   _F("d", "Direction", "point", required=True, start="0, 0, 1")]),
            Variant("2P", "Through two points", [_F("p1", "Point 1", "expr", required=True),
                                                  _F("p2", "Point 2", "expr", required=True)]),
            Variant("PLANES", "Where two planes meet", [_F("a", "Plane 1", "datum", required=True),
                                                         _F("b", "Plane 2", "datum", required=True)]),
        ]
    return [  # POINT
        Variant("XYZ", "At coordinates", [_F("p", "Point", "point", required=True, pick="ANY")]),
        Variant("VERTEX", "At a vertex", [_F("id", "Vertex ID", "ids", required=True, pick="VERTEX")]),
        Variant("CENTER", "Centre of an edge, face or body",
                [_F("kind", "Of a", "choice", "EDGE", required=True, choices=("EDGE", "FACE", "BODY")),
                 _F("id", "ID", "ids", required=True, pick="ANY")]),
        Variant("ON", "Along an edge", [edge, _F("t", "At fraction t", required=True, default="", start="0.5")]),
    ]


def _hand() -> dict[str, FormSpec]:
    specs: dict[str, FormSpec] = {}

    def add(name, variants, word_slot=-1, title=""):
        cmd = REGISTRY[name]
        specs[name] = FormSpec(name, title or name.title(), cmd.help, "", variants, word_slot)

    for d in ("PLANE", "AXIS", "POINT"):
        vs = _datum_variants(d)
        for v in vs:
            v.head = ("name",)
            v.fields = [replace(_NAME)] + v.fields
        add(d, vs, word_slot=1)

    body = _F("b", "Body", "body", required=True, pick="BODY")
    fuse = _F("fuse", "Fuse into one body", "flag", word="FUSE")
    cut = _F("cut", "Cut them all from", "body", pick="BODY",
             help="a body to cut every copy from, the original too, in one step (leave empty to keep the copies)")
    mode = _F("mode", "Frame", "choice", "MINTWIST", choices=("MINTWIST", "FRENET", "FIXED"))
    add("ARRAY", [
        Variant("LINEAR", "In a row (or a grid)", [replace(body), _F("n", "Count", required=True, start="4"),
                                                    _F("d", "Step", "point", required=True, start="20, 0, 0"),
                                                    _F("n2", "Count 2 (grid)"), _F("d2", "Step 2", "point"), fuse,
                                                    cut]),
        Variant("POLAR", "Around an axis", [replace(body), _F("n", "Count", required=True, start="6"),
                                            _F("angle", "Total angle", default="360"),
                                            _F("p", "Axis point", "point", default="0, 0, 0"),
                                            _F("d", "Axis direction", "point", default="0, 0, 1"), fuse,
                                            replace(cut)]),
        Variant("PATH", "Along a curve", [replace(body), _F("path", "Path", "body", required=True, pick="BODY"),
                                          _F("n", "Count", required=True, start="5"),
                                          _F("twist", "Twist law", "expr", default="0"),
                                          _F("scale", "Scale law", "expr", default="1"), mode, fuse,
                                          replace(cut)]),
    ], word_slot=0)
    steps = _F("steps", "Steps that made the feature", required=True, start="1",
               help="how many of the last history steps made the feature: 1 for a HOLE, 2 for SEL then THREAD ...")
    pbody = _F("b", "On body", "body", required=True, pick="BODY")
    add("PATTERN", [
        Variant("LINEAR", "In a row (or a grid)", [pbody, steps, _F("n", "Count", required=True, start="4"),
                                                    _F("d", "Step", "point", required=True, start="20, 0, 0"),
                                                    _F("n2", "Count 2 (grid)"), _F("d2", "Step 2", "point")]),
        Variant("POLAR", "Around an axis", [replace(pbody), replace(steps), _F("n", "Count", required=True, start="6"),
                                            _F("angle", "Total angle", default="360"),
                                            _F("p", "Axis point", "point", default="0, 0, 0"),
                                            _F("d", "Axis direction", "point", default="0, 0, 1")]),
    ], word_slot=0)

    pts = _F("pts", "Points", "points", required=True, pick="VERTEX",
             help="one point per line: x, y, z (or a datum point's name)")
    add("POLYLINE", [Variant("", "", [pts, _F("close", "Closed", "flag", word="CLOSE")])])
    add("SPLINE", [Variant("", "", [replace(pts), _F("close", "Closed loop", "flag", word="CLOSE")])])
    add("INST", [Variant("", "", [
        _F("part", "Part", "part", required=True),
        _F("x", "Position", "point", default="0, 0, 0"),
        _F("angle", "Turn (degrees)", default="0"),
        _F("d", "Turn axis", "point", default="0, 0, 1"),
        _F("values", "Part values", "params",
           help="the part's parameters for this copy; left empty, they keep the part's defaults"),
    ])])
    add("LIB", [Variant("", "", [_F("action", "", "choice", "LOAD", choices=("LOAD",)),
                                 _F("file", "Part file", "path", required=True,
                                    help="a part name in the library folder, or a .cmd file")])])
    add("LOFT", [Variant("", "", [_F("s", "Sections", "bodies", required=True, pick="BODY", count=24,
                                     help="the section curves, in order (select them, then press ← Selection)"),
                                  _F("ruled", "Straight between sections", "flag", word="RULED"),
                                  _F("closed", "Loop back to the first", "flag", word="CLOSED"),
                                  _F("surface", "Surface only (no caps)", "flag", word="SURFACE")])])
    add("SPINELOFT", [Variant("", "", [
        _F("spine", "Spine", "body", required=True, pick="BODY", help="the centre line the sections follow"),
        _F("s", "Sections", "bodies", required=True, pick="BODY", count=16,
           help="the section curves, each drawn across the spine where it belongs (any order)"),
        _F("frenet", "Sections follow the spine's bend (FRENET)", "flag", word="FRENET"),
        _F("fixed", "Sections never turn (FIXED)", "flag", word="FIXED"),
        _F("surface", "Surface only (no caps)", "flag", word="SURFACE")])])

    def two(name):
        k = ("FACE", "EDGE", "VERTEX", "BODY", "DATUM")
        add(name, [
            Variant("", "The two selected things", [],
                    help="Select two things first: click one, Ctrl+click the other"),
            Variant("BY_ID", "Two things by ID", [
                _F("k1", "First is a", "choice", "FACE", required=True, choices=k), _F("i1", "ID or name", "word", required=True),
                _F("k2", "Second is a", "choice", "FACE", required=True, choices=k), _F("i2", "ID or name", "word", required=True)]),
        ])
    two("DIST")
    two("ANGLE")

    add("SKETCH", [
        Variant("PLANE", "On a plane", [replace(_NAME), _F("on", "Plane", "datum", "", choices=("XY", "YZ", "ZX"),
                                                        help="empty: the work plane, or XY")]),
        Variant("FACE", "On a flat face", [replace(_NAME), _F("id", "Face ID", "ids", required=True, pick="FACE")]),
    ], word_slot=1)  # FACE goes between the name and the ID; a plane name is written as is

    smode = _F("mode", "How", "choice", "S", required=True, choices=("S", "R", "A", "U"),
               help="S new selection, R reselect from it, A add, U take away")
    skind = _F("kind", "What", "choice", "FACE", required=True, choices=("FACE", "EDGE", "VERTEX", "BODY"))
    add("SEL", [
        Variant("ID", "By ID", [smode, skind, _F("crit", "", "choice", "ID", choices=("ID",)),
                                _F("a", "From ID", required=True), _F("b", "To ID")]),
        Variant("NORMAL", "Faces facing a direction", [replace(smode), replace(skind), _F("crit", "", "choice", "NORMAL", choices=("NORMAL",)),
                                                      _F("d", "Direction", "point", required=True, start="0, 0, 1")]),
        Variant("LOC", "At a coordinate", [replace(smode), replace(skind), _F("crit", "", "choice", "LOC", choices=("LOC",)),
                                           _F("axis", "Axis", "choice", "Z", required=True, choices=("X", "Y", "Z")),
                                           _F("v1", "Value (or from)", required=True), _F("v2", "To")]),
        Variant("SIZE", "By size", [replace(smode), replace(skind), _F("crit", "", "choice", "SIZE", choices=("SIZE", "RADIUS")),
                                    _F("op", "Compare", "choice", "GT", required=True, choices=("GT", "LT", "EQ", "GE", "LE")),
                                    _F("v1", "Value", required=True)]),
        Variant("TYPE", "By surface or curve type", [replace(smode), replace(skind), _F("crit", "", "choice", "TYPE", choices=("TYPE",)),
                                                     _F("t", "Type", "choice", "CYLINDER", required=True,
                                                        choices=("PLANE", "CYLINDER", "CONE", "SPHERE", "TORUS",
                                                                 "LINE", "CIRCLE", "BSPLINE"))]),
        Variant("BODY", "All of a body", [replace(smode), replace(skind), _F("crit", "", "choice", "BODY", choices=("BODY",)),
                                          _F("b", "Body", "body", required=True, pick="BODY")]),
        Variant("LAYER", "On a layer", [replace(smode), replace(skind, start="BODY"),
                                        _F("crit", "", "choice", "LAYER", choices=("LAYER",)),
                                        _F("lay", "Layer", "layer", required=True)]),
        Variant("OF", "Edges of the selected faces", [replace(smode), _F("kind", "What", "choice", "EDGE", required=True,
                                                                         choices=("EDGE", "VERTEX", "FACE")),
                                                      _F("crit", "", "choice", "OF", choices=("OF",)),
                                                      _F("of", "Of the selected", "choice", "FACE", required=True,
                                                         choices=("FACE", "EDGE", "BODY"))]),
        Variant("ALL", "Everything of a kind", [_F("mode", "", "choice", "ALL", choices=("ALL",)), replace(skind)]),
        Variant("NONE", "Nothing", [_F("mode", "", "choice", "NONE", choices=("NONE",))]),
        Variant("INVE", "Invert", [_F("mode", "", "choice", "INVE", choices=("INVE",))]),
    ])
    for sp in specs.values():
        sp.title = TITLES.get(sp.command, REGISTRY[sp.command].name.title())
    return specs


# menu titles where the command name alone says little
TITLES = {"INST": "Place a part", "EXPLODE": "Explode", "LIB": "Load parts from library",
          "LIBSAVE": "Save part to library"}

_SPECS: dict[str, FormSpec] | None = None


def specs() -> dict[str, FormSpec]:
    """Every form, by command name."""
    global _SPECS
    if _SPECS is None:
        Processor()  # makes sure every handler module has registered
        hand = _hand()
        out: dict[str, FormSpec] = {}
        for cat, names in CATEGORIES:
            for n in names:
                if n == PARAM:
                    out[n] = FormSpec(PARAM, "Parameter", "Set a parameter: a name for a number, a point or a "
                                      "text that later commands can use (W = 40, then BLOCK, 0,0,0, W, 10, 5). "
                                      "Change it later in the Parameters panel and the model re-runs.", cat,
                                      [Variant("", "", [_F("name", "Name", "word", required=True),
                                                        _F("value", "Value", "expr", required=True,
                                                           help="a number or expression, e.g. 40 or W/2")])])
                    continue
                if n not in REGISTRY:
                    continue
                sp = hand.get(n) or FormSpec(n, TITLES.get(n, n.title()), REGISTRY[n].help, cat,
                                             [Variant("", "", _generic(n))])
                sp.category = cat
                for v in sp.variants:  # a fresh form opens with the starting values
                    for f in v.fields:
                        if f.key in STARTS.get(n, {}) and not f.start:
                            f.start = STARTS[n][f.key]
                out[n] = sp
        _SPECS = out
    return _SPECS


def spec(name: str) -> FormSpec:
    try:
        return specs()[name.upper()]
    except KeyError:
        raise FormError(f"{name.upper()} has no form") from None


def missing_forms() -> list[str]:
    """Model-changing commands with neither a form nor another GUI route."""
    have = set(specs())
    return sorted(n for n in REGISTRY if n not in have and n not in NO_FORM)


# ---- choices the model offers ----------------------------------------------------

def body_label(p: Processor, bid: int) -> str:
    b = p.model.bodies.get(bid)
    if b is None:
        return str(bid)
    return b.name if b.name and not b.name.lower().startswith("body") else str(bid)


def options(p: Processor, f: Field, command: str = "") -> list[str]:
    """The values a field's list offers (the user may also type their own)."""
    m = p.model
    if f.kind == "choice":
        return list(f.choices)
    if f.kind in ("body", "bodies"):
        out = [body_label(p, b) for b in sorted(m.bodies)]
        if f.kind == "body" and m.bodies:
            out.append("LAST")
        if command == "SHOW":
            out = ["ALL"] + out
        if command in ("COLOR", "MATERIAL", "ISOLATE"):
            out = ["SEL", "ALL"] + out
            if command == "ISOLATE":
                out = ["SEL"] + [lay.name for lay in m.layers.values()] + out[2:]
        return out
    if f.kind == "layer":
        return [lay.name for lay in m.layers.values()]
    if f.kind == "datum":
        planes = [d.name for d in m.datums.values() if d.kind == "PLANE"]
        axes = [d.name for d in m.datums.values() if d.kind == "AXIS"]
        pts = [d.name for d in m.datums.values() if d.kind == "POINT"]
        if command == "REVOLVE":
            return ["V", "H"] + axes + ["X", "Y", "Z"]
        if command == "DATUM":
            return planes + axes + pts
        if command == "SPLIT":
            return planes + ["XY", "YZ", "ZX"] + [body_label(p, b) for b in sorted(m.bodies)]
        if f.key == "axis":
            return axes + ["X", "Y", "Z"]
        base = planes + ["XY", "YZ", "ZX"]
        if command in ("WORKPLANE", "SECTION"):
            base = base + ["OFF"]
        return base
    if f.kind == "sketch":
        return [sk.name for sk in m.sketches.values()]
    if f.kind == "part":
        return [pd.name.lower() for pd in p.parts.values()]
    return []


def _centre_of_selection(p: Processor) -> str:
    from ..commands.queries import bbox, centre

    m = p.model
    if not m.selection:
        raise FormError("nothing is selected")
    kind = m.selection_kind
    if kind == "BODY":
        x0, y0, z0, x1, y1, z1 = bbox(m.bodies[m.selection[0]].shape)
        c = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    else:
        c = centre(kind, m.entity_shape(kind, m.selection[0]))
    if m.workplane is not None:
        c = m.workplane.local(c)
    return ", ".join(fmt_num(round(v, 6) + 0.0) for v in c)


def from_selection(p: Processor, f: Field) -> str:
    """The value the "← Selection" button puts in a field."""
    m = p.model
    sel = list(m.selection)
    if f.kind in ("body", "bodies"):
        if m.selection_kind == "BODY":
            bids = sel
        else:  # a picked face or edge stands for its body
            bids = []
            for gid in sel:
                b = m.entity_owner(m.selection_kind, gid)[0]
                if b not in bids:
                    bids.append(b)
        if not bids:
            raise FormError("select a body first (or a face of it)")
        labels = [body_label(p, b) for b in bids]
        return labels[0] if f.kind == "body" else ", ".join(labels)
    if f.kind == "ids":
        if f.pick not in ("", "ANY") and m.selection_kind != f.pick:
            raise FormError(f"select {f.pick.lower()}s first (Pick mode: {f.pick.title()})")
        if not sel:
            raise FormError("nothing is selected")
        return ", ".join(str(i) for i in sel[: f.count or None])
    if f.kind == "point":
        return _centre_of_selection(p)
    if f.kind == "points":
        if m.selection_kind != "VERTEX" or not sel:
            raise FormError("select vertices first (Pick mode: Vertex)")
        from ..commands.queries import centre

        rows = []
        for gid in sel:
            c = centre("VERTEX", m.entity_shape("VERTEX", gid))
            if m.workplane is not None:
                c = m.workplane.local(c)
            rows.append(", ".join(fmt_num(round(v, 6) + 0.0) for v in c))
        return "\n".join(rows)
    raise FormError("this field does not read the selection")


def initial(p: Processor, sp: FormSpec, variant: str = "") -> dict[str, str]:
    """Values a fresh form opens with: starting values, plus what is selected."""
    v = sp.variant(variant)
    vals: dict[str, str] = {}
    m = p.model
    for f in v.fields:
        val = f.start
        if f.kind == "choice" and not val:
            val = f.default or (f.choices[0] if f.choices and f.required else "")
        if f.kind in ("body", "bodies") and f.pick == "BODY":
            got = ""
            # an optional body (CHECK, MASSPROP ...) is filled only from picked bodies
            if f.required or m.selection_kind == "BODY":
                try:
                    got = from_selection(p, f)
                except FormError:
                    pass
            if got:
                if f.kind == "body":
                    val = got.split(",")[0]
                else:
                    val = got
            elif f.kind == "body" and f.required and m.bodies:
                val = "LAST"
        if f.kind == "ids" and m.selection and (f.pick in ("", "ANY") or m.selection_kind == f.pick):
            val = from_selection(p, f)
        if f.kind == "part" and not val:
            names = options(p, f)
            val = names[-1] if names else ""
        if f.kind == "sketch" and not val:
            names = options(p, f)
            val = names[-1] if names else ""
        if f.kind == "bool" and not val:
            val = f.default or "1"
        vals[f.key] = val
    # names: the next free one
    prefix = {"PLANE": "P", "AXIS": "A", "POINT": "PT", "SKETCH": "s", "CM": "set"}.get(sp.command)
    if prefix and "name" in vals and not vals["name"]:
        from .feature_actions import free_name

        vals["name"] = free_name(p, prefix)
    # colour, material, isolate: whatever is picked (bodies, or the bodies of picked faces)
    if sp.command in ("COLOR", "MATERIAL", "ISOLATE") and m.selection and len(m.selection) > 1 or (
            sp.command in ("COLOR", "MATERIAL", "ISOLATE") and m.selection and m.selection_kind != "BODY"):
        vals["target"] = "SEL"
    # HOLE: drill where the picked face is
    if sp.command == "HOLE" and m.selection and m.selection_kind in ("FACE", "VERTEX"):
        vals["x"] = _centre_of_selection(p)
    # a body list after a first body: the rest of the selection
    if sp.command in ("UNION", "SUBTRACT", "INTERSECT", "CLASH"):
        first, rest = v.fields[0].key, v.fields[1].key
        try:
            labels = [s.strip() for s in from_selection(p, Field("b", "", "bodies")).split(",")]
        except FormError:
            labels = []
        if sp.command == "CLASH" and m.selection_kind != "BODY":
            labels = []
        if len(labels) >= 2:
            vals[first], vals[rest] = labels[0], ", ".join(labels[1:] if sp.command != "CLASH" else labels[1:2])
        elif sp.command != "CLASH":
            # the picked body (or the last one) first, then the newest other body
            others = [body_label(p, b) for b in sorted(m.bodies) if body_label(p, b) != vals.get(first)]
            if vals.get(first) == "LAST" and len(m.bodies) >= 2:
                ids = sorted(m.bodies)
                vals[first] = body_label(p, ids[-2])
                others = [body_label(p, ids[-1])]
            vals[rest] = others[-1] if others else ""
    return vals


# ---- building the command text ---------------------------------------------------

def _quote(s: str) -> str:
    return '"' + s.replace('"', "'") + '"'


def _list(text: str) -> list[str]:
    try:
        return [t for t in split_args(text) if t]
    except ScriptError as exc:
        raise FormError(str(exc)) from None


def _tokens(f: Field, value: str) -> list[tuple[str, str]]:
    """The arguments one field writes, each with its default."""
    value = (value or "").strip()
    if f.kind == "point":
        if not value:
            return [("", d) for d in f.defaults()]
        parts = _list(value[1:-1] if value.startswith("(") and value.endswith(")") else value)
        if len(parts) == 1:  # a whole point in one expression: (1,2,3) or a parameter holding one
            return [(parts[0], "")]
        if len(parts) != 3:
            raise FormError(f"{f.label}: give three numbers x, y, z")
        return list(zip(parts, f.defaults()))
    if f.kind in ("bodies", "ids"):
        parts = _list(value)
        if f.count and len(parts) > f.count:
            raise FormError(f"{f.label}: at most {f.count}")
        return [(t, "") for t in parts] or [("", f.default)]
    if f.kind == "points":
        rows = [r.strip() for r in value.replace(";", "\n").splitlines() if r.strip()]
        out = []
        for r in rows:
            r = r[1:-1] if r.startswith("(") and r.endswith(")") else r
            parts = _list(r)
            if len(parts) == 1 and is_ident(parts[0]):
                out.append((parts[0], ""))
            elif len(parts) in (2, 3):
                out.append(("(" + ", ".join(parts) + ")", ""))
            else:
                raise FormError(f"{f.label}: each line is x, y, z")
        return out
    if f.kind == "path":
        if value and not (value[0] in "\"'" and value[-1] == value[0]):
            value = _quote(value)
        return [(value, f.default)]
    if f.kind == "text":
        if value and not is_ident(value) and value[:1] not in "\"'(" and any(c in value for c in ",!\"' "):
            value = _quote(value)
        return [(value, f.default)]
    if f.kind == "bool":
        value = value or f.default
        return [("1" if value.lower() in ("1", "true", "yes", "on") else "0", f.default)]
    if f.kind == "flag":
        return []
    return [(value, f.default)]


def build(sp: FormSpec, values: dict[str, str], variant: str = "") -> str:
    """The command line for these form values. Raises FormError if a required
    value is missing; whether the values make sense is the command's job."""
    v = sp.variant(variant)
    if sp.command == PARAM:
        name, value = (values.get("name") or "").strip(), (values.get("value") or "").strip()
        if not name or not value:
            raise FormError(("Name" if not name else "Value") + ": needed")
        if not is_ident(name):
            raise FormError(f"Name: {name!r} is not a valid name (letters, digits, _)")
        return f"{name} = {value}"
    groups: list[list[tuple[str, str]]] = []  # one per field: its arguments with their defaults
    words: list[str] = []
    for f in v.fields:
        val = (values.get(f.key) or "").strip()
        if f.kind == "choice" and len(f.choices) == 1 and not val:
            val = f.choices[0]  # the fixed word of this variant
        if f.kind == "flag":
            if val.lower() in ("1", "true", "yes", "on", f.word.lower()):
                words.append(f.word)
            continue
        if f.key == "cut" and sp.command == "ARRAY":  # CUT, target: written with the words at the end
            if val:
                words.extend(["CUT", val])
            continue
        if f.kind == "params":  # NAME=value: their place does not matter, so they go last
            for t in _list(val):
                name, eq, expr = t.partition("=")
                if not eq or not is_ident(name.strip()) or not expr.strip():
                    raise FormError(f"{f.label}: write NAME=value, got {t!r}")
                words.append(f"{name.strip().upper()}={expr.strip()}")
            continue
        if f.required and not val and not (f.kind == "point" and f.default):
            raise FormError(f"{f.label or f.key}: needed")
        got = _tokens(f, val)
        if f.required or (f.kind == "choice" and len(f.choices) == 1):
            got = [(t, "") for t, _ in got]  # always written, even when it equals the default
        groups.append(got)
    # the variant keyword, before the field it introduces
    key = v.key
    if sp.command in ("DIST", "ANGLE", "SEL") or (sp.command == "SKETCH" and key != "FACE"):
        key = ""
    if key:
        groups.insert(min(max(sp.word_slot, 0), len(groups)), [(key, "")])

    def unused(g: list[tuple[str, str]]) -> bool:
        return all(t == "" or (d != "" and _same(t, d)) for t, d in g)

    # leave out what is at its default at the end; a point is written whole or not at all
    while groups and unused(groups[-1]):
        groups.pop()
    args = [t for g in groups for t, _ in g] + words
    return sp.command + (", " + ", ".join(args) if args else "")


def _same(a: str, b: str) -> bool:
    if a.strip().upper() == b.strip().upper():
        return True
    try:
        return float(a) == float(b)
    except ValueError:
        return False


# ---- reading a command back into a form (Edit in form) -------------------------

def parse(text: str) -> tuple[FormSpec, str, dict[str, str]]:
    """Form, variant and values for one command line, so a history entry can
    be edited in its form. Raises FormError when the line has no form or does
    not fit one."""
    line = strip_comment(first_code_line(text)).strip()
    if not line or "\n" in text.strip() and len([ln for ln in text.splitlines() if strip_comment(ln).strip()]) > 1:
        raise FormError("only a one-line command opens in a form")
    head = line.split(",")[0]
    if "=" in head and is_ident(head.split("=")[0].strip()) and not head.lstrip().startswith("*"):
        name, value = line.split("=", 1)
        return spec(PARAM), "", {"name": name.strip(), "value": value.strip()}
    try:
        parts = split_args(line)
    except ScriptError as exc:
        raise FormError(str(exc)) from None
    name = parts[0].upper()
    sp = spec(name)
    args = parts[1:]
    while args and args[-1] == "":
        args.pop()
    # pick the variant
    variant = ""
    if len(sp.variants) > 1:
        keys = {v.key.upper() for v in sp.variants}
        if sp.command == "SEL":
            if args and args[0].upper() in ("ALL", "NONE", "INVE"):
                variant = args[0].upper()
            elif len(args) >= 3:
                c = args[2].upper()
                variant = {"RADIUS": "SIZE"}.get(c, c)
                if variant not in keys:
                    raise FormError(f"SEL by {c} has no form; edit it as text")
            else:
                variant = "ID"
            if variant in ("ID",) and len(args) >= 3 and args[2].upper() != "ID":
                args = args[:2] + ["ID"] + args[2:]
        elif sp.command in ("DIST", "ANGLE"):
            variant = "BY_ID" if args else ""
        elif sp.command == "SKETCH":
            variant = "FACE" if len(args) > 1 and args[1].upper() == "FACE" else "PLANE"
            if variant == "FACE":
                args = args[:1] + args[2:]
        else:
            slot = max(sp.word_slot, 0)
            if len(args) <= slot or args[slot].upper() not in keys:
                raise FormError(f"{name}: the form does not know this way of using it")
            variant = args[slot].upper()
            args = args[:slot] + args[slot + 1:]
    v = sp.variant(variant)
    values: dict[str, str] = {}
    if sp.command == "ARRAY":
        up = [a.strip().upper() for a in args]
        if "CUT" in up:
            k = up.index("CUT")
            values["cut"] = args[k + 1] if k + 1 < len(args) else ""
            args = args[:k] + args[k + 2:]
    words = {f.word.upper(): f for f in v.fields if f.kind == "flag"}
    pfield = next((f for f in v.fields if f.kind == "params"), None)
    plain, pvals = [], []
    for a in args:
        name, eq, _expr = a.partition("=")
        if a.upper() in words:
            values[words[a.upper()].key] = "1"
        elif pfield is not None and eq and is_ident(name.strip()):
            pvals.append(a.strip())
        else:
            plain.append(a)
    if pfield is not None:
        values[pfield.key] = ", ".join(pvals)
    i = 0
    fields = [f for f in v.fields if f.kind not in ("flag", "params") and not (f.key == "cut" and sp.command == "ARRAY")]
    for f in fields:
        if f.kind == "point":
            if i < len(plain) and plain[i].startswith("("):
                values[f.key] = plain[i][1:-1].strip() if plain[i].endswith(")") else plain[i]
                i += 1
            else:
                got = plain[i:i + 3]
                values[f.key] = ", ".join(got) if any(got) else ""
                i += 3
        elif f.kind in ("bodies", "points") or (f.kind == "ids" and (f.count == 0 or f.count > 1)):
            n = f.count if f.kind != "points" and f.count else len(plain) - i
            got = plain[i:i + n]
            if f.kind == "points":
                values[f.key] = "\n".join(t[1:-1] if t.startswith("(") and t.endswith(")") else t for t in got)
            else:
                values[f.key] = ", ".join(t for t in got if t)
            i += n
        else:
            val = plain[i] if i < len(plain) else ""
            if f.kind == "path" and len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
                val = val[1:-1]
            values[f.key] = val
            i += 1
    if i < len(plain) and any(plain[i:]):
        raise FormError(f"{name}: more arguments than the form has fields; edit it as text")
    return sp, variant, values


# ---- checking before running -----------------------------------------------------

def check(p: Processor, sp: FormSpec, values: dict[str, str], variant: str = "") -> tuple[str, dict[str, str]]:
    """The command text and per-field problems found without running it:
    expressions that do not evaluate, bodies that do not exist."""
    problems: dict[str, str] = {}
    v = sp.variant(variant)
    for f in v.fields:
        val = (values.get(f.key) or "").strip()
        if not val:
            continue
        try:
            if f.kind == "num" or (sp.command == PARAM and f.key == "value"):
                p.evaluate(val)
            elif f.kind == "point":
                for part in _list(val[1:-1] if val.startswith("(") and val.endswith(")") else val):
                    p.evaluate(part)
            elif f.kind in ("body", "bodies"):
                for part in _list(val):
                    if part.upper() in ("LAST", "SEL", "ALL"):
                        continue
                    bid = p._body_arg(REGISTRY.get(sp.command, REGISTRY["MOVE"]), part)
                    if bid not in p.model.bodies:
                        raise FormError(f"there is no body {part}")
            elif f.kind == "ids":
                for part in _list(val):
                    p.evaluate(part)
            elif f.kind == "params":
                known = {n for n, _ in part_params(p, values.get("part", ""))}
                for t in _list(val):
                    name, _eq, expr = t.partition("=")
                    if known and name.strip().upper() not in known:
                        raise FormError(f"the part has no {name.strip()} (it has {', '.join(sorted(known))})")
                    p.evaluate(expr.strip())
            elif f.kind == "part" and val.upper() not in p.parts:
                raise FormError(f"no part {val}" + ("" if p.parts else "; define one with *PART or load one"))
        except (ExprError, CommandError, FormError) as exc:
            msg = str(exc)
            problems[f.key] = msg.split(": ", 1)[-1] if msg.startswith(sp.command) else msg
    try:
        text = build(sp, values, variant)
    except FormError as exc:
        text = ""
        problems.setdefault("", str(exc))
    return text, problems


def part_params(p: Processor, name: str) -> list[tuple[str, str]]:
    """A part's parameters and their defaults (as written), for its form."""
    pd = p.parts.get((name or "").strip().upper())
    return [(n, d or "") for n, d in pd.params] if pd else []


def has_form(text: str) -> bool:
    """Whether a history entry can be edited in a form."""
    try:
        parse(text)
    except FormError:
        return False
    return True


def replace_code_line(old: str, new: str) -> str:
    """Put a new command in place of an entry's command line, keeping its comments."""
    lines = old.splitlines()
    for i, raw in enumerate(lines):
        code = strip_comment(raw).strip()
        if code:
            comment = raw[len(strip_comment(raw)):].strip()
            lines[i] = new + (f"    {comment}" if comment else "")
            return "\n".join(lines)
    return new
