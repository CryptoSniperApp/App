import asyncio
from datetime import datetime
import sys
import time
import traceback
from loguru import logger

from solana_snipping.backend.db import setup
from solana_snipping.backend.solana import SolanaChain
from solana_snipping.backend.solana.monitor import SolanaMonitor
from solana_snipping.common.constants import SOL_ADDR
from solana_snipping.frontend.telegram.alerting import send_msg_log
from solana_snipping.backend.utils import format_number_decimal
from solana_snipping.solana_strategies import FiltersRaydiumPools


async def process_transaction(signature: str):
    solana = SolanaChain()

    parsed_transaction = await solana.get_transaction_parsed(signature=signature)
    mint1, mint2, pair = await solana.raydium.get_pool_tokens_mints(parsed_transaction)

    return mint1, mint2, pair


async def process_mint(
    mint: str, dt: datetime, signature_trans: str, pool_id: str, token2: str
):
    mint, token2 = (
        mint if not mint.startswith("So1") else token2,
        mint if mint.startswith("So1") else token2,
    )

    solana = SolanaChain()
    raydium = solana.raydium

    try:
        first_added_liquidity = await solana.solscan.get_added_liquidity_value(
            signature_trans
        )
        pool_raydium = format_number_decimal(first_added_liquidity)
    except Exception as e:
        logger.exception(e)
        pool_raydium = None

    try:
        volume_of_pool = await raydium.get_volume_of_pool(pool_id)
        volume_of_pool = format_number_decimal(volume_of_pool)
    except Exception as e:
        logger.exception(e)
        volume_of_pool = None

    try:
        decimals = await solana.get_token_decimals(mint_addr=mint)
        price = await raydium.get_swap_price(
            mint1=mint, mint2=SOL_ADDR, decimals=decimals
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
        f"Адрес - *{mint}*\n"
        f"Поймали транзакцию в _{dt}_, купили монету в _{capture_time}_.\n\n"
        f"Первая ликвидность: *{pool_raydium}* USD.\n"
        f"Объем пула сейчас: *{volume_of_pool}* USD.\n"
        f"Купили по цене: 1 token = *{price}* SOL\n"
    )
    await send_msg_log(message, mint, trans=signature_trans)

    monitor = SolanaMonitor()
    minutes_watch = 15
    coro = monitor.watch_pool(
        mint1=mint,
        mint2=token2,
        pool_id=pool_id,
        signature_transaction=signature_trans,
        seconds_stop=60 * minutes_watch,
        capture_time=capture_time,
        first_added_liquidity=float(first_added_liquidity),
        min_percents=200,
        max_percents=5,
    )
    await coro


async def solana_strategy():
    cache = []
    reset_cache = time.time()

    solana = SolanaChain()
    q = asyncio.Queue()
    filter_pools = FiltersRaydiumPools()
    asyncio.create_task(solana.raydium.subscribe_to_new_pools(queue=q))
    await asyncio.sleep(1)
    
    async def process(signature: str, dt: datetime):
        mint1, mint2, pair = await process_transaction(signature)
        if not await filter_pools(
            mint1, mint2, pair, signature=signature
        ):  # If check filter not passed
            return
        await process_mint(mint1, dt, signature, pair, mint2)

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
            await asyncio.shield()
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
