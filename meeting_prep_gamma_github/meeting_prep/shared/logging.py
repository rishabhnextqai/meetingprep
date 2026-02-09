import logging
import os

LOG_LEVEL = os.getenv("TRADE_SHOW_LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

logger = logging.getLogger("trade_show")
