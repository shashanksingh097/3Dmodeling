"""The MCP server (ai/mcp_server.py): the assistant's tools for any MCP client."""

from __future__ import annotations

import io
import json
import subprocess
import sys

import pytest

from modeler.ai.mcp_server import PROTOCOL, Server
from modeler.ai.tools import Toolbox
from modeler.commands import Processor


def server():
    return Server(Toolbox(Processor()), io.StringIO(), "test")


def req(s, mid, method, params=None):
    msg = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        msg["params"] = params
    return s.handle(json.dumps(msg))


def test_handshake_and_tool_list():
    s = server()
    r = req(s, 1, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                 "clientInfo": {"name": "t", "version": "1"}})
    assert r["result"]["protocolVersion"] == "2025-03-26"
    assert r["result"]["capabilities"]["tools"] == {"listChanged": False}
    assert req(s, 2, "initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"] == PROTOCOL
    assert s.handle(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})) is None
    tools = req(s, 3, "tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"run", "model_summary", "describe_body", "check", "sandbox", "probe_ray"} <= names
    assert all(t["inputSchema"]["type"] == "object" for t in tools)
    assert req(s, 4, "ping")["result"] == {}


def test_tools_call_models_and_reports_errors():
    s = server()
    r = req(s, 1, "tools/call", {"name": "run", "arguments": {"script": "NOSUCHCOMMAND, 1"}})
    assert "unknown command" in r["result"]["content"][0]["text"]
    r = req(s, 2, "tools/call", {"name": "run", "arguments": {"script": "CYL, 0,0,0, 5, 10"}})
    body = json.loads(r["result"]["content"][0]["text"])
    assert not r["result"]["isError"], body
    assert r["result"]["structuredContent"] == body
    r = req(s, 3, "tools/call", {"name": "check", "arguments": {"expectations": ["VALID(1)", "VOL(1) > 100"]}})
    assert not r["result"]["isError"], r
    r = req(s, 4, "tools/call", {"name": "describe_body", "arguments": {"body": 999}})
    assert r["result"]["isError"] is True


def test_protocol_errors():
    s = server()
    assert s.handle("{not json")["error"]["code"] == -32700
    assert req(s, 1, "no/such")["error"]["code"] == -32601
    assert req(s, 2, "tools/call", {"name": "nope"})["error"]["code"] == -32602
    assert req(s, 3, "tools/call", {"name": "run", "arguments": [1]})["error"]["code"] == -32602
    assert s.handle(json.dumps({"jsonrpc": "2.0", "id": 9, "result": {}})) is None
    batch = s.handle(json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "ping"},
                                 {"jsonrpc": "2.0", "method": "notifications/initialized"}]))
    assert batch == [{"jsonrpc": "2.0", "id": 1, "result": {}}]


def test_the_command_line_server_keeps_stdout_clean(tmp_path):
    script = tmp_path / "start.cmd"
    script.write_text('BLOCK, 0,0,0, 10,10,10\n*MSG, "this goes to stderr"\n')
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTOCOL}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "model_summary", "arguments": {}}},
    ]
    proc = subprocess.run([sys.executable, "-m", "modeler", "mcp", "--script", str(script)],
                          input="".join(json.dumps(m) + "\n" for m in lines),
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    answers = [json.loads(x) for x in proc.stdout.splitlines()]  # every stdout line is JSON
    assert [a["id"] for a in answers] == [1, 2]
    summary = answers[1]["result"]["structuredContent"]
    assert "1" in json.dumps(summary)


def test_with_the_mcp_package_client(tmp_path):
    """The reference client library talks to it (skipped where it is not installed)."""
    mcp = pytest.importorskip("mcp")
    import anyio
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "modeler", "mcp"])
        async with stdio_client(params) as (r, w):
            async with mcp.ClientSession(r, w) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert any(t.name == "run" for t in tools.tools)
                res = await session.call_tool("run", {"script": "SPHERE, 0,0,0, 5"})
                assert not getattr(res, "isError", getattr(res, "is_error", False))
                res = await session.call_tool("model_summary", {})
                return res.content[0].text

    text = anyio.run(go)
    assert "SPHERE" in text.upper() or "1" in text


def test_apply_then_save_and_export(tmp_path):
    s = server()
    req(s, 1, "tools/call", {"name": "run", "arguments": {"script": "BLOCK, 0,0,0, 10,10,10\nNAME, LAST, cube"}})
    # the working copy is what the reading tools look at
    summ = req(s, 2, "tools/call", {"name": "model_summary", "arguments": {}})["result"]["structuredContent"]
    assert len(summ["bodies"]) == 1
    out = req(s, 3, "tools/call", {"name": "export", "arguments": {"path": str(tmp_path / "early.step")}})
    assert "apply first" in out["result"]["structuredContent"]["hint"]  # the model itself is still empty
    r = req(s, 4, "tools/call", {"name": "apply", "arguments": {}})["result"]["structuredContent"]
    assert r["applied"] == 2 and r["bodies"] == 1
    for fname in ("cube.step", "cube.stl"):
        r = req(s, 5, "tools/call", {"name": "export", "arguments": {"path": str(tmp_path / fname), "body": "cube"}})
        assert not r["result"]["isError"], r
        assert (tmp_path / fname).stat().st_size > 100
    r = req(s, 6, "tools/call", {"name": "save_project", "arguments": {"path": str(tmp_path / "cube.m3d")}})
    assert not r["result"]["isError"], r
    r = req(s, 7, "tools/call", {"name": "export", "arguments": {"path": str(tmp_path / "cube.xyz")}})
    assert r["result"]["isError"]
