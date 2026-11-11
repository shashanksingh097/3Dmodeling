# 3Dmodeling

A PySide6 desktop application for 3D modeling where **every action is a command**.

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

## Planned architecture

| Layer | Responsibility |
|-------|----------------|
| `commands/` | Command parser, registry, and one handler per command (`BLOCK`, `SEL`, `MOVE`, ...) |
| `core/` | Model / geometry kernel, entity IDs, selection sets, undo stack |
| `gui/` | PySide6 main window, menus, toolbars, command line widget, log panel |
| `viewport/` | 3D rendering and picking (picks emit commands, never mutate the model) |
| `scripts/` | Example `.cmd` scripts |
| `ai/` | *(later)* AI chat assistant that helps users and can generate commands |

## Roadmap

The full product and technical plan (kernel choice, command language,
feature catalogue, milestones) is in [docs/PLAN.md](docs/PLAN.md).
Short version:

1. Command parser, registry, and processor with logging
2. Minimal model: points, primitives (block, cylinder, sphere), entity IDs
3. PySide6 window with command line, log panel, and 3D viewport
4. Selection commands and viewport picking
5. Transform and boolean commands, undo/redo
6. Save/load as command scripts
7. AI chat box that explains commands and drafts scripts from plain language

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[test]"
python -m modeler scripts/flange.cmd                   # GUI with a parametric flange
python -m modeler run scripts/flange.cmd -D N_BOLTS=8  # same script, headless
```

Status: M0 (viewer and picking, [docs/M0.md](docs/M0.md)), M1 (command
core, [docs/M1.md](docs/M1.md)) and M2 (shapes on curves,
[docs/M2.md](docs/M2.md), and a fill-in form for every command so a part can
be made by mouse alone, [docs/M2-forms.md](docs/M2-forms.md)) are in. M3 so far: datums and part features
([docs/M3.md](docs/M3.md)) and the sketcher with `EXTRUDE` and `REVOLVE`
([docs/M3-sketcher.md](docs/M3-sketcher.md)).

## Requirements

- Python 3.10+
- PySide6
- OCP (`cadquery-ocp`, the Open CASCADE kernel; installs with pip)
- numpy (the sketch solver)
