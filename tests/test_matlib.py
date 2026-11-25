"""PLAN item 102: the material library every project shares (core/matlib.py, MATLIB)."""

import json
import os

import pytest

from modeler.commands.processor import Processor
from modeler.core import matlib


@pytest.fixture()
def lib(tmp_path, monkeypatch):
    f = tmp_path / "materials.json"
    monkeypatch.setenv("MODELER_MATERIALS", str(f))
    return f


def run(p, line):
    r = p.run(line)
    assert r.ok, r.message
    return r


def test_set_show_and_file(lib):
    p = Processor()
    r = run(p, 'MATLIB, SET, AL6061, density=2700 E=68900 nu=0.33 yield=276 k=167 cte=23.6 '
               'look=ALUMINIUM shiny=yes color=GREY note="6061-T6"')
    assert "added to" in r.message
    data = json.loads(lib.read_text())
    entry = data["materials"][0]
    assert entry["name"] == "AL6061" and entry["E_MPa"] == 68900 and entry["note"] == "6061-T6"
    assert p.reports["MATLIB"]["yield_MPa"] == 276
    # a second session (another project) sees it
    q = Processor()
    assert "AL6061" in q.model.materials
    run(q, "MATLIB, SHOW, AL6061")
    assert q.reports["MATLIB"]["source"] == "library"
    run(q, "MATLIB, LIST")
    names = [m["name"] for m in q.reports["MATLIB"]["materials"]]
    assert "STEEL" in names and "AL6061" in names
    run(q, "MATLIB, FILE")
    assert q.reports["MATLIB"]["file"] == str(lib)


def test_bad_values_are_refused(lib):
    p = Processor()
    assert not p.run("MATLIB, SET, X1, E=70000").ok  # no density
    assert not p.run("MATLIB, SET, X1, density=-3").ok
    assert not p.run("MATLIB, SET, X1, density=100 nu=0.7").ok
    assert not p.run("MATLIB, SET, X1, density=100 look=NEON").ok
    assert not p.run("MATLIB, SET, X1, density=100 colour").ok
    assert not p.run("MATLIB, DELETE, STEEL").ok  # built in, not in the library
    assert not lib.exists()


def test_masses_stress_and_builtin_change(lib):
    p = Processor()
    run(p, "BLOCK, 0, 0, 0, 100, 20, 10")
    run(p, "MATLIB, SET, FOAM, density=30")
    run(p, "MATERIAL, 1, FOAM")
    run(p, "MASSPROP, 1")
    rep = p.reports["MASSPROP"]
    assert rep["mass_kg"] == pytest.approx(20000e-9 * 30)
    assert rep["materials"]["FOAM"]["density"] == 30
    # no stiffness: STRESS says what to add
    r = p.run('STRESS, 1, "1", "2", FORCE, 0, 0, -100')
    assert not r.ok and "MATLIB, SET, FOAM" in r.message
    # your own steel for every project: only the yield changes, the rest stays built in
    run(p, "MATLIB, SET, STEEL, yield=355")
    assert p.model.materials["STEEL"].yield_ == 355 and p.model.materials["STEEL"].E == 200000
    run(p, "MATERIAL, 1, STEEL")
    run(p, 'STRESS, 1, "1", "2", FORCE, 0, 0, -100')
    assert p.reports["STRESS"]["yield_MPa"] == 355
    run(p, "MATLIB, DELETE, STEEL")
    assert p.model.materials["STEEL"].yield_ == 250


def test_change_reaches_undo_and_rebuild(lib):
    p = Processor()
    run(p, "BLOCK, 0, 0, 0, 10, 10, 10")
    run(p, "MATLIB, SET, CORK, density=240")
    run(p, "MATERIAL, 1, CORK")
    run(p, "MATLIB, SET, CORK, density=120")
    run(p, "UNDO")
    run(p, "REDO")
    assert p.model.materials["CORK"].density == 120
    p.rebuild(0)
    assert p.model.materials["CORK"].density == 120


def test_project_keeps_library_materials(lib, tmp_path, monkeypatch):
    p = Processor()
    run(p, "BLOCK, 0, 0, 0, 10, 10, 10")
    run(p, "MATLIB, SET, CORK, density=240 E=20 nu=0.1 yield=1")
    run(p, "MATERIAL, 1, CORK")
    f = str(tmp_path / "cork.m3d")
    run(p, f"SAVE, {f}")
    # another computer: an empty library
    monkeypatch.setenv("MODELER_MATERIALS", str(tmp_path / "other" / "materials.json"))
    q = Processor()
    assert "CORK" not in q.model.materials
    run(q, f"OPEN, {f}")
    assert q.model.materials["CORK"].density == 240
    assert q.model.body(1).material == "CORK"
    run(q, "MATLIB, SHOW, CORK")
    assert q.reports["MATLIB"]["source"] == "kept with the project"
    run(q, "MATLIB, KEEP, CORK")
    assert "CORK" in matlib.read()


def test_broken_file_is_named(lib):
    lib.write_text("{not json")
    p = Processor()
    assert "STEEL" in p.model.materials  # the built-in ones still work
    r = p.run("MATLIB")
    assert not r.ok and "cannot be read" in r.message
    assert p.run("MATLIB, FILE").ok


def test_render_look_and_form(lib):
    from modeler.viewport.nice_render import _look

    p = Processor()
    run(p, "MATLIB, SET, GOLDISH, density=19300 look=GOLD shiny=yes")
    assert _look(p.model, "GOLDISH") == ("GOLD", True)
    assert _look(p.model, "steel") == ("STEEL", True)
    try:
        from modeler.gui import forms
        from modeler.commands.processor import REGISTRY
    except ImportError:
        pytest.skip("no Qt here")
    spec = REGISTRY["MATERIAL"]
    arg = next(a for a in spec.args if a.name == "name")
    assert "GOLDISH" in forms._choices("MATERIAL", arg)


def test_materials_window(lib):
    try:
        from PySide6.QtWidgets import QApplication

        from modeler.gui.main_window import MainWindow
    except ImportError:
        pytest.skip("no Qt here")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])  # noqa: F841
    win = MainWindow()
    try:
        win.execute("MATLIB, SET, CORK, density=240")
        dlg = win.open_materials()
        keys = [dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount())]
        assert "CORK" in keys and "STEEL" in keys
        r = keys.index("CORK")
        dlg.table.item(r, 2).setText("25")  # stiffness
        assert win.processor.model.materials["CORK"].E == 25
        assert matlib.read()["CORK"].E == 25
        dlg.close()
    finally:
        win.close()
