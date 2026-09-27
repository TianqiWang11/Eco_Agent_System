import os
import subprocess
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

from src.agent.api import router as agent_router
from src.platform.data.api import router as data_router
from src.agent.runtime import get_runtime
from src.platform.data.source_status import get_data_source_status
from src.agent.harness.provider import model_status
from src.agent.tools.local_tools.knowledge_tools import retrieve_knowledge

FRONTEND_DIR = PROJECT_ROOT / "frontend"
_warmup_lock = threading.Lock()
_twin_reset_lock = threading.Lock()
_warmup_status = {
    "state": "idle",
    "started_at": None,
    "finished_at": None,
    "message": "等待预热",
}

app = FastAPI(
    title="Chebaling Eco Digital Twin & AI Platform",
    description="车八岭生态数字孪生与 AI 智能分析平台统一后端",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发阶段先放开
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


app.include_router(agent_router)
app.include_router(data_router)


@app.on_event("startup")
def start_agent_runtime():
    get_runtime()


@app.on_event("shutdown")
def stop_agent_runtime():
    get_runtime().close()


app.mount("/portal-assets", StaticFiles(directory=FRONTEND_DIR), name="portal-assets")


@app.get("/", include_in_schema=False)
def portal():
    return FileResponse(FRONTEND_DIR / "platform.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(FRONTEND_DIR / "platform-logo.svg", media_type="image/svg+xml")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "chebaling-platform-api",
        "version": app.version,
    }


@app.get("/platform/config")
def platform_config():
    """向门户提供非敏感运行配置。"""
    auto_connect = os.getenv("PIXEL_STREAMING_AUTO_CONNECT", "true").lower()
    return {
        "platform_name": os.getenv(
            "PLATFORM_NAME", "车八岭生态数字孪生与AI智能分析平台"
        ),
        "pixel_streaming_url": os.getenv("PIXEL_STREAMING_URL", ""),
        "pixel_streaming_port": int(os.getenv("PIXEL_STREAMING_HTTP_PORT", "8080")),
        "pixel_streaming_player_path": os.getenv(
            "PIXEL_STREAMING_PLAYER_PATH", "/uiless.html"
        ),
        "pixel_streaming_auto_connect": auto_connect not in {"0", "false", "no"},
        "data_source_mode": os.getenv("DATA_SOURCE_MODE", "excel").lower(),
    }


@app.get("/platform/status")
def platform_status():
    """统一门户状态页使用的轻量检查，不触发大表全量加载。"""
    return {
        "api": {"state": "ready", "label": "后端服务"},
        "ai": model_status(),
        "data_source": get_data_source_status(),
        "digital_twin": {
            "state": "configured"
            if os.getenv("PIXEL_STREAMING_URL")
            or os.getenv("PIXEL_STREAMING_HTTP_PORT")
            else "standby",
            "label": "数字孪生服务",
        },
        "warmup": dict(_warmup_status),
    }


@app.post("/platform/reset-twin")
def reset_twin():
    """Restart only the packaged UE streamer so the shared scene returns home."""
    restart_script = (
        PROJECT_ROOT
        / "infrastructure"
        / "ue-connection"
        / "restart_ue.ps1"
    )
    if not restart_script.exists():
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "UE restart script is missing"},
        )

    with _twin_reset_lock:
        try:
            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(restart_script),
                ],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=45,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": str(exc)},
            )

    if completed.returncode != 0:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": (completed.stderr or completed.stdout).strip(),
            },
        )
    return {"ok": True, "message": completed.stdout.strip()}


def _warm_up_excel_data() -> None:
    with _warmup_lock:
        if _warmup_status["state"] in {"running", "ready"}:
            return
        _warmup_status.update(
            state="running",
            started_at=time.time(),
            finished_at=None,
            message="正在加载常用生态数据",
        )

    try:
        from src.agent.tools.local_tools.get_data.loader import (
            load_grid_plot_data,
            load_monitoring_data,
            load_traits,
        )

        load_traits()
        load_monitoring_data(enrich_for_agb=True)
        load_grid_plot_data(enrich_for_agb=True)
        _warmup_status.update(
            state="ready",
            finished_at=time.time(),
            message="常用生态数据已就绪",
        )
    except Exception:
        _warmup_status.update(
            state="error",
            finished_at=time.time(),
            message="数据预热未完成，可在首次查询时按需加载",
        )


@app.post("/platform/warmup", status_code=202)
def platform_warmup(background_tasks: BackgroundTasks):
    """门户打开后预加载常用Excel数据，降低首次演示查询等待时间。"""
    if os.getenv("DATA_SOURCE_MODE", "excel").lower() == "excel":
        background_tasks.add_task(_warm_up_excel_data)
    return {"accepted": True, "warmup": dict(_warmup_status)}


@app.post("/chat")
def chat(req: ChatRequest):
    try:
        # Synchronous HTTP transport over the durable Harness runtime.
        runtime = get_runtime()
        state, token = runtime.start_session(req.message)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            task = runtime.public(state["id"])
            if task["status"] not in {"queued", "running"}:
                return {**(task["final"] or {"answer": "任务等待审批，请使用任务接口继续。", "artifacts": []}),
                        "session_id": state["id"], "session_token": token, "status": task["status"]}
            time.sleep(0.1)
        return JSONResponse(status_code=202, content={"answer": "任务仍在执行，可通过任务接口查看进度。",
            "artifacts": [], "session_id": state["id"], "session_token": token, "status": "running"})

    except Exception:
        return JSONResponse(
            status_code=500,
            content={
                "answer": "暂时无法完成本次回答，请稍后重试。",
                "artifacts": [],
            },
        )


@app.get("/knowledge-search")
def knowledge_search(query: str, top_k: int = 2):
    retrieval = retrieve_knowledge(query, top_k=top_k)
    return {
        "query": query,
        "sources": retrieval["sources"],
        "results": retrieval["results"],
    }
