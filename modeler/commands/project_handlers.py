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

import numpy as np

from OCP.BRep import BRep_Builder
from OCP.BRepTools import BRepTools
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS_Shape

from ..lang.script import first_code_line, parse
from .processor import Arg, CommandError, Path, Processor, Text, command
from .sketch_edit import saved_entries

PROJECT_VERSION = 1
_IMPORT_FORMATS = ("STEP", "IGES", "BREP", "STL", "OBJ", "3MF", "GLTF", "PLY", "OFF", "VTK", "MESH", "XYZ", "PTS",
                   "E57", "SCAD")
POINT_FORMATS = ("XYZ", "PTS", "E57")
# formats read as triangles (a faceted body); MESH takes any file meshio reads, by its extension
MESH_FORMATS = ("STL", "OBJ", "3MF", "GLTF", "PLY", "OFF", "VTK", "MESH")


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


def _read_triangles(fmt: str, path: str, units: str):
    """(points, triangles) of a mesh file, in the model's units."""
    from ..core.model import UNITS
    from ..geometry import meshfiles

    name = os.path.basename(path)
    try:
        if fmt == "3MF":
            pts, tris = meshfiles.read_3mf(path)
            pts = pts / UNITS[units]
        elif fmt == "GLTF":
            pts, tris = meshfiles.read_gltf(path)
            pts = pts / UNITS[units]
        elif fmt == "STL":
            pts, tris = meshfiles.read_stl(path)
        else:
            pts, tris = meshfiles.read_with_meshio(path)
    except meshfiles.MeshFileError as exc:
        raise CommandError(f"IMPORT: {name}: {exc}") from None
    if len(tris) == 0:
        raise CommandError(f"IMPORT: {name} has no surface triangles (only points or lines)")
    return pts, tris


def _ply_faces(path: str) -> int:
    from ..geometry import pointcloud as pc

    try:
        return pc.read_ply(path)[1]
    except (pc.CloudError, OSError, ValueError, KeyError):
        return -1  # let the mesh reader say what is wrong


def _import_points(p: Processor, fmt: str, path: str, name: str) -> str:
    from ..geometry import pointcloud as pc
    from .handlers import _added

    fname = os.path.basename(path)
    try:
        if fmt in POINT_FORMATS or fmt == "PLY":
            pts = pc.read(path) if fmt != "PLY" else pc.read_ply(path)[0]
        else:
            pts, _t = _read_triangles(fmt, path, p.model.units)
    except pc.CloudError as exc:
        raise CommandError(f"IMPORT: {fname}: {exc}") from None
    except (OSError, ValueError) as exc:
        raise CommandError(f"IMPORT: {fname} cannot be read: {exc}") from None
    pts = np.asarray(pts, float)
    pts = pts[np.isfinite(pts).all(axis=1)]
    if not len(pts):
        raise CommandError(f"IMPORT: {fname} has no points")
    n = len(pts)
    pts = pc.thin(pts, pc.MOST_POINTS)
    body = p.model.add_body(pc.make_shape(pts), name)
    if len(pts) < n:
        p.warn(f"IMPORT: {fname} has {n:,} points; thinned evenly to {len(pts):,} (one per {pc.MOST_POINTS:,}th of "
               "the space) so the cloud stays quick to show and pick")
    return _added(p, body, "IMPORT")


# each triangle becomes a face of the body: past this the body gets too slow to work with
MAX_MESH_TRIANGLES = 100_000


def read_shape(fmt: str, path: str) -> TopoDS_Shape:
    """An exact (STEP, IGES or BREP) file as one shape."""
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
    raise CommandError(f"IMPORT: {fmt} is not an exact format")


def _exact_pieces(fmt: str, path: str, pmi: list | None = None,
                  named: list | None = None) -> list[tuple[TopoDS_Shape, str, tuple | None]]:
    """(shape, name, colour) for each body an exact file gives. STEP keeps part names and colours, and
    puts its sizes and tolerances (AP242) in ``pmi`` when given and its named faces, edges and points
    in ``named`` as (sub-shape, name) (PLAN item 95)."""
    if fmt == "STEP":
        from ..geometry import robust, stepdoc

        try:
            parts = stepdoc.read(path, pmi)
        except OSError:
            raise CommandError(f"IMPORT: could not read STEP file {path}") from None
        if not parts:
            raise CommandError(f"IMPORT: {path} holds no shapes")
        out, loose = [], []
        for part in parts:
            if named is not None:
                named += part.faces
            pieces = _solids(part.shape)
            if not part.name and not robust.solids(part.shape):
                loose += pieces  # unnamed faces and skins: kept together, as the plain reader gives them
                continue
            for i, s in enumerate(pieces):
                own = part.name if i == 0 or not part.name else f"{part.name}_{i + 1}"
                out.append((s, own, part.color))
        if loose:
            out.append((loose[0] if len(loose) == 1 else _compound_of(loose), "", None))
        return out
    return [(s, "", None) for s in _solids(read_shape(fmt, path))]


def _compound_of(shapes: list[TopoDS_Shape]) -> TopoDS_Shape:
    from OCP.TopoDS import TopoDS_Compound

    b, c = BRep_Builder(), TopoDS_Compound()
    b.MakeCompound(c)
    for s in shapes:
        b.Add(c, s)
    return c


def _free_name(model, wanted: str) -> str:
    """``wanted`` made into a name commands can use (letters, digits, _) and not yet taken; "" for none."""
    import re

    base = re.sub(r"\W+", "_", wanted.strip()).strip("_")
    if not base:
        return ""
    if not (base[0].isalpha() or base[0] == "_"):
        base = "P_" + base
    name, n = base, 1
    while True:
        try:
            model._check_name_free(name)
            return name
        except Exception:  # noqa: BLE001 - taken: try the next number
            n += 1
            name = f"{base}_{n}"


def _solids(shape: TopoDS_Shape) -> list[TopoDS_Shape]:
    """Each solid, then each shell that is not part of a solid (an open mesh piece)."""
    out = []
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    if out:
        ex = TopExp_Explorer(shape, TopAbs_SHELL, TopAbs_SOLID)
        while ex.More():
            out.append(ex.Current())
            ex.Next()
    return out or [shape]


def _import_scad(p: Processor, path: str, name: str) -> str:
    """OpenSCAD's constructive part as exact bodies: one per top-level object (PLAN item 101)."""
    from ..geometry import robust
    from ..geometry import scad
    from .handlers import _added

    fname = os.path.basename(path)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            shapes, counts = scad.read(fh.read())
    except scad.ScadError as exc:
        raise CommandError(f"IMPORT: {fname}: {exc}") from None
    except RecursionError:
        raise CommandError(f"IMPORT: {fname}: a module calls itself without end") from None
    shapes = [s for s in shapes if s is not None and not robust.is_empty(s)]
    if not shapes:
        raise CommandError(f"IMPORT: {fname} makes no shapes")
    msgs, flat = [], 0
    for k, s in enumerate(shapes):
        s = robust.unwrap(s)
        if not robust.solids(s):
            flat += 1
        body = p.model.add_body(s, name if (name and k == 0) else "")
        msgs.append(_added(p, body, "IMPORT"))
    if flat:
        p.warn(f"IMPORT: {flat} top-level object{'s are' if flat != 1 else ' is'} flat (2D); EXTRUDE or "
               "linear_extrude makes a solid")
    used = ", ".join(f"{v} {k}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:6])
    head = f"IMPORT {fname}: {len(shapes)} bod{'y' if len(shapes) == 1 else 'ies'} from OpenSCAD ({used})"
    return "\n".join([head] + ["  " + m for m in msgs])


@command(
    "IMPORT",
    Arg("format", str, help="STEP, IGES, BREP, SCAD, STL, OBJ, 3MF, GLTF, PLY, OFF, VTK, MESH, or points: XYZ, "
                            "PTS, E57"),
    Arg("file", Path),
    Arg("name", Text, "", "name for the (first) imported body"),
    Arg("kind", str, "AUTO", "for triangle files: SOLID (faceted, one face per triangle), MESH (a mesh body), "
                             "POINTS (only the corners, as a point body) or AUTO (SOLID up to 100,000 triangles, "
                             "MESH above)"),
    help="Read bodies from a file. Each solid in it becomes a body. STEP, IGES and BREP are exact; STL, OBJ, 3MF, "
         "GLTF, PLY, OFF and VTK (.vtk, .vtu) are triangles and become one faceted body (a solid when closed; "
         "volume meshes keep their outer skin), or a mesh body with kind MESH or when the file is big. MESH "
         "reads any other mesh file meshio knows, by its extension (Gmsh .msh, Abaqus .inp, Nastran .bdf, ...). "
         "XYZ (.xyz, .txt, .csv), PTS and E57 scanner files, and PLY files with no faces, become a point body, "
         "thinned to at most 200,000 points. SCAD reads an OpenSCAD file's solids, flat shapes, extrusions, "
         "transforms, booleans, variables, loops and modules as exact bodies, one per top-level object. Saved "
         "projects keep a copy of the file.",
)
def import_(p: Processor, format, file, name, kind):
    if format not in _IMPORT_FORMATS:
        raise CommandError(f"IMPORT: format must be one of {', '.join(_IMPORT_FORMATS)}")
    path = p.file_map.get(file, file)
    if not os.path.isfile(path):
        raise CommandError(f"IMPORT: no such file: {file}")
    from .handlers import _added

    msgs: list[str] = []
    tail: list[str] = []  # notes after the bodies (sets, annotations)
    if kind not in ("AUTO", "SOLID", "MESH", "POINTS"):
        raise CommandError("IMPORT: kind is AUTO, SOLID, MESH or POINTS")
    if format in POINT_FORMATS or (format == "PLY" and (kind == "POINTS" or _ply_faces(path) == 0)) \
            or (kind == "POINTS" and format in MESH_FORMATS):
        return _import_points(p, format, path, name)
    if format == "SCAD":
        return _import_scad(p, path, name)
    if format in MESH_FORMATS:
        from ..geometry import meshbody, meshfiles

        pts, tris = _read_triangles(format, path, p.model.units)
        fname = os.path.basename(path)
        if kind == "MESH" or (kind == "AUTO" and len(tris) > MAX_MESH_TRIANGLES):
            if len(tris) > meshbody.MAX_MESH_BODY_TRIANGLES:
                raise CommandError(f"IMPORT: {fname} has {len(tris):,} triangles; a mesh body "
                                   f"takes up to {meshbody.MAX_MESH_BODY_TRIANGLES:,}")
            try:
                pts, tris = meshfiles.clean(pts, tris)
            except meshfiles.MeshFileError as exc:
                raise CommandError(f"IMPORT: {fname}: {exc}") from None
            if len(tris) == 0:
                raise CommandError(f"IMPORT: {fname} has no triangles with area")
            shape = meshbody.make_shape(pts, tris)
            body = p.model.add_body(shape, name)
            if not meshbody.info(shape).closed:
                p.warn(f"IMPORT: {fname} is not closed, so the mesh body has no inside and cannot take booleans")
            return _added(p, body, "IMPORT")
        if len(tris) > MAX_MESH_TRIANGLES:
            raise CommandError(f"IMPORT: {fname} has {len(tris):,} triangles; up to {MAX_MESH_TRIANGLES:,} can "
                               "become a faceted solid. Import it with kind MESH, or reduce it first.")
        try:
            pieces = meshfiles.mesh_to_pieces(pts, tris)
        except meshfiles.MeshFileError as exc:
            raise CommandError(f"IMPORT: {fname}: {exc}") from None
        if not pieces:
            raise CommandError(f"IMPORT: {fname} has no triangles with area")
        for k, pc in enumerate(pieces):
            body = p.model.add_body(pc.shape, name if (name and k == 0) else "")
            note = "" if pc.closed else ", open surface, not a solid"
            msgs.append(f"{_added(p, body, 'IMPORT')} [{pc.triangles} triangles{note}]")
    else:
        from ..geometry import robust

        unclean = []
        pmi: list = []
        new_ids = []
        named: list = []
        for k, (s, own, colour) in enumerate(_exact_pieces(format, path, pmi, named)):
            body = p.model.add_body(s, name if (name and k == 0) else _free_name(p.model, own))
            new_ids.append(body.id)
            if colour is not None:
                p.model.set_style(body.id, color=colour)
            msgs.append(_added(p, body, "IMPORT"))
            if robust.count(s, robust.TopAbs_FACE) and not robust.report(s)["ok"]:
                unclean.append(body.id)
        if named:
            made = _named_sets_back(p, new_ids, named)
            if made:
                tail.append(f"{len(made)} named set{'s' if len(made) != 1 else ''} from the file: "
                            + ", ".join(made))
        if unclean:
            b0 = unclean[0]
            which = f"body {b0} is" if len(unclean) == 1 else f"bodies {', '.join(map(str, unclean))} are"
            p.warn(f"IMPORT: {which} not a clean solid (open edges, loose faces or invalid faces); "
                   f"CHECK, {b0}, FLAWS lists the flaws and HEAL, {b0} repairs what it can")
        if pmi:
            from ..geometry import step_pmi
            from .pmi_notes import records_to_notes

            made = records_to_notes(p, pmi, new_ids)
            tail.append(f"{made} note{'s' if made != 1 else ''} from the file's annotations "
                        f"({step_pmi.summary(pmi)}; LIST, NOTES shows them)")
    if len(msgs) == 1:
        return "\n  ".join(msgs + tail)
    return f"IMPORT {file}: {len(msgs)} bodies\n  " + "\n  ".join(msgs + tail)


def _named_sets_back(p: Processor, bids: list[int], named: list) -> list[str]:
    """Turn the faces, edges and points a STEP file names back into named sets (CM) and wall
    thicknesses, on the bodies just imported. Returns the set names made."""
    m = p.model
    groups: dict[str, tuple[str, list[int]]] = {}
    for sub, text in named:
        kind = {"Face": "FACE", "Edge": "EDGE", "Vertex": "VERTEX"}.get(_shape_kind(sub))
        if kind is None:
            continue
        gid = 0
        for bid in bids:
            try:
                gid = m.find_entity(bid, kind, sub)
                owner = bid
                break
            except Exception:  # noqa: BLE001 - not in this body
                continue
        if not gid:
            continue
        for word in (w.strip() for w in text.split(";")):
            if not word:
                continue
            if word.lower().startswith("thickness ") and kind == "FACE":
                try:
                    m.thickness.setdefault(owner, {})[gid] = float(word.split()[1])
                except ValueError:
                    pass
                continue
            name = "".join(c if c.isalnum() or c == "_" else "_" for c in word)
            g = groups.setdefault(name.upper(), (kind, []))
            if g[0] == kind and gid not in g[1]:
                g[1].append(gid)
            groups.setdefault("~" + name.upper(), (name, []))
    made = []
    for key, (kind, ids) in groups.items():
        if key.startswith("~"):
            continue
        name = groups["~" + key][0]
        m.save_set(name, kind, ids)
        made.append(name)
    return made


def _shape_kind(s) -> str:
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX

    return {TopAbs_FACE: "Face", TopAbs_EDGE: "Edge", TopAbs_VERTEX: "Vertex"}.get(s.ShapeType(), "")


# ---- projects -------------------------------------------------------------------
def _imports_in(p: Processor) -> list[str]:
    """File names that IMPORT commands in the applied history read."""
    files: list[str] = []

    def walk(stmts):
        for st in stmts:
            name = getattr(st, "name", None)
            args = getattr(st, "args", [])
            if name in ("SDXF", "SSVG", "STRACE", "IMAGE") and args and args[0].strip().strip('"').upper() != "CLEAR":
                raw = st.args[0].strip()
                if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]:
                    raw = raw[1:-1]
                if raw not in files:
                    files.append(raw)
            elif name == "BOARD" and args:  # the board file, and its IDF library (given, or the one next to it)
                for raw in [args[0].strip(), *([args[4].strip()] if len(args) > 4 and args[4].strip() else
                                               [os.path.splitext(args[0].strip().strip("\"'"))[0] + ".emp"])]:
                    if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]:
                        raw = raw[1:-1]
                    if raw and raw not in files and (raw == args[0].strip().strip("\"'") or
                                                     os.path.isfile(p.file_map.get(raw, raw))):
                        files.append(raw)
            elif (name == "IMPORT" and len(args) >= 2) or (name == "LIB" and len(args) >= 2
                                                            and args[0].strip().upper() in ("LOAD", "LINK")):
                raw = st.args[1].strip()
                if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]:
                    raw = raw[1:-1]
                if raw not in files:
                    files.append(raw)
            for sub in [getattr(st, "body", None), getattr(st, "orelse", None)] + [b for _, b in getattr(st, "branches", [])]:
                if isinstance(sub, list):
                    walk(sub)

    for e in saved_entries(p):
        if not e.suppressed:
            try:
                walk(parse(e.text))
            except Exception:  # noqa: BLE001 - a broken entry has nothing to save
                pass
    return files


def _link_paths(p: Processor, project: str) -> dict:
    out = dict(p.link_paths)
    for name, lk in p.links.items():
        if lk.copy or not os.path.isfile(lk.path):
            continue  # missing: keep where it was last seen
        full = os.path.abspath(lk.path)
        try:
            rel = os.path.relpath(full, os.path.dirname(os.path.abspath(project)))
        except ValueError:  # another drive on Windows
            rel = ""
        out[name] = {"abs": full, "rel": rel}
    return out


CHAT_KEEP = 200  # assistant messages kept with a project (the newest)
BACKUPS_KEEP = 5  # earlier saves of a project kept in its backups folder (BACKUPS, n changes it)


def save_project(p: Processor, path: str, backup: bool = True) -> int:
    """Write the project zip; returns the number of history entries. The file is written next to the
    project first and put in its place only when complete, so a crash while saving leaves the last
    saved project as it was; with ``backup`` the one it replaces is kept in the backups folder."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".tmp"
    try:
        n = _write_project(p, path, tmp)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    if backup and os.path.isfile(path):
        from .safety_handlers import keep_backup

        keep_backup(p, path)
    os.replace(tmp, path)
    if backup:
        p.saved_script = p.script()
    if backup and p.drawings_auto:
        from .drawsheet_handlers import refresh

        refresh(p)
    return n


def _write_project(p: Processor, path: str, tmp: str) -> int:
    files = {}
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("script.cmd", p.script())
        for i, name in enumerate(_imports_in(p)):
            real = p.file_map.get(name) or p.lib_files.get(name) or name
            if name in p.links:  # a linked part file: keep a copy of what it holds now
                real = p.links[name].path
            if os.path.isfile(real):
                stored = f"files/{i}_{os.path.basename(name)}"
                z.write(real, stored)
                files[name] = stored
        # what each entry remembers: the IDs it handed out and its pick
        # fingerprints, so the reopened model is numbered exactly as it is now
        history = [
            {"text": e.text, "uid": e.uid, "pins": e.pins, "refs": e.refs}
            for e in saved_entries(p)
            if not e.suppressed
        ]
        meta = {
            "version": PROJECT_VERSION,
            "app": "3Dmodeling",
            "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
            "units": p.model.units,
            "entries": len(history),
            "files": files,
            "history": history,
            "view": p.model.view_state(),  # hidden and faded by the view (not history)
            # where each linked part file is, so reopening reads the file itself
            "links": _link_paths(p, path),
        }
        if p.drawings_auto:  # the drawings written again after every rebuild and save
            meta["drawings_auto"] = p.drawings_auto
        if p.note_ends:  # what the ends of each size were on when it was made
            meta["note_ends"] = [[u, n, list(e)] for (u, n), e in p.note_ends.items()]
        if p.config_off:  # steps turned off per configuration, by entry uid
            meta["config_off"] = {k: sorted(v) for k, v in p.config_off.items() if v}
        if p.config:  # the configuration in use (CONFIG/USECONFIG), with its values for the replay
            meta["config"] = {"name": p.config, "values": dict(p.config_values)}
        if p.chat:  # the assistant conversation, kept with the project
            meta["chat"] = [{"who": e.get("who", ""), "text": e.get("text", "")} for e in p.chat[-CHAT_KEEP:]]
        if p.strokes:  # sculpt strokes: their points, by name
            import io

            import numpy as np

            buf = io.BytesIO()
            np.savez_compressed(buf, **{k: np.asarray(v, dtype=np.float32) for k, v in p.strokes.items()})
            z.writestr("strokes.npz", buf.getvalue())
            meta["strokes"] = "strokes.npz"
        if p.taken:  # geometry taken from other parts (TAKE): fingerprints, and copies as BREP text
            meta["taken"] = p.taken
        if p.backups_keep != BACKUPS_KEEP:
            meta["backups_keep"] = p.backups_keep
        kept = _library_materials(p)
        if kept:  # library materials the bodies use, so the project opens the same without that library
            meta["materials"] = kept
        z.writestr("project.json", json.dumps(meta, indent=2))
    return p.cursor


def _same(a, b) -> bool:
    """Two materials alike as the library writes them (colours rounded)."""
    return a is not None and b is not None and a.props() == b.props()


def _library_materials(p: Processor) -> list[dict]:
    """The materials the bodies use (or a step names) that come from the material library (or that an opened
    project brought), as library entries."""
    from ..core import matlib
    from ..core.model import MATERIALS

    lib = {**matlib.library(), **p.model.pinned}
    import re

    words = set(re.findall(r"[A-Z_][A-Z0-9_]*", p.script().upper()))  # a step may name one no body keeps
    used = sorted({b.material.upper() for b in p.model.bodies.values() if b.material} | (words & set(lib)))
    out = []
    for key in used:
        mat = p.model.materials.get(key)
        if mat is not None and key in lib and _same(mat, lib[key]) and not _same(mat, MATERIALS.get(key)):
            out.append(mat.props())
    return out


def open_project(p: Processor, path: str) -> tuple[int, list[str]]:
    """Replace the session with the project. Returns (entries run, errors)."""
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        from .safety_handlers import backups_of

        older = backups_of(path)
        hint = f"; the newest backup is {older[0]} (OPEN it, or BACKUPS lists them)" if older else ""
        raise CommandError(f"OPEN: {path} is not a project file or is damaged ({exc}){hint}") from None
    with z:
        try:
            meta = json.loads(z.read("project.json"))
            script = z.read("script.cmd").decode("utf-8")
        except KeyError as exc:
            raise CommandError(f"OPEN: {path} is missing {exc}") from None
        if meta.get("version", 0) > PROJECT_VERSION:
            raise CommandError("OPEN: this project was saved by a newer version")
        strokes = {}
        if meta.get("strokes"):
            import io

            import numpy as np

            try:
                with np.load(io.BytesIO(z.read(meta["strokes"]))) as data:
                    strokes = {k: data[k].astype(float) for k in data.files}
            except (KeyError, ValueError, OSError) as exc:
                raise CommandError(f"OPEN: the sculpt strokes in {path} cannot be read ({exc})") from None
        tmpdir = tempfile.mkdtemp(prefix="m3d_")
        mapping = {}
        for name, stored in meta.get("files", {}).items():
            z.extract(stored, tmpdir)
            mapping[name] = os.path.join(tmpdir, stored)
    p.reset()
    p.file_map = mapping
    p.strokes = strokes
    p.taken = {str(k).upper(): v for k, v in dict(meta.get("taken", {})).items() if isinstance(v, dict)}
    p.chat = [e for e in meta.get("chat", []) if isinstance(e, dict) and isinstance(e.get("text"), str)]
    p.link_paths = dict(meta.get("links", {}))
    p.project_dir = os.path.dirname(os.path.abspath(path))
    p.drawings_auto = str(meta.get("drawings_auto", "") or "")
    p.backups_keep = int(meta.get("backups_keep", BACKUPS_KEEP))
    p.note_ends = {(int(u), int(n)): tuple(e) for u, n, e in meta.get("note_ends", []) if len(e) == 2}
    p.config_off = {str(k).upper(): {int(u) for u in v} for k, v in dict(meta.get("config_off", {})).items()}
    cfg = meta.get("config")
    if isinstance(cfg, dict) and cfg.get("name"):
        p.config = str(cfg["name"]).upper()
        p.config_values = {str(k).upper(): v for k, v in dict(cfg.get("values", {})).items()}
    pins = {}
    for d in meta.get("materials", []) or []:
        from ..core import matlib

        try:
            mat = matlib.from_dict(d)
        except matlib.LibraryError:
            continue
        pins[mat.name] = mat
    if pins:
        p.model.pinned = pins
        p.model.materials.update(pins)
        p._snaps[0] = p._state()
    results = p.run_script(script, meta.get("history"))
    p.model.set_view_state(meta.get("view"))
    p.saved_script = p.script()
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
    p.project_dir = os.path.dirname(os.path.abspath(file))
    said = f"saved {n} entr{'y' if n == 1 else 'ies'} to {file}"
    if p.sketch_edit is not None:
        said += (f" (sketch {p.sketch_edit.name.lower()} is still being edited: saved as it was before "
                 "the edit; ENDSKETCH and SAVE again to keep the change)")
    return said


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


@command("NEW", Arg("template", Text, "", "a template to start from: part, assembly, sheet_metal, drawing, or "
                                          "one of your own (TEMPLATE lists them)"), session=True,
         help="Start an empty session (unsaved work is lost; UNDO cannot bring it back). NEW, part starts from "
              "a template instead: its steps (units, layers, parameters, title block ...) become the first "
              "history entries.")
def new(p: Processor, template=""):
    name = (template or "").strip().strip('"')
    if not name:
        p.reset()
        p.project_path = None
        return "new session"
    from . import template_handlers as th

    try:
        t = th.find(name)
    except CommandError as exc:
        raise CommandError(f"NEW: {exc}") from None
    results = th.start_from(p, t)
    return f"new {t.title.lower().removeprefix('new ')} from the template {t.name}: {len(results)} steps ({th._setup_text(t.sets())})"
