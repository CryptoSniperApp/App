import base64
from envyaml.envyaml import io
from grpclib.client import Channel
from solana.rpc.async_api import AsyncClient
from solders.rpc.responses import GetTransactionResp
from solders.signature import Signature
import ua_generator
import aiohttp
import asyncio
from loguru import logger
import websockets.client
from gql.transport.exceptions import TransportClosed
import websockets.exceptions
import orjson
import httpx
from pydantic import BaseModel
from datetime import datetime
from solana_snipping.backend.proto_generated import pools
from solana_snipping.common.config import get_config
from gql import gql
from gql.transport.websockets import WebsocketsTransport
from solana_snipping.backend.utils import asyncio_callbacks
from solana_snipping.backend.proto_generated.pools import TokensSolanaStub


class TokenMetadata(BaseModel):
    name: str
    symbol: str
    uri: str
    socials: list[dict[str, str]] | None = None
    websites: list[dict[str, str]] | None = None
    image: str | None = None
    description: str | None = None
    decimals: int


class MintToken(BaseModel):
    token: TokenMetadata
    decimals: int = 9
    amount: int | None = None


class MoonshotAPI:
    def __init__(self):
        self.base_url = "https://api.moonshot.cc/trades/v2/latest/solana"

        self._bitquery_wss = "wss://streaming.bitquery.io/eap"
        self._httpx_client = httpx.AsyncClient()

        self._mints_to_watch = []
        self._queues = []

        self._mints_price_watch = []
        self._mints_price_watch_queues = []
        
        self._grpc_conn: TokensSolanaStub | None = None
    
    @property
    def bitquery_token(self):
        cfg = get_config()
        return cfg["bitquery"]["token"]
        
    @property
    def bitquery_secret(self):
        cfg = get_config()
        return cfg["bitquery"]["secret"]
    
    @property
    def wss_mainnet_beta(self):
        cfg = get_config()
        networks = cfg["chains"]["solana"]["networks"]
        return networks["mainnet-beta"]["websocket"]

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
    
    async def _scan_new_mints_mainnet_beta(self, q: asyncio.Queue):
        slots = []
        client = AsyncClient("https://api.mainnet-beta.solana.com/", "confirmed")
        async def send_in_queue(raw: str):
            nonlocal slots
            time = datetime.now()
            block_data = orjson.loads(raw)

            try:
                slot = block_data['params']['result']["context"]["slot"]
                if slot:
                    print(slot)
                    slots.append(slot)
                if not block_data['params']['result']['value']['block']:
                    return
                
                transactions = [
                    tr 
                    for tr in block_data['params']['result']['value']['block']['transactions']
                    # if any(log.count('TokenMint') for log in tr['meta']['logMessages'])
                ]
                
            except KeyError:
                return
            
            if not transactions:
                return
            
            for trans in transactions:
                instructions = trans['meta']['logMessages']
                
                start_pool_instruction_i = next(
                    (
                        instructions.index(instr)
                        for instr in instructions
                        if instr.count(
                            f"Program {program_address} invoke [1]"
                        )
                    ),
                    None,
                )
                end_pool_instruction_i = next(
                    (
                        instructions.index(instr)
                        for instr in instructions
                        if instr.count(
                            f"Program {program_address} success"
                        )
                    ),
                    None,
                )
                if start_pool_instruction_i is None or end_pool_instruction_i is None:
                    return

                # signature = trans['transaction']['signatures'][0]
                signature = trans['transaction']
                pool_instructions = instructions[
                    start_pool_instruction_i : end_pool_instruction_i + 1
                ]
                if trans["meta"]["err"] or not all(
                    any(
                        instruction.lower().count(
                            f"Program log: Instruction: {needed_instruction}".lower()
                        )
                        for instruction in pool_instructions
                    )
                    for needed_instruction in needed_instructions
                ):
                    return
                
                ...
                # bytes_data = await client.get_transaction(
                #     Signature.from_string(signature),
                #     encoding="base64",
                #     max_supported_transaction_version=0
                # )
                # ...
                # instruction = [
                #     i for i in 
                #     bytes_data.value.transaction.transaction.message.instructions
                #     if len(i.accounts) == 11
                # ][0]
                # data = instruction.data
                
                # block = await client.get_block(
                #     slot=log_data['params']['result']['context']['slot'],
                #     max_supported_transaction_version=0, encoding="base64"
                # )
                
                # transactions = [
                #     b 
                #     for b in block.value.transactions
                #     if any(log.count('TokenMint') for log in b.meta.log_messages)
                # ]
                # inst = [i for i in transactions[0].transaction.message.instructions if len(i.accounts) == 11]
                # data = inst[0].data
                
                instruction = trans['transaction']['message']['instructions'][0]
                data = instruction['data']

                parsed = await self.parse_mint_instruction_data(data)
                now = datetime.now()
                data = (signature, time.isoformat(), now.isoformat(), parsed)
                print(data)
                await q.put(data)
        
        while True:
            try:
                program_address = "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG"
                async with websockets.client.connect(
                    # "wss://api.mainnet-beta.solana.com",
                    # "wss://solana-mainnet.core.chainstack.com/1f0c0d85ee1233545fc318f123c5eb8e",
                    "wss://solana-mainnet.g.alchemy.com/v2/q5Ps-5QwBKRtxjxNMVHwoNGAAVNj78Fq",
                    ping_interval=None
                ) as websocket:
                    msg = orjson.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "logsSubscribe",
                            "params": [
                                {"mentions": [program_address]},
                                {"commitment": "processed"},
                            ],
                        }
                    )
                    msg = orjson.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": "1",
                            "method": "blockSubscribe",
                            "params": [
                                {
                                    "mentionsAccountOrProgram": program_address
                                },
                                {
                                    # "commitment": "confirmed",
                                    "encoding": "jsonParsed",
                                    "encoding": "base64",
                                    # "showRewards": True,
                                    "transactionDetails": "full",    
                                }
                            ]
                        }
                    )

                    res = await websocket.send(msg.decode('utf-8'))

                    needed_instructions = [
                        "TokenMint"
                    ]
                    loop = asyncio.get_running_loop()
                    print("начали") 
                    import base64
                    from pprint import pprint
                    while True:
                        raw = await websocket.recv()
                        # d = orjson.loads(raw)
                        # pprint(d) 
                        ...
                        asyncio.eager_task_factory(
                            loop=loop,
                            coro=send_in_queue(raw)
                        )
                        # await asyncio.sleep(1000)
                        
            except websockets.exceptions.   ConnectionClosedError:
                await asyncio.sleep(3)
            except Exception as e:
                logger.exception(e)
                raise e
    
    def _setup_grpc_stub(self):
        cfg = get_config()
        opts = cfg["microservices"]["grpc"]
        channel = Channel(host=opts["host"], port=int(opts["port"]))
        self._grpc_conn = TokensSolanaStub(channel=channel)
            
    async def parse_mint_instruction_data(self, encoded_data: bytes) -> MintToken | pools.ResponseRpcOperation:
        if self._grpc_conn is None:
            self._setup_grpc_stub()
        res = await self._grpc_conn.decode_moonshot_mint_instruction(instruction_data=encoded_data)
        if not res.success:
            logger.error(f"получили ошибку когда пытались декодировать token mint moonshot instruction data. error data: {res.error}")
            return res
        
        token_data = orjson.loads(res.raw_data)
        
        meta = TokenMetadata(
            name=token_data["name"],
            symbol=token_data["symbol"],
            uri=token_data["uri"],
            decimals=token_data["decimals"]
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(token_data["uri"]) as resp:
                    json = await resp.json(content_type=resp.content_type)
                    meta.image = json["image"]
                    meta.websites = json["websites"]
                    meta.socials = json["socials"]
        except Exception as e:
            logger.exception(e)
        
        event = MintToken(
            token=meta,
            decimals=meta.decimals,
            amount=int(token_data["amount"])
        )
        return event

    async def subscribe_to_dexscreener_moonshot_mints_create(
        self, queue: asyncio.Queue
    ) -> None:
        dexscreener_account_address = "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG"

        headers = {
            "Sec-WebSocket-Protocol": "graphql-ws",
            "Content-Type": "application/json",
        }
        url = f"{self._bitquery_wss}?token={self.bitquery_token}"
        transport = WebsocketsTransport(
            url=url, headers=headers, ping_interval=20, pong_timeout=60
        )
        self._setup_grpc_stub()
        if not transport.websocket:
            await transport.connect()

        try:
            while True:
                try:
                    # gql_query = gql(
                    #     """
                    #     subscription {
                    #         Solana(trigger_on: all) {
                    #             Instructions(
                    #             where: {Instruction: {Program: {Method: {is: "tokenMint"}, Address: {is: "<MOONSHOT_ADDRESS>"}}, Accounts: {includes: {Token: {Mint: {not: ""}}}}}, Transaction: {Result: {Success: true}}}
                    #             ) {
                    #             Instruction {
                    #                 Accounts {
                    #                 Token {
                    #                     Mint
                    #                     Owner
                    #                     ProgramId
                    #                 }
                    #                 IsWritable
                    #                 Address
                    #                 }
                    #                 Program {
                    #                 Method
                    #                 Name
                    #                 }
                    #             }
                    #             Transaction {
                    #                 Signature
                    #                 Signer
                    #             }
                    #             }
                    #         }
                    #     }

                    #     """.replace("<MOONSHOT_ADDRESS>", dexscreener_account_address)
                    # )
                    gql_query = gql(
                        """
                        subscription MyQuery {
                            Solana {
                                Instructions(
                                    where: {Instruction: {Program: {Address: {is: "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG"}, Method: {is: "tokenMint"}}}, Transaction: {Result: {Success: true}}}
                                ) {
                                Instruction {
                                    Data
                                    Accounts {
                                        Address
                                        Token {
                                            Mint
                                        }
                                    }
                                }
                                Transaction {
                                    Signature
                                    Result {
                                        Success
                                        ErrorMessage
                                    }
                                }
                                }
                            }
                            }
                        """
                    )

                    async for result in transport.subscribe(gql_query):
                        catch_time = datetime.now()
                        data = result.data["Solana"]["Instructions"][0]
                        
                        hex_decoded = bytes.fromhex(data['Instruction']['Data'])
                        meta = await self.parse_mint_instruction_data(hex_decoded)

                        mint = data["Instruction"]["Accounts"][4]["Address"]
                        signature = data["Transaction"]["Signature"]

                        queue_data = (signature, mint, catch_time, meta)
                        await queue.put(queue_data)

                        self._mints_price_watch.append(mint)

                except (TransportClosed, websockets.exceptions.ConnectionClosedError):
                    await asyncio.sleep(3)
                    if not transport.websocket:
                        await transport.connect()
                        
                except Exception as e:
                    logger.exception(e)
                    raise e
        finally:
            await transport.close()

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
        headers = {
            "Sec-WebSocket-Protocol": "graphql-ws",
            "Content-Type": "application/json",
        }
        url = f"{self._bitquery_wss}?token={self.bitquery_token}"
        transport = WebsocketsTransport(url=url, headers=headers)

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
                                [
                                    await queue.put((item, mint))
                                    for queue in self._queues
                                ]

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
        f = asyncio.eager_task_factory(
            loop, self._send_bitquery_moonshot_subscription()
        )
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
            
    async def get_token_info(self, mint: str) -> dict:
        query = ("""
        query {
            Solana {
            DEXTradeByTokens(
            where: {Trade: {Currency: {MintAddress: {is: "<MINT>", not: "11111111111111111111111111111111"}}, Dex: {ProgramAddress: {is: "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG"}}, Price: {ne: 0}, PriceInUSD: {ne: 0}}, Transaction: {Result: {Success: true}}}
            orderBy: {descending: Block_Time}
            limit: {count: 10}
            ) {
            Trade {
                Currency {
                Decimals
                }
                PriceInUSD
                Price
            }
            }
        }
        }

        """.replace("<MINT>", mint))
        variables = {
            "X-API-KEY": self.bitquery_secret,
            'Authorization': f'Bearer {self.bitquery_token}'
        }
        resp = await httpx.AsyncClient().post(
            "https://streaming.bitquery.io/eap",
            headers=variables,
            json={"query": query},
        ) 
        data = resp.json()
        section = data['data']['Solana']['DEXTradeByTokens'][0]
        return {
            "usd": section['Trade']['PriceInUSD'],
            "price": section['Trade']['Price'],
            "decimals": section['Trade']['Currency']['Decimals']
        }

    async def _scan_prices_of_mints(self) -> None:
        query = """
        subscription {
            Solana {
                DEXTradeByTokens(
                where: {Trade: {Price: {ne: 0}, PriceInUSD: {ne: 0}, Currency: {MintAddress: {not: "So11111111111111111111111111111111111111112"}}}, Transaction: {Result: {Success: true}}}
                ) {
                Block {
                    Time
                }
                Trade {
                    Currency {
                    MintAddress
                    Name
                    Symbol
                    Decimals
                    }
                    Dex {
                    ProtocolName
                    ProtocolFamily
                    ProgramAddress
                    }
                    Side {
                    Currency {
                        MintAddress
                        Symbol
                        Name
                    }
                    }
                    Price
                    PriceInUSD
                }
                Transaction {
                    Signature
                }
                }
            }
            }
        """

        headers = {
            "Sec-WebSocket-Protocol": "graphql-ws",
            "Content-Type": "application/json",
        }
        url = f"{self._bitquery_wss}?token={self.bitquery_token}"
        transport = WebsocketsTransport(
            url=url, headers=headers, ping_interval=20, pong_timeout=60
        )
        await transport.connect()
        
        async def yield_data(data: dict):
            
            for trade in data["Solana"]["DEXTradeByTokens"]:
                mint = trade["Trade"]["Currency"]["MintAddress"]
                if mint in self._mints_price_watch:
                    [
                        await queue.put((trade, mint))
                        for queue in self._mints_price_watch_queues
                    ]

        try:
            loop = asyncio.get_running_loop()
            while True:
                try:
                    async for result in transport.subscribe(gql(query)):
                        if result.errors:
                            print(f"result errors: {result.errors}")
                            continue
                        
                        data = result.data
                        f = asyncio.eager_task_factory(loop, yield_data(data))
                        f.add_done_callback(asyncio_callbacks.raise_exception_if_set)

                except (
                    websockets.exceptions.ConnectionClosedError,
                    TransportClosed,
                ) as e:
                    if "keepalive ping timeout" in str(e):
                        logger.warning(
                            "Соединение закрыто из-за таймаута пинга. Переподключение..."
                        )
                        await asyncio.sleep(5)
                    elif isinstance(e, websockets.exceptions.ConnectionClosedError):
                        logger.error(f"Ошибка соединения WebSocket: {e}")
                        # await asyncio.sleep(3)

                    if not transport.websocket:
                        await transport.connect()

                except Exception as e:
                    logger.exception(e)
                    await asyncio.sleep(3)
        finally:
            await transport.close()


async def main():
    moonshot = MoonshotAPI()
    queue = asyncio.Queue()
    client = AsyncClient('https://solana-mainnet.core.chainstack.com/1f0c0d85ee1233545fc318f123c5eb8e', "confirmed")
    # r = await client.get_transaction(
    #     Signature.from_string("2ZhnKAsButWtx6RfHRxqfiycrESQVN1F9LZLky4rgknsRMLyuqJHeGXxNjeaDWKR6CQnBUxDyoaRZohrzSFG9kL3"),
    #     encoding="base64",
    #     max_supported_transaction_version=0
    # )
    # print(r.value.transaction.transaction.message.instructions[1].data)
    # block = await client.get_block(
    #     slot=297093802,
    #     encoding="base64",
    #     max_supported_transaction_version=0
    # )
    # transactions = [
    #     b 
    #     for b in block.value.transactions
    #     if any(log.count('TokenMint') for log in b.meta.log_messages)
    # ]
    # inst = [i for i in transactions[0].transaction.message.instructions if len(i.accounts) == 11]
    # data = inst[0].data
    # s = "032CA4B87B0DF5B3060000006A6F79636174060000006A6F796361744400000068747470733A2F2F63646E2E64657873637265656E65722E636F6D2F636D732F746F6B656E732F6D657461646174612F4236755257336231536771746739736D465A416C0900000064A7B3B6E00D0101"
    # data = bytes.fromhex(s)
    # grpc = TokensSolanaStub(Channel())
    # parsed = await grpc.decode_moonshot_mint_instruction(instruction_data=data)
    # print(parsed)
    # return
    await moonshot._scan_new_mints_mainnet_beta(queue)
    # await moonshot.subscribe_to_dexscreener_moonshot_mints_create(queue)

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
