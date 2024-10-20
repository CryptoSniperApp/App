from pydantic import BaseModel

from typing import TypeVar


N = TypeVar("N")


class AnalyticData(BaseModel):
    id: int | N = N
    time: int | float
    pool_addr: str | N = N
    mint1_addr: str | N = N
    mint2_addr: str | N = N
    first_added_liquiduty_value: str | N = N
    capture_time: float | N = N
    pool_open_time: float | N = N
    swap_time: float | N = N
    swap_price: float | N = N
    percentage_difference: float | N = N
    comment: str | N = N
    