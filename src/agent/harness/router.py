"""Deterministic routing for common, latency-sensitive demo queries."""

from __future__ import annotations

import re

from src.agent.contracts import ToolCall


class FastRouter:
    @staticmethod
    def _id(turn: int, name: str, index: int = 1) -> str:
        return f"fast_{turn}_{name}_{index}"

    def route(self, query: str, turn: int = 1) -> list[ToolCall]:
        text = query.strip()
        lowered = text.lower()
        if ("生物量" in text or "agb" in lowered) and any(
            word in text for word in ("统计", "汇总", "总", "计算", "分析")
        ):
            year_match = re.search(r"\b(2016|2021|2025)\b", text)
            year = int(year_match.group(1)) if year_match else None
            if year in {2016, 2021}:
                arguments = {"dataset": "monitoring", "year": year,
                             "metric": "agb", "operation": "summary"}
            else:
                arguments = {"dataset": "grid_plot", "metric": "agb",
                             "operation": "summary"}
            return [ToolCall(id=self._id(turn, "analysis"), name="analysis", arguments=arguments)]

        database_words = "数据库" in text or "入库" in text
        summary_words = any(word in text for word in (
            "总数", "数量", "多少", "概览", "汇总", "最多", "前5", "前 5", "树种数", "样地数",
        ))
        if database_words and summary_words:
            calls = [ToolCall(id=self._id(turn, "database", 1), name="database",
                              arguments={"operation": "summary"})]
            tree_match = re.search(r"(?:编号|tree[_ ]?id)[为是：:\s]*([0-9]{7})\b", text, re.IGNORECASE)
            if tree_match:
                calls.append(ToolCall(id=self._id(turn, "database", 2), name="database",
                                      arguments={"operation": "tree_detail", "tree_id": tree_match.group(1)}))
            return calls
        return []


def relevant_tool_names(query: str) -> set[str]:
    """Limit hazardous and specialized capabilities to explicit user intent."""
    text = query.lower()
    if any(word in text for word in ("不要查询", "无需查询", "不调用工具", "不要调用工具")):
        return set()
    names = set()
    if any(word in text for word in ("数据库", "入库", "树木编号", "单木编号", "样地", "查询数据", "查一下数据")):
        names.add("database")
    if any(word in text for word in (
        "统计", "分析", "生物量", "agb", "胸径", "树高", "结构复杂度", "分布图", "直方图", "网格图",
    )):
        names.add("analysis")
    if any(word in text for word in ("原始数据", "本地数据", "excel", "缺失值", "数据表")):
        names.add("get_data")
    if any(word in text for word in ("知识库", "依据资料", "项目资料", "研究依据", "文献")):
        names.add("knowledge")
    if any(word in text for word in ("预测", "未来", "生长模型")):
        names.add("predict")
    if any(word in text for word in ("ue", "场景", "高亮", "聚焦", "建模", "可视化")):
        names.add("ue_scene")
    if any(word in text for word in ("联网", "网络搜索", "网上", "最新", "近期", "新闻")):
        names.add("web_search")
    if "mcp" in text:
        names.update({"mcp_list_tools", "mcp_call_tool", "mcp_list_resources", "mcp_read_resource"})
    if any(word in text for word in ("sandbox", "沙箱", "python脚本", "运行代码", "工作区", "创建文件")):
        names.update({"workspace_read", "workspace_write", "sandbox_python"})
    return names


def compose_fast_response(query: str, results: list[dict]) -> str:
    """Render deterministic results without paying for a second model round."""
    failed = next((result for result in results if result.get("isError")), None)
    if failed:
        return "数据处理未完成：" + str(failed.get("error") or "当前数据不可用。")

    if len(results) == 1 and results[0].get("metric") == "agb":
        result = results[0]
        summary = result["summary"]
        scope = "2025年（当前单木分割数据）" if result.get("dataset") == "grid_plot" else f"{result.get('year')}年"
        tonnes = summary["agb_sum_kg"] / 1000
        notes = "；".join(result.get("notes", []))
        return (
            f"## {scope}地上生物量统计\n\n"
            "| 指标 | 结果 |\n|---|---:|\n"
            f"| 总记录数 | {summary['total_records']:,} 条 |\n"
            f"| 有效AGB记录 | {summary['valid_agb_records']:,} 条 |\n"
            f"| 缺失AGB记录 | {summary['missing_agb_records']:,} 条 |\n"
            f"| **总地上生物量** | **{summary['agb_sum_kg']:,.2f} kg（约 {tonnes:,.2f} 吨）** |\n"
            f"| 平均单木AGB | {summary['agb_mean_kg']:,.2f} kg |\n"
            f"| 最大单木AGB | {summary['agb_max_kg']:,.2f} kg |\n\n"
            f"说明：{notes or '结果为所选数据范围内的估算值。'}"
        )

    summary_result = next((r for r in results if r.get("operation") == "summary"), None)
    if summary_result:
        summary = summary_result["summary"]
        top_match = re.search(r"前\s*(\d+)", query)
        top_n = min(int(top_match.group(1)), 10) if top_match else 10
        years = "、".join(
            f"{item['measurement_year']}年 {item['row_count']:,} 条"
            for item in summary.get("measurement_years", [])
        )
        rows = "\n".join(
            f"| {index} | {item['species']} | {item['tree_count']:,} |"
            for index, item in enumerate(summary.get("top_species", [])[:top_n], 1)
        )
        answer = (
            "## 数据库概览\n\n"
            f"- 树木总数：**{summary['tree_count']:,} 棵**\n"
            f"- 树种数量：**{summary['species_count']:,} 种**\n"
            f"- 样地数量：**{summary['plot_count']:,} 个**\n"
            f"- 测量记录：**{summary.get('measurement_count', 0):,} 条**"
        )
        if years:
            answer += f"（{years}）"
        if rows:
            answer += f"\n\n### 树木数量最多的前{min(top_n, len(summary.get('top_species', [])))}个树种\n\n| 排名 | 树种 | 树木数量 |\n|---:|---|---:|\n{rows}"
        detail = next((r for r in results if r.get("operation") == "tree_detail"), None)
        if detail:
            if not detail.get("found"):
                answer += "\n\n未找到请求中的树木编号。"
            else:
                value = detail["result"]
                tree = value["tree"]
                measurements = value["measurements"]
                lines = "\n".join(
                    f"| {m['measurement_year']} | {m.get('dbh_m') if m.get('dbh_m') is not None else '-'} | "
                    f"{m.get('tree_height_m') if m.get('tree_height_m') is not None else '-'} |"
                    for m in measurements
                )
                answer += (
                    f"\n\n### 单木 {tree['tree_id']}\n\n"
                    f"- 树种：{tree['species']}\n- 样地编号：{tree['plot_id']}\n\n"
                    "| 年份 | 胸径（m） | 树高（m） |\n|---:|---:|---:|\n" + lines
                )
        return answer

    raise ValueError("Fast route result cannot be composed")
