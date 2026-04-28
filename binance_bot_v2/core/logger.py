from loguru import logger
import sys
import os

LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{extra[tag]:<12}</level> | "
    "<level>{message}</level>"
)

def setup_logger(level="INFO"):
    logger.remove()
    os.makedirs("data", exist_ok=True)

    logger.add(
        sys.stdout,
        format=LOG_FORMAT,
        level=level,
        colorize=True,
    )
    logger.add(
        "data/sniper_v2.log",
        format=LOG_FORMAT,
        level="DEBUG",
        rotation="10 MB",
        retention=3,
        encoding="utf-8",
    )
    return logger

log = logger
log.configure(extra={"tag": "INIT"})
setup_logger()
