from loguru import logger


async def log_msg(msg: str):
    logger.info(msg)
