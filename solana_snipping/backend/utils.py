import decimal

import ua_generator

def format_number_decimal(num: int | float | str) -> str:
    num = decimal.Decimal(str(num))
    decimals = - num.as_tuple().exponent
    return f"{num:,.{decimals}f}"


def append_hdrs(headers: dict):
    for k, v in ua_generator.generate().headers.get().items():
        headers[k] = v
    return headers
