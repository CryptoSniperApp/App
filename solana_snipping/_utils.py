from solana_snipping.common.constants import solana_async_client
from solders.pubkey import Pubkey

async def main():
    data = await solana_async_client.get_account_info(Pubkey.from_string("HvAqakZgurMR2br1eGWPU6EeFcxzmeW8n6Mn7ejEf3DV"))
    print(data)
    ...


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())