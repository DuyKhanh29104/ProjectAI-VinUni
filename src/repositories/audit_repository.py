from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_log import AuditLog


class AuditRepository:
    async def list_for_case(
        self,
        session: AsyncSession,
        case_id: str,
    ) -> tuple[int, list[AuditLog]]:
        count_query = select(func.count()).select_from(AuditLog).where(AuditLog.case_id == case_id)
        query = (
            select(AuditLog)
            .where(AuditLog.case_id == case_id)
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        )
        count = int((await session.execute(count_query)).scalar_one())
        events = list((await session.execute(query)).scalars().all())
        return count, events

    def add(self, session: AsyncSession, event: AuditLog) -> None:
        session.add(event)
