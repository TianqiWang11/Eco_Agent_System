"""Validation and execution boundary for the finite Agent Action state machine."""

from __future__ import annotations

import json
from typing import Literal

from src.agent.contracts import (
    AgentAction,
    AskUserAction,
    CallToolAction,
    FinishAction,
    RespondAction,
    WaitAction,
    ToolCall,
    validate_agent_action,
)
from src.agent.presentation import public_response

LoopControl = Literal["continue", "pause", "stop"]


class ActionValidator:
    def __init__(self, registry):
        self.registry = registry

    def validate(self, value, state: dict, *, resuming: bool = False) -> AgentAction:
        action = validate_agent_action(value)
        if isinstance(action, CallToolAction):
            for call in action.calls:
                self.registry.resolve(call)
                if not resuming and call.id in state["ledger"]:
                    raise ValueError("Model reused an existing tool-call ID")
        return action


class ActionExecutor:
    def __init__(self, dispatcher, context, store, telemetry):
        self.dispatcher = dispatcher
        self.context = context
        self.store = store
        self.telemetry = telemetry

    @staticmethod
    def _set_history_status(state: dict, status: str):
        if state.get("action_history"):
            state["action_history"][-1]["status"] = status

    def _complete(self, action: RespondAction | FinishAction, state: dict) -> LoopControl:
        payload = {
            "answer": action.message,
            "artifacts": [item for result in state["results"] for item in result.get("artifacts", [])],
            "ue_actions": [item for result in state["results"] for item in result.get("ue_actions", [])],
        }
        state["final"] = public_response(payload)
        state["blocks"].append([{"role": "assistant", "content": state["final"]["answer"]}])
        state["status"] = "completed"
        state["current_action"] = None
        self._set_history_status(state, "completed")
        self.store.save(state)
        self.telemetry.emit(state["id"], "session.completed")
        return "stop"

    def _call_tools(self, action: CallToolAction, state: dict) -> LoopControl:
        if not state["pending"]:
            state["pending"] = [call.model_dump() for call in action.calls]
            self.store.save(state)
        results = []
        for value in state["pending"]:
            call = ToolCall.model_validate(value)
            result = self.dispatcher.execute(call, state)
            if result is None:
                self._set_history_status(state, "paused")
                self.store.save(state)
                return "pause"
            results.append(result)
        block = [{"role": "assistant", "content": None, "tool_calls": [
            {"id": call["id"], "type": "function", "function": {
                "name": call["name"],
                "arguments": json.dumps(call["arguments"], ensure_ascii=False),
            }} for call in state["pending"]
        ]}]
        for call, result in zip(state["pending"], results):
            block.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": self.context.tool_content(result, call["id"]),
            })
        state["blocks"].append(block)
        state["results"].extend(results)
        completed = state.setdefault("task_state", {}).setdefault("completed_steps", [])
        completed.extend({"tool": call["name"], "result": "error" if result.get("isError") else "ok"}
                         for call, result in zip(state["pending"], results))
        state["task_state"]["completed_steps"] = completed[-12:]
        state["pending"], state["approval"], state["current_action"] = [], None, None
        self._set_history_status(state, "completed")
        self.store.save(state)
        return "continue"

    def execute(self, action: AgentAction, state: dict) -> LoopControl:
        if isinstance(action, CallToolAction):
            return self._call_tools(action, state)
        if isinstance(action, AskUserAction):
            state["status"] = "awaiting_input"
            state["input_request"] = {
                "question": action.question,
                "missing_fields": action.missing_fields,
            }
            state["final"] = public_response({"answer": action.question})
            state["blocks"].append([{"role": "assistant", "content": action.question}])
            state["current_action"] = None
            self._set_history_status(state, "awaiting_input")
            self.store.save(state)
            self.telemetry.emit(state["id"], "user.input_required")
            return "pause"
        if isinstance(action, WaitAction):
            state["status"] = "waiting"
            state["wait"] = {"reason": action.reason, "resume_hint": action.resume_hint}
            state["final"] = public_response({"answer": action.reason})
            state["current_action"] = None
            self._set_history_status(state, "waiting")
            self.store.save(state)
            self.telemetry.emit(state["id"], "session.waiting")
            return "pause"
        if isinstance(action, (RespondAction, FinishAction)):
            return self._complete(action, state)
        raise TypeError("Unsupported Agent Action")
