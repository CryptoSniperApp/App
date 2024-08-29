import asyncio
from datetime import datetime
import decimal
import json
import sys
import traceback
from typing import Any, Literal
import httpx
from loguru import logger
from solana.rpc.async_api import AsyncClient
from solders.signature import Signature
import websockets
import websockets.client
import websockets.connection
import websockets.exceptions

from solana_snipping.constants import SOL_ADDR, USDT_ADDR, WSOL_ADDR
from solana_snipping.external.dex import RadiumAPI
from solana_snipping.tg import send_msg_log

pool_account_address = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
url = "wss://api.mainnet-beta.solana.com"
client = AsyncClient("https://api.mainnet-beta.solana.com")


def format_number(num: int | float | str, decimals: int = None) -> str:
    num = float(num)
    return f"{num:,.15}".rstrip("0").rstrip(".")


async def solscan_market(*mint_addrs) -> dict[str, Any]:
    client = httpx.AsyncClient()
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
        "origin": "https://solscan.io",
        "priority": "u=1, i",
        "referer": "https://solscan.io/",
        "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        # "sol-aut": "a=IytegZKfZB9dls0fKkCGFptCPJ9UrmFpou8hmR",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    }

    params = {
        "ids": ",".join(mint_addrs),
    }

    resp = await client.get(
        "https://price.jup.ag/v4/price", params=params, headers=headers
    )
    response = resp.json()

    return response


async def get_volume_of_pool(trans: str):
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
        # 'if-none-match': 'W/"1b8f7-12gT2Zb0QtzhIJw7KRKvSdx0mm4"',
        "origin": "https://solscan.io",
        "priority": "u=1, i",
        "referer": "https://solscan.io/",
        "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        # 'sol-aut': 'dKPXT8rWbfzL47YnKIFfWFT0xVMB9dls0fKLAy2T',
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    }

    params = {
        "tx": trans,
    }
    url = "https://api-v2.solscan.io/v2/transaction/detail"
    client = httpx.AsyncClient()

    resp = await client.get(url, headers=headers, params=params)
    response = resp.json()
    if not response.get("success"):
        return response

    def find_pool_id():
        for obj in response["data"]["parsed_instructions"]:
            try:
                if obj["program"].count("raydium_amm"):
                    for activity in obj["activities"]:
                        try:
                            return activity["data"]["amm_id"]
                        except Exception as e:
                            logger.exception(e)
            except Exception as e:
                logger.exception(e)

    pool_id = find_pool_id()
    if pool_id is None:
        return

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
        # 'cookie': '_ga=GA1.1.1196653353.1724497524; _ga_PS3V7B7KV0=GS1.1.1724782985.9.1.1724787342.0.0.0; cf_clearance=22EWDIP5.4Y0Z.Ow6S5jserXlkB_PINBLOBs3UHwwIM-1724787344-1.2.1.1-YS_svBaytZ1eqpPN6ns.Eyk8Yj0srEcy1x1PPB9FniK5619pZDd.YqRrpYba_YwRauaSgSxlc2H..tIkjD_BDmanbCfLfUWtO_ex5jq4ZTyAhvBGVaFQ9u1V7XPFeH9NZAh6RhUWT0z43iqFLYc6yMi4nk_2RYmHqTb0QigJJv4DiPqetHZTYp1WiSaF20Xtqa1cW_diqqLPqFCbHtJ3vr1qv8cKDlyhiVM8XxfqGDVn9ULpu0p8Ks8TRqemxRtRUWyDq8emsmqh4ymlZ_xgu3iLWfYLquFOcneH8wCh0qDo0Z3wqytFiraIdGaJYtFBSUqGiibqcAoUp4l6kdgieZNGmUi52Bnl5.ljGGexHGeNT4Y.9uyD.4yeiD8GJZLR',
        # "if-none-match": 'W/"933-XAPJ2K93tCVRXI6EHiA2Vz/iUvk"',
        "origin": "https://solscan.io",
        "priority": "u=1, i",
        "referer": "https://solscan.io/",
        "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        # "sol-aut": "zb9OySWyo4HB9dls0fKNCWiyf5nfOzeJy7AW6t0c",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    }

    params = {
        "address": pool_id,
    }

    resp = await client.get(
        "https://api-v2.solscan.io/v2/defi/pool_info", params=params, headers=headers
    )
    response = resp.json()

    amount = None
    token = None
    for num in [1, 2]:
        try:
            if response["data"][f"token{num}"].count(WSOL_ADDR[:-3]):
                amount = response["data"][f"token{num}_amount"]
                token = response["data"][f"token{num}"]
                break
        except Exception:
            pass

    if not amount or not token:
        return

    resp = await solscan_market(token)
    price = resp["data"][token]["price"]
    return price * amount * 2


async def get_first_liquidity_add_value(trans: str) -> float:
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
        # 'if-none-match': 'W/"1b8f7-12gT2Zb0QtzhIJw7KRKvSdx0mm4"',
        "origin": "https://solscan.io",
        "priority": "u=1, i",
        "referer": "https://solscan.io/",
        "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        # 'sol-aut': 'dKPXT8rWbfzL47YnKIFfWFT0xVMB9dls0fKLAy2T',
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    }

    params = {
        "tx": trans,
    }
    url = "https://api-v2.solscan.io/v2/transaction/detail"

    resp = await httpx.AsyncClient().get(url, headers=headers, params=params)
    response = resp.json()
    summary_actions = response["data"]["render_summary_main_actions"]

    full_price = 0
    for obj in summary_actions[0]["title"][0]:
        for k, v in obj.items():
            if k not in ["token_amount", "number", "decimals", "token_address"]:
                continue
            amount = v["number"]
            decimals = v["decimals"]
            tokens = decimal.Decimal(float(amount) / int("1" + "0" * decimals))
            market_resp = await solscan_market(v["token_address"])
            try:
                full_price += market_resp["data"][v["token_address"]]["price"] * float(
                    tokens
                )
            except Exception as e:
                continue

    return round(full_price, 2)


async def get_token_from_transactions_from_blockchain(sig: str) -> list[str, str, str]:
    resp = await client.get_transaction(
        Signature.from_string(sig), max_supported_transaction_version=0,
        encoding="jsonParsed"
    )

    solmint = "So111111111111111111111111111111111"
    try:
        instructions = resp.value.transaction.transaction.message.instructions
        accounts = [i.accounts for i in instructions if str(i.program_id) == '675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8'][0]
        token1 = accounts[8].__str__()
        token2 = accounts[9].__str__()
        pair = accounts[4].__str__()
        
        tokens = [token1, token2]
        if tokens[0].count(solmint):
            tokens.reverse()
            
        tokens.append(pair)
            
        return tokens
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
    decimals: int = 9,
):
    response = await RadiumAPI().get_swap_info(mint1, mint2, amount=amount)
    if not response.get("success"):
        return f"raw error: {response}"

    price = response["data"]["outputAmount"]
    result = decimal.Decimal(float(price) / int("1" + "0" * decimals))
    return round(result, decimals)


async def process_transaction(signature: str):
    mint, token2, pair = await get_token_from_transactions_from_blockchain(sig=signature)
    if not mint:
        with open("failed_transactions.txt", "a") as f:
            f.write(f"{signature}\n\n")
        return

    return mint, token2, pair


async def process_mint(mint: str, dt: datetime, signature_trans: str, pool_id: str, token2: str):
    try:
        # pool_raydium = await get_liquidity_from_pool(mint)
        pool_raydium = await get_first_liquidity_add_value(signature_trans)
        pool_raydium = format_number(pool_raydium)
    except Exception:
        pool_raydium = None

    try:
        volume_of_pool = await RadiumAPI().get_liquidity_from_pool(pool_id)
        if volume_of_pool:
            volume_of_pool = format_number(volume_of_pool)
    except Exception as e:
        logger.exception(e)
        volume_of_pool = None

    try:
        price = await swap_on_jupiter(mint1=mint)
        price = format_number(price)
    except Exception:
        price = "Не удалось получить цену"

    # Buy here

    message = (
        f"Адрес - *{mint}*\n"
        f"Поймали транзакцию в _{dt}_, купили монету в _{datetime.now()}_.\n\n"
        f"Первая ликвидность: *{pool_raydium}* USD.\n"
        f"Объем пула сейчас: *{volume_of_pool}* USD.\n"
        f"Купили по цене: 1 token = *{price}* SOL\n"
    )
    with open("logs.txt", "a") as f:
        f.write(f"{message}\n\n")
    await send_msg_log(message, mint, trans=signature_trans)


async def strategy():
    async for signature, time in get_newest_token_transactions_from_raydium_pool():
        print(signature, time)
        try:
            mint, token2, pair = await process_transaction(signature)
            await process_mint(mint, time, signature, pair, token2=token2)
        except Exception as e:
            logger.exception(e)


async def main():
    return await strategy()
    # mint = "5FdLfn2yx2b4x3WULG9oXw3zigj3gTx8ZBcQWZ59YbkY"
    # print(await swap_on_jupiter(mint1=mint))

    # sig = "2HYbGQ843hMs5rQqySRNKqpHiMygmGt8WVygxwEid52Zx5UPxhXT8CHD4MAuNW9pNajBLkvuccCLCvJJyYxhJ8yK"
    # time = datetime.now()
    # mint = await process_transaction(sig)
    # await process_mint(mint, time, sig)

    # volume = await get_volume_of_pool(sig)
    # print(volume)
    # response = await get_first_liquidity_add_value(sig)
    # print(response)
    ...


def global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    stack = "".join(
        traceback.format_exception(exc_type, value=exc_value, tb=exc_traceback)
    )
    logger.error(f"exception {exc_type.__name__}:\n{stack}")


if __name__ == "__main__":
    print(datetime.now())
    logger.add("debug_program.log")
    sys.excepthook = global_exception_handler
    asyncio.run(main())
