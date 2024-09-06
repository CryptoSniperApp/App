import asyncio
from datetime import datetime
import decimal
import random
import time

from loguru import logger
import solana
import solana.exceptions
import solana.rpc
from solana_snipping.backend.db import create_async_sessiomaker, setup
from solana_snipping.backend.db.repositories import AnalyticRepository
from solana_snipping.backend.solana import SolanaChain
from solana_snipping.backend.utils import get_proxies
from solana_snipping.common.constants import SOL_ADDR, solana_async_client
from solana_snipping.common.app_types import AnalyticData


class SolanaMonitor:
    def __init__(self) -> None:
        self._client = solana_async_client
        self._chain = SolanaChain()
        pass

    async def watch_pool(
        self,
        mint1: str,
        mint2: str,
        pool_id: str,
        signature_transaction: str,
        seconds_stop: float,
        min_percents: int,
        max_percents: int,
        first_added_liquidity: int | None = None,
        capture_time: datetime | None = None,
    ):
        start = time.time()
        dbsession = create_async_sessiomaker()

        if not capture_time:
            capture_time = datetime.now()

        while True:
            try:
                proxies = get_proxies()
                proxy = random.choice(proxies)

                if not first_added_liquidity:
                    first_added_liquidity = (
                        await self._chain.solscan.get_added_liquidity_value(
                            trans=signature_transaction, proxy=proxy
                        )
                    )

                # try:
                pool_open_time = await self._chain.get_transaction_time(
                    signature=signature_transaction
                )

                swap_price_first = await self._chain.raydium.get_swap_price(
                    mint1=mint1,
                    mint2=SOL_ADDR,
                    decimals=9,
                    amount=0.77,
                    base_out=True,
                    proxy=proxy,
                )

                async with dbsession() as session:
                    repo = AnalyticRepository(session)
                    while True:
                        if time.time() - start >= seconds_stop:
                            return

                        swap_time = datetime.now()
                        swap_price = await self._chain.raydium.get_swap_price(
                            mint1=mint1,
                            mint2=SOL_ADDR,
                            decimals=9,
                            amount=0.77,
                            base_out=True,
                            proxy=proxy
                        )
                        if type(swap_price) not in (float, decimal.Decimal):
                            await asyncio.sleep(3)
                            continue

                        percentage_diff = float(
                            (swap_price - swap_price_first) / swap_price_first * 100
                        )

                        data = AnalyticData(
                            time=time.time(),
                            pool_addr=pool_id,
                            mint1_addr=mint1,
                            mint2_addr=mint2,
                            first_added_liquiduty_value=first_added_liquidity,
                            capture_time=capture_time.timestamp(),
                            pool_open_time=pool_open_time.timestamp(),
                            swap_price=swap_price,
                            swap_time=swap_time.timestamp(),
                            percentage_difference=percentage_diff
                        )

                        print(
                            f"Swap price: {swap_price}, first swap price: {swap_price_first}. Percentage diff: {percentage_diff}"
                        )
                        await repo.add_analytic(model=data)

                        if percentage_diff >= max_percents:
                            # We are sell token
                            logger.success(
                                f"We are swap token {mint1} on 0.77 SOL "
                                f"(~100 USD)"
                            )
                            return

                        elif (
                            percentage_diff < 0
                            and (percentage_diff * -1) >= min_percents
                        ):
                            # We are leave from market with token :-(
                            return

                        await asyncio.sleep(3)
            except solana.exceptions.SolanaRpcException:
                await asyncio.sleep(5)
                continue
            except Exception as e:
                logger.exception(e)
                await asyncio.sleep(2)


async def main():
    mon = SolanaMonitor()
    await setup()

    # liquidity = await mon._chain.solscan.get_added_liquidity_value("3zmhmUyjuyLsQZitoyXy96D7jiQmtVRdYZzcBvGBA7EtETSRvKBjhFD3jMvCXp1EJTMvsMkKHQf1gutEHmZAGiLN")

    await mon.watch_pool(
        mint1="2eHYigEDcXUGtDL5hcsTbbn3BiAvt12D4sunDDEdZ4cr",
        mint2="So11111111111111111111111111111111111111112",
        pool_id="FVEUcVTCHfiN6K1nk6Q4BB1Qssi2EvaH8AR39wNarXyk",
        signature_transaction="ZRJgeBGYZuDoWQPNQZT3tTQdqHfBZyJ4xfXzhT87ye5PGWWd1YQ6P7GzjtPBZXeLYH4BFv91GfV2fwKyzma1gCw",
        seconds_stop=300,
        max_percents=10,
        min_percents=200,
    )

    ...


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
