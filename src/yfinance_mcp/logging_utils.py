from __future__ import annotations

import logging
import os
import sys

import structlog


def _resolve_log_level() -> int:
    configured = os.getenv("YF_LOG_LEVEL")
    if configured:
        return getattr(logging, configured.upper(), logging.WARNING)
    transport = os.getenv("YF_TRANSPORT", "stdio").lower()
    return logging.WARNING if transport == "stdio" else logging.INFO


def configure_logging() -> None:
    if structlog.is_configured():
        return
    log_level = _resolve_log_level()
    logging.basicConfig(level=log_level, stream=sys.stderr)
    logging.getLogger("mcp").setLevel(log_level)
    logging.getLogger("mcp.server").setLevel(log_level)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
