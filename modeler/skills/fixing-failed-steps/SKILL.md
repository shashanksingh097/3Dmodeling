---
name: fixing-failed-steps
description: What to do when a step fails or warns - read the message and hint, the usual fixes for fillets, shells, booleans, sweeps and lofts, CHECK and HEAL for broken bodies. Use when run, a history rebuild or the user reports an error.
commands: CHECK, HEAL, CLEAN, FILLET, SHELL, UNION, SUBTRACT, INTERSECT, PIPE, LOFT, HIST
---
# Fixing failed steps

A step that fails changes nothing: the model stays as it was before it, and
the message says why. Most messages already name the fix. Read it before
trying anything else.

## Steps

1. **Read the message and the hint** (the `run` tool gives both per step).
   After a history edit, later steps that now fail stay in the history,
   marked failed, and are skipped: `history` lists them.
   **Call `diagnose` first** (with the step number, or the failed line): it
   tries the usual fixes below on a copy of the model and gives the exact
   line for each one that works. People get the same from **Why?** on a
   failed step in the History panel.
2. **Find the cause in the model**, not by guessing: `describe_body` on the
   body, `describe_entities` on the faces or edges the step used,
   `section_profile` or `probe_ray` near the place the message names.
3. **Try the fix in the sandbox** (`sandbox`, `run`), check it, then hand it
   over as a history edit of the failing step (`propose_edits`).

## The usual fixes

| Message says | Fix |
|---|---|
| FILLET: "the largest radius that works here is about 9.9" | use a radius below that, or round fewer edges in one step |
| SHELL: "cannot be shelled with these faces open" | shell before filleting (move the fillet after the shell), or a thinner wall, or open fewer faces |
| INTERSECT: "no volume in common" | the bodies do not overlap: check them with `placement` or `contact` |
| UNION warning: "do not all touch ... separate pieces" | move one so they overlap a little (or `MATE`), then check `PIECES(b), EQ, 1` |
| SUBTRACT: "nothing is left" | the tool covers the whole body: wrong body order (`SUBTRACT, keep, tool`) or the tool is too big |
| PIPE / SWEEP: "runs into itself near t = 0.5 ... bends with a radius of about 9.45" | a smaller profile, a gentler bend (more spline points), or round a sharp corner of the path |
| LOFT: sections cut through each other or are out of order | list the sections in order along the shape, one per plane |
| SEL: "no FACE with ID 99" | IDs moved after an edit: select by what it is (`selector_for` on the right face) |
| A boolean warning about a tolerance | it worked; run `CHECK, b` and keep going if it is OK |

## Broken bodies

```cmd
BLOCK, 0, 0, 0, 40, 30, 10
NAME, LAST, part
CHECK, part
CLEAN, part
ASSERT, VALID(part)
```

`CHECK, b` says OK or what is wrong and what to try. `HEAL, b` (or
`HEAL, b, 0.01` to close gaps up to 0.01) repairs imported bodies; it
refuses when the repair would not give a valid body. `CLEAN, b` joins faces
split into pieces on one surface.

## Mistakes to avoid

* Retrying the same step with random values: the hint gives the limit.
* Working around a failure with steps on top (a second body, a `MOVE`)
  instead of fixing the step that failed.
* Saying a step worked without checking: `check` with `VALID(b)` and the
  sizes asked for.
