# M3: sketch editing tools

Trim, extend, fillet, offset, mirror, pattern and projected body edges in
the sketcher. The commands are in LANGUAGE.md section 16 ("Editing sketch
geometry"); `scripts/sketch_tools.cmd` draws a plate with all of them.

## What was built

| Command | Mouse | Code |
|---------|-------|------|
| `STRIM, curve, u, v` | **Trim** tool (T): the piece is shown before the click | `sketch/edit.py` `trim`, `trim_piece` |
| `SEXTEND, end [, to]` | **Extend** tool (E): click near an end | `extend` |
| `SFILLET, corner..., r` | **Fillet** tool (F): click a corner | `fillet` |
| `SOFFSET, d, curves...` | **Offset…** on the selection | `offset` |
| `SMIRROR, axis, geometry...` | **Mirror…** on the selection | `mirror` |
| `SPATTERN, LINEAR/POLAR, ...` | **Pattern…** on the selection | `pattern` |
| `SPROJECT, edges / FACE, faces / SEL` | **Project…** (offers the picked edges or faces) | `commands/sketch_edit_handlers.py` |

All of it is plain 2D Python except SPROJECT, which reads the edges from
the kernel. Every step is one history entry, like the rest of the sketcher.

## Design decisions

**The sketch keeps meaning what was asked.** Each tool rewrites the
constraints it touches instead of leaving the user a broken sketch:

* A trimmed or extended end gets an `ON` constraint to the curve that cut
  it. Constraints that held the part that went (a length, a fix, a
  midpoint) are dropped and named in the output.
* A fillet keeps the corner as a construction point `ON` both lines, and
  every constraint that named either line end at the corner now names that
  point. A `LENGTH` of a filleted line becomes a `DIST` from the corner point
  to the far end, so a fully defined sketch stays fully defined (tested).
  The radius is a `RADIUS` size made by the `SFILLET` step; double-clicking
  it, or the **Sizes of sketch** table, edits the radius in that step.
* Offsets and copies get two new internal constraint kinds, `OFFSET` and
  `COPY`, so they follow their originals when a later step changes them.
  They are not offered in `SCON`; they come only from the tools.

**Offset equations are chosen so the solver can tell joints apart.** A
line's offset holds both its ends at the signed distance from the original
line; an arc's offset keeps the centre and the radius plus the distance.
At a sharp corner the two offset pieces are joined with `COINCIDENT`, which
is well posed because the offset curves cross. At a smooth (tangent) joint
the two offset curves only touch, and asking the solver for a point on both
would be a double root (the Jacobian loses rank, so the degrees of freedom
come out wrong). There, each piece's end is instead held square across from
the original joint, which fixes it exactly. The same goes for the free ends
of an open chain. The result: a rounded rectangle offset by 3 is fully
defined, with no repeated constraints.

**Copies are held point by point.** A `COPY` constraint puts each point of
the copy where the move puts the original's point (a mirror reads the
mirror line from the sketch, so moving the line moves the copies; a polar
pattern turns about a sketch point). Copies of joined curves are not tied
to each other: they are already placed exactly, and ties would only repeat.

**Repeats made by a tool are not reported.** The solver already blames a
constraint only when none of its equations add anything new. A fillet's
corner point `ON` both lines can still repeat what a user's constraint
says (for example a `SYMMETRIC` that also keeps the side upright). Such a
repeat is harmless and not the user's to clean up, so constraints a tool
added (`auto`) are left out of the "only repeat other constraints"
warning. The degrees of freedom are counted from the rank as before.

**Projected edges are fixed and remade on rebuild.** `SPROJECT` makes
lines, circles and arcs (or a chain of 24 lines for other curves) with a
`FIX` on each. Being a history step, it runs again whenever an earlier step
changes, so a sketch drawn round a projected hole follows the hole (tested
by growing the hole with `HIST, EDIT`).

## Checks

* `tests/test_sketch_edit.py`: 18 tests. Fillet volume and fully defined
  state, radius edit through the history, sizes to the corner survive,
  offsets of closed and open chains and circles, offset following a later
  size, trim of middle, end, circle and lone curve, trimmed ends following
  the cutting curve, extend, mirror following a drag, linear and polar
  patterns keeping radii, patterned holes extruded, projection of a face
  and its rebuild, and the mouse tools and selection buttons.
* `tests/test_sketch_gui.py`: a real window: Fillet and Trim by mouse,
  Offset from the toolbar.
* Run on OCP 8 (py3.13) and OCP 7.9 (py3.10).

Screenshots are in the project files under `m3d/`.

## Left

* A fillet between a line and an arc, or two arcs (only two lines now).
* Trimming against the sketch axes H and V (they do not cut now).
* An offset of a chain that crosses itself.
