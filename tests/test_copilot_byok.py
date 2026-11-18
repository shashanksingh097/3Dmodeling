"""'Use your own key': provider settings, keys kept only on request, and (with
MODELER_TEST_COPILOT_RUNTIME=1) the real Copilot runtime talking to a fake
OpenAI-compatible service on this computer, with the modeler's tools."""

import asyncio
import json
import os
import stat
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from modeler.ai import providers as pv

pytest.importorskip("copilot", reason="the assistant needs the GitHub Copilot SDK (Python 3.11+)")

from modeler.ai import copilot as cp  # noqa: E402
from modeler.commands import Processor  # noqa: E402


@pytest.fixture(autouse=True)
def private_data(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELER_COPILOT_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("MODELER_AI_KEY", raising=False)


@pytest.fixture
def plate():
    p = Processor()
    assert p.run("BLOCK, 0,0,0, 40,30,10\nNAME, LAST, plate\nCYL, 20,15,-1, 4, 12\nSUBTRACT, plate, LAST").ok
    return p


def test_kinds_and_what_is_missing():
    assert list(pv.KINDS) == ["copilot", "openai", "anthropic", "azure", "ollama", "custom"]
    assert pv.ProviderSetting().problem() == "" and pv.ProviderSetting().sdk_config() is None
    s = pv.ProviderSetting("openai")
    assert s.problem() == "name the model"
    s.model = "gpt-test"
    assert s.problem() == "enter the API key"
    s.api_key = "sk-1"
    assert s.problem() == ""
    assert s.sdk_config() == {"type": "openai", "base_url": "https://api.openai.com/v1", "wire_model": "gpt-test",
                              "api_key": "sk-1"}
    assert pv.ProviderSetting("azure", "dep", api_key="k").problem() == "give the service's address"
    local = pv.ProviderSetting("ollama", "qwen3")
    assert local.problem() == ""  # no key for a model on this computer
    assert local.sdk_config() == {"type": "openai", "base_url": "http://localhost:11434/v1", "wire_model": "qwen3",
                                  "model_provider": "ollama"}
    assert pv.ProviderSetting("anthropic", "claude-sonnet-5-5").label() == "Anthropic Claude: claude-sonnet-5-5"
    assert "api_key" not in repr(pv.ProviderSetting("openai", "m", api_key="secret")).replace("api_key=", "")


def test_the_environment_key_wins(monkeypatch):
    monkeypatch.setenv("MODELER_AI_KEY", "from-env")
    s = pv.ProviderSetting("openai", "m", api_key="stored")
    assert s.problem() == "" and s.sdk_config()["api_key"] == "from-env"


def test_keys_are_kept_only_when_asked_and_privately():
    assert pv.load_key("openai") == ""
    path = pv.save_key("openai", "sk-1")
    pv.save_key("anthropic", "sk-2")
    assert pv.load_key("openai") == "sk-1" and pv.load_key("anthropic") == "sk-2"
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    pv.save_key("openai", "")
    assert pv.load_key("openai") == "" and pv.load_key("anthropic") == "sk-2"
    s = pv.from_settings({"kind": "anthropic", "model": "claude-sonnet-5-5"})
    assert s.api_key == "sk-2"
    assert pv.from_settings({"kind": "nonsense"}).is_copilot
    assert "api_key" not in s.to_settings()


def test_own_key_needs_no_github(plate):
    a = cp.CopilotAssistant(plate, provider=pv.ProviderSetting("openai", "gpt-test", api_key="sk"))
    st = asyncio.run(a.status())
    assert st == {"signed_in": True, "login": "OpenAI: gpt-test", "message": "", "own_key": True}
    assert asyncio.run(a.quota()) == {}
    assert asyncio.run(a.models()) == [{"id": "gpt-test", "name": "OpenAI: gpt-test"}]
    with pytest.raises(cp.AssistantError, match="own key"):
        asyncio.run(a.sign_in(lambda *x: None))


def test_missing_key_is_explained_before_starting(plate):
    a = cp.CopilotAssistant(plate, provider=pv.ProviderSetting("openai", "gpt-test"))
    with pytest.raises(cp.AssistantError, match="enter the API key"):
        asyncio.run(a.ask("hello"))
    assert a.client is None  # nothing was started


def test_pictures_only_for_models_that_see_them(plate):
    assert pv.ProviderSetting("openai").sees_pictures() and not pv.ProviderSetting("ollama").sees_pictures()
    assert pv.ProviderSetting("ollama", vision=True).sees_pictures()
    assert pv.from_settings(pv.ProviderSetting("custom", "m", vision=True).to_settings()).vision is True
    assert pv.from_settings({"kind": "custom"}).vision is None

    def names(setting):
        return [t.name for t in cp.CopilotAssistant(plate, provider=setting).sdk_tools()]

    assert "render" in names(pv.ProviderSetting("anthropic", "m", api_key="k"))
    assert "render" not in names(pv.ProviderSetting("ollama", "qwen3"))
    assert "render" in names(pv.ProviderSetting())  # Copilot knows its models


def test_copilot_setting_keeps_the_copilot_path(plate):
    a = cp.CopilotAssistant(plate, provider=pv.ProviderSetting("copilot", "gpt-5"))
    assert a.provider is None and a.model == "gpt-5"


def test_cli_rejects_unknown_provider(capsys):
    assert cp.main(["ask", "--provider", "nope", "hi"]) == 2
    assert "one of copilot, openai" in capsys.readouterr().out


# ---- the real runtime against a fake OpenAI-compatible service ----------------------------
class FakeOpenAI(BaseHTTPRequestHandler):
    requests: list = []
    tool = ("describe_body", {"body": "plate"})  # what the fake model calls first

    def log_message(self, *a):
        pass

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send_json({"object": "list", "data": [{"id": "fake-model", "object": "model"}]})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        FakeOpenAI.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": req})
        msgs = req.get("messages", [])
        if any(m.get("role") == "tool" for m in msgs):
            delta = {"role": "assistant", "content": "The plate has one hole, 8 mm across."}
            finish = "stop"
        else:
            delta = {"role": "assistant", "content": None, "tool_calls": [{
                "index": 0, "id": "call_1", "type": "function",
                "function": {"name": FakeOpenAI.tool[0], "arguments": json.dumps(FakeOpenAI.tool[1])}}]}
            finish = "tool_calls"
        if not req.get("stream"):
            msg = dict(delta)
            if "tool_calls" in msg:
                msg["tool_calls"] = [{k: v for k, v in c.items() if k != "index"} for c in msg["tool_calls"]]
            self._send_json({"id": "c1", "object": "chat.completion", "model": req.get("model"),
                             "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
                             "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in ({"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                      {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                       "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}):
            chunk.update({"id": "c1", "object": "chat.completion.chunk", "model": req.get("model")})
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


@pytest.mark.skipif(os.environ.get("MODELER_TEST_COPILOT_RUNTIME") != "1",
                    reason="starts the real Copilot runtime (set MODELER_TEST_COPILOT_RUNTIME=1)")
def test_runtime_with_own_key_uses_the_tools(plate, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    FakeOpenAI.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        a = cp.CopilotAssistant(plate, provider=pv.ProviderSetting("custom", "fake-model", url, "sk-test"))

        async def go():
            try:
                return await asyncio.wait_for(a.ask("How big is the hole?", timeout=120), 150)
            finally:
                await a.stop()

        reply = asyncio.run(go())
    finally:
        server.shutdown()
    assert not reply.error, reply.error
    assert "8 mm" in reply.text and "describe_body" in reply.tools
    first = FakeOpenAI.requests[0]
    assert first["auth"] == "Bearer sk-test" and first["body"]["model"] == "fake-model"
    system = next(m for m in first["body"]["messages"] if m["role"] == "system")["content"]
    assert "Every command" in system  # our first prompt, not the runtime's own
    names = {t["function"]["name"] for t in first["body"].get("tools", [])}
    assert {"describe_body", "propose_commands", "read_file"} <= names
    assert "bash" not in names and "shell" not in names
    result = [m for m in FakeOpenAI.requests[-1]["body"]["messages"] if m["role"] == "tool"]
    assert '"holes"' in str(result[0]["content"])
    assert [e["kind"] for e in a.log][:4] == ["system", "prompt", "tool_call", "tool_result"]


@pytest.mark.skipif(os.environ.get("MODELER_TEST_COPILOT_RUNTIME") != "1",
                    reason="starts the real Copilot runtime (set MODELER_TEST_COPILOT_RUNTIME=1)")
def test_runtime_sends_pictures_to_the_model(plate, monkeypatch):
    import base64

    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    FakeOpenAI.requests = []
    FakeOpenAI.tool = ("render", {"view": "ISO"})
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        a = cp.CopilotAssistant(plate, provider=pv.ProviderSetting("custom", "fake-model", url, "sk-test",
                                                                   vision=True))
        a.render_view = lambda *args: png

        async def go():
            try:
                return await asyncio.wait_for(a.ask("Does it look right?", timeout=120), 150)
            finally:
                await a.stop()

        reply = asyncio.run(go())
    finally:
        server.shutdown()
        FakeOpenAI.tool = ("describe_body", {"body": "plate"})
    assert not reply.error, reply.error
    assert "render" in reply.tools
    last = json.dumps(FakeOpenAI.requests[-1]["body"]["messages"])
    assert base64.b64encode(png).decode() in last  # the picture reached the model
    assert "omitted" not in last


@pytest.mark.skipif(os.environ.get("MODELER_TEST_COPILOT_RUNTIME") != "1",
                    reason="starts the real Copilot runtime (set MODELER_TEST_COPILOT_RUNTIME=1)")
def test_runtime_benchmark_task(monkeypatch):
    """The benchmark's path end to end: the fake model proposes the flange's reference script."""
    from modeler.ai import bench

    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    task = bench.TASKS[0]
    FakeOpenAI.requests = []
    FakeOpenAI.tool = ("propose_commands", {"script": task.reference, "summary": "a flange"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        a = cp.CopilotAssistant(Processor(), provider=pv.ProviderSetting("custom", "fake-model", url, "sk"))

        async def go():
            try:
                return await bench.run(bench.assistant_ask(a), ["flange"], log=lambda *x: None)
            finally:
                await a.stop()

        results = asyncio.run(go())
    finally:
        server.shutdown()
        FakeOpenAI.tool = ("describe_body", {"body": "plate"})
    r = results[0]
    assert r.passed, (r.note, r.checks)
    assert r.turns == 2 and r.input_tokens > 0 and r.tools == ["propose_commands"]
