import asyncio
import random
import time
from datetime import datetime
from typing import TypedDict

import httpx
import solana
import solana.exceptions
import solana.rpc
from gql import gql
from gql.transport.websockets import WebsocketsTransport
from loguru import logger

from solana_snipping.backend.db import create_async_sessiomaker
from solana_snipping.backend.db.repositories import AnalyticRepository
from solana_snipping.backend.solana import SolanaChain
from solana_snipping.backend.utils import get_proxies
from solana_snipping.common.app_types import AnalyticData
from solana_snipping.common.config import get_config
from solana_snipping.common.constants import SOL_ADDR, solana_async_client
from solana_snipping.backend.utils import asyncio_callbacks


class BitQueryMintResult(TypedDict):
    mint_address: str
    """Адрес минта токена"""
    name: str | None
    """Название токена"""
    symbol: str | None
    """Символ токена"""
    success: bool
    """Флаг успешности операции"""

    price: float
    """Цена токена"""
    price_in_usd: float
    """Цена токена в USD"""

    change_amount: float
    """Изменение количества токенов"""
    change_amount_in_usd: float
    """Изменение стоимости в USD"""

    post_amount: float
    """Количество токенов после операции"""
    post_amount_in_usd: float
    """Стоимость токенов после операции в USD"""

    dex_protocol_family: str
    """Семейство протокола DEX"""
    dex_program_address: str
    """Адрес программы DEX"""

    block_time: int
    """Время блока"""
    block_slot: int
    """Номер слота блока"""

    transaction_signature: str
    """Сигнатура транзакции"""
    transaction_signer: str
    """Кто провел транзакцию"""
    instruction_program_method: str
    """Метод инструкции"""


class SolanaMonitor:
    def __init__(self) -> None:
        self._client = solana_async_client
        self._chain = SolanaChain()
        
        cfg = get_config()
        
        self._bitquery_wss = "wss://streaming.bitquery.io/eap"
        self._bitquery_token = cfg["bitquery"]["token"]
        headers = {
            "Sec-WebSocket-Protocol": "graphql-ws",
            "Content-Type": "application/json",
        }
        url = f"{self._bitquery_wss}?token={self._bitquery_token}"
        self._bitquery = WebsocketsTransport(url=url, headers=headers)

        self._mints_to_watch = []
        self._queues = []

    def add_mint_to_watch(self, mint: str):
        if mint not in self._mints_to_watch:
            self._mints_to_watch.append(mint)

    def remove_mint_to_watch(self, mint: str):
        if mint in self._mints_to_watch:
            self._mints_to_watch.remove(mint)

    def subscribe_mint_price_change(self, mint1: str, q: asyncio.Queue):
        loop = asyncio.get_running_loop()
        f = asyncio.eager_task_factory(loop, self._send_bitquery_subscription())
        f.add_done_callback(asyncio_callbacks.raise_exception_if_set)
        self.add_mint_to_watch(mint1)
        if q not in self._queues:
            self._queues.append(q)

    def unsubscribe_mint_price_change(self, mint1: str, q: asyncio.Queue):
        self.remove_mint_to_watch(mint1)
        if q in self._queues:
            try:
                self._queues.remove(q)
            except ValueError:
                pass

    async def _send_bitquery_subscription(self):
        transport = self._bitquery
        if not transport.websocket:
            await transport.connect()

        attempts = 0
        try:
            while True:
                try:
                    query = gql(
                        """
                        subscription {
                            Solana {
                                DEXPools(
                                where: {Pool: {Market: {QuoteCurrency: {MintAddress: {startsWith: "So1111111111111111111111111111111111"}}}}, Transaction: {Result: {Success: true}}}
                            ) {
                            Block {
                                Time
                            }
                            Pool {
                                Base {
                                    ChangeAmount
                                    PostAmount
                                    Price
                                    PriceInUSD
                                }
                                Dex {
                                    ProgramAddress
                                    ProtocolFamily
                                }
                                Market {
                                    BaseCurrency {
                                        MintAddress
                                        Name
                                        Symbol
                                }
                                    MarketAddress
                                }
                            }
                            Instruction {
                                Program {
                                    Method
                                }
                            }
                            Transaction {
                                Signer
                                Signature
                            }
                        }
                    }
                    }

                    """
                    )

                    async for result in transport.subscribe(query):
                        if result.errors:
                            print(f"result errors: {result.errors}")
                            continue

                        data = result.data

                        for item in data["Solana"]["DEXPools"]:
                            try:
                                block_dt = datetime.strptime(
                                    item["Block"]["Time"], "%Y-%m-%dT%H:%M:%SZ"
                                )
                            except ValueError:
                                block_dt = item["Block"]["Time"]

                            obj = BitQueryMintResult(
                                mint_address=item["Pool"]["Market"]["BaseCurrency"][
                                    "MintAddress"
                                ],
                                name=item["Pool"]["Market"]["BaseCurrency"]["Name"],
                                symbol=item["Pool"]["Market"]["BaseCurrency"]["Symbol"],
                                market_address=item["Pool"]["Market"]["MarketAddress"],
                                change_amount=item["Pool"]["Base"]["ChangeAmount"],
                                post_amount=item["Pool"]["Base"]["PostAmount"],
                                price=item["Pool"]["Base"]["Price"],
                                price_usd=item["Pool"]["Base"]["PriceInUSD"],
                                dex_program=item["Pool"]["Dex"]["ProgramAddress"],
                                dex_protocol=item["Pool"]["Dex"]["ProtocolFamily"],
                                transaction_signature=item["Transaction"]["Signature"],
                                transaction_signer=item["Transaction"]["Signer"],
                                block_time=block_dt,
                                instruction_method=item["Instruction"]["Program"][
                                    "Method"
                                ],
                            )
                            if obj["mint_address"] in self._mints_to_watch:
                                [await q.put(obj) for q in self._queues]

                except BaseException as e:
                    if attempts >= 5:
                        return
                    attempts += 1
                    logger.exception(e)
                    await asyncio.sleep(2)
        finally:
            await transport.close()

    async def watch_mint(
        self,
        mint: str,
        seconds_stop: float,
        min_percents: int,
        max_percents: int,
    ):
        start = time.time()
        q = asyncio.Queue()
        self.subscribe_mint_price_change(mint, q)
        start_price = None

        while True:
            try:
                data = await q.get()

                if not start_price:
                    start_price = data["price_usd"]

                current_price = data["price_usd"]
                percentage_diff = (current_price - start_price) / start_price * 100

                logger.info(
                    f"USD price: {current_price}, first price: {start_price}. Percentage diff: {percentage_diff}. mint - {mint}"
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
                if time.time() - start > seconds_stop:
                    self.unsubscribe_mint_price_change(mint, q)
                    return

    async def watch_pool(
        self,
        mint1: str,
        mint2: str,
        pool_id: str,
        seconds_stop: float,
        min_percents: int,
        max_percents: int,
        signature_transaction: str | None = None,
        first_added_liquidity: int | None = None,
        capture_time: datetime | None = None,
    ):
        start = time.time()
        dbsession = create_async_sessiomaker()

        if not capture_time:
            capture_time = datetime.now()

        swap_price_first = None
        pool_open_time = None
        attempts = 0

        def get_proxy():
            proxies = get_proxies()
            proxy = random.choice(proxies)
            return proxy

        async def set_first_added_liquidity():
            nonlocal first_added_liquidity

            proxy = get_proxy()
            try:
                for _proxy in [None, proxy]:
                    first_added_liquidity = (
                        await self._chain.solscan.get_added_liquidity_value(
                            trans=signature_transaction, proxy=_proxy
                        )
                    )
            except Exception as e:
                logger.exception(e)

        async def set_pool_open_time():
            nonlocal pool_open_time

            try:
                pool_open_time = await self._chain.get_transaction_time(
                    signature=signature_transaction
                )
            except Exception as e:
                logger.exception(e)

        if not first_added_liquidity and signature_transaction:
            await set_first_added_liquidity()
        if not pool_open_time and signature_transaction:
            await set_pool_open_time()

        attempts = 0
        while True:
            try:
                proxy = get_proxy()

                for _proxy in [None, proxy]:
                    swap_price_first = await self._chain.raydium.get_swap_price(
                        mint1=mint1,
                        mint2=SOL_ADDR,
                        decimals=9,
                        amount=0.77,
                        base_out=True,
                        proxy=_proxy,
                    )

                attempts = 0

            except solana.exceptions.SolanaRpcException:
                attempts += 1
                await asyncio.sleep(5)
                continue
            except (httpx.ReadError, httpx.ReadTimeout):
                attempts += 1
                await asyncio.sleep(3)
                continue
            except Exception as e:
                attempts += 1
                logger.exception(e)
                await asyncio.sleep(2)
            finally:
                if swap_price_first:
                    break
                elif attempts >= 7:
                    return

        q = asyncio.Queue()
        self.subscribe_mint_price_change(mint1, q)

        async with dbsession() as session:
            repo = AnalyticRepository(session)
            exc_count = 0
            while True:
                try:
                    _data: BitQueryMintResult = await q.get()

                    swap_time = datetime.now()
                    swap_price = 100 / _data["price_usd"]
                    percentage_diff = float(
                        (float(swap_price) - float(swap_price_first))
                        / float(swap_price_first)
                        * 100
                    )

                    data = AnalyticData(
                        time=time.time(),
                        pool_addr=pool_id,
                        mint1_addr=mint1,
                        mint2_addr=mint2,
                        capture_time=capture_time.timestamp(),
                        swap_price=swap_price,
                        swap_time=swap_time.timestamp(),
                        percentage_difference=percentage_diff,
                    )

                    if pool_open_time:
                        data.pool_open_time = pool_open_time.timestamp()
                    if first_added_liquidity:
                        data.first_added_liquiduty_value = first_added_liquidity

                    logger.info(
                        f"Swap price: {swap_price}, first swap price: {swap_price_first}. Percentage diff: {percentage_diff}. mint - {mint1}"
                    )
                    await repo.add_analytic(model=data)

                    if percentage_diff >= max_percents:
                        # We are sell token
                        logger.success(
                            f"We are swap token {mint1} on 0.77 SOL " f"(~100 USD)"
                        )
                        self.unsubscribe_mint_price_change(mint1, q)
                        return

                    elif percentage_diff < 0 and (percentage_diff * -1) >= min_percents:
                        # We are leave from market with token :-(
                        logger.warning(
                            "We leave from monitor because percentage"
                            f" difference: {percentage_diff}"
                        )
                        self.unsubscribe_mint_price_change(mint1, q)
                        return

                    exc_count = 0

                except Exception as e:
                    logger.exception(e)
                    if exc_count >= 5:
                        self.unsubscribe_mint_price_change(mint1, q)
                        return
                    exc_count += 1
                    await asyncio.sleep(2)

                finally:
                    if time.time() - start > seconds_stop:
                        self.unsubscribe_mint_price_change(mint1, q)
                        return


async def main():
    mon = SolanaMonitor()
    # await mon.watch_pool(
    #     mint1="BuHZAmYGVTJaDzPaLZu2ixKDrvUPTzmPZaWvH1CDmuLb",
    #     mint2="So11111111111111111111111111111111111111112",
    #     pool_id="EaDvrEJfWhWqb1pxJzqLAeehxJiPs7JUcEsX4mNVXQ5M",
    # seconds_stop=300,
    # max_percents=10,
    # min_percents=200,
    # )
    await mon.watch_mint(
        "GrCiDZBmKVRxZjMgXJ4BRmkTVZrYDgmEkWtfgsZQZccK",
        seconds_stop=300,
        max_percents=10,
        min_percents=200,
    )

    ...


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
