"""Files: IMPORT shapes, and SAVE / OPEN / NEW projects.

A project file (``.m3d``) is a zip holding the history as a script
(``script.cmd``), every file the script imports (``files/``), and a small
``project.json``. Opening one replays the script, with IMPORT reading the
files stored inside the project, so a project keeps working when it is
moved to another computer.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import zipfile

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepTools import BRepTools
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape

from ..lang.script import first_code_line, parse
from .processor import Arg, CommandError, Path, Processor, Text, command

PROJECT_VERSION = 1
_IMPORT_FORMATS = ("STEP", "IGES", "BREP", "STL")
_as_shell = getattr(TopoDS, "Shell_s", None) or TopoDS.Shell


def _static(cls, name):
    return getattr(cls, name + "_s", None) or getattr(cls, name)


# ---- reading shapes ------------------------------------------------------------
def _read_step_like(reader, path: str, what: str) -> TopoDS_Shape:
    status = reader.ReadFile(path)
    if status != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise CommandError(f"IMPORT: could not read {what} file {path}")
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        raise CommandError(f"IMPORT: {path} holds no shapes")
    return shape


def _read_stl(path: str) -> TopoDS_Shape:
    from OCP.StlAPI import StlAPI_Reader

    shape = TopoDS_Shape()
    if not StlAPI_Reader().Read(shape, path):
        raise CommandError(f"IMPORT: could not read STL file {path}")
    # an STL is a soup of triangles: sew them and make a solid when it is closed
    sew = BRepBuilderAPI_Sewing(1e-6)
    sew.Add(shape)
    sew.Perform()
    sewn = sew.SewedShape()
    ex = TopExp_Explorer(sewn, TopAbs_SHELL)
    if ex.More():
        mk = BRepBuilderAPI_MakeSolid(_as_shell(ex.Current()))
        if mk.IsDone():
            solid = mk.Solid()
            if BRepCheck_Analyzer(solid).IsValid():
                return solid
    return sewn


def read_shape(fmt: str, path: str) -> TopoDS_Shape:
    if fmt == "STEP":
        return _read_step_like(STEPControl_Reader(), path, "STEP")
    if fmt == "IGES":
        from OCP.IGESControl import IGESControl_Reader

        return _read_step_like(IGESControl_Reader(), path, "IGES")
    if fmt == "BREP":
        shape = TopoDS_Shape()
        if not _static(BRepTools, "Read")(shape, path, BRep_Builder()):
            raise CommandError(f"IMPORT: could not read BREP file {path}")
        return shape
    return _read_stl(path)


def _solids(shape: TopoDS_Shape) -> list[TopoDS_Shape]:
    out = []
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out or [shape]


@command(
    "IMPORT",
    Arg("format", str, help="STEP, IGES, BREP or STL"),
    Arg("file", Path),
    Arg("name", Text, "", "name for the (first) imported body"),
    help="Read bodies from a file. Each solid in it becomes a body. Saved projects keep a copy of the file.",
)
def import_(p: Processor, format, file, name):
    if format not in _IMPORT_FORMATS:
        raise CommandError(f"IMPORT: format must be one of {', '.join(_IMPORT_FORMATS)}")
    path = p.file_map.get(file, file)
    if not os.path.isfile(path):
        raise CommandError(f"IMPORT: no such file: {file}")
    shape = read_shape(format, path)
    from .handlers import _added

    msgs = []
    for k, s in enumerate(_solids(shape)):
        body = p.model.add_body(s, name if (name and k == 0) else "")
        msgs.append(_added(p, body, "IMPORT"))
    if len(msgs) == 1:
        return msgs[0]
    return f"IMPORT {file}: {len(msgs)} bodies\n  " + "\n  ".join(msgs)


# ---- projects -------------------------------------------------------------------
def _imports_in(p: Processor) -> list[str]:
    """File names that IMPORT commands in the applied history read."""
    files: list[str] = []

    def walk(stmts):
        for st in stmts:
            name = getattr(st, "name", None)
            args = getattr(st, "args", [])
            if (name == "IMPORT" and len(args) >= 2) or (name == "LIB" and len(args) >= 2
                                                          and args[0].strip().upper() == "LOAD"):
                raw = st.args[1].strip()
                if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]:
                    raw = raw[1:-1]
                if raw not in files:
                    files.append(raw)
            for sub in [getattr(st, "body", None), getattr(st, "orelse", None)] + [b for _, b in getattr(st, "branches", [])]:
                if isinstance(sub, list):
                    walk(sub)

    for e in p.history[: p.cursor]:
        if not e.suppressed:
            try:
                walk(parse(e.text))
            except Exception:  # noqa: BLE001 - a broken entry has nothing to save
                pass
    return files


def save_project(p: Processor, path: str) -> int:
    """Write the project zip; returns the number of history entries."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".tmp"
    files = {}
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("script.cmd", p.script())
        for i, name in enumerate(_imports_in(p)):
            real = p.file_map.get(name) or p.lib_files.get(name) or name
            if os.path.isfile(real):
                stored = f"files/{i}_{os.path.basename(name)}"
                z.write(real, stored)
                files[name] = stored
        # what each entry remembers: the IDs it handed out and its pick
        # fingerprints, so the reopened model is numbered exactly as it is now
        history = [
            {"text": e.text, "uid": e.uid, "pins": e.pins, "refs": e.refs}
            for e in p.history[: p.cursor]
            if not e.suppressed
        ]
        meta = {
            "version": PROJECT_VERSION,
            "app": "3Dmodeling",
            "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
            "units": p.model.units,
            "entries": p.cursor,
            "files": files,
            "history": history,
        }
        z.writestr("project.json", json.dumps(meta, indent=2))
    os.replace(tmp, path)
    return p.cursor


def open_project(p: Processor, path: str) -> tuple[int, list[str]]:
    """Replace the session with the project. Returns (entries run, errors)."""
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise CommandError(f"OPEN: {path} is not a project file ({exc})") from None
    with z:
        try:
            meta = json.loads(z.read("project.json"))
            script = z.read("script.cmd").decode("utf-8")
        except KeyError as exc:
            raise CommandError(f"OPEN: {path} is missing {exc}") from None
        if meta.get("version", 0) > PROJECT_VERSION:
            raise CommandError("OPEN: this project was saved by a newer version")
        tmpdir = tempfile.mkdtemp(prefix="m3d_")
        mapping = {}
        for name, stored in meta.get("files", {}).items():
            z.extract(stored, tmpdir)
            mapping[name] = os.path.join(tmpdir, stored)
    p.reset()
    p.file_map = mapping
    results = p.run_script(script, meta.get("history"))
    errors = [f"'{first_code_line(r.line)}': {r.message}" for r in results if not r.ok]
    return len([r for r in results if r.ok]), errors


def _resolve(p: Processor, file: str, what: str) -> str:
    if file.upper() == "AUTOSAVE":
        if not p.autosave_path:
            raise CommandError(f"{what}: there is no autosave in this session")
        return p.autosave_path
    return file if os.path.splitext(file)[1] else file + ".m3d"


@command("SAVE", Arg("file", Path, "", "project file (.m3d); default: the last one saved or opened"), session=True,
         help="Save the project: the history, plus a copy of every imported file.")
def save(p: Processor, file):
    file = _resolve(p, file, "SAVE") if file else p.project_path
    if not file:
        raise CommandError("SAVE: give a file name, e.g. SAVE, bracket.m3d")
    n = save_project(p, file)
    p.project_path = file
    return f"saved {n} entr{'y' if n == 1 else 'ies'} to {file}"


@command("OPEN", Arg("file", Path, help="project file (.m3d), or AUTOSAVE"), session=True,
         help="Open a project: the session is replaced and the history replayed. OPEN, AUTOSAVE recovers the last autosave.")
def open_(p: Processor, file):
    path = _resolve(p, file, "OPEN")
    if not os.path.isfile(path):
        raise CommandError(f"OPEN: no such file: {file}")
    n, errors = open_project(p, path)
    if file.upper() != "AUTOSAVE":
        p.project_path = path
    msg = f"opened {file}: {n} entr{'y' if n == 1 else 'ies'}, {len(p.model.bodies)} bodies"
    if errors:
        raise CommandError(msg + "; stopped at " + errors[0])
    return msg


@command("NEW", session=True, help="Start an empty session (unsaved work is lost; UNDO cannot bring it back).")
def new(p: Processor):
    p.reset()
    p.project_path = None
    return "new session"
