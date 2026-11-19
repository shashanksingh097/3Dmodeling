---
name: editing-a-model
description: Change a model that already exists - a size, a hole position, a failing step - by editing its history (parameter lines first) instead of adding patches on top. Use for "make it wider", "move the holes", "change the bolt size".
commands: HIST, STEPS, UNDO, DIFF, ASSERT
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
5. In the assistant: try the edit with `round_trip` or in the sandbox,
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
