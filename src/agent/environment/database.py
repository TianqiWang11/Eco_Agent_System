"""PostgreSQL repositories used by tools; orchestration never lives here."""
from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd
import psycopg
BUSINESS_TABLES = {"monitoring": "forest_inventory", "grid_plot": "tree_segmentation"}
logger = logging.getLogger(__name__)


def connect():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    options: dict[str, Any] = {"connect_timeout": 8, "application_name": "eco_agent"}
    return psycopg.connect(url, **options)


def load_analysis_dataset(dataset: str) -> pd.DataFrame:
    from src.agent.tools.local_tools.get_data import loader
    if dataset == "traits":
        return loader.load_traits().copy()
    table = BUSINESS_TABLES.get(dataset)
    if not table:
        raise ValueError("不支持该分析数据集")
    try:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(f'SELECT * FROM public."{table}" ORDER BY source_row')
            values = cursor.fetchall()
            columns = [item.name for item in cursor.description or ()]
    except psycopg.errors.UndefinedTable as exc:
        # Transitional safety for demo environments awaiting one-time DBA setup.
        logger.warning("PostgreSQL analysis tables are absent; using the legacy import source")
        from src.agent.tools.local_tools.get_data import loader
        loaders = {"monitoring": loader.load_monitoring_data,
                   "grid_plot": lambda: loader.prepare_segmentation_data(loader.load_large_plot_segmentation_data())}
        return loaders[dataset]().copy()
    frame = pd.DataFrame(values, columns=columns)
    frame = frame.drop(columns=["source_row"], errors="ignore")
    if dataset == "monitoring":
        return loader.prepare_monitoring_data(frame)
    return loader.prepare_segmentation_data(frame)
