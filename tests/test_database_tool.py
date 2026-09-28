from types import SimpleNamespace

from src.agent.contracts import ToolCall
from src.agent.tools.local_tools import database_tools
from src.agent.tools.local_tools.registration import register_local
from src.agent.tools.registry import ToolRegistry


def database_spec():
    registry = ToolRegistry()
    register_local(registry)
    call = ToolCall(id="db-call", name="database", arguments={"operation": "summary"})
    return registry.resolve(call)


def test_database_tool_is_read_only_and_does_not_require_approval():
    spec = database_spec()
    assert spec.replay_safe is True
    assert spec.approval is False
    assert "SQL" not in spec.schema["properties"]
    assert set(spec.schema["properties"]["operation"]["enum"]) == {
        "describe_schema", "summary", "search_trees", "tree_detail"
    }


def test_database_tool_describes_semantics_without_database_connection():
    result = database_spec().handler(
        {"operation": "describe_schema", "table": "tree_segmentation"},
        SimpleNamespace(),
    )
    table = result["tables"]["tree_segmentation"]
    assert table["grain"] == "每个分割出的单木对象一行。"
    assert table["fields"]["dbh_m"]["unit"] == "m"
    assert any("没有树种字段" in item for item in table["limitations"])


def test_database_catalog_prevents_unsafe_raw_table_join_assumption():
    result = database_spec().handler({"operation": "describe_schema"}, SimpleNamespace())
    assert "只有 trees 与 tree_measurements" in result["join_rule"]
    assert result["tables"]["forest_inventory"]["fields"]["tree_id"]["description"].startswith(
        "原调查"
    )


def test_database_tool_summary(monkeypatch):
    monkeypatch.setattr(database_tools, "data_summary", lambda: {"tree_count": 1526})
    result = database_spec().handler({"operation": "summary"}, SimpleNamespace())
    assert result == {"operation": "summary", "summary": {"tree_count": 1526}}


def test_database_tool_requires_tree_id_for_detail():
    result = database_spec().handler({"operation": "tree_detail"}, SimpleNamespace())
    assert result["isError"] is True
    assert "tree_id" in result["error"]
