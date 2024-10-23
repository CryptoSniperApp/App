import os
from sqlalchemy.orm import  Mapped, mapped_column, DeclarativeBase
from sqlalchemy import Integer, String, Float
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class Base(DeclarativeBase): ...


class AnalyticData(Base):
    __tablename__ = "analytic"
    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    time: Mapped[int] = mapped_column(Integer, autoincrement=False)
    pool_addr: Mapped[str] = mapped_column(String, nullable=True)
    mint1_addr: Mapped[str] = mapped_column(String, nullable=True)
    mint2_addr: Mapped[str] = mapped_column(String, nullable=True)
    first_added_liquiduty_value: Mapped[str] = mapped_column(String, nullable=True)
    capture_time: Mapped[float] = mapped_column(Float, nullable=True)
    pool_open_time: Mapped[float] = mapped_column(Float, nullable=True)
    swap_time: Mapped[float] = mapped_column(Float, nullable=True)
    swap_price: Mapped[float] = mapped_column(Float, nullable=True)
    percentage_difference: Mapped[float] = mapped_column(Float, nullable=True)
    comment: Mapped[str] = mapped_column(String, nullable=True)
    meta: Mapped[str] = mapped_column(String, nullable=True)


def create_async_sessiomaker():
    url = "sqlite+aiosqlite:///database.db"
    eng = create_async_engine(url)
    return async_sessionmaker(eng, expire_on_commit=False)


async def setup():
    if not os.path.exists("database.db"):
        with open("database.db", "w"):
            pass
        
    eng = create_async_sessiomaker()().bind
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
