---
name: drawings-and-tolerances
description: 2D drawings and sheets (views, sections, details, sizes, title block) as SVG, DXF or PDF, notes and sizes pinned to the 3D model, ISO 286 fits, geometric tolerances with datums, and tolerance stack-ups. Use for "make a drawing", "add tolerances", "will these parts always fit".
commands: DRAWING, PROPERTY, NOTE, FITS, STACKUP, SECTION
---
# Drawings and tolerances

## Steps

1. **Title block**: `PROPERTY, TITLE, Bearing plate`, `PROPERTY, NUMBER,
   BP-001` (also REVISION, AUTHOR ...). `PROPERTY` alone lists them.
2. **Notes on the model** (shown in the view and carried onto sheets):
   select a face, then
   * `NOTE, DATUM, A` (a datum letter);
   * `NOTE, GDT, FLATNESS, 0.02`, `NOTE, GDT, PARALLELISM, 0.05, A`,
     `NOTE, GDT, POSITION, D0.05, A, B` (D = a round zone);
   * `NOTE, FIT, H7` (the diameter with its limits), `NOTE, HOLE`;
   * `NOTE, SIZE, x1,y1,z1, x2,y2,z2` (a size between two points);
   * `NOTE, "text", x,y,z [, x2,y2,z2]` (text with a leader).
3. **Fits**: `FITS, H7/g6, 30` gives hole and shaft limits and the
   clearance (or interference) range.
4. **Stack-ups**: `STACKUP, +20.2 ±0.05, -20 ±0.05, MIN=0.05, MAX=0.4`:
   each size of the chain added or taken away with its tolerance (or an
   ISO fit: `+25 H7`), worst case and statistical range of the gap, each
   link's share, and whether the gap stays within what is allowed.
5. **The drawing**: `DRAWING, "part.svg"` (front, top, right and iso with
   sizes), views by name `TOP+FRONT+ISO`, one body, `sizes NONE`;
   `.dxf` for CAD; `.pdf` or a sheet size (A4, A3 ...) for a framed sheet
   with the title block. Sections `"X 30"` and details
   `"FRONT 20 0 5 8 3"` go in the section and detail arguments.
   DRAWING writes a file: in the assistant, propose it for the user to run
   (files are refused in the sandbox).

```cmd
BLOCK, 0, 0, 0, 60, 40, 10
NAME, LAST, plate
SEL, S, FACE, LOC, Z, 0
NOTE, DATUM, A
SEL, NONE
FITS, H7/g6, 20
```

## Check the result

* The STACKUP answer says "always within" for worst case (or for the
  statistical range, if the user accepts that).
* `FITS` says clearance, transition or interference as the user wants.
* Notes: `LIST` or the notes in the view; every GD&T frame that names a
  datum needs that datum letter on a face.

## Mistakes to avoid

* A tolerance frame naming datum B when no face carries `NOTE, DATUM, B`.
* Mixing a fit and a ± tolerance on one size.
* Writing drawings from the sandbox: file commands are refused there.
* A stack-up with a sign wrong: sizes that open the gap are +, sizes that
  close it are -.
