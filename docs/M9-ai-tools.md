# M9: tools for the AI assistant

This is the design of the tools the in-app AI assistant uses to build and
check models. The summary is in PLAN.md section 5.8.

**Status.** Most of step M9a and the first part of M9b (section 7) are
built: see "What is built" at the end. The rest is still a plan.

## 1. The idea

An AI that builds a model has to know whether what it built is right. The
obvious way is to look at a picture of the viewport, but pictures are
expensive (each one costs on the order of a thousand tokens and more at
high resolution), slow, and poor at exact answers: a picture cannot tell
whether a hole is 6.0 or 6.4 mm, whether two bodies touch, or whether a
fillet left an invalid shape.

The modeler already knows all of that exactly. So the assistant gets
**text tools that answer questions about the model the way a careful
engineer would check it**: what bodies exist and how big they are, which
holes a body has, what a cut through it looks like, whether a ray from a
point hits material, whether a set of expected values holds, what changed
since the last step. It runs its work in a **sandbox copy** of the model,
tests it there, and only then proposes the commands to the user.

Pictures stay available as a fallback for the questions text cannot
answer well (looks, style, organic shapes, "this looks wrong to me").

The target: most requests are finished with no picture at all, and the
checks are stronger than looking would be.

## 2. Rules every tool follows

1. **Built on the command language.** Each tool is a thin wrapper over a
   command or query the processor already runs (or a new one added for
   this), so it works headless, is unit tested without a window, and a
   person can type the same thing in the command line. The AI layer only
   formats input and output.
2. **The AI never changes the real model.** Read tools read the real
   model. Everything that changes geometry runs in a sandbox. The only way
   into the real history is `propose`, which the user accepts or rejects.
3. **Small, exact, structured answers.** Results are compact JSON with
   short keys. Numbers are rounded to what the tolerance can resolve
   (`/TOL`, by default 3 decimals in the model unit), and the unit is given
   once per answer. Lists are paged (`limit`, and `more: n` when cut), and
   the order is stable (by ID) so two answers can be compared.
4. **Summary first, detail on request.** Every read tool has a `detail`
   level. The default answer fits in about 200 to 500 tokens; the AI asks
   for faces, edges or features only when it needs them.
5. **Stable handles.** Every body, face and edge is named by its stable ID
   (PLAN.md 3.2), its body name, and the history entry that made it. The
   tools also hand back a robust selector (a `SEL` criterion) for any
   entity, so scripts the AI writes do not depend on raw IDs.
6. **Every answer carries the model revision.** Tools take an optional
   `since` revision and then report only what changed, so repeated checks
   stay cheap.
7. **Errors say what to do.** A failure returns the processor's message,
   the line, and a `hint` (for example the largest fillet radius that
   works, from the existing checks in LANGUAGE.md section 12) and, where it
   helps, which tool to call next.
8. **A fixed tool list.** The set of tools does not change during a chat,
   so the tool definitions and system prompt can be cached by the API and
   paid for once per conversation, not once per turn. Long help text is
   fetched on demand (`command_help`), not put in the prompt.

## 3. The tools

Six groups, about 25 tools. Names are the tool names the AI sees; the
command in brackets is what runs underneath (new commands are marked new).

### 3.1 Learn the language

| Tool | What it returns |
|------|-----------------|
| `find_commands(query)` | commands whose name or help matches, one line each (`HOLE: hole in a body at a point, with depth, counterbore, countersink`) |
| `command_help(name)` | the arguments with types, defaults and units, one or two examples, related commands, and the errors it can give. Generated from the same registry metadata as the GUI forms and `HELP` |
| `search_docs(query)` | the matching sections of LANGUAGE.md and the example scripts in `scripts/`, trimmed to the relevant part |

The system prompt holds only a one-page summary of the language (syntax,
parameters, selection, the command families). Everything else comes from
these tools, so the prompt stays small and cacheable.

### 3.2 Read the model

| Tool | What it returns |
|------|-----------------|
| `model_summary()` [`LIST` family] | units and tolerance; every body (ID, name, kind solid/surface/mesh, volume, bounding box, valid or not, number of pieces, hidden); parameters with values; datums; sketches; named sets; the current selection; history length with counts of failed and warned entries; the revision |
| `describe_body(body, detail)` [`DESCRIBE`, new] | see 3.2.1. The tool that replaces looking at a body |
| `describe_entities(kind, ids or criterion, fields)` [`DESCRIBE`] | one row per face, edge or vertex. Face: surface type, area, centre, normal or axis, radius, the faces next to it, which entry made it. Edge: curve type, length, end points, radius, convex or concave, its two faces |
| `around(entity, depth)` [`DESCRIBE, NEAR`, new] | the faces and edges touching an entity, out to `depth` steps: "face 12 (the top) touches the walls of holes 3 to 8 and four fillet faces of radius 2" |
| `history(range, detail)` [`HIST`] | entries with number, text, status (ok, warning, failed, suppressed), the message, and the bodies each one made or changed |
| `parameters()` [`LIST, PARAMS`] | every parameter, its value, the entry that sets it, and the entries that read it |
| `sketch_state(name)` [`LIST, SKETCH`] | entities with sizes, constraints, degrees of freedom left, redundant or conflicting constraints, closed profiles found |
| `user_context()` | what the user is pointing at: the selection (with descriptions), the last pick, the active sketch and work plane, the view direction, an open form. This is how "make **this** face 5 mm thicker" is understood without a picture |

#### 3.2.1 `describe_body`

Levels:

* `summary`: volume, area, bounding box, centre of mass, valid, pieces,
  counts of faces, edges and vertices, faces grouped by type
  (`plane 14, cylinder 13, torus 4`), flat faces grouped by normal.
* `features`: the parts a person would name. Holes (diameter, axis,
  position, depth, through or blind, counterbore or countersink, thread),
  bosses and pins, pockets and slots, fillets and chamfers grouped by size,
  ribs, shells (wall thickness), patterns of equal features (6 holes on a
  circle of radius 40, every 60 degrees), and symmetry planes.
* `faces`: every face as in `describe_entities`.

Features come first from the history (an entry made by `HOLE` or
`PATTERN` already says what it is) and otherwise from the geometry, so
imported bodies are described too. Geometry rules are simple and exact: a
hole is a concave cylindrical face with its axis inside the body's
material on all sides; it is through when both ends open onto outer faces;
a fillet is a cylinder or torus face tangent to both of its neighbours.

Example answer (about 150 tokens):

```json
{"rev": 41, "unit": "mm", "body": 3, "name": "flange", "valid": true,
 "volume": 82080.2, "bbox": [-50,-50,0, 50,50,12],
 "features": [
   {"type": "hole", "n": 6, "d": 8.0, "through": true, "axis": [0,0,1],
    "pattern": {"circle": [0,0,0], "r": 40, "step_deg": 60},
    "faces": [21,22,23,24,25,26], "made_by": 7},
   {"type": "hole", "n": 1, "d": 30.0, "through": true, "at": [0,0,0], "faces": [20], "made_by": 5},
   {"type": "fillet", "r": 2.0, "edges": 8, "made_by": 9}],
 "symmetry": ["XZ", "YZ"]}
```

### 3.3 Probe space

These answer "where is material" without a picture.

| Tool | What it returns |
|------|-----------------|
| `probe_ray(origin, dir, bodies)` [`PROBE, RAY`, new] | every hit along the ray: body, face, point, distance, entering or leaving. So the wall is 3 mm thick here, the hole goes all the way through, the boss sits 10 mm above the plate |
| `probe_point(points)` [`PROBE, POINT`, new] | for each point: inside, outside or on the surface of which body, the nearest face and the distance to it |
| `section_profile(body, plane or planes)` [`SECTION, PROFILE`, new] | the cut through a body as text: each loop (outer or inner) with its segments (line, arc, circle, spline) and sizes, area, centre. With a list of planes (every 5 mm up Z, say) it reads like a scan, showing how the shape changes along an axis |
| `outline(body, view)` [`OUTLINE`, new] | the silhouette from a view as a simplified 2D polygon or SVG path with its size: a "picture" in a few hundred tokens of text |
| `measure(what, a, b)` [`DIST`, `ANGLE`, `MASSPROP`, `CLASH`, `GAP`] | the existing measure commands as structured results |
| `wall_thickness(body, min)` [`THICK`, new; PLAN.md 5.7] | the thinnest walls, with where they are (face IDs and points) |

Example `section_profile(flange, Z=6)`:

```json
{"rev": 41, "plane": "Z=6", "area": 6845.6,
 "loops": [
   {"outer": true, "circle": {"c": [0,0], "r": 50}},
   {"outer": false, "circle": {"c": [0,0], "r": 15}},
   {"outer": false, "circles": {"n": 6, "r": 4, "on": {"c": [0,0], "r": 40}}}]}
```

### 3.4 Try things in a sandbox

The sandbox is a copy of the model (the processor's snapshot and restore
already make copies cheap). The AI can run, check, undo and run again as
often as it likes; the user's model and history are untouched.

| Tool | What it does |
|------|--------------|
| `sandbox(from)` | starts a sandbox from the current model, from an empty model, or from the model before entry n. One is open at a time; starting again resets it |
| `lint(script)` [`LINT`, new] | checks a script without running it: syntax, unknown commands, wrong numbers or types of arguments, parameters used before they are set, raw IDs where a selector would be safer, `*PY` blocks (refused) |
| `run(script, stop_on_error)` | runs the script in the sandbox, entry by entry. For each entry: ok, warning or error, the message and hint, and a short diff (bodies made, removed and changed, with volume change and new face counts). `ECHO` output is returned. Quiet by default; `detail` asks for more |
| `diff(from_rev, to_rev)` [`DIFF`, new] | what changed between two revisions: bodies, volumes, bounding boxes, faces added and removed, parameters, warnings |
| `check(expectations)` [`ASSERT`, new] | tests a list of expectations and reports pass or fail with the actual values; see 3.4.1 |
| `vary(param, values, expectations)` | re-runs the sandbox history with each value of a parameter and reports which values fail or break an expectation. Shows whether the model is really parametric (does the bolt circle still work with 3 holes? with 12?) |
| `round_trip(edits)` | makes history edits and undoes them, then checks that picks and IDs came back unchanged and no entry has a warning. Tests reference stability (PLAN.md 3.2) for what the AI wrote |
| `check_design(body, rules)` [`CHECK` plus new rules] | validity (`CHECK`), plus rules the user turns on: minimum wall, small edges and slivers, sharp inner corners, draft for moulding, overhangs for 3D printing, bodies in separate pieces, clashes between bodies. Each problem comes with face IDs and a point |

#### 3.4.1 Expectations

An expectation is an expression of the language's model queries with a
comparison and a tolerance, so the AI states what "right" means and the
modeler checks it exactly:

```text
ASSERT, VOL(flange), BETWEEN, 81500, 82200
ASSERT, BBOX(flange).dz, EQ, 12, 0.01
ASSERT, HOLES(flange, 8), EQ, 6                ! six holes of 8 mm (new query)
ASSERT, VALID(flange)                          ! (new query)
ASSERT, GAP(bolt1, plate), EQ, 0               ! touching
ASSERT, PIECES(flange), EQ, 1                  ! (new query)
ASSERT, SYMMETRIC(flange, "YZ")                ! (new query)
ASSERT, MINWALL(housing), GE, 2                ! (new query)
```

`ASSERT` is a real command, not only a tool: it does nothing when the
check passes and fails the entry when it does not, so expectations can be
kept in scripts, in parts (a bolt part can assert its own head height),
and in the regression corpus (PLAN.md risk 2). New queries added for it
(`HOLES`, `VALID`, `PIECES`, `SYMMETRIC`, `MINWALL`, `NFACES`) become
available in all expressions.

### 3.5 Hand over to the user

| Tool | What it does |
|------|--------------|
| `propose(script or history edits, summary, checks)` | shows the user a card in the chat with the commands, a plain summary, the sandbox diff and the checks that passed, and a preview in the viewport (the new bodies as a ghost). **Accept** runs the commands through the processor into the real history, as one group that one `UNDO` takes back; **Edit** opens them in the command line; **Reject** discards them. The AI is told the outcome and the new revision |
| `ask_pick(kind, prompt)` | asks the user to click a face, edge, body or point in the viewport ("click the face the bracket should sit on") and returns the pick with its description and a robust selector. Asking costs a few tokens; guessing from a picture costs far more and can be wrong |
| `highlight(ids, note)` | colours entities in the viewport for the user, to point at what an answer is about. Nothing comes back to the AI |
| `selector_for(kind, id)` [`SEL` helper, new] | the most robust selector that finds exactly this entity (`SEL, S, FACE, NORMAL, 0,0,1` then `SEL, R, FACE, LOC, Z, 12`), or says that only the ID works. Also used by the GUI for PLAN.md 3.2 item 7 |
| `preview_selection(criterion)` | runs a `SEL` criterion without changing the user's selection and returns how many match and which; warns when look-alikes make it ambiguous |

### 3.6 Look, when text is not enough

| Tool | What it returns |
|------|-----------------|
| `render(view, bodies, highlight, section, labels, size)` | a small image of the viewport (default 512 px wide, shaded with edges), with optional ID labels drawn on the faces and edges so the picture and the text answers use the same names |
| `render_compare(rev_a, rev_b, view)` | before and after side by side in one image |
| `render_detail(entity, size)` | a close-up framed on one entity, for small features |

When the AI should use them:

* the question is about looks: style, proportions, a smooth or lumpy
  surface, sculpted and freeform shapes (M5, M7) where faces and features
  do not describe the shape well;
* the user says something looks wrong and the text tools find nothing;
* the text answers disagree with each other or with what the user says.

Rendering is off-screen (CI already renders the viewer under a virtual
display; a true off-screen view is part of M9c), so it works in batch mode
too. The default size is small on purpose,
since image cost grows with pixel area; the AI asks for a larger or cropped
image only for detail.

## 4. How the assistant works with them

A typical request, "make a 100 mm flange, 12 thick, with a 30 mm bore and
6 bolt holes of 8 mm on a 80 mm circle, edges rounded 2 mm":

1. `model_summary` (empty model) and `command_help` for `CYL`, `HOLE`,
   `PATTERN`, `FILLET` if it is unsure of the arguments.
2. Writes a parametric script (`D = 100`, `T = 12` ...), `lint`.
3. `run` in a fresh sandbox. Say the fillet fails: the hint names the
   largest radius that works, it fixes the order of steps and runs again.
4. `check` with the request turned into expectations: bounding box
   100 x 100 x 12, `HOLES(flange, 8) == 6`, `HOLES(flange, 30) == 1`,
   valid, one piece, symmetric.
5. `vary(N, [3, 4, 12])` to make sure the bolt count really is a
   parameter.
6. `propose` with the script, the summary and the passed checks.

No picture was needed, and every claim in the proposal was checked
exactly. Rough cost of the tool results: a few thousand tokens in total,
against roughly a thousand per picture for a look-and-fix loop that
would still not prove the hole sizes. These numbers will be measured by the
benchmark (section 6), not assumed.

For edits of an existing model ("move the holes 5 mm outwards") the AI
reads `user_context` and `history`, finds the entry and parameter that
control the holes (`parameters`), tries `HIST, EDIT` in the sandbox, checks
with `diff` and `check`, then proposes the history edit, so the change is a
parameter edit and not a patch on top.

The system prompt tells the assistant this order of preference: exact
queries and expectations first, probes and section profiles next, a
picture last, and to say when it used one.

## 5. Safety and limits

* Sandbox runs have the processor's limits (loop and step counts) plus a
  time limit, and can be cancelled from the chat.
* `*PY` blocks, file commands (`SAVE`, `OPEN`, `EXPORT`, `IMPORT`, `RUN` of
  files outside the project's examples) and settings changes are refused
  in the sandbox; the AI can propose them for the user to accept.
* Everything the AI proposes is plain command text in the history, so it
  can be read, edited and undone like anything the user typed.
* The chat does not send the model or project files anywhere except the
  tool answers the AI asked for, and the user can turn the assistant off.

## 6. Testing and the benchmark

* Every tool has unit tests on fixed models with checked outputs, so the
  answer formats stay stable (the AI relies on them) and a kernel upgrade
  that changes a result is caught.
* A benchmark of modelling requests (flange, bracket, bolt and nut, shelled
  box, pipe fitting, spring, an edit of an existing model, a request that
  is impossible and must be refused clearly), each with expectations. For
  each run it records: success, turns, tokens, tool calls, pictures used.
  Goals: at least 9 of 10 tasks finished correctly, and most of them with
  no picture.
* The tools can also be offered to outside AI agents as an MCP server
  (`python -m modeler mcp`), which runs the same code headless. That gives
  a second way to test them, and lets coding agents build models in batch.

## 7. Build order

The tools do not need the chat panel, and several help the rest of the
plan, so they can be built in three steps:

| Step | Delivers | Useful before M9 for |
|------|----------|----------------------|
| **M9a** Tools without AI | JSON output for queries; `DESCRIBE` (summary, faces), `selector_for`, `preview_selection`, `ASSERT` and the new queries, `LINT`, `DIFF`, the sandbox with `run`; tests | `ASSERT` for the regression corpus (risk 2); `selector_for` for GUI picks written as criteria (3.2 item 7) |
| **M9b** Seeing without pictures | feature recognition in `DESCRIBE`, `PROBE`, `SECTION, PROFILE`, `OUTLINE`, `THICK`, `check_design`, `vary`, `round_trip` | minimum wall thickness (5.7); design checks for users |
| **M9c** The assistant | chat panel, `propose` cards with ghost preview, `ask_pick`, `highlight`, off-screen `render` tools, the API connection (tool use with cached tool definitions and system prompt), the benchmark, the MCP server | |

M9 exit test (adds to the one in PLAN.md section 7): the flange request
above gives a correct script that passes its expectations without a
picture, and an edit request on an existing model is done as a history
edit that survives `round_trip`.

## 8. What is built

Step M9a, first part (the commands are in LANGUAGE.md section 23):

| Planned | Built as | Notes |
|---------|----------|-------|
| `ASSERT` and new queries | `ASSERT` command; `VALID`, `PIECES`, `NFACES`, `HOLES`, `SYMMETRIC` | `MINWALL` waits for `THICK` (M9b). `scripts/flange.cmd` carries its own checks, so the regression corpus runs them |
| `describe_body` (summary, faces), `describe_entities`, `model_summary` | `DESCRIBE` command and `modeler/ai/describe.py` | the summary already finds round holes (through or blind, depth, counterbore, axis, positions, circle patterns) from the geometry, so it works on imported bodies. The rest of feature recognition (fillets, pockets, bosses, history-first naming) is M9b |
| `selector_for`, `preview_selection` | `SELFOR` command and `modeler/ai/selectors.py` | greedy: adds the criterion that narrows the most until one entity is left, and checks the lines against the model |
| `lint` | `LINT` command and `modeler/ai/lint.py` | |
| `diff` | `DIFF` command and `modeler/ai/diff.py` | between history positions; `since` revisions are not done yet |
| `sandbox`, `run`, `check` | `modeler/ai/sandbox.py`, `modeler/ai/tools.py` | a second processor sharing the immutable bodies; file commands refused; a time limit per run (`Processor.deadline`) |
| `find_commands`, `command_help`, `history` | `modeler/ai/tools.py` | from the command registry |
| JSON tool list | `Toolbox` in `modeler/ai/tools.py`; `python -m modeler tools` and `python -m modeler tool ...` | 15 tools; errors are answers with a `hint` |

Measured on the worked example of section 4 (a 100 mm flange, 30 mm bore,
6 holes of 8 mm, rim rounded): lint, run in an empty sandbox, seven checks,
diff and the final script take 1.5 s of wall time including start-up, and
the `describe_body` answer for the result is about 200 tokens.

Step M9b, first part:

| Planned | Built as | Notes |
|---------|----------|-------|
| `probe_ray`, `probe_point` | `PROBE, RAY` / `PROBE, POINT`; `modeler/geometry/probe.py`, `modeler/ai/probe.py` | crossings merged where a ray passes an edge; stretches of material per body |
| `section_profile` | `PROFILE` command (the plan called it `SECTION, PROFILE`; `SECTION` stays the view command) | loops as circles, rectangles or lines, arcs and curves; equal holes grouped with their circle; stacks of cuts; a cut on a flat face is moved a hair aside and says so |
| `wall_thickness`, `MINWALL` | `THICK` command, `MINWALL()` query | inward rays from 5 x 5 points per face; a wall seen from both sides is listed once |
| `vary`, `round_trip` | `modeler/ai/experiments.py` | in sandbox copies; `round_trip` compares IDs, volumes, selection and named sets |

Not yet: `search_docs`, `around`, `parameters` with readers, `sketch_state`,
`user_context`, `since` on every tool, `outline`, `check_design`, the rest of
feature recognition (fillets, pockets, bosses), and M9c.
