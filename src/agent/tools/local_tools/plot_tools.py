# pyright: reportArgumentType=false, reportGeneralTypeIssues=false, reportCallIssue=false, reportAttributeAccessIssue=false
# Local Tools: business computation/retrieval, without agent orchestration.
# Agent local ecology capability.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import re

import base64
import io
import numpy as np
import pandas as pd

# 重要：后端服务/多线程环境下禁用 macOS GUI backend
# 必须在 import matplotlib.pyplot 之前设置
import matplotlib

matplotlib.use("Agg")

from matplotlib import colors as mpl_colors
from matplotlib import ticker as ticker
from matplotlib import ticker as mpl_ticker

from scipy.spatial import Delaunay, cKDTree
from src.project_paths import REFERENCE_DATA_DIR


VECTOR_GRID_DIR = REFERENCE_DATA_DIR / "车八岭矢量图（网格）" / "车八岭矢量图"


@dataclass(frozen=True)
class PlotArtifact:
    """前端图像产物结构：标题、MIME、文件名与 base64 内容。"""
    title: str
    mime: str
    filename: str
    content_base64: str


def _configure_matplotlib_fonts() -> None:
    """统一配置绘图字体与基础样式，优先兼容中文渲染。"""
    # 尽量使用 macOS 常见中文字体；找不到则回退到 DejaVu Sans
    matplotlib.rcParams["font.sans-serif"] = [
        "PingFang SC",
        "Heiti SC",
        "Songti SC",
        "Hiragino Sans GB",
        "Arial Unicode MS",
        "SimHei",
        "Noto Sans CJK SC",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["figure.facecolor"] = "white"
    matplotlib.rcParams["axes.facecolor"] = "white"
    matplotlib.rcParams["axes.edgecolor"] = "#222222"
    matplotlib.rcParams["axes.linewidth"] = 0.8
    matplotlib.rcParams["grid.color"] = "#b0b0b0"
    matplotlib.rcParams["grid.alpha"] = 0.25
    matplotlib.rcParams["grid.linewidth"] = 0.8
    matplotlib.rcParams["xtick.color"] = "#222222"
    matplotlib.rcParams["ytick.color"] = "#222222"
    matplotlib.rcParams["xtick.labelsize"] = 10
    matplotlib.rcParams["ytick.labelsize"] = 10
    matplotlib.rcParams["axes.labelsize"] = 11
    matplotlib.rcParams["axes.titlesize"] = 12
    matplotlib.rcParams["legend.fontsize"] = 9


def _pick_xy_columns(df: pd.DataFrame) -> tuple[Optional[str], Optional[str]]:
    """自动选择可用的空间坐标列名（优先 global_x/global_y）。"""
    for x, y in [
        ("global_x", "global_y"),
        ("grid_x_20m", "grid_y_20m"),
        ("GX", "GY"),  # 兼容未标准化情况
        ("x20", "y20"),
    ]:
        if x in df.columns and y in df.columns:
            return x, y
    return None, None


def _freedman_diaconis_bins(x: np.ndarray) -> int:
    """使用 Freedman-Diaconis 规则估算直方图箱数，并做稳健裁剪。"""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return 10
    q25, q75 = np.percentile(x, [25, 75])
    iqr = q75 - q25
    if iqr <= 0:
        return int(np.clip(np.sqrt(n), 10, 80))
    bin_width = 2 * iqr * (n ** (-1 / 3))
    if bin_width <= 0:
        return int(np.clip(np.sqrt(n), 10, 80))
    bins = int(np.ceil((x.max() - x.min()) / bin_width))
    return int(np.clip(bins, 10, 80))


def _fig_to_base64_png(fig) -> str:
    """将 matplotlib Figure 编码为 base64 PNG 字符串。"""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def _web_mercator_to_lonlat(x: float, y: float) -> tuple[float, float]:
    """将 Web Mercator 米坐标转为经纬度；用于兼容部分矢量网格图层。"""
    lon = x / 6378137.0 * 180.0 / np.pi
    lat = (2.0 * np.arctan(np.exp(y / 6378137.0)) - np.pi / 2.0) * 180.0 / np.pi
    return float(lon), float(lat)


def _normalize_map_xy(x: float, y: float) -> tuple[float, float]:
    """矢量图层坐标可能是经纬度或 Web Mercator，这里统一到经纬度坐标。"""
    if abs(x) > 180 or abs(y) > 90:
        return _web_mercator_to_lonlat(x, y)
    return float(x), float(y)


def _iter_shape_parts(shape) -> list[list[tuple[float, float]]]:
    """将 pyshp 的 multipart geometry 拆为点列表。"""
    points = shape.points
    parts = list(shape.parts) + [len(points)]
    out = []
    for start, end in zip(parts[:-1], parts[1:]):
        part = [_normalize_map_xy(float(x), float(y)) for x, y in points[start:end]]
        if len(part) >= 2:
            out.append(part)
    return out


def _read_shapefile_records(name: str):
    """读取矢量图层，返回字段字典与 shape；缺文件时返回空列表。"""
    shp_path = VECTOR_GRID_DIR / f"{name}.shp"
    if not shp_path.exists():
        return []

    import shapefile

    reader = shapefile.Reader(str(shp_path), encoding="utf-8", encodingErrors="replace")
    fields = [f[0] for f in reader.fields[1:]]
    return [(dict(zip(fields, sr.record)), sr.shape) for sr in reader.iterShapeRecords()]


def _load_vector_grid_locations() -> pd.DataFrame:
    """读取矢量图中的网格样地位置（样方号 -> 经纬度）。"""
    records = []
    for attrs, shape in _read_shapefile_records("网格样地"):
        grid_id = attrs.get("样方号")
        if not grid_id:
            continue
        lon = attrs.get("经度")
        lat = attrs.get("纬度")
        if lon is None or lat is None:
            points = getattr(shape, "points", None)
            if not points:
                continue
            lon, lat = points[0][:2]
        x, y = _normalize_map_xy(float(lon), float(lat))
        records.append({"grid_id": str(grid_id).strip(), "map_x": x, "map_y": y, "position_source": "vector"})
    return pd.DataFrame(records)


def _attach_vector_positions(grid_df: pd.DataFrame) -> pd.DataFrame:
    """
    将网格 AGB 表映射到矢量地图位置。

    优先使用 `网格样地.shp` 中的样方号位置；对于矢量点缺失的网格（如 TDxx），
    使用已匹配网格的 Excel CGCS2000 坐标与矢量经纬度拟合仿射转换后补位。
    """
    loc_df = _load_vector_grid_locations()
    if len(loc_df) == 0:
        return grid_df.copy()

    out = grid_df.copy()
    out["grid_id"] = out["grid_id"].astype(str).str.strip()
    out = out.merge(loc_df, on="grid_id", how="left")

    missing = out["map_x"].isna() | out["map_y"].isna()
    fit_cols = ["global_x", "global_y", "map_x", "map_y"]
    matched = out.dropna(subset=fit_cols)
    if missing.any() and len(matched) >= 3 and {"global_x", "global_y"}.issubset(out.columns):
        gx = pd.to_numeric(matched["global_x"], errors="coerce").to_numpy(dtype=float)
        gy = pd.to_numeric(matched["global_y"], errors="coerce").to_numpy(dtype=float)
        A = np.column_stack([gx, gy, np.ones(len(matched))])
        coef_x, *_ = np.linalg.lstsq(A, matched["map_x"].to_numpy(dtype=float), rcond=None)
        coef_y, *_ = np.linalg.lstsq(A, matched["map_y"].to_numpy(dtype=float), rcond=None)

        miss = out[missing].copy()
        mgx = pd.to_numeric(miss["global_x"], errors="coerce").to_numpy(dtype=float)
        mgy = pd.to_numeric(miss["global_y"], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(mgx) & np.isfinite(mgy)
        if np.any(valid):
            M = np.column_stack([mgx[valid], mgy[valid], np.ones(int(valid.sum()))])
            pred_x = M @ coef_x
            pred_y = M @ coef_y
            idx = miss.index[valid]
            out.loc[idx, "map_x"] = pred_x
            out.loc[idx, "map_y"] = pred_y
            out.loc[idx, "position_source"] = "estimated_from_cgcs2000"

    return out


def _extract_grid_prefix(grid_id: object) -> Optional[str]:
    """从样地编号中提取网格前缀（如 A0701 -> A07）。"""
    if grid_id is None or pd.isna(grid_id):
        return None
    s = str(grid_id).strip().upper()
    if not s:
        return None
    m = re.search(r"[A-Z]\d{2}", s)
    if m:
        return m.group(0)
    s2 = "".join(ch for ch in s if ch.isalnum())
    return s2[:3] if len(s2) >= 3 else None


def _load_vector_grid_polygons() -> pd.DataFrame:
    """
    读取保护区矢量网格面（优先 80 网格），返回网格编号、中心点与多边形顶点。
    """
    records = []
    for layer_name in ("cbl_80网格", "cbl_100网格"):
        rows = _read_shapefile_records(layer_name)
        if not rows:
            continue
        for attrs, shape in rows:
            grid_code = attrs.get("wangge") or attrs.get("网格号") or attrs.get("gridid")
            if grid_code is None or pd.isna(grid_code):
                continue
            parts = _iter_shape_parts(shape)
            if not parts:
                continue
            all_points = [pt for part in parts for pt in part]
            if not all_points:
                continue
            xs = np.array([p[0] for p in all_points], dtype=float)
            ys = np.array([p[1] for p in all_points], dtype=float)
            records.append(
                {
                    "grid_code": str(grid_code).strip().upper(),
                    "parts": parts,
                    "map_x": float(np.mean(xs)),
                    "map_y": float(np.mean(ys)),
                }
            )
        if records:
            break

    if not records:
        return pd.DataFrame(columns=["grid_code", "parts", "map_x", "map_y"])
    out = pd.DataFrame(records)
    out = out.drop_duplicates(subset=["grid_code"], keep="first").reset_index(drop=True)
    return out


def render_agb_histogram(
    df: pd.DataFrame,
    *,
    x_scale: str = "log10",
    year_label: str | None = None,
) -> PlotArtifact:
    """
    绘制 AGB 直方图并返回前端可直接渲染的图像工件。

    Args:
        df: 需包含 `agb_kg` 列的数据表。
        x_scale: 横轴尺度，`log10` 或线性。
        year_label: 可选年份标签，用于标题后缀。
    """
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts()

    valid = pd.to_numeric(df.get("agb_kg"), errors="coerce").dropna()
    if len(valid) == 0:
        raise ValueError("没有可用于绘制直方图的有效 AGB 数据（agb_kg 全缺失）。")

    x_raw = valid.to_numpy(dtype=float)
    stats_src = x_raw[np.isfinite(x_raw)]
    if x_scale == "log10":
        # AGB 常高度右偏，很多论文会用 log 或对数色标来更清晰呈现长尾
        x_pos = x_raw[x_raw > 0]
        if len(x_pos) == 0:
            raise ValueError("AGB 数据中没有正值，无法绘制 log10 直方图。")
        x_plot = np.log10(x_pos)
        stats_src = x_pos
        xlabel = "log10(AGB) (kg)"
        title = "Histogram of AGB (log10 scale)"
    else:
        x_plot = x_raw
        xlabel = "AGB (kg)"
        title = "Histogram of AGB"

    bins = _freedman_diaconis_bins(x_plot)

    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=220)
    ax.hist(
        x_plot,
        bins=bins,
        color="#2c7fb8",
        edgecolor="white",
        linewidth=0.6,
        alpha=0.92,
    )
    title_with_year = f"{title} ({year_label})" if year_label else title
    ax.set_title(title_with_year)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Frequency")
    # 标出均值/中位数（论文里常见的辅助线）
    mean_v = float(np.mean(x_plot))
    med_v = float(np.median(x_plot))
    ax.axvline(mean_v, color="#d95f0e", linestyle="--", linewidth=1.2, label="Mean")
    ax.axvline(med_v, color="#1b9e77", linestyle="-.", linewidth=1.2, label="Median")
    ax.legend(frameon=False, fontsize=9)
    ax.grid(True, axis="y")

    # 图内统计信息（论文里常见：n、均值±SD、范围）
    n = int(len(stats_src))
    mu = float(np.mean(stats_src)) if n else float("nan")
    sd = float(np.std(stats_src, ddof=1)) if n > 1 else float("nan")
    mn = float(np.min(stats_src)) if n else float("nan")
    mx = float(np.max(stats_src)) if n else float("nan")
    # 避免 en-dash/数学负号导致的字体缺字告警，统一使用 ASCII '-'
    txt = f"n = {n}\nmean = {mu:.2f} kg\nSD = {sd:.2f} kg\nmin-max = {mn:.2f}-{mx:.2f} kg"
    ax.text(
        0.98,
        0.98,
        txt,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#dddddd", alpha=0.95),
    )
    fig.tight_layout()
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)

    return PlotArtifact(
        title="AGB 分布直方图",
        mime="image/png",
        filename="agb_histogram.png",
        content_base64=content_b64,
    )


def render_agb_spatial_distribution(
    df: pd.DataFrame,
    *,
    gridsize: int = 60,
    year_label: str | None = None,
) -> PlotArtifact:
    """
    绘制 AGB 空间分布图（hexbin + 对数色标）。

    颜色代表六边形网格内 AGB 均值，适合高密度样点场景。
    """
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts()

    x_col, y_col = _pick_xy_columns(df)
    if not x_col or not y_col:
        raise ValueError("缺少空间坐标字段，无法生成分布图（需要 global_x/global_y 或 grid_x_20m/grid_y_20m）。")

    sub = df[[x_col, y_col, "agb_kg"]].copy()
    sub["agb_kg"] = pd.to_numeric(sub["agb_kg"], errors="coerce")
    sub = sub.dropna(subset=[x_col, y_col, "agb_kg"])

    if len(sub) == 0:
        raise ValueError("没有可用于绘制空间分布图的有效数据（坐标或 agb_kg 缺失）。")

    # 参考常见论文风格：高密度点避免 overplot，优先用 hexbin / 2D binning
    x = sub[x_col].to_numpy(dtype=float)
    y = sub[y_col].to_numpy(dtype=float)
    c = sub["agb_kg"].to_numpy(dtype=float)

    # 色标对数归一化更适合长尾（同时避免极端值把色标“拉死”）
    vmin, vmax = float(np.nanpercentile(c, 2)), float(np.nanpercentile(c, 98))
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin <= 0 or vmin >= vmax:
        vmin = float(np.nanmin(c[c > 0])) if np.any(c > 0) else 1e-6
        vmax = float(np.nanmax(c))
    norm = mpl_colors.LogNorm(vmin=max(vmin, 1e-6), vmax=max(vmax, vmin * 1.01))

    fig, ax = plt.subplots(figsize=(7.2, 6.2), dpi=220)
    hb = ax.hexbin(
        x,
        y,
        C=c,
        reduce_C_function=np.mean,
        gridsize=gridsize,
        cmap="viridis",
        norm=norm,
        mincnt=1,
        linewidths=0,
    )
    base_title = "Spatial distribution of AGB (hexbin mean, log color scale)"
    ax.set_title(f"{base_title} ({year_label})" if year_label else base_title)
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.set_aspect("equal" if "grid_" in x_col or "global_" in x_col else "auto")
    cb = fig.colorbar(hb, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("AGB (kg; mean per bin)")
    # 默认 LogNorm 色标会用 10^{x} 的 mathtext，可能触发 unicode minus 的字体缺字告警；
    # 这里改成纯数字刻度，便于跨字体/前端渲染一致。
    cb.formatter = mpl_ticker.FuncFormatter(lambda val, pos: f"{val:g}")
    cb.update_ticks()
    fig.tight_layout()
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)

    return PlotArtifact(
        title="AGB 空间分布图",
        mime="image/png",
        filename="agb_spatial_distribution.png",
        content_base64=content_b64,
    )


def render_agb_grid_distribution(
    grid_df: pd.DataFrame,
    *,
    year_label: str | None = None,
) -> PlotArtifact:
    """
    绘制 AGB 网格聚合图：
    - 以矢量网格（`cbl_80网格`）位置为准；
    - 用样地编号前三位（如 A0701 -> A07）匹配网格编号；
    - 对未匹配网格，使用已匹配网格的 AGB 结果做 IDW 插值补值。
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon

    _configure_matplotlib_fonts()

    required = ["grid_id", "agb_sum_kg"]
    for col in required:
        if col not in grid_df.columns:
            raise ValueError(f"网格分布图缺少字段: {col}")

    vector_df = _load_vector_grid_polygons()
    if len(vector_df) == 0:
        raise ValueError("未找到矢量网格图层（cbl_80网格/cbl_100网格），无法生成网格聚合图。")

    work = grid_df[["grid_id", "agb_sum_kg"]].copy()
    work["agb_sum_kg"] = pd.to_numeric(work["agb_sum_kg"], errors="coerce")
    work["grid_code"] = work["grid_id"].map(_extract_grid_prefix)
    work = work.dropna(subset=["grid_code"])
    if len(work) == 0:
        raise ValueError("当前网格数据无法提取样地编号前三位，无法匹配地图网格。")

    observed = work.groupby("grid_code", dropna=False)["agb_sum_kg"].sum(min_count=1).reset_index()
    observed = observed.rename(columns={"agb_sum_kg": "observed_agb_sum_kg"})
    map_df = vector_df.merge(observed, on="grid_code", how="left")
    map_df["agb_sum_kg"] = map_df["observed_agb_sum_kg"]
    map_df["value_source"] = np.where(map_df["agb_sum_kg"].notna(), "matched", "missing")

    # 对未匹配网格做 IDW 插值（使用矢量网格中心点作为距离计算坐标）
    known_mask = np.isfinite(pd.to_numeric(map_df["agb_sum_kg"], errors="coerce"))
    miss_mask = ~known_mask
    if miss_mask.any() and known_mask.any():
        known_xy = map_df.loc[known_mask, ["map_x", "map_y"]].to_numpy(dtype=float)
        known_val = map_df.loc[known_mask, "agb_sum_kg"].to_numpy(dtype=float)
        miss_xy = map_df.loc[miss_mask, ["map_x", "map_y"]].to_numpy(dtype=float)
        tree = cKDTree(known_xy)
        kk = int(min(max(8, 1), len(known_val)))
        dists, idxs = tree.query(miss_xy, k=kk, workers=-1)
        if kk == 1:
            dists = dists[:, None]
            idxs = idxs[:, None]
        eps = 1e-12
        w = 1.0 / np.maximum(dists, eps) ** 2.0
        vv = known_val[idxs]
        pred = np.sum(w * vv, axis=1) / np.sum(w, axis=1)
        has_zero = np.any(dists <= eps, axis=1)
        if np.any(has_zero):
            first_zero = np.argmax(dists <= eps, axis=1)
            pred[has_zero] = vv[np.arange(len(vv)), first_zero][has_zero]
        map_df.loc[miss_mask, "agb_sum_kg"] = pred
        map_df.loc[miss_mask, "value_source"] = "idw"

    vals = pd.to_numeric(map_df["agb_sum_kg"], errors="coerce").dropna().to_numpy(dtype=float)
    positive_vals = vals[vals > 0]
    if len(positive_vals) == 0:
        raise ValueError("没有可用于绘制网格图的有效 AGB 网格数据。")

    lvmin, lvmax = float(np.nanpercentile(positive_vals, 2)), float(np.nanpercentile(positive_vals, 98))
    if not np.isfinite(lvmin) or lvmin <= 0:
        lvmin = float(np.nanmin(positive_vals))
    if not np.isfinite(lvmax) or lvmax <= lvmin:
        lvmax = float(np.nanmax(positive_vals))
    norm = mpl_colors.LogNorm(vmin=max(lvmin, 1e-6), vmax=max(lvmax, max(lvmin, 1e-6) * 1.01))
    cmap = plt.get_cmap("viridis")

    fig, ax = plt.subplots(figsize=(10.2, 7.0), dpi=220)

    drawn_vals = []
    bounds_x: list[float] = []
    bounds_y: list[float] = []
    for r in map_df.itertuples(index=False):
        val = float(r.agb_sum_kg) if pd.notna(r.agb_sum_kg) else np.nan
        source = str(r.value_source)
        if np.isfinite(val) and val > 0:
            face = cmap(norm(val))
            alpha = 0.92 if source == "matched" else 0.80
            drawn_vals.append(val)
        else:
            face = "#f3f4f6"
            alpha = 0.55

        for part in r.parts:
            if len(part) < 3:
                continue
            poly = Polygon(
                part,
                closed=True,
                facecolor=face,
                edgecolor="#ef4444",
                linewidth=0.45,
                alpha=alpha,
                zorder=3,
            )
            ax.add_patch(poly)
            px = [p[0] for p in part]
            py = [p[1] for p in part]
            bounds_x.extend(px)
            bounds_y.extend(py)

        # 参考用户示例图：网格号标注在格网中心
        ax.text(
            float(r.map_x),
            float(r.map_y),
            str(r.grid_code),
            fontsize=6,
            color="#ea580c",
            ha="center",
            va="center",
            alpha=0.85,
            zorder=4,
        )

    base_title = "AGB grid aggregation map (vector layout + IDW fill)"
    ax.set_title(f"{base_title} ({year_label})" if year_label else base_title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    if bounds_x and bounds_y:
        xmin, xmax = min(bounds_x), max(bounds_x)
        ymin, ymax = min(bounds_y), max(bounds_y)
        dx = max((xmax - xmin) * 0.03, 1e-4)
        dy = max((ymax - ymin) * 0.03, 1e-4)
        ax.set_xlim(xmin - dx, xmax + dx)
        ax.set_ylim(ymin - dy, ymax + dy)
    ax.grid(False)

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array(np.array(drawn_vals if drawn_vals else vals))
    cb = fig.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("AGB sum per square grid (kg, log scale)")
    # 增加对数刻度密度，便于快速读取大概数值范围
    cb.locator = ticker.LogLocator(base=10.0, subs=(1.0, 2.0, 5.0), numticks=20)
    cb.formatter = mpl_ticker.FuncFormatter(lambda val, pos: f"{val:g}")
    cb.update_ticks()

    matched_n = int((map_df["value_source"] == "matched").sum())
    idw_n = int((map_df["value_source"] == "idw").sum())
    fig.text(
        0.02,
        0.01,
        f"Grid values: matched={matched_n}, IDW-filled={idw_n}",
        ha="left",
        va="bottom",
        fontsize=8,
        color="#374151",
    )

    fig.tight_layout()
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)

    return PlotArtifact(
        title="AGB 网格聚合图",
        mime="image/png",
        filename="agb_grid_aggregation_map.png",
        content_base64=content_b64,
    )


def render_grid_attribute_distribution(
    grid_df: pd.DataFrame,
    *,
    value_col: str,
    display_name: str,
    unit_label: str,
    year_label: str | None = None,
) -> PlotArtifact:
    """
    绘制通用网格属性聚合图（按网格均值）：
    - 样地编号前三位匹配矢量网格；
    - 未匹配网格用 IDW 插值补值。
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon

    _configure_matplotlib_fonts()

    required = ["grid_id", value_col]
    for col in required:
        if col not in grid_df.columns:
            raise ValueError(f"网格属性图缺少字段: {col}")

    vector_df = _load_vector_grid_polygons()
    if len(vector_df) == 0:
        raise ValueError("未找到矢量网格图层（cbl_80网格/cbl_100网格），无法生成网格聚合图。")

    work = grid_df[["grid_id", value_col]].copy()
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
    work["grid_code"] = work["grid_id"].map(_extract_grid_prefix)
    work = work.dropna(subset=["grid_code"])
    if len(work) == 0:
        raise ValueError("当前网格数据无法提取样地编号前三位，无法匹配地图网格。")

    observed = work.groupby("grid_code", dropna=False)[value_col].mean().reset_index()
    observed = observed.rename(columns={value_col: "observed_value"})
    map_df = vector_df.merge(observed, on="grid_code", how="left")
    map_df["value"] = map_df["observed_value"]
    map_df["value_source"] = np.where(map_df["value"].notna(), "matched", "missing")

    known_mask = np.isfinite(pd.to_numeric(map_df["value"], errors="coerce"))
    miss_mask = ~known_mask
    if miss_mask.any() and known_mask.any():
        known_xy = map_df.loc[known_mask, ["map_x", "map_y"]].to_numpy(dtype=float)
        known_val = map_df.loc[known_mask, "value"].to_numpy(dtype=float)
        miss_xy = map_df.loc[miss_mask, ["map_x", "map_y"]].to_numpy(dtype=float)
        tree = cKDTree(known_xy)
        kk = int(min(max(8, 1), len(known_val)))
        dists, idxs = tree.query(miss_xy, k=kk, workers=-1)
        if kk == 1:
            dists = dists[:, None]
            idxs = idxs[:, None]
        eps = 1e-12
        w = 1.0 / np.maximum(dists, eps) ** 2.0
        vv = known_val[idxs]
        pred = np.sum(w * vv, axis=1) / np.sum(w, axis=1)
        has_zero = np.any(dists <= eps, axis=1)
        if np.any(has_zero):
            first_zero = np.argmax(dists <= eps, axis=1)
            pred[has_zero] = vv[np.arange(len(vv)), first_zero][has_zero]
        map_df.loc[miss_mask, "value"] = pred
        map_df.loc[miss_mask, "value_source"] = "idw"

    vals = pd.to_numeric(map_df["value"], errors="coerce").dropna().to_numpy(dtype=float)
    if len(vals) == 0:
        raise ValueError(f"没有可用于绘制网格图的有效{display_name}数据。")
    vmin, vmax = float(np.nanpercentile(vals, 2)), float(np.nanpercentile(vals, 98))
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin >= vmax:
        vmin, vmax = float(np.nanmin(vals)), float(np.nanmax(vals))
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin >= vmax:
        vmin, vmax = vmin - 0.5, vmax + 0.5
    norm = mpl_colors.Normalize(vmin=vmin, vmax=vmax)
    cmap = plt.get_cmap("viridis")

    fig, ax = plt.subplots(figsize=(10.2, 7.0), dpi=220)
    drawn_vals = []
    bounds_x: list[float] = []
    bounds_y: list[float] = []
    for r in map_df.itertuples(index=False):
        val = float(r.value) if pd.notna(r.value) else np.nan
        source = str(r.value_source)
        if np.isfinite(val):
            face = cmap(norm(val))
            alpha = 0.92 if source == "matched" else 0.80
            drawn_vals.append(val)
        else:
            face = "#f3f4f6"
            alpha = 0.55

        for part in r.parts:
            if len(part) < 3:
                continue
            poly = Polygon(
                part,
                closed=True,
                facecolor=face,
                edgecolor="#ef4444",
                linewidth=0.45,
                alpha=alpha,
                zorder=3,
            )
            ax.add_patch(poly)
            px = [p[0] for p in part]
            py = [p[1] for p in part]
            bounds_x.extend(px)
            bounds_y.extend(py)

        ax.text(
            float(r.map_x),
            float(r.map_y),
            str(r.grid_code),
            fontsize=6,
            color="#ea580c",
            ha="center",
            va="center",
            alpha=0.85,
            zorder=4,
        )

    base_title = f"{display_name} grid aggregation map (mean by grid + IDW fill)"
    ax.set_title(f"{base_title} ({year_label})" if year_label else base_title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    if bounds_x and bounds_y:
        xmin, xmax = min(bounds_x), max(bounds_x)
        ymin, ymax = min(bounds_y), max(bounds_y)
        dx = max((xmax - xmin) * 0.03, 1e-4)
        dy = max((ymax - ymin) * 0.03, 1e-4)
        ax.set_xlim(xmin - dx, xmax + dx)
        ax.set_ylim(ymin - dy, ymax + dy)
    ax.grid(False)

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array(np.array(drawn_vals if drawn_vals else vals))
    cb = fig.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label(f"{display_name} mean ({unit_label})")
    cb.formatter = mpl_ticker.FuncFormatter(lambda val, pos: f"{val:g}")
    cb.update_ticks()

    matched_n = int((map_df["value_source"] == "matched").sum())
    idw_n = int((map_df["value_source"] == "idw").sum())
    fig.text(
        0.02,
        0.01,
        f"Grid values: matched={matched_n}, IDW-filled={idw_n}",
        ha="left",
        va="bottom",
        fontsize=8,
        color="#374151",
    )

    fig.tight_layout()
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)
    safe_name = re.sub(r"[^a-z0-9_]+", "_", display_name.lower()).strip("_")
    if not safe_name:
        safe_name = value_col
    return PlotArtifact(
        title=f"{display_name} 网格聚合图",
        mime="image/png",
        filename=f"{safe_name}_grid_aggregation_map.png",
        content_base64=content_b64,
    )


def render_grid_attribute_histogram(
    df: pd.DataFrame,
    *,
    value_col: str,
    display_name: str,
    unit_label: str,
    year_label: str | None = None,
) -> PlotArtifact:
    """绘制通用属性直方图，并标注均值与方差。"""
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts()

    valid = pd.to_numeric(df.get(value_col), errors="coerce").dropna()
    if len(valid) == 0:
        raise ValueError(f"没有可用于绘制直方图的有效{display_name}数据。")

    x = valid.to_numpy(dtype=float)
    bins = _freedman_diaconis_bins(x)

    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=220)
    ax.hist(
        x,
        bins=bins,
        color="#2c7fb8",
        edgecolor="white",
        linewidth=0.6,
        alpha=0.92,
    )
    base_title = f"Histogram of {display_name}"
    ax.set_title(f"{base_title} ({year_label})" if year_label else base_title)
    ax.set_xlabel(f"{display_name} ({unit_label})")
    ax.set_ylabel("Frequency")
    ax.grid(True, axis="y")

    mean_v = float(np.mean(x))
    var_v = float(np.var(x, ddof=1)) if len(x) > 1 else 0.0
    ax.axvline(mean_v, color="#d95f0e", linestyle="--", linewidth=1.2, label="Mean")
    ax.legend(frameon=False, fontsize=9)

    txt = f"n = {len(x)}\nmean = {mean_v:.3f} {unit_label}\nvariance = {var_v:.3f} {unit_label}^2"
    ax.text(
        0.98,
        0.98,
        txt,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#dddddd", alpha=0.95),
    )

    fig.tight_layout()
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)
    safe_name = re.sub(r"[^a-z0-9_]+", "_", display_name.lower()).strip("_")
    if not safe_name:
        safe_name = value_col
    return PlotArtifact(
        title=f"{display_name} 直方图",
        mime="image/png",
        filename=f"{safe_name}_histogram.png",
        content_base64=content_b64,
    )


def render_vegetation_type_grid_map(
    veg_df: pd.DataFrame,
    *,
    year_label: str | None = None,
) -> PlotArtifact:
    """绘制植被亚型网格分布图（分类着色，含图例）。"""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Polygon

    _configure_matplotlib_fonts()
    if veg_df is None or len(veg_df) == 0:
        raise ValueError("没有可用的植被类型分类数据。")
    if "grid_code" not in veg_df.columns or "vegetation_group" not in veg_df.columns:
        raise ValueError("植被类型网格图缺少字段（grid_code / vegetation_group）。")

    vector_df = _load_vector_grid_polygons()
    if len(vector_df) == 0:
        raise ValueError("未找到矢量网格图层（cbl_80网格/cbl_100网格）。")

    work = veg_df[["grid_code", "vegetation_group"]].copy()
    work["grid_code"] = work["grid_code"].astype(str).str.strip().str.upper()
    work["vegetation_group"] = work["vegetation_group"].astype(str).str.strip()
    map_df = vector_df.merge(work, on="grid_code", how="left")
    map_df["vegetation_group"] = map_df["vegetation_group"].where(map_df["vegetation_group"].notna(), "未分类")

    classes = sorted(map_df["vegetation_group"].dropna().astype(str).unique().tolist())
    cmap = plt.get_cmap("tab20", max(len(classes), 1))
    color_map = {c: cmap(i % cmap.N) for i, c in enumerate(classes)}

    fig, ax = plt.subplots(figsize=(10.5, 7.2), dpi=220)
    bounds_x: list[float] = []
    bounds_y: list[float] = []
    for r in map_df.itertuples(index=False):
        cls = str(r.vegetation_group)
        face = color_map.get(cls, "#d1d5db")
        for part in r.parts:
            if len(part) < 3:
                continue
            poly = Polygon(
                part,
                closed=True,
                facecolor=face,
                edgecolor="#ef4444",
                linewidth=0.45,
                alpha=0.92,
                zorder=2,
            )
            ax.add_patch(poly)
            bounds_x.extend([p[0] for p in part])
            bounds_y.extend([p[1] for p in part])

    title = "车八岭植被亚型网格分布图"
    ax.set_title(f"{title} ({year_label})" if year_label else title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    if bounds_x and bounds_y:
        xmin, xmax = min(bounds_x), max(bounds_x)
        ymin, ymax = min(bounds_y), max(bounds_y)
        dx = max((xmax - xmin) * 0.03, 1e-4)
        dy = max((ymax - ymin) * 0.03, 1e-4)
        ax.set_xlim(xmin - dx, xmax + dx)
        ax.set_ylim(ymin - dy, ymax + dy)
    ax.grid(False)

    legend_items = [Patch(facecolor=color_map[c], edgecolor="none", label=c) for c in classes]
    if legend_items:
        ax.legend(
            handles=legend_items,
            title="植被亚型名称",
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            frameon=True,
            fontsize=8,
        )

    fig.subplots_adjust(right=0.78)
    fig.tight_layout(rect=[0, 0, 0.78, 1])
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)
    return PlotArtifact(
        title="车八岭植被亚型网格分布图",
        mime="image/png",
        filename="vegetation_type_grid_map.png",
        content_base64=content_b64,
    )


def render_vegetation_type_attribute_bars(agg_df: pd.DataFrame) -> PlotArtifact:
    """
    绘制不同植被类型下多属性均值 bar 图（2x4 子图）。
    """
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts()
    if agg_df is None or len(agg_df) == 0:
        raise ValueError("没有可用于绘制植被类型属性 bar 图的数据。")
    if "vegetation_group" not in agg_df.columns:
        raise ValueError("缺少 vegetation_group 字段。")

    metric_meta = [
        ("height_m", "树高", "m"),
        ("dbh_m", "胸径", "m"),
        ("crown_diameter_m", "冠径", "m"),
        ("crown_ns_m", "南北冠径", "m"),
        ("crown_ew_m", "东西冠径", "m"),
        ("crown_area_m2", "冠幅面积", "m^2"),
        ("crown_volume_m3", "冠幅体积", "m^3"),
        ("clear_bole_height_m", "枝下高", "m"),
    ]
    present = [(c, n, u) for c, n, u in metric_meta if c in agg_df.columns]
    if not present:
        raise ValueError("植被类型属性 bar 图缺少可用指标列。")

    work = agg_df.copy()
    work["vegetation_group"] = work["vegetation_group"].astype(str)
    work = work.sort_values("vegetation_group")
    x_labels = work["vegetation_group"].tolist()
    xs = np.arange(len(x_labels))

    cmap = plt.get_cmap("tab20", max(len(x_labels), 1))
    bar_colors = [cmap(i % cmap.N) for i in range(len(x_labels))]

    fig, axes = plt.subplots(2, 4, figsize=(14.8, 8.6), dpi=220)
    axes_flat = axes.ravel()

    for ax, (col, name, unit) in zip(axes_flat, present):
        vals = pd.to_numeric(work[col], errors="coerce").to_numpy(dtype=float)
        vals = np.where(np.isfinite(vals), vals, np.nan)
        ax.bar(xs, vals, color=bar_colors, edgecolor="white", linewidth=0.5, alpha=0.93)
        ax.set_title(f"{name} 均值")
        ax.set_xticks(xs)
        ax.set_xticklabels(x_labels, rotation=35, ha="right", fontsize=8)
        ax.set_ylabel(unit)
        ax.grid(True, axis="y", alpha=0.2)

    # 清理未使用子图
    for ax in axes_flat[len(present):]:
        ax.axis("off")

    fig.suptitle("不同植被亚型的网格样地属性均值对比（bar）", fontsize=13, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)
    return PlotArtifact(
        title="不同植被亚型属性均值 bar 图",
        mime="image/png",
        filename="vegetation_type_attribute_bars.png",
        content_base64=content_b64,
    )


def render_dbh_method_comparison_scatter(compare_df: pd.DataFrame) -> PlotArtifact:
    """
    绘制样地层面的两种方法胸径对比散点图，并拟合线性相关。

    需要列：
    - dbh_seg_cm: 单木分割法胸径均值（cm）
    - dbh_monitor_mean_cm: 监测法（2016/2021 平均）胸径均值（cm）
    """
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts()
    req = {"dbh_seg_cm", "dbh_monitor_mean_cm"}
    if not req.issubset(set(compare_df.columns)):
        raise ValueError("胸径对比散点图缺少必要列。")

    work = compare_df[["dbh_seg_cm", "dbh_monitor_mean_cm"]].copy()
    work["dbh_seg_cm"] = pd.to_numeric(work["dbh_seg_cm"], errors="coerce")
    work["dbh_monitor_mean_cm"] = pd.to_numeric(work["dbh_monitor_mean_cm"], errors="coerce")
    work = work.dropna(subset=["dbh_seg_cm", "dbh_monitor_mean_cm"])
    if len(work) < 3:
        raise ValueError("可用于样地胸径对比的重叠样地过少（少于3个）。")

    x = work["dbh_seg_cm"].to_numpy(dtype=float)
    y = work["dbh_monitor_mean_cm"].to_numpy(dtype=float)

    # 线性拟合与相关性统计
    slope, intercept = np.polyfit(x, y, deg=1)
    y_hat = slope * x + intercept
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    if len(x) > 1 and float(np.std(x)) > 0 and float(np.std(y)) > 0:
        r = float(np.corrcoef(x, y)[0, 1])
    else:
        r = float("nan")

    fig, ax = plt.subplots(figsize=(7.2, 6.2), dpi=220)
    ax.scatter(x, y, s=26, alpha=0.82, color="#2c7fb8", edgecolors="white", linewidths=0.4, label="plot mean")

    # 拟合线
    xx = np.linspace(float(np.nanmin(x)), float(np.nanmax(x)), 120)
    yy = slope * xx + intercept
    ax.plot(xx, yy, color="#d95f0e", linewidth=1.5, label="Linear fit")

    # 1:1 参考线
    lo = float(min(np.nanmin(x), np.nanmin(y)))
    hi = float(max(np.nanmax(x), np.nanmax(y)))
    ax.plot([lo, hi], [lo, hi], color="#6b7280", linestyle="--", linewidth=1.0, label="1:1")

    ax.set_title("样地胸径对比散点图")
    ax.set_xlabel("20公顷单木分割法 DBH mean (cm)")
    ax.set_ylabel("监测法 DBH mean (2016/2021 avg, cm)")
    ax.grid(True, alpha=0.22, linestyle="--")
    ax.legend(frameon=False, fontsize=8)

    stat_txt = (
        f"n = {len(work)}\n"
        f"y = {slope:.3f}x + {intercept:.3f}\n"
        f"r = {r:.3f}\n"
        f"R^2 = {r2:.3f}"
    )
    ax.text(
        0.98,
        0.98,
        stat_txt,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#dddddd", alpha=0.95),
    )

    fig.tight_layout()
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)
    return PlotArtifact(
        title="样地胸径对比散点图",
        mime="image/png",
        filename="dbh_plot_comparison_scatter.png",
        content_base64=content_b64,
    )


def render_dbh_grid_comparison_scatter(compare_df: pd.DataFrame) -> PlotArtifact:
    """
    绘制网格层面的两种方法胸径对比散点图，并拟合线性相关。

    需要列：
    - dbh_seg_cm: 网格样地单木分割法胸径均值（cm）
    - dbh_grid_2022_cm: 网格调查法 DBH2022 网格均值（cm）
    """
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts()
    req = {"dbh_seg_cm", "dbh_grid_2022_cm"}
    if not req.issubset(set(compare_df.columns)):
        raise ValueError("网格胸径对比散点图缺少必要列。")

    work = compare_df[["dbh_seg_cm", "dbh_grid_2022_cm"]].copy()
    work["dbh_seg_cm"] = pd.to_numeric(work["dbh_seg_cm"], errors="coerce")
    work["dbh_grid_2022_cm"] = pd.to_numeric(work["dbh_grid_2022_cm"], errors="coerce")
    work = work.dropna(subset=["dbh_seg_cm", "dbh_grid_2022_cm"])
    if len(work) < 3:
        raise ValueError("可用于网格胸径对比的重叠网格过少（少于3个）。")

    x = work["dbh_seg_cm"].to_numpy(dtype=float)
    y = work["dbh_grid_2022_cm"].to_numpy(dtype=float)

    slope, intercept = np.polyfit(x, y, deg=1)
    y_hat = slope * x + intercept
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    r = float(np.corrcoef(x, y)[0, 1]) if len(x) > 1 else float("nan")

    fig, ax = plt.subplots(figsize=(7.2, 6.2), dpi=220)
    ax.scatter(x, y, s=28, alpha=0.84, color="#2c7fb8", edgecolors="white", linewidths=0.4, label="grid mean")

    xx = np.linspace(float(np.nanmin(x)), float(np.nanmax(x)), 120)
    yy = slope * xx + intercept
    ax.plot(xx, yy, color="#d95f0e", linewidth=1.5, label="Linear fit")

    lo = float(min(np.nanmin(x), np.nanmin(y)))
    hi = float(max(np.nanmax(x), np.nanmax(y)))
    ax.plot([lo, hi], [lo, hi], color="#6b7280", linestyle="--", linewidth=1.0, label="1:1")

    ax.set_title("网格胸径对比散点图（两种方法）")
    ax.set_xlabel("网格样地单木分割法 DBH mean (cm)")
    ax.set_ylabel("网格调查法 DBH2022 mean (cm)")
    ax.grid(True, alpha=0.22, linestyle="--")
    ax.legend(frameon=False, fontsize=8)

    stat_txt = (
        f"n = {len(work)}\n"
        f"y = {slope:.3f}x + {intercept:.3f}\n"
        f"r = {r:.3f}\n"
        f"R^2 = {r2:.3f}"
    )
    ax.text(
        0.98,
        0.98,
        stat_txt,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#dddddd", alpha=0.95),
    )

    fig.tight_layout()
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)
    return PlotArtifact(
        title="网格胸径对比散点图",
        mime="image/png",
        filename="dbh_grid_comparison_scatter.png",
        content_base64=content_b64,
    )


def render_dbh_model_tree_comparison_scatter(compare_df: pd.DataFrame) -> PlotArtifact:
    """
    绘制“建模每木”层面的胸径对比散点图（监测 tag 对应分割单木）。

    需要列：
    - dbh_seg_cm: 单木分割法胸径（cm）
    - dbh_monitor_cm: 监测数据胸径（cm）
    """
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts()
    req = {"dbh_seg_cm", "dbh_monitor_cm"}
    if not req.issubset(set(compare_df.columns)):
        raise ValueError("建模每木胸径对比散点图缺少必要列。")

    work = compare_df[["dbh_seg_cm", "dbh_monitor_cm"]].copy()
    work["dbh_seg_cm"] = pd.to_numeric(work["dbh_seg_cm"], errors="coerce")
    work["dbh_monitor_cm"] = pd.to_numeric(work["dbh_monitor_cm"], errors="coerce")
    work = work.dropna(subset=["dbh_seg_cm", "dbh_monitor_cm"])
    if len(work) < 3:
        raise ValueError("可用于建模每木胸径对比的重叠样本过少（少于3个）。")

    x = work["dbh_seg_cm"].to_numpy(dtype=float)
    y = work["dbh_monitor_cm"].to_numpy(dtype=float)

    slope, intercept = np.polyfit(x, y, deg=1)
    y_hat = slope * x + intercept
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    r = float(np.corrcoef(x, y)[0, 1]) if len(x) > 1 else float("nan")

    fig, ax = plt.subplots(figsize=(7.2, 6.2), dpi=220)
    ax.scatter(x, y, s=24, alpha=0.80, color="#2c7fb8", edgecolors="white", linewidths=0.35, label="per-tree pair")

    xx = np.linspace(float(np.nanmin(x)), float(np.nanmax(x)), 120)
    yy = slope * xx + intercept
    ax.plot(xx, yy, color="#d95f0e", linewidth=1.5, label="Linear fit")

    lo = float(min(np.nanmin(x), np.nanmin(y)))
    hi = float(max(np.nanmax(x), np.nanmax(y)))
    ax.plot([lo, hi], [lo, hi], color="#6b7280", linestyle="--", linewidth=1.0, label="1:1")

    ax.set_title("大样地建模每木胸径对比散点图")
    ax.set_xlabel("20公顷单木分割法 DBH (cm)")
    ax.set_ylabel("20公顷监测法 DBH (cm)")
    ax.grid(True, alpha=0.22, linestyle="--")
    ax.legend(frameon=False, fontsize=8)

    stat_txt = (
        f"n = {len(work)}\n"
        f"y = {slope:.3f}x + {intercept:.3f}\n"
        f"r = {r:.3f}\n"
        f"R^2 = {r2:.3f}"
    )
    ax.text(
        0.98,
        0.98,
        stat_txt,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#dddddd", alpha=0.95),
    )

    fig.tight_layout()
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)
    return PlotArtifact(
        title="大样地建模每木胸径对比散点图",
        mime="image/png",
        filename="dbh_model_tree_comparison_scatter.png",
        content_base64=content_b64,
    )


def render_grid_relation_scatter(
    compare_df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    title: str,
    x_label: str,
    y_label: str,
    filename: str,
    x_lim: tuple[float, float] | None = None,
    show_identity_line: bool = False,
) -> PlotArtifact:
    """
    绘制20m网格层面的通用关系散点图（含线性拟合与1:1参考线）。
    """
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts()
    req = {x_col, y_col}
    if not req.issubset(set(compare_df.columns)):
        raise ValueError(f"关系散点图缺少必要列：{req}")

    work = compare_df[[x_col, y_col]].copy()
    work[x_col] = pd.to_numeric(work[x_col], errors="coerce")
    work[y_col] = pd.to_numeric(work[y_col], errors="coerce")
    work = work.dropna(subset=[x_col, y_col])
    if len(work) < 3:
        raise ValueError("可用于关系散点图的有效网格样本过少（少于3个）。")

    x = work[x_col].to_numpy(dtype=float)
    y = work[y_col].to_numpy(dtype=float)

    slope, intercept = np.polyfit(x, y, deg=1)
    y_hat = slope * x + intercept
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    if len(x) > 1 and float(np.std(x)) > 0 and float(np.std(y)) > 0:
        r = float(np.corrcoef(x, y)[0, 1])
    else:
        r = float("nan")

    fig, ax = plt.subplots(figsize=(7.2, 6.2), dpi=220)
    ax.scatter(x, y, s=28, alpha=0.84, color="#2c7fb8", edgecolors="white", linewidths=0.4, label="20m grid")

    xx = np.linspace(float(np.nanmin(x)), float(np.nanmax(x)), 120)
    yy = slope * xx + intercept
    ax.plot(xx, yy, color="#d95f0e", linewidth=1.5, label="Linear fit")

    if show_identity_line:
        lo = float(min(np.nanmin(x), np.nanmin(y)))
        hi = float(max(np.nanmax(x), np.nanmax(y)))
        ax.plot([lo, hi], [lo, hi], color="#6b7280", linestyle="--", linewidth=1.0, label="1:1")

    if x_lim is not None:
        xmin, xmax = float(x_lim[0]), float(x_lim[1])
        if xmin < xmax:
            ax.set_xlim(xmin, xmax)

    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.grid(True, alpha=0.22, linestyle="--")
    ax.legend(frameon=False, fontsize=8)

    stat_txt = (
        f"n = {len(work)}\n"
        f"y = {slope:.3f}x + {intercept:.3f}\n"
        f"r = {r:.3f}\n"
        f"R^2 = {r2:.3f}"
    )
    ax.text(
        0.98,
        0.98,
        stat_txt,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#dddddd", alpha=0.95),
    )

    fig.tight_layout()
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)
    return PlotArtifact(
        title=title,
        mime="image/png",
        filename=filename,
        content_base64=content_b64,
    )


def render_agb_interpolation_20m(
    df: pd.DataFrame,
    *,
    cell_size_m: float = 20.0,
    k: int = 12,
    power: float = 2.0,
    max_points: int = 12000,
    year_label: str | None = None,
) -> PlotArtifact:
    """
    生成 AGB 空间插值图（20m 网格）。

    方法：IDW（Inverse Distance Weighting），用 KDTree 做 kNN 加速。
    - 以 global_x/global_y 作为平面坐标（单位按你的数据定义，默认按米理解）
    - 在规则网格（20m）上插值出 AGB 面场
    """
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts()

    if "global_x" not in df.columns or "global_y" not in df.columns:
        raise ValueError("缺少 global_x/global_y，无法进行 20m 空间插值。")

    sub = df[["global_x", "global_y", "agb_kg"]].copy()
    sub["agb_kg"] = pd.to_numeric(sub["agb_kg"], errors="coerce")
    sub["global_x"] = pd.to_numeric(sub["global_x"], errors="coerce")
    sub["global_y"] = pd.to_numeric(sub["global_y"], errors="coerce")
    sub = sub.dropna(subset=["global_x", "global_y", "agb_kg"])
    sub = sub[sub["agb_kg"] > 0]
    if len(sub) > max_points:
        sub = sub.sample(n=max_points, random_state=42)

    if len(sub) < 5:
        raise ValueError("有效 AGB 点位过少，无法稳定生成插值图。")

    x = sub["global_x"].to_numpy(dtype=float)
    y = sub["global_y"].to_numpy(dtype=float)
    v = sub["agb_kg"].to_numpy(dtype=float)

    # 构建 20m 规则网格（覆盖数据范围）
    xmin, xmax = float(np.min(x)), float(np.max(x))
    ymin, ymax = float(np.min(y)), float(np.max(y))

    # 对齐到 cell_size 的格网边界
    xmin_g = np.floor(xmin / cell_size_m) * cell_size_m
    xmax_g = np.ceil(xmax / cell_size_m) * cell_size_m
    ymin_g = np.floor(ymin / cell_size_m) * cell_size_m
    ymax_g = np.ceil(ymax / cell_size_m) * cell_size_m

    xs = np.arange(xmin_g, xmax_g + cell_size_m, cell_size_m)
    ys = np.arange(ymin_g, ymax_g + cell_size_m, cell_size_m)
    X, Y = np.meshgrid(xs, ys)
    grid_points = np.column_stack([X.ravel(), Y.ravel()])

    # kNN + IDW
    tree = cKDTree(np.column_stack([x, y]))
    kk = int(min(max(k, 3), len(v)))
    dists, idxs = tree.query(grid_points, k=kk, workers=-1)

    # 保证维度一致（k=1 时 scipy 返回 1D）
    if kk == 1:
        dists = dists[:, None]
        idxs = idxs[:, None]

    # 避免距离为 0 的点导致除 0：距离为 0 直接取该点值
    eps = 1e-12
    w = 1.0 / np.maximum(dists, eps) ** power
    vv = v[idxs]

    # 若某网格点正好落在样点位置（dist=0），用该样点值覆盖
    has_zero = np.any(dists <= eps, axis=1)
    interp = np.sum(w * vv, axis=1) / np.sum(w, axis=1)
    if np.any(has_zero):
        first_zero = np.argmax(dists <= eps, axis=1)
        interp[has_zero] = vv[np.arange(len(vv)), first_zero][has_zero]

    Z = interp.reshape(Y.shape)

    # 论文里常见做法：裁剪到采样点的凸包范围，避免在无数据支撑区域外推
    tri = Delaunay(np.column_stack([x, y]))
    inside = tri.find_simplex(grid_points) >= 0
    Z_flat = Z.ravel()
    Z_flat[~inside] = np.nan
    Z = Z_flat.reshape(Z.shape)

    # 可视化：论文里常见用 log 色标 + 分位截断
    vmin, vmax = float(np.nanpercentile(v, 2)), float(np.nanpercentile(v, 98))
    norm = mpl_colors.LogNorm(vmin=max(vmin, 1e-6), vmax=max(vmax, vmin * 1.01))

    fig, ax = plt.subplots(figsize=(7.2, 6.2), dpi=220)

    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad(color="white")  # 无数据区域白底，接近论文里的“研究区外为空白”

    im = ax.imshow(
        Z,
        origin="lower",
        extent=[xs.min(), xs.max(), ys.min(), ys.max()],
        cmap=cmap,
        norm=norm,
        aspect="equal",
        interpolation="nearest",
    )

    # 按前端展示需求，保持插值图简洁：不叠加采样点和等值线。

    base_title = f"AGB spatial interpolation (IDW, {int(cell_size_m)} m grid)"
    ax.set_title(f"{base_title} ({year_label})" if year_label else base_title)
    ax.set_xlabel("global_x")
    ax.set_ylabel("global_y")

    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("AGB (kg; interpolated)")
    cb.formatter = mpl_ticker.FuncFormatter(lambda val, pos: f"{val:g}")
    cb.update_ticks()

    # 保留指北针，放图外空白处避免遮挡图面。
    nax = fig.add_axes([0.935, 0.82, 0.04, 0.10])
    nax.annotate(
        "N",
        xy=(0.5, 0.78),
        xytext=(0.5, 0.40),
        xycoords="axes fraction",
        textcoords="axes fraction",
        ha="center",
        va="center",
        fontsize=9,
        arrowprops=dict(arrowstyle="-|>", lw=0.7, color="#111827"),
    )
    nax.axis("off")

    fig.subplots_adjust(left=0.10, right=0.92, top=0.92, bottom=0.10)
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)

    return PlotArtifact(
        title="AGB 空间插值图（20m）",
        mime="image/png",
        filename="agb_interpolation_20m.png",
        content_base64=content_b64,
    )


# 结构复杂度 20m 网格分布图：与常见林分结构/遥感制图论文一致（栅格面 + 色标 + 等值线 + 北向 + 图注）
_SC_METRIC_META = {
    "dbh_cv": {
        "title_en": "Structural complexity: CV(DBH) (20 m grid)",
        "cbar": "CV(DBH)",
        "title_zh": "结构复杂度-胸径变异系数（20m网格）",
    },
    "height_cv": {
        "title_en": "Structural complexity: CV(height) (20 m grid)",
        "cbar": "CV(height)",
        "title_zh": "结构复杂度-树高变异系数（20m网格）",
    },
    "species_shannon_norm": {
        "title_en": "Structural complexity: normalized Shannon diversity (20 m grid)",
        "cbar": "Shannon (norm.)",
        "title_zh": "结构复杂度-物种多样性 Shannon（归一化，20m网格）",
    },
    "vertical_entropy_norm": {
        "title_en": "Structural complexity: vertical structure entropy (norm., 20 m grid)",
        "cbar": "Vertical entropy (norm.)",
        "title_zh": "结构复杂度-垂直分层熵（归一化，20m网格）",
    },
    "score": {
        "title_en": "Structural complexity: composite score (20 m grid)",
        "cbar": "Composite score (0-1)",
        "title_zh": "结构复杂度-综合得分（20m网格）",
    },
}


def render_structural_complexity_grid_map(
    grid_df: pd.DataFrame,
    component: str,
    year_label: str | None = None,
) -> PlotArtifact:
    """
    绘制结构复杂度指标在 20m 网格上的空间分布图。

    输入需为网格聚合结果（含 `grid_x_20m/grid_y_20m` 和指标列）。
    """
    import matplotlib.pyplot as plt

    if component not in _SC_METRIC_META:
        raise ValueError(f"未知指标: {component}")

    _configure_matplotlib_fonts()

    if grid_df is None or len(grid_df) == 0:
        raise ValueError("没有可用的 20m 网格结构复杂度数据（样本过少或缺少网格字段）。")

    col = component
    if col not in grid_df.columns:
        raise ValueError(f"聚合结果中缺少列: {col}")

    gx_raw = pd.to_numeric(grid_df["grid_x_20m"], errors="coerce").dropna()
    gy_raw = pd.to_numeric(grid_df["grid_y_20m"], errors="coerce").dropna()
    if len(gx_raw) == 0 or len(gy_raw) == 0:
        raise ValueError("网格坐标为空。")
    gx_idx = np.arange(int(np.floor(gx_raw.min())), int(np.ceil(gx_raw.max())) + 1, dtype=int)
    gy_idx = np.arange(int(np.floor(gy_raw.min())), int(np.ceil(gy_raw.max())) + 1, dtype=int)
    if len(gx_idx) == 0 or len(gy_idx) == 0:
        raise ValueError("网格坐标范围为空。")

    ix = {int(v): i for i, v in enumerate(gx_idx)}
    iy = {int(v): i for i, v in enumerate(gy_idx)}
    Z = np.full((len(gy_idx), len(gx_idx)), np.nan, dtype=float)

    for row in grid_df.itertuples(index=False):
        gx_v = int(float(row.grid_x_20m))
        gy_v = int(float(row.grid_y_20m))
        val = getattr(row, col, None)
        if val is None or (isinstance(val, float) and not np.isfinite(val)):
            continue
        if gx_v in ix and gy_v in iy:
            Z[iy[gy_v], ix[gx_v]] = float(val)

    vals = Z[np.isfinite(Z)]
    if len(vals) == 0:
        raise ValueError(f"指标 {col} 在网格上无有效值。")

    meta = _SC_METRIC_META[component]

    fig, ax = plt.subplots(figsize=(7.4, 6.2), dpi=220)
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad(color="white")

    # 使用与 AGB 空间图一致的整体坐标系（单位：m），每像元对应 20m 网格。
    cell_size_m = 20.0
    extent = [
        float(gx_idx.min() * cell_size_m),
        float((gx_idx.max() + 1) * cell_size_m),
        float(gy_idx.min() * cell_size_m),
        float((gy_idx.max() + 1) * cell_size_m),
    ]

    vmin, vmax = float(np.nanpercentile(vals, 2)), float(np.nanpercentile(vals, 98))
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin >= vmax:
        vmin, vmax = float(np.nanmin(vals)), float(np.nanmax(vals))

    im = ax.imshow(
        Z,
        origin="lower",
        extent=extent,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        aspect="equal",
        interpolation="nearest",
    )

    # 保持图面简洁：不叠加等值线，避免出现不必要的线条。

    ax.set_title(f"{meta['title_en']} ({year_label})" if year_label else meta["title_en"])
    ax.set_xlabel("global_x (m)")
    ax.set_ylabel("global_y (m)")

    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label(meta["cbar"])
    cb.formatter = mpl_ticker.FuncFormatter(lambda val, pos: f"{val:g}")
    cb.update_ticks()

    # 指北针放到图外右上角空白区，避免遮挡格网内容。
    nax = fig.add_axes([0.935, 0.82, 0.04, 0.10])
    nax.annotate(
        "N",
        xy=(0.5, 0.78),
        xytext=(0.5, 0.40),
        xycoords="axes fraction",
        textcoords="axes fraction",
        ha="center",
        va="center",
        fontsize=9,
        arrowprops=dict(arrowstyle="-|>", lw=0.7, color="#111827"),
    )
    nax.axis("off")

    # 将网格大小注释放在图外左下空白处，避免压在图面上。
    fig.text(
        0.02,
        0.01,
        "Grid size: 20 m x 20 m",
        ha="left",
        va="bottom",
        fontsize=8,
        color="#444444",
    )
    fig.subplots_adjust(left=0.10, right=0.90, top=0.92, bottom=0.10)
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)

    safe_name = f"sc_{component}_20m_grid.png"
    return PlotArtifact(
        title=meta["title_zh"],
        mime="image/png",
        filename=safe_name,
        content_base64=content_b64,
    )


def render_agb_histogram_two_years(
    df: pd.DataFrame,
    col_2016: str = "agb_2016_kg",
    col_2021: str = "agb_2021_kg",
    *,
    x_scale: str = "log10",
) -> PlotArtifact:
    """绘制 2016/2021 双年份 AGB 直方图对比图。"""
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts()

    v16 = pd.to_numeric(df.get(col_2016), errors="coerce").dropna()
    v21 = pd.to_numeric(df.get(col_2021), errors="coerce").dropna()
    if len(v16) == 0 and len(v21) == 0:
        raise ValueError("两年均无可用于绘图的 AGB 数据。")

    if x_scale == "log10":
        x16 = np.log10(v16[v16 > 0].to_numpy(dtype=float)) if len(v16) else np.array([])
        x21 = np.log10(v21[v21 > 0].to_numpy(dtype=float)) if len(v21) else np.array([])
        xlabel = "log10(AGB) (kg)"
        title = "Histogram of AGB (2016 vs 2021, log10 scale)"
    else:
        x16 = v16.to_numpy(dtype=float)
        x21 = v21.to_numpy(dtype=float)
        xlabel = "AGB (kg)"
        title = "Histogram of AGB (2016 vs 2021)"

    all_x = np.concatenate([x16, x21]) if len(x16) and len(x21) else (x16 if len(x16) else x21)
    bins = _freedman_diaconis_bins(all_x)

    fig, ax = plt.subplots(figsize=(8.2, 5.0), dpi=220)
    if len(x16):
        ax.hist(x16, bins=bins, alpha=0.45, color="#3182bd", edgecolor="white", linewidth=0.5, label="2016")
    if len(x21):
        ax.hist(x21, bins=bins, alpha=0.45, color="#e6550d", edgecolor="white", linewidth=0.5, label="2021")

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Frequency")
    ax.grid(True, axis="y")
    ax.legend(frameon=False)
    fig.tight_layout()

    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)
    return PlotArtifact(
        title="AGB 两年对比直方图（2016 vs 2021）",
        mime="image/png",
        filename="agb_histogram_2016_2021.png",
        content_base64=content_b64,
    )


def render_agb_spatial_distribution_two_years(
    df: pd.DataFrame,
    col_2016: str = "agb_2016_kg",
    col_2021: str = "agb_2021_kg",
    *,
    gridsize: int = 60,
) -> PlotArtifact:
    """绘制 2016/2021 双年份 AGB 空间分布对比图。"""
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts()
    x_col, y_col = _pick_xy_columns(df)
    if not x_col or not y_col:
        raise ValueError("缺少空间坐标字段，无法生成两年空间分布图。")

    sub = df[[x_col, y_col, col_2016, col_2021]].copy()
    sub[col_2016] = pd.to_numeric(sub[col_2016], errors="coerce")
    sub[col_2021] = pd.to_numeric(sub[col_2021], errors="coerce")
    sub[x_col] = pd.to_numeric(sub[x_col], errors="coerce")
    sub[y_col] = pd.to_numeric(sub[y_col], errors="coerce")
    sub = sub.dropna(subset=[x_col, y_col], how="any")

    c_all = np.concatenate(
        [
            sub[col_2016].dropna().to_numpy(dtype=float),
            sub[col_2021].dropna().to_numpy(dtype=float),
        ]
    )
    c_all = c_all[c_all > 0]
    if len(c_all) == 0:
        raise ValueError("两年均无有效 AGB 数值。")

    vmin, vmax = float(np.nanpercentile(c_all, 2)), float(np.nanpercentile(c_all, 98))
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin <= 0 or vmin >= vmax:
        vmin = float(np.nanmin(c_all))
        vmax = float(np.nanmax(c_all))
    norm = mpl_colors.LogNorm(vmin=max(vmin, 1e-6), vmax=max(vmax, vmin * 1.01))

    fig, axes = plt.subplots(1, 2, figsize=(11.6, 5.3), dpi=220, sharex=True, sharey=True)
    hb_ref = None
    for ax, col, year in zip(axes, [col_2016, col_2021], ["2016", "2021"]):
        sub_y = sub.dropna(subset=[col]).copy()
        if len(sub_y) == 0:
            ax.text(0.5, 0.5, f"{year}: no data", transform=ax.transAxes, ha="center", va="center")
            ax.set_title(f"AGB spatial distribution ({year})")
            continue
        hb = ax.hexbin(
            sub_y[x_col].to_numpy(dtype=float),
            sub_y[y_col].to_numpy(dtype=float),
            C=sub_y[col].to_numpy(dtype=float),
            reduce_C_function=np.mean,
            gridsize=gridsize,
            cmap="viridis",
            norm=norm,
            mincnt=1,
            linewidths=0,
        )
        if hb_ref is None:
            hb_ref = hb
        ax.set_title(f"AGB spatial distribution ({year})")
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.set_aspect("equal" if "grid_" in x_col or "global_" in x_col else "auto")

    if hb_ref is not None:
        cb = fig.colorbar(hb_ref, ax=axes.ravel().tolist(), fraction=0.028, pad=0.03)
        cb.set_label("AGB (kg; mean per bin)")
        cb.formatter = mpl_ticker.FuncFormatter(lambda val, pos: f"{val:g}")
        cb.update_ticks()

    fig.tight_layout()
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)
    return PlotArtifact(
        title="AGB 两年空间分布图（2016 vs 2021）",
        mime="image/png",
        filename="agb_spatial_distribution_2016_2021.png",
        content_base64=content_b64,
    )


def render_agb_interpolation_20m_two_years(
    df: pd.DataFrame,
    col_2016: str = "agb_2016_kg",
    col_2021: str = "agb_2021_kg",
    *,
    cell_size_m: float = 20.0,
    max_points: int = 12000,
) -> PlotArtifact:
    """绘制 2016/2021 双年份 AGB 20m IDW 插值对比图。"""
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts()
    if "global_x" not in df.columns or "global_y" not in df.columns:
        raise ValueError("缺少 global_x/global_y，无法生成两年插值图。")

    def _surface(value_col: str):
        """为指定年份列计算 IDW 插值面。"""
        sub = df[["global_x", "global_y", value_col]].copy()
        sub["global_x"] = pd.to_numeric(sub["global_x"], errors="coerce")
        sub["global_y"] = pd.to_numeric(sub["global_y"], errors="coerce")
        sub[value_col] = pd.to_numeric(sub[value_col], errors="coerce")
        sub = sub.dropna(subset=["global_x", "global_y", value_col])
        sub = sub[sub[value_col] > 0]
        if len(sub) > max_points:
            sub = sub.sample(n=max_points, random_state=42)
        if len(sub) < 5:
            return None

        x = sub["global_x"].to_numpy(dtype=float)
        y = sub["global_y"].to_numpy(dtype=float)
        v = sub[value_col].to_numpy(dtype=float)
        xmin, xmax = float(np.min(x)), float(np.max(x))
        ymin, ymax = float(np.min(y)), float(np.max(y))
        xmin_g = np.floor(xmin / cell_size_m) * cell_size_m
        xmax_g = np.ceil(xmax / cell_size_m) * cell_size_m
        ymin_g = np.floor(ymin / cell_size_m) * cell_size_m
        ymax_g = np.ceil(ymax / cell_size_m) * cell_size_m
        xs = np.arange(xmin_g, xmax_g + cell_size_m, cell_size_m)
        ys = np.arange(ymin_g, ymax_g + cell_size_m, cell_size_m)
        X, Y = np.meshgrid(xs, ys)
        grid_points = np.column_stack([X.ravel(), Y.ravel()])

        tree = cKDTree(np.column_stack([x, y]))
        kk = int(min(max(12, 3), len(v)))
        dists, idxs = tree.query(grid_points, k=kk, workers=-1)
        if kk == 1:
            dists = dists[:, None]
            idxs = idxs[:, None]
        eps = 1e-12
        w = 1.0 / np.maximum(dists, eps) ** 2.0
        vv = v[idxs]
        z = np.sum(w * vv, axis=1) / np.sum(w, axis=1)
        Z = z.reshape(Y.shape)

        tri = Delaunay(np.column_stack([x, y]))
        inside = tri.find_simplex(grid_points) >= 0
        Z_flat = Z.ravel()
        Z_flat[~inside] = np.nan
        Z = Z_flat.reshape(Z.shape)
        return xs, ys, X, Y, Z, v

    s16 = _surface(col_2016)
    s21 = _surface(col_2021)
    if s16 is None and s21 is None:
        raise ValueError("两年均无足够点位生成插值图。")

    vals = []
    if s16 is not None:
        vals.append(s16[-1])
    if s21 is not None:
        vals.append(s21[-1])
    all_v = np.concatenate(vals)
    vmin, vmax = float(np.nanpercentile(all_v, 2)), float(np.nanpercentile(all_v, 98))
    norm = mpl_colors.LogNorm(vmin=max(vmin, 1e-6), vmax=max(vmax, vmin * 1.01))

    fig, axes = plt.subplots(1, 2, figsize=(11.6, 5.3), dpi=220, sharex=False, sharey=False)
    im_ref = None
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad(color="white")

    for ax, surf, year in zip(axes, [s16, s21], ["2016", "2021"]):
        if surf is None:
            ax.text(0.5, 0.5, f"{year}: no data", transform=ax.transAxes, ha="center", va="center")
            ax.set_title(f"AGB interpolation ({year}, IDW 20m)")
            continue
        xs, ys, X, Y, Z, _ = surf
        im = ax.imshow(
            Z,
            origin="lower",
            extent=[xs.min(), xs.max(), ys.min(), ys.max()],
            cmap=cmap,
            norm=norm,
            aspect="equal",
            interpolation="nearest",
        )
        if im_ref is None:
            im_ref = im
        ax.set_title(f"AGB interpolation ({year}, IDW 20m)")
        ax.set_xlabel("global_x")
        ax.set_ylabel("global_y")

    if im_ref is not None:
        cb = fig.colorbar(im_ref, ax=axes.ravel().tolist(), fraction=0.028, pad=0.03)
        cb.set_label("AGB (kg; interpolated)")
        cb.formatter = mpl_ticker.FuncFormatter(lambda val, pos: f"{val:g}")
        cb.update_ticks()

    fig.tight_layout()
    content_b64 = _fig_to_base64_png(fig)
    plt.close(fig)
    return PlotArtifact(
        title="AGB 两年空间插值图（2016 vs 2021）",
        mime="image/png",
        filename="agb_interpolation_2016_2021.png",
        content_base64=content_b64,
    )
