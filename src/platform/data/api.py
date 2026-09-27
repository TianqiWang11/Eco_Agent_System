"""HTTP API for querying the Chebaling PostgreSQL dataset."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .database import DatabaseUnavailable, data_summary, database_status, search_trees, tree_detail


router = APIRouter(prefix="/data", tags=["Data Center"])


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="数据库暂时不可用，请检查连接配置。")


@router.get("/status")
def status():
    return database_status()


@router.get("/summary")
def summary():
    try:
        return data_summary()
    except DatabaseUnavailable:
        raise _unavailable() from None


@router.get("/trees")
def trees(
    tree_id: str | None = Query(default=None, max_length=64),
    species: str | None = Query(default=None, max_length=100),
    plot_id: str | None = Query(default=None, max_length=64),
    measurement_year: int | None = Query(default=None, ge=1900, le=2200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
):
    try:
        return search_trees(
            tree_id=tree_id,
            species=species,
            plot_id=plot_id,
            measurement_year=measurement_year,
            page=page,
            page_size=page_size,
        )
    except DatabaseUnavailable:
        raise _unavailable() from None


@router.get("/trees/{tree_id}")
def tree(tree_id: str):
    try:
        result = tree_detail(tree_id)
    except DatabaseUnavailable:
        raise _unavailable() from None
    if result is None:
        raise HTTPException(status_code=404, detail="没有找到这棵树。")
    return result
