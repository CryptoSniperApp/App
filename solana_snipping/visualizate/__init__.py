import asyncio
import time
import httpx
import plotly.graph_objects as go
import pandas as pd

from solana_snipping.constants import USDT_ADDR


async def get_graph(mint: str, time_from: int, time_to: int):
    headers = {
        "accept": "*/*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
        "origin": "https://jup.ag",
        "priority": "u=1, i",
        "referer": "https://jup.ag/",
        "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "x-api-key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE2NzI5MDEwNzZ9.c66gFnI20ymHoPWapB0JgISzqDIK6Q_Zg0oAVp8Ssyc",
    }

    params = {
        "base_address": mint,
        "quote_address": "So11111111111111111111111111111111111111112",
        "type": "1m",
        "time_from": f"{int(time_from)}",
        "time_to": f"{int(time_to)}",
    }
    url = "https://public-api.birdeye.so/defi/ohlcv/base_quote"
    resp = await httpx.AsyncClient().get(url=url, params=params, headers=headers)
    data = resp.json()
    df = pd.DataFrame(data["data"]["items"])

    df["datetime"] = pd.to_datetime(df["unixTime"], unit="s")

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df["datetime"], open=df["o"], high=df["h"], low=df["l"], close=df["c"]
            )
        ]
    )

    fig.update_layout(
        title="USDT/TON",
        xaxis_title="Date",
        yaxis_title="Price (USDT)",
        xaxis_rangeslider_visible=False,
        xaxis=dict(
            tickformat="%Y-%m-%d %H:%M:%S"
        ),
    )

    fig.show()
    ...


async def main():
    mint = 'mUrehbGYgckMqeEXZyCp2rsYwko7B4mCEGTsZBpaQp9'
    from_ = time.time() - 50000
    to = time.time()
    
    await get_graph(mint, from_, to)

    ...


if __name__ == "__main__":
    asyncio.run(main())
