from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select

from solana_snipping.backend.db import AnalyticData, Cache
from solana_snipping.common.app_types import N, CacheData


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
        
    async def add(self, model: AnalyticData, commit: bool = True):
        values = convert_type(model)
        stmt = insert(self._model).values(**values)
        return await self._execute_stmt(stmt, commit)
        
    async def get(self, *where_clause):
        stmt = select(self._model).where(*where_clause)
        return await self._execute_stmt(stmt)

class CacheRepository(AnalyticRepository):
    _model = Cache
    
    async def add(self, model: CacheData, commit: bool = True):
        return await super().add(model, commit=commit)
    
    async def get_all(self) -> list[CacheData | None]:
        stmt = select(self._model)
        res = await self._execute_stmt(stmt)
        if res:
            results = res.fetchall()
            return [CacheData(**row._asdict()) for row in results]
            
        return []
