"""Keeping projects safe: backups of earlier saves (BACKUPS), the outside files a project uses and
pointing it at a moved one (FILES, RELINK), and a check before sharing (SHARECHECK).

Backups: every SAVE over a project first moves the one it replaces into ``<name>-backups/`` next
to it, named by the time it was saved; the newest ``BACKUPS_KEEP`` (5, or ``BACKUPS, n``) are kept.
The autosave makes none. A damaged project file names its newest backup when it will not open.

A project keeps a copy of every file it imports or links, so it opens when the files are gone; a
linked part file is followed while it is there. ``FILES`` lists them with where each was found;
``RELINK, name, new place`` points the project at a file that moved (or at a newer version of an
imported file) and rebuilds from the first step that reads it.
"""

from __future__ import annotations

import os
import shutil
import time

from ..lang.script import parse
from .processor import Arg, CommandError, Path, Processor, Text, command

# ---- backups -----------------------------------------------------------------------------------------

def backup_dir(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    return os.path.join(os.path.dirname(os.path.abspath(path)), f"{stem}-backups")


def backups_of(path: str) -> list[str]:
    """The backups of a project, newest first."""
    d = backup_dir(path)
    if not os.path.isdir(d):
        return []
    stem = os.path.splitext(os.path.basename(path))[0]
    files = [os.path.join(d, f) for f in os.listdir(d) if f.startswith(stem + "-") and f.endswith(".m3d")]
    return sorted(files, key=lambda f: (os.path.getmtime(f), f), reverse=True)


def keep_backup(p: Processor, path: str) -> str | None:
    """Move the project about to be replaced into its backups folder; drop the oldest beyond the limit."""
    keep = p.backups_keep
    if keep <= 0:
        return None
    d = backup_dir(path)
    os.makedirs(d, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    when = time.strftime("%Y%m%d-%H%M%S", time.localtime(os.path.getmtime(path)))
    target = os.path.join(d, f"{stem}-{when}.m3d")
    k = 2
    while os.path.exists(target):
        target = os.path.join(d, f"{stem}-{when}-{k}.m3d")
        k += 1
    shutil.copy2(path, target)
    for old in backups_of(path)[keep:]:
        try:
            os.remove(old)
        except OSError:
            pass
    return target


@command(
    "BACKUPS",
    Arg("keep", str, "", "how many earlier saves to keep (0: none); none: list them"),
    session=True,
    help="The backups of the project: every SAVE over it first keeps the one it replaces in <name>-backups next "
         "to it (the newest 5). BACKUPS lists them, newest first; BACKUPS, 10 keeps ten (saved with the project); "
         "OPEN one to go back to it.",
)
def backups(p: Processor, keep):
    if keep:
        try:
            n = int(keep)
        except ValueError:
            raise CommandError("BACKUPS: give how many to keep, e.g. BACKUPS, 10") from None
        if n < 0:
            raise CommandError("BACKUPS: the number cannot be negative")
        p.backups_keep = n
        return f"keeping the last {n} save{'s' if n != 1 else ''}" if n else "no backups will be kept"
    if not p.project_path:
        return "the project is not saved yet, so it has no backups (SAVE, name.m3d)"
    files = backups_of(p.project_path)
    if not files:
        return f"no backups of {os.path.basename(p.project_path)} yet (one is kept each time you save over it)"
    lines = [f"{len(files)} backup{'s' if len(files) != 1 else ''} of {os.path.basename(p.project_path)} "
             f"(keeping {p.backups_keep}), newest first:"]
    for f in files:
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(f)))
        lines.append(f"  {when}  {f}")
    return "\n".join(lines)


# ---- the outside files a project uses -----------------------------------------------------------------

def _reads(p: Processor) -> list[tuple[str, str, int]]:
    """(name as written, command, first step) for every outside file the history reads."""
    out: dict[str, tuple[str, str, int]] = {}

    def walk(stmts, step):
        for st in stmts:
            name = getattr(st, "name", None)
            args = getattr(st, "args", []) or []
            raw = None
            if name in ("SDXF", "STRACE", "IMAGE") and args and args[0].strip().strip('"').upper() != "CLEAR":
                raw = args[0]
            elif name == "IMPORT" and len(args) >= 2:
                raw = args[1]
            elif name == "LIB" and len(args) >= 2 and args[0].strip().upper() in ("LOAD", "LINK"):
                raw = args[1]
                name = "LIB " + args[0].strip().upper()
            if raw is not None:
                raw = raw.strip()
                if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]:
                    raw = raw[1:-1]
                out.setdefault(raw, (raw, name, step))
            for sub in [getattr(st, "body", None), getattr(st, "orelse", None)] + \
                    [b for _, b in getattr(st, "branches", [])]:
                if isinstance(sub, list):
                    walk(sub, step)

    for i, e in enumerate(p.history[: p.cursor]):
        if e.suppressed:
            continue
        try:
            walk(parse(e.text), i + 1)
        except Exception:  # noqa: BLE001 - a step that does not parse reads nothing
            pass
    return list(out.values())


def files(p: Processor) -> list[dict]:
    from .part_handlers import link_candidates, resolve_library

    rows = []
    for name, cmd, step in _reads(p):
        row = {"name": name, "command": cmd, "step": step, "copy": name in p.file_map}
        if cmd == "LIB LINK":
            found = next((c for c in link_candidates(p, name) if os.path.isfile(c)), "")
            row.update({"follows": True, "found": found, "missing": not found})
        elif cmd == "LIB LOAD":
            try:
                found = resolve_library(p, name)
            except CommandError:
                found = ""
            row.update({"follows": False, "found": found if os.path.isfile(found) else "",
                        "missing": not os.path.isfile(found)})
        else:
            here = p.file_map.get(name, name)
            if not os.path.isabs(here) and p.project_dir and not os.path.isfile(here):
                here = os.path.join(p.project_dir, here)
            row.update({"follows": False, "found": here if os.path.isfile(here) else "",
                        "missing": not os.path.isfile(here)})
        row["from_copy"] = bool(row["found"]) and row["found"] == p.file_map.get(name) and cmd != "LIB LINK" \
            and not getattr(p, "_relinked", {}).get(name)
        rows.append(row)
    return rows


def files_text(rows: list[dict]) -> str:
    if not rows:
        return "the project reads no outside files"
    lines = []
    for r in rows:
        if r["missing"]:
            state = ("MISSING: the copy saved in the project is used" if r["copy"]
                     else "MISSING and the project has no copy: RELINK it")
        elif r["follows"]:
            state = f"followed at {r['found']}"
        elif r["from_copy"]:
            state = "read from the copy saved in the project"
        else:
            state = f"read from {r['found']}"
        lines.append(f"  {r['name']} ({r['command'].lower()}, step {r['step']}): {state}")
    missing = sum(1 for r in rows if r["missing"])
    head = f"{len(rows)} outside file{'s' if len(rows) != 1 else ''}" + (f", {missing} missing:" if missing else ":")
    return "\n".join([head, *lines])


@command(
    "FILES",
    Arg("fmt", str, "TEXT", "TEXT or JSON"),
    logged=False,
    help="The outside files the project reads (IMPORT, LIB, SDXF, IMAGE ...): the step that reads each, where it "
         "was found, and which are missing (the copy saved in the project is used then). RELINK points the "
         "project at one that moved.",
)
def files_cmd(p: Processor, fmt):
    rows = files(p)
    p.give_report("files", {"files": rows})
    if fmt == "JSON":
        import json

        return json.dumps({"files": rows})
    return files_text(rows)


@command(
    "RELINK",
    Arg("name", Text, help="the file as the history names it (FILES lists them)"),
    Arg("file", Path, help="where it is now"),
    session=True,
    help="Point the project at a file that moved, or at a newer version of an imported file: RELINK, "
         "bracket.step, \"D:/new/bracket.step\". The steps that read it run again; the history keeps the old "
         "name, and the next SAVE keeps a copy of the new file.",
)
def relink(p: Processor, name, file):
    rows = {r["name"]: r for r in files(p)}
    if name not in rows:
        known = ", ".join(rows) or "none"
        raise CommandError(f"RELINK: the project reads no file {name!r} (it reads: {known})")
    if not os.path.isfile(file):
        raise CommandError(f"RELINK: no such file: {file}")
    full = os.path.abspath(file)
    r = rows[name]
    if r["command"] == "LIB LINK":
        rel = ""
        if p.project_dir:
            try:
                rel = os.path.relpath(full, p.project_dir)
            except ValueError:
                rel = ""
        p.link_paths = {**p.link_paths, name: {"abs": full, "rel": rel}}
    else:
        p.file_map = {**p.file_map, name: full}
        p._relinked = {**getattr(p, "_relinked", {}), name: full}
    msg = p.rebuild(r["step"] - 1, skip=False)
    return f"{name} now read from {full}\n{msg}"


# ---- before sharing -----------------------------------------------------------------------------------

def share_check(p: Processor) -> dict:
    from .take_handlers import depends

    out: dict = {"problems": [], "notes": []}
    probs, notes = out["problems"], out["notes"]
    if not p.project_path:
        probs.append("the project has never been saved: SAVE it first, then share the .m3d file")
    elif p.saved_script != p.script():
        probs.append("there are changes since the last SAVE: they would not be in the shared file")
    failed = [(i + 1, e) for i, e in enumerate(p.history[: p.cursor]) if not e.ok and not e.suppressed]
    for n, e in failed:
        probs.append(f"step {n} fails: {e.message.splitlines()[0] if e.message else e.label}")
    warned = [(i + 1, e) for i, e in enumerate(p.history[: p.cursor]) if e.ok and e.warning]
    if warned:
        notes.append(f"{len(warned)} step{'s' if len(warned) != 1 else ''} with a warning (first: step "
                     f"{warned[0][0]}: {warned[0][1].warning.splitlines()[0]})")
    for r in files(p):
        if r["missing"] and not r["copy"]:
            probs.append(f"{r['name']} is missing and the project has no copy of it: the model cannot be rebuilt "
                         "from the shared file (RELINK it)")
        elif r["command"] == "LIB LINK" and r["found"]:
            inside = p.project_dir and os.path.abspath(r["found"]).startswith(os.path.abspath(p.project_dir) + os.sep)
            if not inside:
                notes.append(f"{r['name']} is linked from outside the project folder: on another computer the copy "
                             "saved in the project is used until the file is there too")
    d = depends(p)
    for b in d["broken"]:
        where = f"step {b['step']}" if "step" in b else f"body {b['body']}"
        if "missing" not in b["why"]:
            probs.append(f"broken link at {where}: {b['why']}")
    for c in d["loops"]:
        probs.append("parts place each other in a loop: " + " -> ".join(c))
    if p.chat:
        notes.append(f"the assistant conversation ({len(p.chat)} message{'s' if len(p.chat) != 1 else ''}) is saved "
                     "in the project and goes with it (New chat in the assistant panel, then SAVE, leaves it out)")
    private = {k: v for k, v in p.model.properties.items() if k.upper() in ("AUTHOR", "COMPANY")}
    if private:
        notes.append("the title block names " + ", ".join(f"{k.lower()} {v!r}" for k, v in private.items()))
    paths = [lp.get("abs") for lp in p.link_paths.values() if lp.get("abs")]
    if p.drawings_auto:
        paths.append(p.drawings_auto)
    home = os.path.expanduser("~")
    personal = sorted({x for x in paths if x and home and home != "/" and x.startswith(home)})
    if personal:
        notes.append("full paths in your own folders are saved in the project: " + ", ".join(personal[:3])
                     + (" ..." if len(personal) > 3 else ""))
    out["ready"] = not probs
    return out


@command(
    "SHARECHECK",
    Arg("fmt", str, "TEXT", "TEXT or JSON"),
    logged=False,
    help="A check before sending the project to someone: unsaved changes, failing steps, missing files with no "
         "copy, broken links, part loops; and things to know: warnings, files linked from outside the project "
         "folder, the saved assistant conversation, names in the title block, full paths in your own folders.",
)
def sharecheck(p: Processor, fmt):
    d = share_check(p)
    p.give_report("sharecheck", d)
    if fmt == "JSON":
        import json

        return json.dumps(d)
    lines = ["ready to share" if d["ready"] else f"{len(d['problems'])} problem{'s' if len(d['problems']) != 1 else ''} "
             "to fix before sharing:"]
    lines += [f"  - {x}" for x in d["problems"]]
    if d["notes"]:
        lines.append("good to know:")
        lines += [f"  - {x}" for x in d["notes"]]
    return "\n".join(lines)
