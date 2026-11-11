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
  commands like `SEL, S, VOLU, , 3`, so selection sets can be scripted.
- **Undo/redo** works on the command history.

## Example script

```text
! simple bracket
BLOCK, 0,0,0, 20,10,2
CYL,   10,5,0, 3, 2
SUBTRACT, VOLU, 1, 2
SEL, S, VOLU, , 3
MOVE, 0,0,5
VIEW, ISO
```

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

## Quick start (M0 spike)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[test]"
python -m modeler scripts/m0_demo.cmd
```

See [docs/M0.md](docs/M0.md) for what to try and what to check on each OS.

## Requirements

- Python 3.10+
- PySide6
- OCP (`cadquery-ocp`, the Open CASCADE kernel; installs with pip)
