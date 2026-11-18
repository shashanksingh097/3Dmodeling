# Rebuilds that don't freeze the window (PLAN item 16, part 1)

Before this, a long history edit (for example a change near the start of the
car body, 215 steps, about 35 s) ran on the window's own thread. The progress
dialog let the window repaint between steps, but every kernel step froze it,
and nothing could be looked at while it ran.

## Why a process, not a thread

The kernel bindings keep Python's interpreter lock for the whole of every
kernel call. Measured: while one thread meshed a body for 2.0 s, a second
thread that only counted time could not run at all for 2.0 s. So a worker
thread would freeze the window just the same. A second process has its own
lock.

## How it works

- `modeler/core/transfer.py` packs everything a processor holds (history,
  saved states for undo, parameters, parts, the model with its bodies,
  sketches, layers, masks...) into bytes and back. Kernel shapes don't
  pickle, so they are collected while pickling and written together as one
  compound in the kernel's own binary format, which keeps shared shapes
  shared and keeps their meshes. Things that belong to the window (the view,
  listeners, the progress callback) stay behind. Every example script round
  trips; the car body (the biggest) is 45 MB, 1.4 s to pack and 0.65 s to
  unpack.
- `modeler/core/helper.py` is the helper process (`python -m
  modeler.core.helper`, or `3Dmodeling-cli rebuild-helper` in the packaged
  app). It gets the state and the command, runs it on its own processor,
  reports each step, and sends the new state back. It stays running between
  rebuilds, so only the first one pays the second it takes to start; the
  window starts it as soon as the history has taken a second or more to
  build.
- Each history entry now remembers how long it took (`Entry.seconds`).
- `modeler/gui/offload.py`: `MainWindow.execute` sends a `HIST` edit (EDIT,
  INSERT, DELETE, SUPPRESS, RESUME, MOVE, REPLAY, PART) to the helper when
  the steps it re-runs took 1 s or more last time. Not while a sketch is
  open or a block is being typed.

## What you see

A small dialog shows the step being re-run and has Cancel. It does not
block the window: the view can be turned and zoomed, and panels can be
read. Commands typed or clicked meanwhile are refused with a note in the
status bar. When the helper is done, the window takes over its result: the
model, history and undo are exactly what a run in the window gives, and
UNDO takes the edit back in one step. Cancel stops the helper at once (even
in the middle of a kernel step, which the old Cancel could not) and the
window's model was never touched. If the helper cannot start or breaks, the
edit just runs in the window the old way.

Measured on the car body, `HIST, REPLAY`: 37 s, and the window's longest
pause was 0.34 s (packing the state at the start and taking it back at the
end).

![rebuild running](../examples/rebuild-running.png)

## Left for later

- Packing a very big model takes about a second at the start; sending only
  what changed since the last job would remove it.
- Other long single commands (a big boolean, `REMESH`) still run in the
  window; the same helper could take them.
- The other parts of item 16: fitting smooth surfaces to meshes, and
  1M-triangle sculpting.
