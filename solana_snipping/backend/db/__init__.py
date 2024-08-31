from sqlalchemy.orm import  Mapped, mapped_column, DeclarativeBase
from sqlalchemy import Integer, String, Float, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession


class Base(DeclarativeBase): ...


class AnalyticData(Base):
    __tablename__ = "analytic"
    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    time: Mapped[int] = mapped_column(Integer, autoincrement=False)
    pool_addr: Mapped[str] = mapped_column(String)
    mint1_addr: Mapped[str] = mapped_column(String)
    mint2_addr: Mapped[str] = mapped_column(String)
    first_added_liquiduty_value: Mapped[str] = mapped_column(String)
    capture_time: Mapped[float] = mapped_column(Float)
    pool_open_time: Mapped[float] = mapped_column(Float)
    buy_time: Mapped[float] = mapped_column(Float)
    buy_price: Mapped[float] = mapped_column(Float)
    sell_time: Mapped[float] = mapped_column(Float)
    sell_price: Mapped[float] = mapped_column(Float)


def create_async_sessiomakern():
    url = "sqlite+aiosqlite:///database.db"
    eng = create_async_engine(url)
    return async_sessionmaker(eng, expire_on_commit=False)
