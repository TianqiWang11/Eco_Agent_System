"""Idempotently import the two complete business datasets into PostgreSQL."""
from __future__ import annotations

import json

import pandas as pd
from psycopg import sql
from dotenv import load_dotenv

from src.agent.environment.database import BUSINESS_TABLES, connect
from src.agent.environment.catalog import sync_postgres_comments
from src.agent.tools.local_tools.get_data import loader
from src.project_paths import SERVICE_ROOT

load_dotenv(SERVICE_ROOT / ".env")


def _sql_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series.dtype): return "boolean"
    if pd.api.types.is_integer_dtype(series.dtype): return "bigint"
    if pd.api.types.is_numeric_dtype(series.dtype): return "double precision"
    return "text"


def _value(value):
    if pd.isna(value): return None
    return value.item() if hasattr(value, "item") else value


def import_business_data() -> dict[str, int]:
    frames = {
        "monitoring": loader.load_monitoring_records(),
        "grid_plot": loader.load_large_plot_segmentation_data(),
    }
    counts = {}
    with connect() as connection:
        for key, frame in frames.items():
            table = BUSINESS_TABLES[key]
            columns = list(frame.columns)
            definitions = [sql.SQL("source_row bigint PRIMARY KEY")]
            definitions.extend(sql.SQL("{} {}").format(sql.Identifier(name), sql.SQL(_sql_type(frame[name]))) for name in columns)
            with connection.cursor() as cursor:
                qualified = sql.Identifier("public", table)
                cursor.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(qualified))
                cursor.execute(sql.SQL("CREATE TABLE {} ({})").format(qualified, sql.SQL(", ").join(definitions)))
                statement = sql.SQL("COPY {} ({}) FROM STDIN").format(qualified, sql.SQL(", ").join([sql.Identifier("source_row"), *map(sql.Identifier, columns)]))
                with cursor.copy(statement) as copy:
                    for index, row in enumerate(frame.itertuples(index=False, name=None), 1):
                        copy.write_row((index, *(_value(value) for value in row)))
                for index_column in ({"tree_id", "qudrat_id"} if key == "monitoring" else {"grid_id"}):
                    if index_column in columns:
                        cursor.execute(sql.SQL("CREATE INDEX {} ON {} ({})").format(
                            sql.Identifier(table + "_" + index_column + "_idx"), qualified,
                            sql.Identifier(index_column)))
            counts[key] = len(frame)
        sync_postgres_comments(connection)
    return counts


def main():
    print(json.dumps({"postgresql": import_business_data()}, ensure_ascii=False))


if __name__ == "__main__": main()
