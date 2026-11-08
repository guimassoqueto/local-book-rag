"""Structured JSON logging, with an execution ID for each ingestion and query operation."""

import json
import logging
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT_LOGGER = "book_rag"
INFERENCE_LOGGER = "book_rag.inference"

_MAX_LOG_BYTES = 10 * 1024 * 1024
_LOG_BACKUPS = 5

_operation_fields: ContextVar[dict[str, Any] | None] = ContextVar("operation_fields", default=None)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, carrying the fields of the running operation."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(_operation_fields.get() or {})
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(level: str, inference_level: str, logs_dir: Path, console: bool = True) -> None:
    """Send application logs to logs/app.jsonl, and inference logs to logs/inference.jsonl.

    Args:
        level: threshold for application logs.
        inference_level: threshold for inference logs, independent from `level`.
        logs_dir: created if needed.
        console: also write application logs to stdout, which `docker compose logs` shows.
            Off for commands, whose output is meant for a person.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    formatter = JsonFormatter()

    def file_handler(name: str) -> logging.Handler:
        handler = RotatingFileHandler(logs_dir / name, maxBytes=_MAX_LOG_BYTES, backupCount=_LOG_BACKUPS)
        handler.setFormatter(formatter)
        return handler

    handlers = [file_handler("app.jsonl")]
    if console:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(formatter)
        handlers.append(stream)

    root = logging.getLogger(ROOT_LOGGER)
    root.handlers[:] = handlers
    root.setLevel(level)
    root.propagate = False

    inference = logging.getLogger(INFERENCE_LOGGER)
    inference.handlers[:] = [file_handler("inference.jsonl")]
    inference.setLevel(inference_level)
    inference.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{ROOT_LOGGER}.{name}")


def new_execution_id() -> str:
    return uuid.uuid4().hex[:12]


def log_event(logger: logging.Logger, message: str, level: int = logging.INFO, **fields: Any) -> None:
    """Log a message with structured fields next to it."""
    logger.log(level, message, extra={"fields": fields})


@contextmanager
def operation(logger: logging.Logger, name: str, **fields: Any) -> Iterator[str]:
    """Log the start, end and duration of an operation, tagging every log line inside it.

    Args:
        logger: receives the start and end lines.
        name: the operation, such as "add_book".
        **fields: added to every line, such as book_id.

    Yields:
        The execution ID.
    """
    execution_id = new_execution_id()
    token = _operation_fields.set({"execution_id": execution_id, "operation": name, **fields})
    started = perf_counter()
    log_event(logger, "operation started")
    try:
        yield execution_id
    except Exception:
        logger.exception("operation failed", extra={"fields": {"duration_seconds": perf_counter() - started}})
        raise
    else:
        log_event(logger, "operation finished", duration_seconds=perf_counter() - started)
    finally:
        _operation_fields.reset(token)
