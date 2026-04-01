from __future__ import annotations

import contextvars
import logging
import os
import sys
import uuid

import structlog
from structlog import contextvars as structlog_contextvars


_upstream_call_count: contextvars.ContextVar[int] = contextvars.ContextVar("upstream_call_count", default=0)


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
            structlog_contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


def next_request_id() -> str:
    return uuid.uuid4().hex


def bind_request_context(*, request_id: str, tool_name: str) -> None:
    structlog_contextvars.clear_contextvars()
    structlog_contextvars.bind_contextvars(request_id=request_id, tool_name=tool_name)
    _upstream_call_count.set(0)


def clear_request_context() -> None:
    structlog_contextvars.clear_contextvars()
    _upstream_call_count.set(0)


def increment_upstream_call_count() -> int:
    count = _upstream_call_count.get() + 1
    _upstream_call_count.set(count)
    return count


def get_upstream_call_count() -> int:
    return _upstream_call_count.get()
