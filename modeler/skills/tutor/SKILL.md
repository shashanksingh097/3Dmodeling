---
name: tutor
description: Teaching someone new to the app - the built-in tutorials (TUTORIAL), which button does what, units in numbers, the view cube and layouts. Use when the user is following a tutorial, says they are new, or asks how to do something by mouse.
commands: TUTORIAL, LAYOUT, VIEW, /UNITS, PROPS, REPEAT, WHY, HELP
---
# Teaching a new user

People new to the app learn fastest by doing each step themselves, with a
pointer to the right button. Do the work for them only when they ask.

## Steps

1. **Is a lesson running?** Call `tutorial`. It gives the step the user is
   on, its text, the checks (with `pass` and what was found) and `hints`
   (what **Show me** runs). Answer about *that* step: name the button and
   tab from the step text ("Model tab, Block…"), and the one value that is
   still wrong from the failed check ("the plate is 60 long, the step wants
   80: change `1.dx` in Properties").
2. **Not sure what they see?** `view_state` says where the 3D view looks
   from and what is in sight; `selection_numbers` what is picked. To turn
   the view: `VIEW, TOP` (or click the view cube), `VIEW, HOME`.
3. **Say it the mouse way first, then the command.** Every button only
   writes a command line, so give both: "click **Hole…** on the Features
   tab (or type `HOLE, plate, 15, 25, 10, 8`)".
4. **Numbers may carry units**: `25 mm`, `1/4 in`, `30 deg` work in any
   field and command; `/UNITS, IN, SHOW` shows inches without changing the
   model.
5. **Do it for them** only when asked ("show me", "do it"): run the step's
   `hints` (or `TUTORIAL, SHOW`). Then say what changed and that
   **Next** is ready (`TUTORIAL, NEXT`). Never skip a step for them with
   NEXT while its checks fail; NEXT refuses anyway.
6. **Room to work**: `LAYOUT, sketch` (a big view while sketching),
   `LAYOUT, sculpt` (everything put away), `LAYOUT, modelling` to go back;
   `LAYOUT, SAVE, name` keeps their own.
7. **Something failed?** Point at the red step and **Why?**, as in the
   fixing-failed-steps skill: the bar under the view says what went wrong
   and **Find fixes** tries the usual ones.

## Tutorials

| name | what it teaches |
| --- | --- |
| `first_part` | a shape, a name, changing a size in Properties, holes, fillets |
| `sketch_to_solid` | SKETCH, rectangle and circle, Finish sketch, EXTRUDE |
| `fix_a_step` | a red step, Why?, Find fixes, a parameter change that still works |

`TUTORIAL` lists them (with any the user wrote in their tutorials folder).
Starting one opens a new project: if theirs has unsaved changes, tell them
to save first (TUTORIAL refuses without `, NEW`).
