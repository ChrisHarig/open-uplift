from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class SelfReport(BaseModel):
    session_id: Optional[str] = None
    tool_source: str = "claude_code"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    speedup_factor: Optional[float] = Field(default=None, ge=0.1, le=100.0)
    # Legacy fields — kept for backward compat, all optional now
    task_type: str = ""
    complexity: str = ""
    duration_minutes: int = Field(default=0, ge=0)
    perceived_speedup_pct: int = Field(default=0, ge=0, le=100)
    ai_quality_rating: int = Field(default=0, ge=0, le=5)
    notes: str = ""


class MessageData(BaseModel):
    session_id: str
    request_id: Optional[str] = None
    timestamp: str
    role: str
    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_create_tokens: int = 0
    cost_usd: float = 0.0
    tool_names: Optional[str] = None


class SharingConfig(BaseModel):
    level: int = 1  # 1 = aggregates only, 2 = aggregates + per-session summaries
    stats: dict = Field(default_factory=lambda: {
        "tokens": True,
        "cost": True,
        "messages": True,
        "tool_calls": True,
        "uplift": True,
        "compacted_transcripts": False,
        "full_transcripts": False,
    })


class OrgMembership(BaseModel):
    org_id: str
    org_name: Optional[str] = None
    member_name: Optional[str] = None
    role: str = "member"
    git_repo_url: Optional[str] = None
    git_auth_token: Optional[str] = None
    local_path: Optional[str] = None
    sharing_config: Optional[dict] = None
    last_push_at: Optional[str] = None
    last_pull_at: Optional[str] = None
    config_changed: int = 0
    joined_at: Optional[str] = None


class SessionData(BaseModel):
    session_id: str
    tool_source: str = "claude_code"
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    git_branch: Optional[str] = None
    started_at: str = ""
    ended_at: Optional[str] = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_create_tokens: int = 0
    total_cost_usd: float = 0.0
    message_count: int = 0
    tool_call_count: int = 0
    model_primary: Optional[str] = None
    continued_from: Optional[str] = None
    continuation_type: Optional[str] = None
