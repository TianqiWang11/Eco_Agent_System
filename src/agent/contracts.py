from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Callable, Literal, Protocol, Union
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    arguments: dict[str, Any] = Field(default_factory=dict)


class RespondAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["respond"] = "respond"
    message: str = Field(min_length=1, max_length=12000)


class AskUserAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["ask_user"] = "ask_user"
    question: str = Field(min_length=1, max_length=2000)
    missing_fields: list[str] = Field(default_factory=list, max_length=10)


class CallToolAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["call_tool"] = "call_tool"
    calls: list[ToolCall] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def unique_call_ids(self):
        if len({c.id for c in self.calls}) != len(self.calls):
            raise ValueError("Duplicate tool call IDs")
        return self


class WaitAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["wait"] = "wait"
    reason: str = Field(min_length=1, max_length=2000)
    resume_hint: str | None = Field(default=None, max_length=500)


class FinishAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["finish"] = "finish"
    message: str = Field(min_length=1, max_length=12000)


AgentAction = Annotated[
    Union[RespondAction, AskUserAction, CallToolAction, WaitAction, FinishAction],
    Field(discriminator="type"),
]
ACTION_ADAPTER = TypeAdapter(AgentAction)


def validate_agent_action(value: Any) -> AgentAction:
    return ACTION_ADAPTER.validate_python(value)


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: dict
    handler: Callable[[dict, Any], dict]
    kind: Literal["local", "mcp", "sandbox"] = "local"
    approval: bool = False
    replay_safe: bool = False
    endpoint: str | None = None

    def model_schema(self):
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.schema}}


class ModelClient(Protocol):
    def next(self, messages: list[dict], tools: list[dict], state: dict) -> AgentAction: ...


TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
