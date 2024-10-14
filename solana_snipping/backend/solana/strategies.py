import asyncio
from datetime import datetime, timedelta
import random
import time

from loguru import logger
from solana.rpc.api import Client
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from typing import Literal
from solders.rpc.responses import GetTransactionResp
from grpclib.client import Channel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from solders.signature import Signature

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
from solana_snipping.backend.proto_generated.pools import PoolStateStub, TokensSolanaStub
from solana_snipping.common.config import get_config


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
        self._grpc_conn = None
        
    async def __aenter__(self):
        self._setup_grpc_stub()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if self._grpc_conn:
            self._close_grpc_channel()

    def _close_grpc_channel(self):
        self._grpc_conn.channel.close()
        self._grpc_conn = None

    def _setup_grpc_stub(self):
        cfg = get_config()
        opts = cfg["microservices"]["grpc"]
        channel = Channel(host=opts["host"], port=int(opts["port"]))
        self._grpc_conn = TokensSolanaStub(channel=channel)

    def handle_transaction(
        self, signature: str, transaction_received: datetime, mint: str
    ):
        f = asyncio.eager_task_factory(
            loop=self._loop,
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
        
    async def _create_token_account(self, mint: str, private_key: str, ata_public_key: str | None = None):
        resp = await self._grpc_conn.create_token_account(
            mint=mint,
            private_key=private_key,
            ata_public_key=ata_public_key or ""
        )
        return resp.tx_signature
    
    async def _swap_tokens(
        self, 
        swap_type: Literal["BUY", "SELL"], 
        mint: str, 
        private_wallet_key: str, 
        amount: int = 0,
        microlamports: int | None = None, 
        slippage: int | None = None,
        swap_all: bool = False,
        close_account: bool = False,
        token_account_address: str = "",
        decimal: int | None = None
    ) -> list[str, str, bool]:
        if microlamports is None:
            microlamports = 100_000
        if slippage is None:
            slippage = 0

        resp = await self._grpc_conn.swap_tokens(
            transaction_type=swap_type,
            mint=mint,
            amount=amount,
            microlamports=microlamports,
            slippage=slippage,
            private_key=private_wallet_key,
            swap_all=swap_all,
            close_account=close_account,
            token_account_address=token_account_address,
            decimal=decimal or 0
        )
        
        if not resp.success:
            msg = (
                f"Не удалось совершить swap для {mint} ({swap_type}). "
                f"Error - {resp.error}.\nВремя транзакции - {resp.ms_time_taken}\n"
                f"Результат - {resp.tx_signature}"
            )
            logger.error(msg)
            return [resp.tx_signature, resp.ms_time_taken, False]
        
        return [resp.tx_signature, resp.ms_time_taken, True]
    
    @property
    def _private_wallet_key(self):
        return get_config()["microservices"]["moonshot"]["private_key"]
    
    async def transaction_finalized(self, signature: str):
        endpoint = get_config()["microservices"]["moonshot"]["rpc_endpoint"]
        client = AsyncClient(
            endpoint,
            commitment="finalized"
        )
        
        resp: GetTransactionResp = await client.get_transaction(
            Signature.from_string(signature), commitment="finalized",
            max_supported_transaction_version=0
        )
        if resp.value is None or resp.value.slot is None or resp.value.transaction.meta.err:
            return False
        
        return True

    async def _process_data(
        self,
        mint: str,
        transaction_received: datetime,
        signature_transaction: str = "not needed"
    ):
        queue = asyncio.Queue()
        self._moonshot_client._mints_price_watch_queues.append(queue)
        
        if self._grpc_conn is None:
            self._setup_grpc_stub()
        
        decimals = 9  # количество знаков после запятой     
        first_swap_price = None  # цена первой покупки
        buy_amount_usd = 0.1 # какой эквивалент в токенах покупаем
        
        buy_amount = 25_000 # сколько токенов покупаем
        start_function_time = time.time()
        
        failed = 0
        while True:
            buy_tx_signature, ms_time_taken, success = await self._swap_tokens(
                swap_type="BUY",
                mint=mint,
                private_wallet_key=self._private_wallet_key,
                amount=buy_amount,
                slippage=5000,
                decimal=decimals or None,
                microlamports=100_000
            )
            if success:
                break
            else:
                if failed > 3:
                    logger.warning(f"Не удалось купить токен - {mint}. Выходим из функции")
                    return
                failed += 1
                await asyncio.sleep(1)
        
        end_function_time = time.time()    
        capture_time = datetime.now()
        message = (
            f"ТИП - MOONSHOT DEXSCREENER\n"
            f"Адрес токена - *{mint}*\n\n"
            f"Поймали транзакцию в _{transaction_received}_, купили монету в _{capture_time}_.\n\n"
            f"Купили {buy_amount} единиц токена\n"
            f"Время самой транзакции - {ms_time_taken} ms\n"
            f"[DEBUG] Время выполнения функции вместе с транзакцией - {end_function_time - start_function_time} s\n"
            f"Результат - {buy_tx_signature}"
        )
        await send_msg_log(message, mint, trans=signature_transaction)
        logger.info(message)

        seconds_watch = 60 * 60 * 10  # 10 hours
        interval_seconds_for_check_price = 60 * 5  # 5 minutes

        min_percents = 200  # если цена опустилась на этот процент, то выходим из функции
        percents_diff_for_sell_body = 530  # если цена выросла на этот процент, то начинаем продавать тело
        percents_diff_for_sell = percents_diff_for_sell_body + 500  # если цена выросла на этот процент, то продаем остаток
        sell_body = False  # когда продали тело, ставим в True
        amount_to_sell_first_part_tokens = None  # сколько токенов продали, когда продали тело
        price_usd = None  # цена в данный момент
        
        dbsession = create_async_sessiomaker()
        
        async def sell_all_tokens():
            nonlocal exit_from_monitor
            
            # продаем только в том случае, если цена упала ниже цены первой покупки
            # иначе выходим из функции.
            # price_usd - цена в данный момент
            # first_swap_price - цена первой покупки
            if not (price_usd and price_usd < first_swap_price):
                return
            
            exit_from_monitor = True
            init_msg = f"[ЦЕНА ({price_usd}) УПАЛА НИЖЕ ЦЕНЫ ПЕРВОЙ ПОКУПКИ ({first_swap_price})]\n"
            
            failed = 0
            while True:
                is_finalized = await self.transaction_finalized(buy_tx_signature)
                if is_finalized:
                    break
                else:
                    if failed >= 3:
                        logger.info(f"{init_msg} Не удалось получить подтверждение для первой покупки ({mint})")
                        return
                    
                    await asyncio.sleep(8)
                    failed += 1
            
            logger.info(f"{init_msg}. С момента первой покупки прошло {time.time() - start_function_time} секунд ({mint}). Продаем все")
            failed = 0
            amount = buy_amount if not sell_body else int((buy_amount - amount_to_sell_first_part_tokens) - 20)
            while True:
                tx_signature, ms_time_taken, success = await self._swap_tokens(
                    swap_type="SELL",
                    mint=mint,
                    private_wallet_key=self._private_wallet_key,
                    slippage=5000,
                    decimal=decimals or None,
                    amount=amount,
                    microlamports=100_000,
                )
                if failed > 15:
                    logger.info(f"{init_msg} Не удалось продать все токены из за неудачной транзакции ({mint})")
                    return
                
                if not success:
                    await asyncio.sleep(5)
                    failed += 1
                else:
                    break
            
                await asyncio.sleep(10)
            failed = 0
            while True:
                is_finalized = await self.transaction_finalized(tx_signature)
                if is_finalized:
                    break
                else:
                    if failed >= 15:
                        logger.info(f"{init_msg} Не удалось подтвердить продажу токенов - непроверенная транзакция ({mint})")
                        return
                    
                    await asyncio.sleep(5)
                    failed += 1
            
            logger.success(
                f"{init_msg} Успешно продали токены из за отсутствия роста цены - {buy_tx_signature} "
                f"время выполнения - {ms_time_taken} ms, "
                f"сигнатура - {tx_signature}"
            )
            scheduler.remove_job(job.id)
            
        scheduler = AsyncIOScheduler()
        
        job = scheduler.add_job(
            sell_all_tokens, 
            IntervalTrigger(
                seconds=interval_seconds_for_check_price,       
            ),
            max_instances=1
        )
        scheduler.start()

        try:
            session = dbsession()
            await session.__aenter__()      
            repo = AnalyticRepository(session)
            sell_all_failed = 0  # счетчик ошибок при продаже всех токенов

            exit_from_monitor = False
            async with asyncio.timeout(seconds_watch):
                while not exit_from_monitor:
                    try:
                        data, event_mint = await queue.get()
                        if event_mint != mint:
                            continue
                        
                        if exit_from_monitor:
                            return

                        price_usd = data["Trade"]["PriceInUSD"]
                        if not first_swap_price:
                            first_swap_price = float(price_usd)
                            
                        percentage_diff = (
                            (price_usd - first_swap_price) / first_swap_price * 100
                        )
                        
                        data = AnalyticData(
                            time=time.time(),
                            mint1_addr=mint,
                            capture_time=capture_time.timestamp(),
                            swap_price=price_usd,
                            swap_time=datetime.now().timestamp(),
                            percentage_difference=percentage_diff,
                        )
                        
                        await repo.add_analytic(data)

                        logger.debug(
                            f"Swap price: {first_swap_price}, first swap price: {price_usd}. Percentage diff: {percentage_diff}. mint - {mint}"
                        )

                        if sell_body and percentage_diff >= percents_diff_for_sell:
                            # продаем оставшиеся токены
                            init_msg = "[ВЫВОДИМ ОСТАТОК]"
                            while True:
                                tx_signature, ms_time_taken, success = await self._swap_tokens(
                                    swap_type="SELL",
                                    mint=mint,
                                    private_wallet_key=self._private_wallet_key,
                                    slippage=5000,
                                    decimal=decimals or None,
                                    amount=int((buy_amount - amount_to_sell_first_part_tokens) - 5),
                                    microlamports=50_000
                                )
                                if not success:
                                    logger.info(
                                        f"{init_msg} Не удалось продать оставшиеся токены. "
                                        f"Сигнатура транзакции - {tx_signature}, "
                                        f"время выполнения - {ms_time_taken} ms"
                                    )
                                    sell_all_failed += 1
                                    await asyncio.sleep(5)
                                    if sell_all_failed >= 5:
                                        logger.info(f"{init_msg} Не удалось продать оставшиеся токены {mint}. Выходим из функции")
                                        return
                                    continue
                                
                                await asyncio.sleep(10)
                                failed = 0
                                retry = False
                                while True:
                                    is_finalized = await self.transaction_finalized(tx_signature)
                                    if is_finalized:
                                        break
                                    else:
                                        if failed >= 15:
                                            logger.info(f"{init_msg} Не удалось получить подтверждение для продажи оставшиейся части {mint}. Выходим из функции")
                                            retry = True
                                            break
                                        
                                        failed += 1
                                        await asyncio.sleep(5)
                                
                                if retry:
                                    continue
                                
                                logger.success(f"{init_msg} We are swap token {mint}.")
                                return
                            
                        elif not sell_body and percentage_diff >= percents_diff_for_sell_body:
                            # проверяем покупку
                            init_msg = "[ВЫВОДИМ ТЕЛО]"
                            while True:
                                failed = 0
                                while True:
                                    is_finalized = await self.transaction_finalized(buy_tx_signature)
                                    if is_finalized:
                                        break
                                    else:
                                        if failed >= 3:
                                            logger.info(f"{init_msg} Не удалось получить подтверждение для первой покупки {mint}. Выходим из функции")
                                            return
                                        
                                        await asyncio.sleep(8)
                                        failed += 1
                                
                                # продаем вложенные 10 центов
                                amount_to_sell_first_part_tokens = buy_amount_usd / price_usd
                                tx_signature, ms_time_taken, success = await self._swap_tokens(
                                    swap_type="SELL",
                                    mint=mint,
                                    private_wallet_key=self._private_wallet_key,
                                    slippage=5000,
                                    decimal=decimals or None,
                                    amount=amount_to_sell_first_part_tokens,
                                    microlamports=200_000,
                                )
                                await asyncio.sleep(10)
                                failed = 0
                                if success:
                                    while True:
                                        is_finalized = await self.transaction_finalized(tx_signature)
                                        if is_finalized:
                                            break
                                        else:
                                            if failed > 10:
                                                logger.info(f"{init_msg} Не удалось получить подтверждение для вывода тела {mint}. Выходим из функции")
                                                return
                                            await asyncio.sleep(5)
                                            failed += 1
                                    
                                    sell_body = True
                                    logger.success(f"{init_msg} We are sell body for mint - {mint}")
                                    break
                                else:
                                    failed += 1
                                    if failed >= 3:
                                        logger.info(f"{init_msg} Не удалось получить подтверждение для вывода тела {mint}. Выходим из функции")
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
        except asyncio.TimeoutError:
            logger.info(f"Выходим из мониторинга {mint}")
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
    from solana.rpc.api import Client
    from solders.signature import Signature
    
    m = Moonshot()
    # q = asyncio.Queue()
    # mint = "3TGWPjCCqneoGvdagp2AbbYHcVwzu2ZnD9PYPienMBTL"
    # print("start ", mint)
    
    # m.subscribe_to_moonshot_mints_create(queue=q)
    # m._moonshot_client._mints_price_watch.append(mint)
    # m.handle_transaction(mint=mint, transaction_received=datetime.now(), signature="")
    
    # await asyncio.sleep(10000)

    async with m:
        ...
        # await m._swap_tokens(
        #     swap_type="SELL",
        #     mint="4BqSTuvKUvQbqpjRYf9egVjou16F32aThHz39EnBF7kn",
        #     private_wallet_key=m._private_wallet_key,
        #     # amount=5,
        #     slippage=500,
        #     decimal=9,
        #     microlamports=100_000,
        #     swap_all=True,
        #     close_account=True,
        # )
    ...


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
