import asyncio
import decimal
import random
import re

from loguru import logger
import ua_generator

def format_number_decimal(num: int | float | str) -> str:
    num = decimal.Decimal(str(num))
    decimals = - num.as_tuple().exponent
    return f"{num:,.{decimals}f}"


class AsyncioTasksCallbacks:
    @staticmethod
    def raise_exception_if_set(task: asyncio.Task):
        try:
            task.result()
        except Exception as e:
            logger.exception(e)
            raise e

asyncio_callbacks = AsyncioTasksCallbacks()


def append_hdrs(headers: dict):
    for k, v in ua_generator.generate().headers.get().items():
        headers[k] = v
    return headers


def get_proxies(filepath: str = "proxies.txt"):
    with open(filepath) as f:
        content = f.read()
    
    proxies = []
    for proxy in content.splitlines():
        proxies_range = re.search(r"<(\d+-\d+)>", proxy)
        if proxies_range:
            proxies_range = proxies_range.group(1)
            start_port, stop_port = proxies_range.split("-")
            proxy = re.sub(
                r"<\d+-\d+>",
                str(
                    random.randrange(start=int(start_port), stop=int(stop_port))
                ),
                proxy,
            )
        proxies.append(proxy)
    return proxies
