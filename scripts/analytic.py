from datetime import datetime
import sqlite3

import pandas as pd


class ReadableAnalytic:
    def __init__(self) -> None:
        conn = sqlite3.connect("database.db")
        df = pd.read_sql_query("select * from analytic;", conn)
        data = df.to_dict("records")

        self._conn = conn
        self.df = df
        self.data = data

        self._tokens = list(set([d["mint1_addr"] for d in data]))

    def construct_data(self):
        data = []
        for token in self._tokens:
            token_data = [r for r in self.data if r["mint1_addr"] == token]

            times = [r["time"] for r in token_data]
            time_start = min(times)
            time_end = max(times)

            amount_start = [
                r["swap_price"] for r in token_data if r["time"] == time_start
            ][0]
            amount_start_time = [r["swap_time"] for r in token_data if r["swap_price"] == amount_start][0]

            all_amounts = [r["swap_price"] for r in token_data]

            percent_diffirences = [
                r["percentage_difference"]
                for r in self.data
                if r["mint1_addr"] == token
            ]
            min_percent_diffirence = min(percent_diffirences)
            max_percent_diffirence = max(percent_diffirences)

            first_liquidity = [r["first_added_liquiduty_value"] for r in token_data][0]
            pool_open_time = [r["pool_open_time"] for r in token_data][0]
            
            max_amount = max(all_amounts)
            
            min_amount = min(all_amounts)
            min_amount_time = [r["swap_time"] for r in token_data if r["swap_price"] == min_amount][0]

            obj = {
                "Адрес Токена": token,
                "Кол-во токенов при первой покупке за 0.77 SOL": amount_start,
                "Минимальное кол-во токенов за 0.77 SOL": min_amount,
                "Максимальное кол-во токенов за 0.77 SOL": max_amount,
                "Разница в %": round((amount_start - min_amount) / min_amount * 100, 2),
                "Первая ликвидность": first_liquidity,
                "Время открытия пула": datetime.fromtimestamp(pool_open_time).strftime("%H:%M:%S %d.%m.%Y"),
                "Время максимальной цены": datetime.fromtimestamp(min_amount_time).strftime("%H:%M:%S %d.%m.%Y"),
                "Время первой покупки": datetime.fromtimestamp(amount_start_time).strftime("%H:%M:%S %d.%m.%Y"),
            }
            data.append(obj)

        return pd.DataFrame(data)


async def main():
    analytic = ReadableAnalytic()
    df = analytic.construct_data()
    df.to_csv("data.csv", index=False)
    ...


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
