from jsonschema import Draft202012Validator


MANAGED_TOOL_NAMES = {
    "database", "get_data", "analysis", "knowledge", "predict", "ue_scene",
    "web_search", "mcp_list_tools", "mcp_call_tool", "mcp_list_resources",
    "mcp_read_resource", "workspace_read", "workspace_write", "sandbox_python",
    "session_result",
}


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, tool):
        if tool.name in self.tools:
            raise ValueError("Duplicate tool name")
        Draft202012Validator.check_schema(tool.schema)
        self.tools[tool.name] = tool

    def resolve(self, call):
        if call.name not in self.tools:
            raise ValueError("Unknown tool")
        tool = self.tools[call.name]
        # Reject remote references instead of allowing validator network retrieval.
        def check(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "$ref" and not str(value).startswith("#"):
                        raise ValueError("Remote schema references are forbidden")
                    check(value)
            elif isinstance(node, list):
                for value in node:
                    check(value)
        check(tool.schema)
        Draft202012Validator(tool.schema).validate(call.arguments)
        return tool

    def schemas(self, allowed_names=None):
        return [
            tool.model_schema()
            for name, tool in self.tools.items()
            if allowed_names is None or name in allowed_names or name not in MANAGED_TOOL_NAMES
        ]
