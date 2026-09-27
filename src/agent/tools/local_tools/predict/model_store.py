"""Load the trained growth model and its non-secret metadata."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from catboost import CatBoostRegressor


MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_PATH = MODEL_DIR / "dbh_growth_catboost.cbm"
METADATA_PATH = MODEL_DIR / "dbh_growth_catboost.metadata.json"
_LOCK = threading.RLock()
_CACHE: tuple[int, CatBoostRegressor, dict] | None = None


def load_bundle() -> tuple[CatBoostRegressor, dict]:
    global _CACHE
    if not MODEL_PATH.exists() or not METADATA_PATH.exists():
        raise FileNotFoundError("胸径生长模型尚未训练")
    modified = max(MODEL_PATH.stat().st_mtime_ns, METADATA_PATH.stat().st_mtime_ns)
    with _LOCK:
        if _CACHE is not None and _CACHE[0] == modified:
            return _CACHE[1], _CACHE[2]
        model = CatBoostRegressor()
        model.load_model(str(MODEL_PATH))
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        _CACHE = (modified, model, metadata)
        return model, metadata
