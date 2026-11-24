"""The five demonstration projects (PLAN item 65, docs/demos/, pages on the website): each one
is built from an empty model, its first parameter is changed and the model rebuilt, it is
saved and opened again, and every file it writes is read back and compared with the model."""

import os
import re

import pytest

from modeler import docsite
from modeler.commands import Processor

NAMES = docsite.demo_scripts()


def test_there_are_five_demonstrations_with_pictures():
    assert NAMES == list(docsite.DEMO_ORDER)
    for n in NAMES:
        assert os.path.getsize(os.path.join(docsite.DEMOS, n + ".png")) > 10_000


def ok(p, text):
    res = p.run_script(text)
    bad = [r for r in res if not r.ok]
    assert not bad, f"{bad[0].line.splitlines()[-1]}: {bad[0].message}"
    return res


def shown_volume(p):
    m = p.model
    return sum(p.evaluate(f"VOL({b})") for b in m.bodies if m.is_shown(b) and not _is_mesh(p, b))


def _is_mesh(p, b):
    from modeler.geometry import meshbody

    return meshbody.is_mesh(p.model.bodies[b].shape)


@pytest.fixture
def built(request, tmp_path, monkeypatch):
    name = request.param
    monkeypatch.chdir(tmp_path)
    with open(os.path.join(docsite.DEMOS, name + ".cmd"), encoding="utf-8") as f:
        script = f.read()
    p = Processor()
    ok(p, script)
    return name, script, p, tmp_path


@pytest.mark.parametrize("built", NAMES, indirect=True)
def test_the_demonstration_builds_and_reads_back(built):
    name, script, p, tmp = built
    files = sorted(os.listdir(tmp))
    assert files, "it wrote no files"
    for f in files:
        path = str(tmp / f)
        ext = f.rsplit(".", 1)[-1].lower()
        if ext == "step":
            q = Processor()
            ok(q, f'IMPORT, STEP, "{path}"')
            want = _exported_volume(p, script, f)
            assert shown_volume(q) == pytest.approx(want, rel=1e-6), f
        elif ext == "stl" and f != "scan.stl":
            q = Processor()
            ok(q, f'IMPORT, STL, "{path}", back, MESH')
            assert q.evaluate("VOL(back)") == pytest.approx(_exported_volume(p, script, f), rel=0.02), f
        elif ext == "pdf":
            data = open(path, "rb").read()  # noqa: SIM115
            assert data.startswith(b"%PDF") and int(re.search(rb"/Count (\d+)", data).group(1)) >= 1
        elif ext == "dxf":
            q = Processor()
            ok(q, f'SKETCH, s, XY\nSDXF, "{path}", 1, 0, 0, OUTLINE\nENDSKETCH\nEXTRUDE, s, 1')
            flat = q.evaluate("VOL(LAST)")
            blank = p.evaluate("VOL(blank)") / p.evaluate("BBOX(blank).dz")
            assert flat == pytest.approx(blank, rel=1e-3), "the DXF blank has the unfolded body's area"


def _exported_volume(p, script, filename):
    """Volume of what the EXPORT line that wrote ``filename`` wrote (one body, or all shown)."""
    line = next(ln for ln in script.splitlines() if ln.startswith("EXPORT") and filename in ln)
    parts = [a.strip() for a in line.split(",")]
    if len(parts) > 3 and parts[3]:
        # the body as it was when written: the scan demo moves its solid afterwards (same volume)
        return p.evaluate(f"VOL({parts[3]})")
    return shown_volume(p)


@pytest.mark.parametrize("built", NAMES, indirect=True)
def test_the_demonstration_saves_opens_and_follows_its_parameters(built):
    name, script, p, tmp = built
    vol = shown_volume(p)
    path = str(tmp / "project.m3d")
    ok(p, f'SAVE, "{path}"')
    q = Processor()
    ok(q, f'OPEN, "{path}"')
    assert shown_volume(q) == pytest.approx(vol, rel=1e-9)
    first = q.history[0].text.strip()
    m = re.match(r"^(\w+)\s*=\s*([\d.]+)", first)
    if not m:  # the scan starts from its file, not a parameter
        return
    bigger = float(m.group(2)) * 1.1
    ok(q, f'HIST, EDIT, 1, "{m.group(1)} = {bigger:g}"')
    assert all(e.ok for e in q.history), [e.message for e in q.history if not e.ok]
    assert shown_volume(q) > vol


def test_the_assembly_is_fully_placed_without_overlaps(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = Processor()
    with open(os.path.join(docsite.DEMOS, "assembly_hinge.cmd"), encoding="utf-8") as f:
        ok(p, f.read())
    mates = p.run("MATES").message
    assert mates.count(": holds") == 3 and "DOES NOT HOLD" not in mates
    assert "0 fights, 0 repeats" in mates
    assert "0 overlapping" in p.run("CONTACT").message
    assert "6 pieces" in p.run("BOM").message


def test_each_demonstration_has_a_page():
    pages, nav = docsite.demo_pages()
    assert [list(x.values())[0] for x in nav] == ["demos/index.md"] + [f"demos/{n}.md" for n in NAMES]
    for n in NAMES:
        md = pages[f"demos/{n}.md"]
        assert md.startswith("# ") and f"]({n}.png)" in md and "```text" in md and "## Kept working" in md
        assert md.count("\n## ") >= 4  # the steps are explained part by part
