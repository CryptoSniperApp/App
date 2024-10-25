import asyncio
from datetime import datetime, timedelta
import os
import random
import re
import time
import traceback

import base58
import httpx
from loguru import logger
import orjson
from solana.rpc.core import RPCException
from solders.pubkey import Pubkey
from typing import Literal
from solders.rpc.responses import GetLatestBlockhashResp, GetTransactionResp
from grpclib.client import Channel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from solders.signature import Signature
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TokenAccountOpts
from solana.exceptions import SolanaRpcException
from solders.keypair import Keypair


from solana_snipping.backend import solana
from solana_snipping.backend.db import create_async_sessiomaker
from solana_snipping.backend.db.repositories import AnalyticRepository, CacheRepository
from solana_snipping.backend.solana import SolanaChain
from solana_snipping.backend.solana.monitor import SolanaMonitor
from solana_snipping.backend.solana.moonshot_api import MoonshotAPI
from solana_snipping.backend.utils import format_number_decimal, get_proxies
from solana_snipping.common.app_types import AnalyticData, CacheData
from solana_snipping.common.constants import SOL_ADDR, SOLANA_TOKEN_PROGRAM_ID
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
        self._alock = asyncio.Lock()
        self._mints_metas = []
        self._last_blockhash = None
        
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
        self, 
        signature: str, 
        transaction_received: datetime, 
        mint: str, 
        private_wallet_key: str,
        mint_meta: dict = {},
        cache: dict = {},
    ):
        if not self._grpc_conn:
            self._setup_grpc_stub()
            
        if mint_meta:
            mints_images = [m["image"] for m in self._mints_metas]
            mints_name = [m["name"] for m in self._mints_metas]
            mints_websites = [w["url"] for m in self._mints_metas for w in m["websites"]]
            mints_socials = [s["url"] for m in self._mints_metas for s in m["socials"]]
            
            if any(w["url"] in mints_websites for w in mint_meta["websites"]):
                return
            if any(s["url"] in mints_socials for s in mint_meta["socials"]):
                return
            if mint_meta["image"] in mints_images:
                return

        self._mints_metas.append(mint_meta)
        f = asyncio.eager_task_factory(
            loop=self._loop,
            coro=self._wrapper_process_data(
                mint, 
                transaction_received, 
                signature, 
                private_wallet_key, 
                mint_meta,
                cache=cache
            ),
        )
        f.add_done_callback(asyncio_callbacks.raise_exception_if_set)
        self._futures.append(f)

    async def _wrapper_process_data(
        self,
        mint: str,
        transaction_received: datetime,
        signature: str, 
        private_wallet_key: str,
        mint_meta: dict,
        cache: dict = {}
    ):
        try:
            await self._process_data(
                mint=mint,
                transaction_received=transaction_received,
                signature_transaction=signature,
                private_wallet_key=private_wallet_key,
                mint_meta=mint_meta,
                cache=cache
            )
        except Exception as e:
            logger.exception(e)
            msg = f"[ПРОИЗОШЛА ОШИБКА В ГЛАВНОМ ОБРАБОТЧИКЕ МИНТА]\nМетаданные: {mint_meta}\nМинт: {mint}\nТранзакция минта: {signature}"
            logger.warning(msg)
            await self._sell_all_tokens(
                msg, 
                mint=mint,
                private_wallet_key=private_wallet_key,
                decimals=mint_meta.get('decimals') or 9,
                microlamports=100_000
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
        decimal: int | None = None,
        on_moonshot: bool = False,
        blockhash: GetLatestBlockhashResp = None,
    ) -> list[str, str, bool]:
        if microlamports is None:
            microlamports = 100_000
        if slippage is None:
            slippage = 0
        
        if blockhash is None:
            last_blockhash = self.latest_blockhash.value.blockhash.__str__()
            last_valid_block_height = int(self.latest_blockhash.value.last_valid_block_height.__str__())
        else:
            last_blockhash = last_blockhash.value.blockhash.__str__()
            last_valid_block_height = int(last_blockhash.value.last_valid_block_height.__str__())
            
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
            decimal=decimal or 0,
            on_moonshot=on_moonshot,
            last_blockhash=last_blockhash,
            last_valid_block_height=last_valid_block_height
        )
        
        if not resp.success:
            log_method = logger.error
            if resp.error.count("block height exceeded"):
                log_method = logger.warning
            elif resp.error.count("could not find account"):
                log_method = logger.warning
                
            msg = (
                f"Не удалось совершить swap для {mint} ({swap_type}). "
                f"Error - {resp.error}.\nВремя транзакции - {resp.ms_time_taken}\n"
                f"Результат - {resp.tx_signatures}"
            )
            log_method(msg)
            return [resp.tx_signatures, resp.ms_time_taken, False, str(resp.error)]
        
        return [resp.tx_signatures, resp.ms_time_taken, True, ""]
    
    @property
    def _private_wallet_key(self):
        return get_config()["microservices"]["moonshot"]["private_key"]
    
    async def transaction_finalized(self, signature: str):
        if signature == "":
            return False
        
        last_error = None
        for _ in range(3):
            try:
                client = self.proxy_sol_client
                
                resp: GetTransactionResp = await client.get_transaction(
                    Signature.from_string(signature), commitment="finalized",
                    max_supported_transaction_version=0
                )
                last_error = None
                if resp.value is None or resp.value.slot is None:
                    return False
                return True
            except Exception as e:
                last_error = e
                continue
        
        if last_error:
            raise last_error
        
        return True
    
    async def sell_all_tokens(self, private_key: str, close_token_account: bool = True):
        if self._grpc_conn is None:
            self._setup_grpc_stub()
        
        conn_grpc = self._grpc_conn
        
        kp = Keypair.from_base58_string(private_key)
        async with self._alock:
            accounts = None
            last_error = None
            for _ in range(3):
                try:
                    connection = self.proxy_sol_client
                    accounts = await connection.get_token_accounts_by_owner_json_parsed(
                        kp.pubkey(),
                        TokenAccountOpts(
                            program_id=Pubkey.from_string(SOLANA_TOKEN_PROGRAM_ID)
                        ),
                        commitment="finalized"
                    )
                    last_error = None
                except Exception as e:
                    last_error = e
                    continue
            
            if last_error:
                raise last_error
            
            for val in accounts.value:
                account = val.account
                
                amount = int(account.data.parsed['info']['tokenAmount']['uiAmount'])
                if 0 < amount <= 100:
                    await conn_grpc.swap_tokens(
                        transaction_type="SELL",
                        mint=account.data.parsed["info"]["mint"],
                        amount=amount,
                        microlamports=100_000,
                        slippage=2000,
                        private_key=private_key,
                        decimal=account.data.parsed['info']['tokenAmount']['decimals'],
                    )
                elif amount == 0 and close_token_account:
                    await conn_grpc.close_token_account(
                        wallet_private_key=private_key,
                        token_account_address=str(val.pubkey)
                    )
                    
    async def _get_error_transaction(self, signature: str) -> str:
        last_error = None
        resp = None
        for _ in range(3):
            try:
                client = self.proxy_sol_client
                
                resp: GetTransactionResp = await client.get_transaction(
                    Signature.from_string(signature), 
                    commitment="finalized",
                    max_supported_transaction_version=0
                )
                last_error = None
            except Exception as e:
                last_error = e
                continue
        
        if last_error:
            raise last_error
        
        if resp.value is None or resp.value.slot is None:
            raise ValueError("Transaction not finalized in blockchain!")
        
        if resp.value.transaction.meta.err:
            pattern = r"[eE]rror [Mm]essage([: ]){0,3}(.+)"
            res = re.search(pattern, "\n".join(resp.value.transaction.meta.log_messages))
            return res.group(2) if res else str(resp.value.transaction.meta.err.err)
            
        return ""
    
    async def is_transaction_success(self, signature: str, retries: int = 5) -> tuple[bool, str]:
        failed = 0
        while True:
            is_finalized = await self.transaction_finalized(signature)
            if is_finalized:
                break
            else:
                if failed >= retries:
                    return False, "NOT FINALIZED"
                
                await asyncio.sleep(8)
                failed += 1
        
        try:
            error = await self._get_error_transaction(signature)
        except ValueError as e:
            if str(e).count('not finalized'):
                return False, error
            raise e
        
        if error:
            return False, error
        
        return True, error
    
    async def is_mint_in_wallet(
        self, 
        private_wallet_key: str, 
        mint: str,
        needed_balance: int = None
    ):
        try:
            keypair = Keypair.from_base58_string(private_wallet_key)
            ata = await self._grpc_conn.get_associated_token_account(
                mint_address=mint, 
                wallet_public_key=keypair.pubkey().__str__()
            )
            
            if not ata.ata_public_key:
                return False
            
            last_error = None
            balance = None
            for _ in range(3):
                try:
                    client = self.proxy_sol_client
                    balance = await client.get_token_account_balance(
                        Pubkey.from_string(ata.ata_public_key),
                        "confirmed"
                    )
                    last_error = None
                except Exception as e:
                    last_error = e
                    continue
                
            if last_error:
                raise last_error
                
            if not balance.value.ui_amount:
                return False
            
            if needed_balance:
                if int(balance.value.ui_amount) >= needed_balance:
                    return True
            return True
        
        except Exception as e:
            if not str(e).count("could not find account"):
                logger.exception(e)
            return False
        
    async def extract_sol_amount_from_buy_transaction(self, sig: str) -> int | None:
        try:
            signature = Signature.from_string(sig)
            last_error = None
            resp = None
            for _ in range(3):
                client = self.proxy_sol_client
                
                try:
                    try:
                        resp = await client.get_transaction(
                            signature, encoding="jsonParsed", max_supported_transaction_version=0
                        )
                    except RPCException as e:
                        msg = 'message: "Transaction version (0) is not supported'
                        if not str(e).count(msg):
                            raise e
                        
                        resp = await client.get_transaction(
                            signature, encoding="jsonParsed"
                        )
                    last_error = None
                except Exception as e:
                    last_error = e
                    continue
            
            if last_error:
                raise last_error
            
            if not resp.value:
                raise ValueError(f"transaction not found: {sig}")
            
            meta = resp.value.transaction.meta
            if meta.err:
                raise ValueError(f"transaction has error: {meta.err}")
            
            transaction = resp.value.transaction.transaction
            
            instruction = [
                instruction 
                for instruction in transaction.message.instructions
                if hasattr(instruction, 'accounts') and len(instruction.accounts) == 11
            ][0]        
            
            account = instruction.accounts[2]
            i = next((i for i, x in enumerate(transaction.message.account_keys) if x.pubkey == account), None)
            if not i:
                return
            return (meta.post_balances[i] - meta.pre_balances[i]) / 1_000_000_000
        except Exception as e:
            logger.exception(e)
            return
        
    async def _sell_all_tokens(
        self, 
        init_msg: str, 
        mint: str, 
        private_wallet_key: str,
        amount: int = 0, 
        decimals: int = None, 
        slippage: int = 1000, 
        microlamports: int = 100_000,
        max_attempts: int = 15
    ):
        failed = 0
        data = {"success": False, "error": ""}
        while True:
            tx_signatures, ms_time_taken, success, error = await self._swap_tokens(
                swap_type="SELL",
                mint=mint,
                private_wallet_key=private_wallet_key,
                slippage=slippage,
                decimal=decimals or None,
                amount=amount,
                microlamports=microlamports
            )
            data["tx_signature"] = ", ".join(tx_signatures)
            data["ms_time_taken"] = ms_time_taken
            
            if failed > max_attempts:
                logger.info(f"{init_msg} Не удалось продать все токены из за неудачной транзакции ({mint})")
                return data
            
            if tx_signatures:
                break
            elif error.count("could not find account"):
                data["success"] = True
                data["error"] = error
                return data
            if not success:
                await asyncio.sleep(5)
                failed += 1
                continue
        
        for tx_signature in tx_signatures:
            data["tx_signature"] = tx_signature
            is_success, error = await self.is_transaction_success(tx_signature)
            if not is_success:
                known_errors = [
                    "to be already initialized",
                    "Trade amount too low , resulting in 0 costs",
                    "NOT FINALIZED"
                ]
                if isinstance(error, str) and any(error.count(msg) for msg in known_errors):
                    data["error"] = error
                    
                elif error:
                    logger.error(f"{init_msg} Получили ошибку после попытки продать все токены. {error}. sig - {tx_signature}. mint - {mint}")    
                    data["error"] = str(error)
                    
            else:
                data["error"] = ""
                data["success"] = True
                break
        
        return data
    
    async def get_creator_buy_amount(self, sig: str) -> int | None:
        try:
            signature = Signature.from_string(sig)
            last_error = None
            resp = None
            for _ in range(3):
                
                client = self.proxy_sol_client
                try:
                    try:
                        resp = await client.get_transaction(
                            signature, encoding="jsonParsed", max_supported_transaction_version=0
                        )
                    except RPCException as e:
                        msg = 'message: "Transaction version (0) is not supported'
                        if not str(e).count(msg):
                            raise e
                        
                        resp = await client.get_transaction(
                            signature, encoding="jsonParsed"
                        )
                    last_error = None
                except Exception as e: 
                    last_error = e
                    continue
            
            if last_error:
                raise last_error
                    
            if not resp.value:
                raise ValueError(f"transaction not found: {sig}")
            
            meta = resp.value.transaction.meta
            if meta.err:
                raise ValueError(f"transaction has error: {meta.err}")
            
            transaction = resp.value.transaction.transaction
            instructions = transaction.message.instructions
            if len(instructions) < 3:
                return
            buy_data = instructions[2].data
            parsed_instruction = await self._moonshot_client.parse_buy_instruction_data(base58.b58decode(buy_data))
            
            return parsed_instruction['data']['data']['tokenAmount'] / 1_000_000_000
        except Exception as e:
            logger.exception(e)
            return
        
    @property
    def proxy_sol_client(self) -> AsyncClient:
        with open("ts/proxies.json") as f:
            proxies = orjson.loads(f.read())
        
        if proxies:
            proxy = random.choice(proxies["proxies"])
        else:
            proxy = get_config().get("PROXY_URL")
            
        client = AsyncClient('https://api.mainnet-beta.solana.com', "confirmed")
        timeout = client._provider.session.timeout
        timeout.read = 30
        client._provider.session = httpx.AsyncClient(
            timeout=timeout,
            proxy=proxy,
            verify=False
        )
        return client
    
    async def update_latest_blockhash(self):
        for _ in range(3):
            client = self.proxy_sol_client
            try:
                self._last_blockhash = await client.get_latest_blockhash()
                break
            except (SolanaRpcException, httpx.ProxyError):
                await asyncio.sleep(1.5)
                continue
    
    @property
    def latest_blockhash(self):
        return self._last_blockhash
    
    async def load_cache(self):
        sessionmaker = create_async_sessiomaker()
        async with sessionmaker() as session:
            repo = CacheRepository(session)
            cache_data = await repo.get_all()
            
        mints = []
        for cache in sorted(cache_data, key=lambda x: x.id, reverse=True):
            value = orjson.loads(cache.cache_value)
            if time.time() - value["price_updated_at"] > 60 * 60 * 25:
                continue
            
            mint = value["mint"]
            if mint in mints:
                continue
            mints.append(mint)
            
            try:
                self.handle_transaction(
                    mint=mint,
                    transaction_received=datetime.fromtimestamp(float(value["transaction_received"])),
                    signature=value["signature"],
                    private_wallet_key=value["private_wallet_key"],
                    mint_meta=value["mint_meta"],
                    cache=value
                )
            except Exception as e:
                logger.exception(e)
                

    async def _process_data(
        self,
        mint: str,
        transaction_received: datetime,
        signature_transaction: str,
        private_wallet_key: str,
        mint_meta: dict = {},
        cache: dict = {}
    ):
        queue = asyncio.Queue()
        dbsession = create_async_sessiomaker()
        wallet_public_key = Keypair.from_base58_string(private_wallet_key).pubkey().__str__()
        
        if self._grpc_conn is None:
            self._setup_grpc_stub()

        decimals = cache.get("decimals") or 9  # количество знаков после запятой     
        first_swap_price = cache.get("first_swap_price") or None  # цена первой покупки
        buy_amount_usd = cache.get("buy_amount_usd") or None # какой эквивалент в токенах покупаем
        buy_amount_sol = cache.get("buy_amount_sol") or None  # сколько токенов мы купили в sol
        
        buy_amount = cache.get("buy_amount") or 10_000 # сколько токенов покупаем
        start_function_time = cache.get("start_function_time") or time.time()
        
        if not cache:
            # buy_tx_signatures, ms_time_taken, success, error = await self._swap_tokens(
            #     swap_type="BUY",
            #     mint=mint,
            #     private_wallet_key=private_wallet_key,
            #     amount=buy_amount,
            #     slippage=3500,
            #     decimal=decimals or None,
            #     microlamports=120_000,
            #     on_moonshot=True
            # )
            
            # in_wallet = False
            # # await asyncio.sleep(10)
            # for _ in range(10):
            #     try:
            #         in_wallet = await self.is_mint_in_wallet(
            #             private_wallet_key=private_wallet_key,
            #             mint=mint,
            #             needed_balance=buy_amount
            #         )
            #     except Exception as e:
            #         logger.exception(e)
                
            #     if not in_wallet:
            #         await asyncio.sleep(5)
            #     else:
            #         break
            
            # if not in_wallet:
            #     msg = (
            #         f"\nНе получилось купить токен.\n"
            #         f"Метаданные токена: {mint_meta}\n"
            #         f"Пробовали купить {buy_amount} токенов "
            #         f"{mint} несколько раз. ошибка: {error}. Не получилось. Выходим из функции\n\n"
            #         f"Транзакции: {buy_tx_signatures}\n"
            #     )
            #     logger.warning(msg)
            #     logger.error(msg)
            #     return
            
            # need_to_sell = False
            # creator_buy_amount = None
            # for _ in range(3):
            #     init_msg = f"[ПРОДАЕМ ВСЕ ТОКЕНЫ ТАК КАК КРЕАТОР КУПИЛ {creator_buy_amount}]"
            #     try:
            #         creator_buy_amount = await self.get_creator_buy_amount(signature_transaction)
            #         if not creator_buy_amount:
            #             break
            #         if creator_buy_amount >= 201_000_000:
            #             need_to_sell = True
            #             await self._sell_all_tokens(
            #                 init_msg,
            #                 mint=mint, 
            #                 microlamports=180_000,
            #                 private_wallet_key=private_wallet_key
            #             )
            #             return
            #         else:
            #             break
            #     except Exception as e:
            #         logger.exception(e)
            #         logger.warning(
            #             f"{init_msg} Ошибка: {e}, stack:\n{traceback.format_exc()}"
            #         )
            
            # if need_to_sell:
            #     return
            
            # buy_tx_signature = None
            # for tx in buy_tx_signatures:
            #     is_success, error = await self.is_transaction_success(tx)
                
            #     if is_success and not error:
            #         buy_tx_signature = tx
            #         break
            
            # buy_amount_sol = None
            # for _ in range(5):
            #     buy_amount_sol = await self.extract_sol_amount_from_buy_transaction(buy_tx_signature)
            #     if buy_amount_sol is None:
            #         await asyncio.sleep(3)
            #         continue
            #     break
            
            # if buy_amount_sol is None:
            #     await self._sell_all_tokens(
            #         init_msg=f"[НЕ УДАЛОСЬ ПОЛУЧИТЬ ЗНАЧЕНИЕ В SOL НАШЕЙ ПОКУПКИ]",
            #         mint=mint,
            #         private_wallet_key=private_wallet_key
            #     )
            #     return

            end_function_time = time.time() 
            capture_time = datetime.now()
            message = (
                f"ТИП - MOONSHOT DEXSCREENER\n"
                f"Адрес токена - *{mint}*\n\n"
                f"Поймали транзакцию в _{transaction_received}_, купили монету в _{capture_time}_.\n\n"
                f"Купили {buy_amount} единиц токена\n"
                # f"Сумма в SOL: {buy_amount_sol}\n"
                # f"Время самой транзакции - {ms_time_taken} ms\n"
                # f"[DEBUG] Время выполнения функции вместе с транзакцией - {end_function_time - start_function_time} s\n"
                # f"Результат - {buy_tx_signature}"
            )
            try:
                await send_msg_log(message, mint, trans=signature_transaction)
            except Exception as e:
                logger.exception(e)
            logger.info(message)
        else:
            capture_time = datetime.fromtimestamp(float(cache["transaction_received"]))
        
        if mint not in self._moonshot_client._mints_price_watch:
            self._moonshot_client._mints_price_watch.append(mint)
            
        self._moonshot_client._mints_price_watch_queues.append(queue)

        seconds_watch = cache.get("seconds_watch") or 60 * 60 * 24  # 15 hours
        interval_seconds_for_check_price = cache.get("interval_seconds_for_check_price") or 60 * 1 # 1 minute
        max_diff_percents_of_drop_price = cache.get("max_diff_percents_of_drop_price") or 50

        min_percents = cache.get("min_percents") or 200  # если цена опустилась на этот процент, то выходим из функции
        percents_diff_for_sell_body = cache.get("percents_diff_for_sell_body") or 530  # если цена выросла на этот процент, то начинаем продавать тело
        percents_diff_for_sell = cache.get("percents_diff_for_sell") or percents_diff_for_sell_body + 500  # если цена выросла на этот процент, то продаем остаток
        
        max_time_for_sell_tokens = cache.get("max_time_for_sell_tokens") or 60 * 90  # если цена не менялась столько секунд, продаем все токены
        
        sell_body = cache.get("sell_body") or False  # когда продали тело, ставим в True
        amount_to_sell_first_part_tokens = cache.get("amount_to_sell_first_part_tokens") or None  # сколько токенов продали, когда продали тело
        price_usd = cache.get("price_usd") or None  # цена в данный момент
        price_updated_at = cache.get("price_updated_at") or time.time()  # во сколько последний раз цена быда обновленна
        only_scan = cache.get("only_scan") or False  # если True, то просто следим за ценой и записываем в базу не делая транзакции
        
        async def sell_all_tokens():
            nonlocal exit_from_monitor, only_scan
            
            if time.time() - price_updated_at < max_time_for_sell_tokens:
                return
            
            init_msg = f"[НЕТ ТРАНЗАКЦИЙ ЗА ПОСЛЕДНИЕ {max_time_for_sell_tokens} СЕКУНД]"
            logger.info(f"{init_msg}. С момента первой покупки прошло {int(time.time() - start_function_time)} секунд ({mint}). Продаем все")
            
            # result = await self._sell_all_tokens(
            #     init_msg=init_msg,
            #     mint=mint,
            #     amount=0,
            #     private_wallet_key=private_wallet_key
            # )
            # success, error = result["success"], result["error"]
            
            # if not success:
            #     if error.count("to be already initialized"):
            #         only_scan = True
            #         scheduler.remove_job(job.id)
            #     else:
            #         logger.warning(f"{init_msg} Получили ошибку после попытки продать все токены. {error}. tx_signature - {result["tx_signature"]}. mint - {mint}")    
            #     return
            
            only_scan = True
            scheduler.remove_job(job.id)
            logger.success(
                f"{init_msg} Успешно продали токены из за отсутствия роста цены - "
                # f"{buy_tx_signature} "
                f"\"\" "
                # f"время выполнения - {result["ms_time_taken"]} ms, "
                # f"сигнатура - {result["tx_signature"]}. "
                f"mint - {mint}"
            )
            
        scheduler = AsyncIOScheduler()
        job = scheduler.add_job(
            sell_all_tokens, 
            IntervalTrigger(
                seconds=interval_seconds_for_check_price,       
            ),
            max_instances=1
        )
        scheduler.start()
        
        sell_all_failed = cache.get("sell_all_failed") or 0  # счетчик ошибок при продаже всех токенов
        amount_to_sell_first_part_tokens = cache.get("amount_to_sell_first_part_tokens") or None  # сумма токенов при выводе тела
        max_price_sol = cache.get("max_price_sol") or None
        exit_from_monitor = cache.get("exit_from_monitor") or False
        
        def get_cached_locals():
            return {
                "max_price_sol": max_price_sol,
                "amount_to_sell_first_part_tokens": amount_to_sell_first_part_tokens,
                "sell_all_failed": sell_all_failed,
                "exit_from_monitor": exit_from_monitor,
                "only_scan": only_scan,
                "price_updated_at": price_updated_at,
                "price_usd": price_usd,
                "sell_body": sell_body,
                "max_time_for_sell_tokens": max_time_for_sell_tokens,
                "percents_diff_for_sell": percents_diff_for_sell,
                "percents_diff_for_sell_body": percents_diff_for_sell_body,
                "min_percents": min_percents,
                "max_diff_percents_of_drop_price": max_diff_percents_of_drop_price,
                "interval_seconds_for_check_price": interval_seconds_for_check_price,
                "seconds_watch": seconds_watch,
                "buy_amount": buy_amount,
                'start_function_time': start_function_time,
                "buy_amount_sol": buy_amount_sol,
                "buy_amount_usd": buy_amount_usd,
                "first_swap_price": first_swap_price,
                "decimals": decimals,
                "mint": mint,
                "transaction_received": transaction_received.timestamp(),
                "signature": signature_transaction,
                "private_wallet_key": private_wallet_key,
                "mint_meta": mint_meta
            }

        try:
            session = dbsession()
            await session.__aenter__()      
            repo = AnalyticRepository(session)
            
            # cache_session = dbsession()
            # await cache_session.__aenter__()
            # cache_repo = CacheRepository(cache_session)
            
            data = AnalyticData(
                time=time.time(),
                mint1_addr=mint,
                capture_time=capture_time.timestamp(),
                swap_price=buy_amount,
                swap_time=capture_time.timestamp(),
                percentage_difference=0,
                meta=orjson.dumps(mint_meta).decode('utf-8'),
                wallet_public_key=wallet_public_key
            )
            await repo.add(data)
            
            
            # cache_value = CacheData(
            #     cache_value=orjson.dumps(get_cached_locals()).decode('utf-8')
            # )
            # await cache_repo.add(cache_value)

            async with asyncio.timeout(seconds_watch):
                while not exit_from_monitor:
                    try:
                        data, event_mint = await queue.get()
                        if exit_from_monitor:
                            return
                        
                        if event_mint != mint:
                            continue
                        
                        price_usd = data["Trade"]["PriceInUSD"]
                        price_sol = data["Trade"]["Price"]
                        price_updated_at = time.time()
                        if not first_swap_price:
                            first_swap_price = float(price_usd)
                        if not buy_amount_usd:
                            buy_amount_usd = float(price_usd) * buy_amount
                            
                        if max_price_sol is None:
                            max_price_sol = price_sol
                        if price_sol > max_price_sol:
                            max_price_sol = price_sol
                            
                        # price_usd = first_swap_price * 6.5 if not sell_body else price_usd * 16.5  # for tests
                        # price_sol = price_sol * 6.5 if not sell_body else price_sol * 16.5
                        # price_sol = max_price_sol / 2.4
                        percentage_diff = (
                            (price_usd - first_swap_price) / first_swap_price * 100
                        )
                        
                        data = AnalyticData(
                            time=time.time(),
                            mint1_addr=mint,
                            capture_time=capture_time.timestamp(),
                            swap_price=price_sol,
                            swap_time=datetime.now().timestamp(),
                            percentage_difference=percentage_diff,
                            meta=orjson.dumps(mint_meta).decode('utf-8'),
                            wallet_public_key=wallet_public_key
                        )
                        
                        await repo.add(data)
                        
                        # cache_value = CacheData(
                        #     cache_value=orjson.dumps(get_cached_locals()).decode('utf-8')
                        # )
                        # await cache_repo.add(cache_value)

                        logger.debug(
                            f"Swap price USD: {price_usd}, SOL: {price_sol}.\nFirst swap price "
                            f"USD: {first_swap_price}.\nMax SOL price: "
                            f"{max_price_sol}.\nPercentage diff: "
                            f"{percentage_diff}.\nMint - {mint}"
                        )
                        only_scan = False
                        if only_scan:
                            continue
                        
                        # если текущая цена ниже максимальной цены                            
                        if not only_scan and (price_updated_at - capture_time.timestamp()) > 60 and price_sol < max_price_sol:
                            # вычисляем разницу в процентах относительно максимальной цены и текущей цены
                            diff = (price_sol - max_price_sol) / max_price_sol * 100
                            # если цена упала более чем на 50%
                            if sell_body and (diff * -1) > max_diff_percents_of_drop_price:
                                init_msg = f"[ЦЕНА УПАЛА НА {round((diff * -1), 2)} ПРОЦЕНТОВ]"
                                msg = (
                                    f"{init_msg}\n"
                                    "Сработал 2 триггер на продажу всех "
                                    "токенов. С момента покупки прошло "
                                    f"{round(time.time() - capture_time.timestamp(), 2)} секунд.\n"
                                    f"Максимальная цена SOL - {max_price_sol}\n"
                                    f"Текущая цена SOL - {price_sol}\n"
                                    f"Попытка №{sell_all_failed} продать все токены (максимум 5)"
                                )
                                logger.info(msg)
                                # result = await self._sell_all_tokens(
                                #     init_msg=init_msg,
                                #     mint=mint,
                                #     amount=0,
                                #     private_wallet_key=private_wallet_key
                                # )
                                # success, error = result["success"], result["error"]
                                # if not success:
                                #     if error.count("to be already initialized"):
                                #         logger.warning(f"{init_msg}. Ошибка продажи токенов с несуществующего токен аккаунта. raw error: {error}")
                                #         only_scan = True
                                #     if sell_all_failed >= 5:
                                #         only_scan = True
                                #     sell_all_failed += 1
                                #     logger.warning(f"{init_msg}. не удалось продать все токены по 2 триггеру. ошибка {error}. сигнатура -  {result["tx_signature"]}")
                                #     continue
                                succ_msg = (
                                    f"{init_msg}. Успешно продали все токены по 2 триггеру.\n"
                                    f"Макс цена в sol - {max_price_sol}\n"
                                    f"Текущая цена в sol - {price_sol}\n"
                                    f"Попытка продать все токены - {sell_all_failed}"
                                )
                                
                                # try:
                                #     swap_time = datetime.now()
                                #     swap_price = await self.extract_sol_amount_from_buy_transaction(sig=result["tx_signature"])
                                #     if swap_price:
                                #         data = AnalyticData(
                                #             time=time.time(),
                                #             mint1_addr=mint,
                                #             capture_time=capture_time.timestamp(),
                                #             swap_price=price_usd * buy_amount,
                                #             swap_time=swap_time.timestamp(),
                                #             percentage_difference=(swap_price - buy_amount_sol) / buy_amount_sol * 100,
                                #             meta=orjson.dumps(mint_meta).decode('utf-8'),
                                #             wallet_public_key=wallet_public_key,
                                #         )
                                # except Exception as e:
                                #     logger.exception(e)
                                
                                logger.success(succ_msg)
                                only_scan = True

                                try:
                                    data.comment = init_msg
                                    await repo.add(data)
                                    # await cache_repo.add(CacheData(
                                    #     cache_value=orjson.dumps(get_cached_locals()).decode("utf-8")
                                    # ))
                                except Exception as e:
                                    logger.exception(e)

                        if sell_body and percentage_diff >= percents_diff_for_sell:
                            # продаем оставшиеся токены
                            init_msg = "[ВЫВОДИМ ОСТАТОК]"
                            while True:
                                swap_time = datetime.now()
                                # tx_signatures, ms_time_taken, success, error = await self._swap_tokens(
                                #     swap_type="SELL",
                                #     mint=mint,
                                #     private_wallet_key=private_wallet_key,
                                #     slippage=3500,
                                #     decimal=decimals or None,
                                #     amount=int((buy_amount - amount_to_sell_first_part_tokens) - 5),
                                #     microlamports=70_000,
                                # )
                                # if not success:
                                #     logger.info(
                                #         f"{init_msg} Не удалось продать оставшиеся токены. "
                                #         f"Сигнатуры транзакций - \"{tx_signatures}\", "
                                #         f"время выполнения - \"{ms_time_taken}\" ms. Неудачных попыток - {sell_all_failed}"
                                #     )
                                #     sell_all_failed += 1
                                #     if sell_all_failed >= 5:
                                #         logger.info(f"{init_msg} Не удалось продать оставшиеся токены {mint}. Выходим из функции")
                                #         only_scan = True
                                #         break
                                #     await asyncio.sleep(5)
                                #     continue
                                
                                # await asyncio.sleep(10)
                                # failed = 0
                                # retry = False
                                # success = False
                                # tx_signature = None
                                # while True:
                                #     for tx_signature in tx_signatures:
                                #         is_success, error = await self.is_transaction_success(tx_signature)
                                #         if is_success:
                                #             success = True
                                #             break
                                #         else:
                                #             if failed >= 15:
                                #                 logger.info(f"{init_msg} Не удалось получить подтверждение для продажи оставшиейся части токенов {mint}. ({error})")
                                #                 retry = True
                                #                 break
                                            
                                #             failed += 1
                                #             await asyncio.sleep(5)
                                        
                                #     if success:
                                #         break
                                
                                # if retry:
                                #     continue
                                
                                logger.success(f"{init_msg} Мы успешно вывели все оставшиеся токены {mint}.")
                                
                                # try:
                                #     swap_price = await self.extract_sol_amount_from_buy_transaction(sig=tx_signature)
                                #     if swap_price:
                                #         data = AnalyticData(
                                #             time=time.time(),
                                #             mint1_addr=mint,
                                #             capture_time=capture_time.timestamp(),
                                #             swap_price=swap_price,
                                #             swap_time=swap_time.timestamp(),
                                #             percentage_difference=(swap_price - buy_amount_sol) / buy_amount_sol * 100,
                                #             meta=orjson.dumps(mint_meta).decode('utf-8'),
                                #             wallet_public_key=wallet_public_key,
                                #         )      
                                # except Exception as e:
                                #     logger.exception(e)
                                    
                                data.comment = init_msg
                                await repo.add(data)
                                only_scan = True
                                # await cache_repo.add(CacheData(
                                #     cache_value=orjson.dumps(get_cached_locals()).decode("utf-8")
                                # ))
                                break
                            
                        elif not sell_body and percentage_diff >= percents_diff_for_sell_body:
                            # проверяем покупку
                            init_msg = "[ВЫВОДИМ ТЕЛО]"
                            failed = 0
                            while True:
                                # swap_time = datetime.now()
                                # # продаем вложенные доллары
                                # # amount_to_sell_first_part_tokens = buy_amount_usd / price_usd
                                # amount_to_sell_first_part_tokens = buy_amount_sol / price_sol
                                # tx_signatures, ms_time_taken, success, error = await self._swap_tokens(
                                #     swap_type="SELL",
                                #     mint=mint,
                                #     private_wallet_key=private_wallet_key,
                                #     slippage=3500,
                                #     decimal=decimals or None,
                                #     amount=amount_to_sell_first_part_tokens,
                                #     microlamports=100_000,
                                # )
                                # if not failed:
                                #     await asyncio.sleep(10)
                                # if success:
                                #     tx_signature = None
                                #     is_success = False
                                #     while True:
                                #         for tx_signature in tx_signatures:
                                #             is_success, error = await self.is_transaction_success(tx_signature)
                                #             if is_success:
                                #                 break
                                #             else:
                                #                 if failed > 10:
                                #                     logger.info(f"{init_msg} Не удалось получить подтверждение   для вывода тела {mint} ({error}). Выходим из функции")
                                #                     only_scan = True
                                #                 await asyncio.sleep(5)
                                #                 failed += 1
                                                
                                #         if is_success:
                                #             break
                                    
                                #     try:
                                #         swap_price = await self.extract_sol_amount_from_buy_transaction(sig=tx_signature)
                                #         if swap_price:
                                #             data = AnalyticData(
                                #                 time=time.time(),
                                #                 mint1_addr=mint,
                                #                 capture_time=capture_time.timestamp(),
                                #                 swap_price=swap_price,
                                #                 swap_time=swap_time.timestamp(),
                                #                 percentage_difference=(swap_price - buy_amount_sol) / buy_amount_sol * 100,
                                #                 meta=orjson.dumps(mint_meta).decode('utf-8'),
                                #                 wallet_public_key=wallet_public_key
                                #             )
                                #     except Exception as e:
                                #         logger.exception(e)
                                    
                                data.comment = init_msg
                                await repo.add(data)
                                sell_body = True
                                logger.success(f"{init_msg} We are sell body for mint - {mint}")
                                # await cache_repo.add(CacheData(
                                #     cache_value=orjson.dumps(get_cached_locals()).decode("utf-8")
                                # ))
                                break
                                # else:
                                #     failed += 1
                                #     if failed >= 3:
                                #         logger.info(f"{init_msg} Не удалось получить подтверждение для вывода тела {mint}. Выходим из функции")
                                #         only_scan = True
                            
                        elif percentage_diff < 0 and (percentage_diff * -1) >= min_percents:
                            # We are leave from market with token :-(
                            logger.warning(
                                "We leave from monitor because percentage"
                                f" difference: {percentage_diff}"
                            )
                            only_scan = True

                    except Exception as e:
                        logger.exception(e)
                        await asyncio.sleep(2)
        except asyncio.TimeoutError:
            logger.info(f"Выходим из мониторинга {mint}")
        finally:
            await session.__aexit__(None, None, None)
            try:
                self._moonshot_client._mints_price_watch_queues.remove(queue)
                self._moonshot_client._mints_price_watch.remove(mint)
                self._mints_metas.remove(mint_meta)
            except Exception:
                pass
            scheduler.shutdown(wait=False)

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
    from solana.rpc.async_api import AsyncClient
    from solders.signature import Signature
    import base64
    
    m = Moonshot()
    # q = asyncio.Queue()
    # mint = "BdgT2QewMPZ291P2H4iZTPsZWhZbYRocUMqW1N6uvFVY"
    # print("start ", mint)
    # m._setup_grpc_stub()
    # last_blockhash = await m.proxy_sol_client.get_latest_blockhash()
    
    # start = datetime.now()
    # print("start", start)
    # res = await m._grpc_conn.swap_tokens(
    #     transaction_type="BUY",
    #     mint="J4LgFGz3qBW184tMxQ6ix7zV4BFgChaL38FzwS1q7utY",
    #     amount=10,
    #     microlamports=100_000,
    #     slippage=300,
    #     private_key=m._private_wallet_key,
    #     on_moonshot=True,
    #     last_blockhash=last_blockhash.value.blockhash.__str__(),
    #     last_valid_block_height=int(last_blockhash.value.last_valid_block_height.__str__())
    # )
    # stop = datetime.now()
    
    # print(res)
    # print(f"taken: {stop - start}")
    # m._grpc_conn.channel.close()
    print(
        await m._sell_all_tokens(   )
    )
    return
    # m.subscribe_to_moonshot_mints_create(queue=q)
    # m._moonshot_client._mints_price_watch.append(mint)
    # m.handle_transaction(mint=mint, transaction_received=datetime.now(), signature="")
    await asyncio.sleep(10000)
    
    # secret_keys = [
    #     
    # ]
    

    # async with m:
    #     grpc = m._grpc_conn
    #     # r = await grpc.transfer_sol_to_wallets(
    #     #     payer_private_key=m._private_wallet_key,
    #     #     wallets_amounts={
    #     #         Keypair.from_base58_string(k).pubkey().__str__(): 0.001 for k in secret_keys
    #     #     }
    #     # )
    #     r = await grpc.receive_sol_from_wallets(
    #         wallets_datas={
    #             k: 0 for k in secret_keys
    #         },
    #         destination_wallet_public_key="D5dAYrkpD3QVqjkAnpRzpGK4LdMNwC8YRt7iV294CEiG"
    #     )
    #     print(r)
    #     ...
    #     # await m._swap_tokens(
    #     #     swap_type="SELL",
    #     #     mint="4BqSTuvKUvQbqpjRYf9egVjou16F32aThHz39EnBF7kn",
    #     #     private_wallet_key=m._private_wallet_key,
    #     #     # amount=5,
    #     #     slippage=500,
    #     #     decimal=9,
    #     #     microlamports=100_000,
    #     #     swap_all=True,
    #     #     close_account=True,
    #     # )
    # ...


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
