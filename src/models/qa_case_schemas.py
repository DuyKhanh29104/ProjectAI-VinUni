from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from src.models.base_schemas import ApiModel

QaCaseStatus = Literal[
    "unreviewed",
    "in_review",
    "confirmed",
    "corrected",
    "rejected",
    "skipped",
]
QaCasePriority = Literal["low", "medium", "high", "critical"]


class QaCaseResponse(ApiModel):
    id: str
    dataset_id: str
    dataset_version: str
    source_split: str | None = None
    source_image_id: str | None = None
    evaluation_id: str | None = None
    sequence_id: str
    frame_index: int
    frame_file_name: str
    class_name: str
    target_track_id: str | None = None
    error_type: str
    risk_score: int
    priority: QaCasePriority
    status: QaCaseStatus
    evidence: dict[str, Any]
    recommendation: str
    assigned_to: str | None = None
    created_at: datetime
    updated_at: datetime


class QaCaseListResponse(ApiModel):
    count: int
    results: list[QaCaseResponse]
    limit: int
    offset: int


class AuditLogResponse(ApiModel):
    id: str
    case_id: str
    event_type: str
    actor_type: Literal["user", "system", "agent"]
    actor_id: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AuditLogListResponse(ApiModel):
    count: int
    results: list[AuditLogResponse]
