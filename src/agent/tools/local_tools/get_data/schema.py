from dataclasses import dataclass
from typing import Optional


# 原始列名 -> 内部标准列名
RENAME_MAP = {
    "tag": "tree_id",
    "subqudrat": "subplot_id",
    "species": "species_cn",
    "latin": "species_latin",
    "Life_form": "life_form",
    "DBH": "dbh_cm",
    "Status": "status",
    "H": "height_m",
    "TB": "stem_part",
    "WD": "wood_density_g_cm3",
    "WDMC": "wood_dry_matter_content",
    "WWC": "wood_water_content",

    "WD_T": "wood_density_trunk_g_cm3",
    "WDMC_T": "wood_dry_matter_content_trunk",
    "WWC_T": "wood_water_content_trunk",
    "WD_B": "wood_density_branch_g_cm3",
    "WDMC_B": "wood_dry_matter_content_branch",
    "WWC_B": "wood_water_content_branch",

    "LA": "leaf_area_cm2",
    "SLA": "specific_leaf_area_cm2_g",
    "LDMC": "leaf_dry_matter_content",
    "LT": "leaf_thickness",
    "LFM": "leaf_fresh_mass",
    "LDM": "leaf_dry_mass",
    "LWC": "leaf_water_content",

    "GX": "global_x",
    "GY": "global_y",
    "x20": "grid_x_20m",
    "y20": "grid_y_20m",
}


# 读取后希望至少存在的核心字段
REQUIRED_COLUMNS = [
    "tree_id",
    "species_cn",
    "species_latin",
    "life_form",
    "dbh_cm",
    "status",
    "height_m",
]


# 数值字段
NUMERIC_COLUMNS = [
    "dbh_cm",
    "height_m",
    "wood_density_g_cm3",
    "wood_dry_matter_content",
    "wood_water_content",

    "wood_density_trunk_g_cm3",
    "wood_dry_matter_content_trunk",
    "wood_water_content_trunk",
    "wood_density_branch_g_cm3",
    "wood_dry_matter_content_branch",
    "wood_water_content_branch",

    "leaf_area_cm2",
    "specific_leaf_area_cm2_g",
    "leaf_dry_matter_content",
    "leaf_thickness",
    "leaf_fresh_mass",
    "leaf_dry_mass",
    "leaf_water_content",

    "global_x",
    "global_y",
    "grid_x_20m",
    "grid_y_20m",
]


# 类别字段
CATEGORICAL_COLUMNS = [
    "tree_id",
    "subplot_id",
    "species_cn",
    "species_latin",
    "life_form",
    "status",
    "stem_part",
]


# 字段元数据：含义 + 单位 + 备注
FIELD_META = {
    "tree_id": {
        "raw_name": "tag",
        "label_cn": "单木编号",
        "label_en": "Tree ID",
        "unit": None,
        "description": "单木唯一标识，后续应优先作为主键候选字段",
    },
    "subplot_id": {
        "raw_name": "subqudrat",
        "label_cn": "子样方编号",
        "label_en": "Subquadrat ID",
        "unit": None,
        "description": "子样方/网格编号，拼写来自原始表，后续数据库字段建议统一",
    },
    "species_cn": {
        "raw_name": "species",
        "label_cn": "中文种名",
        "label_en": "Species (Chinese)",
        "unit": None,
        "description": "树种中文名",
    },
    "species_latin": {
        "raw_name": "latin",
        "label_cn": "拉丁学名",
        "label_en": "Species (Latin)",
        "unit": None,
        "description": "树种拉丁学名",
    },
    "life_form": {
        "raw_name": "Life_form",
        "label_cn": "生活型",
        "label_en": "Life form",
        "unit": None,
        "description": "Arbor, shrub or liana；原 notes 中有 sh_st、li_sh 等缩写说明",
    },
    "dbh_cm": {
        "raw_name": "DBH",
        "label_cn": "胸径",
        "label_en": "Diameter at breast height",
        "unit": "cm",
        "description": "胸高直径，碳汇/生物量计算核心输入字段",
    },
    "status": {
        "raw_name": "Status",
        "label_cn": "存活状态",
        "label_en": "Status",
        "unit": None,
        "description": "Alive or dead",
    },
    "height_m": {
        "raw_name": "H",
        "label_cn": "树高",
        "label_en": "Height",
        "unit": "m",
        "description": "树高，碳汇/生物量计算核心输入字段",
    },
    "stem_part": {
        "raw_name": "TB",
        "label_cn": "茎部类型",
        "label_en": "Trunk/Branch flag",
        "unit": None,
        "description": "T for trunk, B for branch",
    },
    "wood_density_g_cm3": {
        "raw_name": "WD",
        "label_cn": "木材密度",
        "label_en": "Wood density",
        "unit": "g/cm3",
        "description": "木材密度，碳汇/生物量计算核心输入字段",
    },
    "wood_dry_matter_content": {
        "raw_name": "WDMC",
        "label_cn": "木材干物质含量",
        "label_en": "Wood dry matter content",
        "unit": "g/g",
        "description": "原 notes 指出 trunk/branch 可能存在不同含义",
    },
    "wood_water_content": {
        "raw_name": "WWC",
        "label_cn": "木材含水量",
        "label_en": "Wood water content",
        "unit": "g/g",
        "description": "木材含水量",
    },
    "leaf_area_cm2": {
        "raw_name": "LA",
        "label_cn": "叶面积",
        "label_en": "Leaf area",
        "unit": "cm2",
        "description": "单叶面积",
    },
    "specific_leaf_area_cm2_g": {
        "raw_name": "SLA",
        "label_cn": "比叶面积",
        "label_en": "Specific leaf area",
        "unit": "cm2/g",
        "description": "leaf area / leaf dry mass",
    },
    "leaf_dry_matter_content": {
        "raw_name": "LDMC",
        "label_cn": "叶干物质含量",
        "label_en": "Leaf dry matter content",
        "unit": "g/g",
        "description": "leaf dry mass / leaf fresh mass",
    },
    "global_x": {
        "raw_name": "GX",
        "label_cn": "全局X坐标",
        "label_en": "Global X",
        "unit": None,
        "description": "样地全局坐标X",
    },
    "global_y": {
        "raw_name": "GY",
        "label_cn": "全局Y坐标",
        "label_en": "Global Y",
        "unit": None,
        "description": "样地全局坐标Y",
    },
    "grid_x_20m": {
        "raw_name": "x20",
        "label_cn": "20米网格内X坐标",
        "label_en": "X within 20m grid",
        "unit": None,
        "description": "20m 网格局部坐标X",
    },
    "grid_y_20m": {
        "raw_name": "y20",
        "label_cn": "20米网格内Y坐标",
        "label_en": "Y within 20m grid",
        "unit": None,
        "description": "20m 网格局部坐标Y",
    },
}


@dataclass
class TraitsRecord:
    tree_id: str
    subplot_id: Optional[str] = None
    species_cn: Optional[str] = None
    species_latin: Optional[str] = None
    life_form: Optional[str] = None
    dbh_cm: Optional[float] = None
    status: Optional[str] = None
    height_m: Optional[float] = None
    stem_part: Optional[str] = None
    wood_density_g_cm3: Optional[float] = None
    wood_dry_matter_content: Optional[float] = None
    wood_water_content: Optional[float] = None
    leaf_area_cm2: Optional[float] = None
    specific_leaf_area_cm2_g: Optional[float] = None
    leaf_dry_matter_content: Optional[float] = None
    global_x: Optional[float] = None
    global_y: Optional[float] = None
    grid_x_20m: Optional[float] = None
    grid_y_20m: Optional[float] = None