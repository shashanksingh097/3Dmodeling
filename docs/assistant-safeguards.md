# Assistant safeguards and reports (PLAN item 66)

The assistant (in the app, or another program through `python -m modeler mcp`) never
changes the model on its own. This item makes that a checked rule and gives the user what
they need to decide before anything runs. The code is `modeler/ai/safeguards.py`.

## Reading and changing kept apart

Every tool has a kind (`safeguards.kind_of`):

| Kind | Tools | What it may do |
|------|-------|----------------|
| read | `model_summary`, `describe_body`, `probe_ray`, `history`, ... | look at the model |
| try | `sandbox`, `run`, `undo`, `check`, `diagnose`, `vary`, `round_trip`, `sandbox_script` | work on a copy |
| view | `ask_pick`, `highlight`, `render*` | change what the 3D view shows, or ask for a click |
| propose | `propose_commands`, `propose_edits` | hand a change to the user |
| change | `apply`, `save_project`, `export` (MCP server only) | change the model, write files |

`Toolbox.call` checks after every read and try tool that the user's model, history, undo
list, parameters and selection are as they were (`safeguards.fingerprint`). If a tool ever
changed them (a bug), they are put back and the answer says so. The test calls every tool.

The MCP server marks the read and try tools `readOnlyHint: true` in its tool list, so
clients that ask before changes can tell them apart. The Debug tab shows the kind of each
tool call that is not a plain read.

## A plan with the expected effect

`propose_commands` and `propose_edits` take a `summary` and a `plan` (the steps in plain
words). Before the proposal is shown, the script or the edits are run on a copy of the model
and the difference worked out (`safeguards.effect`): bodies added, changed (with volume
before and after; a boolean that keeps the name counts as a change) and removed,
parameters set, steps added, edited, removed and re-run, and the lines that use files
(which the copy does not run). A script that fails on the copy is not shown; the assistant
hears the error. The panel shows the plan and "What it will do" above **Run**.

## A confirm for broad changes

A change is broad when it removes a body, changes 3 or more existing bodies, changes a
body's volume by more than half, re-runs 10 or more history steps, edits 3 or more steps
or removes one, or reads or writes files. The panel names the reasons on a tick box, and
**Run** works only once it is ticked. Through MCP, `apply` answers `needs_confirm` with the
reasons and the effect, and applies only when called again with `confirm: true`.

## One undo for the whole proposal

`Processor.undo_group(label)` makes everything run inside one UNDO step (and one REDO):
new steps, history edits, or both. The panel runs a proposal inside one, and so does the
MCP server's `apply`. The assistant is told to put the whole change for one answer in one
proposal.

## DESIGNCHECK report rows

Each problem now has `severity` (error or warning), `measured`, `limit`, `fix` (a command,
or advice) and `fix_checked`: the fix is run on a copy and the rule tested again, giving
"fixes it", "does not fix it" or "not tried" (advice). The text form shows the same in two
lines per problem. For example, an imported open box gets `HEAL, box` as its fix, and the
row says the fix does not work: HEAL finds nothing within its tolerance to join the open
edges to, so the user is not told to try something that will not help.
