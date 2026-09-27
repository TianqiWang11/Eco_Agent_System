"""Kimi client that must return exactly one validated Agent Action category."""
import json

import httpx

from src.agent.contracts import (
    AskUserAction,
    CallToolAction,
    FinishAction,
    RespondAction,
    ToolCall,
    WaitAction,
)
from src.agent.harness.provider import load_model_settings


def _action_schema(name, description, properties, required):
    return {"type": "function", "function": {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }}


ACTION_SCHEMAS = [
    _action_schema("_respond", "Respond：直接回答当前请求并结束当前轮。",
                   {"message": {"type": "string", "minLength": 1, "maxLength": 12000}}, ["message"]),
    _action_schema("_ask_user", "AskUser：缺少不可安全推断的关键信息时向用户提一个明确问题。",
                   {"question": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "missing_fields": {"type": "array", "items": {"type": "string"}, "maxItems": 10}},
                   ["question"]),
    _action_schema("_wait", "Wait：仅当外部异步任务确实仍在处理时暂停，等待外部恢复。",
                   {"reason": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "resume_hint": {"type": "string", "maxLength": 500}}, ["reason"]),
    _action_schema("_finish", "Finish：多步骤任务完成后给出最终总结并结束当前轮。",
                   {"message": {"type": "string", "minLength": 1, "maxLength": 12000}}, ["message"]),
]
CONTROL_ACTIONS = {"_respond", "_ask_user", "_wait", "_finish"}


def decode_action_message(message):
    """Convert one native model message into exactly one finite Agent Action."""
    raw_calls = message.get("tool_calls") or []
    if not raw_calls:
        raise ValueError("Model must select one Agent Action")
    parsed = [(
        call["id"],
        call["function"]["name"],
        json.loads(call["function"]["arguments"]),
    ) for call in raw_calls]
    controls = [item for item in parsed if item[1] in CONTROL_ACTIONS]
    if controls:
        if len(parsed) != 1:
            raise ValueError("A control Agent Action cannot be mixed with tool calls")
        _, name, arguments = controls[0]
        if name == "_respond":
            return RespondAction(message=arguments["message"])
        if name == "_ask_user":
            return AskUserAction(
                question=arguments["question"],
                missing_fields=arguments.get("missing_fields", []),
            )
        if name == "_wait":
            return WaitAction(reason=arguments["reason"], resume_hint=arguments.get("resume_hint"))
        return FinishAction(message=arguments["message"])
    return CallToolAction(calls=[
        ToolCall(id=call_id, name=name, arguments=arguments)
        for call_id, name, arguments in parsed
    ])


class ToolCallingModel:
    def __init__(self, policy=None, telemetry=None):
        self.policy, self.telemetry = policy, telemetry

    @staticmethod
    def network_endpoint():
        config = load_model_settings(require_api_key=False)
        return config.base_url.rstrip("/") + "/chat/completions"

    def next(self, messages, tools, state):
        config = load_model_settings()
        payload: dict[str, object] = {
            "model": config.model,
            "messages": messages,
            "stream": False,
            "max_completion_tokens": config.max_completion_tokens,
        }
        payload["tools"] = [*tools, *ACTION_SCHEMAS]
        payload["tool_choice"] = "required"
        if config.model.startswith("kimi-k3"):
            payload["reasoning_effort"] = config.reasoning_effort
        else:
            payload["thinking"] = {"type": "disabled"}

        endpoint = self.network_endpoint()

        def check(request):
            try:
                if not self.policy:
                    raise PermissionError("Model network policy is not configured")
                self.policy.network(str(request.url))
            except PermissionError:
                if self.telemetry:
                    self.telemetry.emit(state["id"], "network.denied", tool="model")
                raise

        check(httpx.Request("POST", endpoint))
        if self.telemetry:
            self.telemetry.emit(state["id"], "network.allowed", tool="model")

        transport = httpx.HTTPTransport(retries=config.max_retries)
        with httpx.Client(
            timeout=config.timeout,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            event_hooks={"request": [check]},
        ) as client:
            response = client.post(
                endpoint,
                headers={"Authorization": f"Bearer {config.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        if choice.get("finish_reason") in {"length", "content_filter"}:
            raise ValueError("Model response was incomplete")
        message = choice["message"]
        return decode_action_message(message)
