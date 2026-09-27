"""Training pipeline for the unified species-aware DBH growth model."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import psycopg
from catboost import CatBoostRegressor
from scipy.spatial import cKDTree  # pyright: ignore[reportAttributeAccessIssue]
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold

from .model_store import METADATA_PATH, MODEL_DIR, MODEL_PATH


FEATURE_COLUMNS = [
    "species",
    "dbh_m",
    "elevation_m",
    "tree_position_x_m",
    "tree_position_y_m",
    "neighbor_count_10m",
    "neighbor_basal_area_m2_10m",
    "hegyi_index_10m",
]
CATEGORICAL_FEATURES = ["species"]
GROUP_COLUMN = "plot_id"
TARGET_COLUMN = "annual_dbh_growth_m"


def load_growth_data() -> pd.DataFrame:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    query = """
        SELECT
            t.tree_id,
            t.species,
            t.plot_id,
            t.tree_position_x_m,
            t.tree_position_y_m,
            t.elevation_m,
            max(m.dbh_m) FILTER (WHERE m.measurement_year = 2016) AS dbh_m_2016,
            max(m.dbh_m) FILTER (WHERE m.measurement_year = 2021) AS dbh_m_2021
        FROM public.trees t
        JOIN public.tree_measurements m USING (tree_id)
        GROUP BY t.tree_id, t.species, t.plot_id, t.tree_position_x_m,
                 t.tree_position_y_m, t.elevation_m
        ORDER BY t.tree_id
    """
    with psycopg.connect(database_url) as connection:
        cursor = connection.execute(query)
        rows = cursor.fetchall()
        description = cursor.description
        if description is None:
            raise RuntimeError("PostgreSQL did not return growth columns")
        columns = [column.name for column in description]
    frame = pd.DataFrame(rows, columns=columns)
    frame = frame.dropna(subset=["dbh_m_2016", "dbh_m_2021", "species", "plot_id"])
    frame = frame[(frame["dbh_m_2016"] > 0) & (frame["dbh_m_2021"] > 0)].reset_index(drop=True)
    return frame


def add_competition_features(frame: pd.DataFrame, dbh_column: str) -> pd.DataFrame:
    result = frame.copy()
    coordinates = result[["tree_position_x_m", "tree_position_y_m"]].to_numpy(dtype=float)
    dbh = result[dbh_column].to_numpy(dtype=float)
    neighborhoods = cKDTree(coordinates).query_ball_point(coordinates, r=10.0)
    counts = np.zeros(len(result), dtype=float)
    basal_areas = np.zeros(len(result), dtype=float)
    hegyi = np.zeros(len(result), dtype=float)
    for index, neighbors in enumerate(neighborhoods):
        neighbors = [other for other in neighbors if other != index]
        if not neighbors:
            continue
        neighbor_indices = np.asarray(neighbors, dtype=int)
        distances = np.linalg.norm(coordinates[neighbor_indices] - coordinates[index], axis=1)
        distances = np.maximum(distances, 0.1)
        neighbor_dbh = dbh[neighbor_indices]
        counts[index] = len(neighbor_indices)
        basal_areas[index] = np.sum(np.pi * np.square(neighbor_dbh) / 4.0)
        hegyi[index] = np.sum((neighbor_dbh / dbh[index]) / distances)
    result["neighbor_count_10m"] = counts
    result["neighbor_basal_area_m2_10m"] = basal_areas
    result["hegyi_index_10m"] = hegyi
    result["dbh_m"] = result[dbh_column]
    return result


def model_parameters(seed: int) -> dict:
    return {
        "iterations": 500,
        "depth": 6,
        "learning_rate": 0.04,
        "loss_function": "RMSE",
        "l2_leaf_reg": 5.0,
        "random_seed": seed,
        "verbose": False,
        "allow_writing_files": False,
        "thread_count": -1,
    }


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    return {
        "mae_m_per_year": float(mean_absolute_error(actual, predicted)),
        "rmse_m_per_year": float(np.sqrt(mean_squared_error(actual, predicted))),
        "r2": float(r2_score(actual, predicted)),
    }


def train(seed: int = 42) -> dict:
    raw = load_growth_data()
    frame = add_competition_features(raw, "dbh_m_2016")
    raw_target = (frame["dbh_m_2021"] - frame["dbh_m_2016"]) / 5.0
    upper_cap = float(raw_target.quantile(0.99))
    frame[TARGET_COLUMN] = raw_target.clip(lower=0.0, upper=upper_cap)
    features = frame[FEATURE_COLUMNS].copy()
    features["species"] = features["species"].astype(str)
    target = frame[TARGET_COLUMN].to_numpy(dtype=float)
    groups = frame[GROUP_COLUMN].astype(str).to_numpy()

    splitter = GroupKFold(n_splits=5)
    out_of_fold = np.zeros(len(frame), dtype=float)
    baseline = np.zeros(len(frame), dtype=float)
    fold_metrics = []
    for fold, (train_indices, validation_indices) in enumerate(splitter.split(features, target, groups), 1):
        model = CatBoostRegressor(**model_parameters(seed + fold))
        model.fit(
            features.iloc[train_indices],
            target[train_indices],
            cat_features=CATEGORICAL_FEATURES,
        )
        prediction = model.predict(features.iloc[validation_indices])
        prediction = np.clip(prediction, 0.0, upper_cap)
        out_of_fold[validation_indices] = prediction
        baseline[validation_indices] = float(np.mean(target[train_indices]))
        fold_metrics.append({"fold": fold, **_metrics(target[validation_indices], prediction)})

    final_model = CatBoostRegressor(**model_parameters(seed))
    final_model.fit(features, target, cat_features=CATEGORICAL_FEATURES)
    residuals = target - out_of_fold
    data_hash = hashlib.sha256(
        pd.util.hash_pandas_object(
            frame[["tree_id", "species", "plot_id", "dbh_m_2016", "dbh_m_2021"]],
            index=False,
        ).to_numpy(dtype=np.uint64).tobytes()
    ).hexdigest()
    numeric_features = [column for column in FEATURE_COLUMNS if column not in CATEGORICAL_FEATURES]
    feature_importance = np.asarray(final_model.get_feature_importance(), dtype=float).ravel()
    metadata = {
        "model_name": "unified_species_dbh_growth_catboost",
        "model_version": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + data_hash[:12],
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "CatBoostRegressor",
        "catboost_version": __import__("catboost").__version__,
        "training_years": [2016, 2021],
        "target": TARGET_COLUMN,
        "target_definition": "max(0, min((dbh_m_2021-dbh_m_2016)/5, p99))",
        "target_upper_cap_m_per_year": upper_cap,
        "training_rows": len(frame),
        "species_count": int(frame["species"].nunique()),
        "plot_count": int(frame["plot_id"].nunique()),
        "features": FEATURE_COLUMNS,
        "categorical_features": CATEGORICAL_FEATURES,
        "validation_group": GROUP_COLUMN,
        "plot_id_is_model_feature": False,
        "cross_validation": {
            "strategy": "GroupKFold",
            "folds": 5,
            "overall": _metrics(target, out_of_fold),
            "baseline": _metrics(target, baseline),
            "per_fold": fold_metrics,
        },
        "annual_residual_quantiles_m": {
            "p10": float(np.quantile(residuals, 0.10)),
            "p90": float(np.quantile(residuals, 0.90)),
        },
        "numeric_feature_medians": {
            column: float(features[column].median()) for column in numeric_features
        },
        "known_species": sorted(frame["species"].astype(str).unique().tolist()),
        "feature_importance": {
            column: float(value)
            for column, value in zip(FEATURE_COLUMNS, feature_importance)
        },
        "data_sha256": data_hash,
        "limitations": [
            "2025 segmentation DBH is excluded from training because its measurement scale is not comparable.",
            "The model predicts DBH increment for surviving matched trees, not mortality or recruitment.",
            "Predictions beyond the observed interval are experimental extrapolations.",
        ],
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    temporary_model = MODEL_PATH.with_suffix(".tmp.cbm")
    temporary_metadata = METADATA_PATH.with_suffix(".tmp.json")
    final_model.save_model(str(temporary_model), format="cbm")
    temporary_metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary_model, MODEL_PATH)
    os.replace(temporary_metadata, METADATA_PATH)
    return metadata
