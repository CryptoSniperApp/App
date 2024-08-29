import httpx

from solana_snipping.constants import USDT_ADDR


class JupiterAPI:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient()

    async def get_swap_info(
        self, token1: str, token2: str, amount: int = 50, swap_mode: str = "ExactIn"
    ):
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
            "swapMode": swap_mode,
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
            "amount": str(amount * 1_000_000).replace(".", ""),
            "slippageBps": "50",
            "txVersion": "V0",
        }
        url = "https://transaction-v1.raydium.io/compute/swap-base-in"
        resp = await self.client.get(url, params=params, headers=headers)
        return resp.json()

    async def get_amount_in_usdt(self, tokenaddr):
        response = await self.get_swap_info(tokenaddr, USDT_ADDR, amount=1)
        return int(response["data"]["outputAmount"]) / 1_000_000

    async def get_liquidity_from_pool(self, pool_id: str):
        headers = {
            "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://raydium.io/",
            "sec-ch-ua-mobile": "?0",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "sec-ch-ua-platform": '"Linux"',
        }

        params = {
            "ids": pool_id,
        }

        resp = await self.client.get(
            "https://api-v3.raydium.io/pools/info/ids", params=params, headers=headers
        )
        response = resp.json()
        return round(
            response["data"][0]["lpAmount"] * response["data"][0]["lpPrice"], 3
        )
