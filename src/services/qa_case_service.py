from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_log import AuditLog
from src.models.qa_case import QaCase
from src.models.qa_case_schemas import AuditLogListResponse, AuditLogResponse, QaCaseListResponse, QaCaseResponse
from src.repositories.audit_repository import AuditRepository
from src.repositories.qa_case_repository import QaCaseRepository

_LOCAL_CASE_EXPLANATIONS = {
    "wrong_class": (
        "Ground truth và prediction đang khác class hoặc không khớp đủ tốt; hãy đối chiếu đối tượng trong ảnh trước khi sửa nhãn.",
        "Mở 2D Editor để kiểm tra class và bounding box.",
    ),
    "missing_object": (
        "Model phát hiện một vùng có confidence đáng kể nhưng chưa có ground-truth tương ứng.",
        "Mở 2D Editor và bổ sung annotation nếu đối tượng thuộc phạm vi đánh giá.",
    ),
    "box_misalignment": (
        "Ground truth và prediction có thể cùng đối tượng nhưng bounding box chưa khớp tốt.",
        "Điều chỉnh bounding box trong 2D Editor để bao phủ đúng đối tượng.",
    ),
    "duplicate_annotation": (
        "Có dấu hiệu annotation chồng lấp hoặc trùng lặp cho cùng đối tượng.",
        "Giữ annotation chính xác và xoá nhãn trùng trong 2D Editor.",
    ),
}


def _display_explanation_and_recommendation(qa_case: QaCase) -> tuple[dict[str, Any], str]:
    evidence = deepcopy(qa_case.evidence_json or {})
    summary = evidence.get("summary")
    if not isinstance(summary, str) or "GOOGLE_API_KEY" not in summary:
        return evidence, qa_case.recommendation
    explanation, recommendation = _LOCAL_CASE_EXPLANATIONS.get(
        qa_case.error_type,
        (
            "Agent đã phát hiện một sai lệch cần được kiểm tra dựa trên evidence của case.",
            "Kiểm tra evidence và sửa annotation trong 2D Editor nếu cần.",
        ),
    )
    evidence["summary"] = explanation
    return evidence, recommendation


class QaCaseService:
    def __init__(self, qa_case_repository: QaCaseRepository | None = None, audit_repository: AuditRepository | None = None) -> None:
        self._qa_cases = qa_case_repository or QaCaseRepository()
        self._audit = audit_repository or AuditRepository()

    async def list_cases(
        self,
        session: AsyncSession,
        *,
        status: str | None,
        sequence_id: str | None,
        min_risk: int | None,
        limit: int,
        offset: int,
        dataset_id: str | None = None,
        source_split: str | None = None,
        source_image_id: str | None = None,
    ) -> QaCaseListResponse:
        count, cases = await self._qa_cases.list(
            session,
            status=status,
            sequence_id=sequence_id,
            dataset_id=dataset_id,
            source_split=source_split,
            source_image_id=source_image_id,
            min_risk=min_risk,
            limit=limit,
            offset=offset,
        )
        return QaCaseListResponse(count=count, results=[self.to_response(item) for item in cases], limit=limit, offset=offset)

    async def get_case(self, session: AsyncSession, case_id: str) -> QaCaseResponse | None:
        qa_case = await self._qa_cases.get(session, case_id)
        return self.to_response(qa_case) if qa_case is not None else None

    async def update_status(
        self,
        session: AsyncSession,
        case_id: str,
        *,
        status: str,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> QaCaseResponse | None:
        qa_case = await self._qa_cases.get(session, case_id)
        if qa_case is None:
            return None
        if qa_case.status == status:
            return self.to_response(qa_case)
        allowed = {
            "unreviewed": {"in_review", "confirmed", "rejected", "skipped"},
            "in_review": {"confirmed", "rejected", "skipped"},
            "skipped": {"in_review", "confirmed", "rejected"},
            "corrected": {"confirmed", "in_review"},
            "confirmed": {"in_review"},
            "rejected": {"in_review"},
        }
        if status not in allowed.get(qa_case.status, set()):
            raise ValueError(f"QA case {case_id} cannot move from '{qa_case.status}' to '{status}'.")
        now = datetime.now(UTC)
        previous = qa_case.status
        qa_case.status = status
        qa_case.updated_at = now
        metadata = {"source": "qa_queue"}
        if reason:
            metadata["reason"] = reason
        session.add(
            AuditLog(
                id=str(uuid4()),
                case_id=qa_case.id,
                event_type="case_status_changed",
                actor_type="user",
                actor_id=actor_id,
                before_json={"status": previous},
                after_json={"status": status},
                metadata_json=metadata,
                created_at=now,
            )
        )
        await session.commit()
        return self.to_response(qa_case)

    async def get_audit(self, session: AsyncSession, case_id: str) -> AuditLogListResponse | None:
        if await self._qa_cases.get(session, case_id) is None:
            return None
        count, events = await self._audit.list_for_case(session, case_id)
        return AuditLogListResponse(count=count, results=[self.audit_to_response(event) for event in events])

    @staticmethod
    def to_response(qa_case: QaCase) -> QaCaseResponse:
        evidence, recommendation = _display_explanation_and_recommendation(qa_case)
        return QaCaseResponse(
            id=qa_case.id,
            dataset_id=qa_case.dataset_id,
            dataset_version=qa_case.dataset_version,
            source_split=qa_case.source_split,
            source_image_id=qa_case.source_image_id,
            evaluation_id=qa_case.evaluation_id,
            sequence_id=qa_case.sequence_id,
            frame_index=qa_case.frame_index,
            frame_file_name=qa_case.frame_file_name,
            class_name=qa_case.class_name,
            target_track_id=qa_case.target_track_id,
            error_type=qa_case.error_type,
            risk_score=qa_case.risk_score,
            priority=qa_case.priority,
            status=qa_case.status,
            evidence=evidence,
            recommendation=recommendation,
            assigned_to=qa_case.assigned_to,
            created_at=qa_case.created_at,
            updated_at=qa_case.updated_at,
        )

    @staticmethod
    def audit_to_response(event: AuditLog) -> AuditLogResponse:
        return AuditLogResponse(
            id=event.id,
            case_id=event.case_id,
            event_type=event.event_type,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            before=event.before_json,
            after=event.after_json,
            metadata=event.metadata_json,
            created_at=event.created_at,
        )
