# M4, part 1: reusable parts and instances

A part is a recipe with parameters. You define it once and place it many
times, and every copy follows the definition. As always, this is all
commands first; the GUI only builds and sends them. The full reference is
LANGUAGE.md section 17, and `scripts/bolted_plate.cmd` is an example.

| Area | Commands |
|------|----------|
| Define | `*PART, name, P=default, ...` ... `*ENDPART` (one history entry) |
| Place | `INST, part, x,y,z [, angle [, dx,dy,dz]] [, P=value ...]` |
| Take apart | `EXPLODE, b` |
| Library | `LIB, LOAD, name/file` · `LIBSAVE, part [, file]` · `LIST, PARTS` |
| From history | `HIST, PART, first, "last, name"` |
| GUI | Commands → Parts: "Place a part" (one box per part value, the default shown in grey), Explode, Load parts from library, Save part to library. History panel: select steps, right click, "Make a part from steps …" |

## Design

* **A part runs in a model of its own** (a fresh processor) with only its
  own parameters. So a part means the same thing in every project and in the
  library, and its body numbers do not depend on the main model. A part
  that needs an outside value says so in its error, and how to pass it.
* **Definitions are history entries and live in the undo state** (like
  macros), so undo, redo and history edits treat them like everything else.
  Editing the definition re-runs the steps after it, and every `INST`
  rebuilds.
* **Built shapes are cached** by (definition text, values given). The text is
  part of the key, so an edited definition can never reuse an old shape, and
  the cache needs no clearing. Placing the same bolt fifty times builds it
  once.
* **An instance is a normal body** with a record of its part and values
  (`Model.instances`, kept in snapshots). Moving or copying keeps the record;
  any change to its shape drops it, because the body then no longer is "a
  bolt".
* **Library files are kept with projects.** `LIB, LOAD` remembers which file
  it read, and `SAVE` stores it in the project like an imported file.
* **Making a part from steps** builds the new part first and changes the
  history only if that works, then puts back the name the steps gave their
  body, so later steps that use the name still work.

## Tests

`tests/test_parts.py` (headless): defaults that use other parameters,
placement (turn, then move, then the work plane), the cache, errors that say
what to do (unknown parameter, outside parameter, a part placing itself,
missing value), parts inside parts, editing a part updates all eight
copies, a passed-in parameter drives every copy, move/copy/boolean and
instances, explode, undo, the library round trip with a project opened
after the library file is gone, steps turned into a part (same volume, and
it still follows outside parameters), and the Place a part form.
`tests/test_forms_gui.py`: the part value boxes follow the chosen part, and
making a part from steps in the History panel.

## Next in M4

Threads and springs (a real thread on the bolt), sweeps along one and two
rails, spine lofts, text, and placement by mates.
