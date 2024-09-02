import httpx

from solders.pubkey import Pubkey # type: ignore
from solana_snipping.common.constants import solana_async_client


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
        if not response.get("risks"):
            return None
        return len(response["risks"])


class WalletAudit:
    
    def __init__(self) -> None:
        self._solclient = solana_async_client
    
    async def get_finalized_signatures(self, wallet_addr: str):
        pub = Pubkey.from_string(wallet_addr)
        resp = await self._solclient.get_signatures_for_address(pub, commitment="finalized")
        return resp.value
