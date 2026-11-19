---
name: scan-to-cad
description: Turn a scanned or imported mesh into CAD - import, clean (HEAL, SMOOTH, SIMPLIFY), split into regions (SEGMENT), rebuild machined parts exactly from planes, cylinders and spheres (RECONSTRUCT), and fit smooth NURBS surfaces to rounded shapes (FITSURF). Use for STL or OBJ scans, reverse engineering, imported meshes.
commands: IMPORT, HEAL, SMOOTH, SIMPLIFY, REMESH, SEGMENT, RECONSTRUCT, FITSURF, MASK, TOSOLID, TOMESH
---
# Scan to CAD

## Steps

1. **Import**: `IMPORT, STL, "scan.stl", scan` (also OBJ, 3MF, PLY ...;
   `..., MESH` keeps it as a mesh body, the usual choice for scans).
   `describe_body` says whether a body is exact, faceted or a mesh.
2. **Clean**: `SMOOTH, scan` (noise), `SIMPLIFY, scan, 0.05` (fewer
   triangles within 0.05), `REMESH, scan, 1` (finer, even triangles).
   `HEAL` is for exact bodies (STEP, IGES) that CHECK reports broken.
3. **Machined parts** (flat faces, bores, bosses, round ends):
   `SEGMENT, scan` lists the regions split at sharp edges and what each is
   (plane, cylinder or bore, sphere, freeform) with how far the fit is off.
   Then `RECONSTRUCT, scan` fits and joins them into one exact solid (a new
   body; the mesh stays). It refuses rounded freeform regions.
4. **Rounded, freeform shapes** (a handle, a body panel, a sculpt):
   `FITSURF, scan [, region [, tol]]`: a closed star-shaped mesh becomes a
   solid, an open scan a face. Paint a region with `MASK, scan, PAINT, ...`
   and `FITSURF, scan, MASK` to fit one piece at a time.
5. **Then model on it**: the exact solid takes HOLE, FILLET, booleans;
   round the fitted sizes to the intended ones by modelling the clean part
   with parameters, using the fits as the measurements.

```cmd
BLOCK, 0, 0, 0, 30, 20, 10
NAME, LAST, part
TOMESH, part
RECONSTRUCT, part
NAME, LAST, rebuilt
ASSERT, VALID(rebuilt)
```

## Check the result

* `VALID(solid)`, `PIECES(solid), EQ, 1`.
* `VOL(solid)` close to the mesh's (RECONSTRUCT prints the difference).
* `COMPARE, solid, scan` or `section_profile` of both at a few heights.
* Sizes from a scan are close, not exact (a 10 mm bore fits as 9.99): check
  with a tolerance, and say so in the answer.

## Mistakes to avoid

* RECONSTRUCT on an organic shape: it refuses; use FITSURF.
* A scan with holes in its skin: close them in the scanning program first,
  or FITSURF gives an open face and RECONSTRUCT leaves gaps.
* Taking fitted sizes as design sizes without rounding them on purpose.
* TOSOLID on a huge mesh: SIMPLIFY first (it is limited to 100,000
  triangles).
