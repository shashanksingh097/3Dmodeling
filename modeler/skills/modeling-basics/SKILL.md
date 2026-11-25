---
name: modeling-basics
description: How to write any model as a script that stays editable - parameters first, names instead of IDs, SEL criteria instead of picks, ASSERT checks at the end. Use for every new part.
commands: BLOCK, CYL, NAME, SEL, UNION, SUBTRACT, FILLET, ASSERT, CHECK, PREVIEW, TOOLS
---
# Modelling basics

Every model is a script of commands; each top-level line is one history
step. A good script can be edited later by changing one number.

## Steps

1. **Parameters first.** Put every size the user gave in a line of its own
   (`W = 80`) at the top, and write the rest with them (`W/2`, `T + 1`).
   Then "make it wider" is one edit of one line.
2. **Name the bodies** right after making them: `NAME, LAST, plate`. Use the
   names in later steps, never the numbers 1, 2, 3, which move when earlier
   steps change.
3. **Select by what things are**, not by ID: `SEL, S, FACE, LOC, Z, T`
   (the face at height T), `SEL, S, FACE, NORMAL, 0,0,1`, `SEL, S, EDGE, AT,
   x,y,z`. If you only have an ID, `selector_for` gives the SEL lines.
   End with `SEL, NONE` so the next step starts clean.
   Whole groups in one line: `SEL, S, EDGE, LOOP, e` (the edges round a
   face that edge e is on), `SEL, S, EDGE, CHAIN, e` (edges joined to e
   without a corner, such as a rounded rim) and `SEL, S, FACE, TANGENT, f`
   (f and the faces that meet it smoothly). The user gets the same by
   double-clicking in the 3D view; a box pick writes `PICK, FACE, 3 5 7`.
4. **Booleans**: `UNION, a, b`, `SUBTRACT, a, b` (b is cut from a; the
   result keeps a's name), `INTERSECT`. Many tools at once: make them, then
   `SEL, S, BODY, ...` and `SUBTRACT, plate, SEL` (much faster).
5. **Fillets and chamfers last**, after the holes and cuts, on selected
   edges: `SEL, S, EDGE, ...` then `FILLET, 2`.
6. **Check at the end** with `ASSERT` lines that say what the user asked
   for. They stay in the script and fail loudly if a later edit breaks it.

```cmd
W = 80
D = 50
T = 10
BLOCK, 0, 0, 0, W, D, T
NAME, LAST, plate
SEL, S, EDGE, LOC, Z, T
FILLET, 2
SEL, NONE
ASSERT, VALID(plate)
ASSERT, BBOX(plate).dz, EQ, T, 0.01
```

## Check the result

* `VALID(b)`, `PIECES(b), EQ, 1` (one solid, nothing loose).
* Sizes: `BBOX(b).dx`, `.dy`, `.dz`, `VOL(b), BETWEEN, lo, hi`.
* `HOLES(b, d), EQ, n` for n holes of diameter d.
* In the assistant: `run` in the sandbox, then `check` with the same
  expectations, `describe_body` for what was made, then `propose_commands`.
* One step at a time: `preview_step` says what a step would add, change
  (volume before and after) or remove, or why it would fail and on which
  faces or edges, without running it. The user's forms show the same as a
  see-through ghost.
* "What can I do with this face?": `suggest_tools` lists the tools that
  fit the user's pick, the same list as their right-click menu.

## Mistakes to avoid

* Raw IDs in `SEL, S, FACE, ID, 7` or `SUBTRACT, 1, 2`: fine while typing,
  fragile in a script. `LINT` warns about them.
* A fillet before a shell or boolean: do it last, or the later step may
  fail on the rounded edges.
* Guessing a command's arguments: `command_help` gives them, with examples.
* Sizes without units in the answer: the model is in mm unless `/UNITS` says
  otherwise.
