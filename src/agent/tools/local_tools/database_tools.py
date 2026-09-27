"""Structured, read-only access to the configured PostgreSQL tree database."""

from __future__ import annotations

from src.platform.data.database import (
    DatabaseUnavailable,
    data_summary,
    search_trees,
    tree_detail,
)


def query_database(arguments: dict) -> dict:
    operation = arguments["operation"]
    try:
        if operation == "summary":
            return {"operation": operation, "summary": data_summary()}

        if operation == "search_trees":
            result = search_trees(
                tree_id=arguments.get("tree_id"),
                species=arguments.get("species"),
                plot_id=arguments.get("plot_id"),
                measurement_year=arguments.get("year"),
                page=1,
                page_size=arguments.get("limit", 10),
            )
            return {"operation": operation, **result}

        if operation == "tree_detail":
            tree_id = str(arguments.get("tree_id") or "").strip()
            if not tree_id:
                raise ValueError("tree_detail 查询必须提供 tree_id")
            result = tree_detail(tree_id)
            return {
                "operation": operation,
                "found": result is not None,
                "result": result,
            }

        raise ValueError("不支持的数据库查询操作")
    except DatabaseUnavailable:
        return {
            "isError": True,
            "error": "PostgreSQL 数据库暂时不可用，请检查平台数据库连接。",
        }
    except ValueError as exc:
        return {"isError": True, "error": str(exc)}
