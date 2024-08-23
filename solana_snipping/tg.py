import os
from aiogram import Bot
from aiogram.types import FSInputFile

from solana_snipping.config import get_config


cfg = get_config()
bot = Bot(cfg["telegram"]["token"])


async def send_msg_log(message: str):
    if len(message) > 4096:
        fn = "message.txt"
        with open(fn, "w") as f:
            f.write(message)
            doc = FSInputFile(fn)
        await bot.send_document(
            cfg["telegram"]["chat_id"], doc, caption="Слишком большое сообщение"
        )
        os.remove(fn)
    else:
        await bot.send_message(
            cfg["telegram"]["chat_id"], message, parse_mode="Markdown"
        )
