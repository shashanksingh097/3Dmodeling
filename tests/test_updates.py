"""PLAN item 117: the update check (opt-in) and What's new."""

import io
import json
import os
import sys
import urllib.error

import pytest

from modeler import __version__, updates
from modeler.commands import Processor

GUI = pytest.mark.skipif(os.environ.get("MODELER_GUI_TESTS") == "0" or
                         (sys.platform.startswith("linux") and not os.environ.get("DISPLAY")), reason="no display")


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(tag="v99.0.0", body="- everything is better"):
    def open_(req, timeout=0):
        assert "releases/latest" in req.full_url
        assert req.get_header("User-agent") == "3Dmodeling-update-check"  # nothing about the user
        return _Resp(json.dumps({"tag_name": tag, "html_url": "https://example.invalid/r", "body": body,
                                 "published_at": "2026-12-01T00:00:00Z"}).encode())
    return open_


def test_versions_compare():
    assert updates.parse("v0.6.0") == (0, 6, 0)
    assert updates.is_newer("0.10.0", "0.9.3")
    assert updates.is_newer("v1.0", "0.9.9")
    assert not updates.is_newer("0.6.0", "0.6")
    assert not updates.is_newer("0.6.0-beta", "0.6.0")
    assert not updates.is_newer("nonsense", "0.1.0")


def test_check_with_an_answer_and_without_a_network():
    r = updates.check(opener=_opener())
    assert r["newer"] and r["latest"] == "99.0.0" and r["current"] == __version__
    r = updates.check(opener=_opener(tag=f"v{__version__}"))
    assert not r["newer"]

    def offline(req, timeout=0):
        raise urllib.error.URLError("no network")

    with pytest.raises(updates.UpdateError, match="could not reach"):
        updates.check(opener=offline)

    def missing(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    with pytest.raises(updates.UpdateError, match="no release"):
        updates.check(opener=missing)


def test_whats_new_from_the_changelog():
    secs = updates.notes(__version__)
    assert secs and secs[0][0] == __version__ and "###" in secs[0][1]
    older = updates.notes(__version__, since="0.4.0")
    assert [v for v, _ in older][:2] == [__version__, "0.5.0"] and "0.4.0" not in [v for v, _ in older]
    assert updates.notes("0.0.1") == []


def test_version_command(monkeypatch):
    p = Processor()
    r = p.run("VERSION")
    assert r.ok and __version__ in r.message and p.reports["version"]["version"] == __version__
    r = p.run("VERSION, NEWS")
    assert r.ok and r.message.startswith(f"## {__version__}")
    assert p.reports["version"]["news"][0]["version"] == __version__
    monkeypatch.setattr(updates, "latest", lambda *a, **k: {"version": "99.0.0", "url": "https://x.invalid",
                                                             "name": "", "published": "", "notes": ""})
    r = p.run("VERSION, CHECK")
    assert r.ok and "99.0.0 is out" in r.message and p.reports["version"]["newer"] is True
    assert not p.run("VERSION, NEWS, banana").ok
    assert not p.run("VERSION, LOUDER").ok
    assert not p.history  # never a history step


@GUI
def test_whats_new_once_after_an_update_and_the_check_is_off_by_default(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from modeler.gui import updates_ui
    from modeler.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat)
    w = MainWindow(autosave="off", settings=settings)
    asked = []
    monkeypatch.setattr(updates_ui, "check_now", lambda win, quiet=False: asked.append(quiet))
    updates_ui.on_start(w)  # a first start: no What's new, no check (it is off until turned on)
    assert not getattr(w, "_whats_new", None) and not asked
    assert settings.value(updates_ui.LAST_VERSION_SETTING) == __version__
    settings.setValue(updates_ui.LAST_VERSION_SETTING, "0.5.0")  # as if the app was 0.5.0 last time
    updates_ui.set_enabled(w, True)
    updates_ui.on_start(w)
    dlg = w._whats_new
    assert __version__ in dlg.windowTitle() and "0.5.0" not in dlg.view.toMarkdown().split("\n")[0]
    assert asked == [True]  # quiet: it says something only when a newer one is out
    updates_ui.on_start(w)  # once only
    assert w._whats_new is dlg
    dlg.close()
    monkeypatch.setattr(updates, "check", lambda *a, **k: {"current": __version__, "latest": "99.0.0", "newer": True,
                                                           "url": "https://x.invalid", "notes": "", "published": ""})
    c = updates_ui.Checker(w, quiet=True)
    c._done(updates.check())
    assert c.box is not None and "99.0.0" in c.box.text()
    c.box.close()
    c = updates_ui.Checker(w, quiet=True)
    c._done("could not reach GitHub")
    assert c.box is None  # quiet: a failed check at start says nothing
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()
