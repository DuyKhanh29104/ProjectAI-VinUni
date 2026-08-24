from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.models.audit_log import AuditLog
from src.models.qa_case import QaCase
from src.services.qa_case_service import QaCaseService


def make_case(case_id: str, risk_score: int, status: str = "unreviewed") -> QaCase:
    timestamp = datetime(2026, 8, 9, tzinfo=UTC)
    return QaCase(
        id=case_id, dataset_id="label-guardian-mini", dataset_version="1.0",
        source_split="val", source_image_id="000001", evaluation_id=None,
        sequence_id="seq-001", frame_index=2, frame_file_name="frame_0002.png",
        class_name="car", target_track_id="car-main", error_type="box_misalignment",
        risk_score=risk_score, priority="high", status=status,
        evidence_json={"summary": "evidence"}, recommendation="Review in 2D Editor.",
        assigned_to=None, created_at=timestamp, updated_at=timestamp,
    )


def test_response_replaces_legacy_llm_credential_error_with_actionable_text() -> None:
    qa_case = make_case("LG-legacy", 88)
    qa_case.evidence_json = {"summary": "KhÃ´ng láº¥y Ä‘Æ°á»£c giáº£i thÃ­ch tá»« LLM (lá»—i: GOOGLE_API_KEY is required)."}
    response = QaCaseService.to_response(qa_case)
    assert "GOOGLE_API_KEY" not in response.evidence["summary"]
    assert "2D Editor" in response.recommendation


@pytest.mark.asyncio
async def test_service_filters_cases_and_returns_append_only_audit(postgres_async_session_factory) -> None:
    async with postgres_async_session_factory() as session:
        high_case = make_case("LG-0001", 88)
        session.add_all([high_case, make_case("LG-0002", 50, status="confirmed")])
        session.add(AuditLog(id=str(uuid4()), case_id=high_case.id, event_type="case_created", actor_type="system", actor_id="test", before_json=None, after_json={"status": "unreviewed"}, metadata_json={"source": "test"}, created_at=high_case.created_at))
        await session.commit()
    service = QaCaseService()
    async with postgres_async_session_factory() as session:
        result = await service.list_cases(session, status="unreviewed", sequence_id=None, min_risk=80, limit=20, offset=0)
        audit = await service.get_audit(session, "LG-0001")
    assert result.count == 1
    assert result.results[0].source_image_id == "000001"
    assert audit is not None and audit.results[0].event_type == "case_created"
