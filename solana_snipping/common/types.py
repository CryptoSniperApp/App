from pydantic import BaseModel

from typing import TypeAlias



SQLALCHEMY_NULL: TypeAlias = None


class AnalyticData(BaseModel):
    id: int | SQLALCHEMY_NULL
    time: int
    pool_addr: str
    mint1_addr: str
    mint2_addr: str
    first_added_liquiduty_value: str
    capture_time: float
    pool_open_time: float
    buy_time: float
    buy_price: float
    sell_time: float
    sell_price: float

