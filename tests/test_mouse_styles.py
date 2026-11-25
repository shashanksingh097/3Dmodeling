"""PLAN item 75: mouse styles (headless part)."""

from modeler.viewport import mouse_styles as ms


def test_every_style_orbits_pans_and_zooms_somehow():
    for st in ms.STYLES.values():
        what = set(st.drags.values())
        assert {"ROTATE", "PAN"} <= what, st.key
        assert st.label and st.help


def test_left_click_always_picks_in_the_cad_styles():
    for key in ("middle-orbit", "middle-pan", "blender"):
        assert ms.get(key).action("LEFT", "") is None


def test_ctrl_and_alt_drag_fall_back_to_the_plain_drag():
    d = ms.get("default")
    assert d.action("LEFT", "CTRL") == "ROTATE" and d.action("LEFT", "ALT") == "ROTATE"
    assert d.action("LEFT", "SHIFT") == "PAN"


def test_unknown_style_is_the_default():
    assert ms.get("nope").key == ms.DEFAULT


def test_status_text_names_the_drags():
    t = ms.get("middle-orbit").status_text()
    assert t.startswith("Middle drag: orbit") and "Shift+middle drag: zoom" in t


def test_modifier_word():
    assert ms.modifier_word(True, True, False) == "CTRL"
    assert ms.modifier_word(False, False, False) == ""
