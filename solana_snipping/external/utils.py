import asyncio
from gql import gql
from gql.transport.websockets import WebsocketsTransport
from loguru import logger
from solana_snipping.cache import TokenMonitor


BASE_QUERY = """
subscription {
    Solana {
        General: Instructions(
            where: {
                Instruction: {
                    Program: {
                        Method: {in: ["syncNative", "initializeImmutableOwner", "initializeAccount", "initializeMultisig", "initializeAccount2", "initializeAccount3", "initializeMultisig2"]},
                    },
                },
                Transaction: {
                    Result: {Success: true}
                }
            }
            
            ) {
            Block {
                Time    
            }
            Instruction {
                Accounts {
                    Address
                    IsWritable
                    Token {
                        Owner
                        ProgramId
                        Mint
                }
                }
                Program {
                    AccountNames
                    Address
                }
            }
            count
        }
    }
}
"""


class BitQuery:
    
    def __init__(self) -> None:
        token = "ory_at_hV28Na5oA-2G6Zr3r2HnaVUle-uibmPdMyWsoIgTbUs.3eXtT211RahfbAUFvRVB0SeZ1NT9kdOMlMsLiCVJggY"
        self._transport = WebsocketsTransport(
            url=f"wss://streaming.bitquery.io/eap?token={token}",
            headers={"Sec-WebSocket-Protocol": "graphql-ws"},
            ping_interval=None,
        )
    
    async def data_from_blockchain(self, query: str = None):
        if not query:
            query = BASE_QUERY
        
        await self._transport.connect()
        try:
            async for result in self._transport.subscribe(gql(query)):
                if result == "ping" or result.data == "ping" or result.extensions == "ping":
                    print(result, result.data, result.extensions)
                    ...
                    
                if result.data:
                    yield result
        finally:
            await self._transport.close()
            
    async def get_mint_addresses(self, data: dict):
        mints = []
        for block in data["Solana"]["General"]:
            accounts = block["Instruction"]["Accounts"]
            mints.extend([a["Token"]["Mint"] for a in accounts if a["Token"]["Mint"]])
        return mints

async def run_subscription():
    bit = BitQuery()
    mon = TokenMonitor()
    
    async for data in bit.data_from_blockchain():
        mints = [mint for mint in await bit.get_mint_addresses(data.data) if mint != "So11111111111111111111111111111111111111112"]
        if not mints:
            print("not mints")
            continue
        
        # print(mints)
        for addr in mints:
            # await mon.add_token_to_cache(addr)
            try:
                task = await mon.trigger_token(addr)
            except Exception as e:
                print(f"{e.__class__.__name__}: {e}")
            ...
            # asyncio.create_task(task)
            
        ...
    
    
if __name__ == "__main__":
    logger.add("strategy2.log")
    asyncio.run(run_subscription())
    