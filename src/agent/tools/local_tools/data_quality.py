# Local Tools: business computation/retrieval, without agent orchestration.
# Agent local ecology capability.
import pandas as pd


def column_summary(df: pd.DataFrame) -> list[dict]:
    """逐列输出类型、空值与非空值统计。"""
    results = []

    for col in df.columns:
        results.append(
            {
                "column": col,
                "dtype": str(df[col].dtype),
                "non_null_count": int(df[col].notna().sum()),
                "null_count": int(df[col].isna().sum()),
                "null_ratio": round(float(df[col].isna().mean()), 4),
            }
        )

    return results


def missing_report(df: pd.DataFrame) -> dict:
    """返回每列缺失计数与缺失比例。"""
    return {
        col: {
            "null_count": int(df[col].isna().sum()),
            "null_ratio": round(float(df[col].isna().mean()), 4),
        }
        for col in df.columns
    }


def numeric_summary(df: pd.DataFrame) -> dict:
    """对全部数值列计算 count/mean/min/max。"""
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    result = {}

    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) == 0:
            result[col] = {
                "count": 0,
                "mean": None,
                "min": None,
                "max": None,
            }
        else:
            result[col] = {
                "count": int(series.shape[0]),
                "mean": float(series.mean()),
                "min": float(series.min()),
                "max": float(series.max()),
            }

    return result


def agb_ready_report(df: pd.DataFrame) -> dict:
    """检查记录是否满足 AGB 计算条件（DBH/高度/木材密度齐全）。"""
    required_cols = ["dbh_cm", "height_m", "wood_density_g_cm3"]

    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"缺少 AGB 所需字段: {col}")

    ready_mask = (
        df["dbh_cm"].notna()
        & df["height_m"].notna()
        & df["wood_density_g_cm3"].notna()
    )

    ready_df = df[ready_mask].copy()
    not_ready_df = df[~ready_mask].copy()

    return {
        "total_records": int(len(df)),
        "agb_ready_records": int(len(ready_df)),
        "agb_not_ready_records": int(len(not_ready_df)),
        "agb_ready_ratio": round(float(len(ready_df) / len(df)), 4) if len(df) > 0 else 0.0,
        "missing_dbh": int(df["dbh_cm"].isna().sum()),
        "missing_height": int(df["height_m"].isna().sum()),
        "missing_wd": int(df["wood_density_g_cm3"].isna().sum()),
    }


def status_distribution(df: pd.DataFrame) -> list[dict]:
    """统计存活状态字段 `status` 的频次分布。"""
    if "status" not in df.columns:
        return []

    result = (
        df.groupby("status", dropna=False)
        .size()
        .rename("count")
        .reset_index()
        .sort_values("count", ascending=False)
    )

    return result.to_dict(orient="records")
