from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from src.config import Settings
from src.main import create_app
from src.models.audit_log import AuditLog
from src.models.qa_case import QaCase


def make_case(case_id: str, risk_score: int, status: str = "unreviewed") -> QaCase:
    timestamp = datetime(2026, 8, 9, tzinfo=UTC)
    return QaCase(
        id=case_id, dataset_id="label-guardian-mini", dataset_version="1.0",
        source_split="val", source_image_id="000001", evaluation_id=None,
        sequence_id="seq-001", frame_index=2, frame_file_name="frame_0002.png",
        class_name="car", target_track_id="car-main", error_type="box_misalignment",
        risk_score=risk_score, priority="high", status=status,
        evidence_json={"summary": "evidence"}, recommendation="Open the 2D Editor and review.",
        assigned_to=None, created_at=timestamp, updated_at=timestamp,
    )


@pytest.mark.asyncio
async def test_qa_case_list_detail_status_and_audit(postgres_async_session_factory, postgres_test_database):
    async with postgres_async_session_factory() as session:
        high_case = make_case("LG-0001", 88)
        session.add_all([high_case, make_case("LG-0002", 50, status="confirmed")])
        session.add(AuditLog(id=str(uuid4()), case_id=high_case.id, event_type="case_created", actor_type="system", actor_id="test", before_json=None, after_json={"status": "unreviewed"}, metadata_json={"source": "test"}, created_at=high_case.created_at))
        await session.commit()

    application = create_app(settings=Settings(app_env="test", database_url=postgres_test_database.async_url, _env_file=None), db_session_factory=postgres_async_session_factory)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://testserver") as client:
            listed = await client.get(
                "/api/v1/qa-cases?status=unreviewed&minRisk=80&split=val&sourceImageId=000001"
            )
            detail = await client.get("/api/v1/qa-cases/LG-0001")
            updated = await client.post("/api/v1/qa-cases/LG-0001/status", json={"status": "in_review", "actorId": "reviewer-1", "reason": "Start review"})
            audit = await client.get("/api/v1/qa-cases/LG-0001/audit")

    assert listed.status_code == 200 and listed.json()["count"] == 1
    assert detail.json()["sourceImageId"] == "000001"
    assert updated.status_code == 200 and updated.json()["status"] == "in_review"
    assert [item["eventType"] for item in audit.json()["results"]] == ["case_created", "case_status_changed"]


@pytest.mark.asyncio
async def test_qa_case_not_found_invalid_status_and_transition(postgres_async_session_factory, postgres_test_database):
    async with postgres_async_session_factory() as session:
        session.add(make_case("LG-LOCKED", 70, status="confirmed"))
        await session.commit()
    application = create_app(settings=Settings(app_env="test", database_url=postgres_test_database.async_url, _env_file=None), db_session_factory=postgres_async_session_factory)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://testserver") as client:
            missing = await client.get("/api/v1/qa-cases/missing")
            invalid = await client.get("/api/v1/qa-cases?status=invalid")
            blocked = await client.post("/api/v1/qa-cases/LG-LOCKED/status", json={"status": "rejected"})
    assert missing.status_code == 404
    assert invalid.status_code == 422
    assert blocked.status_code == 409
