from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, get_db_session, require_roles
from src.models.auth_schemas import AuthenticatedUser
from src.models.qa_case_schemas import AuditLogListResponse, QaCaseListResponse, QaCaseResponse, QaCaseStatus
from src.services.qa_case_service import QaCaseService

router = APIRouter(
    prefix="/qa-cases",
    tags=["QA Cases"],
    dependencies=[Depends(get_current_user)],
)


class QaCaseStatusRequest(BaseModel):
    status: Literal["in_review", "confirmed", "rejected", "skipped"]
    actor_id: str | None = Field(default=None, max_length=128)
    reason: str | None = Field(default=None, max_length=2000)


@router.get("", response_model=QaCaseListResponse)
async def list_qa_cases(
    status: QaCaseStatus | None = Query(default=None),
    sequence_id: str | None = Query(default=None, alias="sequenceId"),
    dataset_id: str | None = Query(default=None, alias="datasetId"),
    source_split: str | None = Query(default=None, alias="split"),
    source_image_id: str | None = Query(default=None, alias="sourceImageId"),
    min_risk: int | None = Query(default=None, alias="minRisk", ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> QaCaseListResponse:
    return await QaCaseService().list_cases(
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


@router.get("/{case_id}", response_model=QaCaseResponse)
async def get_qa_case(case_id: str, session: AsyncSession = Depends(get_db_session)) -> QaCaseResponse:
    qa_case = await QaCaseService().get_case(session, case_id)
    if qa_case is None:
        raise HTTPException(status_code=404, detail="QA case was not found")
    return qa_case


@router.post("/{case_id}/status", response_model=QaCaseResponse)
async def update_qa_case_status(
    case_id: str,
    request: QaCaseStatusRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_roles("reviewer", "admin"))],
    session: AsyncSession = Depends(get_db_session),
) -> QaCaseResponse:
    try:
        result = await QaCaseService().update_status(
            session,
            case_id,
            status=request.status,
            actor_id=current_user.id,
            reason=request.reason,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=404, detail="QA case was not found")
    return result


@router.get("/{case_id}/audit", response_model=AuditLogListResponse)
async def get_qa_case_audit(case_id: str, session: AsyncSession = Depends(get_db_session)) -> AuditLogListResponse:
    audit = await QaCaseService().get_audit(session, case_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="QA case was not found")
    return audit
