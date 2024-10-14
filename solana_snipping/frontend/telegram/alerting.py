import os
from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from solana_snipping.common.config import get_config


cfg = get_config()
bot = Bot(cfg["telegram"]["token"])


def build_mp(mint_addr: str, trans_addr: str) -> InlineKeyboardBuilder:
    dexscreener_url = f"https://dexscreener.com/search?q={mint_addr}"
    raydium_url = f"https://raydium.io/swap/?inputMint={mint_addr}&outputMint=sol"
    transaction_url = f"https://solscan.io/tx/{trans_addr}"

    kb = InlineKeyboardBuilder()

    for text, url in [
        ("DexScreener", dexscreener_url),
        ("Raydium", raydium_url),
        ("Transaction", transaction_url),
    ]:
        btn = InlineKeyboardButton(text=text, url=url)
        kb.add(btn)
    return kb


async def log_in_chat(message: str):
    try:
        try:
            await bot.send_message(
                cfg["microservices"]["moonshot"]["logger_chat_id"],
                message,
                parse_mode="Markdown",
            )
        except Exception:
            await bot.send_message(
                cfg["microservices"]["moonshot"]["logger_chat_id"],
                message,
            )
    except Exception as e:
        logger.exception(e)


async def send_msg_log(message: str, mint: str, trans: str):
    kb = build_mp(mint_addr=mint, trans_addr=trans)
    kb: InlineKeyboardBuilder

    if len(message) > 4096:
        fn = "message.txt"
        with open(fn, "w") as f:
            f.write(message)
            doc = FSInputFile(fn)
        await bot.send_document(
            cfg["telegram"]["chat_id"],
            doc,
            caption="Слишком большое сообщение",
            reply_markup=kb.as_markup(),
        )
        os.remove(fn)
    else:
        await bot.send_message(
            cfg["telegram"]["chat_id"],
            message,
            parse_mode="Markdown",
            reply_markup=kb.as_markup(),
        )
