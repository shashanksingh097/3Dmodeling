# M12: better assistant tools, skill files and help

Items 43 to 45 are built (see "What was built" at the end); 46 and 47
are still a plan. It follows on from
[M9-ai-tools.md](M9-ai-tools.md) (the tools), [M9-copilot.md](M9-copilot.md)
(the in-app assistant) and [mcp.md](mcp.md) (the same tools for outside
agents). The short version is PLAN.md items 43 to 47.

## 1. Where things stand (checked on main, 2026-11-19)

| Part | What is there |
|------|---------------|
| Tools | 28 Toolbox tools (learn, read, probe, sandbox, contact and design checks, `vary`, `round_trip`), plus the app-only `propose_commands`, `propose_edits`, `ask_pick`, `highlight`, `user_context`, `render`, `list_files`, `read_file` |
| First prompt | `first_prompt()` = how to work + `LANGUAGE_BASICS` + one line for every command: **24.7 KB** today for **244 commands** (it was 19 KB at PR #59), sent with every new chat |
| Providers | Copilot SDK (signed in per user), own key (OpenAI, Anthropic, Azure, Ollama, custom), the MCP server (`python -m modeler mcp`) |
| Help for people | the help browser (one page per command, examples from `scripts/`, opens the form), USER-GUIDE.md, LANGUAGE.md (110 sections), 47 example scripts |
| Benchmark | 10 tasks (flange, bracket, shelled box, pipe tee ...), exact checks; no published numbers yet |

## 2. What is missing

1. **The assistant knows commands, not workflows.** The catalogue says what
   `SHEET`, `FLANGE` and `UNFOLD` are, but not the order to use them, which
   checks prove the result, or the usual mistakes. The same is true for
   enclosures, assemblies with mates and motion, frames, moulds, drawings,
   scan to CAD and sculpting. Today it learns this by trial and error in the
   sandbox, which costs turns and tokens.
2. **The first prompt keeps growing.** Every new command adds a line to
   every chat. On Copilot Free the allowance is small, and small local
   models (Ollama) lose track in long prompts.
3. **The newer checks answer in prose.** `STRESS`, `GRAVITY`, `PRINTCHECK`,
   `MILL`, `BOM`, `CUTLIST`, `STACKUP`, `MOTION`, `PARTING`, `SHEETINFO` and
   `MASSPROP` return a text message through `run`. The assistant has to read
   numbers out of sentences, and none of them can be checked with `ASSERT`
   (there is no `MASS()`, `SAFETY()`, `MAXSTRESS()`, `OVERHANGS()` ... query).
4. **Planned tools never built** (M9-ai-tools.md section 8): `search_docs`,
   `parameters` (with who reads each one), `sketch_state`, `around`,
   `outline`, `since` revisions, `render_compare`, `render_detail`, and
   recognising fillets, chamfers, pockets, slots and bosses in
   `describe_body`.
5. **No help when a step fails.** The message and hint are there, but
   nothing tries the obvious fixes (a smaller fillet radius, another step
   order) or points to the right guide.
6. **The MCP server has empty `prompts/list` and `resources/list`.** Outside
   agents get the tools but none of the know-how.
7. **People have per-command help but no "how do I ..." guides,** and no way
   to go from a guide to the assistant or back.
8. **The benchmark covers only the early commands** and cannot tell whether
   a change to the prompt or the tools helped.

## 3. Skill files

A **skill** is one Markdown file that teaches one workflow. The format is the
open Agent Skills layout (`SKILL.md` with a short front matter), so the same
files work in our assistant, in Copilot, and in outside agents such as
Claude Code.

```
modeler/skills/
  sheet-metal/
    SKILL.md
    example.cmd        # runs in CI, ends with ASSERT lines
  enclosure/
    SKILL.md
    example.cmd
  ...
```

```markdown
---
name: sheet-metal
description: Bent sheet parts - base flange from a sketch, edge flanges, bends along a line, flat pattern to DXF. Use for brackets, covers, chassis.
commands: SHEET, FLANGE, SBEND, UNFOLD, SHEETINFO
---
## Steps
1. Parameters first: T (thickness), R (bend radius), K (K-factor).
...
## Check the result
ASSERT, VALID(b) ... SHEETINFO answers ...
## Mistakes to avoid
- A flange on an edge that is not on the sheet's outer face ...
```

Rules for every skill:

* **Short**: under about 4 KB, steps first, then checks, then mistakes. The
  longer reference stays in LANGUAGE.md and is reached by `search_docs`.
* **Checked in CI**: every command named in the file must exist in the
  registry, every command line in the file must pass `LINT`, and
  `example.cmd` must run and pass its `ASSERT` lines. So a skill cannot go
  stale when a command changes.
* **One source for people and the assistant**: the help browser shows the
  same files as guides (section 5).

### 3.1 How the assistant uses them

| Route | How |
|-------|-----|
| In-app (Copilot and own key) | the first prompt carries only the **skill index** (name and description, one line each, about 2 KB). New tools `list_skills()` and `load_skill(name)` return the index and a skill's text. The system prompt says: when a request matches a skill, load it before writing a script |
| MCP server | each skill is an MCP **prompt** (`prompts/list`, `prompts/get`) and a **resource** (`skill://sheet-metal`), and the two tools are there too, for clients that use only tools |
| Outside agents with their own skill folders | `python -m modeler skills export --to <folder>` writes the skill folders with a line that says to start the MCP server, for example into `.claude/skills/` for Claude Code |
| Copilot's own skill loading | SDK 1.0.35 has `skill_directories` and `skill_provider`, but `empty` mode turns skills off by default and our session allows only our own tools. Worth a test (item 47), but our own tools stay the main route because they work for every provider |

### 3.2 The user's own skills

A user can keep their own skill files (company rules, "our standard
bracket", preferred materials) in a `skills/` folder in the project folder or
in the app's settings folder. Settings lists every skill with an on/off
switch; skills from the project folder are marked as such. They are read like
the built-in ones and are only ever text for the assistant: they cannot run
anything by themselves, and scripts they lead to still go through
`propose_commands`.

### 3.3 The first set of skills

| Skill | Covers |
|-------|--------|
| `modeling-basics` | a parametric script: parameters first, names over IDs, `SEL` criteria over picks, `ASSERT` at the end |
| `editing-a-model` | change sizes through `HIST, EDIT` of parameter lines, not steps on top; `round_trip` after |
| `fixing-failed-steps` | reading the message and hint, the usual fixes for fillets, shells, booleans and lofts, `CHECK`/`HEAL` |
| `sketch-to-solid` | sketch, constrain until no freedom is left, `EXTRUDE`/`REVOLVE`, sketch on a face |
| `holes-and-patterns` | `HOLE` (counterbore, countersink, thread), `PATTERN`, `ARRAY ... CUT`, `HOLES()` checks |
| `enclosure` | `SHELL`, `LIP`/groove, `BOSS`, `SNAP`, `VENT`, `RIB`, draft, two halves |
| `sheet-metal` | `SHEET`, `FLANGE`, `SBEND`, `UNFOLD` |
| `fasteners-and-threads` | `FASTENER`, `THREAD`, nut phase, `CLEARANCE`, `FITS` |
| `gears-and-cams` | `GEAR` (spur, helical, bevel, worm), centre distance, `CAM`, `CAMLIFT()` |
| `assembly-and-motion` | parts and links, `MATE`, `DRIVE`, `MOTION`, `GRAVITY`, `CONTACT`, `BOM` |
| `frames-and-welds` | `MEMBER`, `CUTLIST`, `WELD` |
| `curves-and-surfaces` | `LOFT`, `SWEEP` laws, `RAILSWEEP`, `SPINELOFT`, NURBS, `ANALYZE` |
| `scan-to-cad` | mesh import, `SEGMENT`, `RECONSTRUCT`, `FITSURF` |
| `sculpting` | `SCULPT`, masks, `REMESH`, when text tools do not help and `render` does |
| `strength-and-weight` | `STRESS`, `TOPOPT`, materials, safety factor, what the quick check can and cannot say |
| `manufacturing` | `PRINTCHECK`, `MILL`, `PARTING`, `MOLD` |
| `drawings-and-tolerances` | `DRAWING` sheets, `NOTE`, GD&T, `STACKUP`, `FITS` |

## 4. Better tools

### 4.1 Answers as data, and queries to check them

Every analysis command keeps its message for people and also returns a
**report** (a dict) that `run` passes on as `report` next to `msg`, and that
the MCP server returns as structured content. New queries make the main
numbers usable in `ASSERT` and in scripts:

| Command | Report holds | New queries |
|---------|--------------|-------------|
| `MASSPROP` | volume, area, mass, centre, inertia | `MASS(b)` |
| `STRESS` | largest stress and where, largest deflection, safety factor | `MAXSTRESS()`, `SAFETY()`, `DEFLECT()` |
| `GRAVITY` | grounded and floating parts, tipping angle | `FLOATING()`, `TIPANGLE()` |
| `PRINTCHECK` | overhang faces and area, thin walls, hollows | `OVERHANGS(b, angle)` |
| `MILL` | operations, path length, time | |
| `BOM`, `CUTLIST` | rows | `QTY(name)` |
| `STACKUP` | worst case and RSS range | |
| `MOTION` | clashes with their positions | `CLASHES()` |
| `SHEETINFO`, `PARTING` | bends, flat size; faces needing draft | |

### 4.2 The tools planned in M9 and not built

* `search_docs(query)`: the matching parts of LANGUAGE.md, USER-GUIDE.md,
  the skills and the example scripts, trimmed. Plain keyword ranking, no
  network and no extra package.
* `parameters()`: every parameter, its value, the line that sets it and the
  lines that read it. This is what makes "make it 10 mm wider" a one-line
  edit.
* `sketch_state(name)`: entities, constraints, freedom left, conflicts,
  closed profiles.
* `around(entity, depth)`, `outline(body, view)`, `since` on the read tools.
* `describe_body` also names fillets and chamfers by size, pockets, slots
  and bosses.
* `render_compare(before, after)` and `render_detail(entity)` with ID
  labels, for the picture fallback.

### 4.3 Fixing failed steps

`diagnose(entry)` looks at a failed or warned history step and, in a
sandbox, tries the fixes that usually work for that command (a fillet radius
below the limit the hint gives, the fillet before the shell, a nudge for a
boolean on touching faces, `HEAL` on an import) and reports which ones pass,
with the edit to make. The same is behind a **Why?** button on a failed step
(section 5), which works without an AI: it shows the message, the hint, what
`diagnose` found, and the guide for that command.

### 4.4 A smaller first prompt

With skills and `search_docs` in place, the first prompt can carry the
language basics, the skill index and command **names by family** (about
8 KB instead of 25 KB). The full catalogue stays one tool call away
(`find_commands`, `command_help`) and as a setting (**Full command list in
the first prompt**). The switch is made only if the benchmark (section 6)
shows it does no harm.

## 5. Help for people

* **Guides in the help browser**: a Guides list beside Commands, made from
  the same skill files. Each guide has **Open example** (runs
  `example.cmd` in a new model), the commands as links to their pages, and
  **Ask the assistant** (opens the chat with the guide loaded).
* **Why? on failures**: a failed step in the history or the command line
  gets a Why? link (section 4.3).
* **From a command to a guide**: each command page lists the guides that
  use it.
* All of this works offline and with the assistant off.

## 6. Benchmark

* Grow from 10 to about 25 tasks, adding one per skill area (sheet metal
  bracket, enclosure with snaps, gear pair at the right centre distance, a
  frame with a cut list, a print check, an edit of an existing model, a
  failed step to fix, a request that must be refused).
* Run modes: skills on or off, full or small first prompt. Record success,
  turns, tokens, tool calls and pictures.
* CI runs every reference script (no AI), so the tasks stay valid.
* Numbers for a few models still need a signed-in run by the owner.

## 7. Safety

* Skills are text for the assistant. Built-in ones ship with the app; the
  user's own come only from the folders they chose. Neither changes what
  the tools may do: the model still changes only through proposals.
* `skills export` writes only to the folder the user names.
* Never put keys or personal data in a skill; the CI check refuses files
  that look like keys.

## 8. Build order

| Item | Delivers |
|------|----------|
| 43 | skill format, loader and CI check; `list_skills`, `load_skill`; skill index in the first prompt; MCP prompts and resources; `skills export`; the first six skills (`modeling-basics`, `editing-a-model`, `fixing-failed-steps`, `sketch-to-solid`, `holes-and-patterns`, `enclosure`) |
| 44 | the other skills; Guides in the help browser; the user's own skill folders with on/off in Settings |
| 45 | reports and new queries for the analysis commands (4.1); `search_docs`, `parameters`, `sketch_state` |
| 46 | `diagnose` and the Why? button; `around`, `outline`, more feature recognition, `render_compare`, `render_detail` |
| 47 | benchmark to about 25 tasks with run modes; the small first prompt behind a setting; a test of Copilot's own skill loading |

## 9. What was built (items 43 to 45, 2026-11-19)

- **17 skills** in `modeler/skills/`: modeling-basics, editing-a-model,
  fixing-failed-steps, sketch-to-solid, holes-and-patterns, enclosure,
  sheet-metal, fasteners-and-threads, gears-and-cams, assembly-and-motion,
  frames-and-welds, curves-and-surfaces, scan-to-cad, sculpting,
  strength-and-weight, manufacturing, drawings-and-tolerances. Each has a
  `SKILL.md` (front matter `name`, `description`, `commands`) and an
  `example.cmd` that ends in `ASSERT` lines.
- **`modeler/ai/skills.py`**: reading (built-in, the user's skills folder,
  `MODELER_SKILLS`, folders added in the app, a project's own `skills/`
  folder; a later one replaces an earlier one of the same name), switching
  skills off, `check` (name matches the folder, size, no keys or tokens,
  every command exists, every `cmd` block passes `LINT`, the example runs
  and no step of it fails afterwards) and `export`.
  `python -m modeler skills list | show NAME | check | export --to DIR`.
  `tests/test_skills.py` runs every example.
- **Assistant tools**: `list_skills`, `load_skill`, `search_docs` (BM25
  over LANGUAGE.md, USER-GUIDE.md, the skills and the example scripts, no
  network), `parameters` (value, the step that sets it with a ready
  `HIST, EDIT` line, the steps that read it) and `sketch_state` (geometry,
  constraints, freedom left, repeated constraints, profiles). The first
  prompt carries a one-line index of the skills.
- **MCP server**: each skill is a prompt (`prompts/get` with an optional
  `request`) and two resources (`skill://name`, `skill://name/example.cmd`).
- **Answers as data**: `STRESS`, `PRINTCHECK`, `GRAVITY`, `MOTION`, `BOM`,
  `CUTLIST`, `MASSPROP`, `MILL`, `PARTING`, `SHEETINFO` and `STACKUP` put a
  report on their result; the `run` tool shows it on the step. New queries
  `MASS`, `SAFETY`, `MAXSTRESS`, `DEFLECT`, `OVERHANGS`, `FLOATING`,
  `TIPANGLE` and `QTY` run the checks quietly and keep the answer until the
  model changes.
- **For people**: Help > Guides shows the skills in the help browser, with
  links to every command they use (and "Guides that use it" on command
  pages), Open example and Ask the assistant. Help > Assistant skills… lists
  the skills with an on/off box, the user's own folders and Check skills.

Not done yet: the smaller first prompt (4.4) waits for the benchmark in
item 47, and Copilot's own `skill_directories` stays unused because our
sessions only allow our own tools; `load_skill` does the same job.
