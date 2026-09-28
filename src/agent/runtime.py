import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .session import SessionStore
from .telemetry import Telemetry
from .tools.registry import ToolRegistry
from .tools.local_tools import register_local
from .tools.mcp import MCPTools
from .harness.context import ContextManager
from .harness.policy import Policy
from .harness.dispatcher import ToolDispatcher
from .harness.model import ToolCallingModel
from .harness.loop import AgentLoop
from .contracts import ToolCall

CONTRACT_VERSION = 4


class Runtime:
    def __init__(self, root: Path, model=None, registry=None, recover=True):
        self.store = SessionStore(root / "sessions.sqlite3")
        recovered = self.store.recover() if recover else []
        self.telemetry = Telemetry(self.store)
        for sid in recovered:
            self.telemetry.emit(sid, "session.interrupted")
        servers = {}
        default_config = Path(__file__).resolve().parents[2] / "config" / "mcp.json"
        config_file = os.getenv("AGENT_MCP_CONFIG") or (
            str(default_config) if default_config.is_file() else None
        )
        if config_file:
            config = json.loads(Path(config_file).read_text(encoding="utf-8"))
            servers = config.get("servers", {})
            if not isinstance(servers, dict):
                raise ValueError("MCP config 'servers' must be an object")
        self.policy = Policy([item["url"] for item in servers.values()])
        self.sandbox = None  # Sandbox is deliberately outside the active runtime until a task needs it.
        self.registry = registry or ToolRegistry()
        if registry is None:
            register_local(self.registry)
            MCPTools(servers).register(self.registry)
        if model is None:
            self.policy.allowed_endpoints.add(ToolCallingModel.network_endpoint())
        self.model = model or ToolCallingModel(self.policy, self.telemetry)
        self.dispatcher = ToolDispatcher(self.registry, self.policy, self.store, self.telemetry, self.sandbox)
        self.loop = AgentLoop(self.model, ContextManager(), self.dispatcher, self.store, self.telemetry)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent")
        self.guard = threading.RLock()
        self.active = set()

    def create(self, query):
        state, token = self.store.create(query)
        state["contract_version"] = CONTRACT_VERSION
        self.store.save(state)
        self.telemetry.emit(state["id"], "session.created")
        self.telemetry.emit(state["id"], "prompt.received", chars=len(query))
        return state, token

    def start_session(self, query):
        with self.guard:
            if len(self.active) >= 16:
                raise ValueError("Task queue is full")
            state, token = self.create(query)
            self.submit(state["id"])
            return state, token

    def submit(self, sid):
        with self.guard:
            if sid in self.active:
                raise ValueError("Task is already scheduled")
            if len(self.active) >= 16:
                raise ValueError("Task queue is full")
            if self.store.get(sid)["status"] != "queued":
                raise ValueError("Task is not queued")
            self.active.add(sid)
            self.executor.submit(self._run, sid)

    def _run(self, sid):
        try:
            state = self.store.get(sid)
            if state.get("contract_version") != CONTRACT_VERSION:
                state.update(status="failed", final={"answer": "该任务使用已停用的工具契约，请创建新任务。旧记录仍保留。", "artifacts": []})
                self.store.save(state)
                self.telemetry.emit(sid, "session.failed", error_type="ContractVersionMismatch")
                return
            self.loop.run(state)
        finally:
            with self.guard:
                self.active.discard(sid)

    def approve(self, sid, digest, allow):
        with self.guard:
            state = self.store.get(sid)
            if state.get("contract_version") != CONTRACT_VERSION:
                raise ValueError("任务工具契约已更新，请创建新任务；不会批准旧指令")
            if sid in self.active or state["status"] != "awaiting_approval":
                raise ValueError("Task is not awaiting approval")
            approval = state["approval"]
            if not approval or approval["digest"] != digest or approval["decision"] is not None:
                raise ValueError("Stale or already consumed approval")
            approval["decision"] = allow
            state["status"] = "queued"
            self.store.save(state)
            self.telemetry.emit(sid, "approval.approved" if allow else "approval.denied",
                                tool=approval["call"]["name"], call_id=approval["call"]["id"])
            self.submit(sid)

    def resume(self, sid):
        with self.guard:
            state = self.store.get(sid)
            if state.get("contract_version") != CONTRACT_VERSION:
                raise ValueError("任务工具契约已更新，请创建新任务；不会重放旧指令")
            if sid in self.active or state["status"] not in {"failed", "interrupted", "waiting"}:
                raise ValueError("Task is not resumable")
            for value in state["pending"]:
                call = ToolCall.model_validate(value)
                entry = state["ledger"].get(call.id)
                if entry and entry["status"] == "started" and not self.registry.resolve(call).replay_safe:
                    raise ValueError("工具可能已产生外部效果，请人工核实；不能自动重试")
            if state["step"] >= self.loop.max_steps:
                raise ValueError("任务已耗尽步骤预算，请创建新任务")
            state["status"], state["final"], state["wait"] = "queued", None, None
            self.store.save(state)
            self.telemetry.emit(sid, "session.resumed")
            self.submit(sid)

    def turn(self, sid, query):
        with self.guard:
            state = self.store.get(sid)
            if state.get("contract_version") != CONTRACT_VERSION:
                raise ValueError("任务工具契约已更新，请创建新任务")
            if sid in self.active or state["status"] not in {"completed", "cancelled", "awaiting_input"}:
                raise ValueError("Finish the current task before starting another turn")
            state["blocks"].append([{"role": "user", "content": query}])
            state.update(query=query, status="queued", step=0, pending=[], results=[], approval=None, final=None,
                         current_action=None, input_request=None, wait=None,
                         turn=state["turn"] + 1, query_pinned=False, fast_route=False)
            state["task_state"] = {"known_facts": [], "constraints": [], "open_questions": [], "completed_steps": []}
            self.store.save(state)
            self.telemetry.emit(sid, "prompt.received", chars=len(query))
            self.submit(sid)

    def public(self, sid):
        state = self.store.get(sid)
        approval = state.get("approval")
        public_approval = None
        if state["status"] == "awaiting_approval" and approval:
            public_approval = {
                "digest": approval["digest"],
                "summary": "继续执行这项受控操作需要你的确认。",
            }
        public_input = state.get("input_request") if state["status"] == "awaiting_input" else None
        public_wait = state.get("wait") if state["status"] == "waiting" else None
        phases = {"queued": "working", "running": "working", "awaiting_approval": "needs_approval",
                  "awaiting_input": "needs_input", "waiting": "waiting", "completed": "done",
                  "cancelled": "done", "failed": "error", "interrupted": "error"}
        return {"id": sid, "status": state["status"], "turn": state["turn"], "step": state["step"],
                "contract_version": state.get("contract_version"),
                "phase": phases.get(state["status"], "working"), "final": state["final"],
                "approval": public_approval, "input_request": public_input, "wait": public_wait}

    def user_view(self, sid):
        snapshot = self.public(sid)
        return {key: snapshot[key] for key in (
            "id", "phase", "final", "approval", "input_request", "wait"
        )}

    def close(self):
        self.executor.shutdown(wait=True)
        self.telemetry.close()


_runtime = None
_guard = threading.Lock()


def get_runtime():
    global _runtime
    with _guard:
        if _runtime is None:
            root = Path(os.getenv("AGENT_STATE_DIR") or str(Path(__file__).resolve().parents[2] / "storage" / "agent"))
            _runtime = Runtime(root)
    return _runtime
