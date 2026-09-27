import hashlib
import json
from dataclasses import dataclass


@dataclass
class ToolContext:
    sid: str
    state: dict
    sandbox: object
    telemetry: object
    policy: object

    def read_result(self, args):
        entry = self.state["ledger"].get(args["call_id"])
        if not entry or entry["status"] != "completed":
            raise ValueError("No completed result for this session")
        value = {k: v for k, v in entry["result"].items() if k not in {"artifacts", "raw_result"}}
        text = json.dumps(value, ensure_ascii=False, default=str)
        offset = args.get("offset", 0)
        return {"text": text[offset:offset + 2500], "next_offset": offset + 2500 if offset + 2500 < len(text) else None}


def fingerprint(call):
    return hashlib.sha256(json.dumps(call.model_dump(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ToolDispatcher:
    def __init__(self, registry, policy, store, telemetry, sandbox):
        self.registry, self.policy, self.store = registry, policy, store
        self.telemetry, self.sandbox = telemetry, sandbox

    def execute(self, call, state):
        tool = self.registry.resolve(call)
        sid, digest = state["id"], fingerprint(call)
        entry = state["ledger"].get(call.id)
        if entry:
            if entry["digest"] != digest:
                raise ValueError("Tool call ID reused with different arguments")
            if entry["status"] == "completed":
                return entry["result"]
            if entry["status"] == "started" and not tool.replay_safe:
                raise RuntimeError("Ambiguous external effect; automatic replay forbidden")
        approval = state.get("approval")
        if self.policy.approval_required(tool):
            if not approval or approval["digest"] != digest:
                state["approval"] = {"call": call.model_dump(), "digest": digest, "decision": None}
                state["status"] = "awaiting_approval"
                self.store.save(state)
                self.telemetry.emit(sid, "approval.requested", tool=call.name, call_id=call.id)
                return None
            if approval["decision"] is None:
                return None
            if not approval["decision"]:
                result = {"error": "User denied this operation"}
                state["ledger"][call.id] = {"digest": digest, "status": "completed", "result": result}
                self.store.save(state)
                return result
        if tool.endpoint:
            try:
                self.policy.network(tool.endpoint)
            except PermissionError:
                self.telemetry.emit(sid, "network.denied", tool=call.name)
                raise
            self.telemetry.emit(sid, "network.allowed", tool=call.name)
        state["ledger"][call.id] = {"digest": digest, "status": "started"}
        self.store.save(state)  # Write-ahead before any side effect.
        self.telemetry.emit(sid, "tool.started", tool=call.name, call_id=call.id)
        try:
            with self.telemetry.span("tool." + call.name, sid):
                result = tool.handler(call.arguments, ToolContext(sid, state, self.sandbox, self.telemetry, self.policy))
                if not isinstance(result, dict):
                    raise TypeError("Tool must return a JSON object")
                # Force JSON-safe durable values at the adapter boundary.
                result = json.loads(json.dumps(result, ensure_ascii=False, default=str))
        except Exception as exc:
            if not tool.replay_safe:
                self.telemetry.emit(sid, "tool.failed", tool=call.name, error_type=type(exc).__name__)
                # Keep started ledger state: a failed external request may have taken effect.
                raise
            result = {
                "isError": True,
                "error": str(exc)[:1000] or type(exc).__name__,
            }
        state["ledger"][call.id] = {"digest": digest, "status": "completed", "result": result}
        self.store.save(state)
        self.telemetry.emit(sid, "tool.failed" if result.get("isError") else "tool.completed",
                            tool=call.name, call_id=call.id)
        return result
