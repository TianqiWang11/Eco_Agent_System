"""Durable Agent Action loop.

Each iteration follows one explicit lifecycle:
load state -> build context -> propose action -> validate -> execute -> persist
-> apply loop control.
"""

from src.agent.contracts import CallToolAction, FinishAction, ToolCall, validate_agent_action
from src.agent.harness.actions import ActionExecutor, ActionValidator
from src.agent.harness.router import FastRouter, compose_fast_response, relevant_tool_names


class AgentLoop:
    def __init__(self, model, context, dispatcher, store, telemetry, max_steps=8, router=None):
        self.model, self.context, self.dispatcher = model, context, dispatcher
        self.store, self.telemetry, self.max_steps = store, telemetry, max_steps
        self.router = router or FastRouter()
        self.validator = ActionValidator(dispatcher.registry)
        self.executor = ActionExecutor(dispatcher, context, store, telemetry)

    def _record_action(self, state: dict, action, source: str):
        state["step"] += 1
        serialized = action.model_dump()
        state["current_action"] = serialized
        state["action_history"].append({
            "step": state["step"],
            "turn": state.get("turn", 1),
            "type": action.type,
            "source": source,
            "status": "selected",
        })
        self.store.save(state)
        self.telemetry.emit(state["id"], "action.selected", step=state["step"])

    def _resume_pending_action(self, state: dict):
        value = state.get("current_action")
        action = validate_agent_action(value) if value else CallToolAction(
            calls=[ToolCall.model_validate(call) for call in state["pending"]]
        )
        action = self.validator.validate(action, state, resuming=True)
        return self.executor.execute(action, state)

    def _finish_fast_route(self, state: dict):
        action = FinishAction(message=compose_fast_response(state["query"], state["results"]))
        action = self.validator.validate(action, state)
        self._record_action(state, action, "harness")
        return self.executor.execute(action, state)

    def _candidate_action(self, state: dict):
        routed = (
            self.router.route(state["query"], state.get("turn", 1))
            if state["step"] == 0 and not state["results"]
            else []
        )
        if routed:
            state["fast_route"] = True
            return CallToolAction(calls=routed), "harness"

        allowed = relevant_tool_names(state["query"])
        if any(entry.get("status") == "completed" for entry in state["ledger"].values()):
            allowed.add("session_result")
        schemas = self.dispatcher.registry.schemas(allowed)
        messages, removed = self.context.build(state, schemas)
        if removed:
            self.telemetry.emit(state["id"], "context.compacted", count=removed)
        self.store.save(state)
        self.telemetry.emit(state["id"], "model.started", step=state["step"])
        with self.telemetry.span("model.next", state["id"]):
            action = self.model.next(messages, schemas, state)
        call_count = len(action.calls) if isinstance(action, CallToolAction) else 0
        self.telemetry.emit(state["id"], "model.completed", count=call_count)
        return action, "model"

    def run(self, state):
        sid = state["id"]
        state["status"] = "running"
        self.store.save(state)
        self.telemetry.emit(sid, "session.started")
        try:
            with self.telemetry.span("agent.run", sid):
                while True:
                    # 1. State is loaded by Runtime. Resume a durable action first.
                    if state["pending"]:
                        control = self._resume_pending_action(state)
                        if control != "continue":
                            return
                        if state.get("fast_route"):
                            self._finish_fast_route(state)
                            return

                    # 2-3. Context Manager builds model input; model or Harness
                    # proposes exactly one finite Agent Action.
                    if state["step"] >= self.max_steps:
                        raise RuntimeError("Agent Action step budget exhausted")
                    candidate, source = self._candidate_action(state)

                    # 4. Strict action contract and tool argument validation.
                    action = self.validator.validate(candidate, state)

                    # 5-6. Execute the action and durably write Session/State.
                    self._record_action(state, action, source)
                    control = self.executor.execute(action, state)

                    # 7. Loop control.
                    if control == "continue":
                        if state.get("fast_route"):
                            self._finish_fast_route(state)
                            return
                        continue
                    return
        except Exception as exc:
            state["status"] = "failed"
            state["error_type"] = type(exc).__name__
            state["current_action"] = None
            if state.get("action_history"):
                state["action_history"][-1]["status"] = "failed"
            state["final"] = {
                "answer": "本次任务未完成。请检查工具配置或任务执行状态后再试。",
                "artifacts": [],
            }
            self.store.save(state)
            self.telemetry.emit(sid, "session.failed", error_type=type(exc).__name__)
