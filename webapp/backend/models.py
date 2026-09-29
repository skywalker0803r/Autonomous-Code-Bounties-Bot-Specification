"""API schemas shared between the FastAPI backend and the React frontend.

Field names are snake_case in Python and serialized as camelCase JSON to
match webapp/frontend/src/types.ts.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AgentStatusOut(CamelModel):
    state: str  # "RUNNING" | "STOPPED"
    last_error: Optional[str] = None


class BountyOut(CamelModel):
    id: str
    title: str
    repository: str
    source: str
    reward: float
    language: str
    type: str
    difficulty: str
    estimated_ai_cost: float
    issue_url: str
    poster_login: Optional[str] = None
    poster_url: Optional[str] = None
    suspicion_level: str = "low"  # "low" | "medium" | "high"
    suspicion_reasons: list[str] = Field(default_factory=list)


class RunStageOut(CamelModel):
    key: str
    label: str
    status: str  # done | running | waiting | failed | skipped


class RunOut(CamelModel):
    id: str
    issue_title: str
    repository: str
    reward: float
    started_at: datetime
    status: str  # running | success | failed
    stages: list[RunStageOut]
    pr_url: Optional[str] = None
    duplicate_pr: bool = False
    error_message: Optional[str] = None
    logs: list[str]


class SolveRequest(CamelModel):
    bounty_id: str


class AdvancedSettingsOut(CamelModel):
    poll_interval_seconds: int
    docker_memory_limit: str
    docker_cpu_limit: float
    max_retries: int
    max_parallel_tests: int


class SettingsOut(CamelModel):
    github_connected: bool
    github_username: Optional[str] = None
    ai_provider: str
    api_key_set: bool
    ai_model: Optional[str] = None
    local_base_url: str = "http://127.0.0.1:11434/v1"
    local_api_key_set: bool = False
    languages: list[str]
    min_bounty: float
    max_ai_cost: float
    auto_submit_pr: bool
    email_notifications: bool = False
    notification_email: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password_set: bool = False
    advanced: AdvancedSettingsOut


class AdvancedSettingsIn(CamelModel):
    poll_interval_seconds: Optional[int] = None
    docker_memory_limit: Optional[str] = None
    docker_cpu_limit: Optional[float] = None
    max_retries: Optional[int] = None
    max_parallel_tests: Optional[int] = None


class SettingsIn(CamelModel):
    ai_provider: Optional[str] = None
    api_key: Optional[str] = None
    ai_model: Optional[str] = None
    local_base_url: Optional[str] = None
    languages: Optional[list[str]] = None
    min_bounty: Optional[float] = None
    max_ai_cost: Optional[float] = None
    auto_submit_pr: Optional[bool] = None
    email_notifications: Optional[bool] = None
    notification_email: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    advanced: Optional[AdvancedSettingsIn] = None


class GithubConnectIn(CamelModel):
    token: str


class GithubConnectOut(CamelModel):
    connected: bool
    username: Optional[str] = None
    error: Optional[str] = None


class EmailTestOut(CamelModel):
    sent: bool
    error: Optional[str] = None


class AiConnectionTestOut(CamelModel):
    connected: bool
    error: Optional[str] = None
    message: Optional[str] = None
