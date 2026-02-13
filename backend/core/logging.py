import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional


_RESERVED_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


class StructuredFormatter(logging.Formatter):
    """Render logs as JSON with consistent fields."""

    def format(self, record: logging.LogRecord) -> str:
        base: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_KEYS and not key.startswith("_")
        }
        event = extras.pop("event", None)
        if event:
            base["event"] = event
        if extras:
            base["extra"] = extras
        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(base, default=str)


def init_logging(level: str = "INFO") -> None:
    """Configure default root logger with structured console output only."""
    init_logging_advanced(
        level=level,
        log_to_file=False,
        log_dir="logs",
        console_level=level,
        incident_level="WARNING",
        audit_trade_enabled=False,
        audit_stream_enabled=False,
    )


def init_logging_advanced(
    *,
    level: str = "INFO",
    log_to_file: bool = True,
    log_dir: str = "logs",
    console_level: str = "INFO",
    incident_level: str = "WARNING",
    audit_trade_enabled: bool = True,
    audit_stream_enabled: bool = False,
) -> None:
    """Configure root + dedicated audit loggers with structured JSON lines."""
    formatter = StructuredFormatter()
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, console_level.upper(), logging.INFO))
    root.addHandler(console_handler)

    if log_to_file:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        incidents_handler = RotatingFileHandler(
            log_path / "incidents.jsonl",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        incidents_handler.setFormatter(formatter)
        incidents_handler.setLevel(getattr(logging, incident_level.upper(), logging.WARNING))
        root.addHandler(incidents_handler)

    def _configure_audit_logger(name: str, enabled: bool, filename: str) -> None:
        audit_logger = logging.getLogger(name)
        audit_logger.handlers.clear()
        audit_logger.setLevel(logging.INFO)
        audit_logger.propagate = False
        if enabled and log_to_file:
            log_path = Path(log_dir)
            handler = RotatingFileHandler(
                log_path / filename,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            handler.setFormatter(formatter)
            handler.setLevel(logging.INFO)
            audit_logger.addHandler(handler)
        else:
            audit_logger.addHandler(logging.NullHandler())

    _configure_audit_logger("audit.trade", audit_trade_enabled, "trade_audit.jsonl")
    _configure_audit_logger("audit.stream", audit_stream_enabled, "stream_health.jsonl")


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a module-scoped logger."""
    return logging.getLogger(name if name else __name__)
