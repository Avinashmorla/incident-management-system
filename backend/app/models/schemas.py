from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ComponentType(str, Enum):
    API = "API"
    MCP_HOST = "MCP_HOST"
    CACHE = "CACHE"
    QUEUE = "QUEUE"
    RDBMS = "RDBMS"
    NOSQL = "NOSQL"


class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class WorkItemState(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class RootCauseCategory(str, Enum):
    CODE_DEPLOY = "CODE_DEPLOY"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    DATA_CORRUPTION = "DATA_CORRUPTION"
    CAPACITY = "CAPACITY"
    THIRD_PARTY = "THIRD_PARTY"
    UNKNOWN = "UNKNOWN"


class SignalIn(BaseModel):
    component_id: str = Field(..., min_length=2, max_length=120)
    component_type: ComponentType
    message: str = Field(..., min_length=1, max_length=800)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


class SignalRecord(SignalIn):
    id: str = Field(default_factory=lambda: str(uuid4()))
    work_item_id: str | None = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RCAIn(BaseModel):
    incident_start: datetime
    incident_end: datetime
    root_cause_category: RootCauseCategory
    fix_applied: str = Field(..., min_length=8)
    prevention_steps: str = Field(..., min_length=8)

    @field_validator("incident_end")
    @classmethod
    def end_must_follow_start(cls, incident_end: datetime, info):
        incident_start = info.data.get("incident_start")
        if incident_start and incident_end < incident_start:
            raise ValueError("incident_end must be after incident_start")
        return incident_end


class RCARecord(RCAIn):
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mttr_seconds: float


class WorkItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    component_id: str
    component_type: ComponentType
    severity: Severity
    status: WorkItemState = WorkItemState.OPEN
    first_signal_at: datetime
    last_signal_at: datetime
    signal_count: int = 0
    signal_ids: list[str] = Field(default_factory=list)
    alert_channel: str
    rca: RCARecord | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TransitionRequest(BaseModel):
    status: WorkItemState


class DashboardState(BaseModel):
    active: list[WorkItem]
    totals_by_severity: dict[str, int]
    signals_per_second: float


class IngestionAccepted(BaseModel):
    accepted: int
    queued: int
    rejected: int = 0
