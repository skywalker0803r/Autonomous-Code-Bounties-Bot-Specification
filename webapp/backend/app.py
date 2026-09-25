"""FastAPI backend for the Bounty Bot web UI.

Wraps the existing bounty_bot CLI modules (monitor/ingestor/solver/tester/
submitter) behind a small HTTP API so the React frontend never has to shell
out to the CLI. Also serves the frontend's production build (see
webapp/frontend/dist), so the whole app is one process on one port:

    uvicorn webapp.backend.app:app --port 8000

then open http://localhost:8000. During frontend development, run
`npm run dev` in webapp/frontend instead (its Vite dev server proxies /api
to this backend) and this app only needs to serve /api/*.
"""

from __future__ import annotations

import logging
import threading
import uuid

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import store
from .models import (
    AgentStatusOut,
    BountyOut,
    GithubConnectIn,
    GithubConnectOut,
    RunOut,
    SettingsIn,
    SettingsOut,
)
from .pipeline import run_pipeline

logging.basicConfig(level="INFO", format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv(store.ENV_PATH)

app = FastAPI(title="Bounty Bot API")

# This app holds live GitHub/OpenAI credentials and can trigger real PRs, so
# it must never be reachable as an open control plane from an arbitrary web
# page. Only the exact origins this app is actually served from are allowed
# (single-server prod on :8000, or the Vite dev server on :5173 whose own
# proxy forwards /api same-origin) - never "*".
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Restricting CORS alone doesn't stop a plain HTML <form> POST (those are
# never subject to CORS/preflight), so every /api/* call must also carry this
# custom header - forms can't set custom headers, and a cross-origin
# fetch/XHR trying to add it would be blocked by the CORS policy above.
_REQUIRED_CLIENT_HEADER = "x-bounty-bot-client"


@app.middleware("http")
async def require_same_app_client(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        if request.headers.get(_REQUIRED_CLIENT_HEADER) != "1":
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


# ==================== Agent ====================


@app.get("/api/agent/status", response_model=AgentStatusOut)
def get_agent_status() -> dict:
    return {"state": store.agent_controller.state, "last_error": store.agent_controller.last_error}


@app.post("/api/agent/start", response_model=AgentStatusOut)
def start_agent() -> dict:
    store.agent_controller.start()
    return {"state": store.agent_controller.state, "last_error": store.agent_controller.last_error}


@app.post("/api/agent/stop", response_model=AgentStatusOut)
def stop_agent() -> dict:
    store.agent_controller.stop()
    return {"state": store.agent_controller.state, "last_error": store.agent_controller.last_error}


# ==================== Bounties ====================


@app.get("/api/bounties", response_model=list[BountyOut])
def list_bounties() -> list[dict]:
    return store.bounty_store.list()


@app.post("/api/bounties/{bounty_id}/solve", response_model=RunOut)
def solve_bounty(bounty_id: str) -> dict:
    bounty = store.bounty_store.get(bounty_id)
    if not bounty:
        raise HTTPException(status_code=404, detail="找不到這個懸賞")

    run_id = f"run_{uuid.uuid4().hex[:10]}"
    run = store.run_store.create(run_id, bounty)
    threading.Thread(target=run_pipeline, args=(run_id, bounty, store.run_store), daemon=True).start()
    return run


# ==================== Runs ====================


@app.get("/api/runs", response_model=list[RunOut])
def list_runs() -> list[dict]:
    return store.run_store.list()


@app.get("/api/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str) -> dict:
    run = store.run_store.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="找不到這筆執行紀錄")
    return run


@app.post("/api/runs/{run_id}/retry", response_model=RunOut)
def retry_run(run_id: str) -> dict:
    run = store.run_store.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="找不到這筆執行紀錄")

    bounty = store.bounty_store.get(run.get("bounty_id")) or {
        "id": run.get("bounty_id", run_id),
        "title": run["issue_title"],
        "repository": run["repository"],
        "reward": run["reward"],
        "repository_url": f"https://github.com/{run['repository']}",
        "issue_url": "",
        "language": "",
        "description": "",
    }

    store.run_store.reset_stages(run_id)
    store.run_store.append_log(run_id, "--- 重試中 ---")
    threading.Thread(target=run_pipeline, args=(run_id, bounty, store.run_store), daemon=True).start()
    return store.run_store.get(run_id)


# ==================== Settings ====================


@app.get("/api/settings", response_model=SettingsOut)
def get_settings() -> dict:
    return store.get_settings_snapshot()


@app.post("/api/settings", response_model=SettingsOut)
def save_settings(patch: SettingsIn) -> dict:
    store.apply_settings_patch(patch.model_dump(exclude_none=True))
    return store.get_settings_snapshot()


@app.post("/api/settings/github/connect", response_model=GithubConnectOut)
def connect_github(payload: GithubConnectIn) -> dict:
    try:
        resp = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"token {payload.token}", "Accept": "application/vnd.github+json"},
            timeout=10,
        )
    except requests.RequestException as exc:
        return {"connected": False, "error": f"無法連線到 GitHub：{exc}"}

    if resp.status_code != 200:
        return {"connected": False, "error": "Token 無效或權限不足，請確認已授予 repo 權限"}

    username = resp.json().get("login")
    store.write_env_values({"GITHUB_TOKEN": payload.token, "GITHUB_USERNAME": username})
    return {"connected": True, "username": username}


# ==================== Frontend (production build) ====================
# Registered last so every /api/* route above still takes priority.

FRONTEND_DIST = store.PROJECT_ROOT / "webapp" / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    logger.warning(
        "No frontend build found at %s - run `npm run build` in webapp/frontend, "
        "or use `npm run dev` there for local development.",
        FRONTEND_DIST,
    )
