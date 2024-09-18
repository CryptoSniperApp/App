from datetime import datetime

import orjson
from solana_snipping.backend.solana.audit import RugCheckAPI, WalletAudit
from solana_snipping.common.constants import solana_async_client
from solana_snipping.backend.solana.raydium import RaydiumAPI
from solana_snipping.backend.solana.solscan import Solscan
from solders.signature import Signature  # type: ignore
from solders.pubkey import Pubkey  # type: ignore
from spl.token._layouts import MINT_LAYOUT


class SolanaChain:
    def __init__(self) -> None:
        self._solclient = solana_async_client
        self._grpc_conn = None

    @property
    def raydium(self):
        return RaydiumAPI()

    @property
    def solscan(self):
        return Solscan()
    
    @property
    def solclient(self):
        return self._solclient

    @property
    def rug_checker(self):
        return RugCheckAPI()

    @property
    def wallet_auditor(self):
        return WalletAudit()

    async def get_transaction_parsed(self, signature: str) -> str:
        resp = await self._solclient.get_transaction(
            Signature.from_string(signature),
            max_supported_transaction_version=0,
            encoding="jsonParsed",
        )
        return resp.to_json()
    
    async def get_transaction_time(self, signature: str) -> datetime:
        json = await self.get_transaction_parsed(signature=signature)
        data = orjson.loads(json)
        return datetime.fromtimestamp(data["result"]["blockTime"])

    async def _get_mint_info(self, mint_addr: str):
        pubkey = Pubkey.from_string(mint_addr)
        resp = await self._solclient.get_account_info(pubkey, commitment="finalized")
        return MINT_LAYOUT.parse(resp.value.data)

    async def get_token_decimals(self, mint_addr: str) -> int:
        parsed = await self._get_mint_info(mint_addr=mint_addr)
        return int(parsed.decimals)

    async def get_signer_of_transaction(self, signature: str):
        resp = await self._solclient.get_transaction(
            Signature.from_string(signature),
            max_supported_transaction_version=0,
            encoding="jsonParsed",
        )
        return next(
            (
                a.pubkey.__str__()
                for a in resp.value.transaction.transaction.message.account_keys
                if a.signer
            ),
            None,
        )


async def main():
    # solana = SolanaChain()
    # pool_id = "AB1eu2L1Jr3nfEft85AuD2zGksUbam1Kr8MR3uM2sjwt"
    # sig = "43zvzPomoii5yTWZUVAabKkHtip3n7tghTF98H22787378ceB5huhbAakjWeBftb1Uvx7TmFxpEiSRKvxcg34k5"
    # print(await solana.raydium.get_volume_of_pool(pool_id))
    # print(await solana.get_transaction_time(sig))
    ...


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
