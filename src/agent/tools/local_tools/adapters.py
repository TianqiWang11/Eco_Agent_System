"""New structured tool boundary. No natural-language routing or agent state."""
import json
import re
from dataclasses import asdict
from .get_data.tool import load_dataset


def _finite(value):
    import math
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if math.isfinite(float(value)) else None
    return value


def records(frame):
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def metadata(arguments, frame):
    notes = ["结果范围仅为所选数据集与筛选条件，不代表整个保护区。"]
    for column, name in (("height_imputed", "树高"), ("wd_imputed", "木材密度")):
        if column in frame and frame[column].fillna(False).any():
            notes.append(f"部分{name}来自参考数据补齐，结果属于估算。")
    return {"dataset": arguments["dataset"], "year": arguments.get("year"),
            "record_count": len(frame), "notes": notes, "artifacts": []}


def _grid_means(frame, column):
    import pandas as pd
    if "grid_id" not in frame:
        raise ValueError("数据集缺少网格编号，无法生成该网格图")
    work = frame.copy()
    work[column] = pd.to_numeric(work[column], errors="coerce")
    fields = [column] + [c for c in ("global_x", "global_y") if c in work and c != column]
    return work.groupby("grid_id", dropna=False)[fields].mean().reset_index()


def analyze(arguments):
    from . import agb_tools, plot_tools, structural_complexity
    metric, operation = arguments["metric"], arguments["operation"]
    frame = load_dataset(arguments, require_year=True)
    result = metadata(arguments, frame)
    artifact = None
    year_label = str(arguments["year"]) if "year" in arguments else None
    if metric == "agb":
        calculated = agb_tools.add_agb_column(frame)
        result.update(metric="agb", unit="kg", summary=agb_tools.agb_summary(calculated))
        if operation == "summary":
            pass
        elif operation == "by_species":
            result["species"] = records(agb_tools.agb_by_species(calculated, arguments.get("top_n", 10)))
        elif operation == "histogram":
            artifact = plot_tools.render_agb_histogram(calculated, year_label=year_label)
        elif operation == "spatial_map":
            artifact = plot_tools.render_agb_spatial_distribution(calculated, year_label=year_label)
        elif operation == "grid_map":
            artifact = plot_tools.render_agb_grid_distribution(agb_tools.agb_by_grid(calculated), year_label=year_label)
        else:
            raise ValueError("不支持该生物量操作")
    elif metric in {"height", "dbh"}:
        column, label, unit = ("height_m", "树高", "m") if metric == "height" else ("dbh_cm", "胸径", "cm")
        if column not in frame:
            raise ValueError(f"数据集缺少{label}字段")
        values = frame[column].dropna()
        if values.empty:
            raise ValueError(f"没有有效{label}数值")
        result.update(metric=metric, unit=unit, mean=float(values.mean()), valid_records=len(values))
        if operation == "histogram":
            artifact = plot_tools.render_grid_attribute_histogram(frame, value_col=column, display_name=label, unit_label=unit, year_label=year_label)
        elif operation == "grid_map":
            artifact = plot_tools.render_grid_attribute_distribution(_grid_means(frame, column), value_col=column, display_name=label, unit_label=unit, year_label=year_label)
        elif operation != "summary":
            raise ValueError("树高/胸径支持summary、histogram或grid_map")
    elif metric == "structural_complexity":
        if operation == "summary":
            summary = structural_complexity.compute_structural_complexity(frame)
            result.update(metric=metric, score=summary.score, components=_finite(summary.components))
        elif operation == "grid_map":
            component = arguments.get("component", "score")
            grids = structural_complexity.aggregate_structural_complexity_20m_grid(frame)
            artifact = plot_tools.render_structural_complexity_grid_map(grids, component, year_label=year_label)
            result.update(metric=metric, component=component, grid_count=len(grids))
        else:
            raise ValueError("结构复杂度支持summary或grid_map")
    else:
        raise ValueError("不支持该指标")
    if artifact:
        result["artifacts"] = [asdict(artifact)]
    if operation == "grid_map" and metric != "structural_complexity":
        result["notes"].append("原网格绘图函数可能使用IDW补值；插值区域不是实测值或预测模型结果。")
    return result


def retrieve(arguments):
    from .knowledge_tools import retrieve_knowledge
    return retrieve_knowledge(arguments["query"], top_k=arguments.get("top_k", 2))


def scene_action(arguments):
    action = arguments["action"]
    if action not in {"highlight", "focus", "clear_highlight", "reset_scene"}:
        raise ValueError("不支持该场景操作")
    target = arguments.get("target_id")
    if action in {"highlight", "focus"} and (not target or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", target)):
        raise ValueError("高亮或聚焦需要明确的对象编号，保留编号的前导零")
    command = {"type": action}
    if action in {"highlight", "focus"}:
        command["target_id"] = target
    if action == "highlight":
        command["focus"] = arguments.get("focus", False)
    return {"answer": "已生成UE控制请求；是否执行成功需等待UE回执。", "ue_actions": [command], "artifacts": []}
