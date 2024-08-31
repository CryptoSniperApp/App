import json
import httpx
import asyncio

import websockets

class JupiterMainAPI:
    
    def __init__(self) -> None:
        self._client = httpx.AsyncClient()
    
    async def _get_prices_history(self):
        ...
        

async def subscribe_to_account(account_pubkey):
    uri = "wss://api.mainnet-beta.solana.com"
    async with websockets.connect(uri) as websocket:
        subscription_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "accountSubscribe",
            "params": [
                account_pubkey,
                {
                    "encoding": "jsonParsed"
                }
            ]
        }
        await websocket.send(json.dumps(subscription_request))
        while True:
            response = await websocket.recv()
            print(response)

account_pubkey = "YourPoolAccountPublicKey"
asyncio.run(subscribe_to_account(account_pubkey))


async def main():
    ...


if __name__ == "__main__":
    asyncio.run(main())