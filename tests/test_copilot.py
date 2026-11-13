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
    assert names == [d["name"] for d in a.toolbox.definitions()] + ["propose_commands", "propose_edits"]
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
    assert props == [cp.Proposal("CYL, 0,0,0, 1, 2", "a pin")]
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
    assert login.inputs[-1] == "yes"


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
        a = cp.CopilotAssistant(plate, home=str(tmp_path))
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
                           + ["propose_commands", "propose_edits"])


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
