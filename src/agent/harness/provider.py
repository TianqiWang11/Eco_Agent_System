"""Kimi-only model connection settings for the Harness."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


KIMI_BASE_URL = "https://api.moonshot.cn/v1"
KIMI_MODEL = "kimi-k3"

# Model configuration belongs to Harness and must work without importing app.py.
load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)


@dataclass(frozen=True)
class ModelSettings:
    model: str
    base_url: str
    api_key: str = field(repr=False)
    provider: str = field(default="kimi", init=False)
    timeout: float = 120
    max_retries: int = 1
    reasoning_effort: str = "medium"
    max_completion_tokens: int = 4096


def _first(*keys: str, default: str = "") -> str:
    return next((os.environ[key] for key in keys if os.environ.get(key)), default)


def load_model_settings(require_api_key: bool = True) -> ModelSettings:
    """Load only Moonshot/Kimi settings; other providers are intentionally unsupported."""
    settings = ModelSettings(
        model=_first("MOONSHOT_CHAT_MODEL", "MOONSHOT_MODEL", default=KIMI_MODEL),
        base_url=_first("MOONSHOT_BASE_URL", default=KIMI_BASE_URL),
        api_key=_first("MOONSHOT_API_KEY"),
        timeout=float(_first("MOONSHOT_TIMEOUT", default="120")),
        max_retries=int(_first("MOONSHOT_MAX_RETRIES", default="1")),
        reasoning_effort=_first("MOONSHOT_REASONING_EFFORT", default="medium"),
        max_completion_tokens=int(_first("MOONSHOT_MAX_COMPLETION_TOKENS", default="4096")),
    )
    if require_api_key and not settings.api_key:
        raise ValueError("Configure MOONSHOT_API_KEY")
    if not settings.model.startswith("kimi-"):
        raise ValueError("Only Kimi models are supported")
    if settings.base_url.rstrip("/") != KIMI_BASE_URL:
        raise ValueError("MOONSHOT_BASE_URL must use the official Kimi API endpoint")
    if settings.timeout <= 0 or settings.max_retries not in range(4) or settings.max_completion_tokens < 128:
        raise ValueError("Invalid Kimi timeout, retry limit or output budget")
    if settings.reasoning_effort not in {"low", "medium", "high"}:
        raise ValueError("MOONSHOT_REASONING_EFFORT must be low, medium or high")
    return settings


def model_status() -> dict:
    settings = load_model_settings(require_api_key=False)
    return {
        "state": "ready" if settings.api_key else "needs_configuration",
        "label": "Kimi Agent 模型服务",
        "provider": "kimi",
        "model": settings.model,
        "api_key_configured": bool(settings.api_key),
    }
