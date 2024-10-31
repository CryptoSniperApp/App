import asyncio
from datetime import datetime
import json
import re

from grpclib.client import Channel
from loguru import logger
import orjson
from solana.rpc.async_api import AsyncClient
import httpx
from solders.signature import Signature
import websockets.client
from pprint import pprint

from solana_snipping.backend.proto_generated import pools
from solana_snipping.backend.utils import get_proxies, get_wallets_private_keys
from solana_snipping.common.config import get_config
from solana_snipping.backend.proto_generated.pools import PumpFunStub


class PumpFunUtils:
    def __init__(self):
        cfg = get_config()
        self._grpc = PumpFunStub(Channel(
            host=cfg["microservices"]["pumpfun"]["host"],
            port=cfg["microservices"]["pumpfun"]["port"]
        ))
        
    @property
    def program_address(self):
        return "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
        
    async def decode_pump_fun_buy_event(self, data: str):
        return await self._grpc.decode_pump_fun_buy_event(program_data=data)
    
    async def get_mint_from_pumpfun(self, client: AsyncClient, signature: str):
        resp = await client.get_transaction(
            Signature.from_string(signature),
            max_supported_transaction_version=0,
            encoding="jsonParsed",
            commitment="confirmed",
        )
        
        transaction = resp.value.transaction.transaction
        try:
            instruction = [
                i for i in transaction.message.instructions
                if hasattr(i, "accounts") and len(i.accounts) == 14
            ][0]
            mint = instruction.accounts[3]
        except IndexError:
            instruction = [
                i for i in transaction.message.instructions
                if hasattr(i, "accounts") and len(i.accounts) == 12
            ][0]
            mint = instruction.accounts[2]
            
        return mint


class CopyTrading:
    def __init__(self):
        self._pumpfun_utils = PumpFunUtils()
        self._wallet = 'DfMxre4cKmvogbLrPigxmibVTTQDuzjdXojWzjCXXhzj'
        
    @property
    def _external_wallets(self):
        with open("copy_trading_wallets.txt") as f:
            return [line.strip() for line in f.readlines()]
        
    @property
    def _internal_wallets(self):
        with open("wallets.txt") as f:
            return [line.strip() for line in f.readlines()]
    
    @property
    def client_with_proxy_balancer(self):
        client = AsyncClient(
            endpoint="https://api.mainnet-beta.solana.com",
            commitment="confirmed",
        )
        timeout = client._provider.session.timeout
        timeout.read = 30.0
        proxies = get_proxies()
        if not proxies:
            proxy = get_config().get("PROXY_URL")
            if not proxy:
                raise ValueError("No proxies found")
            proxies = [proxy]
        
        async def request(*args, **kwargs):
            error = None
            for proxy in proxies:
                try:
                    client = httpx.AsyncClient(
                        verify=False,
                        proxy=proxy,
                        timeout=timeout
                    )
                    response = await client.request(*args, **kwargs)
                    return response
                except httpx.ProxyError as e:
                    error = e
                    continue
            raise error
        
        session = client._provider.session
        session.timeout = timeout
        session.request = request
        
        client._provider.session = session
        return client
    
    async def buy(self, mint: str, amount: float, private_key: str):
        grpc = self._pumpfun_utils._grpc
        return await grpc.swap_tokens(
            mint=mint,
            amount=amount,
            slippage_bps=1000,
            unit_limit=500_000,
            unit_price=2_500_000,
            private_key=private_key,
            tx_type="BUY"
        )
    
    async def sell(self, mint: str, private_key: str, amount: float = 0):
        grpc = self._pumpfun_utils._grpc
        return await grpc.swap_tokens(
            mint=mint,
            amount=amount,
            slippage_bps=300,
            unit_limit=500_000,
            unit_price=2_500_000,
            private_key=private_key,
            tx_type="SELL"
        )
    
    async def subscribe_to_transactions(self):
        instructions = [
            "Buy",
            "PumpBuy",
            "Sell",
            "PumpSell"
        ]
        mints = {}
        wallet = self._wallet
        async def process_logs(raw: str):
            if all(not raw.count(f"Program log: Instruction: {i}") for i in instructions):
                return
            time = datetime.now()
            decoded = orjson.loads(raw)
            signature = decoded["params"]["result"]["value"]["signature"]
            if raw.count(wallet) and raw.count(self._pumpfun_utils.program_address) and (raw.count("Buy")):
                logs = decoded['params']['result']['value']['logs']
                datas = [i for i in logs if "Program data:" in i]
                # pprint(logs)
                if not datas:
                    return
                
                if raw.count("MintTo"):
                    if len(datas) == 1:
                        return
                    data = datas[1].split("Program data: ")[1]
                else:
                    data = datas[0].split("Program data: ")[1]
                event = await self._pumpfun_utils.decode_pump_fun_buy_event(data)
                decoded_event = orjson.loads(event.raw_data)
                if not decoded_event:
                    return
                
                decoded_event["data"]["time"] = time
                decoded_event["data"]["signature"] = signature
                mint = decoded_event["data"]["mint"]
                
                if raw.count("Buy"):
                    mints[mint] = asyncio.Queue()
                    return decoded_event, mints[mint]
                
                elif raw.count("Sell"):
                    if mint in mints:
                        q = mints[mint]
                        await q.put(decoded_event)
            # else:
            #     raise ValueError(f"Unknown instruction. Signature: {signature}")
            
        attempts = 5
        error = None
        while True:
            try:
                async with websockets.client.connect(
                    "wss://api.mainnet-beta.solana.com",
                    ping_interval=None
                ) as websocket:
                    msg = orjson.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "logsSubscribe",
                            "params": [
                                {
                                    "mentions": [
                                        '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P',
                                    ]
                                },
                                {
                                    "commitment": "confirmed"
                                }
                            ]
                        }
                    )
                    await websocket.send(msg.decode('utf-8'))
                    get_response = False
                    await asyncio.sleep(0.5)
                    while True:
                        raw = await websocket.recv()
                        # print(f"Received at {datetime.now()}")
                        if not get_response:
                            get_response = True
                            continue
                        yield process_logs(raw)
                
            except websockets.exceptions.ConnectionClosedError:
                await asyncio.sleep(3)
            except Exception as e:
                logger.exception(e)
                attempts -= 1
                error = e
                if attempts == 0:
                    break
                
        raise error


async def check_creators():
    with open("creators.json") as f:
        creators = json.load(f)
    
    retries = {c: creators.count(c) for c in creators if creators.count(c) > 1}
    print(f"rerties creators: {retries}")


async def main():
    # return await check_creators()
    copy_trading = CopyTrading()
    client = copy_trading.client_with_proxy_balancer
    
    # resp = await client.get_transaction(
    #     Signature.from_string("hiecNwmFETGYkCPf1cvUtXAfyzpk3t7a7cCidSP96hb7Ar1aYooGdon3aA7XfQV4AKuP7V6W5ZPAjveQ9vgZtkH"),
    #     encoding="jsonParsed",
    #     max_supported_transaction_version=0
    # )
    # data = [i for i in resp.value.transaction.meta.log_messages if "Program data:" in i][0].split("Program data: ")[1]
    # print(data)
    # event = await copy_trading._pumpfun_utils.decode_pump_fun_buy_event(data)
    # print(event)
    private_key = get_wallets_private_keys()[0]
    mints = []
    # copy_trading._wallet = ''
    
    async def proccess(coro):
        result = await coro
        if not result:
            return
        data = result[0].get("data")
        q = result[1]
        q: asyncio.Queue
        if not data:
            return
        
        mint = data["mint"]
        # amount = data["solAmount"] / 10 ** 9
        amount = 0.0000005
        res = None
        try:
            if data["isBuy"] is True:
                
                if mint not in mints:
                    if len(mints) >= 30:
                        return
                    logger.info(f"{data["time"]} - {data["signature"]}")
                    mints.append(mint)
                    res = await copy_trading.buy(mint, amount, private_key)
            # else:
            #     if mint not in mints:
            #         return
            #     # res = await copy_trading.sell(mint, private_key)
            #     mints.remove(mint)
        except KeyError:
            pass
        except Exception as e:
            logger.exception(e)
            
        # print(f"Get data at {datetime.now()}. Data: {data}")
        ...
    
    loop = asyncio.get_running_loop()
    async for coro in copy_trading.subscribe_to_transactions():
        ...
        asyncio.eager_task_factory(
            loop=loop,
            coro=proccess(coro)
        )
    
    

if __name__ == "__main__":
    asyncio.run(main())
