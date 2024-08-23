from solana_snipping.external.audit import RugCheckAPI
from solana_snipping.constants import USDT_ADDR
from solana_snipping.blockchain.explorers import SolscanAPI
from solana_snipping.external.dex import RadiumAPI, JupiterAPI
from decimal import Decimal, getcontext

from solana_snipping.logs import log_msg


class TokenMonitor:
    def __init__(self) -> None:
        self.cached_tokens = set()
        pass

    async def trigger_token(self, addr: str):
        if list(self.cached_tokens).count(addr):
            return
        else:
            self.cached_tokens.add(addr)
            
            radium = RadiumAPI()
            jupiter = JupiterAPI()
            solscan = SolscanAPI()
            
            transfers_count = await solscan.get_count_transfers(addr)
            if 1 < transfers_count or transfers_count > 15:
                print(f"not buy token:, his count {transfers_count} transfers")
                return

            swap_info = await jupiter.get_swap_info(
                token1=addr, token2=USDT_ADDR, amount=1
            )
            if swap_info.get("error"):
                print(swap_info["error"])
                return
            
            price = float(swap_info["outAmount"]) / 1000000
            if not swap_info:
                swap_info = await radium.get_swap_info(
                    token1=addr, token2=USDT_ADDR, amount=1
                )
                if not swap_info:
                    raise RuntimeError(f"No swap info for token addr: {addr}")
                price = 0
                with open("radium_swap.txt", "a") as f:
                    f.write(f"{swap_info}\n\n")
                return
            
            audit = RugCheckAPI()
            warnings_num = await audit.count_of_warnings(addr)
            
            if isinstance(warnings_num, int) and warnings_num > 4:
                raise ValueError(f"Token {addr} count {warnings_num} warnings")
            
            getcontext().prec = 100
            price = Decimal(str(price))
            
            msg = f"we are buy 1 token ({addr}) by {price} $. his contains follow warnings num - {warnings_num}, and {transfers_count} transfers"
            await log_msg(msg)
