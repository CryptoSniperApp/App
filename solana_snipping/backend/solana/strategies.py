import asyncio
from datetime import datetime
import random
import time

from loguru import logger
from solders.pubkey import Pubkey
from solders.rpc.responses import GetTransactionResp

from solana_snipping.backend.db import create_async_sessiomaker
from solana_snipping.backend.db.repositories import AnalyticRepository
from solana_snipping.backend.solana import SolanaChain
from solana_snipping.backend.solana.monitor import SolanaMonitor
from solana_snipping.backend.solana.moonshot_api import MoonshotAPI
from solana_snipping.backend.utils import format_number_decimal, get_proxies
from solana_snipping.common.app_types import AnalyticData
from solana_snipping.common.constants import SOL_ADDR
from solana_snipping.frontend.telegram.alerting import send_msg_log
from solana_snipping.backend.utils import asyncio_callbacks


class FilterRaydiumPools:
    def __init__(self) -> None:
        self._client = SolanaChain()
        self._raydium_client = self._client.raydium

    async def __call__(
        self, mint1: str, mint2: str, pair_mint: str, signature: str
    ) -> bool:
        if mint1.endswith("pump") or mint2.endswith("pump"):
            return False

        liquidity, wallet_addr = await asyncio.gather(
            self._client.solscan.get_added_liquidity_value(signature),
            self._client.get_signer_of_transaction(signature=signature),
        )

        if liquidity <= 10_000:
            return False

        thxs = await self._client.wallet_auditor.get_finalized_signatures(
            wallet_addr=wallet_addr
        )

        if len(thxs) < 50:
            return False

        return True


class RaydiumPools:
    def __init__(self):
        self._filter_pools = FilterRaydiumPools()
        self._solana = SolanaChain()
        self._solana_monitor = SolanaMonitor()
        self._futures = []
        self._loop = asyncio.get_running_loop()

    def handle_transaction(self, signature: str, transaction_received: datetime):
        f = asyncio.eager_task_factory(
            loop=self._loop,
            coro=self._handle_transaction(signature, transaction_received),
        )
        f.add_done_callback(asyncio_callbacks.raise_exception_if_set)
        self._futures.append(f)

    async def _handle_transaction(self, signature: str, transaction_received: datetime):
        parsed_transaction = await self._solana.get_transaction_parsed(
            signature=signature
        )
        mint1, mint2, pair = await self._solana.raydium.extract_mints_from_transaction(
            parsed_transaction
        )

        # if not await self._filter_pools(
        #     mint1, mint2, pair, signature=signature
        # ):  # If check filter not passed
        #     return

        await self._process_data(
            mint1=mint1,
            mint2=mint2,
            pool_id=pair,
            transaction_received=transaction_received,
            signature_transaction=signature,
        )

    async def _process_data(
        self,
        mint1: str,
        mint2: str,
        pool_id: str,
        transaction_received: datetime,
        signature_transaction: str,
    ):
        mint1, mint2 = (
            mint1 if not mint1.startswith("So1") else mint2,
            mint1 if mint1.startswith("So1") else mint2,
        )

        solana = self._solana
        raydium = solana.raydium

        proxies = get_proxies()
        proxy = random.choice(proxies)

        first_added_liquidity = None
        try:
            for _proxy in [None, proxy]:
                first_added_liquidity = await solana.solscan.get_added_liquidity_value(
                    signature_transaction, proxy=_proxy
                )
                pool_raydium = format_number_decimal(first_added_liquidity)
        except Exception as e:
            logger.exception(e)
            pool_raydium = None

        try:
            parsed_pool_data = await solana.solclient.get_account_info(
                Pubkey.from_string(pool_id), commitment="finalized"
            )
            volume_of_pool = await solana.raydium.get_volume_of_pool(
                parsed_pool_data.value.data
            )
            volume_of_pool = format_number_decimal(volume_of_pool)
        except Exception as e:
            logger.exception(e)
            volume_of_pool = None

        try:
            decimals = await solana.get_token_decimals(mint_addr=mint1)
            for _proxy in [None, proxy]:
                price = await raydium.get_swap_price(
                    mint1=mint1, mint2=SOL_ADDR, decimals=decimals, proxy=_proxy
                )
                if isinstance(price, str):
                    raise ValueError

                price = format_number_decimal(price)
        except Exception as e:
            logger.exception(e)
            price = "Не удалось получить цену"

        # Buy here
        capture_time = datetime.now()
        message = (
            f"Адрес - *{mint1}*\n"
            f"Поймали транзакцию в _{transaction_received}_, купили монету в _{capture_time}_.\n\n"
            f"Первая ликвидность: *{pool_raydium}* USD.\n"
            f"Объем пула сейчас: *{volume_of_pool}* USD.\n"
            f"Купили по цене: 1 token = *{price}* SOL\n"
        )
        await send_msg_log(message, mint1, trans=signature_transaction)

        monitor = self._solana_monitor
        minutes_watch = 10 * 60  # 10 hours
        await monitor.watch_pool(
            mint1=mint1,
            mint2=mint2,
            pool_id=pool_id,
            signature_transaction=signature_transaction,
            seconds_stop=60 * minutes_watch,
            capture_time=capture_time,
            first_added_liquidity=float(first_added_liquidity)
            if first_added_liquidity
            else None,
            min_percents=200,
            max_percents=20,
        )

    def subscribe_to_raydium_mints_create(self, queue: asyncio.Queue):
        loop = asyncio.get_running_loop()
        f = asyncio.eager_task_factory(
            loop=loop, coro=self._solana.raydium.subscribe_to_new_pools(queue=queue)
        )
        f.add_done_callback(asyncio_callbacks.raise_exception_if_set)
        self._futures.append(f)


class Moonshot:
    def __init__(self):
        self._solana = SolanaChain()
        self._solana_monitor = SolanaMonitor()
        self._moonshot_client = MoonshotAPI()
        self._loop = asyncio.get_running_loop()
        self._futures = []

    def handle_transaction(
        self, signature: str, transaction_received: datetime, mint: str
    ):
        f = asyncio.eager_task_factory(
            loop=self._loop,
            # coro=self._handle_transaction(signature, transaction_received),
            coro=self._process_data(mint, transaction_received, signature),
        )
        f.add_done_callback(asyncio_callbacks.raise_exception_if_set)
        self._futures.append(f)

    async def _handle_transaction(self, signature: str, transaction_received: datetime):
        parsed_transaction = await self._solana.get_transaction_parsed(
            signature=signature
        )
        mint = await self._moonshot_client.extract_mint_from_transaction(
            parsed_transaction
        )
        if mint is None:
            logger.error(
                f"Не удалось получить mint из транзакции {signature}. Moonshot API"
            )
            return

        await self._process_data(
            mint=mint,
            transaction_received=transaction_received,
            signature_transaction=signature,
        )

    async def _process_data(
        self,
        mint: str,
        transaction_received: datetime,
        signature_transaction: str,
    ):
        queue = asyncio.Queue()
        self._moonshot_client._mints_price_watch_queues.append(queue)
        try:
            async with asyncio.timeout(60):
                obj = await queue.get()
                prices = {
                    "usd": obj["Trade"]["PriceInUSD"],
                    "sol": obj["Trade"]["Price"],
                }
                first_swap_price = float(prices["usd"])
        except Exception as e:
            logger.exception(e)
            return

        # Buy here
        capture_time = datetime.now()
        try:
            first_usd_price = format_number_decimal(prices["usd"])
        except Exception:
            first_usd_price = prices["usd"]
        
        message = (
            f"ТИП - MOONSHOT DEXSCREENER\n"
            f"Адрес токена - *{mint}*\n\n"
            f"Поймали транзакцию в _{transaction_received}_, купили монету в _{capture_time}_.\n\n"
            f"Купили по цене: 1 token = *{first_usd_price}* USD\n"
        )
        await send_msg_log(message, mint, trans=signature_transaction)

        seconds_watch = 60 * 60 * 10  # 10 hours
        min_percents = 200
        max_percents = 20
        dbsession = create_async_sessiomaker()

        try:
            session = dbsession()
            await session.__aenter__()
            repo = AnalyticRepository(session)
            
            async with asyncio.timeout(seconds_watch):
                while True:
                    try:
                        data = await queue.get()

                        price = data["Trade"]["PriceInUSD"]
                        percentage_diff = (
                            (price - first_swap_price) / first_swap_price * 100
                        )

                        data = AnalyticData(
                            time=time.time(),
                            mint1_addr=mint,
                            capture_time=capture_time.timestamp(),
                            swap_price=price,
                            swap_time=datetime.now().timestamp(),
                            percentage_difference=percentage_diff,
                        )
                        
                        await repo.add_analytic(data)

                        logger.info(
                            f"Swap price: {first_swap_price}, first swap price: {price}. Percentage diff: {percentage_diff}. mint - {mint}"
                        )

                        if percentage_diff >= max_percents:
                            # We are sell token
                            logger.success(f"We are swap token {mint}. Data - {data}")
                            return

                        elif percentage_diff < 0 and (percentage_diff * -1) >= min_percents:
                            # We are leave from market with token :-(
                            logger.warning(
                                "We leave from monitor because percentage"
                                f" difference: {percentage_diff}"
                            )
                            return

                    except Exception as e:
                        logger.exception(e)
                        await asyncio.sleep(2)
        finally:
            await session.__aexit__(None, None, None)
            self._moonshot_client._mints_price_watch_queues.remove(queue)
            self._moonshot_client._mints_price_watch.remove(mint)

    def subscribe_to_moonshot_mints_create(self, queue: asyncio.Queue):
        loop = asyncio.get_running_loop()

        for coro in [
            self._moonshot_client.subscribe_to_dexscreener_moonshot_mints_create(
                queue=queue
            ),
            self._moonshot_client._scan_prices_of_mints(),
        ]:
            f = asyncio.eager_task_factory(loop=loop, coro=coro)
            f.add_done_callback(asyncio_callbacks.raise_exception_if_set)
            self._futures.append(f)


async def main():
    r = RaydiumPools()
    r.handle_transaction(
        "3Eu37kxtEz4bekqcwiGAXpUbE21EybKFd8jYWX9p9tbDyysYkcsrYMYTFaeHo8dQphSRDyfz8eFFzCVsX2uGeUbF",
        datetime.now(),
    )

    while True:
        await asyncio.sleep(1)

    return

    m = Moonshot()
    # await m.handle_transaction(
    #     "5tYcPCbyH1hZKPcS8Q3BxhSbx8ZfbCEj1sC2MG9uL6ar9UpunXmGeCyW6h4kH4UgAHShSf4vCHtg8N2tQw5q9eci",
    #     datetime.now(),
    # )
    queue = asyncio.Queue()
    m.subscribe_to_moonshot_mints_create(queue)

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
