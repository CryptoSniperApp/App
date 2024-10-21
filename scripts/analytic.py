from datetime import datetime
import sqlite3

from solana_snipping.backend.utils import format_number_decimal
import pandas as pd


class ReadableAnalytic:
    def __init__(self, fn: str = "database.db") -> None:
        conn = sqlite3.connect(fn)
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
            
            mint_time = token_data[0]["capture_time"]
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
            max_amount_time = [r["swap_time"] for r in token_data if r["swap_price"] == max_amount][0]
            min_amount = min(all_amounts)
            min_amount_time = [r["swap_time"] for r in token_data if r["swap_price"] == min_amount][0]
            
            if max_amount_time - min_amount_time == 0:
                continue
            
            last_percent_diffirence = [r["percentage_difference"] for r in token_data if r["time"] == time_end][0]

            obj = {
                "Адрес Токена": token,
                "Цена в USD в начале": format_number_decimal(amount_start),
                "Минимальная цена в USD": format_number_decimal(min_amount),
                "Максимальная цена в USD": format_number_decimal(max_amount),
                # "Разница в %": last_percent_diffirence,
                "Разница между начальной и максимальной ценой в %": (max_amount - amount_start) / amount_start * 100,
                # "Первая ликвидность": first_liquidity,
                # "Время открытия пула": datetime.fromtimestamp(pool_open_time).strftime("%H:%M:%S %d.%m.%Y") if pool_open_time else "",
                "Время минимальной цены": datetime.fromtimestamp(min_amount_time).strftime("%H:%M:%S %d.%m.%Y"),
                "Время минта": datetime.fromtimestamp(mint_time).strftime("%H:%M:%S %d.%m.%Y"),
                "Время максимальной цены": datetime.fromtimestamp(max_amount_time).strftime("%H:%M:%S %d.%m.%Y"),
                "Время первой покупки": datetime.fromtimestamp(amount_start_time).strftime("%H:%M:%S %d.%m.%Y"),
                # "Время начала слежки": datetime.fromtimestamp(time_start),
                # "Время окончания слежки": datetime.fromtimestamp(time_end),
            }
            obj["Время слежки"] = datetime.fromtimestamp(time_end) - datetime.fromtimestamp(time_start)
            
            data.append(obj)
        
        data = sorted(data, key=lambda x: x["Время слежки"], reverse=True)
        data = sorted(data, key=lambda x: x["Разница между начальной и максимальной ценой в %"], reverse=True)
        return pd.DataFrame(data)


async def main():
    analytic = ReadableAnalytic(fn="statistic.db")
    df = analytic.construct_data()
    df.to_csv("data-statistic.csv", index=False)
    ...


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
