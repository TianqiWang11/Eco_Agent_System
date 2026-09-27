from src.agent.contracts import ToolSpec


def register_sandbox(registry):
    path = {"type": "string", "minLength": 1, "maxLength": 200}
    def schema(properties):
        return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
    registry.register(ToolSpec("workspace_read", "读取当前Session工作区内UTF-8文件，最大64KiB。",
        schema({"path": path}), lambda a, c: c.sandbox.local.read(a["path"], c.sandbox.workspace(c.sid)),
        kind="sandbox", replay_safe=True))
    registry.register(ToolSpec("workspace_write", "在当前Session工作区创建UTF-8文件，不覆盖已有文件。",
        schema({"path": path, "text": {"type": "string", "maxLength": 16000}}),
        lambda a, c: c.sandbox.local.write(a["path"], a["text"], c.sandbox.workspace(c.sid)),
        kind="sandbox", approval=True))
    registry.register(ToolSpec("sandbox_python", "在显式启用的Docker沙箱中运行Python；无网络，只读工作区；未启用时拒绝。",
        schema({"code": {"type": "string", "minLength": 1, "maxLength": 12000}}),
        lambda a, c: c.sandbox.execute(a["code"], c.sid), kind="sandbox", approval=True))
    registry.register(ToolSpec("session_result", "按call_id读取本Session已保存工具结果的文本片段，避免上下文截断丢失。",
        {"type": "object", "properties": {"call_id": {"type": "string"},
         "offset": {"type": "integer", "minimum": 0}}, "required": ["call_id"], "additionalProperties": False},
        lambda a, c: c.read_result(a), replay_safe=True))
