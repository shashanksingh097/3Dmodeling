# M3 leftovers: undo for history edits, skipping unchanged steps, sketch fillets and axes

The last open items of M3, done after 0.2.0 (PLAN.md, "After 0.1.0", item 6).

## Undo for history edits

Before, `UNDO` only moved the end of the history back: a `HIST, EDIT` could
not be taken back except by editing again. Now the processor keeps a list of
*actions* for `UNDO` and `REDO` to step through:

* **cursor** actions: a new entry (from n to n+1), or a roll back
  (`HIST, ROLLBACK, n`, from the current end to n, either way). Going back
  over entries keeps them with the action, so `REDO` can put them back even
  if a history edit undone in between had taken them out of the history.
* **hist** actions: any `HIST` edit (`EDIT`, `INSERT`, `DELETE`, `SUPPRESS`,
  `RESUME`, `MOVE`, `PART`, `REPLAY`). Each keeps `history_backup()` from
  before and after the edit (the entries, the saved states and the end), so
  undo and redo are instant: nothing re-runs.

`UNDO, n` takes back the last n actions, whatever they are; its message says
which (`undid 1 step and edit of entry 2`). A new step after an undo clears
the redo list, as before. A refused edit (no such entry, bad text) or a
cancelled rebuild puts everything back and is not an action. At most 100
history edits are kept for undo (each holds a copy of the history list; the
bodies themselves are shared, since they never change).

The History panel's **Roll back to here** and **Redo up to here** now send
`HIST, ROLLBACK, n`, so a roll back is one undo step however many entries it
passes, and the toolbar's Undo and Redo buttons follow `can_undo` / `can_redo`.

## Skipping unchanged steps on a rebuild

When an edit re-runs the history from entry k, every later entry used to run
again. Now an entry runs again only when something it looked at changed.

**What an entry looks at.** While an entry runs, the model's body table, its
face/edge/vertex tables (and the table of which entry made each ID) and the
parameters are swapped for `Track` dicts (`modeler/core/track.py`). A Track
is a dict that notes each key looked at. Anything that looks at a whole
table (iterating it, `len`, comparing, copying) marks the whole table read.
Finding a body by name looks at every name but only reads the body it finds.
What views do when they hear of a change does not count (tracking pauses
while the model's listeners run). The rest of the state (selection, named
sets, datums, sketches, layers, materials, instances, units, `LAST`, the next
free IDs, macros and part definitions) is small, and is compared whole.

**When it can be skipped.** An entry after k is skipped when it ran fine
last time and, comparing the state it starts from now with the one it
started from last time:

* every parameter it read has the same value,
* every body it read is the very same body object (bodies never change in
  place, so the same object means the same shape, name, layer and IDs),
* every face/edge/vertex ID it read belongs to the same body and place,
* if it looked at names, every body has the same name,
* and the rest of the state is equal.

Then it would do exactly what it did last time, so its changes are copied
over: the bodies, IDs and parameters it changed last time (old state after
minus old state before) are applied to the current state, and the rest of
the state is taken from its old result.

**Never skipped:** entries that failed last time (they run to say why), an
entry that runs a command reading something besides the model (`IMPORT`,
`LIB` and every other command with a file name, `RUN`, `PATTERN`, which
reads an older saved state), an entry whose tables were replaced while it
ran (it restored a snapshot itself), and the edited entry itself.
`HIST, REPLAY` runs everything, and `Processor.skip_unchanged = False`
turns skipping off.

**Checked.** For each of 21 example scripts, the first numeric parameters
were edited one at a time with skipping on and with it off, and the
results compared (each body's ID, name, layer, colour, volume, area and
face/edge/vertex IDs; parameters; selection; datums; sketches; each entry's
ok and message): 161 + 228 entries skipped, no differences.

**Speed.** A model with a threaded bolt, a 24-spoke wheel and a plate of 20
holes; editing the plate's width:

| | Time |
|---|---|
| every entry runs again | 1.64 s |
| unchanged entries reused | 0.03 s (4 entries run, 9 reused) |

In a single chain (each step works on the result of the one before) little
can be skipped, and the time is as before (in the 21 scripts above, the
edits took 22.6 s with skipping against 28.7 s without). Tracking itself
costs about 3% on a first run of a script (five example scripts: 2.12 s
against 2.06 s).

## Sketch fillet between a line and an arc

`SFILLET, 1.E, r` now rounds any corner where two curves end, each a line or
an arc. Two lines keep the old exact construction. With an arc
(`edit._fillet_round`):

* the fillet's centre is r from both curves: on the line moved r towards the
  side the other curve goes, and on the arc's circle grown by r (the other
  curve goes away from the circle) or shrunk by r (it heads into it);
* of the crossings of those two, the one whose touching points lie on the
  drawn parts of both curves, nearest the corner, is used;
* both curves are cut back to their touching points, the fillet is joined to
  them with coincident ends and tangent constraints, and the radius is a
  size; the corner stays as a construction point ON both curves, so sizes to
  it still hold (a line's length becomes a distance to it, as before).

Two curves that already join smoothly are refused, and a radius whose
fillet would run off either curve says it does not fit.

## Trimming and extending to the sketch axes

The sketch's H and V axes can cut: `STRIM, 3, u, v, AXES` lets them cut as
well as the other curves, and `SEXTEND, 3.E, V` extends to an axis. The new
end gets an ON constraint to the axis (`ON, 3.S, H`), so it stays on it. In
the GUI, **Axes cut** on the sketch toolbar makes the Trim tool send
`AXES`. Without it, trimming works as before (the axes do not cut), so a
line drawn across the origin is not cut there by surprise.

## Tests

* `tests/test_undo_skip.py`: undo and redo of every kind of history edit,
  mixed with new steps, a refused edit, a cancelled rebuild, roll back as
  one step; skipped counts for edits of a parameter, skipping giving the
  same model as `HIST, REPLAY` over a run of edits, entries that read a
  changed name, a file-reading entry, skipping turned off.
* `tests/test_sketch_edit.py`: line-arc fillets outside and inside the
  circle, an arc-arc fillet, a filleted profile extruded and its radius
  edited, errors; trim and extend to the axes, trim without `AXES`, the
  Trim tool's Axes cut and the Fillet tool on a line-arc corner.
