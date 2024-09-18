from datetime import datetime
import decimal
import betterproto

from grpclib.client import Channel
import httpx
import asyncio
from loguru import logger
import orjson
from solders.rpc.responses import GetTransactionResp  # type: ignore
import websockets.client

from solana_snipping.backend.solana.raydium.generated.pools import PoolStateStub
from solana_snipping.backend.utils import append_hdrs
from solana_snipping.common.config import get_config


class RaydiumAPI:
    def __init__(self) -> None:
        self._grpc_conn = None
        self._http_client = httpx.AsyncClient()
        cfg = get_config()
        networks = cfg["chains"]["solana"]["networks"]
        self._wss_mainnet_beta = networks["mainnet-beta"]["websocket"]
        self._pool_account_address = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

    @property
    def _base_hdrs(self):
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "origin": "https://raydium.io",
            "priority": "u=1, i",
            "referer": "https://raydium.io/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
        }
        return append_hdrs(headers)

    async def get_volume_of_pool(self, parsed_pool_data: bytes):
        if not self._grpc_conn:
            self._setup_grpc_stub()

        data = await self._grpc_conn.get_pool_state(pool_data=parsed_pool_data)
        if data.error.error:
            obj = data.to_dict(
                casing=betterproto.Casing.SNAKE, include_default_values=True
            )
            return obj

        obj = data.to_dict(casing=betterproto.Casing.SNAKE, include_default_values=True)
        data = obj["data"]
        try:
            base_tokens_amounts = await self.price_usdc(data["base_mint"]) * float(
                data["base_token_amount"]
            )
        except TypeError:
            base_tokens_amounts = 0

        try:
            quote_tokens_amount = await self.price_usdc(data["quote_mint"]) * float(
                data["quote_token_amount"]
            )
        except TypeError:
            quote_tokens_amount = 0

        sum_amount = base_tokens_amounts + quote_tokens_amount
        return None if not sum_amount else sum_amount

    async def price_usdc(self, token_addr: str):
        params = {
            "mints": token_addr,
        }
        resp = await self._http_client.get(
            "https://api-v3.raydium.io/mint/price",
            params=params,
            headers=self._base_hdrs,
        )
        response = resp.json()
        if not response.get("success"):
            return response
        if not response["data"].get(token_addr):
            return None

        return float(response["data"][token_addr])

    async def get_swap_info(
        self,
        mint1,
        mint2,
        amount: int | float = 1,
        decimals: int = 9,
        base_out: bool = False,
        proxy: str = None,
    ):
        decimals = 9
        params = {
            "inputMint": mint1,
            "outputMint": mint2,
            "amount": int(amount * int("1" + "0" * decimals)),
            "slippageBps": "50",
            "txVersion": "V0",
        }

        endpoint = "swap-base-out" if base_out else "swap-base-in"
        async with httpx.AsyncClient(proxy=proxy) as client:
            resp = await client.get(
                f"https://transaction-v1.raydium.io/compute/{endpoint}",
                params=params,
                headers=self._base_hdrs,
            )

        return resp.json()

    async def get_swap_price(
        self,
        mint1: str,
        mint2: str,
        decimals: int,
        amount: int | float = None,
        base_out: bool = False,
        proxy: str = None,
    ) -> float | str:
        response = await self.get_swap_info(
            mint1,
            mint2,
            amount=amount or 1,
            decimals=decimals,
            base_out=base_out,
            proxy=proxy,
        )
        if not response.get("success"):
            return f"raw error: {response}"

        price = (
            response["data"]["inputAmount"]
            if base_out
            else response["data"]["outputAmount"]
        )
        result = decimal.Decimal(float(price) / int("1" + "0" * decimals))
        return round(result, decimals)

    async def subscribe_to_new_pools(self, queue: asyncio.Queue) -> None:
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
                                {"mentions": [self._pool_account_address]},
                                {"commitment": "finalized"},
                            ],
                        }
                    )
                    await websocket.send(msg)

                    needed_instructions = [
                        "mintTo",
                        "InitializeAccount",
                        "syncNative",
                    ]
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
                                    f"Program {self._pool_account_address} invoke [1]"
                                )
                            ),
                            None,
                        )
                        end_pool_instruction_i = next(
                            (
                                instructions.index(instr)
                                for instr in instructions
                                if instr.count(
                                    f"Program {self._pool_account_address} success"
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

    async def __aenter__(self):
        self._setup_grpc_stub()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self._close_grpc_channel()

    def _close_grpc_channel(self):
        self._grpc_conn.channel.close()

    def _setup_grpc_stub(self):
        cfg = get_config()
        opts = cfg["microservices"]["raydium"]
        channel = Channel(host=opts["host"], port=int(opts["port"]))
        self._grpc_conn = PoolStateStub(channel=channel)

    async def extract_mints_from_transaction(self, parsed_transaction: str) -> list[None | str]:
        try:
            resp = GetTransactionResp.from_json(parsed_transaction)
            instructions = resp.value.transaction.transaction.message.instructions
            accounts = [
                i.accounts
                for i in instructions
                if str(i.program_id) == self._pool_account_address
            ][0]

            token1 = accounts[8].__str__()
            token2 = accounts[9].__str__()
            pair = accounts[4].__str__()
            return [token1, token2, pair]
        except (KeyError, IndexError, AttributeError):
            return []


async def main():
    async with RaydiumAPI() as api:
        pool_id = "C47dSSMTUTjphq9QS1CAUsBfQGuPzNr6EUBSTz6Z1aQc"
        data = await api.get_volume_of_pool(pool_id)
        print(data)


if __name__ == "__main__":
    asyncio.run(main())
