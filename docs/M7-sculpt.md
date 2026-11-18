# M7: sculpting mesh bodies

M7 adds sculpting: brushes that push, pull, smooth and flatten the points
of a mesh body, with the mouse or as commands (LANGUAGE.md section 28).
This note covers part 1: the brushes, masks, symmetry, stroke logging and
the Sculpt tab. Part 2 (live preview while dragging, a visible mask,
dynamic topology) is listed at the end.

## Commands, not a separate mode

Every stroke is one history line:

```
STROKE, S1, "4,-19,6  8,-19.5,7  12,-18,8"
SCULPT, head, CLAY, 4, 0.8, S1, X
```

A stroke's points (often a few hundred) would make a history line
unreadable, so they are kept by name in the session (`Processor.strokes`)
and saved with the project as `strokes.npz` next to the model. `SCULPT`
and `MASK` take a stroke name or the points in quotes. A saved log
(**File > Save log**, `script(standalone=True)`) writes the `STROKE` lines
first, so the log runs on its own. Undo, history editing, replay and the
assistant's tools then work on sculpting with nothing new.

Rejected: a sculpt session that records many strokes as one opaque step.
It is quicker to store, but a history step that cannot be read or edited
breaks the rule that the history is the model.

## The brush engine (`geometry/sculpt.py`)

Pure numpy on the mesh's arrays (points N x 3, triangles M x 3):

- A stroke is resampled into dabs a quarter of the radius apart.
- Each dab moves the points within the radius by a smooth falloff
  `(1 - (d/r)^2)^2` times `strength * radius * 0.15`, times `1 - mask`.
- Per stroke (and per mirror copy) only the points inside the stroke's
  bounding box, grown by the radius, and the triangles that touch them are
  looked at, so the cost follows the area the stroke covers, not the mesh.
- Neighbours (for `SMOOTH`, `CREASE`) come from a CSR neighbour list built
  with sort and diff; normals are worked out only for the points near the
  stroke.

| Brush | Moves points |
|-------|--------------|
| DRAW | along the average normal under the brush |
| CLAY | like DRAW, only up to a plane just above the surface |
| INFLATE | along each point's own normal |
| SMOOTH | towards the middle of their neighbours |
| FLATTEN | towards the plane of the area under the brush |
| PINCH | sideways towards the stroke |
| CREASE | PINCH plus a little DRAW inwards |
| GRAB | with the stroke, from its first point to its last |

## Masks

`Model.masks` holds one value per point (0 free, 1 frozen) for each mesh
body, kept in snapshots so undo puts it back. A mask belongs to the
points: a command that makes new triangles drops it (its length no longer
fits).

That needs a mesh's points to keep their order, also when the shape is
read back from its triangulation (after the cache drops it, or after
opening a project). Before M7 the read-back sorted the points. Now
`split_sharp` numbers the split copies in the order of the points they came
from, and `_join_exact` keeps points in the order they first appear, so a
read-back gives the points in the order the mesh was made with (tested on a
sharp-edged block, where the split happens).

## Speed

A sphere remeshed to 821,590 triangles (410,797 points), a 20 mm stroke
with a 3 mm brush (about 9,000 points moved):

| Step | Time |
|------|------|
| `DRAW` stroke, numpy | 0.14 s (0.26 s mirrored) |
| `INFLATE` / `SMOOTH` / `GRAB` | 0.24 / 0.14 / 0.03 s |
| Building the new shape, all points | 1.55 s |
| Building the new shape, moved points only | about 0.3 s |
| Whole `SCULPT` command | 0.45 s (was 1.86 s) |

The shape for OCCT used to be built point by point in Python. Since a
stroke keeps the triangles, `meshbody.moved_shape` copies the old
triangulation in C++ (`Poly_Triangulation.Copy`), drops its normals and
sets only the moved nodes. The split copies made for sharp-edge shading
are remembered per shape, so a moved point moves all its copies. Sharp
edges a stroke makes are not split for shading until a command rebuilds
the whole mesh; the shading over them is soft, which suits sculpting.

On a mesh of about 50,000 triangles (the example head) a stroke takes a
few hundredths of a second.

## The Sculpt tab (`gui/sculpt_tool.py`)

- **Sculpt** turns sculpting on in the 3D view (it and the Knife turn each
  other off). A left drag draws the stroke on top, in blue; on release the
  pixels are cast as rays against the mesh (Moller-Trumbore in numpy, all
  triangles at once) and the hits, thinned to a tenth of the radius apart
  (at most 400), become `Sn`.
- The target is the picked mesh body, or the mesh body under the stroke.
- Ctrl: the other way (negative strength; `ERASE` for the Mask brush).
  Shift: `SMOOTH`. `[` and `]`: radius. Esc: off.
- Brushes, Radius, Strength, Mirror X/Y/Z, Clear mask, Invert mask, and
  **Make sculptable** (`TOMESH` + `REMESH` at a 150th of the size).
- A failed command removes its stroke again.

## What is left (part 2)

- **Live preview** while dragging: show the brush's effect before the
  release. Needs a faster way to show changed points than a new
  `AIS_Shape` (a `MeshVS` or `AIS_Triangulation` whose nodes are updated
  in place).
- **Showing the mask** (frozen areas darker) and a brush circle under the
  mouse.
- **Dynamic topology**: split long edges under the brush so detail can be
  added where it is needed, and `REMESH` that keeps a mask.
- The 1M-triangle goal of PLAN.md at interactive speed during a drag.
