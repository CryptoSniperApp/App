import asyncio
from datetime import datetime
import decimal
import json
import sys
import traceback
from typing import Literal
import httpx
from loguru import logger
import loguru
from solana.rpc.async_api import AsyncClient
from solders.signature import Signature
import websockets
import websockets.client
import websockets.connection
import websockets.exceptions

from solana_snipping.constants import SOL_ADDR
from solana_snipping.external.dex import RadiumAPI
from solana_snipping.tg import send_msg_log

pool_account_address = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
url = "wss://api.mainnet-beta.solana.com"
client = AsyncClient("https://api.mainnet-beta.solana.com")


async def get_token_from_transactions_from_blockchain(sig: str) -> str:
    resp = await client.get_transaction(
        Signature.from_string(sig), max_supported_transaction_version=0
    )
    response = resp.to_json()
    data = json.loads(response)

    solmint = "So111111111111111111111111111111111"
    try:
        return [
            obj["mint"]
            for obj in data["result"]["meta"]["preTokenBalances"]
            if not obj["mint"].count(solmint)
        ][0]
    except (KeyError, IndexError, AttributeError) as e:
        return ""


async def get_newest_token_transactions_from_raydium_pool():
    while True:
        try:
            async with websockets.client.connect(url, ping_interval=None) as websocket:
                msg = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "logsSubscribe",
                        "params": [
                            {"mentions": [pool_account_address]},
                            {"commitment": "finalized"},
                        ],
                    }
                )
                await websocket.send(msg)

                needed_instructions = [
                    "mintTo",
                    "InitializeAccount",
                    # "Create",
                    "syncNative",
                ]
                while True:
                    raw = await websocket.recv()
                    log_data = json.loads(raw)

                    try:
                        instructions = log_data["params"]["result"]["value"]["logs"]
                    except KeyError:
                        continue

                    start_pool_instruction_i = next(
                        (
                            instructions.index(instr)
                            for instr in instructions
                            if instr.count(f"Program {pool_account_address} invoke [1]")
                        ),
                        None,
                    )
                    end_pool_instruction_i = next(
                        (
                            instructions.index(instr)
                            for instr in instructions
                            if instr.count(f"Program {pool_account_address} success")
                        ),
                        None,
                    )
                    if not start_pool_instruction_i or not end_pool_instruction_i:
                        continue

                    signature = log_data["params"]["result"]["value"]["signature"]
                    pool_instructions = instructions[
                        start_pool_instruction_i : end_pool_instruction_i + 1
                    ]
                    if log_data["params"]["result"]["value"]["err"] or not all(
                        any(
                            instruction.lower().count(
                                f"Program log: Instruction: {needed_instruction}".lower()
                            )
                            for instruction in pool_instructions
                        )
                        for needed_instruction in needed_instructions
                    ):
                        continue

                    with open("logs_pool.log", "a") as f:
                        f.write(
                            f"{datetime.now()}\n"
                            f"{json.dumps(json.loads(raw), ensure_ascii=False, indent=2)}\n\n"
                        )
                    print("поймал новый лог")
                    yield signature, datetime.now()
        except websockets.exceptions.ConnectionClosedError:
            await asyncio.sleep(3)
        except Exception as e:
            print(traceback.format_exc())
            raise e


async def get_liquidity_from_pool(mint1: str, mint2: str = ""):
    # SOL - So11111111111111111111111111111111111111112
    client = httpx.AsyncClient()

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
        "if-none-match": 'W/"7a5-qq1F+jKDBq2zo3fHVHiE4M2td2M"',
        "origin": "https://raydium.io",
        "priority": "u=1, i",
        "referer": "https://raydium.io/",
        "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    }

    params = {
        "mint1": mint1,
        "mint2": mint2,
        "poolType": "all",
        "poolSortField": "default",
        "sortType": "desc",
        "pageSize": "100",
        "page": "1",
    }

    url = "https://api-v3.raydium.io/pools/info/mint"
    resp = await client.get(url, params=params, headers=headers)
    try:
        response = resp.json()

        pool = response["data"]["data"][0]

        lpAmount = float(pool["lpAmount"])
        lpPrice = float(pool["lpPrice"])
        return lpAmount * lpPrice
    except (IndexError, TypeError):
        return None


async def swap_on_jupiter(
    mint1=SOL_ADDR,
    mint2=SOL_ADDR,
    amount=1,
    swap_mode: Literal["ExactOut", "ExactIn"] = "ExactIn",
):
    response = await RadiumAPI().get_swap_info(
        mint1, mint2, amount=amount
    )
    if not response.get("success"):
        return f"raw error: {response}"
    
    price = response["data"]["outputAmount"]
    decimals = 9
    result = decimal.Decimal(float(price) / int("1" + "0" * decimals))
    return round(result, decimals)


async def process_transaction(signature: str):
    mint = await get_token_from_transactions_from_blockchain(sig=signature)
    if not mint:
        with open("failed_transactions.txt", "a") as f:
            f.write(f"{signature}\n\n")
        return

    return mint


async def process_mint(mint: str, dt: datetime):
    pool_raydium = None
    try:
        pool_raydium = await get_liquidity_from_pool(mint)
    except Exception:
        pass
    
    try:
        price = await swap_on_jupiter(mint1=mint)
    except Exception:
        price = "Не удалось получить цену"

    # Buy here

    message = (
        f"Адрес - {mint}\n"
        f"Поймали транзакцию в {dt}, купили монету в {datetime.now()}.\n"
        f"USD в пуле: {pool_raydium}.\n"
        f"Купили по цене: 1 token = {price} SOL\n"
    )
    with open("logs.txt", "a") as f:
        f.write(f"{message}\n\n")
    await send_msg_log(message)


async def strategy():
    async for signature, time in get_newest_token_transactions_from_raydium_pool():
        print(signature, time)
        try:
            mint = await process_transaction(signature)
            await process_mint(mint, time)
        except Exception as e:
            logger.exception(e)


async def main():
    return await strategy()
    mint = "5FdLfn2yx2b4x3WULG9oXw3zigj3gTx8ZBcQWZ59YbkY"
    print(await swap_on_jupiter(mint1=mint))

    # sig = "qRmQ6Brqng8W8DoPEnmZHBYPHTLkCv1acSQPoFpSWtkXEFmaPjcHZNHzx6PvVJR5KefcZk9kgQyTqgFUhww4iYe"
    # response = await get_token_from_transactions_from_blockchain(sig)
    # print(response)
    ...


def global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    stack = "".join(traceback.format_exception(exc_type, value=exc_value, tb=exc_traceback))
    logger.error(f"exception {exc_type.__name__}:\n{stack}")


if __name__ == "__main__":
    print(datetime.now())
    logger.add("debug_program.log", level="DEBUG")
    sys.excepthook = global_exception_handler
    asyncio.run(main())
