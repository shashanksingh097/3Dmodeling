# M2, last part: a fill-in form for every command

With this step a whole part can be made with the mouse alone. Every command
that changes the model has a form (or, for history, sketch drawing and view
commands, another GUI route), and every form only builds command text and
runs it through the same `MainWindow.execute` the command line uses. So the
History panel and the saved log look exactly as if the part had been typed,
and the log replays to the same part.

## Where the forms are

| Way in | What it does |
|--------|--------------|
| **Commands** menu | Every form, under 14 headings: Parameters, Solids, Sketch, Curves, Profiles, Shapes from curves, Combine, Features, Move and copy, Bodies, Datums, Select, Measure, Settings and files |
| **Commands…** button (Ctrl+K) | Find a command by name or by what it does, then open its form |
| **Block… / Cylinder… / Sphere…** | Now open their forms (they used to make a fixed size) |
| **Form** button by the command line (F2) | Opens the form for what you have typed so far, filled in; with nothing typed it asks for a command |
| History panel, right click, **Edit in form…** | Opens a step in its form; **Change step** sends `HIST, EDIT` and the model re-runs from there. Comments on the step are kept |
| Parameters panel, right click, **New parameter…** | Writes `NAME = value` |

## What a form does for you

* **Fields from the command's own description.** The argument list and help
  that drive `HELP` and the typing hints also make the forms, so a new
  command gets a form without GUI work. Three numbers in a row (`x, y, z`,
  `dx, dy, dz`, `nx, ny, nz`) show as one point field. Keywords are lists.
  Bodies, datum planes and axes, and sketches are lists of what the model
  has, and you can still type a name, an ID or an expression.
* **One form, several ways.** Commands whose arguments change with a keyword
  have a "How" list: `PLANE` (on a face, offset, point and normal, three
  points, turned about an axis, mid-plane, across an edge), `AXIS`, `POINT`,
  `ARRAY` (row or grid, around an axis, along a curve), `SEL` (by ID,
  direction, coordinate, size, type, body, edges of faces, all, none,
  invert), `SKETCH` (on a plane or a face), `DIST` and `ANGLE` (the two
  selected things, or two by ID).
* **The selection fills it in.** A body field starts with the picked body
  (or the body of a picked face); booleans take the first picked body and
  cut or join the rest; `HOLE` starts at the middle of the picked face
  (in work plane coordinates when a work plane is on); ID fields take the
  picked faces or edges. The form does not block the window, so you can
  pick something else and press **← Selection** next to a field.
* **What it will run, before it runs.** The command text is shown under the
  fields and kept up to date. Values that cannot work (an expression that
  does not evaluate, a body that does not exist, a required value left
  empty) are marked in red and named, and OK stays off until they are fixed.
  If the command itself fails, its message shows in the form and the form
  stays open.
* **Short commands.** Optional values left at their default are left out
  at the end of the line; gaps in the middle stay as empty arguments
  (`HOLE, plate, 20, 10, 5, 6, , CSINK, 12`). A point is written whole or
  not at all.
* **Run or OK.** Run keeps the form open for another one (a datum form then
  offers the next free name); OK runs and closes.
* Any field takes an expression: `W/2`, `2*R`, a parameter, `(1, 2, 3)`.

## How it is built

* `gui/forms.py` (no Qt, tested headless): the form descriptions, the menu
  headings, `build()` (values to command text), `parse()` (command text back
  to values, for Edit in form), `initial()` (starting values and the
  selection), `check()` (problems found before running), and
  `missing_forms()`, which a test keeps empty so a new command cannot be
  added without a form or a stated reason.
* `gui/form_dialog.py`: draws a form, the Commands menu and the command
  finder.
* `tests/test_forms.py`: every form builds and reads back; selection
  filling; and the housing example (`scripts/bracket_features.cmd`, with
  datums, draft, shell and three kinds of hole) rebuilt line by line
  through forms, giving the same volume. `tests/test_forms_gui.py` makes a
  plate with a counterbored hole, a grid of posts and a fillet by forms
  alone in the real window, and checks that the log replays to the same
  volume.

## Not in forms, and why

History and session commands (`UNDO`, `REDO`, `HIST`, `OPEN`, `SAVE`,
`NEW`, `RUN`) have toolbar buttons, file dialogs and the History panel.
`PICK`, `PICKMODE`, `VIEW` and `FIT` are what clicks and view buttons send.
Sketch geometry and constraints (`SLINE`, `SCON`, `SDIM` ...) are drawn with
the mouse in sketch mode. Loops, `*IF` blocks and macros are typed (or
edited as text from the History panel).
