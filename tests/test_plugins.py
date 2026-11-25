"""PLAN item 74: plug-ins, people's own commands in Python."""

import os
import shutil

import pytest

from modeler import plugins
from modeler.commands import Processor
from modeler.commands.processor import REGISTRY

SNEAK = '''"""Changes the model behind the commands' back."""
from modeler.plugins import Arg, BodyRef, plugin_command


@plugin_command("SNEAK", Arg("b", BodyRef))
def sneak(api, b):
    api.run("BLOCK, 100,0,0, 5,5,5")
    m = api._p.model
    m.bodies.pop(next(iter(m.bodies)))
    return "done"
'''

READER = '''"""Reads only."""
from modeler.plugins import Arg, BodyRef, plugin_command


@plugin_command("VOLREPORT", Arg("b", BodyRef), logged=False)
def volreport(api, b):
    return f"volume {api.value(f'VOL({b})'):.0f}"
'''


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


@pytest.fixture
def folder(tmp_path):
    shutil.copy(plugins.EXAMPLE, tmp_path / "bolt_ring.py")
    (tmp_path / "sneak.py").write_text(SNEAK, encoding="utf-8")
    (tmp_path / "reader.py").write_text(READER, encoding="utf-8")
    (tmp_path / "broken.py").write_text("x = (\n", encoding="utf-8")
    (tmp_path / "_helper.py").write_text("raise SystemExit", encoding="utf-8")  # not a plug-in: left alone
    plugins.configure([])
    plugins.load_all(str(tmp_path))
    yield tmp_path
    plugins.configure([])
    plugins.unload()


def test_loading(folder):
    found = {pl.name: pl for pl in plugins.plugins()}
    assert set(found) == {"bolt_ring", "sneak", "reader", "broken"}
    assert found["bolt_ring"].commands == ["BOLTRING"] and "Bolt ring" in found["bolt_ring"].about
    assert "SyntaxError" in found["broken"].problem and "line 1" in found["broken"].problem
    assert plugins.commands() == ["BOLTRING", "SNEAK", "VOLREPORT"]
    assert "[plug-in bolt_ring]" in REGISTRY["BOLTRING"].help


def test_a_plugin_command_is_one_history_step(folder):
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 60,60,10\nNAME, LAST, plate")
    r = p.run("BOLTRING, plate, 6, 5, 20")
    assert r.ok, r.message
    assert len(p.history) == 3
    ok(p, "FEATURES, plate")
    assert p.evaluate("HOLES(plate, 5, 1)") == 6
    ok(p, "UNDO")
    assert p.evaluate("HOLES(plate, 5, 1)") == 0
    ok(p, "REDO")
    assert p.evaluate("HOLES(plate, 5, 1)") == 6


def test_unnamed_body_and_rebuild(folder):
    p = Processor()
    ok(p, "W = 60\nBLOCK, 0,0,0, W,W,10\nBOLTRING, LAST, 4, 4, 15")
    assert p.evaluate("HOLES(LAST, 4, 1)") == 4
    ok(p, 'HIST, EDIT, 1, "W = 80"')  # the rebuild runs the plug-in again
    assert p.evaluate("BBOX(LAST).dx") == 80 and p.run("ASSERT, HOLES(LAST, 4, 1), EQ, 4").ok


def test_errors_are_named(folder):
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 20,20,5")
    r = p.run("BOLTRING, LAST, 6, 5, 50")
    assert not r.ok and "does not fit" in r.message and r.message.startswith("BOLTRING")
    assert len(p.history) == 1


def test_the_check_undoes_a_change_made_without_commands(folder):
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 20,20,5")
    r = p.run("SNEAK, 1")
    assert not r.ok and "without using commands" in r.message and "sneak" in r.message
    assert list(p.model.bodies) == [1] and len(p.history) == 1


def test_query_plugin_and_turning_off(folder):
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 10,10,10")
    r = p.run("VOLREPORT, 1")
    assert r.ok and "volume 1000" in r.message and len(p.history) == 1
    plugins.configure(["reader"])
    plugins.load_all(str(folder))
    assert "VOLREPORT" not in REGISTRY
    assert not next(pl for pl in plugins.plugins() if pl.name == "reader").enabled


def test_plugins_command_and_reload(folder):
    os.environ["MODELER_PLUGINS_HOME"], old = str(folder), os.environ.get("MODELER_PLUGINS_HOME")
    try:
        p = Processor()
        r = p.run("PLUGINS")
        assert r.ok and "bolt_ring: BOLTRING" in r.message and "broken: not loaded" in r.message
        assert {x["name"] for x in r.report["plugins"]} == {"bolt_ring", "sneak", "reader", "broken"}
        (folder / "broken.py").write_text(READER.replace("VOLREPORT", "AREAREPORT"), encoding="utf-8")
        r = p.run("PLUGINS, RELOAD")
        assert "broken: AREAREPORT" in r.message and "AREAREPORT" in REGISTRY
    finally:
        os.environ["MODELER_PLUGINS_HOME"] = old or ""


def test_skill_and_form_for_each_plugin(folder):
    from modeler.ai import skills as sk
    from modeler.gui import forms

    got = sk.discover()
    s = got["plugin-bolt-ring"]
    assert s.source == "plug-in" and s.commands == ["BOLTRING"] and "`n`: a whole number, default 6" in s.body
    sp = forms.spec("BOLTRING")
    assert sp.category == forms.PLUGIN_CATEGORY and [f.key for f in sp.variants[0].fields][:2] == ["b", "n"]
    assert ("Plug-ins", ("BOLTRING", "SNEAK", "VOLREPORT")) in forms.categories()
    plugins.unload()
    assert "plugin-bolt-ring" not in sk.discover() and "BOLTRING" not in forms.specs()


def test_name_clash_and_bad_arguments(tmp_path):
    (tmp_path / "clash.py").write_text('from modeler.plugins import plugin_command\n'
                                       '@plugin_command("BLOCK")\ndef f(api):\n    return ""\n', encoding="utf-8")
    (tmp_path / "badarg.py").write_text('from modeler.plugins import Arg, plugin_command\n'
                                        '@plugin_command("ODD", Arg("x", list))\ndef f(api, x):\n    return ""\n',
                                        encoding="utf-8")
    plugins.load_all(str(tmp_path))
    try:
        found = {pl.name: pl for pl in plugins.plugins()}
        assert "BLOCK is already a command" in found["clash"].problem
        assert "Arg of float" in found["badarg"].problem
        assert REGISTRY["BLOCK"].fn.__module__.startswith("modeler.commands")
    finally:
        plugins.unload()


def test_example_is_added(tmp_path):
    path = plugins.add_example(str(tmp_path / "new"))
    assert os.path.isfile(path) and path.endswith("bolt_ring.py")
