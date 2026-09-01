import logging
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

LOG_FILE = LOGS_DIR / f"log_{datetime.now().strftime('%Y-%m-%d')}.log"

logging.basicConfig(
    filename=str(LOG_FILE),
    format="%(asctime)s-%(levelname)s-%(message)s",
    level=logging.INFO,
)


def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    return logger


logger = get_logger("sidecar")
