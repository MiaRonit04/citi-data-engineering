"""Structured logging built on Loguru.

A single :func:`configure_logging` call wires up:

* a coloured console sink at the configured level, and
* a rotating, retained file sink under ``logs/`` that always captures DEBUG.

Every module obtains a logger with :func:`get_logger`; contextual fields
(``batch_id``, ``dataset``, ``stage`` …) are attached with ``logger.bind(...)``
so log lines are machine-parseable, never ``print``-based.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from typing import Any

from loguru import logger

from etl.common.config import Settings, get_settings

_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[stage]}</cyan>:<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
    "<level>{message}</level>"
)
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "stage={extra[stage]} batch={extra[batch_id]} dataset={extra[dataset]} | "
    "{name}:{function}:{line} | {message}"
)

_DEFAULT_CONTEXT: dict[str, Any] = {"stage": "-", "batch_id": "-", "dataset": "-"}


@lru_cache(maxsize=1)
def configure_logging(settings: Settings | None = None) -> None:
    """Configure Loguru sinks exactly once per process (idempotent)."""
    settings = settings or get_settings()
    settings.logs_path.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.configure(extra=_DEFAULT_CONTEXT)

    logger.add(
        sys.stderr,
        level=settings.log_level.upper(),
        format=_CONSOLE_FORMAT,
        colorize=True,
        enqueue=True,
    )
    logger.add(
        settings.logs_path / "pipeline_{time:YYYYMMDD}.log",
        level="DEBUG",
        format=_FILE_FORMAT,
        rotation="20 MB",
        retention="14 days",
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )


def get_logger(stage: str = "-", **context: Any):
    """Return a Loguru logger pre-bound with ``stage`` and optional context.

    Example
    -------
    >>> log = get_logger("bronze", dataset="employees", batch_id="B-123")
    >>> log.info("Ingested {rows} rows", rows=200_000)
    """
    configure_logging()
    bound = {"stage": stage, **context}
    return logger.bind(**bound)
