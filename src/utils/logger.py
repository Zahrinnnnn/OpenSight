import sys
from loguru import logger


def setup_logger(log_level: str = "INFO") -> None:
    # Remove default handler and add a clean one with timestamps
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
        level=log_level,
        colorize=True,
    )
    logger.add(
        "logs/opensight.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
    )


# Call setup on import so any module can just do: from src.utils.logger import logger
setup_logger()
