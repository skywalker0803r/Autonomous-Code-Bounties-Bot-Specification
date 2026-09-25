"""In-memory state + on-disk settings persistence for the web backend.

Kept deliberately simple (no database): a single agent runs on behalf of a
single user, so a few thread-safe in-memory stores are enough. Settings that
must survive a restart (API keys, filters) are read from / written to the
same .env and settings.yaml files the CLI bot already uses.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import dotenv
import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
SETTINGS_PATH = PROJECT_ROOT / "bounty_bot" / "config" / "settings.yaml"

STAGE_DEFS: list[tuple[str, str]] = [
    ("issue_found", "發現 Issue"),
    ("repo_loaded", "倉庫已載入"),
    ("analyzing", "分析中"),
    ("generating_patch", "生成修補程式"),
    ("testing", "測試中"),
    ("pr_submitted", "PR 已提交"),
]


def fresh_stages() -> list[dict]:
    return [
        {"key": key, "label": label, "status": "running" if i == 0 else "waiting"}
        for i, (key, label) in enumerate(STAGE_DEFS)
    ]


# ==================== Settings persistence ====================


def _ensure_env_file() -> None:
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")


def read_env() -> dict:
    _ensure_env_file()
    return dotenv.dotenv_values(ENV_PATH)


def write_env_values(updates: dict[str, str]) -> None:
    _ensure_env_file()
    for key, value in updates.items():
        dotenv.set_key(str(ENV_PATH), key, value, quote_mode="never")
    dotenv.load_dotenv(ENV_PATH, override=True)


def read_settings_yaml() -> dict:
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_settings_yaml(data: dict) -> None:
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def get_settings_snapshot() -> dict:
    env = read_env()
    yaml_data = read_settings_yaml()

    llm = yaml_data.get("llm", {})
    filters = yaml_data.get("filters", {})
    docker_cfg = yaml_data.get("docker", {})
    resources = yaml_data.get("resources", {})
    monitoring = yaml_data.get("monitoring", {})
    submission = yaml_data.get("submission", {})
    testing = yaml_data.get("testing", {})

    provider = (llm.get("provider") or "gemini").lower()
    if provider == "openai":
        api_key_set = bool(env.get("OPENAI_API_KEY"))
    elif provider == "claude_code":
        # Uses the locally-installed Claude Code CLI's own login instead of
        # an API key stored in .env.
        api_key_set = True
    else:
        api_key_set = bool(env.get("GEMINI_API_KEY"))

    return {
        "github_connected": bool(env.get("GITHUB_TOKEN")) and bool(env.get("GITHUB_USERNAME")),
        "github_username": env.get("GITHUB_USERNAME") or None,
        "ai_provider": provider,
        "api_key_set": api_key_set,
        "languages": filters.get("languages", []),
        "min_bounty": filters.get("min_bounty_amount", 50),
        "max_ai_cost": filters.get("max_ai_cost_usd", 5),
        "auto_submit_pr": submission.get("auto_submit_pr", True),
        "testing_mode": testing.get("mode", "docker"),
        "advanced": {
            "poll_interval_seconds": monitoring.get("poll_interval_seconds", 300),
            "docker_memory_limit": docker_cfg.get("memory_limit", "4g"),
            "docker_cpu_limit": docker_cfg.get("cpu_limit", 2),
            "max_retries": resources.get("max_retries", 3),
            "max_parallel_tests": resources.get("max_parallel_tests", 1),
        },
    }


def apply_settings_patch(patch: dict) -> None:
    yaml_data = read_settings_yaml()
    yaml_data.setdefault("llm", {})
    yaml_data.setdefault("filters", {})
    yaml_data.setdefault("docker", {})
    yaml_data.setdefault("resources", {})
    yaml_data.setdefault("monitoring", {})
    yaml_data.setdefault("submission", {})
    yaml_data.setdefault("testing", {})

    if patch.get("ai_provider") is not None:
        new_provider = patch["ai_provider"]
        # There's no UI to set `model` directly, so a stale model left over
        # from the previous provider (e.g. "gpt-4.1-mini" from OpenAI) would
        # otherwise get sent to whatever provider is switched to. Clear it
        # on a real provider change so LLMSolver falls back to that
        # provider's own default model.
        if new_provider != yaml_data["llm"].get("provider"):
            yaml_data["llm"].pop("model", None)
        yaml_data["llm"]["provider"] = new_provider

    if patch.get("api_key"):
        provider = (patch.get("ai_provider") or yaml_data["llm"].get("provider") or "gemini").lower()
        if provider == "openai":
            write_env_values({"OPENAI_API_KEY": patch["api_key"]})
        elif provider != "claude_code":
            write_env_values({"GEMINI_API_KEY": patch["api_key"]})

    if patch.get("languages") is not None:
        yaml_data["filters"]["languages"] = patch["languages"]
    if patch.get("min_bounty") is not None:
        yaml_data["filters"]["min_bounty_amount"] = patch["min_bounty"]
    if patch.get("max_ai_cost") is not None:
        yaml_data["filters"]["max_ai_cost_usd"] = patch["max_ai_cost"]
    if patch.get("auto_submit_pr") is not None:
        yaml_data["submission"]["auto_submit_pr"] = patch["auto_submit_pr"]

    advanced = patch.get("advanced") or {}
    if advanced.get("poll_interval_seconds") is not None:
        yaml_data["monitoring"]["poll_interval_seconds"] = advanced["poll_interval_seconds"]
    if advanced.get("docker_memory_limit") is not None:
        yaml_data["docker"]["memory_limit"] = advanced["docker_memory_limit"]
    if advanced.get("docker_cpu_limit") is not None:
        yaml_data["docker"]["cpu_limit"] = advanced["docker_cpu_limit"]
    if advanced.get("max_retries") is not None:
        yaml_data["resources"]["max_retries"] = advanced["max_retries"]
    if advanced.get("max_parallel_tests") is not None:
        yaml_data["resources"]["max_parallel_tests"] = advanced["max_parallel_tests"]

    write_settings_yaml(yaml_data)


# ==================== Bounty store ====================


def _classify_type(labels: list[str]) -> str:
    lowered = [l.lower() for l in labels]
    if any("feature" in l or "enhancement" in l for l in lowered):
        return "新功能"
    return "錯誤修復"


def _classify_difficulty(bounty_amount: float) -> str:
    if bounty_amount < 75:
        return "簡單"
    if bounty_amount < 150:
        return "中等"
    return "困難"


def _estimate_ai_cost(bounty_amount: float) -> float:
    # Heuristic placeholder: the backend has no real token-cost estimator yet,
    # so this scales loosely with bounty size until one exists.
    return round(max(0.2, min(5.0, bounty_amount * 0.015)), 2)


def bounty_issue_to_dict(issue) -> dict:
    return {
        "id": issue.id,
        "title": issue.title,
        "description": issue.description,
        "repository": issue.repository,
        "repository_url": issue.repository_url,
        "issue_url": issue.issue_url,
        "source": issue.source,
        "reward": issue.bounty_amount,
        "language": issue.language,
        "type": _classify_type(issue.labels),
        "difficulty": _classify_difficulty(issue.bounty_amount),
        "estimated_ai_cost": _estimate_ai_cost(issue.bounty_amount),
    }


class BountyStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bounties: dict[str, dict] = {}

    def set_all(self, bounties: list[dict]) -> None:
        with self._lock:
            self._bounties = {b["id"]: b for b in bounties}

    def list(self) -> list[dict]:
        with self._lock:
            return list(self._bounties.values())

    def get(self, bounty_id: str) -> Optional[dict]:
        with self._lock:
            return self._bounties.get(bounty_id)


# ==================== Run store ====================


class RunStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, dict] = {}

    def create(self, run_id: str, bounty: dict) -> dict:
        run = {
            "id": run_id,
            "bounty_id": bounty["id"],
            "issue_title": bounty["title"],
            "repository": bounty["repository"],
            "reward": bounty["reward"],
            "started_at": datetime.now(),
            "status": "running",
            "stages": fresh_stages(),
            "pr_url": None,
            "error_message": None,
            "logs": [],
        }
        with self._lock:
            self._runs[run_id] = run
        return run

    def get(self, run_id: str) -> Optional[dict]:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> list[dict]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda r: r["started_at"], reverse=True)

    def update_stage(self, run_id: str, stage_key: str, status: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            for stage in run["stages"]:
                if stage["key"] == stage_key:
                    stage["status"] = status
                    break

    def reset_stages(self, run_id: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run["stages"] = fresh_stages()
            run["status"] = "running"
            run["error_message"] = None

    def set_status(self, run_id: str, status: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                run["status"] = status

    def set_error(self, run_id: str, message: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                run["error_message"] = message

    def set_pr_url(self, run_id: str, url: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                run["pr_url"] = url

    def append_log(self, run_id: str, message: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                run["logs"].append(message)


# ==================== Agent controller ====================


class AgentController:
    """Owns the background polling loop that discovers new bounty issues."""

    def __init__(self, bounty_store: BountyStore) -> None:
        self.bounty_store = bounty_store
        self.state = "STOPPED"
        self.last_error: Optional[str] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.state == "RUNNING":
            return
        self.state = "RUNNING"
        self.last_error = None
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.state = "STOPPED"
        self._stop_event.set()

    def _loop(self) -> None:
        # Imported lazily so a missing settings.yaml doesn't crash the whole
        # backend at import time.
        from bounty_bot.src.monitor import IssueMonitor

        while not self._stop_event.is_set():
            try:
                monitor = IssueMonitor(str(SETTINGS_PATH))
                monitor.run_poll_cycle()
                self.bounty_store.set_all([bounty_issue_to_dict(i) for i in monitor.identified_issues])
                self.last_error = None
            except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
                logger.exception("Bounty poll cycle failed")
                self.last_error = str(exc)

            interval = get_settings_snapshot()["advanced"]["poll_interval_seconds"]
            self._stop_event.wait(timeout=max(5, interval))


bounty_store = BountyStore()
run_store = RunStore()
agent_controller = AgentController(bounty_store)
