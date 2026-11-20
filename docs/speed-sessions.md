# Speed, long sessions and clear kernel messages (PLAN item 63)

## The benchmark

`python -m modeler perf` times the work people wait for, on models of a realistic
size, and notes how much memory the process holds after each case:

| Case | What it does | Full run (4-core Linux) |
|------|--------------|-------------------------|
| build plate | an 8 x 8 grid of holes cut in one step, rounded top edges, a pocket | 0.30 s |
| import STEP | that plate written to STEP and read back (337 KB) | 0.15 s |
| pick faces | finding which face was picked, for all 87 faces, 20 times | 0.01 s |
| drawing | `DRAWING` with four views and sizes | 0.24 s |
| save / open | `SAVE`, then `OPEN` in a new session (the history is replayed) | 0.001 s / 0.28 s |
| long history | 243 steps: a bar with 120 pins and holes added one by one | 5.2 s |
| rebuild after edit | `HIST, EDIT` of the first step: all 243 steps again | 5.2 s |

`--quick` runs smaller models (the test suite uses it), `--json file` writes the
numbers, and `--check` compares them with `docs/perf-budgets.json` and fails when a
case is over its budget. CI runs the full benchmark with `--check` on every push and
keeps the numbers as a build artifact. The budgets are about five times the times
above, so they catch a change that makes something several times slower, not noise.

## What the benchmark found

* **Cuts on a body with many faces had become slow.** Since PR #96 every boolean asks
  the kernel what each input face, edge and vertex made, to know where new edges came
  from (for picks that are repaired later). On a part with 300 holes that is a few
  thousand questions a cut, each answered "nothing" for the faces the cut did not
  touch. Those are now skipped: a face that is still in the result exactly as it was
  cannot have made anything (whatever was made on it would have split it). Same
  answers (tests/test_perf.py compares both ways), and:

  | | before | now |
  |-|--------|-----|
  | 300 holes cut one at a time in a plate | 94 s | 17 s |
  | the long history above (243 steps) | 21 s | 5.2 s |

* **Every step kept two copies of the state it started from.** The snapshot taken after
  a step and the one the next step takes before it are the same; now they are one.
  400 steps in one session grew the memory by 94 MB, now by 50 MB.

## The long-session test

`tests/test_long_session.py` squeezes hours of work into a minute: building, undoing
and redoing, editing an early step, saving, opening and drawing, ten times over in one
process. Memory stays flat after the first cycles, the undo list stays bounded and the
last cycles are not slower than the first. A second test adds 400 steps with an undo
and redo every third and checks memory and time grow slowly.

## Clear messages for kernel failures

Commands check their own inputs. What was left came out raw:
`StdFail_NotDone: GC_MakeArcOfCircle::Value() - no result`. Now every failure that is
not one of the program's own messages goes through `modeler/core/kernel_errors.py`:

* **The kernel refused** (any OCCT exception): the command, what that kind of failure
  usually means, what to try, and the kernel's own words in brackets for a bug report.
  `ARC: the geometry kernel could not make the shape from these values. Try values
  further from the limits (...). (kernel: StdFail_NotDone: GC_MakeArcOfCircle::Value() - no result)`
* **A file could not be used:** `EXPORT: could not use the file /x/y.step: Permission denied`.
* **A bug:** `SPHERE: this failed inside the program, which is a bug and not your
  mistake. Undo is safe; please report it with Help > Report a problem. (details: KeyError: 99)`.
* **Counts that would take hours or all the memory** are refused before they start
  (`GEAR` teeth, `HELIX`/`SPRING` turns, `POLYGON` sides, `STAR` points, `SMOOTH` steps,
  `SPATTERN` copies), with the most allowed: commands can declare `limits` per argument.

The model is left as it was in every case, and the step is not added to the history.

To find these, `tests/fuzz_examples.py` ran every command's example again with each
number of its command line changed to 0, -5 and a million (1530 runs in worker
processes, so a crash or hang costs one case). 10 answers needed fixing: 2 raw kernel
messages and 8 hangs on huge counts. `tests/test_kernel_messages.py` keeps them fixed,
and also runs every command with no arguments, a zero, ones and minus ones, in an empty
model and with a face picked, checking that no answer is a bare exception or a bug
(that found one: `GRAVITY, 0`).
