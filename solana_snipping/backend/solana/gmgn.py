import asyncio
from pprint import pprint

import httpx

class GmgnAPI:
    
    def __init__(self) -> None:
        self._client = httpx.AsyncClient()
        
    async def get_unique_token_from_wallet_trades(self, addr: str, next: str = None):
        client = httpx.AsyncClient()
        
        cookies = {
            '_ga': 'GA1.1.1615292806.1729498196',
            '__cf_bm': 'IEFv6JzMxlJlKVGrWe2_lCJpKrtzzMsfX9l0z2tkRy4-1730252425-1.0.1.1-CXyjrn3Dvu2emvK_slU8QC45RrWG1XijFf.9p7LwHB_YiMWAQviPKTdiNBdB7H_0S7N0JvwNXDLswOOPoka4jA',
            'cf_clearance': 'OxjKLVcVel0PiphoPHU_4ZN73SAWsVnxbA8zSa8WCfc-1730252600-1.2.1.1-x8Tu5m9x10uP4yi2qLOiCmUXLIzH5VWxOhcWvwNLuLatw63AlShjh6guCfPspHe2bqpm9A7T85jW7YRg3nSU_QQnUVlchpJy2cO0X7Y9_LsELodTYByT072BTDPX5FobwAmu0ORk3oE7TBWTwelma0CAXCitCnNmpEB7FxGpp__XpfyKXO9hjXJF1i6GNh6PXm._naBZZx8T1tBUci0.XoSo0eX9ThGsFZOt6ub_aFRthHVcXKuRnN6K7RVRdOWU7JeyJb2XdYhWfCf.b16Kfst3QlHQGNhi2KkJYj0ib7z46MFysXVbhEeDPD_befXnfA55QD3k0_88e62gFMzSV.jgTwXYupTH5p.0x_4YstaXLSz_80DqPSIgbGt0Wjvc',
            '_ga_0XM0LYXGC8': 'GS1.1.1730252598.43.1.1730252911.0.0.0',
        }
        
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6',
            'cache-control': 'no-cache',
            # 'cookie': '_ga=GA1.1.1615292806.1729498196; cf_clearance=iAeia9kPgUIEe0F9Y6HHK4RU7HQamCff9hEKbu2Tnpo-1730240926-1.2.1.1-Clx8snR8D1L95CzBeuTCmJYS5OT0AgcHnFV740Z9qeuaFeTbJ3QmpHE4kJafQ3GtYwhROolTFtXhYEpj3pRWaZPq_WJducTadV.Zffcl0onIe6aH76VMhEdVktUTR2roipv6Mt36ihhvfEwiwLnYuX7dLqLCr3c8MK_5GRV2SZ3BIrh8Aa8fcE9TQYR5HLbWMzxbCJ_TTFHp4niqUg_._dCm01.N_CQvatCFjHkv6WCvSnRsR_pyaUPGHLJj_kYg6DU3ywjIVFSxSPygNppOhqDDCTXPVQtbqopmdivd.icZB8i.oFKmWcoPMYIS2M_xttUttIG3zHq7GxOyFM3OBS0v5M7HJfdlJWReJUuY7uFK5RLBzK94mwknIjLQoY.c; __cf_bm=IEFv6JzMxlJlKVGrWe2_lCJpKrtzzMsfX9l0z2tkRy4-1730252425-1.0.1.1-CXyjrn3Dvu2emvK_slU8QC45RrWG1XijFf.9p7LwHB_YiMWAQviPKTdiNBdB7H_0S7N0JvwNXDLswOOPoka4jA; _ga_0XM0LYXGC8=GS1.1.1730252598.43.1.1730252598.0.0.0',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': f'https://gmgn.ai/sol/address/{addr}',
            'sec-ch-ua': '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        }

        params = {
            'type': [
                'buy',
            ],
            'wallet': addr,
            'limit': '10',
            'cost': '10',
        }
        if next:
            params["cursor"] = next
            
        url = 'https://gmgn.ai/defi/quotation/v1/wallet_activity/sol'
        
        resp = await client.get(url, params=params, headers=headers, cookies=cookies)
        if not resp.is_success:
            raise ValueError(resp.reason_phrase)
        data = resp.json()
        mints = []
        
        for activity in data["data"]["activities"]:
            mint = activity["token_address"]
            
            if mint not in mints:
                mints.append(mint)
        
        return mints, data["data"]["activities"]["next"]
    
    
async def main():
    api = GmgnAPI()
    addr = "DfMxre4cKmvogbLrPigxmibVTTQDuzjdXojWzjCXXhzj"
    mints = await api.get_unique_token_from_wallet_trades(addr)
    pprint(mints)


if __name__ == "__main__":
    asyncio.run(main())