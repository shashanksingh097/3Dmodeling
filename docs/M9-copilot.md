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

* **Install.** An optional extra: `pip install "3Dmodeling[ai]"` (skipped on
  Python 3.10, so the rest of the app still installs there). The release
  builds include it. The Copilot runtime (about 190 MB) downloads once to the
  user's cache folder the first time the assistant starts.
* **Sign-in.** The runtime's own GitHub sign-in with a one-time code
  (`session.accounts.login.begin` with `method: device-code`, then
  `advance`): the app shows the code and opens github.com/login/device. The
  runtime stores the credential in the system keychain, as the Copilot
  command-line tool does, and asks first before using a plain file where
  there is no keychain. This uses GitHub's Copilot sign-in, so the project
  needs no OAuth app and ships no secret. A user already signed in to
  Copilot on the computer is signed in here too. This sign-in call is
  marked experimental in the SDK, so the SDK is pinned below 2.0.
* **Working folder.** `empty` mode refuses to start without a folder of its
  own (it never falls back to `~/.copilot`), so the client always gets
  `base_directory = <working folder>/.copilot`. The working folder is
  temporary by default (`<temp>/3Dmodeling-assistant`, or
  `MODELER_COPILOT_HOME`); the panel's **Folder** menu picks the project's
  folder or any folder (QSettings `assistant/folder_mode`,
  `assistant/folder`), and the CLI takes `--folder`. The system prompt names
  the folder for file commands. Changing it restarts Copilot.
* **A clean agent.** The client runs in the SDK's `empty` mode, the session
  allows only custom tools (`available_tools = custom:*`), and our system
  prompt replaces the coding-agent prompt. The runtime's shell, file, web
  and git tools are not there; a test against the real runtime checks that
  exactly our 22 tools are registered.
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

## Testing

* `tests/test_copilot.py` tests the tool mapping, proposals, the sign-in
  steps and asking with a fake session, without the network.
  `MODELER_TEST_COPILOT_RUNTIME=1` also starts the real runtime and checks
  the registered tools.
* `tests/test_assistant_gui.py` tests the panel: Run and Dismiss, and tool
  calls running on the GUI thread.
* **With a real account** (needs a person): `python -m modeler copilot check`
  signs in if needed, then prints PASS or FAIL for: signed in, allowance,
  models, an answer from Copilot, Copilot calling the modeler's tools, and
  the right hole size (8 mm) in the answer. Run it with a Copilot Free
  account before 0.2.0.

## Next

1. The Copilot Free test on a real account, and fixes from it.
2. "Use your own key" for people without GitHub: the SDK's BYOK providers
   (OpenAI, Anthropic, Azure, a local Ollama model), chosen in the panel.
3. Streaming the answer into the panel as it is written, a model picker for
   paid plans, and keeping the conversation with the project.
4. The rest of M9c from M9-ai-tools.md: asking the user to pick, pictures as
   a fallback, and the benchmark.
