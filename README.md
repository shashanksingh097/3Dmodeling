# 3Dmodeling

A desktop 3D modeler for solid parts where **every action is a command**.

**Download:** [latest release](https://github.com/shashanksingh097/3Dmodeling/releases) for
Windows, macOS (Apple silicon) and Linux, no Python needed.
**Learn it:** the [user guide](docs/USER-GUIDE.md), the [examples with pictures](docs/EXAMPLES.md), or **Help > Getting started** in the app.

Anything you do in the GUI (creating a block, selecting a face, moving a node,
deleting an entity, changing the view) is turned into a plain-text command and
executed by a single command processor. That means anything you can click, you
can also type or script.

## Core idea

```
 GUI event ──► builds command text ──┐
                                     ├──► Command Processor ──► Model ──► Viewport refresh
 Command line / script file ─────────┘          │
                                                 └──► Command log (replayable script)
```

- **One path for all changes.** The GUI never edits the model directly. It
  emits a command such as `BLOCK, 0,0,0, 10,5,2` and hands it to the processor,
  exactly as if the user had typed it.
- **Everything is logged.** Every executed command is appended to a session log.
  Replaying the log rebuilds the model from scratch.
- **Scripts are first-class.** A `.cmd` file is just a list of commands. Running
  it is the same as clicking through the GUI.
- **Selection is a command too.** Picking entities in the viewport produces
  commands like `PICK, FACE, 12` or `SEL, S, FACE, NORMAL, 0,0,1`, so selections can be scripted.
- **Undo/redo** works on the command history, and any old step can be edited: the model re-runs from there.

## Example script

```text
! plate with a row of holes; change W or N and it rebuilds
W = 60
N = 4
BLOCK, 0,0,0, W,20,5
NAME, LAST, plate
*MACRO, drill, x, y, d=6
  CYL, x, y, -1, d/2, 7
  SUBTRACT, plate, LAST
*END
*DO, i, 1, N
  drill, i*W/(N+1), 10
*ENDDO
SEL, S, FACE, NORMAL, 0,0,1      ! the top face, chosen by meaning, not number
CM, top, FACE
```

The language (parameters, expressions, loops, conditions, macros, selection
by criteria, the editable history) is described in
[docs/LANGUAGE.md](docs/LANGUAGE.md).

## What it can do (0.1)

- **Model by mouse or by text.** Toolbars, a fill-in form for every command, picking faces and edges in the 3D view, or a command line with completion and argument hints. Scripts with parameters, loops, conditions and your own commands.
- **Edit any step later.** The history panel holds every step; edit, insert, suppress or delete one and the model rebuilds. Picks follow the faces they meant.
- **Sketches** with constraints and sizes, trim, extend, fillet, offset, mirror, pattern; extrude and revolve.
- **Features:** holes (plain, counterbore, countersink, threaded), fillets, chamfers, shell, draft, offset, split, push/pull and delete faces, patterns of features.
- **Shapes from curves:** loft, sweep with twist and scale laws (and a graphical sweep editor), morph, pipe, rail sweeps, spine lofts, real ISO threads, springs, text, shapes from equations.
- **Parts** with parameters, placed many times, and a part library.
- **Layers, colours, materials**, mass properties, distances, angles, clash checks, section views.
- **Results you can trust:** every operation is checked, and a broken result is refused with a reason.
- **Files:** projects (`.m3d`) with autosave and recovery; STEP, IGES, BREP, STL import; STEP, STL, BREP export.
- **Text tools for an AI assistant** (describe a body, probe it with rays, check expectations), ready for the chat panel in a later release.

## Install from source

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[test]"
python -m modeler                                      # the app
python -m modeler scripts/flange.cmd                   # the app with a parametric flange
python -m modeler run scripts/flange.cmd -D N_BOLTS=8  # same script, headless
python -m pytest -q                                    # tests
```

Requirements: Python 3.10+, PySide6, `cadquery-ocp` (the Open CASCADE
kernel, installs with pip) and numpy.

## Code layout

| Folder | What is in it |
|--------|----------------|
| `modeler/lang/` | parser, expressions, scripts |
| `modeler/commands/` | the processor, history, and one handler per command |
| `modeler/core/` | model, entity IDs, references that survive edits |
| `modeler/geometry/` | kernel work: sweeps, checks, features, recognition |
| `modeler/sketch/` | the 2D sketcher and its constraint solver |
| `modeler/viewport/` | 3D view and picking (picks emit commands, never change the model) |
| `modeler/gui/` | main window, forms, panels, menus |
| `modeler/ai/` | text tools for an AI assistant |
| `scripts/` | example scripts (also under **File > Open example**) |
| `packaging/` | the desktop build recipe ([docs/RELEASING.md](docs/RELEASING.md)) |

## Documents

- [User guide](docs/USER-GUIDE.md), [examples with pictures](docs/EXAMPLES.md) and [command language](docs/LANGUAGE.md)
- [Changelog](CHANGELOG.md) and [how releases are made](docs/RELEASING.md)
- [Product and technical plan](docs/PLAN.md), with what comes after 0.1
- Design notes per milestone: [M0](docs/M0.md), [M1](docs/M1.md), [M2](docs/M2.md), [forms](docs/M2-forms.md), [M3](docs/M3.md), [sketcher](docs/M3-sketcher.md), [sketch tools](docs/M3-sketch-tools.md), [sweep editor](docs/M3-sweep-editor.md), [parts](docs/M4-parts.md), [threads](docs/M4-threads.md), [rails](docs/M4-rails.md), [M4 shapes](docs/M4-shapes.md), [speed](docs/speed-patterns.md), [AI tools](docs/M9-ai-tools.md)
