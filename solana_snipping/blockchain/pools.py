import asyncio
import json
from solana.rpc.websocket_api import connect
from solders.pubkey import Pubkey
from solders.rpc.config import RpcTransactionLogsFilter


async def main():
    ...
    async with connect("wss://api.mainnet-beta.solana.com") as websocket:
        pool_account_address = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
        pubkey = Pubkey.from_string(pool_account_address)
        # await websocket.program_subscribe(pubkey, commitment="finalized", encoding="jsonParsed")
        await websocket.logs_subscribe(commitment="finalized")
        # await websocket.account_subscribe(pubkey)

        while True:
            data = await websocket.recv()
            ...
        ...


if __name__ == "__main__":
    asyncio.run(main())
