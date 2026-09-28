import ast
import base64
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import ValidationError

from src.agent.contracts import ToolCall
from src.agent.tools.registry import ToolRegistry
from src.agent.tools.local_tools import register_local
from src.agent.tools.local_tools import adapters, agb_tools
from src.agent.tools.local_tools.get_data import get_data, loader
from src.agent.harness.provider import load_model_settings, model_status
from src.agent.presentation import public_response


@pytest.fixture
def frame(monkeypatch):
    value = pd.DataFrame({
        "species_cn": ["A", "A", "B"], "tree_id": ["001", "002", "003"],
        "dbh_cm": [10., 20., 30.], "dbh_2016_cm": [8., 18., 28.],
        "dbh_2021_cm": [10., 20., 30.], "height_m": [5., 10., 15.],
        "wood_density_g_cm3": [0.5, 0.6, 0.7]})
    for name in ("load_traits", "load_monitoring_data", "load_grid_plot_data"):
        monkeypatch.setattr(loader, name, lambda: value.copy())
    monkeypatch.setattr("src.agent.environment.load_analysis_dataset", lambda dataset: value.copy())
    return value


def test_structured_registry_rejects_old_free_text():
    registry = ToolRegistry()
    register_local(registry)
    assert set(registry.tools) == {
        "get_data", "analysis", "knowledge", "ue_scene", "database",
        "predict",
    }
    with pytest.raises(ValidationError):
        registry.resolve(ToolCall(id="x", name="analysis", arguments={"query": "AGB"}))
    assert registry.tools["ue_scene"].approval
    assert not registry.tools["ue_scene"].replay_safe


def test_query_and_exact_filter(frame):
    result = get_data({"dataset": "traits", "statistic": "species_count"})
    assert result["species_count"] == 2
    result = get_data({"dataset": "traits", "statistic": "records", "tree_id": "001"})
    assert result["record_count"] == 1
    assert result["records"][0]["tree_id"] == "001"
    with pytest.raises(ValueError):
        adapters.load_dataset({"dataset": "traits", "species_cn": "absent"})


def test_year_is_explicit_and_original_agb_is_retained(frame):
    with pytest.raises(ValueError):
        adapters.analyze({"dataset": "monitoring", "metric": "agb", "operation": "summary"})
    args = {"dataset": "monitoring", "year": 2016, "metric": "agb", "operation": "summary"}
    result = adapters.analyze(args)
    expected = frame.assign(dbh_cm=frame.dbh_2016_cm)
    assert result["summary"] == agb_tools.agb_summary(agb_tools.add_agb_column(expected))
    assert frame.dbh_cm.iloc[0] == 10.


@pytest.mark.parametrize("metric", ["agb", "height", "dbh"])
def test_chart_is_real_png(frame, metric):
    result = adapters.analyze({"dataset": "traits", "metric": metric, "operation": "histogram"})
    assert base64.b64decode(result["artifacts"][0]["content_base64"]).startswith(b"\x89PNG\r\n\x1a\n")


def test_scene_has_explicit_id_and_no_execution_claim():
    with pytest.raises(ValueError):
        adapters.scene_action({"action": "highlight"})
    result = adapters.scene_action({"action": "highlight", "target_id": "001"})
    assert result["ue_actions"] == [{"type": "highlight", "target_id": "001", "focus": False}]
    assert "UE" in result["answer"]


def test_provider_new_settings_and_secret_projection(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-secret")
    monkeypatch.setenv("MOONSHOT_CHAT_MODEL", "kimi-k3")
    settings = load_model_settings()
    assert settings.provider == "kimi"
    assert settings.model == "kimi-k3"
    assert settings.base_url == "https://api.moonshot.cn/v1"
    assert "test-secret" not in repr(settings)
    assert "test-secret" not in str(model_status())
    monkeypatch.setenv("MOONSHOT_MAX_RETRIES", "99")
    with pytest.raises(ValueError):
        load_model_settings()


def test_public_response_only_exports_contract():
    assert public_response({"answer": "Evidence [1]", "private": "secret"}) == {
        "answer": "Evidence [1]", "artifacts": []}


def test_no_agent_imports_of_removed_architecture():
    source = Path(__file__).resolve().parents[1] / "src"
    banned = ("src.core", "src.llm", "src.tools")
    for path in source.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            names = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                     else [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            assert not any(n == b or n.startswith(b + ".") for n in names for b in banned), path
