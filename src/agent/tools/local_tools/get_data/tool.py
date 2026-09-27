"""Structured Agent tool for reading project tables."""

from __future__ import annotations

import json
import math


GET_DATA_SCHEMA = {
    "type": "object",
    "properties": {
        "dataset": {
            "type": "string",
            "enum": ["traits", "monitoring", "grid_plot"],
        },
        "year": {"type": "integer", "enum": [2016, 2021]},
        "species_cn": {"type": "string", "minLength": 1, "maxLength": 100},
        "tree_id": {"type": "string", "minLength": 1, "maxLength": 100},
        "statistic": {
            "type": "string",
            "enum": ["species_count", "summary", "missing", "records"],
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
    },
    "required": ["dataset", "statistic"],
    "additionalProperties": False,
}


def load_dataset(arguments: dict, require_year: bool = False):
    from . import loader

    loaders = {
        "traits": loader.load_traits,
        "monitoring": loader.load_monitoring_data,
        "grid_plot": loader.load_grid_plot_data,
    }
    dataset = arguments["dataset"]
    year = arguments.get("year")
    if dataset not in loaders:
        raise ValueError("不支持该数据集")
    if year is not None and (dataset != "monitoring" or year not in {2016, 2021}):
        raise ValueError("只有监测数据支持2016/2021年份选择")
    if dataset == "monitoring" and require_year and year is None:
        raise ValueError("请明确监测数据年份：2016或2021")
    frame = loaders[dataset]().copy()
    if year is not None:
        column = f"dbh_{year}_cm"
        if column not in frame:
            raise ValueError("数据集缺少所选年份的胸径")
        frame["dbh_cm"] = frame[column]
    for field in ("species_cn", "tree_id"):
        if field in arguments:
            if field not in frame:
                raise ValueError(f"数据集缺少筛选字段：{field}")
            frame = frame.loc[frame[field].astype(str) == arguments[field]].copy()
    if frame.empty:
        raise ValueError("所选条件没有匹配记录")
    return frame


def _records(frame):
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def _finite(value):
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def get_data(arguments: dict) -> dict:
    from ..basic_stats import dbh_height_summary, missing_summary, species_count

    statistic = arguments["statistic"]
    frame = load_dataset(arguments, require_year=statistic == "summary")
    result = {
        "dataset": arguments["dataset"],
        "year": arguments.get("year"),
        "record_count": len(frame),
        "artifacts": [],
    }
    if statistic == "species_count":
        counts = species_count(frame)
        result.update(
            species_count=len(counts),
            species=_records(counts.head(arguments.get("limit", 20))),
        )
    elif statistic == "summary":
        result["summary"] = _finite(dbh_height_summary(frame))
    elif statistic == "missing":
        result["missing"] = missing_summary(frame)
    elif statistic == "records":
        result["records"] = _records(frame.head(arguments.get("limit", 20)))
    else:
        raise ValueError("不支持该统计类型")
    return result
