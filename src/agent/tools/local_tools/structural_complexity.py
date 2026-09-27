# Local Tools: business computation/retrieval, without agent orchestration.
# Agent local ecology capability.
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StructuralComplexityResult:
    """结构复杂度计算结果容器（总分、分量、分组明细）。"""
    score: Optional[float]
    components: dict
    by_unit: list[dict]


def _series(frame: pd.DataFrame, name: str) -> pd.Series:
    """Return a real Series so pandas' optional ``DataFrame.get`` is not leaked."""
    return frame[name] if name in frame.columns else pd.Series(dtype="float64")


def _safe_cv(values: pd.Series) -> Optional[float]:
    """计算变异系数（CV），样本不足或均值为 0 时返回 None。"""
    v = pd.to_numeric(values, errors="coerce").dropna()
    if len(v) < 2:
        return None
    m = float(v.mean())
    if m == 0:
        return None
    return float(v.std(ddof=1) / m)


def _shannon_entropy(counts: np.ndarray) -> Optional[float]:
    """计算 Shannon 熵，输入总和<=0 时返回 None。"""
    counts = np.asarray(counts, dtype=float)
    s = counts.sum()
    if s <= 0:
        return None
    p = counts[counts > 0] / s
    return float(-(p * np.log(p)).sum())


def _normalized(value: Optional[float], kind: str, *, max_cv: float = 1.0) -> Optional[float]:
    """将分量标准化到 0-1 范围，便于综合打分。"""
    if value is None or not np.isfinite(value):
        return None
    if kind == "cv":
        return float(min(max(value / max_cv, 0.0), 1.0))
    if kind == "entropy":
        # entropy 归一化需外部给 max，默认认为已是 0~1
        return float(min(max(value, 0.0), 1.0))
    return float(value)


def _compute_group_metrics(g: pd.DataFrame, height_bins: int = 6) -> dict:
    """单个子样方或单个 20m 网格内的结构复杂度分量与综合分。"""
    hcv = _safe_cv(_series(g, "height_m"))
    dcv = _safe_cv(_series(g, "dbh_cm"))

    # 监测数据里 species_cn 可能为空，回退到 species_cn_raw / species_latin
    sp = None
    for c in ["species_cn", "species_cn_raw", "species_latin"]:
        if c in g.columns:
            s = g[c].astype("string").str.strip()
            s = s.where(s.notna() & (s != ""))
            if s.notna().sum() > 0:
                sp = s
                break
    sh_norm = None
    sp_richness = None
    if sp is not None:
        vc = sp.dropna().astype(str).value_counts()
        sp_richness = int(len(vc))
        sh = _shannon_entropy(vc.to_numpy())
        if sh is not None and len(vc) > 1:
            sh_norm = float(sh / np.log(len(vc)))

    hg = pd.to_numeric(_series(g, "height_m"), errors="coerce").dropna()
    ve_norm = None
    if len(hg) >= 2:
        qs = np.linspace(0, 1, height_bins + 1)
        edges = np.unique(np.quantile(hg.to_numpy(), qs))
        if len(edges) >= 3:
            bins = pd.cut(hg, bins=edges.tolist(), include_lowest=True)
            counts = bins.value_counts().to_numpy()
            ve = _shannon_entropy(counts)
            if ve is not None:
                ve_norm = float(ve / np.log(len(counts))) if len(counts) > 1 else 0.0

    parts = [
        _normalized(dcv, "cv"),
        _normalized(hcv, "cv"),
        _normalized(sh_norm, "entropy"),
        _normalized(ve_norm, "entropy"),
    ]
    parts = [v for v in parts if v is not None]
    unit_score = float(np.mean(parts)) if parts else None

    return {
        "n_records": int(len(g)),
        "dbh_cv": dcv,
        "height_cv": hcv,
        "species_richness": sp_richness,
        "species_shannon_norm": sh_norm,
        "vertical_entropy_norm": ve_norm,
        "score": unit_score,
    }


def aggregate_structural_complexity_20m_grid(
    df: pd.DataFrame,
    *,
    height_bins: int = 6,
    min_trees: int = 2,
) -> pd.DataFrame:
    """
    按 20m 网格（grid_x_20m, grid_y_20m）聚合，每个格网计算一套结构复杂度指标。
    格网内样本数 < min_trees 时该格不输出（避免 CV/熵不稳定）。
    """
    need = ["grid_x_20m", "grid_y_20m"]
    for c in need:
        if c not in df.columns:
            raise ValueError(f"缺少 {c} 列，无法按 20m 网格聚合结构复杂度。")

    work = df.copy()
    work["grid_x_20m"] = pd.to_numeric(work["grid_x_20m"], errors="coerce")
    work["grid_y_20m"] = pd.to_numeric(work["grid_y_20m"], errors="coerce")
    work = work.dropna(subset=["grid_x_20m", "grid_y_20m"])

    rows = []
    for (gx, gy), g in work.groupby(["grid_x_20m", "grid_y_20m"], dropna=True):
        if len(g) < min_trees:
            continue
        m = _compute_group_metrics(g, height_bins=height_bins)
        rows.append(
            {
                "grid_x_20m": float(str(gx)),
                "grid_y_20m": float(str(gy)),
                **m,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "grid_x_20m",
                "grid_y_20m",
                "n_records",
                "dbh_cv",
                "height_cv",
                "species_richness",
                "species_shannon_norm",
                "vertical_entropy_norm",
                "score",
            ]
        )

    return pd.DataFrame(rows)


def compute_structural_complexity(
    df: pd.DataFrame,
    unit_col: Optional[str] = None,
    height_bins: int = 6,
) -> StructuralComplexityResult:
    """
    结构复杂度：以“可解释、可落地”为目标的简化版本。

    输出包括：
    - 全局 components：dbh_cv、height_cv、species_shannon_norm、vertical_entropy_norm
    - 全局 score：上述可用项的均值
    - by_unit：若提供 unit_col（如 subplot_id 或 (grid_x_20m, grid_y_20m) 组合列），给出分组结果
    """
    work = df.copy()

    # 自动选择 unit_col
    if unit_col is None:
        for cand in ["subplot_id"]:
            if cand in work.columns:
                unit_col = cand
                break

    # 全局 component
    height_cv = _safe_cv(_series(work, "height_m"))
    dbh_cv = _safe_cv(_series(work, "dbh_cm"))

    species = work.get("species_cn")
    species_shannon = None
    species_shannon_norm = None
    if species is not None:
        vc = species.dropna().astype(str).value_counts()
        species_shannon = _shannon_entropy(vc.to_numpy())
        if species_shannon is not None and len(vc) > 1:
            species_shannon_norm = float(species_shannon / np.log(len(vc)))

    vert_entropy = None
    vert_entropy_norm = None
    h = pd.to_numeric(_series(work, "height_m"), errors="coerce").dropna()
    if len(h) >= 2:
        # 分层：按分位点分 bin，尽量适应不同数据尺度
        qs = np.linspace(0, 1, height_bins + 1)
        edges = np.unique(np.quantile(h.to_numpy(), qs))
        if len(edges) >= 3:
            bins = pd.cut(h, bins=edges.tolist(), include_lowest=True)
            counts = bins.value_counts().to_numpy()
            vert_entropy = _shannon_entropy(counts)
            if vert_entropy is not None:
                vert_entropy_norm = float(vert_entropy / np.log(len(counts))) if len(counts) > 1 else 0.0

    components = {
        "dbh_cv": dbh_cv,
        "height_cv": height_cv,
        "species_shannon": species_shannon,
        "species_shannon_norm": species_shannon_norm,
        "vertical_entropy": vert_entropy,
        "vertical_entropy_norm": vert_entropy_norm,
    }

    score_parts = [
        _normalized(dbh_cv, "cv"),
        _normalized(height_cv, "cv"),
        _normalized(species_shannon_norm, "entropy"),
        _normalized(vert_entropy_norm, "entropy"),
    ]
    score_parts = [v for v in score_parts if v is not None]
    score = float(np.mean(score_parts)) if score_parts else None

    # 分组结果
    by_unit: list[dict] = []
    if unit_col and unit_col in work.columns:
        for unit, g in work.groupby(unit_col, dropna=True):
            m = _compute_group_metrics(g, height_bins=height_bins)
            by_unit.append({"unit": str(unit), **m})

        by_unit = sorted(
            by_unit,
            key=lambda r: (r["score"] is None, -(r["score"] or 0.0)),
        )

    return StructuralComplexityResult(score=score, components=components, by_unit=by_unit)
