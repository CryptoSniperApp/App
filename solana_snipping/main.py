import asyncio
import sys
import time
import traceback
from loguru import logger

from solana_snipping.backend.db import setup
from solana_snipping.backend.solana.strategies import Moonshot, RaydiumPools

async def solana_strategy():
    cache = []
    reset_cache = time.time()

    q = asyncio.Queue()
    
    strategy = Moonshot()
    strategy.subscribe_to_moonshot_mints_create(queue=q)
    # strategy = RaydiumPools()
    # strategy.subscribe_to_raydium_mints_create(queue=q)
    
    await asyncio.sleep(1)

    while True:
        signature, dt = await q.get()

        if time.time() - reset_cache >= 300:  # if more than 5 minutes have passed
            cache.clear()
            reset_cache = time.time()

        if signature in cache:
            continue

        cache.append(signature)
        logger.info(f"{signature} - {dt}")

        try:
            strategy.handle_transaction(signature, dt)
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
