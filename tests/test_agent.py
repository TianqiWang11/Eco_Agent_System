import asyncio
import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.agent.contracts import (
    AskUserAction,
    CallToolAction,
    RespondAction,
    ToolCall,
    ToolSpec,
    WaitAction,
    validate_agent_action,
)
from src.agent.runtime import Runtime
from src.agent.session import SessionStore
from src.agent.harness.context import ContextManager
from src.agent.harness.router import FastRouter, compose_fast_response, relevant_tool_names
from src.agent.harness.dispatcher import ToolContext
from src.agent.harness.policy import Policy
from src.agent.sandbox.local import LocalSandbox
from src.agent.sandbox.workspace import Workspace
from src.agent.tools.registry import ToolRegistry
from src.agent.tools.mcp import MCPTools

SCHEMA = {"type": "object", "properties": {"value": {"type": "integer"}},
          "required": ["value"], "additionalProperties": False}


class FakeModel:
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.contexts = []

    def next(self, messages, tools, state):
        self.contexts.append(messages)
        return next(self.decisions)


def decision(name="calculate", cid="c1", value=3):
    return CallToolAction(calls=[ToolCall(id=cid, name=name, arguments={"value": value})])


@pytest.fixture
def build(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_MCP_CONFIG", raising=False)
    monkeypatch.delenv("AGENT_OTLP_ENDPOINT", raising=False)
    runtimes = []
    def factory(decisions, approval=False, handler=None, replay_safe=True):
        registry = ToolRegistry()
        registry.register(ToolSpec("calculate", "calculate", SCHEMA,
            handler or (lambda a, c: {"value": a["value"] * 2}), approval=approval, replay_safe=replay_safe))
        runtime = Runtime(tmp_path / str(len(runtimes)), FakeModel(decisions), registry)
        runtimes.append(runtime)
        return runtime
    yield factory
    for runtime in runtimes:
        runtime.close()


def run(runtime, query="统计测试"):
    state, token = runtime.create(query)
    runtime.loop.run(state)
    return state["id"], token


def wait(runtime, sid):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        task = runtime.public(sid)
        if sid not in runtime.active and task["status"] not in {"queued", "running"}:
            return task
        time.sleep(0.01)
    raise AssertionError("Task did not settle")


@pytest.mark.parametrize("operation", ["resume", "turn", "approve"])
def test_old_contract_is_readable_but_cannot_execute(build, operation):
    rt = build([])
    state, token = rt.create("historical")
    state.pop("contract_version")
    rt.store.save(state)
    before = rt.store.get(state["id"])
    arguments = {"resume": (), "turn": ("follow up",), "approve": ("digest", True)}
    with pytest.raises(ValueError, match="契约"):
        getattr(rt, operation)(state["id"], *arguments[operation])
    assert rt.store.get(state["id"]) == before
    assert rt.store.authenticate(state["id"], token)
    assert rt.public(state["id"])["contract_version"] is None


def test_tool_loop_and_trace_redaction(build):
    rt = build([decision(), RespondAction(message="计算完成")])
    sid, token = run(rt, "private prompt password=secret")
    state = rt.store.get(sid)
    assert state["status"] == "completed"
    assert state["results"] == [{"value": 6}]
    assert rt.store.authenticate(sid, token)
    events = rt.store.developer_events(sid)
    assert "tool.completed" in [e["kind"] for e in events]
    assert [(e["stage"], e["message"]) for e in rt.store.events(sid)] == [
        ("understanding", "正在理解你的需求…"),
        ("working", "正在调用工具处理任务…"),
    ]
    assert "secret" not in json.dumps(events)
    assert "private prompt" not in json.dumps(events)
    assert any(m["role"] == "tool" for m in rt.model.contexts[-1])


@pytest.mark.parametrize("allow", [True, False])
def test_approval_is_durable_bound_and_single_use(build, allow):
    calls = []
    rt = build([decision(), RespondAction(message="完成")], approval=True,
               handler=lambda a, c: calls.append(a) or {"ok": True})
    sid, _ = run(rt)
    task = rt.public(sid)
    assert task["status"] == "awaiting_approval" and not calls
    with pytest.raises(ValueError):
        rt.approve(sid, "0" * 64, True)
    digest = task["approval"]["digest"]
    assert SessionStore(rt.store.path).get(sid)["approval"]["digest"] == digest
    rt.approve(sid, digest, allow)
    assert wait(rt, sid)["status"] == "completed"
    assert len(calls) == int(allow)
    with pytest.raises(ValueError):
        rt.approve(sid, digest, allow)


def test_multiple_calls_do_not_repeat_completed_effects(build):
    calls = []
    d = CallToolAction(calls=[ToolCall(id=str(i), name="calculate", arguments={"value": i}) for i in (1, 2)])
    rt = build([d, RespondAction(message="ok")], approval=True, replay_safe=False,
               handler=lambda a, c: calls.append(a["value"]) or {"ok": True})
    sid, _ = run(rt)
    for _ in range(2):
        rt.approve(sid, rt.public(sid)["approval"]["digest"], True)
        wait(rt, sid)
    assert calls == [1, 2]


def test_ambiguous_effect_must_not_auto_replay(build):
    rt = build([decision()], replay_safe=False)
    state, _ = rt.create("test")
    from src.agent.harness.dispatcher import fingerprint
    call = decision().calls[0]
    state.update(status="running", pending=[call.model_dump()])
    state["ledger"][call.id] = {"digest": fingerprint(call), "status": "started"}
    rt.store.save(state)
    rt.store.recover()
    assert rt.public(state["id"])["status"] == "interrupted"
    with pytest.raises(ValueError, match="外部效果"):
        rt.resume(state["id"])


def test_recover_completed_call_without_reexecution(build):
    calls = []
    rt = build([RespondAction(message="恢复完成")], handler=lambda a, c: calls.append(1) or {})
    state, _ = rt.create("test")
    call = decision().calls[0]
    state["pending"] = [call.model_dump()]
    result = rt.dispatcher.execute(call, state)
    state["status"] = "interrupted"
    rt.store.save(state)
    rt.resume(state["id"])
    assert wait(rt, state["id"])["status"] == "completed"
    assert calls == [1]


def test_parameter_validation_before_execution(build):
    calls = []
    rt = build([CallToolAction(calls=[ToolCall(id="x", name="calculate", arguments={"value": "wrong"})])],
               handler=lambda a, c: calls.append(a) or {})
    sid, _ = run(rt)
    assert rt.public(sid)["status"] == "failed" and not calls


def test_replay_safe_tool_error_returns_to_loop_instead_of_crashing(build):
    rt = build([
        decision(),
        RespondAction(message="工具失败，已如实说明"),
    ], handler=lambda a, c: (_ for _ in ()).throw(ValueError("bad input")))
    sid, _ = run(rt)
    state = rt.store.get(sid)
    assert state["status"] == "completed"
    assert state["results"][0]["isError"] is True
    assert state["action_history"][0]["type"] == "call_tool"


def test_session_revision_and_access_isolation(build):
    rt = build([])
    a, token = rt.create("a")
    b, _ = rt.create("b")
    old = rt.store.get(a["id"])
    rt.store.save(a)
    with pytest.raises(RuntimeError, match="revision"):
        rt.store.save(old)
    assert not rt.store.authenticate(b["id"], token)


def test_context_budget_and_complete_tool_blocks():
    manager = ContextManager(budget=5500)
    block = [{"role": "assistant", "tool_calls": [{"id": "a"}], "content": None},
             {"role": "tool", "tool_call_id": "a", "content": "x" * 1500}]
    state = {"objective": "保留目标", "query": "当前问题", "memory": "", "blocks": [block for _ in range(10)]}
    messages, removed = manager.build(state, [])
    assert removed > 0
    assert len(json.dumps([messages, []], ensure_ascii=False)) <= 5500
    assert "保留目标" in json.dumps(messages, ensure_ascii=False)
    assert sum(m["role"] == "tool" for m in messages) == sum(bool(m.get("tool_calls")) for m in messages)
    with pytest.raises(ValueError, match="budget"):
        manager.build({"objective": "x" * 10000, "query": "x", "memory": "", "blocks": []}, [])


def test_fast_router_handles_demo_queries_without_model_tool_guessing():
    router = FastRouter()
    biomass = router.route("统计2025年总生物量")
    assert len(biomass) == 1
    assert biomass[0].name == "analysis"
    assert biomass[0].arguments == {
        "dataset": "grid_plot", "metric": "agb", "operation": "summary",
    }

    database = router.route("统计数据库树木数量最多的前5个树种")
    assert len(database) == 1
    assert database[0].name == "database"
    assert database[0].arguments == {"operation": "summary"}


def test_specialized_tools_are_hidden_without_explicit_intent():
    ordinary = relevant_tool_names("统计2025年总生物量")
    assert "sandbox_python" not in ordinary
    assert "ue_scene" not in ordinary
    assert "mcp_call_tool" not in ordinary
    assert "sandbox_python" not in relevant_tool_names("请在Sandbox运行Python脚本")
    assert relevant_tool_names("请介绍你的能力，不要查询数据") == set()
    assert relevant_tool_names("查询数据库中的样地数量") == {"database"}


def test_fast_response_composes_agb_without_another_model_round():
    answer = compose_fast_response("统计2025年总生物量", [{
        "dataset": "grid_plot",
        "metric": "agb",
        "summary": {
            "total_records": 2,
            "valid_agb_records": 2,
            "missing_agb_records": 0,
            "agb_sum_kg": 1234.5,
            "agb_mean_kg": 617.25,
            "agb_max_kg": 800.0,
        },
        "notes": ["测试范围"],
    }])
    assert "1,234.50 kg" in answer
    assert "2025年" in answer


@pytest.mark.parametrize("path", ["../secret", "/tmp/secret", "C:/secret", "a/../../secret", "a:stream", "..\\secret"])
def test_workspace_denies_escape(tmp_path, path):
    with pytest.raises(PermissionError):
        Workspace(tmp_path, "a" * 32).resolve(path)


def test_local_workspace_files_no_overwrite_no_execution(tmp_path):
    w = Workspace(tmp_path, "a" * 32)
    local = LocalSandbox()
    local.write("result.txt", "数据", w)
    assert local.read("result.txt", w)["text"] == "数据"
    with pytest.raises(FileExistsError):
        local.write("result.txt", "覆盖", w)
    with pytest.raises(PermissionError):
        local.execute("print(1)", w)


def test_network_and_remote_schema_denied():
    policy = Policy(["https://example.org/mcp"])
    policy.network("https://example.org/mcp")
    for url in ["https://evil.org/mcp", "file:///etc/passwd", "https://user:pass@example.org/mcp"]:
        with pytest.raises(PermissionError):
            policy.network(url)
    registry = ToolRegistry()
    registry.register(ToolSpec("bad", "bad", {"$ref": "https://example.org/schema"}, lambda a, c: {}))
    with pytest.raises(ValueError, match="Remote"):
        registry.resolve(ToolCall(id="a", name="bad"))


def test_steps_are_bounded(build):
    rt = build([decision(cid="a"), decision(cid="b")])
    rt.loop.max_steps = 2
    sid, _ = run(rt)
    assert rt.public(sid)["status"] == "failed"
    assert rt.store.get(sid)["step"] == 2


def test_api_auth_sse_and_approval(build, monkeypatch):
    from src.agent import api
    rt = build([decision(), RespondAction(message="done")], approval=True)
    monkeypatch.setattr(api, "get_runtime", lambda: rt)
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as client:
        created = client.post("/agent/sessions", json={"message": "sensitive prompt"})
        assert created.status_code == 202
        data = created.json()
        sid = data["id"]
        headers = {"Authorization": "Bearer " + data["token"]}
        wait(rt, sid)
        assert client.get(f"/agent/sessions/{sid}").status_code == 401
        assert client.get(f"/agent/sessions/{sid}", headers={"Authorization": "Bearer wrong"}).status_code == 404
        events = client.get(f"/agent/sessions/{sid}/events", headers=headers)
        assert "user.progress" in events.text and "sensitive prompt" not in events.text
        assert "calculate" not in events.text and "call_id" not in events.text
        task = client.get(f"/agent/sessions/{sid}", headers=headers).json()
        assert not {"status", "turn", "step", "contract_version"} & set(task)
        assert task["phase"] == "needs_approval"
        assert set(task["approval"]) == {"digest", "summary"}
        response = client.post(f"/agent/sessions/{sid}/approval", headers=headers,
            json={"digest": task["approval"]["digest"], "allow": True})
        assert response.status_code == 202
        wait(rt, sid)
        assert client.get(f"/agent/sessions/{sid}", headers=headers).json()["final"]["answer"] == "done"


@contextmanager
def mcp_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None: pass
        def do_GET(self):
            self.send_response(405); self.end_headers()
        def do_DELETE(self):
            self.send_response(204); self.end_headers()
        def do_POST(self):
            value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if "id" not in value:
                self.send_response(202); self.end_headers(); return
            results = {
                "initialize": {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}, "resources": {}}, "serverInfo": {"name": "fixture", "version": "1"}},
                "tools/list": {"tools": [{"name": "double", "description": "double", "inputSchema": SCHEMA}]},
                "tools/call": {"content": [{"type": "text", "text": "6"}], "isError": False},
                "resources/list": {"resources": [{"uri": "eco://fixture", "name": "sample"}]},
                "resources/read": {"contents": [{"uri": "eco://fixture", "text": "sample data"}]},
            }
            payload = json.dumps({"jsonrpc": "2.0", "id": value["id"], "result": results[value["method"]]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try: yield f"http://127.0.0.1:{server.server_port}/mcp"
    finally: server.shutdown(); server.server_close(); thread.join()


def test_real_mcp_sdk_tools_and_resources(build):
    rt = build([])
    state, _ = rt.create("mcp fixture")
    with mcp_server() as url:
        adapter = MCPTools({"fixture": {"url": url}})
        context = ToolContext(state["id"], state, rt.sandbox, rt.telemetry, Policy([url]))
        for operation, args, key in [
            ("list_tools", {}, "tools"), ("call_tool", {"name": "double", "arguments": {"value": 3}}, "content"),
            ("list_resources", {}, "resources"), ("read_resource", {"uri": "eco://fixture"}, "contents"),
        ]:
            result = asyncio.run(adapter.request(operation, {"server": "fixture", **args}, context))
            assert result[key]
        context.policy = Policy()
        with pytest.raises(PermissionError):
            asyncio.run(adapter.request("list_tools", {"server": "fixture"}, context))
        assert rt.store.developer_events(state["id"])[-1]["kind"] == "network.denied"


def test_mcp_web_search_capability_registers_stable_tool():
    registry = ToolRegistry()
    MCPTools({
        "search": {
            "url": "https://search.example/mcp",
            "capabilities": {
                "web_search": {"tool": "provider_search"},
            },
        }
    }).register(registry)
    tool = registry.resolve(ToolCall(
        id="search-1",
        name="web_search",
        arguments={"query": "车八岭自然保护区"},
    ))
    assert tool.kind == "mcp"
    assert not tool.approval
    assert tool.replay_safe
    assert tool.endpoint == "https://search.example/mcp"
    policy = Policy(["https://search.example/mcp"])
    assert not policy.approval_required(tool)
    assert policy.approval_required(registry.tools["mcp_call_tool"])


def test_followup_preserves_message_order(build):
    rt = build([RespondAction(message="第一轮回答"), RespondAction(message="第二轮回答")])
    sid, _ = run(rt, "第一轮问题")
    rt.turn(sid, "第二轮问题")
    assert wait(rt, sid)["status"] == "completed"
    conversation = [m["content"] for m in rt.model.contexts[-1] if m["role"] != "system"]
    assert conversation.index("第一轮问题") < conversation.index("第一轮回答") < conversation.index("第二轮问题")


def test_action_contract_rejects_extra_fields_and_duplicate_calls():
    with pytest.raises(ValueError):
        validate_agent_action({"type": "respond", "message": "ok", "calls": []})
    with pytest.raises(ValueError):
        CallToolAction(calls=decision().calls * 2)


def test_model_message_cannot_bypass_or_mix_action_categories():
    from src.agent.harness.model import decode_action_message
    with pytest.raises(ValueError, match="must select"):
        decode_action_message({"role": "assistant", "content": "自由文本回答"})
    with pytest.raises(ValueError, match="cannot be mixed"):
        decode_action_message({"tool_calls": [
            {"id": "a", "function": {"name": "_respond", "arguments": '{"message":"回答"}'}},
            {"id": "b", "function": {"name": "calculate", "arguments": '{"value":3}'}},
        ]})


def test_ask_user_pauses_and_followup_resumes_same_session(build):
    rt = build([
        AskUserAction(question="请提供预测年份", missing_fields=["target_year"]),
        RespondAction(message="已收到年份"),
    ])
    sid, _ = run(rt, "预测这些树")
    task = rt.public(sid)
    assert task["status"] == "awaiting_input"
    assert task["input_request"]["missing_fields"] == ["target_year"]
    assert task["final"]["answer"] == "请提供预测年份"
    rt.turn(sid, "2035年")
    assert wait(rt, sid)["status"] == "completed"
    assert rt.public(sid)["final"]["answer"] == "已收到年份"


def test_wait_releases_loop_and_can_be_explicitly_resumed(build):
    rt = build([
        WaitAction(reason="等待外部UE任务", resume_hint="收到UE回执后恢复"),
        RespondAction(message="外部任务已完成"),
    ])
    sid, _ = run(rt, "等待UE")
    task = rt.public(sid)
    assert task["status"] == "waiting"
    assert task["wait"]["resume_hint"] == "收到UE回执后恢复"
    rt.resume(sid)
    assert wait(rt, sid)["status"] == "completed"


def test_action_history_is_durable_and_finite(build):
    rt = build([decision(), RespondAction(message="完成")])
    sid, _ = run(rt)
    history = rt.store.get(sid)["action_history"]
    assert [item["type"] for item in history] == ["call_tool", "respond"]
    assert all(item["status"] == "completed" for item in history)


def test_docker_command_has_isolation_and_no_pull(tmp_path, monkeypatch):
    from src.agent.sandbox.docker import DockerSandbox
    from src.agent.sandbox.manager import SandboxManager
    from unittest.mock import Mock
    commands = []
    def launch(command, **kwargs):
        commands.append(command)
        return Mock(poll=lambda: 0, returncode=0)
    monkeypatch.setattr("src.agent.sandbox.docker.subprocess.Popen", launch)
    monkeypatch.setattr("src.agent.sandbox.docker.subprocess.run", lambda command, **kwargs: commands.append(command))
    result = DockerSandbox().execute("print(1)", Workspace(tmp_path, "b" * 32))
    assert result["exit_code"] == 0
    for arg in ["--network=none", "--read-only", "--cap-drop=ALL", "--pull=never", "--memory=256m", "--user=65534:65534"]:
        assert arg in commands[0]
    assert commands[1][:3] == ["docker", "rm", "-f"]
    assert commands[1][3] == commands[0][commands[0].index("--name") + 1]
    with pytest.raises(PermissionError):
        SandboxManager(tmp_path).execute("print(1)", "c" * 32)


def test_otlp_trace_log_metrics_export_not_raw_prompt(tmp_path, monkeypatch):
    from src.agent.telemetry import Telemetry
    received = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None: pass
        def do_POST(self):
            received.append((self.path, self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200); self.send_header("Content-Length", "0"); self.end_headers()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    monkeypatch.setenv("AGENT_OTLP_ENDPOINT", f"http://127.0.0.1:{server.server_port}")
    store = SessionStore(tmp_path / "otlp.sqlite3")
    telemetry = Telemetry(store)
    state, _ = store.create("TOP_SECRET_PROMPT")
    try:
        with telemetry.span("run", state["id"]):
            telemetry.emit(state["id"], "prompt.received", chars=17, prompt="TOP_SECRET_PROMPT")
        assert telemetry.provider is not None
        assert telemetry.meter_provider is not None
        assert telemetry.logger_provider is not None
        telemetry.provider.force_flush()
        telemetry.meter_provider.force_flush()
        telemetry.logger_provider.force_flush()
        assert {"/v1/traces", "/v1/logs", "/v1/metrics"} <= {p for p, _ in received}
        assert all(b"TOP_SECRET_PROMPT" not in body for _, body in received)
        assert store.events(state["id"]) == []
        assert store.developer_events(state["id"])[0]["details"] == {"chars": "17"}
    finally:
        telemetry.close(); server.shutdown(); server.server_close(); thread.join()


def test_native_model_sdk_contract_against_local_server(build, monkeypatch):
    from types import SimpleNamespace
    from src.agent.harness.model import ToolCallingModel
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None: pass
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            message = (
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "local_call", "type": "function",
                     "function": {"name": "calculate", "arguments": '{"value":3}'}}
                ]}
                if len(requests) == 1
                else {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "finish_call", "type": "function",
                     "function": {"name": "_finish", "arguments": '{"message":"结果为6"}'}}
                ]}
            )
            result = {"id": "test", "object": "chat.completion", "created": 0, "model": "fixture",
                      "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls"}]}
            data = json.dumps(result).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_port}/v1"
    config = SimpleNamespace(model="kimi-k3", base_url=base, timeout=3, max_retries=0,
                             api_key="fixture-not-real", reasoning_effort="medium",
                             max_completion_tokens=512)
    monkeypatch.setattr("src.agent.harness.model.load_model_settings", lambda **kwargs: config)
    rt = build([])
    rt.loop.model = ToolCallingModel(Policy([base + "/chat/completions"]), rt.telemetry)
    try:
        sid, _ = run(rt)
        assert rt.public(sid)["final"]["answer"] == "结果为6"
        assert len(requests) == 2 and requests[0]["tools"]
        assert requests[0]["tool_choice"] == "required"
        assert requests[-1]["messages"][-1]["role"] == "tool"
    finally:
        server.shutdown(); server.server_close(); thread.join()
