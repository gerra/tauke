"""
Centralized logging for tauke.

All logs go to ~/.tauke/tauke.log (rotating, max 5 MB × 3 files).
The daemon also inherits this so its output ends up in the same file
instead of a separate worker.log.

Usage:
    from tauke.lib.logger import log
    log.info("task claimed")
    log.error("push failed: %s", err)

Levels: DEBUG, INFO, WARNING, ERROR
"""

import logging
import logging.handlers
from pathlib import Path

from tauke.lib.config import TAUKE_DIR

LOG_FILE = TAUKE_DIR / "tauke.log"
_MAX_BYTES = 5 * 1024 * 1024   # 5 MB
_BACKUP_COUNT = 3
_FMT = "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _setup() -> logging.Logger:
    TAUKE_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("tauke")
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.DEBUG)

    # Rotating file handler — always on
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))
    logger.addHandler(fh)

    return logger


log = _setup()


def get(name: str) -> logging.Logger:
    """Return a child logger, e.g. get('worker'), get('coord_repo')."""
    return log.getChild(name)
