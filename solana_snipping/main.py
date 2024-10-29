import asyncio
from datetime import datetime
import logging
import sys
import time
import traceback
from grpclib.client import Channel
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
import pickle
from solders.signature import Signature

from solana_snipping.backend.db import setup
from solana_snipping.backend.solana.moonshot_api import MintToken
from solana_snipping.backend.solana.strategies import Moonshot
from solana_snipping.backend.utils import get_wallets_private_keys
from solana_snipping.common.config import get_config
from solana_snipping.common.constants import SOLANA_TOKEN_PROGRAM_ID
from solana_snipping.frontend.telegram.alerting import log_in_chat
from solana_snipping.backend.proto_generated.pools import ResponseRpcOperation, TokensSolanaStub


MAIN_SCHEDULER = AsyncIOScheduler()


async def mock_async_task():
    q = asyncio.Queue()
    while True:
        await q.get()


def setup_logger():
    def log_tg_filter(record):
        return record["level"].name not in [
            "EXCEPTION",
            "CRITICAL", 
            "ERROR", 
            "DEBUG"
        ]

    logger.add(log_in_chat, filter=log_tg_filter)


async def solana_strategy():
    setup_logger()
    private_keys = get_wallets_private_keys()
        
    cache = []
    reset_cache = time.time()
    logging.getLogger("apscheduler").setLevel(logging.CRITICAL)

    q = asyncio.Queue()
    strategy = Moonshot()
    
    await strategy.update_latest_blockhash()
    await strategy.load_cache()
    strategy.subscribe_to_moonshot_mints_create(queue=q)
    
    MAIN_SCHEDULER.add_job(strategy.update_latest_blockhash, "interval", seconds=20)
    for private_key in private_keys:
        MAIN_SCHEDULER.add_job(strategy.sell_all_tokens, "interval", args=(private_key,), seconds=60 * 5, max_instances=1)

    while True:
        signature, mint, dt, meta = await q.get()
        # dt = datetime.now()
        # signature = '5j8z3bAS2PqfkfvWAsV4PjjPgXX5ZVVeXohQjPf5eqUPTvjMQkQHtefp5uyZXL4ntR3bf68ooQyWuxQyoNGGonXc'
        # mint = 'FU8AGpYKnnMn2vUov9c1ZR573iPn12SfchcpGSKK4sZk'
        # meta = {
        #     'name': 'KAIROS', 
        #     'symbol': 'KAIROS', 
        #     'uri': 'https://cdn.dexscreener.com/cms/tokens/metadata/XFiuVeItvD8lBOHV9np7', 
        #     'socials': [{'url': 'https://x.com/KairosCoinSOL', 'type': 'twitter'}, {'url': 'https://t.me/KairosCoinSOL', 'type': 'telegram'}], 
        #     'websites': [{'label': 'Website', 'url': 'https://KairosCrypto.org'}], 
        #     'image': 'https://cdn.dexscreener.com/cms/images/kltSd01YmNhbcFyq', 
        #     'description': None, 
        #     'decimals': 9
        # }
        
        if time.time() - reset_cache >= 60 * 15:  # if more than 15 minutes have passed
            cache.clear()
            reset_cache = time.time()

        if mint in cache:
            continue

        cache.append(mint)
        msg = (
            f"\nПоймали минт событие\nСигнатура: {signature}\n"
            f"Минт адрес: {mint}\nПолучили ивент от bitquery: {dt}"
        )
        logger.info(msg)
        
        if isinstance(meta, ResponseRpcOperation):
            msg = (
                "Не смогли распарсить метаданные нового токена.\n"
                f"Стек:\n{meta.error}\nms: {meta.ms_time_taken}, raw: "
                f"'{meta.raw_data}'"
            )
            logger.warning(msg)
            logger.error(msg)
            meta = {}
        else:
            meta: MintToken
            meta = meta.token.model_dump()

        try:
            for private_key in private_keys:
                strategy.handle_transaction(signature, dt, mint, mint_meta=meta, private_wallet_key=private_key)
        except Exception as e:
            logger.exception(e)
        # await asyncio.sleep(1500)


async def main():
    logging.getLogger("apscheduler").setLevel(logging.CRITICAL)
    MAIN_SCHEDULER.add_job(mock_async_task, "date", run_date=datetime.now())
    MAIN_SCHEDULER.start()

    await setup()
    await solana_strategy()


def global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    stack = "".join(
        traceback.format_exception(exc_type, value=exc_value, tb=exc_traceback)
    )
    logger.error(f"exception {exc_type.__name__}:\n{stack}")


if __name__ == "__main__":
    logger.add("debug_program.log")
    logger.info("START PROGRAM")
    sys.excepthook = global_exception_handler
    asyncio.run(main())
