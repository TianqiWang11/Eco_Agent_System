"""Single source of truth for ecology-table semantics."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from psycopg import errors, sql


def _fields(values: dict[str, tuple[str, str | None]]) -> dict[str, dict[str, str]]:
    return {
        name: {**{"description": description}, **({"unit": unit} if unit else {})}
        for name, (description, unit) in values.items()
    }


TABLE_CATALOG: dict[str, dict[str, Any]] = {
    "trees": {
        "description": "已完成跨来源匹配、可与UE场景编号对应的单木主表。",
        "grain": "每个 tree_id 一行。",
        "use_for": ["平台展示", "单木查询", "UE定位", "预测对象选择"],
        "limitations": ["只包含已成功匹配的单木，不代表全部原始调查记录。"],
        "relationships": ["tree_measurements.tree_id 对应本表 tree_id。"],
        "fields": _fields({
            "tree_id": ("已匹配单木的唯一编号，也是UE控制目标编号。", None),
            "species": ("树种中文名称。", None),
            "plot_id": ("与单木分割数据一致的样地/网格编号。", None),
            "tree_position_x_m": ("场景/样地坐标系东向X坐标。", "m"),
            "tree_position_y_m": ("场景/样地坐标系北向Y坐标。", "m"),
            "tree_position_z_m": ("场景/样地坐标系Z坐标。", "m"),
            "elevation_m": ("树木所在位置海拔。", "m"),
        }),
    },
    "tree_measurements": {
        "description": "已匹配单木的2016、2021和2025年度测量事实表。",
        "grain": "每个 tree_id、measurement_year 一行。",
        "use_for": ["单木历年查询", "生长变化分析", "模型训练和预测基线"],
        "limitations": ["2016、2021年主要有胸径；树高和冠幅主要来自2025年分割。"],
        "relationships": ["tree_id 对应 trees.tree_id。"],
        "fields": _fields({
            "tree_id": ("对应 trees.tree_id 的单木编号。", None),
            "measurement_year": ("观测所属年份。", "year"),
            "dbh_m": ("距地面约1.3米处的胸径。", "m"),
            "tree_height_m": ("树高。", "m"),
            "crown_diameter_m": ("综合冠径。", "m"),
            "crown_diameter_ns_m": ("南北方向冠径。", "m"),
            "crown_diameter_ew_m": ("东西方向冠径。", "m"),
            "crown_area_m2": ("冠幅投影面积。", "m2"),
            "crown_volume_m3": ("估算树冠体积。", "m3"),
            "crown_base_height_m": ("冠基高/枝下高。", "m"),
            "data_source": ("数据来源，如 field_inventory 或 ue_segmentation。", None),
        }),
    },
    "forest_inventory": {
        "description": "20公顷样地2016、2021年完整调查记录，保留不同枝干。",
        "grain": "每条原始枝干调查记录一行；同一 tree_id 可以出现多行。",
        "use_for": ["历史胸径统计", "生长和树种分析", "历史生物量输入"],
        "limitations": [
            "不是UE对象表，不能把 tree_id 直接当作UE编号。",
            "单木分析须按 stem_part 聚合；当前工具以平方和开方合成等效胸径。",
            "空值表示没有可用观测，不能按0处理。",
        ],
        "relationships": ["与完整分割表无可靠一对一主键；可靠匹配子集位于核心两表。"],
        "fields": _fields({
            "source_row": ("导入时生成的追溯行号，不是树号。", None),
            "source_sequence_id": ("原调查表序号。", None),
            "survey_year_2016": ("第一期调查时间。", "year"),
            "survey_year_2021": ("第二期调查时间。", "year"),
            "qudrat_id": ("原数据样方编号；字段名沿用源表拼写。", None),
            "subplot_id": ("子样方编号。", None),
            "tree_id": ("原调查树木tag；同一树的枝干可共享该值。", None),
            "species_cn_raw": ("原始中文树种名。", None),
            "tree_species_label": ("原表树种/单木辅助标签。", None),
            "model_tree_label": ("原表建模每木标记。", None),
            "species_latin_raw": ("原始拉丁学名文本。", None),
            "species_code": ("样地物种代号。", None),
            "family_cn": ("中文科名。", None),
            "genus_cn": ("中文属名。", None),
            "stem_part": ("枝干编号，如branch0，用于区分主干和分枝。", None),
            "global_x": ("调查坐标系X坐标。", "m"),
            "global_y": ("调查坐标系Y坐标。", "m"),
            "dbh_2016_cm": ("2016年胸径观测。", "cm"),
            "dbh_2021_cm": ("2021年胸径观测。", "cm"),
            "status_2016": ("2016年调查备注或状态。", None),
            "status": ("2021年调查备注或状态。", None),
            "species_cn": ("清洗/修订后的中文树种名，分析时优先。", None),
            "species_latin": ("清洗后的拉丁学名。", None),
        }),
    },
    "tree_segmentation": {
        "description": "2025年20公顷样地完整单木分割结果和几何属性。",
        "grain": "每个分割出的单木对象一行。",
        "use_for": ["2025年结构统计", "树高/胸径/冠幅分析", "空间与生物量计算"],
        "limitations": [
            "没有树种字段，不能直接做完整数据的分树种统计。",
            "tree_seq_id 是分割内部编号，不等于 trees.tree_id 或UE编号。",
            "几何字段是算法分割结果，不是地面实测值。",
        ],
        "relationships": ["可靠匹配子集位于核心两表；不得仅凭行号或内部编号关联。"],
        "fields": _fields({
            "source_row": ("导入时生成的追溯行号。", None),
            "grid_id": ("单木所在网格/样地编号。", None),
            "tree_seq_id": ("分割数据内部树序号。", None),
            "global_x": ("场景/样地坐标系X坐标。", "m"),
            "global_y": ("场景/样地坐标系Y坐标。", "m"),
            "tree_z_m": ("单木位置Z坐标。", "m"),
            "height_m": ("分割得到的树高。", "m"),
            "dbh_m": ("分割数据胸径。", "m"),
            "crown_diameter_m": ("综合冠径。", "m"),
            "crown_ns_m": ("南北冠径。", "m"),
            "crown_ew_m": ("东西冠径。", "m"),
            "crown_area_m2": ("冠幅投影面积。", "m2"),
            "crown_volume_m3": ("估算树冠体积。", "m3"),
            "clear_bole_height_m": ("枝下高/无枝干高。", "m"),
            "elevation_m": ("单木所在位置海拔。", "m"),
            "dbh_cm": ("由 dbh_m 换算的胸径便利字段。", "cm"),
            "grid_x_20m": ("由 global_x 计算的20米网格X索引。", None),
            "grid_y_20m": ("由 global_y 计算的20米网格Y索引。", None),
        }),
    },
}

def describe_catalog(table: str | None = None) -> dict[str, Any]:
    """Return the whole catalog or one table for Agent context."""
    if table is not None and table not in TABLE_CATALOG:
        raise ValueError(f"未知数据表：{table}")
    selected = {table: TABLE_CATALOG[table]} if table else TABLE_CATALOG
    return {
        "catalog_version": 1,
        "join_rule": "只有 trees 与 tree_measurements 可按 tree_id 直接关联；两张完整原始表不可自行假定一对一对应。",
        "tables": deepcopy(selected),
    }


def sync_postgres_comments(connection) -> int:
    """Write catalog descriptions to existing PostgreSQL tables and columns."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name,column_name FROM information_schema.columns "
            "WHERE table_schema='public'"
        )
        existing: dict[str, set[str]] = {}
        for table_name, column_name in cursor.fetchall():
            existing.setdefault(table_name, set()).add(column_name)

        applied = 0
        for table_name, table in TABLE_CATALOG.items():
            if table_name not in existing:
                continue
            comment = f"{table['description']} 数据粒度：{table['grain']}"
            try:
                with connection.transaction():
                    cursor.execute(sql.SQL("COMMENT ON TABLE {}.{} IS {}").format(
                        sql.Identifier("public"), sql.Identifier(table_name), sql.Literal(comment)))
            except errors.InsufficientPrivilege:
                # COMMENT requires table ownership. The Agent catalog remains
                # usable even when a deployment role only has read access.
                continue
            applied += 1
            for column_name, field in table["fields"].items():
                if column_name not in existing[table_name]:
                    continue
                comment = field["description"]
                if field.get("unit"):
                    comment += f" 单位：{field['unit']}。"
                cursor.execute(sql.SQL("COMMENT ON COLUMN {}.{}.{} IS {}").format(
                    sql.Identifier("public"), sql.Identifier(table_name),
                    sql.Identifier(column_name), sql.Literal(comment)))
                applied += 1
    return applied
