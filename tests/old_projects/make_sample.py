"""Make the sample project with a release, for tests/test_project_safety.py.

It builds the sample model with that release's own code, saves it (sample-<version>.m3d) and writes
what it measured (sample-<version>.json), so the current version can be checked against it. For a
new release (here v0.7.0)::

    git archive v0.7.0 modeler | tar -x -C /tmp/rel
    python -I -c "import sys; sys.path.insert(0, '/tmp/rel'); \
        sys.argv = ['make', 'tests/old_projects/sample-v0.7.0', 'v0.7.0']; \
        exec(open('tests/old_projects/make_sample.py').read())"
"""
import json
import sys

from modeler.commands import Processor

SCRIPT = """W = 60
H = 15
BLOCK, 0,0,0, W, 40, H
NAME, LAST, base
CYL, 15,20,-1, 5, H+2
SUBTRACT, base, LAST
SKETCH, s, XY
SRECT, 70,0, 30, 20
ENDSKETCH
EXTRUDE, s, 8
NAME, LAST, tab
*PART, peg, D=6
  CYL, 0,0,0, D/2, 20
*ENDPART
INST, peg, 45, 20, H
INST, peg, 45, 30, H, D=4"""

out, version = sys.argv[1], sys.argv[2]
p = Processor()
for r in p.run_script(SCRIPT):
    if not r.ok:
        sys.exit(f"{r.line}: {r.message}")
p.run(f'SAVE, "{out}.m3d"')
m = p.model
vols = sorted(round(p.evaluate(f"VOL({b})"), 6) for b in m.bodies if b not in getattr(m, "hidden", set()))
named = {n: round(p.evaluate(f"VOL({n})"), 6) for n in ("base", "tab")}
json.dump({"version": version, "volumes": vols, "named": named, "bodies": len(vols),
           "entries": p.cursor, "W": p.evaluate("W")}, open(out + ".json", "w"), indent=1)
print(version, vols)
