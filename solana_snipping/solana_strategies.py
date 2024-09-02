import asyncio
from solana_snipping.backend.solana import SolanaChain


class FiltersRaydiumPools:
    def __init__(self) -> None:
        self._client = SolanaChain()
        self._raydium_client = self._client.raydium

    async def __call__(
        self, mint1: str, mint2: str, pair_mint: str, signature: str
    ) -> bool:
        if mint1.endswith("pump") or mint2.endswith("pump"):
            return False

        liquidity, wallet_addr = await asyncio.gather(
            self._client.solscan.get_added_liquidity_value(signature),
            self._client.get_signer_of_transaction(signature=signature)
        )
        
        if liquidity <= 10_000:
            return False

        thxs = await self._client.wallet_auditor.get_finalized_signatures(
            wallet_addr=wallet_addr
        )
        
        if len(thxs) < 50:
            return False

        return True
