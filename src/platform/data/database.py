"""Read-only PostgreSQL access for the platform data center."""

from __future__ import annotations

import os
from typing import Any, cast
from typing_extensions import LiteralString

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


class DatabaseUnavailable(RuntimeError):
    """Raised when the configured database cannot serve a request."""


def database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise DatabaseUnavailable("DATABASE_URL is not configured")
    return value


def _connect() -> psycopg.Connection[dict[str, Any]]:
    try:
        return cast(psycopg.Connection[dict[str, Any]], psycopg.connect(
            database_url(),
            connect_timeout=5,
            row_factory=cast(Any, dict_row),
            application_name="chebaling_data_center",
        ))
    except (psycopg.Error, ValueError) as exc:
        raise DatabaseUnavailable("PostgreSQL connection failed") from exc


def database_status() -> dict[str, Any]:
    configured = bool(os.getenv("DATABASE_URL", "").strip())
    if not configured:
        return {
            "mode": "database",
            "label": "PostgreSQL",
            "state": "standby",
            "configured": False,
            "connected": False,
        }
    try:
        with _connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    (SELECT count(*) FROM public.trees) AS tree_count,
                    (SELECT count(*) FROM public.tree_measurements) AS measurement_count
                """
            )
            counts = cursor.fetchone()
            if counts is None:
                raise DatabaseUnavailable("PostgreSQL returned no status row")
        return {
            "mode": "database",
            "label": "PostgreSQL",
            "state": "ready",
            "configured": True,
            "connected": True,
            **counts,
        }
    except (DatabaseUnavailable, psycopg.Error):
        return {
            "mode": "database",
            "label": "PostgreSQL",
            "state": "error",
            "configured": True,
            "connected": False,
        }


def data_summary() -> dict[str, Any]:
    try:
        with _connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    count(*) AS tree_count,
                    count(DISTINCT species) AS species_count,
                    count(DISTINCT plot_id) AS plot_count
                FROM public.trees
                """
            )
            summary = cursor.fetchone()
            if summary is None:
                raise DatabaseUnavailable("PostgreSQL returned no summary row")
            cursor.execute(
                """
                SELECT measurement_year, count(*) AS row_count
                FROM public.tree_measurements
                GROUP BY measurement_year
                ORDER BY measurement_year
                """
            )
            years = cursor.fetchall()
            cursor.execute(
                """
                SELECT species, count(*) AS tree_count
                FROM public.trees
                GROUP BY species
                ORDER BY tree_count DESC, species
                LIMIT 10
                """
            )
            top_species = cursor.fetchall()
        summary["measurement_count"] = sum(row["row_count"] for row in years)
        summary["measurement_years"] = years
        summary["top_species"] = top_species
        return summary
    except psycopg.Error as exc:
        raise DatabaseUnavailable("PostgreSQL summary query failed") from exc


def search_trees(
    *,
    tree_id: str | None = None,
    species: str | None = None,
    plot_id: str | None = None,
    measurement_year: int | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    conditions: list[str] = []
    parameters: list[Any] = []
    measurement_parameters: list[Any] = []
    measurement_condition = ""
    if tree_id:
        conditions.append("t.tree_id ILIKE %s")
        parameters.append(f"%{tree_id.strip()}%")
    if species:
        conditions.append("t.species ILIKE %s")
        parameters.append(f"%{species.strip()}%")
    if plot_id:
        conditions.append("t.plot_id ILIKE %s")
        parameters.append(f"%{plot_id.strip()}%")
    if measurement_year is not None:
        measurement_condition = "AND m.measurement_year = %s"
        measurement_parameters.append(measurement_year)
        conditions.append(
            "EXISTS (SELECT 1 FROM public.tree_measurements ym "
            "WHERE ym.tree_id = t.tree_id AND ym.measurement_year = %s)"
        )
        parameters.append(measurement_year)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * page_size

    try:
        with _connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                # Only fixed code fragments form where_clause; user values stay parameterized.
                sql.SQL(cast(LiteralString, f"SELECT count(*) AS total FROM public.trees t {where_clause}")),
                parameters,
            )
            total_row = cursor.fetchone()
            if total_row is None:
                raise DatabaseUnavailable("PostgreSQL returned no tree count")
            total = total_row["total"]
            cursor.execute(
                sql.SQL(cast(LiteralString, f"""
                SELECT
                    t.tree_id,
                    t.species,
                    t.plot_id,
                    t.tree_position_x_m,
                    t.tree_position_y_m,
                    t.tree_position_z_m,
                    t.elevation_m,
                    latest.measurement_year AS latest_year,
                    latest.dbh_m AS latest_dbh_m,
                    latest.tree_height_m AS latest_tree_height_m
                FROM public.trees t
                LEFT JOIN LATERAL (
                    SELECT measurement_year, dbh_m, tree_height_m
                    FROM public.tree_measurements m
                    WHERE m.tree_id = t.tree_id
                    {measurement_condition}
                    ORDER BY measurement_year DESC
                    LIMIT 1
                ) latest ON true
                {where_clause}
                ORDER BY t.tree_id
                LIMIT %s OFFSET %s
                """)),
                [*measurement_parameters, *parameters, page_size, offset],
            )
            items = cursor.fetchall()
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": max(1, (total + page_size - 1) // page_size),
        }
    except psycopg.Error as exc:
        raise DatabaseUnavailable("PostgreSQL tree query failed") from exc


def tree_detail(tree_id: str) -> dict[str, Any] | None:
    try:
        with _connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM public.trees WHERE tree_id = %s",
                (tree_id,),
            )
            tree = cursor.fetchone()
            if tree is None:
                return None
            cursor.execute(
                """
                SELECT *
                FROM public.tree_measurements
                WHERE tree_id = %s
                ORDER BY measurement_year
                """,
                (tree_id,),
            )
            measurements = cursor.fetchall()
        return {"tree": tree, "measurements": measurements}
    except psycopg.Error as exc:
        raise DatabaseUnavailable("PostgreSQL tree detail query failed") from exc
