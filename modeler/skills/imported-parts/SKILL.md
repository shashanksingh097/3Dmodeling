---
name: imported-parts
description: Changing parts that have no history (imported STEP or IGES files, or any solid) - finding their holes, rounds, chamfers and rows of holes, selecting ones like a face, resizing or removing them in bulk, pushing and moving faces. Use for "simplify this STEP", "make the holes bigger", "remove the small fillets", "the 6 mm holes should be M8 clearance".
commands: IMPORT, SSVG, FEATURES, DEFEATURE, RESIZE, SEL, PUSHPULL, MOVEFACE, DELFACE, CHECK, HEAL
---
# Editing imported parts

## Steps

1. **Bring it in and check it**: `IMPORT, STEP, "part.step", part`, then
   `CHECK, part, FLAWS`; `HEAL, part` when it lists gaps or bad faces.
   An OpenSCAD file: `IMPORT, SCAD, "part.scad"` (one exact body per
   top-level object). A flat SVG drawing goes into a sketch instead:
   `SKETCH, s, XY`, `SSVG, "logo.svg"`, `ENDSKETCH`, then `EXTRUDE`.
2. **See what is there**: `FEATURES, part` lists every hole (diameter,
   depth, through or blind, counterbore), round (radius, inside or outside),
   chamfer (size) and row or ring of holes, numbered, with face IDs. The
   same rows come back as data in the report; read sizes from there instead
   of guessing them from a picture. `FEATURES, part, HOLE` lists one kind.
3. **Change them all at once** by kind and size (EQ, NE, LT, LE, GT, GE,
   ALL):
   - `RESIZE, part, HOLE, EQ, 6, 8.4` (every 6 hole becomes 8.4; position,
     depth and counterbore stay),
   - `RESIZE, part, FILLET, LT, 2, 1` (rounds under 2 become 1),
   - `DEFEATURE, part, FILLET, LT, 1` or `DEFEATURE, part, HOLE, EQ, 3`
     (removed, the faces around close the gap).
4. **Pick them for other commands**: `SEL, S, FACE, FEATURE, HOLE, EQ, 6`
   picks the walls of every 6 hole; `SEL, S, FACE, LIKE, 31` picks faces
   like face 31 (every hole or round of its size, or faces of the same type
   and size); add `, ALL` to look in every body.
5. **Single faces**: `PUSHPULL, d` on picked faces (a hole wall changes the
   radius), `MOVEFACE, dx,dy,dz`, `DELFACE`.

```cmd
BLOCK, 0, 0, 0, 80, 40, 10
NAME, LAST, part
SEL, S, FACE, LOC, Z, 10
HOLE, part, 20, 20, 10, 6
HOLE, part, 60, 20, 10, 6
RESIZE, part, HOLE, EQ, 6, 8
ASSERT, HOLES(part), EQ, 2
```

## Check the result

* `FEATURES, part` again: the sizes are the new ones and nothing else
  changed (the count of each kind is the same, unless you removed some).
* `MASSPROP` or `ASSERT, VOL(part), ...` for the volume change you expect.
* `CHECK, part` says the body is valid.

## Mistakes to avoid

* Face numbers from before a change: they can move. Use `SEL, ..., FEATURE`
  or `LIKE` again after each step, or the sizes in RESIZE and DEFEATURE.
* A RESIZE to a hole wider than its counterbore, or a round larger than
  the wall: it is refused; pick a smaller size.
* Removing a round that another round runs into: remove both kinds
  together (`DEFEATURE, part, FILLET`), or the kernel may not close the gap.
