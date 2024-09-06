import decimal
import httpx

from solana_snipping.backend.utils import append_hdrs
from solana_snipping.common.constants import WSOL_ADDR


class Solscan:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient()

    @property
    def _base_hdrs(self):
        hdrs = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "origin": "https://solscan.io",
            "priority": "u=1, i",
            "referer": "https://solscan.io/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
        }

        return append_hdrs(hdrs)

    async def _raw_pool_info(self, pool_id: str):
        headers = self._base_hdrs
        url = "https://api-v2.solscan.io/v2/defi/pool_info"
        params = {
            "address": pool_id,
        }
        resp = await self._client.get(url, headers=headers, params=params)
        return resp.json()

    async def get_tvl_of_pool(self, pool_id: str):
        response = await self._raw_pool_info(pool_id=pool_id)

        if not response.get("success"):
            return response

        if not response.get("data"):
            return None

        return response["data"]["tvl"] * 2

    async def _raw_trans_detail_info(self, trans_id: str, proxy: str = None):
        headers = self._base_hdrs
        params = {"tx": trans_id}
        url = "https://api-v2.solscan.io/v2/transaction/detail"

        async with httpx.AsyncClient(proxy=proxy) as client:
            resp = await client.get(url, headers=headers, params=params)

        return resp.json()

    async def get_added_liquidity_value(self, trans: str, proxy: str = None) -> float:
        response = await self._raw_trans_detail_info(trans_id=trans, proxy=proxy)
        summary_actions = response["data"]["render_summary_main_actions"]

        full_price = 0
        for obj in summary_actions[0]["title"][0]:
            for k, v in obj.items():
                if k not in ["token_amount", "number", "decimals", "token_address"]:
                    continue
                
                if obj["token_amount"]["token_address"] != WSOL_ADDR:
                    continue
                
                amount = v["number"]
                decimals = v["decimals"]
                tokens = decimal.Decimal(float(amount) / int("1" + "0" * decimals))
                market_resp = await self._raw_solscan_market(
                    v["token_address"], proxy=proxy
                )
                try:
                    full_price += market_resp["data"][v["token_address"]][
                        "price"
                    ] * float(tokens)
                except Exception:
                    continue

        return round(full_price, 2)

    async def _raw_solscan_market(self, *mint_addrs, proxy: str = None):
        params = {
            "ids": ",".join(mint_addrs),
        }

        async with httpx.AsyncClient(proxy=proxy) as client:
            resp = await client.get(
                "https://price.jup.ag/v4/price", params=params, headers=self._base_hdrs
            )
        return resp.json()


async def main():
    solscan = Solscan()
    # print(await solscan.get_tvl_of_pool("C47dSSMTUTjphq9QS1CAUsBfQGuPzNr6EUBSTz6Z1aQc"))
    print(
        await solscan.get_added_liquidity_value(
            "4TU6bGgQPcpH4EGnpWx5FRCqNuvAaGcrrLpS8Mf6rCekNSyHinR9JQhNsZEMx7KyzjScrqPpZXPSCCRTet91X5oQ"
        )
    )
    ...


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
