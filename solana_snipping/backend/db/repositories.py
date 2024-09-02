from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select

from solana_snipping.backend.db import AnalyticData
from solana_snipping.common.app_types import N


def convert_type(model: BaseModel):
    obj = model.model_dump()
    for field in model.model_fields:
        if getattr(model, field) == N:
            del obj[field]
    return obj



class AnalyticRepository:
    _model = AnalyticData
    
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
    
    async def _execute_stmt(self, stmt, commit: bool = True):
        conn = await self._session.connection()
        result = await conn.execute(stmt)
        if commit:
            await conn.commit()
        return result
        
    async def add_analytic(self, model: AnalyticData, commit: bool = True):
        values = convert_type(model)
        stmt = insert(self._model).values(**values)
        return await self._execute_stmt(stmt, commit)
        
    async def get_analytic(self, *where_clause):
        stmt = select(self._model).where(*where_clause)
        return await self._execute_stmt(stmt)

