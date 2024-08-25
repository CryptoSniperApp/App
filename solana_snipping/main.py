import asyncio
from datetime import datetime
import json
from pprint import pprint
import re
from shlex import join
from asyncstdlib import enumerate
import httpx
import solana
from solana.rpc.api import Client
from solana.rpc.types import TokenAccountOpts
from solders.rpc.responses import LogsNotificationResult
from solana.rpc.websocket_api import connect
from solders.rpc.config import RpcTransactionLogsFilter
from solders.pubkey import Pubkey
from solders.signature import Signature


from pysolscan import solscan


USDT_ADDR = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"


pubkey = Pubkey.from_string("5o2q4hvw52F54SafB1co6KE8VLEStgZfHSVJseQ4eyss")
client = Client("https://api.mainnet-beta.solana.com")


async def parse_transaction(
    signature: str = "3XRSbdDekj4971eEuzgaDkgdv4q2C958JyyM1t2ncVkyMi9TAPgRn11GFvC7qQGLAzowbmn2xHYogN1qMETcsMb6",
):
    signature = Signature.from_string(signature)
    resp = client.get_transaction(
        signature, max_supported_transaction_version=0
    )
    meta = resp.value.transaction.meta

    token_addrs = []

    for token_balance in meta.post_token_balances + meta.pre_token_balances:
        addr = "".join(
            re.findall(
                r"[\da-zA-Z]",
                str(token_balance.mint),
            )
        )
        if addr not in token_addrs:
            token_addrs.append(addr)

    return token_addrs


async def get_token_info(token_addr: str):
    pubkey = Pubkey.from_string(token_addr)
    data = client.get_account_info(pubkey)

    signatures = client.get_signatures_for_address(data.value.owner)
    while signatures:
        await asyncio.sleep(2)
        curr_signature = signatures.value[-1]
        ts = curr_signature.block_time
        date = datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
        print(date)

        for sig in reversed(signatures.value):
            if sig.err or not sig.signature:
                continue

            signatures = client.get_signatures_for_address(
                data.value.owner, before=sig.signature
            )
            break

    res = client.get_block_time(data.context.slot)
    ...


import asyncio
import pandas as pd
from gql import Client, gql
from gql.transport.websockets import WebsocketsTransport


class SolscanAPI:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient()
        pass

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
    
    async def get_pool_info(self, addr: str):
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6',
            # 'cookie': '_ga=GA1.1.722851510.1723621279; cf_clearance=xyBkZ.Y.lCKvTf7RccnI82Ajj__Mmx8svdp_BbJ6IHs-1723899021-1.2.1.1-cvJFEV25XNHk7g0Ql9OVscBHIPimhT9ivRMPRLnQBHkA93m4TgzJ8Nbae5bOVvTYRcs3z9un2S2vWU1pisDcYFnpj_L6YiB1y_Pksp7SoKAaqeb4oTraU7P7eVLzpVj3Ru6HEjBEfE.gM97Kime6aNcixkCKC0puFFbstPg.pTi6xFWpEqMLO1Hxf3_n0K89GmhckKwffGeifFf_BqNW1w30I4ki1BZt2rU7UxlC4MJ7nrqpq0bXvPOhs_B4hai4VH8FoC9gCfaIYpmmDnfTp.ctRGHdIbArDGQv6O19uAJgu8vuZcRprn2CfxlXUEAoBH_OmFEHQ5hMRmZK4rNzp33b.FNq7F8ugtnYWplyA3BeTHKhOe4_tpmkuvvUELaG; _ga_PS3V7B7KV0=GS1.1.1723918421.15.1.1723920596.0.0.0',
            # 'if-none-match': 'W/"78e-xj6b40y6bskHKh+vr2EclTPLQ78"',
            'origin': 'https://solscan.io',
            'priority': 'u=1, i',
            'referer': 'https://solscan.io/',
            'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            # 'sol-aut': '7uQdCGBz9Ki-FRkEB9dls0fKJeuq8cXIBbwHoZkM',
            # 'token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImRldi50b2xtYWNoZXZAZ21haWwuY29tIiwiYWN0aW9uIjoibG9nZ2VkIiwiaWF0IjoxNzIzODEwMDE1LCJleHAiOjE3MzQ2MTAwMTV9.LyZRc2IjceHIhSHnMElbbxVjOQClFmI_YChsC1RPCJk',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        }
        params = {
            'address': '52Dj48bHNmUh9fT4A7u3A2Zu94RfLgtKCbGzJNSf96ov',
        }
        url = 'https://api-v2.solscan.io/v2/defi/pool_info'
        
        resp = await self.client.get(url, params=params, headers=headers)
        return resp.json()

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
        
    async def get_pool_open_time(self, addr: str):
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6',
            'origin': 'https://solscan.io',
            'priority': 'u=1, i',
            'referer': 'https://solscan.io/',
            'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        }

        params = {
            'address': addr,
        }
        
        url = "https://api-v2.solscan.io/v2/account"
        resp = await self.client.get(url, params=params, headers=headers)
        response = resp.json()
        return int(json.loads(response["data"]["parsedData"])["poolOpenTime"])


class RugCheckAPI:
    """
    https://rugcheck.xyz/
    """

    def __init__(self) -> None:
        self.client = httpx.AsyncClient()
        pass

    async def get_report(self, tokenaddr: str):
        headers = {
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "Authorization": "",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://rugcheck.xyz",
            "Referer": "https://rugcheck.xyz/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "X-Wallet-Address": "null",
            "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
        }

        url = f"https://api.rugcheck.xyz/v1/tokens/{tokenaddr}/report"

        resp = await self.client.get(url, headers=headers)

        return resp.json()

    async def count_of_warnings(self, addr: str):
        response = await self.get_report(addr)
        return len(response["risks"])


class JupiterAPI:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient()

    async def get_swap_info(self, token1: str, token2: str, amount: int = 50):
        headers = {
            "accept": "*/*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "origin": "https://jup.ag",
            "priority": "u=1, i",
            "referer": "https://jup.ag/",
            "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        }

        params = {
            "inputMint": token1,
            "outputMint": token2,
            "amount": amount * 1_000_000,
            "slippageBps": "300",
            "computeAutoSlippage": "true",
            "swapMode": "ExactIn",
            "onlyDirectRoutes": "false",
            "asLegacyTransaction": "false",
            "maxAccounts": "64",
            "minimizeSlippage": "false",
        }
        url = "https://quote-api.jup.ag/v6/quote"
        resp = await self.client.get(url, params=params, headers=headers)
        return resp.json()

    async def get_amount_in_usdt(self, tokenaddr):
        response = await self.get_swap_info(tokenaddr, USDT_ADDR, amount=1)
        return int(response["outAmount"]) / 1_000_000


class RadiumAPI:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient()

    async def get_swap_info(self, token1: str, token2: str, amount: int = 50):
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "origin": "https://raydium.io",
            "priority": "u=1, i",
            "referer": "https://raydium.io/",
            "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        }

        params = {
            "inputMint": token1,
            "outputMint": token2,
            "amount": amount * 1_000_000,
            "slippageBps": "50",
            "txVersion": "V0",
        }
        url = "https://transaction-v1.raydium.io/compute/swap-base-in"
        resp = await self.client.get(url, params=params, headers=headers)
        return resp.json()

    async def get_amount_in_usdt(self, tokenaddr):
        response = await self.get_swap_info(tokenaddr, USDT_ADDR, amount=1)
        return int(response["data"]["outputAmount"]) / 1_000_000


async def run_subscription():
    # Setup WebSocket connection
    token = "ory_at_hV28Na5oA-2G6Zr3r2HnaVUle-uibmPdMyWsoIgTbUs.3eXtT211RahfbAUFvRVB0SeZ1NT9kdOMlMsLiCVJggY"
    transport = WebsocketsTransport(
        url=f"wss://streaming.bitquery.io/eap?token={token}",
        headers={"Sec-WebSocket-Protocol": "graphql-ws"},
        ping_interval=None,
    )

    # Establish the connection
    await transport.connect()
    print("Connected to WebSocket")

    start = None

    subscribtion = transport.subscribe(
        gql("""
                subscription {
                    Solana {
                        General: Instructions(
                            where: {
                                Instruction: {
                                    Program: {
                                        Method: {in: ["initializeAccount", "mintTo", "initializeAccount2", "initializeAccount3", "initializeMint2"]},
                                    }
                                }, 
                                Transaction: {
                                    Result: {Success: true}
                                }
                            }
                            
                            ) {
                            Block {
                                Time    
                            }
                            Instruction {
                                Accounts {
                                    Address
                                    IsWritable
                                    Token {
                                        Owner
                                        ProgramId
                                        Mint
                                }
                                }
                                Program {
                                    AccountNames
                                    Address
                                }
                            }
                            count
                        }
                    }
                }
                """)
    )
    api = SolscanAPI()
    while True:
        async for result in subscribtion:
            if result.data:
                tokens = [
                    obj["Token"]["Mint"]
                    for obj in result.data["Solana"]["General"][0][
                        "Instruction"
                    ]["Accounts"]
                    if obj["Token"]["Mint"]
                ]
                if not tokens:
                    continue

                for addr in tokens:
                    
                    if addr == "So11111111111111111111111111111111111111112" or not addr:
                        continue
                    
                    data = await api.get_general_info(addr)
                    
                    pools_info = await api.pool_token(addr)
                    
                    for pool in pools_info["data"]:
                        pool_addr = pool["pool_id"]
                        pool_info = await api.get_pool_info(pool_addr)
                        try:
                            pool_created = await api.get_pool_open_time(addr)
                        except KeyError:
                            continue
                        ...
                    
                    pprint(data)

                ...


async def solscan_():
    await run_subscription()
    jupiter = JupiterAPI()
    radium = RadiumAPI()
    audit = RugCheckAPI()
    
    solscan_api = SolscanAPI()
    
    data = await solscan_api.pool_token(
        "2AQP5hQeBz4zUEQg452NpgjiatRkaLJ8nAasDQGkpump"
    )
    pool_addr = "52Dj48bHNmUh9fT4A7u3A2Zu94RfLgtKCbGzJNSf96ov"
    pool = await solscan_api.get_pool_info(pool_addr)
    ...

    addr = "VH8FHAxrXQwK16YcHUqKZf9KJD3YJDTn6UxWaxMQT3w"
    print(f"Count of warnings in token: {await audit.count_of_warnings(addr)}")
    print(
        "Price for swap on 1 usdt in dex jupiter "
        f"{await jupiter.get_amount_in_usdt(addr):.5f}"
    )   
    print(
        "Price for swap on 1 usdt in dex radium "
        f"{await radium.get_amount_in_usdt(addr):.5f}"
    )
    # api = SolscanAPI()

    # tokenaddr = "24nb3XQwvE3BBRZ7QwB6F6tyAtEJXvarLq4Rj3XCpump"
    # data = await api.get_general_info(tokenaddr)
    # pprint(data)
    # return
    # print(await api.get_token(tokenaddr))
    # print(await api.get_acount_token(tokenaddr))
    # print(await api.get_token_price(tokenaddr))
    ...


async def main():
    return await solscan_()
    # token_addrs = await parse_transaction()

    # for addr in token_addrs:
    print(await get_token_info("5mK8m6ff6uHAhtfTzRihbf9cFDu3WH4joTYJSjeHpump"))
    # return
    needed_instructions = ["Mint"]
    async with connect("wss://api.mainnet-beta.solana.com") as websocket:
        # Подписываемся на уведомления о новых блоках
        await websocket.logs_subscribe()
        # await websocket.slots_updates_subscribe()

        while True:
            try:
                # Получаем данные о новом блоке
                data = await websocket.recv()
            except Exception as e:
                print(f"websocket.recv got error {e.__class__.__name__}: {e}")
                await asyncio.sleep(3)
                continue

            for msg in data:
                try:
                    result = msg.result
                    if not isinstance(result, LogsNotificationResult):
                        continue

                    full_signature = result.value.signature
                    logs = result.value.logs
                    signature = "".join(
                        re.findall(r"[\da-zA-Z]+", str(full_signature))
                    )
                    logs = [signature] + logs

                    with open("logs-full.log", "a") as f:
                        f.write(f"{"\n".join(logs)}\n\n")

                    if any(
                        "".join(logs).lower().count(instruction.lower())
                        for instruction in needed_instructions
                    ):
                        print(f"signature: {signature}")
                        logs = "\n".join(logs)
                        print(f"New logs:\n{logs}\n\n")
                        with open("logs.log", "a") as f:
                            f.write(f"{logs}\n\n")

                        token_addrr = [l for l in logs if l.count("Token")]
                        with open("token.log", "a") as f:
                            f.write(f"{"\n".join(token_addrr)}\n\n")
                    else:
                        print("wait for event")

                except Exception as e:
                    print(msg)

            # await asyncio.sleep(1)

        await websocket.wait_closed()


# async def main():
#     async with AsyncClient("https://api.devnet.solana.com") as client:
#         # blocks = await client.get_blocks(5)
#         blocks = await client.get_block(15)
#         print(blocks.to_json())
#         # while True:
#         #     # Получаем данные о новом блоке
#         #     data = await websocket.recv()
#         #     print("New Block Received:")
#         #     print(data)
#         #     await asyncio.sleep(1)

#         # await websocket.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())


"""
on https://jup.ag/va/EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm-USDT


curl 'https://public-api.birdeye.so/defi/ohlcv/base_quote?base_address=EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm&quote_address=Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB&type=1m&time_from=1724450367&time_to=1724487207' \
  -H 'accept: */*' \
  -H 'accept-language: ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6' \
  -H 'origin: https://jup.ag' \
  -H 'priority: u=1, i' \
  -H 'referer: https://jup.ag/' \
  -H 'sec-ch-ua: "Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "Linux"' \
  -H 'sec-fetch-dest: empty' \
  -H 'sec-fetch-mode: cors' \
  -H 'sec-fetch-site: cross-site' \
  -H 'user-agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36' \
  -H 'x-api-key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE2NzI5MDEwNzZ9.c66gFnI20ymHoPWapB0JgISzqDIK6Q_Zg0oAVp8Ssyc'
"""
