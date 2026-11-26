"""PLAN item 116: textures (TEXTURE) and decals (DECAL) on bodies and faces."""

import os
import sys

import pytest

from modeler.commands import Processor
from modeler.geometry import decal as dc

GUI = pytest.mark.skipif(os.environ.get("MODELER_GUI_TESTS") == "0" or
                         (sys.platform.startswith("linux") and not os.environ.get("DISPLAY")), reason="no display")


def ok(p, line):
    r = p.run(line)
    assert r.ok, f"{line}: {r.message}"
    return r


def _png(path, w, h, pixel):
    """A small RGBA PNG written by hand (the CI machine without a display has no Qt GUI library)."""
    import struct
    import zlib

    rows = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(w)) for y in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


@pytest.fixture
def picture(tmp_path):
    """A 200 x 100 picture with a see-through half."""
    path = str(tmp_path / "logo.png")
    _png(path, 200, 100, lambda x, y: (200, 30, 30, 255) if x < 100 else (0, 0, 0, 0))
    return path


def test_decal_follows_its_face_and_lists_as_data(picture):
    p = Processor()
    ok(p, "W = 80")
    ok(p, "BLOCK, 0,0,0, W, 30, 20")
    ok(p, "NAME, LAST, box")
    r = ok(p, f'DECAL, logo, 6, "{picture}", 40, 5, 0, 10')
    assert "logo" in r.message and "40 x 20" in r.message and "angle 10" in r.message
    row = p.reports["decals"]["decals"][0]
    assert row["face"] == 6 and row["height"] == pytest.approx(20) and row["body"] == "box"
    assert row["overhangs"] is False
    ok(p, 'HIST, EDIT, 1, "W = 120"')  # the box grows: the decal stays on its face, now further along
    face = dc._as_face(p.model.entity_shape("FACE", 6))
    assert dc.frame(face)["centre"][0] == pytest.approx(60)
    r = ok(p, "DECAL")
    assert "logo" in r.message and "hangs over" not in r.message
    r = ok(p, f'DECAL, big, 6, "{picture}", 500')
    assert "hangs over the face" in r.message
    ok(p, "DECAL, DELETE, big")
    assert [d["name"] for d in p.model.decals] == ["logo"]
    ok(p, "UNDO")
    assert len(p.model.decals) == 2
    ok(p, "DECAL, CLEAR")
    assert not p.model.decals


def test_decal_on_a_round_face_and_its_limits(picture):
    p = Processor()
    ok(p, "CYL, 0, 0, 0, 10, 40")
    side = next(g for g in p.model.bodies[1].entity_ids["FACE"]
                if _try_frame(p, g) and dc.frame(dc._as_face(p.model.entity_shape("FACE", g)))["kind"] == "ROUND")
    ok(p, f'DECAL, label, {side}, "{picture}", 20, 0, 5')
    assert not p.run(f'DECAL, label, {side}, "{picture}", 20, 0, 0, 45').ok  # round faces: 0 or 180
    assert not p.run(f'DECAL, label, {side}, "{picture}", 200').ok  # wider than the way round
    ok(p, f'DECAL, flip, {side}, "{picture}", 20, 0, 0, 180')
    assert not p.run(f'DECAL, 9x, {side}, "{picture}", 20').ok
    assert not p.run(f'DECAL, x, {side}, "{picture}", 0').ok
    assert not p.run(f'DECAL, x, {side}, nothere.png, 10').ok
    ok(p, "SPHERE, 50, 0, 0, 5")
    sphere_face = p.model.bodies[2].entity_ids["FACE"][0]
    r = p.run(f'DECAL, x, {sphere_face}, "{picture}", 4')
    assert not r.ok and "flat or a round" in r.message


def _try_frame(p, g):
    try:
        dc.frame(dc._as_face(p.model.entity_shape("FACE", g)))
        return True
    except dc.DecalError:
        return False


def test_texture_on_bodies_and_materials(picture, tmp_path):
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40, 20, 10")
    ok(p, "NAME, LAST, desk")
    ok(p, "BLOCK, 50,0,0, 10, 10, 10")
    r = ok(p, f'TEXTURE, desk, "{picture}", 20')
    assert "tiles 20 mm" in r.message
    assert p.model.display_texture(1) == (os.path.abspath(picture), 20.0)
    ok(p, "MATERIAL, 2, WOOD")
    ok(p, f'TEXTURE, WOOD, "{picture}", 30')
    assert p.model.display_texture(2) == (os.path.abspath(picture), 30.0)
    ok(p, "TEXTURE, 2, OFF")  # off for this body, though its material has one
    assert p.model.display_texture(2) is None
    ok(p, "UNION, 1, 2")  # a body made from others keeps the first one's texture
    assert p.model.display_texture(p.model.last_body) == (os.path.abspath(picture), 20.0)
    r = ok(p, "TEXTURE, ALL, OFF")
    assert p.model.display_texture(p.model.last_body) is None
    assert not p.run(f'TEXTURE, nobody, "{picture}", 10').ok
    assert not p.run(f'TEXTURE, WOOD, "{picture}"').ok  # a material's texture needs a tile size
    f = str(tmp_path / "a.m3d")
    ok(p, f'TEXTURE, ALL, "{picture}", 15')
    ok(p, f'DECAL, logo, 6, "{picture}", 10')
    ok(p, f'SAVE, "{f}"')
    q = Processor()
    ok(q, f'OPEN, "{f}"')
    assert q.model.display_texture(q.model.last_body)[1] == 15.0
    assert [d["name"] for d in q.model.decals] == ["logo"]
    r = ok(q, "FILES")
    assert "logo.png" in r.message


def test_tiles_keep_one_size_on_every_face():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 100, 20, 10")
    ok(p, "CYL, 200, 0, 0, 10, 30")
    faces = dc.faces(p.model.bodies[1].shape)
    reps = sorted(dc.tiles(f, 10) for f in faces)
    assert any(abs(ru - 10) < 1e-6 or abs(rv - 10) < 1e-6 for ru, rv in reps)  # the 100 mm side: 10 tiles
    side = max(dc.faces(p.model.bodies[2].shape), key=lambda f: max(dc.tiles(f, 1)))
    ru, rv = dc.tiles(side, 1)
    assert max(ru, rv) == pytest.approx(2 * 3.14159265 * 10, rel=0.02)  # round the cylinder: 2 pi r tiles of 1


@GUI
def test_texture_and_decal_are_drawn(tmp_path, picture):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from modeler.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    w.show()
    app.processEvents()
    assert w.execute("BLOCK, 0,0,0, 40, 20, 10").ok
    assert w.execute(f'TEXTURE, 1, "{picture}", 10').ok
    app.processEvents()
    vp = w.viewport
    assert len(vp._tex_ais.get(1, [])) == 6
    assert vp._ais[1].DisplayMode() == 0  # the body draws its edges; the textured faces its shading
    assert w.execute(f'DECAL, logo, 6, "{picture}", 20').ok
    app.processEvents()
    assert len(vp._decal_ais) == 1
    assert w.execute("PICK, EDGE, 1").ok and w.execute("FILLET, 2").ok  # the body is made again: both follow
    app.processEvents()
    assert len(vp._tex_ais.get(w.processor.model.last_body, [])) == 7 and len(vp._decal_ais) == 1
    assert w.execute("UNDO").ok
    app.processEvents()
    assert len(vp._decal_ais) == 1
    assert w.execute("TEXTURE, ALL, OFF").ok
    app.processEvents()
    assert not any(vp._tex_ais.values())
    assert w.execute("DECAL, CLEAR").ok
    app.processEvents()
    assert not vp._decal_ais
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()
