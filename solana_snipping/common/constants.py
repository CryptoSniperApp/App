from solana.rpc.async_api import AsyncClient

from solana_snipping.common.config import get_config


USDT_ADDR = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
SOL_ADDR = "So11111111111111111111111111111111111111112"
WSOL_ADDR = "So11111111111111111111111111111111111111112"

cfg = get_config()
_networks = cfg["chains"]["solana"]["networks"]
_url_mainnet_beta = _networks["mainnet-beta"]["rpc"]
solana_async_client = AsyncClient(_url_mainnet_beta)
