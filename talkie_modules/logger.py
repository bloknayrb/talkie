"""Structured logging for Talkie with key-redacting filter."""

import logging
import re
from logging.handlers import RotatingFileHandler
from typing import Final

from talkie_modules.paths import LOG_FILE

_LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s [%(module)s] %(message)s"
_KEY_PATTERN: Final[re.Pattern] = re.compile(
    r"(sk-[A-Za-z0-9_-]{10,}|gsk_[A-Za-z0-9_-]{10,}|sk-ant-[A-Za-z0-9_-]{10,})"
)


class KeyRedactingFilter(logging.Filter):
    """Scrubs API key patterns from log output."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _KEY_PATTERN.sub("[REDACTED]", record.msg)
        if record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    new_args.append(_KEY_PATTERN.sub("[REDACTED]", arg))
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)
        return True


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure and return the root Talkie logger."""
    logger = logging.getLogger("talkie")

    if logger.handlers:
        # Already configured
        return logger

    logger.setLevel(level)
    logger.addFilter(KeyRedactingFilter())

    formatter = logging.Formatter(_LOG_FORMAT)

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    # Rotating file handler (5MB, 3 backups)
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        logger.warning("Could not create log file at %s", LOG_FILE)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the talkie namespace."""
    return logging.getLogger(f"talkie.{name}")
