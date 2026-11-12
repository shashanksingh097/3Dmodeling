# Faster repeated cuts, feature patterns, and cancelling long rebuilds

This works on risk 3 in PLAN.md (rebuilding long histories is slow). The
commands are in LANGUAGE.md section 21.

## Where the time went

Every cut makes OCCT rebuild the whole body. Cutting 300 holes one at a time
from a 160 x 160 plate takes 10.7 s. Because the history re-runs from the
edited step onwards, an edit near the start costs the same again.

| 300 holes in a plate | Time |
|----------------------|------|
| `CYL` + `SUBTRACT` 300 times (in a `*DO` loop) | 10.7 s |
| `SUBTRACT, plate, SEL` (all tools in one call, since PR #9) | 0.4 s |
| `ARRAY, LINEAR, pin, 15, ..., 20, ..., CUT, plate` | 0.28 s |
| `HOLE` then `PATTERN, LINEAR, plate, 1, 15, ..., 20, ...` | 0.41 s |
| `HIST, EDIT` of that `HOLE` (the pattern re-runs) | 0.37 s |

All four give the same volume to the last digit.

## Design

* **`ARRAY ... CUT, target`** places the copies as before, then sends the
  original and all copies to one `BRepAlgoAPI_Cut` through `combine` (so
  the result is checked like every boolean). The tool body is used up, as
  with `SUBTRACT`; `KEEP, ON` keeps it, hidden.
* **`PATTERN`** reads what a feature did as two solids: `after - before` (the
  material it added) and `before - after` (the material it took away).
  `before` is the body in the saved state from before the last `steps`
  history entries (the processor keeps a state after every entry, and now
  tells a running entry where it is in the history, also during a rebuild).
  The body is found by ID, or by name when a boolean gave it a new ID.
  Copies of both solids are put in with one fuse and one cut. Face IDs of
  the body carry through both, so picks on it stay good.
  This is how feature patterns work in other modelers too: each copy is the
  same change made at another place.
* **Progress and Cancel.** `Processor.progress` is called before each entry
  a rebuild re-runs. The GUI's `RebuildProgress` shows a modal dialog after
  0.5 s, with the step being run, and returns False when Cancel is pressed.
  The rebuild then stops, and `HIST` puts back the history, the saved states
  and the model exactly as they were before the edit.
  The rebuild still runs on the GUI thread, and the dialog lets the window
  repaint between steps. A worker thread would only help if the kernel
  released Python's lock during long calls, and a step cannot be stopped
  half way in any case.

## Left for later

Skipping steps whose inputs did not change. To do it safely, each step must
record which bodies and parameters it read. Then a step whose inputs are
all unchanged can reuse its old result. This is a larger change to the
processor. With the one-call cuts above, the slow case it would help
(hundreds of single cuts) has a fast way to write it.

## Tests

`tests/test_patterns.py`: a grid, a circle and a path of holes cut in one
step, with and without `KEEP`; feature patterns of a hole (a grid) and of a
boss with its hole (a circle), with exact volumes; an edit of the patterned
hole that the pattern follows; face IDs kept; errors; a cancelled rebuild
that leaves the history, the parameters and the model as they were; the
forms. `tests/test_forms_gui.py`: the progress dialog shows "Step 1 of 4",
and Cancel restores everything and closes it.
