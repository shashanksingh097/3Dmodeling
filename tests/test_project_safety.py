"""Project safety (PLAN item 62): projects saved by earlier releases open and give the same model;
backups of earlier saves; a crash while saving leaves the last save whole; a damaged file names its
backup; outside files listed and relinked; a check before sharing."""

import glob
import json
import os
import subprocess
import sys
import textwrap

import pytest

from modeler.commands import Processor

HERE = os.path.dirname(__file__)
OLD = sorted(glob.glob(os.path.join(HERE, "old_projects", "sample-*.json")))


def ok(p, text):
    res = p.run_script(text)
    bad = [r for r in res if not r.ok]
    assert not bad, f"{bad[0].line}: {bad[0].message}"
    return res[-1]


# ---- projects from earlier releases ----------------------------------------------------------------

@pytest.mark.parametrize("meta", OLD, ids=[os.path.basename(f)[7:-5] for f in OLD])
def test_projects_from_earlier_releases_open_the_same(meta, tmp_path):
    want = json.load(open(meta, encoding="utf-8"))  # noqa: SIM115
    project = meta[:-5] + ".m3d"
    p = Processor()
    msg = ok(p, f'OPEN, "{project}"').message
    assert f"{want['entries']} entries" in msg
    m = p.model
    vols = sorted(round(p.evaluate(f"VOL({b})"), 6) for b in m.bodies if b not in m.hidden)
    assert vols == pytest.approx(want["volumes"], rel=1e-9)
    assert {n: p.evaluate(f"VOL({n})") for n in want["named"]} == pytest.approx(want["named"], rel=1e-9)
    # and it still edits: the parameters drive the model
    ok(p, 'HIST, EDIT, 1, "W = 80"')
    assert p.evaluate("VOL(base)") == pytest.approx(want["named"]["base"] + 20 * 40 * 15)


def test_there_is_a_project_from_every_release():
    assert {os.path.basename(f) for f in OLD} >= {"sample-v0.1.0.json", "sample-v0.3.0.json",
                                                   "sample-v0.4.0.json", "sample-v0.5.0.json",
                                                   "sample-v0.6.0.json", "sample-v0.7.0.json"}


# ---- backups and saving safely ----------------------------------------------------------------------

def test_each_save_keeps_the_one_it_replaces(tmp_path):
    p = Processor()
    path = str(tmp_path / "bracket.m3d")
    ok(p, f'BLOCK, 0,0,0, 10,10,10\nSAVE, "{path}"')
    assert "no backups" in p.run("BACKUPS").message
    for i in range(7):
        os.utime(path, (1_700_000_000 + 100 * i, 1_700_000_000 + 100 * i))  # each save at its own time
        ok(p, f"CYL, {20 * i}, 0, 0, 2, 5\nSAVE")
    files = sorted(os.listdir(tmp_path / "bracket-backups"))
    assert len(files) == 5 and all(f.startswith("bracket-") and f.endswith(".m3d") for f in files)
    assert "5 backups of bracket.m3d (keeping 5)" in p.run("BACKUPS").message
    # the newest backup is the save before the last one
    q = Processor()
    newest = p.run("BACKUPS").message.splitlines()[1].split()[-1]
    ok(q, f'OPEN, "{newest}"')
    assert len(q.model.bodies) == len(p.model.bodies) - 1
    assert "keeping the last 2 saves" in p.run("BACKUPS, 2").message
    ok(p, "SAVE")
    assert len(os.listdir(tmp_path / "bracket-backups")) == 2


def test_a_crash_while_saving_leaves_the_last_save_whole(tmp_path, monkeypatch):
    from modeler.commands import project_handlers as ph

    p = Processor()
    path = str(tmp_path / "a.m3d")
    ok(p, f'BLOCK, 0,0,0, 10,10,10\nSAVE, "{path}"')
    before = open(path, "rb").read()  # noqa: SIM115
    ok(p, "SPHERE, 30, 0, 0, 5")

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(ph, "_write_project", boom)
    assert "disk full" in p.run("SAVE").message
    assert open(path, "rb").read() == before and not os.path.exists(path + ".tmp")  # noqa: SIM115


def test_a_damaged_project_names_its_newest_backup(tmp_path):
    p = Processor()
    path = str(tmp_path / "a.m3d")
    ok(p, f'BLOCK, 0,0,0, 10,10,10\nSAVE, "{path}"\nSPHERE, 30,0,0, 5\nSAVE')
    with open(path, "r+b") as fh:  # half the file is lost
        fh.truncate(os.path.getsize(path) // 2)
    msg = Processor().run(f'OPEN, "{path}"').message
    assert "damaged" in msg and "the newest backup is" in msg and "a-backups" in msg


def test_the_autosave_brings_work_back_after_a_crash(tmp_path):
    """A window that dies without closing (os._exit) leaves its autosave; the next start offers it."""
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        pytest.skip("no X display (run under xvfb-run)")
    auto = str(tmp_path / "autosave.m3d")
    script = textwrap.dedent(f"""
        import os
        from PySide6.QtWidgets import QApplication
        from modeler.gui.main_window import MainWindow
        app = QApplication([])
        w = MainWindow(autosave={auto!r})
        for line in ("W = 40", "BLOCK, 0,0,0, W, 20, 10", "CYL, 10,10,-1, 3, 12", "SUBTRACT, 1, 2"):
            assert w.execute(line).ok
        w.autosave_now()
        os._exit(3)  # a crash: nothing is closed or saved
    """)
    env = dict(os.environ, MODELER_AUTOSAVE=auto, PYTHONPATH=os.path.dirname(HERE))
    r = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=300, check=False)
    assert r.returncode == 3, r.stderr[-2000:]
    assert os.path.isfile(auto)
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from modeler.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow(autosave=auto, settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    try:
        assert w.processor.autosave_path and w.processor.autosave_path.endswith("autosave-previous.m3d")
        assert w.execute("OPEN, AUTOSAVE").ok
        assert w.processor.evaluate("VOL(LAST)") == pytest.approx(40 * 20 * 10 - 3.14159265 * 9 * 10, rel=1e-6)
    finally:
        w.shell.ask_unsaved = lambda *_: "discard"
        w.close()
        app.processEvents()


# ---- outside files ----------------------------------------------------------------------------------

def test_files_are_listed_and_a_moved_one_relinked(tmp_path):
    part = tmp_path / "parts" / "peg.cmd"
    part.parent.mkdir()
    part.write_text("*PART, peg, D=6\n  CYL, 0,0,0, D/2, 20\n*ENDPART\n", encoding="utf-8")
    p = Processor()
    ok(p, f'LIB, LINK, "{part}"\nINST, peg, 0,0,0')
    rows = json.loads(p.run("FILES, JSON").message)["files"]
    assert rows[0]["command"] == "LIB LINK" and rows[0]["found"] == str(part) and not rows[0]["missing"]
    path = str(tmp_path / "proj" / "a.m3d")
    ok(p, f'SAVE, "{path}"')
    # the part file moves (and grows): the project uses its copy until it is relinked
    moved = tmp_path / "elsewhere" / "peg.cmd"
    moved.parent.mkdir()
    moved.write_text("*PART, peg, D=6\n  CYL, 0,0,0, D/2, 30\n*ENDPART\n", encoding="utf-8")
    os.remove(part)
    q = Processor()
    q.run(f'OPEN, "{path}"')
    assert "MISSING: the copy saved in the project is used" in q.run("FILES").message
    msg = q.run(f'RELINK, "{part}", "{moved}"').message
    assert "now read from" in msg
    assert q.evaluate("VOL(1)") == pytest.approx(3.14159265 * 9 * 30, rel=1e-6)
    assert "followed at" in q.run("FILES").message
    assert "reads no file" in q.run('RELINK, "nope.cmd", "x"').message


def test_relink_an_imported_file_to_a_newer_version(tmp_path):
    a, b = str(tmp_path / "v1.brep"), str(tmp_path / "v2.brep")
    q = Processor()
    ok(q, f'BLOCK, 0,0,0, 10,10,10\nEXPORT, BREP, "{a}"\nNEW\nBLOCK, 0,0,0, 20,10,10\nEXPORT, BREP, "{b}"')
    p = Processor()
    ok(p, f'IMPORT, BREP, "{a}"\nMOVE, 1, 5, 0, 0')
    assert p.evaluate("VOL(1)") == pytest.approx(1000)
    ok(p, f'RELINK, "{a}", "{b}"')
    assert p.evaluate("VOL(1)") == pytest.approx(2000)


# ---- before sharing ----------------------------------------------------------------------------------

def test_sharecheck(tmp_path):
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 10,10,10\nPROPERTY, AUTHOR, A. Person")
    d = json.loads(p.run("SHARECHECK, JSON").message)
    assert not d["ready"] and "never been saved" in d["problems"][0]
    path = str(tmp_path / "a.m3d")
    ok(p, f'SAVE, "{path}"')
    assert p.run("SHARECHECK").message.startswith("ready to share")
    assert "author 'A. Person'" in p.run("SHARECHECK").message
    ok(p, "SPHERE, 30, 0, 0, 5")
    assert "changes since the last SAVE" in p.run("SHARECHECK").message
    p.chat = [{"who": "you", "text": "hello"}]
    ok(p, "SAVE")
    msg = p.run("SHARECHECK").message
    assert msg.startswith("ready to share") and "assistant conversation (1 message)" in msg
