import asyncio
import logging
import sys
import time
import traceback
from loguru import logger

from solana_snipping.backend.db import setup
from solana_snipping.backend.solana.strategies import Moonshot
from solana_snipping.frontend.telegram.alerting import log_in_chat


def setup_logger():
    def log_tg_filter(record):
        return record["level"].name not in ["EXCEPTION", "CRITICAL", "ERROR", "DEBUG"]

    logger.add(log_in_chat, filter=log_tg_filter)


async def solana_strategy():
    cache = []
    reset_cache = time.time()
    logging.getLogger("apscheduler").setLevel(logging.CRITICAL)
    setup_logger()

    q = asyncio.Queue()
    
    strategy = Moonshot()
    strategy.subscribe_to_moonshot_mints_create(queue=q)
    # strategy = RaydiumPools()
    # strategy.subscribe_to_raydium_mints_create(queue=q)
    
    # await asyncio.sleep(1)
    
    while True:
        signature, mint, dt = await q.get()
        
        if time.time() - reset_cache >= 60 * 15:  # if more than 15 minutes have passed
            cache.clear()
            reset_cache = time.time()

        if mint in cache:
            continue

        cache.append(mint)
        logger.info(f"{signature} - {mint} - {dt}")

        try:
            strategy.handle_transaction(signature, dt, mint)
        except Exception as e:
            logger.exception(e)


async def main():
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
