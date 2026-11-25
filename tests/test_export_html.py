"""PLAN item 114: EXPORT, HTML writes one web page with the model in a viewer."""

import base64
import json
import re

import numpy as np

from modeler.commands import Processor


def _data(path):
    text = open(path, encoding="utf-8").read()
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', text, re.S)
    return text, json.loads(m.group(1))


def test_web_page_holds_parts_notes_and_the_viewer(tmp_path):
    p = Processor()
    for line in ("BLOCK, 0,0,0, 60,40,10", "CYL, 30,20,10, 8, 20", "UNION, 1, 2", "NAME, LAST, bracket",
                 "COLOR, bracket, #3377cc", "SPHERE, 100, 20, 10, 12", "HIDE, 4", 'NOTE, "</script> bore", 30, 20, 40'):
        assert p.run(line).ok, line
    f = str(tmp_path / "m.html")
    r = p.run(f'EXPORT, HTML, "{f}"')
    assert r.ok and "web page" in r.message
    text, d = _data(f)
    assert "http://" not in text.replace("http://www.w3.org", "") and "https://" not in text  # nothing fetched
    assert [pt["name"] for pt in d["parts"]] == ["bracket", "body4"]
    assert d["parts"][0]["color"] == [0.2, 0.4667, 0.8] and d["parts"][1]["shown"] is False
    pts = np.frombuffer(base64.b64decode(d["parts"][0]["p"]), np.float32).reshape(-1, 3)
    tris = np.frombuffer(base64.b64decode(d["parts"][0]["t"]), np.uint32).reshape(-1, 3)
    assert tris.max() < len(pts) and len(tris) == d["parts"][0]["tris"] > 20
    assert pts[:, 2].max() == np.float32(30.0)
    edges = np.frombuffer(base64.b64decode(d["parts"][0]["e"]), np.float32).reshape(-1, 2, 3)
    assert len(edges) > 12
    assert d["notes"][0]["text"] == "</script> bore" and "<\\/script> bore" in text
    assert p.reports["export"]["parts"] == 2


def test_one_body_and_no_history(tmp_path):
    p = Processor()
    p.run("BLOCK, 0,0,0, 1,1,1")
    p.run("BLOCK, 5,0,0, 1,1,1")
    f = str(tmp_path / "one.html")
    assert p.run(f'EXPORT, HTML, "{f}", 2').ok
    _t, d = _data(f)
    assert len(d["parts"]) == 1
    assert len(p.history) == 2
