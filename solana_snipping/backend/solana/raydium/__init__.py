import betterproto

from grpclib.client import Channel
import httpx
from solana_snipping.backend.solana.raydium.generated.pools import PoolStateStub
from solana_snipping.backend.utils import append_hdrs
from solana_snipping.common.config import get_config


class RaydiumAPI:
    def __init__(self) -> None:
        self._grpc_conn = None
        self._http_client = httpx.AsyncClient()

    @property
    def _base_hdrs(self):
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "origin": "https://raydium.io",
            "priority": "u=1, i",
            "referer": "https://raydium.io/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
        }
        return append_hdrs(headers)

    async def get_volume_of_pool(self, pool_id: str):
        if not self._grpc_conn:
            self._setup_grpc_stub()

        data = await self._grpc_conn.get_pool_state(pool_address=pool_id)
        if data.error.error:
            obj = data.to_dict(
                casing=betterproto.Casing.SNAKE, include_default_values=True
            )
            return obj

        obj = data.to_dict(casing=betterproto.Casing.SNAKE, include_default_values=True)
        data = obj["data"]
        base_tokens_amounts = await self.price_usdc(data["base_mint"]) * float(
            data["base_token_amount"]
        )
        quote_tokens_amount = await self.price_usdc(data["quote_mint"]) * float(
            data["quote_token_amount"]
        )
        return base_tokens_amounts + quote_tokens_amount

    async def price_usdc(self, token_addr: str):
        params = {
            "mints": token_addr,
        }
        resp = await self._http_client.get(
            "https://api-v3.raydium.io/mint/price",
            params=params,
            headers=self._base_hdrs,
        )
        response = resp.json()
        if not response.get("success"):
            return response

        return float(response["data"][token_addr])

    async def get_swap_info(self, mint1, mint2, amount: int = 1):
        decimals = 9
        params = {
            "inputMint": mint1,
            "outputMint": mint2,
            "amount": amount * int("1" + "0" * decimals),
            "slippageBps": "50",
            "txVersion": "V0",
        }
        resp = await self._http_client.get(
            "https://transaction-v1.raydium.io/compute/swap-base-in",
            params=params,
            headers=self._base_hdrs,
        )
        return resp.json()

    async def __aenter__(self):
        self._setup_grpc_stub()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self._close_grpc_channel()

    def _close_grpc_channel(self):
        self._grpc_conn.channel.close()

    def _setup_grpc_stub(self):
        cfg = get_config()
        opts = cfg["microservices"]["raydium"]
        channel = Channel(host=opts["host"], port=int(opts["port"]))
        self._grpc_conn = PoolStateStub(channel=channel)


async def main():
    
    async with RaydiumAPI() as api:
        pool_id = "AB1eu2L1Jr3nfEft85AuD2zGksUbam1Kr8MR3uM2sjwt"
        data = await api.get_volume_of_pool(pool_id)
        print(data)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
