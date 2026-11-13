"""Run a .cmd script in the real window, then save pictures of the 3D view.

This is how the pictures of the car example were taken. Under Linux without
a screen, run it with Xvfb:

    xvfb-run -a -s "-screen 0 1920x1200x24" python scripts/car/shoot.py \\
        scripts/car_body.cmd scripts/car/shots.txt pictures 1600 1000

Each line of the shots file is

    file.png | command; command; ... | view

The commands run first (for example ISOLATE one part, or MOVE parts apart),
then the view is set and the picture is saved. `view` is a named view (ISO,
TOP, FRONT ...) or a direction dx,dy,dz from the model towards the eye, with
z kept up. Lines starting with # are skipped. A path in `file.png` may
contain a folder (parts/01-hood.png); it is made under the output folder.

The script runs with a coarse mesh (fast), then every body is meshed again
finely before the first picture, so curved panels look smooth.
"""

import math
import os
import sys
import time

from OCP.Aspect import Aspect_TOD_RELATIVE
from OCP.Image import Image_AlienPixMap
from OCP.TCollection import TCollection_AsciiString
from PySide6.QtWidgets import QApplication

from modeler.gui.main_window import MainWindow


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    script, shots, outdir = argv[:3]
    w, h = (int(argv[3]), int(argv[4])) if len(argv) > 4 else (1600, 1000)

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.show()
    for _ in range(50):
        app.processEvents()
        if win.viewport._initialized:
            break
    vp = win.viewport

    def pump(n: int = 5) -> None:
        for _ in range(n):
            app.processEvents()

    drawer = vp.context.DefaultDrawer()
    drawer.SetTypeOfDeflection(Aspect_TOD_RELATIVE)
    drawer.SetDeviationCoefficient(0.002)  # coarse while the script runs
    drawer.SetDeviationAngle(math.radians(12))
    t = time.time()
    with open(script, encoding="utf-8") as f:
        res = win.execute(f.read())
    print(f"script ok={res.ok} in {time.time() - t:.1f} s")
    if not res.ok:
        print(res.message[-2000:])
        return 1

    drawer.SetDeviationCoefficient(0.0003)  # fine for the pictures
    drawer.SetDeviationAngle(math.radians(4))
    t = time.time()
    for ais in list(vp._ais.values()):
        vp.context.Redisplay(ais, False, True)
    print(f"fine mesh in {time.time() - t:.1f} s")

    with open(shots, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    for line in lines:
        name, cmds, view = (s.strip() for s in line.split("|"))
        for c in (c.strip() for c in cmds.split(";")):
            if c:
                r = win.execute(c)
                if not r.ok:
                    print(f"  FAILED {c}: {r.message}")
        pump()
        if "," in view:
            dx, dy, dz = (float(v) for v in view.split(","))
            vp.view.SetProj(dx, dy, dz)
            vp.view.SetUp(0, 0, 1)
        else:
            win.execute("VIEW, " + view)
        vp.view.FitAll(0.06, False)
        vp.view.Redraw()
        pump()
        path = os.path.join(outdir, name)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        pix = Image_AlienPixMap()
        ok = vp.view.ToPixMap(pix, w, h) and pix.Save(TCollection_AsciiString(path))
        print(("saved " if ok else "COULD NOT SAVE ") + path)
    win.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
