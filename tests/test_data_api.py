from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.platform.data import api
from src.platform.data.database import DatabaseUnavailable


def client() -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def test_summary(monkeypatch):
    monkeypatch.setattr(
        api,
        "data_summary",
        lambda: {"tree_count": 1526, "species_count": 243, "measurement_count": 4578},
    )
    response = client().get("/data/summary")
    assert response.status_code == 200
    assert response.json()["tree_count"] == 1526


def test_tree_filters_are_forwarded(monkeypatch):
    captured = {}

    def fake_search(**kwargs):
        captured.update(kwargs)
        return {"items": [], "page": 2, "page_size": 10, "total": 0, "pages": 1}

    monkeypatch.setattr(api, "search_trees", fake_search)
    response = client().get(
        "/data/trees",
        params={
            "tree_id": "0101",
            "species": "species",
            "plot_id": "20GQ",
            "measurement_year": 2025,
            "page": 2,
            "page_size": 10,
        },
    )
    assert response.status_code == 200
    assert captured == {
        "tree_id": "0101",
        "species": "species",
        "plot_id": "20GQ",
        "measurement_year": 2025,
        "page": 2,
        "page_size": 10,
    }


def test_tree_not_found(monkeypatch):
    monkeypatch.setattr(api, "tree_detail", lambda _tree_id: None)
    response = client().get("/data/trees/missing")
    assert response.status_code == 404


def test_database_failure_is_sanitized(monkeypatch):
    def fail():
        raise DatabaseUnavailable("secret internal database details")

    monkeypatch.setattr(api, "data_summary", fail)
    response = client().get("/data/summary")
    assert response.status_code == 503
    assert "secret" not in response.text
