"""The in-app assistant on GitHub Copilot: each user signs in with their own GitHub account.

Copilot runs through the GitHub Copilot SDK (``pip install "3Dmodeling[ai]"``).
Nothing is billed to this app: every request counts against the signed-in
user's own Copilot plan, Copilot Free included. The SDK starts a Copilot
runtime (downloaded once, about 190 MB, to the user's cache folder) and talks
to it over a pipe.

Sign-in uses the runtime's own GitHub sign-in with a one-time code: the app
shows a code, the user enters it at github.com/login/device, and the runtime
keeps the credential in the system keychain, as the Copilot command-line tool
does. A user already signed in to Copilot on this computer is signed in here
too.

The assistant gets only this app's tools (``modeler.ai.tools``: reading the
model, probing, a sandbox to try scripts in) plus ``propose_commands``. The
runtime's own coding tools (shell, files, web) are switched off. It never
changes the user's model: it proposes commands, and the user runs them.

Everything here is async; :class:`AssistantThread` runs it on a background
thread for the GUI, and ``python -m modeler copilot ...`` drives it from a
shell (see :func:`main`).
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any

from .tools import Toolbox

SDK_HINT = 'The assistant needs the GitHub Copilot SDK and Python 3.11 or newer: pip install "3Dmodeling[ai]"'
DEVICE_URL = "https://github.com/login/device"
FREE_SIGNUP_URL = "https://github.com/settings/copilot"

SYSTEM_PROMPT = """\
You are the assistant inside 3Dmodeling, a desktop 3D modeler in which every action is a text
command, so every model is a script of commands. Help the user model, explain commands and
errors, and write scripts.

How to work:
- Learn the language from the tools, not from memory: find_commands and command_help give each
  command's arguments, defaults and examples. Commands look like `BLOCK, 0,0,0, 10,20,5`.
- Read the user's model with model_summary, describe_body, history, probe_ray, section_profile.
  Prefer these exact text answers to guessing.
- Before you suggest a script, try it: sandbox, then run (and check with expectations such as
  'VOL(b), BETWEEN, 900, 1100' or 'VALID(b)'). Fix what fails.
- When a script works, call propose_commands with the script and a one-line summary. The user
  sees it with a Run button. You cannot change the user's model yourself, so never say that you
  did; say what the proposal will do.
- To change what is already there (a size, a step that fails, a hole in the wrong place), read the
  history and call propose_edits to change those steps, rather than adding steps on top. Sizes are
  often a parameter line such as `W = 40`: edit that one line.
- Imported bodies: describe_body says where a body came from and whether it is "exact" (STEP, IGES,
  BREP: works like any body, but without the other program's feature history; edit it with HOLE,
  FILLET, SHELL, PUSHPULL, MOVEFACE, DELFACE, booleans) or "faceted" (a mesh: every triangle is a
  flat face; booleans, SPLIT, sections, measuring and export work, fillets, shells and offsets do
  not). When asked what can be done with an import, check it first, then explain in those terms.
- Picks by number break when the history is edited: prefer SEL criteria (selector_for).
- Keep answers short and plain. Give sizes with units.
"""


class AssistantError(Exception):
    """Something the user can act on: no SDK, not signed in, no Copilot plan, quota used up."""


def sdk_available() -> bool:
    try:
        import copilot  # noqa: F401
    except ImportError:
        return False
    return True


def _need_sdk():
    try:
        import copilot
    except ImportError:
        raise AssistantError(SDK_HINT) from None
    return copilot


@dataclass
class Proposal:
    """Commands for the user to run: new steps (``script``), or history edits (``edits``).

    Edits are ``{"action": "edit"|"insert"|"delete", "entry": n, "text": ..., "old": ...}``,
    applied in order, each numbered as the history stands after the ones before."""

    script: str
    summary: str
    edits: list[dict[str, Any]] = field(default_factory=list)

    def commands(self) -> list[str]:
        """The lines to run, one command line each (history edits are HIST commands)."""
        if not self.edits:
            return [self.script]
        from ..lang.expr import format_value

        out = []
        for e in self.edits:
            act = {"edit": "EDIT", "insert": "INSERT", "delete": "DELETE"}[e["action"]]
            line = f"HIST, {act}, {int(e['entry'])}"
            if act != "DELETE":
                line += f", {format_value(e['text'])}"
            out.append(line)
        return out


@dataclass
class Reply:
    """What one question produced."""

    text: str = ""
    tools: list[str] = field(default_factory=list)  # names of the tools called, in order
    proposals: list[Proposal] = field(default_factory=list)
    error: str = ""


# events passed to ``on_event``: ("delta", text) while the answer streams in,
# ("tool", name) when a tool starts, ("proposal", Proposal), ("message", text) for the whole answer
EventFn = Callable[[str, Any], None]


class CopilotAssistant:
    """One signed-in user's Copilot, with the modeler's tools.

    ``run_on_model(fn)`` runs ``fn()`` where it is safe to read the model and
    returns its result; the GUI passes a function that runs it on the GUI
    thread. By default tools run on the assistant's own thread.
    """

    def __init__(self, processor, *, run_on_model: Callable[[Callable[[], Any]], Any] | None = None,
                 on_event: EventFn | None = None, model: str | None = None,
                 home: str | None = None, github_token: str | None = None) -> None:
        self.toolbox = Toolbox(processor)
        self.run_on_model = run_on_model or (lambda fn: fn())
        self.on_event = on_event or (lambda kind, data: None)
        self.model = model
        self.home = home
        self.github_token = github_token
        self.client = None
        self.session = None
        self._reply: Reply | None = None

    # ---- runtime ---------------------------------------------------------------------
    async def start(self) -> None:
        if self.client is not None:
            return
        cp = _need_sdk()
        import logging

        logging.getLogger("copilot").setLevel(logging.CRITICAL)  # failures come back as AssistantError
        kwargs: dict[str, Any] = {"mode": "empty", "log_level": "error"}
        if self.home:
            kwargs["base_directory"] = self.home
        if self.github_token:
            kwargs["github_token"] = self.github_token
        client = cp.CopilotClient(**kwargs)
        try:
            await client.start()
        except Exception as exc:  # noqa: BLE001 - download or start failures come in many kinds
            raise AssistantError(f"could not start Copilot: {exc}") from None
        self.client = client

    async def stop(self) -> None:
        if self.session is not None:
            try:
                await self.session.disconnect()
            except Exception:  # noqa: BLE001 - closing anyway
                pass
            self.session = None
        if self.client is not None:
            try:
                await self.client.stop()
            except Exception:  # noqa: BLE001
                pass
            self.client = None

    # ---- account ---------------------------------------------------------------------
    async def status(self) -> dict[str, Any]:
        """{"signed_in": bool, "login": str, "message": str}."""
        await self.start()
        st = await self.client.get_auth_status()
        return {"signed_in": bool(st.isAuthenticated), "login": st.login or "",
                "message": st.statusMessage or ""}

    async def sign_in(self, show_code: Callable[[str, str, int], None],
                      allow_plaintext: Callable[[], bool] = lambda: False) -> str:
        """Sign in with a one-time code; returns the GitHub login.

        ``show_code(url, code, seconds)`` tells the user where to enter the code.
        ``allow_plaintext()`` asks whether the credential may be stored in a
        plain file when the system has no keychain."""
        from copilot.generated import rpc as R

        session = await self._session()
        login = session.rpc.accounts.login
        try:
            begun = await login.begin(R.AuthLoginBeginRequest(R.LoginProviderKind("githubDotCom"),
                                                              method=R.AuthLoginMethod.DEVICE_CODE))
        except Exception as exc:  # noqa: BLE001
            raise AssistantError(f"could not start GitHub sign-in: {exc}") from None
        step, flow = begun.step, begun.flow_id
        try:
            for _ in range(200):
                kind = step.kind.value
                if kind == "device-code":
                    show_code(step.verification_uri or DEVICE_URL, step.user_code or "", step.expires_in or 900)
                    step = await login.advance(R.AuthLoginAdvanceRequest(flow))
                elif kind == "open-url":
                    show_code(step.url or DEVICE_URL, "", step.expires_in or 900)
                    step = await login.advance(R.AuthLoginAdvanceRequest(flow))
                elif kind in ("awaiting", "needs-interaction"):
                    step = await login.advance(R.AuthLoginAdvanceRequest(flow))
                elif kind == "completed":
                    res = step.result
                    status = res.status.value if res else "completed"
                    if status == "completed":
                        self.session = None  # the next question starts a session as the new user
                        await session.disconnect()
                        return res.login if res and res.login else ""
                    if status == "needs-plaintext-consent":
                        step = await login.advance(R.AuthLoginAdvanceRequest(
                            flow, "yes" if allow_plaintext() else "no"))
                    elif status == "needs-account-selection" and res.accounts:
                        first = res.accounts[0]
                        step = await login.advance(R.AuthLoginAdvanceRequest(
                            flow, getattr(first, "selection_id", None) or getattr(first, "account_id", "")))
                    elif status == "declined":
                        raise AssistantError("sign-in stopped: the credential could not be stored")
                    else:
                        raise AssistantError(f"sign-in stopped ({status})")
                elif kind == "error":
                    raise AssistantError(f"GitHub sign-in failed: {step.message or 'no reason given'}")
                else:  # input-required: only GitHub Enterprise hosts ask for one
                    raise AssistantError(f"GitHub sign-in asks for something this app does not support ({kind})")
            raise AssistantError("GitHub sign-in took too long")
        except BaseException:
            try:
                await login.cancel(R.AuthLoginCancelRequest(flow))
            except Exception:  # noqa: BLE001
                pass
            raise

    async def quota(self) -> dict[str, Any]:
        """What is left of the user's Copilot allowance, by kind (chat, premium_interactions, ...)."""
        from copilot.generated import rpc as R

        await self.start()
        try:
            res = await self.client.rpc.account.get_quota(R.AccountGetQuotaRequest())
        except Exception as exc:  # noqa: BLE001
            raise AssistantError(f"could not read the Copilot allowance: {exc}") from None
        out = {}
        for kind, q in (res.quota_snapshots or {}).items():
            out[kind] = {"unlimited": q.is_unlimited_entitlement, "included": q.entitlement_requests,
                         "used": q.used_requests, "left_percent": round(q.remaining_percentage, 1),
                         "resets": q.reset_date or ""}
        return out

    async def models(self) -> list[dict[str, Any]]:
        await self.start()
        try:
            models = await self.client.list_models()
        except Exception as exc:  # noqa: BLE001
            raise AssistantError(f"could not list models: {exc}") from None
        return [{"id": m.id, "name": getattr(m, "name", "") or m.id} for m in models]

    # ---- chat ------------------------------------------------------------------------
    def sdk_tools(self) -> list:
        """The modeler's tools in the SDK's shape (all read-only or sandboxed: no permission prompt)."""
        cp = _need_sdk()
        from copilot.tools import Tool as SdkTool
        from copilot.tools import ToolResult

        def handler_for(name: str):
            async def handler(invocation) -> ToolResult:
                args = invocation.arguments or {}
                if isinstance(args, str):
                    args = json.loads(args or "{}")
                self.on_event("tool", name)
                if self._reply is not None:
                    self._reply.tools.append(name)
                if name == "propose_commands":
                    answer = self._propose(args)
                elif name == "propose_edits":
                    answer = await asyncio.to_thread(self.run_on_model, lambda: self._propose_edits(args))
                else:
                    answer = await asyncio.to_thread(self.run_on_model, lambda: self.toolbox.call(name, args))
                text = json.dumps(answer, separators=(",", ":"), default=str)
                return ToolResult(text_result_for_llm=text,
                                  result_type="failure" if "error" in answer else "success")
            return handler

        tools = []
        for d in self.toolbox.definitions() + [_PROPOSE, _PROPOSE_EDITS]:
            tools.append(SdkTool(name=d["name"], description=d["description"], parameters=d["input_schema"],
                                 handler=handler_for(d["name"]), skip_permission=True))
        del cp
        return tools

    def _propose(self, args: dict[str, Any]) -> dict[str, Any]:
        script = str(args.get("script", "")).strip()
        if not script:
            return {"error": "propose_commands needs a script"}
        lint = self.run_on_model(lambda: self.toolbox.call("lint", {"script": script}))
        problems = [x for x in lint.get("issues", []) if x.get("level") == "error"] if isinstance(lint, dict) else []
        if problems:
            return {"error": "the script does not pass LINT", "problems": problems[:5]}
        prop = Proposal(script, str(args.get("summary", "")).strip())
        if self._reply is not None:
            self._reply.proposals.append(prop)
        self.on_event("proposal", prop)
        return {"shown_to_user": True, "lines": len(script.splitlines())}

    def _propose_edits(self, args: dict[str, Any]) -> dict[str, Any]:
        """Try history edits on a sandbox copy; show them when every step still works."""
        from ..commands.processor import CommandError
        from .sandbox import Sandbox

        raw = args.get("edits") or []
        if not isinstance(raw, list) or not raw:
            return {"error": "propose_edits needs edits: [{action, entry, text}]"}
        box = Sandbox(self.toolbox.real)
        p = box.p
        before = sum(1 for e in p.history[: p.cursor] if not e.ok)
        edits = []
        for k, e in enumerate(raw, 1):
            if not isinstance(e, dict):
                return {"error": f"edit {k} is not an object"}
            action = str(e.get("action", "edit")).lower()
            try:
                n = int(e.get("entry", 0))
            except (TypeError, ValueError):
                return {"error": f"edit {k}: entry must be a number"}
            text = str(e.get("text", ""))
            if action not in ("edit", "insert", "delete"):
                return {"error": f"edit {k}: action is edit, insert or delete"}
            limit = p.cursor + (1 if action == "insert" else 0)
            if not 1 <= n <= limit:
                return {"error": f"edit {k}: there is no entry {n} (the history has {p.cursor})"}
            if action != "delete" and not text.strip():
                return {"error": f"edit {k}: give the new text"}
            old = p.history[n - 1].text if action != "insert" else ""
            try:
                if action == "edit":
                    p.edit_entry(n, text)
                elif action == "insert":
                    p.insert_entry(n, text)
                else:
                    p.delete_entry(n)
            except CommandError as exc:
                return {"error": f"edit {k} refused: {exc}"}
            edits.append({"action": action, "entry": n, "text": text, "old": old})
        failed = [{"entry": i, "text": e.text, "error": e.message}
                  for i, e in enumerate(p.history[: p.cursor], 1) if not e.ok]
        if len(failed) > before:
            return {"error": "after these edits some steps fail; fix them first", "failed": failed[:5]}
        prop = Proposal("", str(args.get("summary", "")).strip(), edits)
        if self._reply is not None:
            self._reply.proposals.append(prop)
        self.on_event("proposal", prop)
        return {"shown_to_user": True, "edits": len(edits), "bodies_after": len(p.model.bodies)}

    async def _session(self):
        if self.session is not None:
            return self.session
        await self.start()
        cp = _need_sdk()
        from copilot.session import PermissionHandler

        kwargs: dict[str, Any] = dict(
            on_permission_request=PermissionHandler.approve_all,  # only our own read-only tools exist
            tools=self.sdk_tools(),
            available_tools=cp.ToolSet().add_custom("*"),  # none of the runtime's coding tools
            system_message={"mode": "replace", "content": SYSTEM_PROMPT},
            streaming=True,
            client_name="3Dmodeling",
            working_directory=self.home or os.path.expanduser("~"),
        )
        if self.model:
            kwargs["model"] = self.model
        self.session = await self.client.create_session(**kwargs)
        return self.session

    async def ask(self, text: str, timeout: float = 600.0) -> Reply:
        """Send one message and wait for the whole answer (tool calls included)."""
        from copilot.session_events import (
            AssistantMessageData,
            AssistantMessageDeltaData,
            SessionErrorData,
            SessionIdleData,
        )

        status = await self.status()
        if not status["signed_in"] and not self.github_token:
            raise AssistantError("not signed in to GitHub: sign in first")
        session = await self._session()
        reply = Reply()
        self._reply = reply
        done = asyncio.Event()
        parts: list[str] = []

        def on_event(event):
            if getattr(event, "agent_id", None):
                return
            data = event.data
            if isinstance(data, AssistantMessageDeltaData):
                self.on_event("delta", data.delta_content or "")
            elif isinstance(data, AssistantMessageData):
                if data.content:
                    parts.append(data.content)
                    self.on_event("message", data.content)
            elif isinstance(data, SessionErrorData):
                reply.error = getattr(data, "message", "") or str(data)
                done.set()
            elif isinstance(data, SessionIdleData):
                done.set()

        unsubscribe = session.on(on_event)
        try:
            await session.send(text)
            await asyncio.wait_for(done.wait(), timeout)
        except asyncio.TimeoutError:
            reply.error = f"no answer within {timeout:.0f} s"
        except Exception as exc:  # noqa: BLE001
            reply.error = explain_error(exc)
        finally:
            unsubscribe()
            self._reply = None
        reply.text = "\n\n".join(parts)
        if reply.error:
            reply.error = explain_error(reply.error)
        return reply


_PROPOSE = {
    "name": "propose_commands",
    "description": "Show the user a script with a Run button, after it worked in the sandbox. The script is "
                   "checked with LINT first. summary: one line on what running it does.",
    "input_schema": {"type": "object", "properties": {"script": {"type": "string"}, "summary": {"type": "string"}},
                     "required": ["script"]},
}


_PROPOSE_EDITS = {
    "name": "propose_edits",
    "description": "Show the user changes to existing history steps, with a Run button: change a step's text "
                   "('edit'), add a step before entry n ('insert'), or remove one ('delete'). Applied in order, "
                   "each entry number as the history stands after the edits before it. They are tried on a "
                   "sandbox copy first and refused if a step then fails. Use this to change sizes or fix steps "
                   "instead of adding new steps on top. summary: one line on what changes.",
    "input_schema": {"type": "object", "properties": {
        "edits": {"type": "array", "items": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["edit", "insert", "delete"]},
            "entry": {"type": "integer"}, "text": {"type": "string"}}, "required": ["entry"]}},
        "summary": {"type": "string"}}, "required": ["edits"]},
}


def explain_error(exc) -> str:
    """Errors in words a user can act on."""
    text = str(exc)
    low = text.lower()
    if "not authorized" in low or "no copilot" in low or "subscription" in low or "403" in low:
        return ("Your GitHub account has no Copilot plan. Copilot Free costs nothing: turn it on at "
                f"{FREE_SIGNUP_URL} and try again. ({text})")
    if "quota" in low or "rate limit" in low or "429" in low or "exhausted" in low:
        return f"Your Copilot allowance for this month is used up, or you are sending too fast. ({text})"
    return text


# ---- a thread for the GUI ----------------------------------------------------------------
class AssistantThread:
    """Runs a :class:`CopilotAssistant` on its own asyncio loop in a background thread.

    Each method returns a ``concurrent.futures.Future``; callbacks run on that
    thread, so the GUI forwards them with Qt signals."""

    def __init__(self, assistant: CopilotAssistant) -> None:
        self.assistant = assistant
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name="copilot", daemon=True)
        self.thread.start()

    def submit(self, coro) -> Future:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def status(self) -> Future:
        return self.submit(self.assistant.status())

    def sign_in(self, show_code, allow_plaintext=lambda: False) -> Future:
        return self.submit(self.assistant.sign_in(show_code, allow_plaintext))

    def ask(self, text: str) -> Future:
        return self.submit(self.assistant.ask(text))

    def quota(self) -> Future:
        return self.submit(self.assistant.quota())

    def close(self, wait: float = 5.0) -> None:
        try:
            self.submit(self.assistant.stop()).result(wait)
        except Exception:  # noqa: BLE001 - closing the app anyway
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)


# ---- command line ------------------------------------------------------------------------
USAGE = """\
python -m modeler copilot status          signed in? which GitHub login
python -m modeler copilot login           sign in with a one-time code at github.com/login/device
python -m modeler copilot quota           what is left of your Copilot allowance
python -m modeler copilot models          the models your plan offers
python -m modeler copilot ask [--script file.cmd] "question"
                                          ask once; tool calls and proposals are printed
python -m modeler copilot check           the whole test for one account (Copilot Free too):
                                          sign-in, allowance, models, and a question that must
                                          use the modeler's tools; prints PASS or FAIL per step
"""


def main(args: list[str]) -> int:
    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if not sdk_available():
        print(SDK_HINT)
        return 2
    from ..commands import Processor

    p = Processor()
    script = None
    if "--script" in args:
        i = args.index("--script")
        script = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
        if script:
            res = p.run(f'RUN, "{script}"')
            if not res.ok:
                print(res.message)
                return 1

    def on_event(kind, data):
        if kind == "tool":
            print(f"  [tool] {data}", flush=True)
        elif kind == "proposal":
            print(f"  [proposal] {data.summary}\n" + "\n".join("    " + x for x in data.script.splitlines()))

    asst = CopilotAssistant(p, on_event=on_event, model=os.environ.get("MODELER_COPILOT_MODEL") or None)
    return asyncio.run(_cli(asst, args))


def _show_code(url: str, code: str, seconds: int) -> None:
    if code:
        print(f"Open {url} and enter the code {code} (valid for {seconds // 60} minutes).", flush=True)
    else:
        print(f"Open {url} in a browser to sign in.", flush=True)


def _ask_plaintext() -> bool:
    try:
        return input("This computer has no keychain. Store the GitHub credential in a plain file? [y/N] ")\
            .strip().lower().startswith("y")
    except EOFError:
        return False


async def _cli(asst: CopilotAssistant, args: list[str]) -> int:
    cmd = args[0]
    try:
        if cmd == "status":
            st = await asst.status()
            print(f"signed in as {st['login']}" if st["signed_in"] else f"not signed in ({st['message']})")
            return 0 if st["signed_in"] else 1
        if cmd == "login":
            login = await asst.sign_in(_show_code, _ask_plaintext)
            print(f"signed in as {login}")
            return 0
        if cmd == "quota":
            print(json.dumps(await asst.quota(), indent=1))
            return 0
        if cmd == "models":
            for m in await asst.models():
                print(m["id"])
            return 0
        if cmd == "ask" and len(args) >= 2:
            reply = await asst.ask(" ".join(args[1:]))
            print(reply.text)
            if reply.error:
                print(f"ERROR: {reply.error}")
                return 1
            return 0
        if cmd == "check":
            return await _check(asst)
        print(USAGE)
        return 2
    except AssistantError as exc:
        print(f"ERROR: {exc}")
        return 1
    finally:
        await asst.stop()


async def _check(asst: CopilotAssistant) -> int:
    """Each step prints PASS or FAIL; the exit code is the number of failures."""
    fails = 0

    def report(ok: bool, what: str, detail: str = "") -> None:
        nonlocal fails
        fails += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  {what}" + (f": {detail}" if detail else ""), flush=True)

    st = await asst.status()
    if not st["signed_in"]:
        print("Not signed in yet: signing in.")
        try:
            await asst.sign_in(_show_code, _ask_plaintext)
            st = await asst.status()
        except AssistantError as exc:
            report(False, "sign in with GitHub", str(exc))
            return fails
    report(st["signed_in"], "signed in", st["login"] or st["message"])
    try:
        q = await asst.quota()
        report(True, "Copilot allowance", ", ".join(
            f"{k} {'unlimited' if v['unlimited'] else str(v['left_percent']) + '% left'}" for k, v in q.items())
            or "no allowance reported")
    except AssistantError as exc:
        report(False, "Copilot allowance", str(exc))
    try:
        models = await asst.models()
        report(bool(models), "models", ", ".join(m["id"] for m in models[:8]) or "none")
    except AssistantError as exc:
        report(False, "models", str(exc))
    asst.toolbox.real.run("BLOCK, 0,0,0, 40,30,10\nNAME, LAST, plate\nCYL, 20,15,-1, 4, 12\nSUBTRACT, plate, LAST")
    reply = await asst.ask("How many holes does the body 'plate' have, and what is their diameter? "
                           "Use the tools to find out.")
    used = [t for t in reply.tools if t in ("describe_body", "model_summary", "probe_ray", "section_profile")]
    report(not reply.error, "answer from Copilot", reply.error or reply.text[:160].replace("\n", " "))
    report(bool(used), "Copilot called the modeler's tools", ", ".join(reply.tools) or "no tool calls")
    report("8" in reply.text, "the answer has the right size (8 mm)")
    print("All passed." if not fails else f"{fails} step(s) failed.")
    return fails
