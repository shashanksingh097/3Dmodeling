# The sweep editor

This is the last M3 item. It meets the last part of the M3 exit test: drag a
twist handle on a sweep and the law updates. How to use it is in
LANGUAGE.md section 9 ("The sweep editor").

## Pieces

* **`TABLE(t, t0, v0, t1, v1, ...)`** (lang/table.py) is a law given as
  values at stations. The values are joined by a monotone cubic
  (Fritsch-Carlson PCHIP): it is smooth, passes through every station, and
  never overshoots between two of them. A twist of 40, 20, 8 never leaves
  8..40. Before the first station and after the last one, the end values
  hold. It is an ordinary function, so it needs nothing new in `SWEEP`.
* **`SweepEdit`** (gui/sweep_edit.py, no Qt) is opened on one `SWEEP`
  history step.
  * It reads the step back through the `SWEEP` form.
  * It looks up the profile and the path in the saved state from just
    before the step, with the same rules the step used, so `LAST`, `LAST-1`
    and parameters work.
  * It keeps twist and scale as stations. A law written as a formula stays a
    formula until it is first dragged, then becomes five stations sampled
    from it.
  * `section(t)` places the profile at `t` with the same frames and station
    matrix as `SWEEP` itself.
  * `preview()` runs the same section sweep as the command.
  * `entry_text()` writes the new line and keeps the step's comments.
* **The window** (gui/sweep_editor.py) shows one `LawGraph` per law. The
  graphs are drawn with QPainter, with handles you can drag, add and remove.
  There is also a t slider and a readout. The 3D view shows ghosts that are
  not bodies (`OccViewport.set_ghosts`): the see-through sweep and the pink
  section. They are never pickable, and they go away when the editor closes.
  * The section follows every mouse move, which takes under a millisecond.
  * The sweep preview is rebuilt when a drag ends (about 25 ms for the blade
    example).
* **Apply** sends `HIST, EDIT`. The model changes only through the history,
  and Undo and Cancel work as for any edit.

## Not yet

* Handles in the 3D view: you drag on the graphs, not on the model.
* The same editor for `MORPH`, `PIPE` (radius law) and `RAILSWEEP`
  (thickness law), and for the `sx`, `sy`, `ox` and `oy` laws of `SWEEP`.
  The design carries over: each one is a law in `t` read through its form.

## Tests

`tests/test_sweep_editor.py`:
* `TABLE`: goes through its stations, holds its ends, never overshoots,
  gives errors for bad input, and writes and reads back the same text.
* A sweep with a table law.
* `SweepEdit`: turns formulas into stations; moves, adds and removes
  handles (with limits); the section at `t = 1` has the right size, place
  and turn; the preview volume matches the command's volume; the curves are
  read as they were before the step; comments are kept.

`tests/test_forms_gui.py`: open the editor, check that the ghosts are
shown, drag the tip handle from 90 to 30 degrees with mouse events, read
the slider, Apply, and check that the history line is a `TABLE` law and the
ghosts are gone.
