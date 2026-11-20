"""The desktop check (PLAN item 64) runs here too, on Xvfb: every automatic step passes, and
the report it writes is complete."""

import json
import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from modeler import desktop_check  # noqa: E402


def test_the_desktop_check_passes_and_writes_its_report(tmp_path):
    steps = desktop_check.run(str(tmp_path), log=lambda *_: None)
    failed = [f"{s.name}: {s.detail}" for s in steps if not s.ok]
    assert not failed, "\n".join(failed)
    assert len(steps) == 11
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "**11 of 11 steps ok**" in report and "## This computer" in report and "opengl:" in report
    data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert data["facts"]["screens"] and {s["name"] for s in data["steps"]} >= {
        "a mouse click picks the face under it (screen scaling)",
        "save and open in a folder with spaces and non-English letters"}
    for picture in ("view.png", "window.png"):
        assert (tmp_path / picture).stat().st_size > 10_000
    assert (tmp_path / desktop_check.AWKWARD / "model ü.m3d").exists()


def test_a_failed_step_is_reported_with_its_details(tmp_path):
    steps = [desktop_check.Step("the window opens", True, "in 0.2 s", 0.2),
             desktop_check.Step("a mouse click picks the face under it", False,
                                "wanted face 8, got nothing\nTraceback: ...", 0.1)]
    desktop_check.write_report(str(tmp_path), {"app": "x", "screens": ["a: 1x1 at scale 2"]}, {}, steps)
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "**1 of 2 steps ok**, 1 failed: a mouse click picks the face under it" in report
    assert "| **FAIL** | a mouse click picks the face under it | wanted face 8, got nothing |" in report
    assert "Traceback: ..." in report and "- screen a: 1x1 at scale 2" in report
