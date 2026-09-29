"""Standalone PR status tracker - fully decoupled from the main Bounty Bot
web backend, Docker sandbox, or any AI provider. Its only job: read which
bounties already have a submitted PR (from webapp/backend/data/runs.json),
and let you check each one's live GitHub status/comments and post a reply.

Runs on its own port so it never needs the main bot's backend, Docker
Desktop, or Claude Code to be running - just this one lightweight process.
It never polls in the background either; every GitHub call happens only
when the phone/browser asks for it (page load or a manual refresh).

Run with: python -m uvicorn pr_tracker.server:app --host 0.0.0.0 --port 8010
"""

from __future__ import annotations

import base64
import json
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import requests
from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
RUNS_PATH = PROJECT_ROOT / "webapp" / "backend" / "data" / "runs.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"

PR_URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")

app = FastAPI(title="Bounty Bot PR Tracker")


def _token() -> Optional[str]:
    return dotenv_values(ENV_PATH).get("GITHUB_TOKEN") or None


def _access_credentials() -> tuple[Optional[str], Optional[str]]:
    env = dotenv_values(ENV_PATH)
    return env.get("PR_TRACKER_USERNAME"), env.get("PR_TRACKER_PASSWORD")


@app.middleware("http")
async def require_basic_auth(request: Request, call_next):
    """Guard the data API with HTTP Basic Auth. Only matters once this
    server is reachable from outside the LAN (e.g. via a Cloudflare
    Tunnel): without it, anyone who finds the public URL could read your
    submitted-PR list or post GitHub comments using your token. If no
    credentials are configured in .env, the server is left open (matches
    the original LAN-only, no-login behavior).

    The static frontend (index.html, manifest, service worker, icons) is
    deliberately NOT gated - it carries no PR data on its own (that only
    loads via the protected /api/* calls below), and Chrome's "Add to Home
    Screen" fetches the manifest/icons itself without attaching Basic Auth
    credentials, so gating them made every install show a generic grey
    icon instead of the real one.
    """
    if not request.url.path.startswith("/api/") or request.url.path == "/api/health":
        return await call_next(request)
    username, password = _access_credentials()
    if not username or not password:
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8")
            given_user, _, given_pass = decoded.partition(":")
        except Exception:
            given_user, given_pass = "", ""
        if secrets.compare_digest(given_user, username) and secrets.compare_digest(given_pass, password):
            return await call_next(request)
    return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Bounty Bot PR Tracker"'})


def _headers() -> dict:
    token = _token()
    if not token:
        raise HTTPException(status_code=400, detail=".env 沒有設定 GITHUB_TOKEN")
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def _load_submitted_prs() -> list[dict]:
    if not RUNS_PATH.exists():
        return []
    try:
        raw = json.loads(RUNS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    # Retries against the same bounty reuse one PR - keep only the most
    # recent run per PR URL so it isn't listed more than once.
    by_pr_url: dict[str, dict] = {}
    for run in raw.values():
        url = run.get("pr_url")
        if not url or not PR_URL_RE.search(url):
            continue
        existing = by_pr_url.get(url)
        if existing is None or run.get("started_at", "") > existing.get("started_at", ""):
            by_pr_url[url] = run
    items = list(by_pr_url.values())
    items.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return items


def _pr_parts(pr_url: str) -> tuple[str, str, str]:
    match = PR_URL_RE.search(pr_url)
    if not match:
        raise HTTPException(status_code=400, detail="無法解析 PR 網址")
    return match.groups()


class ReplyIn(BaseModel):
    body: str


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "github_token_set": bool(_token())}


@app.get("/api/prs")
def list_prs() -> list[dict]:
    """Submitted PRs with a fresh live status pulled from GitHub for each."""
    prs = _load_submitted_prs()
    token = _token()

    def fetch_status(pr: dict) -> tuple[Optional[str], bool]:
        state, merged = None, pr.get("merged", False)
        if not token:
            return state, merged
        try:
            owner, repo, number = _pr_parts(pr["pr_url"])
            resp = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}",
                headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                state, merged = data.get("state"), data.get("merged", False)
        except requests.RequestException:
            pass
        return state, merged

    # One PR's slow/rate-limited GitHub call used to block every other PR
    # behind it (15 PRs x ~1s each = ~16s felt like the page had hung) -
    # fire them all at once instead.
    with ThreadPoolExecutor(max_workers=min(10, len(prs)) or 1) as pool:
        statuses = list(pool.map(fetch_status, prs))

    result = []
    for i, (pr, (state, merged)) in enumerate(zip(prs, statuses)):
        result.append({
            "index": i,
            "repository": pr["repository"],
            "issueTitle": pr["issue_title"],
            "reward": pr["reward"],
            "prUrl": pr["pr_url"],
            "startedAt": pr.get("started_at"),
            "merged": merged,
            "state": state,
            "duplicatePr": pr.get("duplicate_pr", False),
        })
    return result


@app.get("/api/prs/{index}/comments")
def get_comments(index: int) -> list[dict]:
    prs = _load_submitted_prs()
    if index < 0 or index >= len(prs):
        raise HTTPException(status_code=404, detail="找不到這個 PR")
    owner, repo, number = _pr_parts(prs[index]["pr_url"])
    resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments",
        headers=_headers(), timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail="無法載入留言")
    return [
        {"author": c["user"]["login"], "body": c["body"], "createdAt": c.get("created_at")}
        for c in resp.json()
    ]


@app.post("/api/prs/{index}/reply")
def post_reply(index: int, payload: ReplyIn) -> dict:
    prs = _load_submitted_prs()
    if index < 0 or index >= len(prs):
        raise HTTPException(status_code=404, detail="找不到這個 PR")
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="回覆內容不可為空")
    owner, repo, number = _pr_parts(prs[index]["pr_url"])
    resp = requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments",
        headers=_headers(), json={"body": body}, timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail="回覆失敗")
    return {"ok": True}


# Registered last: API routes above take precedence, this is the fallback
# for "/" (serves index.html) and any other static asset (manifest, sw.js,
# icons).
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
