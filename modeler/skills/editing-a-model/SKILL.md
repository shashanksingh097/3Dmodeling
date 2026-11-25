---
name: editing-a-model
description: Change a model that already exists - a size, a hole position, a failing step - by editing its history (parameter lines first) instead of adding patches on top. Use for "make it wider", "move the holes", "change the bolt size".
commands: HIST, STEPS, UNDO, DIFF, ASSERT, HANDLES, SECTIONEDIT, PUSHPULL, UPTO, COPY, PASTE
---
# Editing a model

The history is the model. A change made by editing the step that made the
thing rebuilds everything after it, so the model stays one clean script.
Adding a `MOVE` or a `SUBTRACT` on top works once and breaks the next edit.

## Steps

1. **Find what controls it.** `history` (tool) or `HIST` lists the steps.
   `STEPS, b` lists the steps that made one body. A size is usually a
   parameter line (`W = 40`): look there first.
2. **Edit that one line**: `HIST, EDIT, n, "W = 50"`. The model rebuilds from
   step n; steps whose inputs did not change are reused, so this is quick.
   For a block, `\n` separates its lines.
3. **Other edits**: `HIST, INSERT, n, "text"` (before step n),
   `HIST, DELETE, n`, `HIST, SUPPRESS, n` / `RESUME`, `HIST, MOVE, n, to`.
4. **Look at what changed**: `DIFF` (or the `diff` tool), and run the
   script's `ASSERT` checks again (`check` tool).
5. **Drags in the view** write ordinary steps: an arrow on a body is
   `MOVE`, a ring `ROTATE` (about the body's middle), the pull arrow on
   faces `PUSHPULL`, a small arrow `MOVEFACE`. `HANDLES` (after a `PICK`)
   lists them, so you can write the same step a person's drag would. A drag
   on a body held by a `JOINT` moves the rest of the linkage too.
6. **Editing in a section**: `SECTIONEDIT, XY, 5` (a plane and an offset)
   lists the lines where the plane cuts the part, each with the `face`
   behind it and `push` (which way that face moves when pulled out). A
   person clicks a line and drags its arrow; you write the same steps:
   `PICK, FACE, id` then `PUSHPULL, d` (d > 0 moves the line along push).
   The report's `draw` gives the steps that start a sketch on the plane,
   to add or remove material with `EXTRUDE, sketch, d, ADD` or `CUT`.
   `SECTIONEDIT, OFF` ends it; it is not kept in the history.
7. **Up to another part**: `UPTO, b, FACE, n` moves body b along the
   face's normal until it touches it (`UPTO, b, VERTEX, n, Z, 2` along Z,
   2 short); `UPTO, FACES 6 7, FACE, n` pulls flat faces level with face n.
   A person gets the same from a drag that snaps to the other part (the
   label says "to a corner of body ...") or from Move up to… / Pull up to….
   Prefer one UPTO over working out a MOVE distance by hand.
8. **Copies**: a person's Ctrl+V writes `COPY, b, dx, dy, dz` (same
   project) or `PASTE, CLIP1, dx, dy, dz` (geometry kept from another
   project; `PASTE, LIST` lists it). Write COPY for copies you make.
9. In the assistant: try the edit with `round_trip` or in the sandbox,
   then hand it over with `propose_edits` (not `propose_commands`), so the
   user sees old and new text per step.

```cmd
W = 40
BLOCK, 0, 0, 0, W, 20, 5
NAME, LAST, bar
HIST, EDIT, 1, "W = 50"
ASSERT, BBOX(bar).dx, EQ, 50, 0.01
```

## Check the result

* Every step still ok: `history` shows no `failed`; a step that now fails
  stays in the list, marked, and is skipped until it is fixed.
* The script's own `ASSERT` lines pass, and a new one for the change.
* `round_trip` with the edit: IDs, picks and named sets came back.
* `vary` on the parameter (a few values) shows the model really follows it.

## Mistakes to avoid

* Patching on top (`MOVE` of a hole, a second `SUBTRACT`) instead of editing
  the step that made it.
* Editing the wrong copy of a number: if `40` appears in several steps but
  no parameter, add a parameter line at the top (`HIST, INSERT, 1, "W = 40"`)
  and edit the steps to use it.
* Counting steps by hand: comment lines belong to the step below them; take
  the numbers from `history`.
* Checks written with numbers (`EQ, 60`) fail after the edit; write them
  with the parameters (`EQ, W`) so they keep holding.
* History edits have Undo (`UNDO` takes the whole edit back).
