# Local Tools: business computation/retrieval, without agent orchestration.
# Agent local ecology capability.
import pandas as pd
import numpy as np


def add_agb_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    按论文中的 Chave et al. (2014) 公式计算单木 AGB:
    AGB = 0.0673 * (WD * DBH^2 * H) ^ 0.976

    其中：
    - WD: wood density (g/cm3)
    - DBH: diameter at breast height (cm)
    - H: height (m)
    """
    result = df.copy()

    required = ["dbh_cm", "height_m", "wood_density_g_cm3"]
    for col in required:
        if col not in result.columns:
            raise ValueError(f"缺少计算 AGB 所需字段: {col}")

    mask = (
        result["dbh_cm"].notna()
        & result["height_m"].notna()
        & result["wood_density_g_cm3"].notna()
    )

    result["agb_kg"] = np.nan
    result.loc[mask, "agb_kg"] = 0.0673 * (
        result.loc[mask, "wood_density_g_cm3"]
        * (result.loc[mask, "dbh_cm"] ** 2)
        * result.loc[mask, "height_m"]
    ) ** 0.976

    return result


def agb_summary(df: pd.DataFrame) -> dict:
    """基于 `agb_kg` 列返回总量、均值、最大值及缺失统计。"""
    if "agb_kg" not in df.columns:
        raise ValueError("请先调用 add_agb_column() 生成 agb_kg 列")

    valid_df = df[df["agb_kg"].notna()]

    return {
        "total_records": int(len(df)),
        "valid_agb_records": int(len(valid_df)),
        "missing_agb_records": int(df["agb_kg"].isna().sum()),
        "agb_sum_kg": float(valid_df["agb_kg"].sum()) if len(valid_df) > 0 else 0.0,
        "agb_mean_kg": float(valid_df["agb_kg"].mean()) if len(valid_df) > 0 else 0.0,
        "agb_max_kg": float(valid_df["agb_kg"].max()) if len(valid_df) > 0 else 0.0,
    }


def agb_by_species(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """按物种汇总 AGB 总量并返回 Top N。"""
    if "agb_kg" not in df.columns:
        raise ValueError("请先调用 add_agb_column() 生成 agb_kg 列")

    valid_df = df[df["agb_kg"].notna()].copy()

    result = (
        valid_df.groupby("species_cn", dropna=False)["agb_kg"]
        .sum()
        .reset_index()
        .sort_values("agb_kg", ascending=False)
        .head(top_n)
    )
    return result


def agb_by_grid(df: pd.DataFrame, grid_col: str = "grid_id") -> pd.DataFrame:
    """按网格汇总 AGB（总量/均值/记录数），并保留网格中心坐标。"""
    if "agb_kg" not in df.columns:
        raise ValueError("请先调用 add_agb_column() 生成 agb_kg 列")
    if grid_col not in df.columns:
        raise ValueError(f"缺少网格字段: {grid_col}")

    work = df.copy()
    if "global_x" in work.columns:
        work["global_x"] = pd.to_numeric(work["global_x"], errors="coerce")
    if "global_y" in work.columns:
        work["global_y"] = pd.to_numeric(work["global_y"], errors="coerce")
    work["agb_kg"] = pd.to_numeric(work["agb_kg"], errors="coerce")

    grouped = work.groupby(grid_col, dropna=False)
    out = grouped["agb_kg"].agg(["sum", "mean", "count"]).reset_index()
    out = out.rename(
        columns={
            "sum": "agb_sum_kg",
            "mean": "agb_mean_kg",
            "count": "valid_agb_records",
        }
    )
    out["tree_records"] = grouped.size().values

    if "global_x" in work.columns and "global_y" in work.columns:
        centers = grouped[["global_x", "global_y"]].mean().reset_index()
        out = out.merge(centers, on=grid_col, how="left")

    out = out.sort_values("agb_sum_kg", ascending=False).reset_index(drop=True)
    return out
