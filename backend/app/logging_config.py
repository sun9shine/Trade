"""
Centralized Logging Configuration
- Structured JSON logs for production
- Pretty console output for development
- File rotation with daily archives
- Correlation IDs for request tracing
"""

import logging
import sys
from pathlib import Path

import structlog

from app.config import app_settings

# Log directory
LOG_DIR = Path("/app/logs") if app_settings.app_env == "production" else Path("./logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging():
    """Configure structlog + stdlib logging for the entire application."""

    # Determine log level
    log_level = logging.DEBUG if app_settings.app_env == "development" else logging.INFO

    # Shared processors for all outputs
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if app_settings.app_env == "development":
        # Pretty console output for development
        renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            pad_event=35,
        )
    else:
        # JSON output for production (Elasticsearch/Grafana compatible)
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Formatter for stdlib handlers
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # File handler — all logs
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "arbitrage_bot.log",
        maxBytes=50 * 1024 * 1024,  # 50 MB
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # Error file handler — errors only
    error_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "errors.log",
        maxBytes=20 * 1024 * 1024,  # 20 MB
        backupCount=5,
        encoding="utf-8",
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)

    # Trade execution log — separate file for audit
    trade_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "trades.log",
        maxBytes=30 * 1024 * 1024,  # 30 MB
        backupCount=20,
        encoding="utf-8",
    )
    trade_handler.setFormatter(formatter)
    trade_handler.setLevel(logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = []
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)

    # Configure trade-specific logger
    trade_logger = logging.getLogger("trades")
    trade_logger.addHandler(trade_handler)
    trade_logger.setLevel(logging.INFO)

    # Silence noisy third-party loggers
    for noisy_logger in [
        "uvicorn.access",
        "httpx",
        "httpcore",
        "websockets",
        "sqlalchemy.engine",
    ]:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    return structlog.get_logger()


# Import for `from logging import handlers`
import logging.handlers
