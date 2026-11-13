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
    assert names == [d["name"] for d in a.toolbox.definitions()] + ["propose_commands"]
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
                           + ["propose_commands"])
