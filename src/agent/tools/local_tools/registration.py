from src.agent.contracts import ToolSpec
from .get_data import GET_DATA_SCHEMA, get_data


def object_schema(properties, required):
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


ANALYSIS_FIELDS = {
    "dataset": {"type": "string", "enum": ["traits", "monitoring", "grid_plot"],
                "description": "traits=功能性状表，monitoring=20公顷监测表，grid_plot=网格样地单木表"},
    "year": {"type": "integer", "enum": [2016, 2021], "description": "仅monitoring支持；须用户明确年份，不得擅自混用年份"},
    "species_cn": {"type": "string", "minLength": 1, "maxLength": 100},
    "tree_id": {"type": "string", "minLength": 1, "maxLength": 100},
}
ANALYSIS_SCHEMA = object_schema({**ANALYSIS_FIELDS,
    "metric": {"type": "string", "enum": ["agb", "height", "dbh", "structural_complexity"]},
    "operation": {"type": "string", "enum": ["summary", "by_species", "histogram", "spatial_map", "grid_map"]},
    "top_n": {"type": "integer", "minimum": 1, "maximum": 100},
    "component": {"type": "string", "enum": ["score", "height_cv", "dbh_cv", "species_shannon_norm", "vertical_entropy_norm"]}},
    ["dataset", "metric", "operation"])
SCENE_SCHEMA = object_schema({
    "action": {"type": "string", "enum": ["highlight", "focus", "clear_highlight", "reset_scene"]},
    "target_id": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"},
    "focus": {"type": "boolean"}}, ["action"])
KNOWLEDGE_SCHEMA = object_schema({"query": {"type": "string", "minLength": 1, "maxLength": 4000},
                                  "top_k": {"type": "integer", "minimum": 1, "maximum": 5}}, ["query"])
DATABASE_SCHEMA = object_schema({
    "operation": {"type": "string", "enum": ["describe_schema", "summary", "search_trees", "tree_detail"]},
    "table": {"type": "string", "enum": ["trees", "tree_measurements", "forest_inventory", "tree_segmentation"]},
    "tree_id": {"type": "string", "minLength": 1, "maxLength": 64},
    "species": {"type": "string", "minLength": 1, "maxLength": 100},
    "plot_id": {"type": "string", "minLength": 1, "maxLength": 64},
    "year": {"type": "integer", "enum": [2016, 2021, 2025]},
    "limit": {"type": "integer", "minimum": 1, "maximum": 25},
}, ["operation"])


def register_local(registry):
    # Business libraries are loaded on demand; no Excel/embedding work at registration.
    def handler(kind, arguments, context):
        from . import adapters
        try:
            if kind == "get_data":
                return get_data(arguments)
            return getattr(adapters, kind)(arguments)
        except (ValueError, KeyError) as exc:
            return {"isError": True, "error": str(exc), "artifacts": []}
        except FileNotFoundError:
            return {"isError": True, "error": "所需本地数据或索引文件不可用。", "artifacts": []}

    registry.register(ToolSpec(
        "get_data",
        "读取根目录data中的本地生态表格，支持物种数、统计摘要、缺失值和记录查询。",
        GET_DATA_SCHEMA,
        lambda arguments, context: handler("get_data", arguments, context),
        approval=False,
        replay_safe=True,
    ))

    for name, kind, schema, description in [
        ("analysis", "analyze", ANALYSIS_SCHEMA, "调用本地Python统计/绘图。AGB支持汇总、物种贡献、直方图、空间图和网格图；树高/胸径支持汇总、直方图、网格图；结构复杂度支持汇总、20m网格图。仅分析，不提供未实现的预测。监测数据计算须明确年份。"),
        ("knowledge", "retrieve", KNOWLEDGE_SCHEMA, "按查询文本检索知识资料；只返回证据，不在工具内部调用语言模型。"),
        ("ue_scene", "scene_action", SCENE_SCHEMA, "生成经审批的UE控制请求。highlight/focus必须有明确对象编号，返回指令不代表UE已执行。"),
    ]:
        registry.register(ToolSpec(name, description, schema,
            lambda a, c, kind=kind: handler(kind, a, c),
            approval=kind == "scene_action", replay_safe=kind != "scene_action"))

    from .database_tools import query_database
    registry.register(ToolSpec(
        "database",
        "只读查询当前车八岭PostgreSQL生态数据库。字段含义、单位、数据粒度或关联不确定时先用describe_schema，可用table只取一张表；summary返回已匹配数据概况；search_trees按编号、树种、样地或年份筛选；tree_detail返回指定tree_id的固定属性及年度测量。不得把原始表内部编号当作UE编号，不得虚构关联或结果。",
        DATABASE_SCHEMA,
        lambda arguments, context: query_database(arguments),
        approval=False,
        replay_safe=True,
    ))

    from .predict import PREDICT_SCHEMA, predict
    registry.register(ToolSpec(
        "predict",
        "使用已训练的统一树种胸径生长模型。status检查模型；predict_tree预测指定单木；用户指定树种和预测年份时使用predict_species_trees预测数据库中该树种所有可预测的真实单木，不限制棵数，target_year必填且不能默认2030年；predict_species只用于给定dbh_m的虚拟树种场景，不能控制真实UE单木；predict_sample随机抽样预测。真实单木预测返回Excel及待发送UE的编号和形态参数，UE是否执行以回执为准。模型以species为分类特征，不使用plot_id，结果属于实验性外推。",
        PREDICT_SCHEMA,
        lambda arguments, context: predict(arguments),
        approval=False,
        replay_safe=True,
    ))
