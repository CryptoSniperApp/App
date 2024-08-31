from solana_snipping.common.config import get_config
from solana_snipping.backend.solana.raydium import RaydiumAPI
from solana_snipping.backend.solana.solscan import Solscan
from solana.rpc.async_api import AsyncClient


class SolanaChain:
    def __init__(self) -> None:
        cfg = get_config()
        networks = cfg["chains"]["solana"]["networks"]
        self._url_mainnet_beta = networks["mainnet-beta"]["rpc"]
        self._solclient = AsyncClient(self._url_mainnet_beta)
        self._grpc_conn = None

    @property
    def raydium(self):
        return RaydiumAPI()

    @property
    def solscan(self):
        return Solscan()


async def main():
    solana = SolanaChain()
    pool_id = "AB1eu2L1Jr3nfEft85AuD2zGksUbam1Kr8MR3uM2sjwt"
    print(await solana.raydium.get_volume_of_pool(pool_id))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
