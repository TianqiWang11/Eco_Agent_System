"""Expose non-sensitive status for the platform's active data source."""

from __future__ import annotations

import os
from typing import Any

from .database import database_status
from src.project_paths import REFERENCE_DATA_DIR


EXCEL_DATA_DIR = REFERENCE_DATA_DIR


def get_data_source_status() -> dict[str, Any]:
    configured_url = bool(os.getenv("DATABASE_URL", "").strip())
    default_mode = "database" if configured_url else "excel"
    mode = os.getenv("DATA_SOURCE_MODE", default_mode).strip().lower()

    if mode == "database":
        return database_status()

    excel_files = list(EXCEL_DATA_DIR.glob("*.xlsx")) if EXCEL_DATA_DIR.exists() else []
    return {
        "mode": "excel",
        "label": "本地表格数据",
        "state": "ready" if excel_files else "warning",
        "file_count": len(excel_files),
        "database_slot": "configured" if configured_url else "reserved",
    }
