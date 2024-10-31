import decimal
from pprint import pprint
import httpx
import json

from solana_snipping.backend.utils import append_hdrs, get_proxies
from solana_snipping.common.constants import WSOL_ADDR


class Solscan:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(15))

    @property
    def _base_hdrs(self):
        hdrs = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "origin": "https://solscan.io",
            "priority": "u=1, i",
            "referer": "https://solscan.io/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
        }

        return append_hdrs(hdrs)

    async def _raw_pool_info(self, pool_id: str):
        headers = self._base_hdrs
        url = "https://api-v2.solscan.io/v2/defi/pool_info"
        params = {
            "address": pool_id,
        }
        resp = await self._client.get(url, headers=headers, params=params)
        return resp.json()

    async def get_tvl_of_pool(self, pool_id: str):
        response = await self._raw_pool_info(pool_id=pool_id)

        if not response.get("success"):
            return response

        if not response.get("data"):
            return None

        return response["data"]["tvl"] * 2

    async def _raw_trans_detail_info(self, trans_id: str, proxy: str = None):
        headers = self._base_hdrs
        params = {"tx": trans_id}
        url = "https://api-v2.solscan.io/v2/transaction/detail"

        async with httpx.AsyncClient(proxy=proxy) as client:
            resp = await client.get(url, headers=headers, params=params)

        return resp.json()

    async def get_added_liquidity_value(self, trans: str, proxy: str = None) -> float:
        response = await self._raw_trans_detail_info(trans_id=trans, proxy=proxy)
        summary_actions = response["data"]["render_summary_main_actions"]

        full_price = 0
        for obj in summary_actions[0]["title"][0]:
            for k, v in obj.items():
                if k not in ["token_amount", "number", "decimals", "token_address"]:
                    continue
                
                if obj["token_amount"]["token_address"] != WSOL_ADDR:
                    continue
                
                amount = v["number"]
                decimals = v["decimals"]
                tokens = decimal.Decimal(float(amount) / int("1" + "0" * decimals))
                market_resp = await self._raw_solscan_market(
                    v["token_address"], proxy=proxy
                )
                try:
                    full_price += market_resp["data"][v["token_address"]][
                        "price"
                    ] * float(tokens)
                except Exception:
                    continue

        return round(full_price, 2)

    async def _raw_solscan_market(self, *mint_addrs, proxy: str = None):
        params = {
            "ids": ",".join(mint_addrs),
        }

        async with httpx.AsyncClient(proxy=proxy) as client:
            resp = await client.get(
                "https://price.jup.ag/v4/price", params=params, headers=self._base_hdrs
            )
        return resp.json()
    
    async def get_transfers(self, target_addr: str, proxy: str = None, page: int = 1):
        if not proxy:
            client = self._client
        else:
            client = httpx.AsyncClient(proxy=proxy, verify=False)
                       
        cookies = {
            'cf_clearance': 'IHfKP7Nw8c9r4ffvL2DoZcjfvyUnvgjEuZorPj9YH3E-1730251095-1.2.1.1-CsMxD9MrXJulOhlsrLorf1zS_0KKsJSd6G_K2lmxNfSoxAnxEL4_YnptDU_RJ9ZQrMrxwAKN5wbLFgexVWLtbQm5fBjFi_uBQr5yzv7AHPQs5oAyTf.CkhlqF5OK9sW98f5xfoFirPoxa8Pgi7FKSb.HrxEexEtY7de8q4xdUQFKU9P3_GICgTtwt55pTYpzj.2PFFegpFPEl2RTksrNUrtuVnSxd4ge0tzt0.9qaLfYRvjozjEA22Hf.PnX2BPCm4rOk4QqHWzaIZR.ocYUffKhk.kWqaRkBF6FQ6Uarl9SMyaev8cRl.x.ihtxQmy5G1_KzXQ3lcgkD7PMfR5vIYB0PhHxX6dXmxiz.IUBamf7Kpfm4fjdhk5XjC4NlbqUVPf.V2sdZLCSSsRqtWgbnySzvGj4qM.XmROACTbGEpA',
            '_ga_PS3V7B7KV0': 'GS1.1.1730251095.1.0.1730251095.0.0.0',
            '_ga': 'GA1.1.1301283733.1730251096',
        }

        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'ru-RU,ru;q=0.9',
            'cache-control': 'no-cache',
            'cookie': 'cf_clearance=IHfKP7Nw8c9r4ffvL2DoZcjfvyUnvgjEuZorPj9YH3E-1730251095-1.2.1.1-CsMxD9MrXJulOhlsrLorf1zS_0KKsJSd6G_K2lmxNfSoxAnxEL4_YnptDU_RJ9ZQrMrxwAKN5wbLFgexVWLtbQm5fBjFi_uBQr5yzv7AHPQs5oAyTf.CkhlqF5OK9sW98f5xfoFirPoxa8Pgi7FKSb.HrxEexEtY7de8q4xdUQFKU9P3_GICgTtwt55pTYpzj.2PFFegpFPEl2RTksrNUrtuVnSxd4ge0tzt0.9qaLfYRvjozjEA22Hf.PnX2BPCm4rOk4QqHWzaIZR.ocYUffKhk.kWqaRkBF6FQ6Uarl9SMyaev8cRl.x.ihtxQmy5G1_KzXQ3lcgkD7PMfR5vIYB0PhHxX6dXmxiz.IUBamf7Kpfm4fjdhk5XjC4NlbqUVPf.V2sdZLCSSsRqtWgbnySzvGj4qM.XmROACTbGEpA; _ga_PS3V7B7KV0=GS1.1.1730251095.1.0.1730251095.0.0.0; _ga=GA1.1.1301283733.1730251096',
            'origin': 'https://solscan.io',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://solscan.io/',
            'sec-ch-ua': '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'sol-aut': 'l1c=Oj6Et=YdB9dls0fKHpsoTWQNdV-VOaxlwJhW',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        }

        params = {
            'address': target_addr,
            'page': page,
            'page_size': '100',
            'remove_spam': 'false',
            'exclude_amount_zero': 'false',
        }
        url = 'https://api-v2.solscan.io/v2/account/transfer'
        resp = await client.get(url, params=params, headers=headers, cookies=cookies)
        
        if not resp.is_success:
            raise ValueError(resp.reason_phrase)
        response = resp.json()
        return response
    
    async def get_unique_token_from_wallet_trades(self, addr: str, pages_count: int = 1):
        mints = []
        
        async def append_mints(page_num: int):
            nonlocal mints
            transfers = await self.get_transfers(addr, page=page_num)
            for transfer in transfers["data"]:
                
                if transfer["activity_type"] != 'ACTIVITY_SPL_TRANSFER':
                    continue
                if transfer["flow"] != "in":
                    continue
                
                mint = transfer["token_address"]
                if not mint.endswith("pump"):
                    continue
                if mint not in mints:
                    print(f"Get mint {mint} from wallet {addr}")
                    mints.append(mint)
        
        tasks = []
        for i in range(1, pages_count + 1):
            if len(tasks) >= 20:
                await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(1)
                tasks.clear()
                
            tasks.append(append_mints(i))
            
        await asyncio.gather(*tasks, return_exceptions=True)
        return mints
    
    async def get_creator_of_token(self, token_addr: str):
        client = self._client
        
        params = {
            'address': token_addr,
        }
        
        cookies = {
            'cf_clearance': 'IHfKP7Nw8c9r4ffvL2DoZcjfvyUnvgjEuZorPj9YH3E-1730251095-1.2.1.1-CsMxD9MrXJulOhlsrLorf1zS_0KKsJSd6G_K2lmxNfSoxAnxEL4_YnptDU_RJ9ZQrMrxwAKN5wbLFgexVWLtbQm5fBjFi_uBQr5yzv7AHPQs5oAyTf.CkhlqF5OK9sW98f5xfoFirPoxa8Pgi7FKSb.HrxEexEtY7de8q4xdUQFKU9P3_GICgTtwt55pTYpzj.2PFFegpFPEl2RTksrNUrtuVnSxd4ge0tzt0.9qaLfYRvjozjEA22Hf.PnX2BPCm4rOk4QqHWzaIZR.ocYUffKhk.kWqaRkBF6FQ6Uarl9SMyaev8cRl.x.ihtxQmy5G1_KzXQ3lcgkD7PMfR5vIYB0PhHxX6dXmxiz.IUBamf7Kpfm4fjdhk5XjC4NlbqUVPf.V2sdZLCSSsRqtWgbnySzvGj4qM.XmROACTbGEpA',
            '_ga_PS3V7B7KV0': 'GS1.1.1730251095.1.0.1730251095.0.0.0',
            '_ga': 'GA1.1.1301283733.1730251096',
        }

        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'ru-RU,ru;q=0.9',
            'cache-control': 'no-cache',
            'cookie': 'cf_clearance=IHfKP7Nw8c9r4ffvL2DoZcjfvyUnvgjEuZorPj9YH3E-1730251095-1.2.1.1-CsMxD9MrXJulOhlsrLorf1zS_0KKsJSd6G_K2lmxNfSoxAnxEL4_YnptDU_RJ9ZQrMrxwAKN5wbLFgexVWLtbQm5fBjFi_uBQr5yzv7AHPQs5oAyTf.CkhlqF5OK9sW98f5xfoFirPoxa8Pgi7FKSb.HrxEexEtY7de8q4xdUQFKU9P3_GICgTtwt55pTYpzj.2PFFegpFPEl2RTksrNUrtuVnSxd4ge0tzt0.9qaLfYRvjozjEA22Hf.PnX2BPCm4rOk4QqHWzaIZR.ocYUffKhk.kWqaRkBF6FQ6Uarl9SMyaev8cRl.x.ihtxQmy5G1_KzXQ3lcgkD7PMfR5vIYB0PhHxX6dXmxiz.IUBamf7Kpfm4fjdhk5XjC4NlbqUVPf.V2sdZLCSSsRqtWgbnySzvGj4qM.XmROACTbGEpA; _ga_PS3V7B7KV0=GS1.1.1730251095.1.0.1730251095.0.0.0; _ga=GA1.1.1301283733.1730251096',
            'origin': 'https://solscan.io',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://solscan.io/',
            'sec-ch-ua': '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'sol-aut': 'l1c=Oj6Et=YdB9dls0fKHpsoTWQNdV-VOaxlwJhW',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        }
        resp = await client.get('https://api-v2.solscan.io/v2/account', params=params, cookies=cookies, headers=headers)
        response = resp.json()
        
        
        tx = response["data"]["tokenInfo"]["first_mint_tx"]
        params = {'tx': tx}

        resp = await client.get('https://api-v2.solscan.io/v2/transaction/detail', params=params, cookies=cookies, headers=headers)
        response = resp.json()
        creator = response["data"]["signer"][0]
        return creator
    
    async def get_all_mints_from_creator(self, creator_addr: str):
        transfers = await self.get_transfers(creator_addr)
        
        trans_id = ''
        mints = []
        for transfer in reversed(transfers["data"]):
            if transfer["activity_type"] == "ACTIVITY_SPL_CREATE_ACCOUNT":
                trans_id = transfer["trans_id"]
                continue

            if transfer["trans_id"] != trans_id:
                continue
            
            mint = transfer["token_address"]
            if not mint.endswith("pump"):
                continue
            
            if mint not in mints:
                mints.append(mint)
        
        return mints


async def main():
    solscan = Solscan()
    addr = 'DfMxre4cKmvogbLrPigxmibVTTQDuzjdXojWzjCXXhzj'
    proxy = get_proxies()[0]
    
    # tokens = await solscan.get_unique_token_from_wallet_trades(addr, pages_count=1500)
    # print(f"tokens: {len(tokens)}")
    with open("tokens.json") as f:
        tokens = json.load(f)
    
    # with open("tokens.json", "w") as f:
    #     json.dump(tokens, f, ensure_ascii=False, indent=2)
        
    creators = []
    
    async def append_creators(mint: str):
        nonlocal creators
        res = await solscan.get_creator_of_token(mint)
        print(f"get creator of mint: {res}")
        creators.append(res)
        
    # tasks = []
    # for token_addr in tokens:
    #     if len(tasks) >= 20:
    #         r = await asyncio.gather(*tasks, return_exceptions=True)
    #         await asyncio.sleep(2)
    #         tasks.clear()
            
    #     tasks.append(append_creators(token_addr))
    
    # r = await asyncio.gather(*tasks, return_exceptions=True)
    
    # with open("creators.json", "w") as f:
    #     json.dump(creators, f, ensure_ascii=False, indent=2)
    
    with open("creators.json") as f:
        creators = json.load(f)
        
    creators_with_more_mints = []
    
    async def get_mints_of_creator(addr: str):
        nonlocal creators_with_more_mints
        res = await solscan.get_all_mints_from_creator(addr)
        print(f"wallet {addr} mints {len(res)} tokens")
        if len(res) > 1:
            creators_with_more_mints.append({"creator": addr, "mints": res})
    
    tasks = []
    for creator in creators:
        
        if len(tasks) >= 20:
            r = await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(2)
            tasks.clear()
        
        tasks.append(get_mints_of_creator(creator))
    
    r = await asyncio.gather(*tasks, return_exceptions=True)
    
    with open("creators-detail.json", "w") as f:
        json.dump(creators_with_more_mints, f, ensure_ascii=False, indent=2)
    
    dup_creators = [t for t in tokens if tokens.count(t) > 1]
    print(f"tokens. orig: {len(tokens)}")
    print(f"creators. orig: {len(creators)}, dup: {len(dup_creators)}. proffesionals: {len(creators_with_more_mints)}")
    
    # res = await solscan.get_all_mints_from_creator('7FfX169JqvxPQtajUpTkokLAf1YJQNDJyF3H8sW5rmpS')
    # print(res)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
