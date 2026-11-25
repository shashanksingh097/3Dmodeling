"""PLAN item 76: language files and the tr() lookup (headless part)."""

from modeler import i18n
from modeler.i18n import sources
from modeler.viewport import mouse_styles as ms


def test_language_files_read_back(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "HERE", tmp_path)
    i18n.write("de", {"Save": ("Speichern", True), "Long help": ("", False)})
    got = i18n.read("de")
    assert got == {"Save": ("Speichern", True), "Long help": ("", False)}
    text = (tmp_path / "de.ts").read_text(encoding="utf-8")
    assert "<!DOCTYPE TS>" in text and 'type="unfinished"' in text


def test_update_adds_new_and_drops_old(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "HERE", tmp_path)
    monkeypatch.setattr(i18n, "LANGUAGES", {"en": "English", "de": "Deutsch"})
    i18n.write("de", {"Old": ("Alt", True), "Save": ("Speichern", True)})
    assert i18n.update({"Save", "New"}) == {"de": 1}
    assert i18n.read("de") == {"Save": ("Speichern", True), "New": ("", False)}


def test_tr_keeps_endings_and_falls_back():
    try:
        i18n.set_language("de")
        assert i18n.tr("Save") == "Speichern"
        assert i18n.tr("Save as…") == "Speichern unter…"
        assert i18n.tr("Theme:") == "Design:"
        assert i18n.tr("No such words here") == "No such words here"
    finally:
        i18n.set_language("en")
    assert i18n.tr("Save") == "Save"


def test_every_language_file_is_well_formed():
    for lang in i18n.LANGUAGES:
        if lang == "en":
            continue
        got = i18n.read(lang)
        assert len(got) > 1000
        assert sum(ok for _t, ok in got.values()) > 1000


def test_commands_and_argument_names_are_not_words():
    assert not sources.words("BLOCK")
    assert not sources.words("XY, YZ")
    assert not sources.words("dx")
    assert not sources.words("/home/x/y.cmd")
    assert sources.words("OK") and sources.words("Fit") and sources.words("Save as…")


def test_mouse_status_in_another_language():
    try:
        i18n.set_language("es")
        t = ms.get("middle-orbit").status_text(i18n.tr)
        assert t.startswith("Arrastrar con el central: orbitar")
    finally:
        i18n.set_language("en")
