"""In-memory state + on-disk persistence for the web backend.

Kept deliberately simple (no database): a single agent runs on behalf of a
single user. Settings that must survive a restart (API keys, filters) are
read from / written to the same .env and settings.yaml files the CLI bot
already uses. Run history (earnings, which bounties were solved) is written
to a local JSON file (see RunStore) - restarting the backend used to wipe
this out entirely, silently losing the record of what was earned/completed.
"""

from __future__ import annotations

import json
import logging
import smtplib
import threading
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

import dotenv
import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
SETTINGS_PATH = PROJECT_ROOT / "bounty_bot" / "config" / "settings.yaml"
RUNS_PATH = PROJECT_ROOT / "webapp" / "backend" / "data" / "runs.json"
SEEN_BOUNTIES_PATH = PROJECT_ROOT / "webapp" / "backend" / "data" / "seen_bounties.json"

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
        dotenv.set_key(str(ENV_PATH), key, value, quote_mode="always")
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
    email_password = env.get("SMTP_PASSWORD")

    provider = (llm.get("provider") or "gemini").lower()
    if provider == "openai":
        api_key_set = bool(env.get("OPENAI_API_KEY"))
    elif provider == "local":
        api_key_set = bool(env.get("LOCAL_LLM_API_KEY"))
    elif provider in {"claude_code", "gemini_cli", "antigravity_cli"}:
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
        "ai_model": llm.get("model") or None,
        "local_base_url": llm.get("local_base_url") or "http://127.0.0.1:11434/v1",
        "local_api_key_set": bool(env.get("LOCAL_LLM_API_KEY")),
        "languages": filters.get("languages", []),
        "min_bounty": filters.get("min_bounty_amount", 50),
        "max_ai_cost": filters.get("max_ai_cost_usd", 5),
        "auto_submit_pr": submission.get("auto_submit_pr", True),
        "email_notifications": env.get("EMAIL_NOTIFICATIONS", "false").lower() == "true",
        "notification_email": env.get("NOTIFICATION_EMAIL") or None,
        "smtp_host": env.get("SMTP_HOST") or None,
        "smtp_port": int(env.get("SMTP_PORT") or 587),
        "smtp_username": env.get("SMTP_USERNAME") or None,
        "smtp_password_set": bool(email_password),
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
        elif provider == "local":
            write_env_values({"LOCAL_LLM_API_KEY": patch["api_key"]})
        elif provider != "claude_code":
            write_env_values({"GEMINI_API_KEY": patch["api_key"]})

    if patch.get("ai_model"):
        yaml_data["llm"]["model"] = patch["ai_model"].strip()
    if patch.get("local_base_url") is not None:
        yaml_data["llm"]["local_base_url"] = patch["local_base_url"].strip()

    if patch.get("languages") is not None:
        yaml_data["filters"]["languages"] = patch["languages"]
    if patch.get("min_bounty") is not None:
        yaml_data["filters"]["min_bounty_amount"] = patch["min_bounty"]
    if patch.get("max_ai_cost") is not None:
        yaml_data["filters"]["max_ai_cost_usd"] = patch["max_ai_cost"]
    if patch.get("auto_submit_pr") is not None:
        yaml_data["submission"]["auto_submit_pr"] = patch["auto_submit_pr"]

    email_updates = {}
    for field, env_key in (
        ("email_notifications", "EMAIL_NOTIFICATIONS"),
        ("notification_email", "NOTIFICATION_EMAIL"),
        ("smtp_host", "SMTP_HOST"),
        ("smtp_port", "SMTP_PORT"),
        ("smtp_username", "SMTP_USERNAME"),
        ("smtp_password", "SMTP_PASSWORD"),
    ):
        if patch.get(field) is not None and (field != "smtp_password" or patch[field]):
            email_updates[env_key] = str(patch[field]).lower() if isinstance(patch[field], bool) else str(patch[field])
    if email_updates:
        write_env_values(email_updates)

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
        "poster_login": issue.poster_login,
        "poster_url": issue.poster_url,
        "suspicion_level": issue.suspicion_level,
        "suspicion_reasons": issue.suspicion_reasons,
    }


class BountyStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bounties: dict[str, dict] = {}
        try:
            self._seen_ids = set(json.loads(SEEN_BOUNTIES_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError):
            self._seen_ids = set()

    def set_all(self, bounties: list[dict]) -> None:
        with self._lock:
            previous_ids = set(self._seen_ids)
            self._bounties = {b["id"]: b for b in bounties}
            new_bounties = [b for b in bounties if b["id"] not in previous_ids]
            self._seen_ids.update(b["id"] for b in bounties)
            try:
                SEEN_BOUNTIES_PATH.parent.mkdir(parents=True, exist_ok=True)
                SEEN_BOUNTIES_PATH.write_text(json.dumps(sorted(self._seen_ids)), encoding="utf-8")
            except OSError:
                logger.exception("Failed to persist seen bounty IDs")
        if new_bounties:
            try:
                send_bounty_notifications(new_bounties)
            except Exception:
                logger.exception("Failed to send bounty notification email")

    def list(self) -> list[dict]:
        with self._lock:
            return list(self._bounties.values())

    def get(self, bounty_id: str) -> Optional[dict]:
        with self._lock:
            return self._bounties.get(bounty_id)


def send_bounty_notifications(bounties: list[dict], *, force: bool = False) -> None:
    """Email a digest of newly discovered bounties when SMTP is configured."""
    env = read_env()
    if not force and env.get("EMAIL_NOTIFICATIONS", "false").lower() != "true":
        return
    required = ["NOTIFICATION_EMAIL", "SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD"]
    missing = [key for key in required if not env.get(key)]
    if missing:
        if force:
            raise ValueError("請先填妥通知信箱、SMTP 伺服器、寄件帳號和密碼")
        logger.warning("Email notifications are enabled but settings are missing: %s", ", ".join(missing))
        return

    lines = [f"{b['title']} — ${b['reward']:,.0f}\n{b['repository']}\n{b['issue_url']}" for b in bounties]
    message = EmailMessage()
    message["Subject"] = f"Bounty Bot：發現 {len(bounties)} 個新懸賞"
    message["From"] = env["SMTP_USERNAME"]
    message["To"] = env["NOTIFICATION_EMAIL"]
    message.set_content("發現以下新懸賞：\n\n" + "\n\n".join(lines))
    port = int(env.get("SMTP_PORT") or 587)
    smtp_class = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with smtp_class(env["SMTP_HOST"], port, timeout=20) as smtp:
        if port != 465:
            smtp.starttls()
        smtp.login(env["SMTP_USERNAME"], env["SMTP_PASSWORD"])
        smtp.send_message(message)


def send_test_email() -> None:
    send_bounty_notifications([{
        "title": "郵件通知測試",
        "reward": 0,
        "repository": "Bounty Bot",
        "issue_url": "http://localhost:8000",
    }], force=True)


# ==================== Run store ====================


class RunStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, dict] = {}
        self._load()

    # -------- persistence --------
    # Every mutation below saves the full run table back to RUNS_PATH so a
    # backend restart (routine during development, or a crash) doesn't
    # silently lose the earnings/completion history - previously this store
    # was purely in-memory and every restart reset "執行紀錄" to empty.

    def _load(self) -> None:
        if not RUNS_PATH.exists():
            return
        try:
            raw = json.loads(RUNS_PATH.read_text(encoding="utf-8"))
            for run_id, run in raw.items():
                run["started_at"] = datetime.fromisoformat(run["started_at"])
                if run.get("status") == "running":
                    # Its background thread died with the previous process -
                    # nothing will ever move it out of "running" again, which
                    # would otherwise show as a permanently spinning run.
                    run["status"] = "failed"
                    run["error_message"] = "伺服器重新啟動時此任務仍在執行中，狀態未知，請重試"
                    for stage in run["stages"]:
                        if stage["status"] == "running":
                            stage["status"] = "failed"
                self._runs[run_id] = run
            logger.info(f"Loaded {len(self._runs)} run(s) from {RUNS_PATH}")
            self._save_locked()  # persist any "running" -> "failed" correction above
        except Exception:
            logger.exception(f"Failed to load run history from {RUNS_PATH}; starting empty")

    def _save_locked(self) -> None:
        # Caller must already hold self._lock.
        try:
            RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                run_id: {**run, "started_at": run["started_at"].isoformat()}
                for run_id, run in self._runs.items()
            }
            tmp_path = RUNS_PATH.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(RUNS_PATH)  # atomic on both POSIX and Windows
        except Exception:
            logger.exception(f"Failed to save run history to {RUNS_PATH}")

    # -------- mutations --------

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
            "duplicate_pr": False,
            "error_message": None,
            "logs": [],
        }
        with self._lock:
            self._runs[run_id] = run
            self._save_locked()
        return run

    def get(self, run_id: str) -> Optional[dict]:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> list[dict]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda r: r["started_at"], reverse=True)

    def pr_url_for_bounty(self, bounty_id: str) -> Optional[str]:
        """Most recent submitted PR URL for a bounty, if any run has one.

        Covers both a run that actually submitted a new PR and one that hit
        an already-open PR (duplicate_pr) - either way there's a real PR the
        bounty list should point at instead of letting it get resubmitted.
        """
        with self._lock:
            candidates = [
                run for run in self._runs.values()
                if run.get("bounty_id") == bounty_id and run.get("pr_url")
            ]
            if not candidates:
                return None
            return max(candidates, key=lambda r: r["started_at"])["pr_url"]

    def update_stage(self, run_id: str, stage_key: str, status: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            for stage in run["stages"]:
                if stage["key"] == stage_key:
                    stage["status"] = status
                    break
            self._save_locked()

    def reset_stages(self, run_id: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run["stages"] = fresh_stages()
            run["status"] = "running"
            run["error_message"] = None
            run["duplicate_pr"] = False
            self._save_locked()

    def set_status(self, run_id: str, status: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                run["status"] = status
                self._save_locked()

    def set_error(self, run_id: str, message: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                run["error_message"] = message
                self._save_locked()

    def set_pr_url(self, run_id: str, url: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                run["pr_url"] = url
                self._save_locked()

    def set_duplicate_pr(self, run_id: str, value: bool = True) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                run["duplicate_pr"] = value
                self._save_locked()

    def delete(self, run_id: str) -> bool:
        with self._lock:
            if run_id not in self._runs:
                return False
            del self._runs[run_id]
            self._save_locked()
            return True

    def append_log(self, run_id: str, message: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                run["logs"].append(message)
                self._save_locked()


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
