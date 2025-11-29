import logging
from typing import Optional


def init_logging(level: str = "INFO") -> None:
    """Configure root logger with structured, concise format."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a module-scoped logger."""
    return logging.getLogger(name if name else __name__)
