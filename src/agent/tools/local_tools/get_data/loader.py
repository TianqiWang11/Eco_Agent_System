from pathlib import Path
from functools import lru_cache
import numpy as np
import pandas as pd

from src.project_paths import REFERENCE_DATA_DIR

from .schema import (
    RENAME_MAP,
    REQUIRED_COLUMNS,
    NUMERIC_COLUMNS,
    CATEGORICAL_COLUMNS,
)

RAW_DATA_DIR = REFERENCE_DATA_DIR
GRID_PLOT_SEARCH_DIR = RAW_DATA_DIR


NA_VALUES = ["NA", "N/A", "None", "none", "null", "NULL", ""]


def _normalize_col_name(name: str) -> str:
    """对列名做宽松标准化，便于兼容不同命名/单位写法。"""
    s = str(name).strip().lower()
    # 常见符号统一
    trans = str.maketrans({
        "（": "(",
        "）": ")",
        " ": "",
        "_": "",
        "-": "",
        "　": "",
    })
    s = s.translate(trans)
    # 常见单位写法统一
    s = s.replace("米", "m")
    s = s.replace("平方米", "sqm")
    s = s.replace("立方米", "cum")
    return s


_GRID_PLOT_COLUMN_ALIASES = {
    "grid_id": ["网格编号", "样地编号", "grid_id", "gridid"],
    "tree_seq_id": ["树编号", "tree_id", "treeseqid"],
    "global_x": ["树方位x(米)", "树方位x(m)", "global_x", "gx"],
    "global_y": ["树方位y(米)", "树方位y(m)", "global_y", "gy"],
    "tree_z_m": ["树方位z(米)", "树方位z(m)", "tree_z_m"],
    "height_m": ["树高(米)", "树高(m)", "height_m"],
    "dbh_m": ["胸径(米)", "胸径(m)", "dbh_m"],
    "crown_diameter_m": ["冠径(米)", "冠径(m)", "crown_diameter_m"],
    "crown_ns_m": ["南北冠径(米)", "南北冠径(m)", "crown_ns_m"],
    "crown_ew_m": ["东西冠径(米)", "东西冠径(m)", "crown_ew_m"],
    "crown_area_m2": ["冠幅面积(平方米)", "冠幅面积(sqM)", "crown_area_m2"],
    "crown_volume_m3": ["冠幅体积(立方米)", "冠幅体积(cuM)", "crown_volume_m3"],
    "clear_bole_height_m": ["枝下高(米)", "枝下高(m)", "clear_bole_height_m"],
    "elevation_m": ["海拔(米)", "海拔(m)", "elevation_m"],
    "species_cn": ["树种", "物种", "中文种名", "species_cn"],
    "species_latin": ["拉丁学名", "species_latin"],
}

_GRID_PLOT_ALIAS_LOOKUP = {
    _normalize_col_name(alias): std_col
    for std_col, aliases in _GRID_PLOT_COLUMN_ALIASES.items()
    for alias in aliases
}

_GRID_PLOT_CORE_FIELDS = {"grid_id", "global_x", "global_y", "dbh_m", "height_m"}

MONITORING_RENAME_MAP = {
    "序号": "source_sequence_id",
    "tag": "tree_id",
    "subqudrat": "subplot_id",
    "spname": "species_cn_raw",
    "Unnamed: 7": "tree_species_label",
    "建模每木": "model_tree_label",
    "修订名(FOC为主)": "species_cn",
    "拉丁学名（不带名字）": "species_latin",
    "拉丁学名": "species_latin_raw",
    "branch": "stem_part",
    "gx": "global_x",
    "gy": "global_y",
    "dbh(2016)": "dbh_2016_cm",
    "dbh1(2021)": "dbh_2021_cm",
    "remark2016": "status_2016",
    "remark2021": "status",
    "调查时间": "survey_year_2016",
    "调查时间.1": "survey_year_2021",
    "样地物种代号": "species_code",
    "科名": "family_cn",
    "中文属名": "genus_cn",
    "qudrat": "qudrat_id",
}

_TRAITS_ALIAS_LOOKUP = {
    _normalize_col_name(raw_name): std_name
    for raw_name, std_name in RENAME_MAP.items()
}
for _col in REQUIRED_COLUMNS:
    _TRAITS_ALIAS_LOOKUP[_normalize_col_name(_col)] = _col

_MONITORING_ALIAS_LOOKUP = {
    _normalize_col_name(raw_name): std_name
    for raw_name, std_name in MONITORING_RENAME_MAP.items()
}
_MONITORING_CORE_FIELDS = {"tree_id", "global_x", "global_y", "dbh_2016_cm", "dbh_2021_cm"}

_VEGETATION_COLUMN_ALIASES = {
    "grid_code": ["网格", "网格编号", "grid", "grid_code", "wangge"],
    "vegetation_group": ["植被型组", "植被类型", "植被型名称", "植被亚型名称", "群系名称"],
}

_VEGETATION_ALIAS_LOOKUP = {
    _normalize_col_name(alias): std_col
    for std_col, aliases in _VEGETATION_COLUMN_ALIASES.items()
    for alias in aliases
}
_VEGETATION_CORE_FIELDS = {"grid_code", "vegetation_group"}

_PLOT_QUDRAT_MAP_COLUMN_ALIASES = {
    "grid_id": ["采集编号", "样地编号", "grid_id", "gridid"],
    "qudrat_id": ["qudrat", "quadrat", "样方编号", "样地号", "qudrat_id", "quadrat_id"],
}

_PLOT_QUDRAT_MAP_ALIAS_LOOKUP = {
    _normalize_col_name(alias): std_col
    for std_col, aliases in _PLOT_QUDRAT_MAP_COLUMN_ALIASES.items()
    for alias in aliases
}
_PLOT_QUDRAT_MAP_CORE_FIELDS = {"grid_id", "qudrat_id"}

_GRID_SURVEY_COLUMN_ALIASES = {
    "grid_code": ["网格号", "网格编号", "网格", "grid_code", "grid", "wangge"],
    "dbh_2022_cm": ["DBH2022", "dbh2022", "dbh_2022", "dbh(2022)", "dbh2022(cm)"],
}

_GRID_SURVEY_ALIAS_LOOKUP = {
    _normalize_col_name(alias): std_col
    for std_col, aliases in _GRID_SURVEY_COLUMN_ALIASES.items()
    for alias in aliases
}
_GRID_SURVEY_CORE_FIELDS = {"grid_code", "dbh_2022_cm"}

_MODEL_TREE_BRIDGE_CORE_FIELDS = {"编号", "转换后"}


def _build_rename_map(columns, alias_lookup: dict[str, str]) -> dict:
    rename_map = {}
    for col in columns:
        std = alias_lookup.get(_normalize_col_name(col))
        if std:
            rename_map[col] = std
    return rename_map


def _standardized_columns(columns, alias_lookup: dict[str, str]) -> set[str]:
    return set(_build_rename_map(columns, alias_lookup).values())


@lru_cache(maxsize=1)
def _scan_raw_excel_catalog() -> list[dict]:
    """
    扫描 data/raw 下全部 xlsx，返回每个工作表的元信息（文件、sheet、表头）。
    """
    if not RAW_DATA_DIR.exists():
        raise FileNotFoundError(f"目录不存在：{RAW_DATA_DIR}")

    xlsx_files = [
        p for p in sorted(RAW_DATA_DIR.glob("*.xlsx"))
        if not p.name.startswith("~$")
    ]
    if not xlsx_files:
        raise FileNotFoundError(f"在 {RAW_DATA_DIR} 下未找到任何 xlsx 文件。")

    catalog = []
    for file_path in xlsx_files:
        try:
            xls = pd.ExcelFile(file_path)
        except Exception:
            continue
        for sheet_name in xls.sheet_names:
            try:
                header_df = pd.read_excel(file_path, sheet_name=sheet_name, nrows=0)
            except Exception:
                continue
            cols = list(header_df.columns)
            catalog.append(
                {
                    "file_path": file_path,
                    "sheet_name": sheet_name,
                    "columns": cols,
                    "sheet_norm": _normalize_col_name(str(sheet_name)),
                }
            )

    if not catalog:
        raise ValueError(f"在 {RAW_DATA_DIR} 下未能读取任何 Excel 工作表。")
    return catalog


@lru_cache(maxsize=1)
def _resolve_traits_source() -> tuple[Path, str]:
    """
    自动识别功能性状数据表：按 REQUIRED_COLUMNS 匹配度最高的工作表。
    """
    best = None
    for item in _scan_raw_excel_catalog():
        std_cols = _standardized_columns(item["columns"], _TRAITS_ALIAS_LOOKUP)
        score = len(set(REQUIRED_COLUMNS) & std_cols)
        if item["sheet_norm"] in {"functionaltraits", "traits"}:
            score += 2
        if best is None or score > best[0]:
            best = (score, item["file_path"], item["sheet_name"])

    if best is None or best[0] < 3:
        raise ValueError("未识别到功能性状数据工作表（字段匹配不足）。")
    return best[1], best[2]


@lru_cache(maxsize=1)
def _resolve_monitoring_source() -> tuple[Path, str]:
    """
    自动识别监测数据表：按监测核心字段匹配度最高的工作表。
    """
    best = None
    for item in _scan_raw_excel_catalog():
        std_cols = _standardized_columns(item["columns"], _MONITORING_ALIAS_LOOKUP)
        score = len(_MONITORING_CORE_FIELDS & std_cols)
        if "监测" in item["sheet_name"]:
            score += 1
        if best is None or score > best[0]:
            best = (score, item["file_path"], item["sheet_name"])

    if best is None or best[0] < 4:
        raise ValueError("未识别到监测数据工作表（字段匹配不足）。")
    return best[1], best[2]


@lru_cache(maxsize=1)
def _resolve_notes_source() -> tuple[Path, str]:
    """
    优先从功能性状所在工作簿读取 Notes；没有则全目录回退查找 Notes。
    """
    traits_file, _ = _resolve_traits_source()
    try:
        xls = pd.ExcelFile(traits_file)
        if "Notes" in xls.sheet_names:
            return traits_file, "Notes"
    except Exception:
        pass

    for item in _scan_raw_excel_catalog():
        if item["sheet_norm"] == "notes":
            return item["file_path"], item["sheet_name"]
    raise ValueError("未找到 Notes 工作表。")


@lru_cache(maxsize=1)
def _resolve_vegetation_source() -> tuple[Path, str]:
    """
    自动识别“植被类型分类”数据源（优先包含植被型组字段的工作表）。
    """
    best = None
    for item in _scan_raw_excel_catalog():
        rename_map = _build_rename_map(item["columns"], _VEGETATION_ALIAS_LOOKUP)
        std_cols = set(rename_map.values())
        score = len(_VEGETATION_CORE_FIELDS & std_cols)
        if "群系已命名" in item["sheet_name"]:
            score += 2
        if "植被" in item["sheet_name"]:
            score += 1
        if "植被类型分类" in str(item["file_path"]):
            score += 2
        if best is None or score > best[0]:
            best = (score, item["file_path"], item["sheet_name"])

    if best is None or best[0] < 2:
        raise ValueError("未识别到植被类型分类工作表（字段匹配不足）。")
    return best[1], best[2]


@lru_cache(maxsize=1)
def _resolve_plot_qudrat_mapping_source() -> tuple[Path, str]:
    """
    自动识别“采集编号(样地编号) <-> qudrat 编号”对应表来源。
    """
    best = None
    for item in _scan_raw_excel_catalog():
        rename_map = _build_rename_map(item["columns"], _PLOT_QUDRAT_MAP_ALIAS_LOOKUP)
        std_cols = set(rename_map.values())
        score = len(_PLOT_QUDRAT_MAP_CORE_FIELDS & std_cols)
        file_str = str(item["file_path"])
        if "采集编号对应表" in file_str:
            score += 3
        if "对应" in item["sheet_name"]:
            score += 1
        if best is None or score > best[0]:
            best = (score, item["file_path"], item["sheet_name"])

    if best is None or best[0] < 2:
        raise ValueError("未识别到采集编号对应表（字段匹配不足，需包含采集编号与qudrat字段）。")
    return best[1], best[2]


@lru_cache(maxsize=1)
def _resolve_grid_survey_source() -> tuple[Path, str]:
    """
    自动识别“网格调查数据（含 DBH2022）”来源。
    """
    best = None
    for item in _scan_raw_excel_catalog():
        rename_map = _build_rename_map(item["columns"], _GRID_SURVEY_ALIAS_LOOKUP)
        std_cols = set(rename_map.values())
        score = len(_GRID_SURVEY_CORE_FIELDS & std_cols)
        file_str = str(item["file_path"])
        if "网格调查数据" in file_str:
            score += 3
        if "2022" in item["sheet_name"]:
            score += 1
        if "网格化监测样地数据" in item["sheet_name"]:
            score += 1
        if best is None or score > best[0]:
            best = (score, item["file_path"], item["sheet_name"])

    if best is None or best[0] < 2:
        raise ValueError("未识别到网格调查数据工作表（字段匹配不足，需包含网格号与DBH2022）。")
    return best[1], best[2]


@lru_cache(maxsize=1)
def _resolve_model_tree_bridge_source() -> tuple[Path, str]:
    """
    自动识别“样地1800树调查数据-建模每木”来源。
    """
    best = None
    for item in _scan_raw_excel_catalog():
        cols_text = "".join(str(c) for c in item["columns"])
        score = 0
        if "样地1800树调查数据" in str(item["file_path"]):
            score += 3
        if "建模每木" in item["sheet_name"]:
            score += 4
        if "编号" in cols_text:
            score += 1
        if "转换后" in cols_text:
            score += 1
        if best is None or score > best[0]:
            best = (score, item["file_path"], item["sheet_name"])

    if best is None or best[0] < 6:
        raise ValueError("未识别到“样地1800树调查数据-建模每木”工作表。")
    return best[1], best[2]


def _build_grid_plot_rename_map(columns) -> dict:
    """按列名别名自动生成重命名映射（原列名 -> 标准列名）。"""
    return _build_rename_map(columns, _GRID_PLOT_ALIAS_LOOKUP)


@lru_cache(maxsize=1)
def _resolve_grid_plot_source() -> tuple[Path, str]:
    """
    自动解析“网格样地单木表”来源：
    - 扫描 data/raw 下所有 xlsx；
    - 逐个工作表按核心字段匹配打分；
    - 选择得分最高者。
    """
    best = None
    for item in _scan_raw_excel_catalog():
        rename_map = _build_grid_plot_rename_map(item["columns"])
        score = len(set(rename_map.values()) & _GRID_PLOT_CORE_FIELDS)
        # 明确优先“网格样地”数据源，避免被其他相似结构表误选
        if "网格样地" in str(item["file_path"]) or "网格样地" in item["sheet_name"]:
            score += 2
        if best is None or score > best[0]:
            best = (score, item["file_path"], item["sheet_name"])

    if best is None or best[0] < 4:
        scanned = sorted({str(item["file_path"]) for item in _scan_raw_excel_catalog()})
        raise ValueError(
            "未识别到网格样地单木数据工作表（核心字段匹配不足）。"
            f"已扫描文件：{scanned}"
        )

    return best[1], best[2]


@lru_cache(maxsize=1)
def _resolve_large_plot_seg_source() -> tuple[Path, str]:
    """
    自动识别“20公顷大样地单木分割属性合并”数据源。
    """
    best = None
    for item in _scan_raw_excel_catalog():
        rename_map = _build_grid_plot_rename_map(item["columns"])
        score = len(set(rename_map.values()) & _GRID_PLOT_CORE_FIELDS)
        file_str = str(item["file_path"])
        if "20公顷大样地单木分割属性合并" in file_str:
            score += 4
        if "合并数据" in item["sheet_name"]:
            score += 1
        if best is None or score > best[0]:
            best = (score, item["file_path"], item["sheet_name"])

    if best is None or best[0] < 4:
        raise ValueError("未识别到20公顷大样地单木分割属性合并工作表（字段匹配不足）。")
    return best[1], best[2]


def load_notes() -> pd.DataFrame:
    notes_file, notes_sheet = _resolve_notes_source()
    return pd.read_excel(notes_file, sheet_name=notes_sheet, keep_default_na=True)


def _clean_string_series(s: pd.Series) -> pd.Series:
    # 保留缺失值，不要转成字符串 "nan"
    s = s.astype("string")
    s = s.str.replace("\xa0", " ", regex=False).str.strip()
    s = s.replace(NA_VALUES, pd.NA)
    return s


def _first_non_null(s: pd.Series):
    s2 = s.dropna()
    return s2.iloc[0] if len(s2) > 0 else pd.NA


def _normalize_qudrat_id_series(s: pd.Series) -> pd.Series:
    """
    统一 qudrat 编号表示：
    - 先做字符串清洗；
    - 对可解析为数字的编号，统一转为 4 位零填充字符串（如 101 -> 0101）。
    """
    out = _clean_string_series(s)
    num = pd.to_numeric(out, errors="coerce")
    mask = num.notna()
    if mask.any():
        # 监测与对应表中 qudrat 可能出现 101 / 0101 的混用，这里统一为 4 位编号。
        out.loc[mask] = num.loc[mask].round().astype("Int64").astype("string").str.zfill(4)
    return out


def _dbh_equivalent_from_stems(s: pd.Series) -> float:
    """
    同一树（同一 tag）多枝条时，按等效胸径合并：
    DBH_eq = sqrt(sum(DBH_i^2))
    """
    v = pd.to_numeric(s, errors="coerce").dropna()
    v = v[v > 0]
    if len(v) == 0:
        return float("nan")
    return float((v.pow(2).sum()) ** 0.5)


def _aggregate_monitoring_tree_level(df: pd.DataFrame) -> pd.DataFrame:
    """
    将监测表按 tree_id 聚合到“单木级”。
    解决同一 tag 多枝条/多记录的问题，DBH 用等效胸径合并。
    """
    work = df.copy()
    work = work[work["tree_id"].notna()].copy()

    grouped = work.groupby("tree_id", dropna=True)

    # 这些字段按树取首个非空值
    first_cols = [
        "qudrat_id",
        "subplot_id",
        "species_cn",
        "species_cn_raw",
        "species_latin",
        "species_latin_raw",
        "species_code",
        "family_cn",
        "genus_cn",
        "status_2016",
        "status",
        "survey_year_2016",
        "survey_year_2021",
    ]
    first_df = grouped[first_cols].first()

    # 坐标取中位数
    coord_df = grouped[["global_x", "global_y"]].median()

    # DBH 等效合并（按树将枝条 DBH 合成为 DBH_eq）
    d16 = pd.to_numeric(work["dbh_2016_cm"], errors="coerce")
    d21 = pd.to_numeric(work["dbh_2021_cm"], errors="coerce")
    d16 = d16.where(d16 > 0)
    d21 = d21.where(d21 > 0)
    # 关键：min_count=1，避免“全为空”的树被 sum() 变成 0，导致空值被误抹平
    dbh16_eq = ((d16.pow(2)).groupby(work["tree_id"]).sum(min_count=1)).pow(0.5).rename("dbh_2016_cm")
    dbh21_eq = ((d21.pow(2)).groupby(work["tree_id"]).sum(min_count=1)).pow(0.5).rename("dbh_2021_cm")

    n_df = grouped.size().rename("n_stem_records")

    agg = pd.concat([first_df, coord_df, dbh16_eq, dbh21_eq, n_df], axis=1).reset_index()
    return agg


@lru_cache(maxsize=1)
def load_traits() -> pd.DataFrame:
    traits_file, traits_sheet = _resolve_traits_source()
    df = pd.read_excel(
        traits_file,
        sheet_name=traits_sheet,
        keep_default_na=True,
        na_values=NA_VALUES,
    )

    # 1. 统一字段名
    df = df.rename(columns=_build_rename_map(df.columns, _TRAITS_ALIAS_LOOKUP))

    # 2. 字符串字段清洗
    for col in CATEGORICAL_COLUMNS:
        if col in df.columns:
            df[col] = _clean_string_series(df[col])

    # 3. 数值字段转 numeric
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 4. 检查必要字段是否存在
    missing_required = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_required:
        raise ValueError(f"缺少必要字段: {missing_required}")

    return df


@lru_cache(maxsize=1)
def _build_traits_species_reference() -> pd.DataFrame:
    """
    从旧表构建按物种聚合的参考信息，用于给监测数据补齐字段（高度/木材密度/生活型）。
    规则：数值字段使用物种平均值（mean）。
    """
    df = load_traits().copy()

    refs = []
    # 1) 按中文名聚合
    if "species_cn" in df.columns:
        g = (
            df.groupby("species_cn", dropna=True)
            .agg(
                ref_height_m=("height_m", "mean"),
                ref_wd=("wood_density_g_cm3", "mean"),
                ref_life_form=("life_form", lambda s: s.dropna().iloc[0] if len(s.dropna()) else pd.NA),
            )
            .reset_index()
        )
        g["key_type"] = "species_cn"
        g["species_key"] = g["species_cn"].astype(str)
        refs.append(g[["key_type", "species_key", "ref_height_m", "ref_wd", "ref_life_form"]])

    # 2) 按拉丁名聚合
    if "species_latin" in df.columns:
        g = (
            df.groupby("species_latin", dropna=True)
            .agg(
                ref_height_m=("height_m", "mean"),
                ref_wd=("wood_density_g_cm3", "mean"),
                ref_life_form=("life_form", lambda s: s.dropna().iloc[0] if len(s.dropna()) else pd.NA),
            )
            .reset_index()
        )
        g["key_type"] = "species_latin"
        g["species_key"] = g["species_latin"].astype(str)
        refs.append(g[["key_type", "species_key", "ref_height_m", "ref_wd", "ref_life_form"]])

    if not refs:
        return pd.DataFrame(columns=["key_type", "species_key", "ref_height_m", "ref_wd", "ref_life_form"])

    return pd.concat(refs, ignore_index=True)


def _merge_species_reference(monitor_df: pd.DataFrame) -> pd.DataFrame:
    ref = _build_traits_species_reference()
    if len(ref) == 0:
        return monitor_df

    work = monitor_df.copy()

    # 优先用拉丁学名匹配，其次中文种名（修订名，再回退原始中文名）
    latin_ref = ref[ref["key_type"] == "species_latin"][["species_key", "ref_height_m", "ref_wd", "ref_life_form"]].copy()
    latin_ref = latin_ref.rename(columns={"species_key": "__latin_key"})
    cn_ref = ref[ref["key_type"] == "species_cn"][["species_key", "ref_height_m", "ref_wd", "ref_life_form"]].copy()
    cn_ref = cn_ref.rename(columns={"species_key": "__cn_key"})
    cn_raw_ref = ref[ref["key_type"] == "species_cn"][["species_key", "ref_height_m", "ref_wd", "ref_life_form"]].copy()
    cn_raw_ref = cn_raw_ref.rename(columns={"species_key": "__cn_raw_key"})

    work = work.merge(latin_ref, how="left", left_on="species_latin", right_on="__latin_key")
    work = work.merge(
        cn_ref,
        how="left",
        left_on="species_cn",
        right_on="__cn_key",
        suffixes=("_latin", "_cn"),
    )
    work = work.merge(
        cn_raw_ref,
        how="left",
        left_on="species_cn_raw",
        right_on="__cn_raw_key",
        suffixes=("", "_cn_raw"),
    )

    # 合并两路参考（拉丁优先）
    work["height_m"] = (
        work["ref_height_m_latin"]
        .combine_first(work["ref_height_m_cn"])
        .combine_first(work.get("ref_height_m", pd.Series(index=work.index, dtype="float64")))
    )
    work["wood_density_g_cm3"] = (
        work["ref_wd_latin"]
        .combine_first(work["ref_wd_cn"])
        .combine_first(work.get("ref_wd", pd.Series(index=work.index, dtype="float64")))
    )
    work["life_form"] = (
        work["ref_life_form_latin"]
        .combine_first(work["ref_life_form_cn"])
        .combine_first(work.get("ref_life_form", pd.Series(index=work.index, dtype="object")))
    )

    drop_cols = [
        "__latin_key",
        "__cn_key",
        "__cn_raw_key",
        "ref_height_m_latin",
        "ref_wd_latin",
        "ref_life_form_latin",
        "ref_height_m_cn",
        "ref_wd_cn",
        "ref_life_form_cn",
        "ref_height_m",
        "ref_wd",
        "ref_life_form",
    ]
    work = work.drop(columns=[c for c in drop_cols if c in work.columns], errors="ignore")
    return work


@lru_cache(maxsize=1)
def load_monitoring_records() -> pd.DataFrame:
    """读取并标准化完整调查记录，不聚合 branch，供数据库导入。"""
    monitoring_file, monitoring_sheet = _resolve_monitoring_source()
    df = pd.read_excel(
        monitoring_file,
        sheet_name=monitoring_sheet,
        keep_default_na=True,
        na_values=NA_VALUES,
    )

    # 字段映射到统一的数据访问层标准名。
    df = df.rename(columns=_build_rename_map(df.columns, _MONITORING_ALIAS_LOOKUP))
    df = df.drop(columns=[column for column in df.columns if str(column).startswith("Unnamed:")], errors="ignore")

    # 清洗字符串
    for col in [
        "tree_id",
        "qudrat_id",
        "subplot_id",
        "species_cn",
        "species_cn_raw",
        "species_latin",
        "status",
        "stem_part",
    ]:
        if col in df.columns:
            df[col] = _clean_string_series(df[col])

    # 数值字段
    for col in [
        "global_x",
        "global_y",
        "dbh_2016_cm",
        "dbh_2021_cm",
        "survey_year_2016",
        "survey_year_2021",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def prepare_monitoring_data(df: pd.DataFrame, enrich_for_agb: bool = True) -> pd.DataFrame:
    """将数据库中的完整调查记录聚合为工具使用的单木级数据。"""
    df = df.copy()

    # 按 tree_id 聚合：同一树的多枝条 DBH 合并为等效胸径
    df = _aggregate_monitoring_tree_level(df)

    # 统一当前胸径：优先 2021，其次 2016
    if "dbh_2021_cm" in df.columns:
        fallback = df.get("dbh_2016_cm", pd.Series(index=df.index, dtype="float64"))
        df["dbh_cm"] = df["dbh_2021_cm"].combine_first(fallback)
    else:
        df["dbh_cm"] = df.get("dbh_2016_cm")

    # 20m 网格索引（以 global_x/global_y 推导网格编号）
    if "global_x" in df.columns and "global_y" in df.columns:
        df["grid_x_20m"] = (df["global_x"] // 20).astype("Int64")
        df["grid_y_20m"] = (df["global_y"] // 20).astype("Int64")

    # 聚合到单木后，不再保留枝条层 stem_part；仅保留记录条数
    df["stem_part"] = pd.Series([pd.NA] * len(df), dtype="string")

    # 用旧表补齐用于 AGB 的关键字段（高度、木材密度、生活型）
    if enrich_for_agb:
        df = _merge_species_reference(df)
        df["height_imputed"] = df["height_m"].notna()
        df["wd_imputed"] = df["wood_density_g_cm3"].notna()

    # 额外保留状态统一
    if "status" in df.columns:
        df["status"] = df["status"].str.lower().replace({"alive": "alive", "dead": "dead"})

    return df


@lru_cache(maxsize=2)
def load_monitoring_data(enrich_for_agb: bool = True) -> pd.DataFrame:
    """从原调查表加载记录，并按工具规则聚合到单木级。"""
    return prepare_monitoring_data(load_monitoring_records(), enrich_for_agb)


@lru_cache(maxsize=2)
def load_grid_plot_data(enrich_for_agb: bool = True) -> pd.DataFrame:
    """
    自动加载“网格样地单木数据”并标准化为系统字段。

    说明：
    - 会自动扫描 `data/raw` 下所有 xlsx，按字段匹配选择最可能的网格单木表；
    - 当前表采用 CGCS2000 投影坐标（树方位X/Y，单位米）。
    - 若缺少 AGB 所需性状（树高/木材密度），按物种均值补齐；
      若表内缺少物种字段，则回退为全库均值。
    """
    grid_file, sheet_name = _resolve_grid_plot_source()

    df = pd.read_excel(
        grid_file,
        sheet_name=sheet_name,
        keep_default_na=True,
        na_values=NA_VALUES,
    )
    df = df.rename(columns=_build_grid_plot_rename_map(df.columns))

    for col in ["grid_id", "species_cn", "species_latin"]:
        if col in df.columns:
            df[col] = _clean_string_series(df[col])

    for col in [
        "tree_seq_id",
        "global_x",
        "global_y",
        "tree_z_m",
        "height_m",
        "dbh_m",
        "crown_diameter_m",
        "crown_ns_m",
        "crown_ew_m",
        "crown_area_m2",
        "crown_volume_m3",
        "clear_bole_height_m",
        "elevation_m",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 将胸径从米转为厘米，以复用现有 AGB 公式（DBH 单位为 cm）
    if "dbh_m" in df.columns:
        df["dbh_cm"] = df["dbh_m"] * 100.0

    if "global_x" in df.columns and "global_y" in df.columns:
        df["grid_x_20m"] = (df["global_x"] // 20).astype("Int64")
        df["grid_y_20m"] = (df["global_y"] // 20).astype("Int64")

    if enrich_for_agb:
        refs = _build_traits_species_reference()
        trait_df = load_traits().copy()
        global_height_mean = float(trait_df["height_m"].dropna().mean()) if "height_m" in trait_df.columns else float("nan")
        global_wd_mean = float(trait_df["wood_density_g_cm3"].dropna().mean()) if "wood_density_g_cm3" in trait_df.columns else float("nan")

        ref_height = pd.Series([global_height_mean] * len(df), index=df.index, dtype="float64")
        ref_wd = pd.Series([global_wd_mean] * len(df), index=df.index, dtype="float64")

        if len(refs) > 0 and "species_latin" in df.columns:
            latin_ref = refs[refs["key_type"] == "species_latin"][["species_key", "ref_height_m", "ref_wd"]].copy()
            latin_ref = latin_ref.rename(columns={"species_key": "__latin_key"})
            df = df.merge(latin_ref, how="left", left_on="species_latin", right_on="__latin_key")
            ref_height = df["ref_height_m"].combine_first(ref_height)
            ref_wd = df["ref_wd"].combine_first(ref_wd)

        if len(refs) > 0 and "species_cn" in df.columns:
            cn_ref = refs[refs["key_type"] == "species_cn"][["species_key", "ref_height_m", "ref_wd"]].copy()
            cn_ref = cn_ref.rename(columns={"species_key": "__cn_key"})
            df = df.merge(
                cn_ref,
                how="left",
                left_on="species_cn",
                right_on="__cn_key",
                suffixes=("", "_cn"),
            )
            ref_height = df.get("ref_height_m_cn", pd.Series(index=df.index, dtype="float64")).combine_first(ref_height)
            ref_wd = df.get("ref_wd_cn", pd.Series(index=df.index, dtype="float64")).combine_first(ref_wd)

        if "height_m" not in df.columns:
            df["height_m"] = np.nan
        height_series = pd.to_numeric(df["height_m"], errors="coerce")
        before_height_na = height_series.isna()
        df["height_m"] = height_series.combine_first(ref_height)
        df["height_imputed"] = before_height_na & df["height_m"].notna()

        # 表内通常没有 WD，按物种均值（无物种时回退全库均值）补齐
        if "wood_density_g_cm3" not in df.columns:
            df["wood_density_g_cm3"] = np.nan
        wd_series = pd.to_numeric(df["wood_density_g_cm3"], errors="coerce")
        before_wd_na = wd_series.isna()
        df["wood_density_g_cm3"] = wd_series.combine_first(ref_wd)
        df["wd_imputed"] = before_wd_na & df["wood_density_g_cm3"].notna()

        drop_cols = ["__latin_key", "__cn_key", "ref_height_m", "ref_wd", "ref_height_m_cn", "ref_wd_cn"]
        df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")

    return df


def load_large_plot_segmentation_data() -> pd.DataFrame:
    """
    加载“20公顷大样地单木分割属性合并”并标准化字段。

    输出字段与 `load_grid_plot_data` 保持一致风格（含 global_x/global_y/dbh_m 等）。
    """
    seg_file, sheet_name = _resolve_large_plot_seg_source()
    df = pd.read_excel(
        seg_file,
        sheet_name=sheet_name,
        keep_default_na=True,
        na_values=NA_VALUES,
    )
    df = df.rename(columns=_build_grid_plot_rename_map(df.columns))

    for col in ["grid_id", "species_cn", "species_latin"]:
        if col in df.columns:
            df[col] = _clean_string_series(df[col])

    for col in [
        "tree_seq_id",
        "global_x",
        "global_y",
        "tree_z_m",
        "height_m",
        "dbh_m",
        "crown_diameter_m",
        "crown_ns_m",
        "crown_ew_m",
        "crown_area_m2",
        "crown_volume_m3",
        "clear_bole_height_m",
        "elevation_m",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "dbh_m" in df.columns:
        df["dbh_cm"] = df["dbh_m"] * 100.0
    if "global_x" in df.columns and "global_y" in df.columns:
        df["grid_x_20m"] = (df["global_x"] // 20).astype("Int64")
        df["grid_y_20m"] = (df["global_y"] // 20).astype("Int64")

    return df


def prepare_segmentation_data(df: pd.DataFrame, enrich_for_agb: bool = True) -> pd.DataFrame:
    """为数据库中的完整单木分割记录补齐工具计算所需的派生字段。"""
    work = df.copy()
    if "dbh_m" in work.columns:
        work["dbh_cm"] = pd.to_numeric(work["dbh_m"], errors="coerce") * 100.0
    if "global_x" in work.columns and "global_y" in work.columns:
        work["grid_x_20m"] = (pd.to_numeric(work["global_x"], errors="coerce") // 20).astype("Int64")
        work["grid_y_20m"] = (pd.to_numeric(work["global_y"], errors="coerce") // 20).astype("Int64")
    if enrich_for_agb:
        traits = load_traits()
        mean_wd = float(traits["wood_density_g_cm3"].dropna().mean())
        if "wood_density_g_cm3" not in work:
            work["wood_density_g_cm3"] = mean_wd
        else:
            work["wood_density_g_cm3"] = pd.to_numeric(work["wood_density_g_cm3"], errors="coerce").fillna(mean_wd)
        work["height_imputed"] = False
        work["wd_imputed"] = True
    return work


def load_vegetation_type_classification() -> pd.DataFrame:
    """
    加载“车八岭植被类型分类-final”并标准化为网格 -> 植被亚型映射。

    Returns:
        至少包含：
        - grid_code: 网格编号（如 A07）
        - vegetation_group: 植被亚型名称（如 Ⅰ-1 亚热带常绿针叶林）
    """
    veg_file, veg_sheet = _resolve_vegetation_source()
    df = pd.read_excel(
        veg_file,
        sheet_name=veg_sheet,
        keep_default_na=True,
        na_values=NA_VALUES,
    )
    # 明确优先级：植被分类标准统一使用“植被亚型名称”；
    # 若缺失再依次回退，避免误用到群系名称等更细分字段。
    grid_col = None
    for c in ["网格", "网格编号", "grid_code", "grid", "wangge"]:
        if c in df.columns:
            grid_col = c
            break
    if grid_col is None:
        rename_map = _build_rename_map(df.columns, _VEGETATION_ALIAS_LOOKUP)
        df = df.rename(columns=rename_map)
        if "grid_code" in df.columns:
            grid_col = "grid_code"

    veg_col = None
    for c in ["植被亚型名称", "植被型名称", "植被型组", "植被类型", "群系名称"]:
        if c in df.columns:
            veg_col = c
            break
    if veg_col is None:
        rename_map = _build_rename_map(df.columns, _VEGETATION_ALIAS_LOOKUP)
        df = df.rename(columns=rename_map)
        if "vegetation_group" in df.columns:
            veg_col = "vegetation_group"

    if grid_col is None or veg_col is None:
        raise ValueError("植被类型分类表缺少必要列（需包含网格编号与植被亚型名称/植被类型）。")

    out = df[[grid_col, veg_col]].copy()
    out = out.rename(columns={grid_col: "grid_code", veg_col: "vegetation_group"})
    out["grid_code"] = _clean_string_series(out["grid_code"]).str.upper()
    out["vegetation_group"] = _clean_string_series(out["vegetation_group"])
    out = out.dropna(subset=["grid_code", "vegetation_group"])
    out = out.drop_duplicates(subset=["grid_code"], keep="first").reset_index(drop=True)
    return out


def load_plot_qudrat_mapping() -> pd.DataFrame:
    """
    加载“采集编号对应表”，输出标准字段：
    - grid_id: 20公顷样地采集编号（如 20GQ001）
    - qudrat_id: 监测表 qudrat 编号（如 101）
    """
    map_file, map_sheet = _resolve_plot_qudrat_mapping_source()
    df = pd.read_excel(
        map_file,
        sheet_name=map_sheet,
        keep_default_na=True,
        na_values=NA_VALUES,
    )
    df = df.rename(columns=_build_rename_map(df.columns, _PLOT_QUDRAT_MAP_ALIAS_LOOKUP))

    missing = [c for c in ["grid_id", "qudrat_id"] if c not in df.columns]
    if missing:
        raise ValueError(f"采集编号对应表缺少必要字段：{missing}")

    out = df[["grid_id", "qudrat_id"]].copy()
    out["grid_id"] = _clean_string_series(out["grid_id"]).str.upper()
    out["qudrat_id"] = _normalize_qudrat_id_series(out["qudrat_id"])

    out = out.dropna(subset=["grid_id", "qudrat_id"])
    out = out.drop_duplicates(subset=["grid_id", "qudrat_id"], keep="first").reset_index(drop=True)
    return out


def load_grid_survey_data() -> pd.DataFrame:
    """
    加载“网格调查数据”并标准化为：
    - grid_code: 网格号（如 A07）
    - dbh_2022_cm: DBH2022（cm）
    """
    survey_file, survey_sheet = _resolve_grid_survey_source()
    df = pd.read_excel(
        survey_file,
        sheet_name=survey_sheet,
        keep_default_na=True,
        na_values=NA_VALUES,
    )
    df = df.rename(columns=_build_rename_map(df.columns, _GRID_SURVEY_ALIAS_LOOKUP))

    missing = [c for c in ["grid_code", "dbh_2022_cm"] if c not in df.columns]
    if missing:
        raise ValueError(f"网格调查数据缺少必要字段：{missing}")

    out = df[["grid_code", "dbh_2022_cm"]].copy()
    out["grid_code"] = _clean_string_series(out["grid_code"]).str.upper()
    out["dbh_2022_cm"] = pd.to_numeric(out["dbh_2022_cm"], errors="coerce")
    return out


def load_model_tree_bridge_data() -> pd.DataFrame:
    """
    加载“样地1800树调查数据-建模每木”并标准化中介字段：
    - tag7: 由编号转为 7 位字符串（如 307048 -> 0307048）
    - model_north: 转换后北坐标（对应分割表树方位Y）
    - model_east: 转换后东坐标（对应分割表树方位X）
    """
    bridge_file, bridge_sheet = _resolve_model_tree_bridge_source()
    df = pd.read_excel(
        bridge_file,
        sheet_name=bridge_sheet,
        header=[0, 1],  # 建模每木是双层表头
        keep_default_na=True,
        na_values=NA_VALUES,
    )
    flat_cols = []
    for c0, c1 in df.columns:
        c0s = str(c0).strip()
        c1s = str(c1).strip()
        if c0s in {"原始采集", "转换后"}:
            flat_cols.append(f"{c0s}_{c1s}")
        else:
            flat_cols.append(c0s)
    df.columns = flat_cols

    required = ["编号", "转换后_北坐标", "转换后_东坐标"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"建模每木表缺少必要字段：{missing}")

    out = df[["编号", "转换后_北坐标", "转换后_东坐标"]].copy()
    out["编号"] = pd.to_numeric(out["编号"], errors="coerce").astype("Int64")
    out["tag7"] = out["编号"].astype("string").str.zfill(7)
    out["model_north"] = pd.to_numeric(out["转换后_北坐标"], errors="coerce")
    out["model_east"] = pd.to_numeric(out["转换后_东坐标"], errors="coerce")
    out = out.dropna(subset=["tag7", "model_north", "model_east"]).reset_index(drop=True)
    return out[["tag7", "model_north", "model_east"]]


def main():
    df = load_traits()

    print("=== 标准化后的字段 ===")
    print(df.columns.tolist())

    print("\n=== 前5行 ===")
    print(df.head())

    print("\n=== 缺失值统计 ===")
    print(df.isna().sum().sort_values(ascending=False).head(20))

    print("\n=== 基础概览 ===")
    print({
        "n_rows": len(df),
        "n_species": df["species_cn"].nunique(dropna=True) if "species_cn" in df.columns else None,
        "dbh_non_null": int(df["dbh_cm"].notna().sum()) if "dbh_cm" in df.columns else None,
        "height_non_null": int(df["height_m"].notna().sum()) if "height_m" in df.columns else None,
        "wd_non_null": int(df["wood_density_g_cm3"].notna().sum()) if "wood_density_g_cm3" in df.columns else None,
    })


if __name__ == "__main__":
    main()
