from solders.rpc.responses import GetTransactionResp
import ua_generator
import asyncio
from loguru import logger
import websockets.client
import websockets.exceptions
import orjson
import httpx
from datetime import datetime
from solana_snipping.common.config import get_config
from gql import gql
from gql.transport.websockets import WebsocketsTransport
from solana_snipping.backend.utils import asyncio_callbacks

class MoonshotAPI:
    def __init__(self):
        self.base_url = "https://api.moonshot.cc/trades/v2/latest/solana"
        cfg = get_config()
        networks = cfg["chains"]["solana"]["networks"]
        self._wss_mainnet_beta = networks["mainnet-beta"]["websocket"]

        self._bitquery_wss = "wss://streaming.bitquery.io/eap"
        self._bitquery_token = cfg["bitquery"]["token"]
        headers = {
            "Sec-WebSocket-Protocol": "graphql-ws",
            "Content-Type": "application/json",
        }
        url = f"{self._bitquery_wss}?token={self._bitquery_token}"
        self._bitquery = WebsocketsTransport(url=url, headers=headers)

        self._httpx_client = httpx.AsyncClient()

        self._mints_to_watch = []
        self._queues = []

    @property
    def _hdrs(self):
        hdrs = {
            "accept": "*/*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "origin": "https://dexscreener.com",
            "priority": "u=1, i",
            "referer": "https://dexscreener.com/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
        }

        for k, v in ua_generator.generate().headers.get().items():
            hdrs[k] = v

        return hdrs

    async def subscribe_to_dexscreener_moonshot_mints_create(
        self, 
        queue: asyncio.Queue
    ) -> None:
        dexscreener_account_address = "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG"

        while True:
            try:
                async with websockets.client.connect(
                    self._wss_mainnet_beta, ping_interval=None
                ) as websocket:
                    msg = orjson.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "logsSubscribe",
                            "params": [
                                {"mentions": [dexscreener_account_address]},
                                {"commitment": "finalized"},
                            ],
                        }
                    )
                    await websocket.send(msg)

                    needed_instructions = ["TokenMint", "MintTo"]
                    while True:
                        raw = await websocket.recv()
                        log_data = orjson.loads(raw)

                        try:
                            instructions = log_data["params"]["result"]["value"]["logs"]
                        except KeyError:
                            continue

                        start_pool_instruction_i = next(
                            (
                                instructions.index(instr)
                                for instr in instructions
                                if instr.count(
                                    f"Program {dexscreener_account_address} invoke [1]"
                                )
                            ),
                            None,
                        )
                        end_pool_instruction_i = next(
                            (
                                instructions.index(instr)
                                for instr in reversed(instructions)
                                if instr.count(
                                    f"Program {dexscreener_account_address} success"
                                )
                            ),
                            None,
                        )
                        if not start_pool_instruction_i or not end_pool_instruction_i:
                            continue

                        signature = log_data["params"]["result"]["value"]["signature"]
                        pool_instructions = instructions[
                            start_pool_instruction_i : end_pool_instruction_i + 1
                        ]
                        if log_data["params"]["result"]["value"]["err"] or not all(
                            any(
                                instruction.lower().count(
                                    f"Program log: Instruction: {needed_instruction}".lower()
                                )
                                for instruction in pool_instructions
                            )
                            for needed_instruction in needed_instructions
                        ):
                            continue

                        data = (signature, datetime.now())
                        await queue.put(data)
            except websockets.exceptions.ConnectionClosedError:
                await asyncio.sleep(3)
            except Exception as e:
                logger.exception(e)
                raise e

    async def extract_mint_from_transaction(
        self, parsed_transaction: str
    ) -> str | None:
        try:
            resp = GetTransactionResp.from_json(parsed_transaction)
            instructions = resp.value.transaction.transaction.message.instructions
            accounts = [
                i.accounts
                for i in instructions
                if str(i.program_id) == "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG"
            ][0]

            return accounts[3].__str__()
        except (KeyError, IndexError, AttributeError):
            return None

    async def _send_bitquery_moonshot_subscription(self):
        transport = self._bitquery

        if not transport.websocket:
            await transport.connect()

        query = gql(
            """
            subscription {
                Solana {
                    DEXTradeByTokens(
                        where: {Instruction: {Program: {Address: {is: "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG"}}}, Trade: {Currency: {MintAddress: {not: "11111111111111111111111111111111"}}}}
                    ) {
                    Trade {
                        AmountInUSD
                        Amount
                        PriceInUSD
                        Price
                        Currency {
                            MintAddress
                            Name
                            Decimals
                            Symbol
                        }
                        Dex {
                            ProtocolFamily
                            ProgramAddress
                        }
                        Market {
                            MarketAddress
                        }
                        Order {
                        Mint
                        Owner
                        Account
                        }
                    }
                    Instruction {
                        Program {
                            Method
                        }
                    }
                    Transaction {
                        Signature
                    }
                    Block {
                        Time
                    }
                    }
                }
                }

            """
        )

        error_count = 0
        try:
            while True:
                try:
                    async for result in transport.subscribe(query):
                        if result.errors:
                            print(f"result errors: {result.errors}")
                            continue

                        data = result.data

                        for item in data["Solana"]["DEXTradeByTokens"]:
                            mint = item["Trade"]["Currency"]["MintAddress"]
                            if mint in self._mints_to_watch:
                                [await queue.put(item) for queue in self._queues]

                    error_count = 0
                except Exception as e:
                    logger.exception(e)
                    await asyncio.sleep(3)
                    error_count += 1
                    if error_count > 5:
                        return

        finally:
            await transport.close()

    def subscribe_mint_price_change(self, mint: str, q: asyncio.Queue):
        loop = asyncio.get_running_loop()
        f = asyncio.eager_task_factory(loop, self._send_bitquery_moonshot_subscription())
        f.add_done_callback(asyncio_callbacks.raise_exception_if_set)
        self._mints_to_watch.append(mint)
        if q not in self._queues:
            self._queues.append(q)

    def unsubscribe_mint_price_change(self, mint: str, q: asyncio.Queue):
        try:
            self._mints_to_watch.remove(mint)
        except ValueError:
            pass
        if q in self._queues:
            try:
                self._queues.remove(q)
            except ValueError:
                pass

    async def get_price_of_mint(self, mint: str) -> dict:
        query = """
            {
                Solana {
                    DEXTradeByTokens(
                    where: {Instruction: {Program: {Address: {is: "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG"}}}, Trade: {Currency: {MintAddress: {is: "<MINT_ADDRESS>"}}}}
                    orderBy: {descending: Block_Time}
                    limit: {count: 1}
                    ) {
                    Trade {
                        AmountInUSD
                        Amount
                        PriceInUSD
                        Price
                        Currency {
                        MintAddress
                        Name
                        }
                        Dex {
                        ProtocolFamily
                        ProtocolName
                        ProgramAddress
                        }
                        PriceAsymmetry
                    }
                    Instruction {
                        Program {
                        Method
                        }
                    }
                    Transaction {
                        Signature
                    }
                    Block {
                        Time
                    }
                    }
                }
            }

            """.replace("<MINT_ADDRESS>", mint)
        url = "https://streaming.bitquery.io/eap"

        hdrs = {
            "accept": "application/json",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "authorization": "Bearer ory_at_7hZWTD9wNVQzwnrbsEy_sPmeDu39grU8P5w_F_exBB4.nbC28py7MP7-rhDc6YyJ-urI71cr0f48zCxnJuOjN8c",
            "content-type": "application/json",
            "origin": "https://ide.bitquery.io",
            "priority": "u=1, i",
            "referer": "https://ide.bitquery.io/",
            "x-api-key": "BQYuQk0CljGIADHi27ky3HNUypYZ0hmG",
        }
        resp = await self._httpx_client.post(
            url, json={"query": query, "variables": {}}, headers=hdrs
        )
        response = resp.json()
        if response.get("errors"):
            raise Exception(response["errors"])
        prices = response["data"]["Solana"]["DEXTradeByTokens"][0]["Trade"]
        
        return {
            "sol": prices["Price"],
            "usd": prices["PriceInUSD"],
        }


async def main():
    moonshot = MoonshotAPI()
    queue = asyncio.Queue()

    moonshot.subscribe_mint_price_change(
        "3HpCwowzKwHGiYrHTFy3KYiBDnSnpNPsy4Cb3u23Ym8d", queue
    )

    while True:
        data = await queue.get()
        print(data)

    # await moonshot.get_price_of_mint("BZAY5idPFHyBZgghgzJomDKjjw3vzwRrXhKWptxp8Y2N")
    # parsed_transaction = await SolanaChain().get_transaction_parsed(
    #     "3QvY3ZjXFP9LJQ6XKbHv12jHKHjpt6JVjN5RxbKtU1XrZzX6BUoG2EWdeTsr3pgvHEpJgC1NosSevca2ehFpFm7T"
    # )
    # return print(await moonshot.extract_mint_from_transaction(parsed_transaction))

    # r = await moonshot.subscribe_to_dexscreener_moonshot(queue)
    # while True:
    #     data = await queue.get()
    #     ...
    #     print(data)
    ...


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
