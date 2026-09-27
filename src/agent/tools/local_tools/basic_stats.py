# Local Tools: business computation/retrieval, without agent orchestration.
# Agent local ecology capability.
import pandas as pd


def species_count(df: pd.DataFrame) -> pd.DataFrame:
    """统计各物种记录数并按数量降序返回。"""
    result = (
        df.groupby("species_cn")
        .size()
        .rename("count")
        .reset_index()
        .sort_values("count", ascending=False)
    )
    return result


def dbh_height_summary(df: pd.DataFrame) -> dict:
    """汇总样本规模与关键性状均值（DBH/树高/木材密度）。"""
    return {
        "tree_count": int(len(df)),
        "dbh_mean_cm": float(df["dbh_cm"].dropna().mean()) if "dbh_cm" in df.columns else None,
        "height_mean_m": float(df["height_m"].dropna().mean()) if "height_m" in df.columns else None,
        "wd_mean_g_cm3": float(df["wood_density_g_cm3"].dropna().mean()) if "wood_density_g_cm3" in df.columns else None,
    }


def missing_summary(df: pd.DataFrame) -> dict:
    """统计核心字段缺失数量，用于快速判断数据可用性。"""
    important_cols = ["dbh_cm", "height_m", "wood_density_g_cm3", "species_cn", "status"]
    result = {}
    for col in important_cols:
        if col in df.columns:
            result[col] = int(df[col].isna().sum())
    return result
