from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select

from solana_snipping.backend.db import AnalyticData


class AnalyticRepository:
    _model = AnalyticData
    
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
    
    async def _execute_stmt(self, stmt):
        conn = await self._session.connection()
        await conn.execute(stmt)
        
    async def add_analytic(self, model: AnalyticData):
        stmt = insert(self._model).values(model)

