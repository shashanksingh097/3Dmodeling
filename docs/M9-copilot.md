# The assistant on GitHub Copilot (M9c, first part)

The in-app assistant runs on the GitHub Copilot SDK. Each user signs in with
their own GitHub account, and requests count against that user's own
Copilot plan. Copilot Free is a plan too, so the assistant costs the user
nothing, and it costs this project nothing either. The tools it works with
are the ones from [M9-ai-tools.md](M9-ai-tools.md).

## What was checked (November 2026)

* The SDK is generally available, MIT licensed, `pip install github-copilot-sdk`
  (version 1.0.33 here), and needs Python 3.11 or newer.
* GitHub's own guide for the SDK describes per-user sign-in: the user
  authorizes, the app hands their token to the SDK, and "Copilot usage is
  billed to each user's subscription". Every user needs a Copilot plan.
* GitHub's plans page says every plan, Free included, comes with the Copilot
  command-line tool. The SDK drives the same runtime. On Free, Copilot
  chooses the model itself ("auto"), and the monthly allowance is small;
  GitHub does not publish a number.
* What is **not** written anywhere: "Copilot Free works with the SDK". The
  runtime does have a call that enrolls a signed-in user in Copilot Free
  (`account.subscribeCopilotFree`, internal) and reports the allowance by
  kind, which suggests Free is expected. **The real test is the user's
  Free account**: `python -m modeler copilot check`.
* Not yet checked: the licence for passing the Copilot runtime on. The app
  does not bundle it: the SDK downloads it from GitHub's releases on first use.

Sources: <https://github.com/github/copilot-sdk>,
[auth](https://github.com/github/copilot-sdk/blob/main/docs/auth/authenticate.md),
[per-user OAuth](https://github.com/github/copilot-sdk/blob/main/docs/setup/github-oauth.md),
[plans](https://docs.github.com/en/copilot/get-started/plans).

## Design

`modeler/ai/copilot.py` holds everything that talks to Copilot.

* **Install.** An optional extra: `pip install -e ".[ai]"` in a checkout (skipped on
  Python 3.10, so the rest of the app still installs there). The release
  builds include it. The Copilot runtime (about 190 MB) downloads once to the
  user's cache folder the first time the assistant starts.
* **Sign-in.** The runtime's own GitHub sign-in with a one-time code
  (`session.accounts.login.begin` with `method: device-code`, then
  `advance`): the app shows the code and opens github.com/login/device. The
  runtime stores the credential in a file in a per-user app-data folder
  (`runtime_dir()`, the client's `base_directory`), because the SDK's
  `empty` mode switches the keychain off (`COPILOT_DISABLE_KEYTAR=1`). It
  asks first (`needs-plaintext-consent`; the answer that accepts is
  `allow`, anything else declines). This uses GitHub's Copilot sign-in, so
  the project needs no OAuth app and ships no secret. A sign-in of the
  Copilot command-line tool is not shared (no keychain). This sign-in call is
  marked experimental in the SDK, so the SDK is pinned below 2.0.
* **Working folder.** `empty` mode refuses to start without a folder of its
  own (it never falls back to `~/.copilot`), so the client always gets
  `base_directory = runtime_dir()` (per user, `MODELER_COPILOT_DATA`
  overrides it), never the working folder. The working folder is
  temporary by default (`<temp>/3Dmodeling-assistant`, or
  `MODELER_COPILOT_HOME`); the panel's **Folder** menu picks the project's
  folder or any folder (QSettings `assistant/folder_mode`,
  `assistant/folder`), and the CLI takes `--folder`. The system prompt names
  the folder for file commands. Changing it restarts Copilot.
* **A clean agent.** The client runs in the SDK's `empty` mode, the session
  allows only custom tools (`available_tools = custom:*`), and our system
  prompt replaces the coding-agent prompt. The runtime's shell, file, web
  and git tools are not there; a test against the real runtime checks that
  exactly our tools are registered.
* **Tools.** Every tool of `modeler.ai.tools.Toolbox` (read the model,
  probe, sandbox, lint, check) plus `propose_commands`. They read the model
  or work in the sandbox only, so they skip permission prompts. In the app
  they run on the GUI thread (`run_on_model`), because the model belongs to
  that thread.
* **Proposals.** `propose_commands` lints the script and shows it in the
  panel with **Run** and **Dismiss**. Run goes through `MainWindow.execute`,
  so the commands land in the history and Undo takes them back. Copilot
  cannot change the model itself.
* **Changing what is there.** `propose_edits` takes history edits
  (`edit`, `insert`, `delete` an entry), tries them on a sandbox copy and
  refuses them when a step then fails. The panel shows each step's old and
  new text; Run sends `HIST, EDIT/INSERT/DELETE` lines. History edits have
  no Undo yet, so the old text stays in the conversation to edit back.
* **Imported bodies.** `describe_body` says where a body came from
  (`imported`, `format`, `file`) and whether it is `exact` or `faceted`
  (flat triangles, found from the faces), with what works on it;
  `model_summary` marks faceted and imported bodies. The system prompt
  tells Copilot to check a body first and explain in those terms.
* **Errors in words.** No plan points to Copilot Free; a used-up allowance
  says so.

`modeler/gui/assistant_panel.py` is the dock: the account line (login and
allowance left), the conversation, the proposal box and the input line.
Copilot runs on a background thread with its own asyncio loop
(`AssistantThread`) and starts only when the user signs in or asks.

## Debug tab, first prompt, files (asked for after 0.2.0)

* **The first prompt carries every command.** `first_prompt(home)` is the
  system message of every new chat: how to work, the working folder,
  `tools.LANGUAGE_BASICS` (lines, parameters, IDs and names, selection,
  blocks, sketches, history) and `tools.command_catalogue()`, one line per
  registered command: `NAME, arg, [optional], v1... - first sentence of
  its help`, with `(not kept)` for commands that are not stored. About
  19 KB in all, so Copilot rarely needs `find_commands` first;
  `command_help` stays for the details and examples.
* **A conversation log.** `CopilotAssistant.log` keeps, in order: the
  system message (with the model and the tool names), every prompt, every
  tool call with its arguments, every result (ok or error, time in ms, the
  JSON text), replies, permission answers, errors and new chats. Each
  entry also goes to the panel as a `debug` event. A tool that raises
  answers `{"error": ...}` instead of failing the turn, and the log shows
  it. `format_log` turns entries into the Debug tab's text (JSON indented,
  number lists on one line, results over 20 000 characters cut).
* **The Debug tab.** The panel has **Chat** and **Debug** tabs. Debug is
  the formatted log, with the number of prompts and tool calls, and
  **Copy**, **Save…** (a text file, the working folder by default) and
  **Clear**.
* **New chat.** The button disconnects the session (the sign-in stays);
  the next question opens a new one with the full first prompt again.
  It also clears the chat, the proposal and any "allow for this chat".
* **Reading files, only with permission.** `list_files` and `read_file`
  read the working folder (the project's folder when that is chosen).
  Paths are resolved (symbolic links too) and must stay inside the
  folder; anything outside, missing or binary is refused before asking.
  Otherwise the user is asked on the GUI thread: **Allow once**, **Allow
  for this chat** or **Deny** (the default, and the answer when nobody is
  there to ask). Text only, at most 200 KB per read; listings show up to
  500 entries.


* `tests/test_copilot.py` tests the tool mapping, proposals, the sign-in
  steps and asking with a fake session, without the network.
  `MODELER_TEST_COPILOT_RUNTIME=1` also starts the real runtime and checks
  the registered tools.
  It also tests the first prompt (every registered command is in it), the
  log of tool calls and results, New chat, and `read_file`/`list_files`:
  asking first, "for this chat" until a new chat, and staying inside the
  working folder.
* `tests/test_assistant_gui.py` tests the panel: Run and Dismiss, tool
  calls running on the GUI thread, the Debug tab (Copy, Save, Clear), New
  chat and the three answers of the permission dialog.
* **With a real account** (needs a person): `python -m modeler copilot check`
  signs in if needed, then prints PASS or FAIL for: signed in, allowance,
  models, an answer from Copilot, Copilot calling the modeler's tools, and
  the right hole size (8 mm) in the answer. Run it with a Copilot Free
  account before 0.2.0.

## Your own key, pointing, pictures, benchmark (after 0.2.0)

- **Own key** (`ai/providers.py`): kinds `copilot`, `openai`, `anthropic`,
  `azure`, `ollama`, `custom`. A `ProviderSetting` becomes the SDK's
  `ProviderConfig` for `create_session` (same runtime, same tools). Keys go
  in `keys.json` (mode 0600) in the app-data folder only when the user asks;
  `MODELER_AI_KEY` wins. The runtime strips images for own-key models unless
  `model_capabilities` says the model has vision, so the vision setting is
  passed as an override.
- **Pointing**: `ask_pick` (the panel asks the user to click a face, edge or
  body; five minutes, or Cancel in the panel), `highlight` (orange marks on the top
  layer, face outlines drawn so an edge-on face still shows) and
  `user_context` (what is picked, the open sketch, the view).
- **Pictures**: `render` returns a PNG of the 3D view (or a named view) as a
  binary tool result; it is offered only when the model can see pictures.
  The camera and marks are put back afterwards.
- **Benchmark** (`ai/bench.py`, `copilot bench`): ten tasks, each set up
  with a script, checked by exact measures, with a reference script that
  must pass. The results file records the model.

## Streaming, Stop, and the conversation kept with the project (after 0.3.0)

- **Streaming.** The session already ran with `streaming=True` and passed
  `("delta", text)` events on; the panel now shows them: the first piece adds
  a "Copilot:" paragraph and the pieces go in as plain text (the view
  follows the end unless the user scrolled up). When the complete message
  comes, the streamed text is taken out and the formatted answer
  (`_markdownish`) put in its place. When a tool starts mid-answer, what was
  written is kept as it is, and the same complete message is not shown again.
- **Stop.** While busy, Send is swapped for Stop.
  `CopilotAssistant.stop_answer()` ends the wait (`Reply.stopped`) and then
  calls `session.abort()` so the runtime stops generating and calling tools.
  The partial answer stays.
- **Kept with the project.** `Processor.chat` holds `{"who": "you" |
  "assistant", "text"}`. The panel appends each question and each answer.
  `save_project` writes the newest 200 into `project.json` (`"chat"`),
  `open_project` reads them back, and `reset` (NEW, OPEN) clears them. After
  OPEN or NEW the panel shows the kept conversation and starts a fresh chat.
- **Remembered.** Before each question the panel sets
  `assistant.earlier = earlier_text(chat)`. Only a fresh session uses it:
  the first message is prefixed with `EARLIER_HEAD` and the conversation as
  plain text (newest turns first to be kept, up to 8000 characters), with a
  warning that the model may have changed since. It is the same with every
  provider, because the SDK's own session resume is tied to one runtime's
  state folder, which a project file does not carry.
- **New chat** also clears the kept conversation.

## Skills (PLAN items 43 to 45)

The first prompt ends with a one-line index of the skill files
(`skills.index_text()`), and the system prompt says to `load_skill` the one
that matches a request before writing commands. Skills the user switched
off in Help > Assistant skills… are left out. The SDK's own
`skill_directories` is not used: our sessions allow only our own tools, so
the SDK's skill tool would be blocked, and `load_skill` works the same with
every provider. Details: [M12-assistant-skills.md](M12-assistant-skills.md).

## Smaller first prompt and benchmark modes (PLAN items 46, 47)

`first_prompt(home, small, skills)`: with `small` the command catalogue
(one line per command, about 18 KB) is replaced by the command names by
family (`tools.command_families()`, the command menu's headings), about
12 KB in all instead of 30 KB; the assistant then reads a command's
arguments with `command_help` before using it. The app's setting is
`assistant/small_prompt` (Help > Assistant skills…, "Short first
message"), read when the assistant starts; the CLI has `--small-prompt`
and `--no-skills`. `copilot bench --modes full,small,noskills,small-noskills`
runs the 24 tasks once per mode and prints a table; the default changes
only if the numbers say so. The picture tools are `render`,
`render_detail` (a close-up framed on entities, `snapshot(focus=...)`) and
`render_compare` (the sandbox's changed bodies in orange over the model);
all three are offered only to models that take pictures.

## Next

1. Benchmark numbers for a few models, published with a release. This needs a
   signed-in run (a Copilot plan or keys for each model), so it is the
   owner's to run: `3Dmodeling-cli copilot bench --model <name>` writes the
   results file.
