# The modelling tools as an MCP server

`python -m modeler mcp` serves the tools the app's own assistant uses as a
[Model Context Protocol](https://modelcontextprotocol.io) server over
stdin and stdout. Any MCP client (a chat app, a coding agent, your own
script) can then model with the app headless: run command lines, look at
the result, measure it and check it.

```
python -m modeler mcp                       # an empty model
python -m modeler mcp --script part.cmd     # start from what a script makes
```

A built app has the same thing as `3Dmodeling-cli mcp`.

## Adding it to a client

Most clients take a command to start. For example, a JSON config:

```json
{
  "mcpServers": {
    "3dmodeling": {
      "command": "python",
      "args": ["-m", "modeler", "mcp"]
    }
  }
}
```

With Claude Code: `claude mcp add 3dmodeling -- python -m modeler mcp`.
Use the full path of the Python that has the app installed if there are
several.

## The tools

They are the assistant's tools (`python -m modeler tools` prints their
definitions), among them:

| tool | what it does |
|---|---|
| `find_commands`, `command_help` | find a command and read its arguments |
| `run` | run command lines; each top-level line is one history step |
| `undo` | take steps back |
| `model_summary`, `describe_body`, `describe_entities`, `history` | what the model holds |
| `probe_ray`, `probe_point`, `section_profile`, `wall_thickness` | measure without pictures |
| `contact`, `assembly_check`, `fit_check`, `placement`, `check_design`, `compare_bodies` | assemblies and design rules |
| `check` | expectations that must hold (`VOL(1) > 100`, `VALID(1)`) |
| `sandbox`, `sandbox_script`, `vary`, `round_trip` | try changes on a copy, vary a parameter |
| `lint`, `diff`, `selector_for`, `preview_selection` | scripts and stable references |
| `list_skills`, `load_skill`, `search_docs` | step-by-step guides to whole jobs, and the manual |
| `parameters`, `sketch_state` | who sets and reads each parameter; a sketch's constraints and freedom |
| `diagnose` | why a step failed, and which usual fixes work (tried on a copy), with the line to run |
| `around`, `outline` | what touches a face or edge; a body seen from a view, as a few hundred numbers |

Three tools are only here, because the app's assistant hands its work to
the person instead:

| tool | what it does |
|---|---|
| `apply` | make the working copy the model (its new steps run on the model) |
| `save_project` | save the model as a project, `path` ending in `.m3d` |
| `export` | write the model's bodies (or one `body`) to a `.step`, `.iges`, `.brep`, `.stl`, `.obj`, `.3mf` or `.glb` file |

**The working copy.** `run` works on a copy of the model (the sandbox; the
first `run` opens it). While it is open, the reading tools (`model_summary`,
`describe_body`, `probe_ray`, `check` ...) look at the copy. `apply` runs
the copy's new steps on the model and closes the copy. Then `save_project`
or `export` write it out. `sandbox` starts a fresh copy (from the model, or
empty), and `undo` takes steps back in the copy.

A failing tool answers with `isError: true` and an `error` (often with a
`hint`); the model is left as it was. Answers are JSON, as text and as
`structuredContent`.

## Skills: prompts and resources

The server also offers the app's skill files (`python -m modeler skills
list`): each skill is a **prompt** (`prompts/list`, `prompts/get` with an
optional `request` argument, which adds the user's request to the skill's
text and example) and two **resources**, `skill://NAME` (the `SKILL.md`)
and `skill://NAME/example.cmd`. The tools `list_skills`, `load_skill` and
`search_docs` give the same text to clients that only use tools. To give
the skills to an agent that reads Agent Skills folders itself, write them
out with `python -m modeler skills export --to DIR`.

## Files

Inside the working copy, commands that read or write files (`SAVE`,
`OPEN`, `RUN`, `EXPORT`, `IMPORT`, `LIB`, `DRAWING`) are refused. Files are
written only by `save_project` and `export`, to the paths the client gives.
Relative paths are taken from the folder the server was started in. Run it
in a folder you are happy for the client to write to.

## How it works

`modeler/ai/mcp_server.py` answers JSON-RPC 2.0, one message per line:
`initialize` (protocol versions 2024-11-05, 2025-03-26 and 2025-06-18),
`tools/list`, `tools/call` (also batches of messages), `ping`, and empty
`resources/list` and `prompts/list`. Notifications are taken quietly, and anything else gets
"method not found". It needs no MCP package. Only answers go to stdout;
the model's own messages (`*MSG`, warnings) go to stderr.
