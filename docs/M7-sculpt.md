# M7: sculpting mesh bodies

M7 adds sculpting: brushes that push, pull, smooth and flatten the points
of a mesh body, with the mouse or as commands (LANGUAGE.md section 28).
This note covers part 1: the brushes, masks, symmetry, stroke logging and
the Sculpt tab. Part 2 (live preview while dragging, the brush circle, the
mask shown) follows; what is left is at the end.

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

## Part 2: seeing it while you drag

### Live preview (`sculpt_tool.LiveStroke`)

A press starts a `LiveStroke` on the body under the mouse. Each mouse move
casts a ray at the *working* surface (so a second pass over a bump lands on
the bump), and once the mouse has gone a quarter of the radius the brush
runs on that segment of the stroke, on a copy of the points. On release the
recorded hits go to `SCULPT` as before, which starts from the body as it
was: the preview is a close approximation, the command is the result. Esc
during a drag, or a failed command, puts the body's drawing back.

How the moved surface is shown depends on the size:

- Below 150,000 triangles the body's own `AIS_Shape` gets a new shape
  (`moved_shape(..., remember=False)`, kept out of the mesh cache) and is
  redrawn.
- From 150,000 triangles, redrawing the whole body at every move is too
  slow, so only the triangles that moved are drawn, as a separate shape on
  the top layer over the body. The edge of that patch is made of points that
  did not move, so it joins the body without a seam.

The brush engine now reports which points moved (`Report.points`), and
`Topology.triangles_of` finds the triangles at those points through a
point-to-triangle index made once per mesh; the stroke also uses it to
find the triangles near the brush on a big mesh. On a big mesh, rays try
the triangles within four radii of the last hit before trying them all.

Time per mouse move, under the test machine's software OpenGL (a real
graphics card draws much faster):

| Mesh | Per move | Of which drawing the view |
|------|----------|---------------------------|
| 47,586 triangles | 0.04 s (about 26 updates a second) | most of it |
| 821,590 triangles | 0.23 s | about 0.1 s |

### Brush circle and mask

- A circle of the brush's radius lies on the surface under the mouse,
  turned to the face it is over (purple for the Mask brush). It follows
  the mouse at most every 30 ms and during a drag. Hover highlighting of
  the body is off while sculpting.
- Frozen areas (mask above a half) are drawn purple over the body, lifted a
  thousandth of its size so they are not hidden by it. `MASK` sends a new
  model event, `mask`, so the view also updates for a typed `MASK` and on
  undo.

## Part 3: finer triangles where you brush

`SCULPT ..., detail` (and the **Detail** box) splits the triangles near the
stroke before the brush runs (`sculpt.refine_near`):

- **Longest-edge splitting.** A triangle within 1.25 radii of the stroke
  whose longest edge is longer than `detail` has that edge split at its
  middle; any triangle with a split edge has its own longest edge split too
  (repeated until nothing changes), so every triangle is cut across its
  longest edge. Triangles with one, two or three split edges become two,
  three or four. This repeats until no edge near the stroke is too long.
  The first version split every long edge, whichever it was, and made
  slivers where fine and coarse triangles met; a crease folded them over
  and the view showed dark streaks.
- **Kept indices.** Old points keep their indices and new points are added
  at the end, so the mask grows with the mesh (a new point takes the mean
  of its edge's two ends). `REMESH` uses the same splitting, everywhere,
  when the body has a mask, so the mask is kept; without a mask it uses
  manifold3d as before.
- **Evening out.** Five rounds move the points near the stroke halfway
  towards the middle of their neighbours, along the surface only (the part
  along the normal is taken off), so the shape stays and the triangles even
  out.
- **A window.** The work is done on the triangles round the stroke. The
  window is big enough when every split edge has an end whose triangles
  are all in it; otherwise it doubles.

| Mesh | Detail stroke |
|------|---------------|
| 35,000 to 70,000 triangles (crease, detail 0.15) | 0.5 s |
| 820,000 to 1,220,000 triangles (detail 0.06) | 7 s (split 1.6 s, building the shape for OCCT about 2 s) |

The live preview runs on the triangles as they were; the command on
release adds the detail.

## Part 4: joining squeezed edges (after 0.3.0)

`sculpt.collapse_near` runs after the brush when `detail` is given, on edges
within 1.25 radii of the stroke shorter than `JOIN` (0.4) times `detail`:

- Each pass takes the short edges shortest first. An edge is joined (both
  ends to its middle, the mask averaged) only if neither end is locked, the
  ends share exactly two neighbours (the link condition, so the surface
  stays a closed 2-manifold), no triangle left at either end turns over or
  nearly so, and neither end is frozen (mask 0.5 or more). The 1-rings of
  both ends are then locked for the pass, so each check sees current data.
- Up to six passes; then points no triangle uses are dropped and the rest
  renumbered in order (the mask goes with them), as the point-order rules
  in part 1 need.
- On a sphere with four PINCH strokes at detail 0.5 the points added and
  joined settle to about the same number per stroke (about 950 each), and
  the surface stays closed and consistently oriented.

## What is left

- Splitting and joining during the drag rather than only on release (the
  live preview moves the triangles as they were).
- The 1M-triangle goal of PLAN.md at interactive speed during a drag.
