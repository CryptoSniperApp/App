import asyncio
from datetime import datetime
import json
import sys
import time
import traceback
from zoneinfo import ZoneInfo
import aiohttp
import httpx
from loguru import logger

from solana_snipping.tg import send_msg_log


class SolscanAPI:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient()

    async def get_token(self, token_addr: str):
        url = f"https://api-v2.solscan.io/v2/search?keyword={token_addr}"

        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            # "if-none-match": 'W/"9b3-d3x5mHujgA993/rzjAGKGmLL74c"',
            "origin": "https://solscan.io",
            "priority": "u=1, i",
            "referer": "https://solscan.io/",
            "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            # 'sol-aut': 'okqvB9dls0fKEmix=sMZz6=G2AN3Xde7EDqajpuK',
            # "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImRldi50b2xtYWNoZXZAZ21haWwuY29tIiwiYWN0aW9uIjoibG9nZ2VkIiwiaWF0IjoxNzIzODEwMDE1LCJleHAiOjE3MzQ2MTAwMTV9.LyZRc2IjceHIhSHnMElbbxVjOQClFmI_YChsC1RPCJk",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        }

        resp = await self.client.get(url, headers=headers)
        return resp.json()

    async def get_count_transfers(self, tokenaddr: str):
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            # 'cookie': '_ga=GA1.1.874406707.1724236388; cf_clearance=WfybjUUqj.RCgIwLgaBM5UkoY3hvkaevMAI9MG5b_4k-1724341695-1.2.1.1-1Gafv1w02CKomF6xGOKgRWaKcGNNxTesMH9dlXXHlTtxGEyagTZnLlSk65Bc9pczA2eFIT1ne2VX1M6zSpn2dPxHqDR45AAn5MlrWvcmwXK4quX0Sv7ZRXz8jnHRD0Ta9S7Pjf8mtVs_RhEPVW7d3w_NgM_ruD96enkbzTh5HMGRrtBq2skwVA81XIj3vY1yQ50qwOSqh.UXsO79OgpMfP2pfYcm2_bUg1Es1WNBYRXsBRGlitNCRbIkzHYDY0CAPI6kuudDznVDCEYEAUS1Kf5lVC1Y.hAXJbfqcFt31AojjsYbp7vZDB3MQ6hkDvWrEQVH3GIDkmvF17oNQ1zxLydd0DPR8gT6DbMGWR0YZGqgOT_Ee4B0Vkswf0AiIP.0; _ga_PS3V7B7KV0=GS1.1.1724339834.3.1.1724341735.0.0.0',
            # 'if-none-match': 'W/"2b-bIL1JICknWNjUR5J0H/+dfNBVYM"',
            "origin": "https://solscan.io",
            "priority": "u=1, i",
            "referer": "https://solscan.io/",
            "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            # 'sol-aut': 'YmwHBB9dls0fKvjvsbTgJj3=9zKK--6--BEJCYq4',
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        }

        params = {
            "address": tokenaddr,
            "exclude_amount_zero": "false",
        }

        url = "https://api-v2.solscan.io/v2/token/transfer/total"
        resp = await self.client.get(url, params=params, headers=headers)
        response = resp.json()
        return response["data"] if response.get("data") else 0

    async def get_acount_token(self, tokenaddr: str):
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "if-none-match": 'W/"9b3-d3x5mHujgA993/rzjAGKGmLL74c"',
            "origin": "https://solscan.io",
            "priority": "u=1, i",
            "referer": "https://solscan.io/",
            "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "sol-aut": "4w12sR8o-WnqQVRoO1qzHB9dls0fK3xK2i5aBBIq",
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImRldi50b2xtYWNoZXZAZ21haWwuY29tIiwiYWN0aW9uIjoibG9nZ2VkIiwiaWF0IjoxNzIzODEwMDE1LCJleHAiOjE3MzQ2MTAwMTV9.LyZRc2IjceHIhSHnMElbbxVjOQClFmI_YChsC1RPCJk",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        }

        url = f"https://api-v2.solscan.io/v2/account?address={tokenaddr}"
        resp = await self.client.get(url, headers=headers)
        return resp.json()

    async def get_token_price(self, tokenaddr: str):
        url = f"https://price.jup.ag/v4/price?ids={tokenaddr}"

        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "origin": "https://solscan.io",
            "priority": "u=1, i",
            "referer": "https://solscan.io/",
            "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        }

        resp = await self.client.get(url, headers=headers)
        return resp.json()

    async def token_exists(self, addr: str) -> bool:
        data = await self.get_token(addr)
        if data.get("data"):
            return True
        return False

    async def pool_token(self, addr: str):
        url = f"https://api-v2.solscan.io/v2/token/pools?page=1&page_size=10&token[]={addr}"
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            # 'cookie': '_ga=GA1.1.722851510.1723621279; cf_clearance=dJEoB_LtLhxIpjgtGOEWVvPdLyY5_Z0tqf3uHKnyEFM-1723827958-1.0.1.1-c.J.8CYgJQ1ePPEmdoXYodS0n2O3zOwuyXVh4g6I7pxNDMfkxhSgy7Uu6IPW8E_UnyxCoXhkinWnIpy4fTEuTw; _ga_PS3V7B7KV0=GS1.1.1723832438.12.1.1723833182.0.0.0',
            # "if-none-match": 'W/"977-kuvYxBoeX3r3FxwlRkxlrIZVJc4"',
            "origin": "https://solscan.io",
            "priority": "u=1, i",
            "referer": "https://solscan.io/",
            "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            # "sol-aut": "G=dEYy-=drYSC6x0jioeZBpPoB9dls0fK3frxnlH",
            # "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImRldi50b2xtYWNoZXZAZ21haWwuY29tIiwiYWN0aW9uIjoibG9nZ2VkIiwiaWF0IjoxNzIzODEwMDE1LCJleHAiOjE3MzQ2MTAwMTV9.LyZRc2IjceHIhSHnMElbbxVjOQClFmI_YChsC1RPCJk",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        }
        resp = await self.client.get(url, headers=headers)

        return resp.json()

    async def get_total_holders(self, addr: str):
        url = f"https://api-v2.solscan.io/v2/token/holder/total?address={addr}"
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            # 'cookie': '_ga=GA1.1.722851510.1723621279; cf_clearance=dJEoB_LtLhxIpjgtGOEWVvPdLyY5_Z0tqf3uHKnyEFM-1723827958-1.0.1.1-c.J.8CYgJQ1ePPEmdoXYodS0n2O3zOwuyXVh4g6I7pxNDMfkxhSgy7Uu6IPW8E_UnyxCoXhkinWnIpy4fTEuTw; _ga_PS3V7B7KV0=GS1.1.1723832438.12.1.1723834347.0.0.0',
            # "if-none-match": 'W/"29-No44Jdy4XMog8u8bM90EpJR/QuM"',
            "origin": "https://solscan.io",
            "priority": "u=1, i",
            "referer": "https://solscan.io/",
            "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            # "sol-aut": "Hht7mnB9dls0fKTMO97RFAno=khBzGfQQT2uJxQB",
            # "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImRldi50b2xtYWNoZXZAZ21haWwuY29tIiwiYWN0aW9uIjoibG9nZ2VkIiwiaWF0IjoxNzIzODEwMDE1LCJleHAiOjE3MzQ2MTAwMTV9.LyZRc2IjceHIhSHnMElbbxVjOQClFmI_YChsC1RPCJk",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        }

        resp = await self.client.get(url, headers=headers)
        return resp.json()

    async def get_general_info(self, addr: str):
        exists = await self.token_exists(addr)
        if not exists:
            return {
                "exists": False,
                "created_ts": None,
                "first_mint_ts": None,
                "market": None,
                "about": None,
            }

        account = await self.get_acount_token(addr)
        token_info = account["data"]["tokenInfo"]

        created_time = token_info.get("created_time")
        first_mint_time = token_info.get("first_mint_time")

        about_token_info = {}
        if isinstance(account["metadata"]["tokens"], list):
            try:
                about_token_info = account["metadata"]["tokens"][0]
            except Exception as e:
                pass

        elif isinstance(account["metadata"]["tokens"], dict):
            about_token_info = account["metadata"]["tokens"].get(addr, {})

        about = {}
        if about_token_info.get("extension"):
            about = {
                "website": about_token_info["extension"]["website"],
                "description": about_token_info["extension"]["website"],
            }

        holders = await self.get_total_holders(addr)
        price_data = await self.get_token_price(addr)
        ...
        market = {
            "supply": float(token_info.get("supply") or 0) / 1_000_000,
            "holders": None,
            "market_cap": None,
            "price": None,
        }

        if holders.get("data"):
            market["holders"] = holders["data"]

        if price_data.get("data") and price_data["data"].get(addr):
            market["price"] = price_data["data"][addr].get("price")

        if type(market["price"]) in [float, int] and type(market["supply"]) in [
            float,
            int,
        ]:
            market["market_cap"] = market["supply"] * market["price"]

        return {
            "exists": True,
            "created_ts": created_time,
            "first_mint_ts": first_mint_time,
            "market": market,
            "about": about,
        }


class RadiumPool(SolscanAPI):
    
    def __init__(self) -> None:
        super().__init__()
        self._cached = []
    
    async def get_newest_tokens(self, q: asyncio.Queue, max_transfers: int = 70):
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            # 'if-none-match': 'W/"1ba6-0s4h5TpBqnj2RcWzys0QYKG4tbM"',
            "origin": "https://solscan.io",
            "priority": "u=1, i",
            "referer": "https://solscan.io/",
            "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            # 'sol-aut': 'QuotGYdJQ91B9dls0fKy2OVewDrbKTmSXod4nEco',
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        }

        raydium_authority_v4 = "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"
        params = {
            "address": raydium_authority_v4,
            "page": "1",
            "page_size": "100",
            "remove_spam": "true",
            "exclude_amount_zero": "false",
            "exclude_token": "So11111111111111111111111111111111111111111",
        }
        bmints = ['So11111111111111111111111111111111111111112']
        checked_mints = set()
        # pool = await get_full_pool()
        
        # try:
        #     async with asyncio.timeout(50):
        #         while len(pool.proxies) < 5:
        #             await asyncio.sleep(1)
        # except asyncio.TimeoutError:
        #     pass
        # else:
        #     client = await pool.get_session()
        #     self.client = client
        
        try:
            while True:
                try:
                    resp = await self.client.get(
                        "https://api-v2.solscan.io/v2/account/transfer",
                        params=params,
                        headers=headers,
                    )
                except httpx.ReadTimeout:
                    await asyncio.sleep(10)
                    continue
                except Exception as e:
                    pass
                    # print(logger.exception(e))
                
                try:
                    if isinstance(self.client, aiohttp.ClientSession):
                        response = await resp.json()
                    else:
                        response = resp.json()

                    if not response.get("success"):
                        raise ValueError(f"Not success request: {response}")
                    
                    print(f"we get {len(response["data"])} transfers")
                    
                    for block in response["data"]:
                        mint = block["token_address"]

                        if mint in bmints or mint in self._cached or mint in list(checked_mints):
                            continue

                        count = await self.get_count_transfers(mint)
                        checked_mints.add(mint)
                        print(f"{mint}: {count} transfers")
                        await asyncio.sleep(1)
                        if count > max_transfers:
                            continue
                        
                        await q.put(mint)
                        self._cached.append(mint)
                        
                    await asyncio.sleep(5)
                except Exception as e:
                    pass
                    # print(logger.exception(e))
        finally:
            if isinstance(self.client, aiohttp.ClientSession):
                await self.client.close()

    async def _lp_info(self, addr: str):
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            # 'cookie': '_ga=GA1.1.874406707.1724236388; cf_clearance=6hIgzHK7MBEbZz7oqO4zcoRNl9LR5ftRXTJS6B8QTd8-1724354311-1.2.1.1-tI_oKhOqnzBbzT7oY9euzk_gV4tKqN8Qpb5OThtvJnQOpDcHCaL4artBWvDpudJtl3cOZeUYFLuH.hRgbuhsYlEfZc5T__keprFGltCUtTiazaRykrwY3TFmzBaN25yAaJLLOb9RYmFPTzBUnNl7D2PGHYcz5sn5YIxF6sdJ3LVqMa3Bc25j9Y0onCbylfkyBJqhNoFeoNt28yP06gMMJ1xlKy03iZklsHcQ2jTW9w061e.D6o305GnQgRck5nTVAk5Z4S7kZOzHQluk73J5DFeJM5s3t8YUv3l44so6TkAeczky3RpUZATRJHyv1NYLn6KSXdtSUKwmPPNizN7b1mNQYp9KLo_R4SWd3i_8o4NPYV1EdlINNYBAM4V3s.1F; _ga_PS3V7B7KV0=GS1.1.1724351750.4.1.1724354657.0.0.0',
            # 'if-none-match': 'W/"8bb-KPcUyezn+TW0tIKbTej42lc/aDw"',
            "origin": "https://solscan.io",
            "priority": "u=1, i",
            "referer": "https://solscan.io/",
            "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            # 'sol-aut': 'cTINUZcaccgL2yxDGnKQbqu=nB9dls0fKjhx90Gd',
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        }

        params = {
            "address": addr,
            "page": "1",
            "page_size": "100",
            "exclude_amount_zero": "false",
        }

        resp = await self.client.get(
            "https://api-v2.solscan.io/v2/token/transfer",
            params=params,
            headers=headers,
        )
        response = resp.json()
        
        if not response.get('success'):
            raise ValueError(f"Request unsuccessfully: `{response}`")
        
        return response


async def send_in_tg(mint: str):
    solscan = SolscanAPI()
    account_info = json.dumps(await solscan.get_acount_token(mint), ensure_ascii=False, indent=2)
    general_info = json.dumps(await solscan.get_general_info(mint), ensure_ascii=False, indent=2)
    
    message = (
        f"Адрес - *{mint}*\n"
        f"Информация об аккаунте\n\n```json\n{account_info}```\n\n"
        f"Основная информация о токене\n\n```json\n{general_info}```\n\n"
        f"Время фиксации - {datetime.now()}"
    )
    logger.success(message)
    await send_msg_log(message)
    ...


async def main():
    pool = RadiumPool()
    q = asyncio.Queue()

    asyncio.create_task(pool.get_newest_tokens(q=q, max_transfers=50))
    
    while True:
        token = await q.get()
        asyncio.create_task(send_in_tg(token))
        ...
    ...

def global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    stack = "".join(traceback.format_exception(exc_type, value=exc_value, tb=exc_traceback))
    logger.error(f"exception {exc_type.__name__}:\n{stack}")


if __name__ == "__main__":
    print("я начал")
    logger.add("debug_program.log")
    sys.excepthook = global_exception_handler
    asyncio.run(main())
