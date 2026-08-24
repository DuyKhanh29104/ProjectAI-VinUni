from typing import cast

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.qa_case import QaCase


class QaCaseRepository:
    async def get(self, session: AsyncSession, case_id: str) -> QaCase | None:
        return cast(QaCase | None, await session.get(QaCase, case_id))

    async def list(
        self,
        session: AsyncSession,
        *,
        status: str | None = None,
        sequence_id: str | None = None,
        dataset_id: str | None = None,
        source_split: str | None = None,
        source_image_id: str | None = None,
        min_risk: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[QaCase]]:
        query: Select[tuple[QaCase]] = select(QaCase)
        count_query = select(func.count()).select_from(QaCase)
        conditions = []
        if status is not None:
            conditions.append(QaCase.status == status)
        if sequence_id is not None:
            conditions.append(QaCase.sequence_id == sequence_id)
        if dataset_id is not None:
            conditions.append(QaCase.dataset_id == dataset_id)
        if source_split is not None:
            conditions.append(QaCase.source_split == source_split)
        if source_image_id is not None:
            conditions.append(QaCase.source_image_id == source_image_id)
        if min_risk is not None:
            conditions.append(QaCase.risk_score >= min_risk)
        if conditions:
            query = query.where(*conditions)
            count_query = count_query.where(*conditions)

        query = query.order_by(QaCase.risk_score.desc(), QaCase.id.asc()).limit(limit).offset(offset)
        count = int((await session.execute(count_query)).scalar_one())
        cases = list((await session.execute(query)).scalars().all())
        return count, cases

    def add(self, session: AsyncSession, qa_case: QaCase) -> None:
        session.add(qa_case)
