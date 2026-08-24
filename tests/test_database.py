import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_async_database_session_executes_query(postgres_async_session_factory) -> None:
    async with postgres_async_session_factory() as session:
        assert await session.scalar(text("SELECT 1")) == 1
