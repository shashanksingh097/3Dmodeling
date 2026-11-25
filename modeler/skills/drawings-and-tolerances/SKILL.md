---
name: drawings-and-tolerances
description: 2D drawings and sheets (views, sections, details, sizes, title block) as SVG, DXF or PDF, notes and sizes pinned to the 3D model, ISO 286 fits, geometric tolerances with datums, and tolerance stack-ups. Use for "make a drawing", "add tolerances", "will these parts always fit".
commands: DRAWING, DRAWSHEET, SHEETTABLE, SHEETNOTE, SHEETDATA, REVISION, PROPERTY, NOTE, FITS, STACKUP, SECTION
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
6. **Sheets kept with the model, with tables**: `DRAWSHEET, front,
   STANDARD, 0, ALL, A3` keeps a sheet; `SHEETTABLE, front, PARTS+HOLES`
   (or ALL) adds a parts list with numbered balloons, a hole table with a
   tag beside each hole (position, size, depth, thread from a NOTE on the
   hole such as `"M6x1"`) and a revision table. Rows come from the model
   each time the sheets are written. `REVISION, B, "Hole moved"` adds a
   revision (the newest is the title block's REV). Check the rows with
   `SHEETDATA, front` (data, writes nothing).
   Drawing details go on with `SHEETNOTE`: `SHEETNOTE, front, CENTRES`
   (centre marks on holes seen end on, centre lines on holes seen from the
   side), `THREADS` (cosmetic threads on holes with a thread NOTE, such as
   a 6.8 hole noted "M8"), `FINISH, 12, 1.6, ground` (surface finish on
   face 12), `WELD, weld_1` (weld symbol with size and length) and
   `LEADER, EDGE 5, "Break sharp edges"`. `SHEETNOTE, front` lists them,
   `SHEETNOTE, front, DELETE, 2` removes one. After DRAWINGS, the report
   `drawings` has `details`: what was placed on which view.
7. **Sizes and tolerances to other programs**: `EXPORT, STEP, "part.step"`
   writes the NOTE sizes, hole diameters and fits, GD&T frames and datums
   on the exported bodies as AP242 annotations (the reply says how many).
   `IMPORT, STEP` of such a file makes them notes again. Plain text notes
   are not written.

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
* Tables: `SHEETDATA, sheet` lists the parts, hole tags and revisions the
  sheet will show; a hole missing from it is not a round hole.
* Notes: `LIST` or the notes in the view; every GD&T frame that names a
  datum needs that datum letter on a face.

## Mistakes to avoid

* A tolerance frame naming datum B when no face carries `NOTE, DATUM, B`.
* Mixing a fit and a ± tolerance on one size.
* Writing drawings from the sandbox: file commands are refused there.
* A stack-up with a sign wrong: sizes that open the gap are +, sizes that
  close it are -.
