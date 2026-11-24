"""The assistant on GitHub Copilot, without the network: the SDK's session is replaced by a fake.

Set MODELER_TEST_COPILOT_RUNTIME=1 to also start the real Copilot runtime
(downloads it once, about 190 MB) and check that exactly the modeler's tools
are registered.
"""

import asyncio
import os

import pytest

pytest.importorskip("copilot", reason="the assistant needs the GitHub Copilot SDK (Python 3.11+)")

from copilot.generated import rpc as R  # noqa: E402
from copilot.session_events import (  # noqa: E402
    AssistantMessageData,
    SessionIdleData,
)
from copilot.tools import ToolInvocation  # noqa: E402

from modeler.ai import copilot as cp  # noqa: E402
from modeler.commands import Processor  # noqa: E402


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def plate():
    p = Processor()
    r = p.run("BLOCK, 0,0,0, 40,30,10\nNAME, LAST, plate\nCYL, 20,15,-1, 4, 12\nSUBTRACT, plate, LAST")
    assert r.ok, r.message
    return p


# ---- tools ---------------------------------------------------------------------------
def test_every_modeler_tool_is_offered(plate):
    a = cp.CopilotAssistant(plate)
    names = [t.name for t in a.sdk_tools()]
    assert names == [d["name"] for d in a.toolbox.definitions()] + ["propose_commands", "propose_edits", "ask_pick", "highlight", "render", "render_detail", "render_compare", "list_files", "read_file"]
    assert all(t.skip_permission for t in a.sdk_tools())  # read-only or sandboxed: no prompts


def test_tool_handlers_answer_in_json(plate):
    seen = []
    a = cp.CopilotAssistant(plate, on_event=lambda k, d: seen.append((k, d)))
    tools = {t.name: t for t in a.sdk_tools()}
    res = run(tools["describe_body"].handler(ToolInvocation(tool_name="describe_body",
                                                             arguments={"body": "plate"})))
    assert res.result_type == "success" and '"holes":[{"d":8.0' in res.text_result_for_llm
    bad = run(tools["describe_body"].handler(ToolInvocation(arguments={"body": "nothing"})))
    assert bad.result_type == "failure"
    assert ("tool", "describe_body") in seen


def test_tools_run_where_the_gui_says(plate):
    calls = []

    def on_gui_thread(fn):
        calls.append(fn)
        return fn()

    a = cp.CopilotAssistant(plate, run_on_model=on_gui_thread)
    tools = {t.name: t for t in a.sdk_tools()}
    run(tools["model_summary"].handler(ToolInvocation(arguments={})))
    assert len(calls) == 1


def test_proposals_must_pass_lint(plate):
    seen = []
    a = cp.CopilotAssistant(plate, on_event=lambda k, d: seen.append((k, d)))
    propose = {t.name: t for t in a.sdk_tools()}["propose_commands"]
    res = run(propose.handler(ToolInvocation(arguments={"script": "FOO, 1"})))
    assert res.result_type == "failure" and "LINT" in res.text_result_for_llm
    res = run(propose.handler(ToolInvocation(arguments={"script": "CYL, 0,0,0, 1, 2", "summary": "a pin"})))
    assert res.result_type == "success"
    props = [d for k, d in seen if k == "proposal"]
    assert [(x.script, x.summary) for x in props] == [("CYL, 0,0,0, 1, 2", "a pin")]
    assert props[0].effect["steps_added"] == 1 and len(props[0].effect["added"]) == 1  # worked out on a copy
    assert len(plate.model.bodies) == 1  # proposing never changes the model


# ---- sign-in, with a fake runtime --------------------------------------------------------
class FakeLogin:
    def __init__(self, steps):
        self.steps = list(steps)
        self.inputs = []
        self.cancelled = False

    async def begin(self, req):
        assert req.method == R.AuthLoginMethod.DEVICE_CODE
        return R.AuthLoginBegun("flow1", self.steps.pop(0))

    async def advance(self, req):
        self.inputs.append(req.input)
        return self.steps.pop(0)

    async def cancel(self, req):
        self.cancelled = True


class FakeSession:
    def __init__(self, login=None, events=()):
        self.rpc = type("Rpc", (), {})()
        self.rpc.accounts = type("Accounts", (), {})()
        self.rpc.accounts.login = login
        self.events = list(events)
        self.handlers = []
        self.sent = []
        self.disconnected = False

    def on(self, fn):
        self.handlers.append(fn)
        return lambda: self.handlers.remove(fn)

    async def send(self, text):
        self.sent.append(text)
        for e in self.events:
            for h in list(self.handlers):
                h(e)
        return "req1"

    async def disconnect(self):
        self.disconnected = True


def _step(kind, **kw):
    return R.AuthLoginStep(R.AuthLoginStepKind(kind), **kw)


def _done(status="completed", login="octo"):
    return _step("completed", result=R.AuthLoginResultDto(R.AuthLoginResultStatus(status), login=login))


def _assistant(plate, session):
    a = cp.CopilotAssistant(plate)

    async def fake_session():
        return session

    a._session = fake_session
    return a


def test_sign_in_with_a_device_code(plate):
    login = FakeLogin([_step("device-code", user_code="ABCD-1234", verification_uri=cp.DEVICE_URL, expires_in=900),
                       _step("awaiting"), _done()])
    session = FakeSession(login)
    a = _assistant(plate, session)
    shown = []
    assert run(a.sign_in(lambda url, code, s: shown.append((url, code, s)))) == "octo"
    assert shown == [(cp.DEVICE_URL, "ABCD-1234", 900)]
    assert session.disconnected and not login.cancelled


def test_sign_in_asks_before_storing_in_plain_text(plate):
    login = FakeLogin([_step("device-code", user_code="X"), _done("needs-plaintext-consent"), _done()])
    a = _assistant(plate, FakeSession(login))
    assert run(a.sign_in(lambda *x: None, allow_plaintext=lambda: True)) == "octo"
    assert login.inputs[-1] == "allow"  # the runtime's word: "yes" counts as declined


def test_sign_in_failure_is_explained_and_cancelled(plate):
    login = FakeLogin([_step("device-code", user_code="X"), _step("error", message="code expired")])
    a = _assistant(plate, FakeSession(login))
    with pytest.raises(cp.AssistantError, match="code expired"):
        run(a.sign_in(lambda *x: None))
    assert login.cancelled


# ---- asking ------------------------------------------------------------------------------
class Ev:
    def __init__(self, data):
        self.data = data
        self.agent_id = None


def test_ask_collects_the_answer(plate):
    events = [Ev(AssistantMessageData(content="The plate has one 8 mm hole.", message_id="m1")),
              Ev(SessionIdleData())]
    session = FakeSession(events=events)
    a = _assistant(plate, session)

    async def signed_in():
        return {"signed_in": True, "login": "octo", "message": ""}

    a.status = signed_in
    reply = run(a.ask("holes?"))
    assert reply.text == "The plate has one 8 mm hole." and not reply.error
    assert session.sent == ["holes?"]


def test_ask_needs_sign_in(plate):
    a = _assistant(plate, FakeSession())

    async def signed_out():
        return {"signed_in": False, "login": "", "message": "Not authenticated"}

    a.status = signed_out
    with pytest.raises(cp.AssistantError, match="sign in"):
        run(a.ask("hello"))


def test_errors_point_to_copilot_free():
    assert "Copilot Free" in cp.explain_error("403: user is not authorized to use Copilot")
    assert "allowance" in cp.explain_error("quota exhausted")
    assert cp.explain_error("something else") == "something else"


def test_cli_help(capsys):
    assert cp.main(["--help"]) == 0
    assert "copilot check" in capsys.readouterr().out


@pytest.mark.skipif(os.environ.get("MODELER_TEST_COPILOT_RUNTIME") != "1",
                    reason="starts the real Copilot runtime (set MODELER_TEST_COPILOT_RUNTIME=1)")
def test_runtime_registers_only_our_tools(plate, tmp_path):
    async def go():
        a = cp.CopilotAssistant(plate)  # no folder given, as in the app: the temporary one
        try:
            st = await a.status()
            assert "signed_in" in st
            session = await a._session()
            meta = await session.rpc.tools.get_current_metadata()
            return sorted(t.name for t in meta.tools)
        finally:
            await a.stop()

    names = run(go())
    assert names == sorted([d["name"] for d in cp.CopilotAssistant(plate).toolbox.definitions()]
                           + ["propose_commands", "propose_edits", "ask_pick", "highlight", "render", "render_detail", "render_compare", "list_files", "read_file"])


# ---- changing what is there ---------------------------------------------------------------
@pytest.fixture
def steps():
    p = Processor()
    for line in ("W = 40", "BLOCK, 0,0,0, W, 30, 10", "NAME, LAST, plate", "CYL, 20,15,-1, 4, 12",
                 "SUBTRACT, plate, LAST"):
        assert p.run(line).ok
    return p


def test_propose_edits_tries_them_in_a_sandbox(steps):
    seen = []
    a = cp.CopilotAssistant(steps, on_event=lambda k, d: seen.append((k, d)))
    tool = {t.name: t for t in a.sdk_tools()}["propose_edits"]
    res = run(tool.handler(ToolInvocation(arguments={
        "edits": [{"action": "edit", "entry": 1, "text": "W = 60"},
                  {"action": "insert", "entry": 6, "text": "SPHERE, 0,0,30, 2"}],
        "summary": "wider plate"})))
    assert res.result_type == "success", res.text_result_for_llm
    prop = [d for k, d in seen if k == "proposal"][0]
    assert prop.edits[0]["old"] == "W = 40"
    assert prop.commands() == ['HIST, EDIT, 1, "W = 60"', 'HIST, INSERT, 6, "SPHERE, 0,0,30, 2"']
    assert steps.evaluate("W") == 40 and len(steps.history) == 5  # nothing changed yet
    for line in prop.commands():
        assert steps.run(line).ok
    assert steps.evaluate("BBOX(plate).dx") == pytest.approx(60)


def test_propose_edits_refuses_edits_that_break_steps(steps):
    a = cp.CopilotAssistant(steps)
    tool = {t.name: t for t in a.sdk_tools()}["propose_edits"]
    res = run(tool.handler(ToolInvocation(arguments={"edits": [{"action": "delete", "entry": 2}]})))
    assert res.result_type == "failure" and "fail" in res.text_result_for_llm
    res = run(tool.handler(ToolInvocation(arguments={"edits": [{"action": "edit", "entry": 9, "text": "X = 1"}]})))
    assert "no entry 9" in res.text_result_for_llm
    assert len(steps.history) == 5


def test_imported_bodies_say_what_they_are(tmp_path):
    p = Processor()
    assert p.run(f'SPHERE, 0,0,0, 10\nEXPORT, STL, "{tmp_path}/s.stl"\nEXPORT, STEP, "{tmp_path}/s.step"\nCLEAR').ok
    for line in (f'IMPORT, STL, "{tmp_path}/s.stl", ball', f'IMPORT, STEP, "{tmp_path}/s.step", exact'):
        assert p.run(line).ok
    box = cp.CopilotAssistant(p).toolbox
    ball = box.call("describe_body", {"body": "ball"})
    assert ball["representation"] == "faceted" and ball["format"] == "STL" and ball["file"] == "s.stl"
    assert "FILLET" in ball["faceted"]["does_not_work"]
    exact = box.call("describe_body", {"body": "exact"})
    assert exact["representation"] == "exact" and exact["format"] == "STEP" and "DELFACE" in exact["note"]
    rows = box.call("model_summary")["bodies"]
    assert rows[0]["faceted"] is True and rows[0]["imported"] == "STL" and "faceted" not in rows[1]


# ---- the working folder ------------------------------------------------------------------
class FakeClient:
    seen: dict = {}

    def __init__(self, **kw):
        FakeClient.seen = kw

    async def start(self):
        pass


def test_the_client_always_gets_a_folder(plate, tmp_path, monkeypatch):
    """Empty mode refuses to start without base_directory (seen on Windows with SDK 1.0.33)."""
    import copilot

    monkeypatch.setattr(copilot, "CopilotClient", FakeClient)
    monkeypatch.setenv("MODELER_COPILOT_HOME", str(tmp_path / "temp"))
    monkeypatch.setenv("MODELER_COPILOT_DATA", str(tmp_path / "data"))
    a = cp.CopilotAssistant(plate)  # no folder chosen: a temporary one
    run(a.start())
    assert FakeClient.seen["mode"] == "empty"
    assert a.home == str(tmp_path / "temp")
    # the sign-in lives in a per-user folder, never in the (temporary or project) working folder
    assert FakeClient.seen["base_directory"] == str(tmp_path / "data")
    assert os.path.isdir(FakeClient.seen["base_directory"])


def test_a_chosen_folder_is_used(plate, tmp_path, monkeypatch):
    import copilot

    monkeypatch.setattr(copilot, "CopilotClient", FakeClient)
    monkeypatch.setenv("MODELER_COPILOT_DATA", str(tmp_path / "data"))
    a = cp.CopilotAssistant(plate, home=str(tmp_path / "proj"))
    run(a.start())
    assert FakeClient.seen["base_directory"] == str(tmp_path / "data")
    assert str(tmp_path) in cp.FOLDER_PROMPT.format(a.home)


def test_default_folder_is_temporary(monkeypatch):
    import tempfile

    monkeypatch.delenv("MODELER_COPILOT_HOME", raising=False)
    assert cp.default_home() == os.path.join(tempfile.gettempdir(), "3Dmodeling-assistant")


def test_sign_in_data_folder_per_platform(tmp_path, monkeypatch):
    monkeypatch.delenv("MODELER_COPILOT_DATA", raising=False)
    monkeypatch.setattr(cp.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert cp.runtime_dir() == os.path.join(str(tmp_path / "Roaming"), "3Dmodeling", "copilot")
    monkeypatch.setattr(cp.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    assert cp.runtime_dir() == os.path.join(str(tmp_path / "share"), "3Dmodeling", "copilot")


# ---- the first prompt, the Debug log, new chats, files ------------------------------------
def test_first_prompt_carries_every_command():
    from modeler.commands import REGISTRY
    text = cp.first_prompt("/work")
    assert "/work" in text and "Every command" in text
    for name in REGISTRY:
        assert f"\n{name}" in text or text.startswith(name), name
    assert "`!` starts a comment" in text and "LAST is the newest body" in text  # the basics
    assert len(text) < 40_000


def test_the_log_records_tool_calls_and_results(plate):
    seen = []
    a = cp.CopilotAssistant(plate, on_event=lambda k, d: seen.append((k, d)))
    tools = {t.name: t for t in a.sdk_tools()}
    run(tools["describe_body"].handler(ToolInvocation(arguments={"body": "plate"})))
    kinds = [e["kind"] for e in a.log]
    assert kinds == ["tool_call", "tool_result"]
    call, result = a.log
    assert call["args"] == {"body": "plate"} and result["ok"] and result["ms"] >= 0
    assert '"holes"' in result["result"]
    assert [d for k, d in seen if k == "debug"] == a.log
    text = cp.format_log(a.log)
    assert "TOOL CALL describe_body" in text and "TOOL RESULT describe_body (ok" in text


def test_ask_logs_the_system_message_prompt_and_reply(plate, monkeypatch):
    events = [Ev(AssistantMessageData(content="One hole.", message_id="m1")), Ev(SessionIdleData())]
    session = FakeSession(events=events)
    a = _assistant(plate, session)

    async def signed_in():
        return {"signed_in": True, "login": "octo", "message": ""}

    a.status = signed_in
    run(a.ask("holes?"))
    kinds = [e["kind"] for e in a.log]
    assert kinds == ["prompt", "reply"]
    a.session = session
    run(a.new_chat())
    assert session.disconnected and a.session is None
    assert a.log[-1]["kind"] == "new_chat"
    assert "NEW CHAT" in cp.format_log(a.log)


def _files(plate, tmp_path, answers):
    (tmp_path / "notes.txt").write_text("bolt circle 60 mm")
    (tmp_path / "sub").mkdir()
    (tmp_path / "blob.bin").write_bytes(b"\0\1\2")
    a = cp.CopilotAssistant(plate, home=str(tmp_path))
    asked = []

    def ask(what, path):
        asked.append((what, path))
        return answers.pop(0) if answers else "deny"

    a.ask_read = ask
    return a, asked


def test_reading_files_asks_first(plate, tmp_path):
    a, asked = _files(plate, tmp_path, ["deny", "once", "once"])
    assert "not allow" in a._files("read_file", {"path": "notes.txt"})["error"]
    assert a._files("read_file", {"path": "notes.txt"})["text"] == "bolt circle 60 mm"
    listing = a._files("list_files", {})
    assert listing["entries"][0] == "sub/" and any(e.startswith("notes.txt") for e in listing["entries"])
    assert len(asked) == 3
    assert [e["answer"] for e in a.log if e["kind"] == "permission"] == ["deny", "once", "once"]


def test_allow_for_this_chat_lasts_until_a_new_chat(plate, tmp_path):
    a, asked = _files(plate, tmp_path, ["chat"])
    assert "text" in a._files("read_file", {"path": "notes.txt"})
    assert "entries" in a._files("list_files", {"path": "sub"})
    assert len(asked) == 1
    run(a.new_chat())
    assert "error" in a._files("read_file", {"path": "notes.txt"})  # asked again, and the default is no
    assert len(asked) == 2


def test_files_stay_inside_the_working_folder(plate, tmp_path):
    a, asked = _files(plate, tmp_path, ["chat"])
    assert "outside" in a._files("read_file", {"path": "../secret.txt"})["error"]
    assert "outside" in a._files("read_file", {"path": "/etc/passwd"})["error"]
    assert "outside" in a._files("list_files", {"path": ".."})["error"]
    assert "no file" in a._files("read_file", {"path": "missing.txt"})["error"]
    assert asked == []  # refused before asking
    assert "not a text file" in a._files("read_file", {"path": "blob.bin"})["error"]


def test_file_tools_through_the_sdk(plate, tmp_path):
    a, _ = _files(plate, tmp_path, ["once"])
    tool = {t.name: t for t in a.sdk_tools()}["read_file"]
    res = run(tool.handler(ToolInvocation(arguments={"path": "notes.txt"})))
    assert res.result_type == "success" and "bolt circle" in res.text_result_for_llm


# ---- pointing ------------------------------------------------------------------------------
def test_ask_pick_waits_for_the_click(plate):
    import threading as th

    a = cp.CopilotAssistant(plate)
    asked = []

    def pick_request(kind, prompt, done):
        asked.append((kind, prompt))
        if done:  # the user clicks a little later, from another thread (as the GUI does)
            th.Timer(0.05, lambda: done(("FACE", 7))).start()

    a.pick_request = pick_request
    tool = {t.name: t for t in a.sdk_tools()}["ask_pick"]
    res = run(tool.handler(ToolInvocation(arguments={"kind": "face", "prompt": "Click the top face"})))
    assert res.result_type == "success", res.text_result_for_llm
    assert asked == [("FACE", "Click the top face")]
    assert '"id":7' in res.text_result_for_llm and '"selector"' in res.text_result_for_llm
    assert [e["kind"] for e in a.log if e["kind"].startswith("pick")] == ["pick_asked", "pick"]
    assert "THE USER CLICKED: FACE 7" in cp.format_log(a.log)


def test_ask_pick_without_a_view_or_cancelled(plate):
    a = cp.CopilotAssistant(plate)  # the default: no view, answers at once
    assert "did not pick" in run(a._ask_pick({"kind": "EDGE", "prompt": "x"}))["error"]
    assert "error" in run(a._ask_pick({"kind": "PLANET", "prompt": "x"}))


def test_ask_pick_gives_up_and_stops_asking(plate):
    a = cp.CopilotAssistant(plate)
    calls = []
    a.pick_request = lambda kind, prompt, done: calls.append(kind)
    assert "did not click" in run(a._ask_pick({"kind": "FACE", "prompt": "x"}, timeout=0.05))["error"]
    assert calls == ["FACE", None]  # asked, then stopped asking


def test_highlight_checks_ids_and_marks(plate):
    a = cp.CopilotAssistant(plate)
    assert a._highlight({"kind": "FACE", "ids": [7]})["shown"] is False  # no view
    marks = []
    a.show_marks = lambda kind, ids, note: marks.append((kind, ids, note)) or True
    assert a._highlight({"kind": "FACE", "ids": [7], "note": "the hole"}) == {"shown": True, "kind": "FACE",
                                                                              "ids": [7]}
    assert "error" in a._highlight({"kind": "FACE", "ids": [9999]})
    assert a._highlight({"kind": "FACE", "ids": []}) == {"cleared": True}
    assert marks == [("FACE", [7], "the hole"), ("", [], "")]


def test_user_context_describes_the_selection(plate):
    from modeler.ai.tools import Toolbox

    assert plate.run("PICK, FACE, 7").ok
    ctx = Toolbox(plate).call("user_context", {})
    assert ctx["selection"]["kind"] == "FACE" and ctx["selection"]["ids"] == [7]
    assert ctx["selection"]["described"]["faces"][0]["id"] == 7
    assert ctx["selection"]["selector"]["lines"]
    assert plate.run("SEL, NONE").ok
    assert "ask_pick" in Toolbox(plate).call("user_context", {})["selection"]["note"]


# ---- pictures, when text is not enough -----------------------------------------------------
def test_render_without_a_view_says_so(plate):
    a = cp.CopilotAssistant(plate)
    assert "no 3D view" in a._render({})["error"]
    assert "error" in a._render({"kind": "FACE", "highlight": [9999]})


def test_render_sends_the_picture(plate):
    seen = []
    a = cp.CopilotAssistant(plate, on_event=lambda k, d: seen.append((k, d)))
    asked = []
    png = b"\x89PNG\r\n\x1a\nfake"

    def render_view(view, w, h, kind, ids):
        asked.append((view, w, h, kind, ids))
        return png

    a.render_view = render_view
    tool = {t.name: t for t in a.sdk_tools()}["render"]
    res = run(tool.handler(ToolInvocation(arguments={"view": "TOP", "width": 5000, "kind": "face",
                                                     "highlight": [7]})))
    assert res.result_type == "success"
    assert asked == [("TOP", 1024, 768, "FACE", [7])]  # capped
    assert res.binary_results_for_llm[0].mime_type == "image/png"
    import base64
    assert base64.b64decode(res.binary_results_for_llm[0].data) == png
    assert '"shows":"the 3D view from TOP, face 7 marked in orange"' in res.text_result_for_llm
    assert "_png" not in res.text_result_for_llm
    assert ("picture", png) in seen
    assert a.log[-1]["image_bytes"] == len(png) and "picture 1 KB sent" in cp.format_log(a.log)


# ---- the conversation kept with the project, and Stop --------------------------------------
async def _signed_in():
    return {"signed_in": True, "login": "octo", "message": ""}


def test_earlier_text_keeps_the_newest_turns():
    chat = []
    for i in range(50):
        chat += [{"who": "you", "text": f"question {i}"}, {"who": "assistant", "text": f"answer {i} " + "x" * 80}]
    text = cp.earlier_text(chat, limit=1000)
    assert len(text) <= 1000
    assert text.endswith("answer 49 " + "x" * 80) and "User: question 49" in text
    assert "question 0" not in text
    assert cp.earlier_text([]) == ""


def test_a_fresh_chat_is_given_the_earlier_conversation_once(plate):
    events = [Ev(AssistantMessageData(content="ok", message_id="m1")), Ev(SessionIdleData())]
    session = FakeSession(events=events)
    a = cp.CopilotAssistant(plate)
    a.status = _signed_in

    async def fresh_session():  # like the real one: a session is made once per chat
        a.session = session
        return session

    a._session = fresh_session
    a.earlier = "User: make a plate\n\nAssistant: done, 40 x 30"
    run(a.ask("now a hole"))
    assert session.sent[0].startswith(cp.EARLIER_HEAD) and "done, 40 x 30" in session.sent[0]
    assert session.sent[0].endswith("now a hole")
    a.earlier = "User: something else"
    run(a.ask("and another"))  # the chat goes on: not given again
    assert session.sent[1] == "and another"


def test_stop_ends_the_wait_and_aborts(plate):
    class SlowSession(FakeSession):
        aborted = False

        async def abort(self):
            self.aborted = True

    session = SlowSession(events=[Ev(AssistantMessageData(content="partial", message_id="m1"))])  # never idle
    a = _assistant(plate, session)
    a.status = _signed_in

    async def go():
        task = asyncio.ensure_future(a.ask("long one"))
        for _ in range(20):
            await asyncio.sleep(0)
        assert await a.stop_answer()
        return await asyncio.wait_for(task, 5)

    reply = run(go())
    assert reply.stopped and reply.text == "partial" and not reply.error
    assert session.aborted
    assert not run(a.stop_answer())  # nothing to stop now
