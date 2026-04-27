"""structlog configuration.

Pretty console output in dev (`ENV=dev`), JSON in production. Other modules
should call `get_logger(__name__)` rather than instantiating a logger directly.

# TODO(phase-2): wire structlog → Langfuse for trace export.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from rett_repurposing.config import get_settings


def configure_logging() -> None:
    """Configure structlog and the stdlib root logger.

    Idempotent: safe to call multiple times. The first call wins; subsequent
    calls are no-ops because structlog's `configure` is process-global.
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.env == "dev":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to optional initial context."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    if initial_values:
        logger = logger.bind(**initial_values)
    return logger
