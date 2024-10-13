from solders.rpc.responses import GetTransactionResp
import ua_generator
import asyncio
from loguru import logger
import websockets.client
from gql.transport.exceptions import TransportClosed
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
        self._bitquery_secret = cfg["bitquery"]["secret"]
        headers = {
            "Sec-WebSocket-Protocol": "graphql-ws",
            "Content-Type": "application/json",
        }
        url = f"{self._bitquery_wss}?token={self._bitquery_token}"
        self._bitquery = WebsocketsTransport(url=url, headers=headers)

        self._httpx_client = httpx.AsyncClient()

        self._mints_to_watch = []
        self._queues = []

        self._mints_price_watch = []
        self._mints_price_watch_queues = []

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
        self, queue: asyncio.Queue
    ) -> None:
        dexscreener_account_address = "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG"

        headers = {
            "Sec-WebSocket-Protocol": "graphql-ws",
            "Content-Type": "application/json",
        }
        url = f"{self._bitquery_wss}?token={self._bitquery_token}"
        transport = WebsocketsTransport(
            url=url, headers=headers, ping_interval=20, pong_timeout=60
        )
        if not transport.websocket:
            await transport.connect()

        try:
            while True:
                try:
                    gql_query = gql(
                        """
                        subscription {
                            Solana {
                                Instructions(
                                where: {Instruction: {Program: {Method: {is: "tokenMint"}, Address: {is: "<MOONSHOT_ADDRESS>"}}, Accounts: {includes: {Token: {Mint: {not: ""}}}}}, Transaction: {Result: {Success: true}}}
                                ) {
                                Instruction {
                                    Accounts {
                                    Token {
                                        Mint
                                        Owner
                                        ProgramId
                                    }
                                    IsWritable
                                    Address
                                    }
                                    Program {
                                    Method
                                    Name
                                    }
                                }
                                Transaction {
                                    Signature
                                    Signer
                                }
                                }
                            }
                        }

                        """.replace("<MOONSHOT_ADDRESS>", dexscreener_account_address)
                    )

                    async for result in transport.subscribe(gql_query):
                        data = result.data["Solana"]["Instructions"][0]
                        mint = data["Instruction"]["Accounts"][5]["Token"]["Mint"]
                        signature = data["Transaction"]["Signature"]

                        queue_data = (signature, mint, datetime.now())
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
            "X-API-KEY": self._bitquery_secret,
            'Authorization': f'Bearer {self._bitquery_token}'
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

    async def   _scan_prices_of_mints(self) -> None:
        query = """
        subscription {
            Solana {
                DEXTradeByTokens(
                where: {Trade: {Dex: {ProgramAddress: {is: "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG"}}, Price: {ne: 0}, PriceInUSD: {ne: 0}, Currency: {MintAddress: {not: "11111111111111111111111111111111"}}}, Transaction: {Result: {Success: true}}}
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
        url = f"{self._bitquery_wss}?token={self._bitquery_token}"
        transport = WebsocketsTransport(
            url=url, headers=headers, ping_interval=20, pong_timeout=60
        )
        await transport.connect()

        try:
            while True:
                try:
                    async for result in transport.subscribe(gql(query)):
                        if result.errors:
                            print(f"result errors: {result.errors}")
                            continue

                        data = result.data

                        for trade in data["Solana"]["DEXTradeByTokens"]:
                            mint = trade["Trade"]["Currency"]["MintAddress"]
                            if mint in self._mints_price_watch:
                                [
                                    await queue.put((trade, mint))
                                    for queue in self._mints_price_watch_queues
                                ]

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
                        await asyncio.sleep(3)

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

    return print(
        await moonshot.get_price_of_mint("FFBDunxagMP9Z79rVFSXaYf58BDkZBSVpiuzEX1v3cKE")
    )

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
