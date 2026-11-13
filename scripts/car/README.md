# Car example: the working files

Everything used to make the car example (`scripts/car_body.cmd`) and its
pictures. The method is described in `docs/example-car.md`.

| File | What it is |
|------|------------|
| `../car_body.cmd` | the finished car: 218 bodies, all pass `CHECK` |
| `shots.txt` | the shots taken: the whole car from 7 angles, 2 exploded views, then each part alone |
| `sheet.py` | puts several pictures on one sheet, to check a batch of shots at a glance |
| `prototypes/proto.cmd` | first try: the whole body as one `LOFT` through 14 closed splines (came out wavy and boxy, dropped) |
| `prototypes/tub.cmd` | second try: the lower body as `NSURF` of closed `NURBS` rows, `FILL` caps, `SEW` (smooth; became the method) |
| `prototypes/v2.cmd` | lower body plus cabin, both from control-point rows |
| `prototypes/wheel.cmd` | tyre, rim and brake parts tried on their own |
| `prototypes/shell_and_first_panels.cmd` | the 3 mm skin and two panels cut with the panel macros |
| `prototypes/seam_offset_check.cmd` | why `OFFSET` failed on one side: the seam of the closed rows adds a face there |
| `prototypes/list_bodies.cmd` | lists every body of the finished car with its layer |

## Taking the pictures again

From the repository folder (on Linux without a screen, through Xvfb):

```bash
xvfb-run -a -s "-screen 0 1920x1200x24" python -m modeler render \
    scripts/car_body.cmd --shots scripts/car/shots.txt pictures --size 1600x1000
python scripts/car/sheet.py sheet.png pictures/car-*.png
```

The whole run takes a few minutes: the script itself about 85 s in the
window, then the fine mesh and one picture per line. On a desktop, leave out
`xvfb-run ...` and run `python -m modeler render ...` directly.

A line of `shots.txt` is `file.png | commands | view`. For a part alone the
commands are `PICK, BODY, name; PICK, BODY, other, A; ISOLATE, SEL`; the
exploded views `MOVE` each part away from the car first. The view is a
direction from the car towards the eye (`-1,-1.25,0.55` is front right, from
a little above) or a named view such as `TOP`.

The prototypes run on their own (`python -m modeler run
scripts/car/prototypes/tub.cmd`), or from File → Open in the app.
