"""Structured logging for the Anvil forge pipeline.

Provides a consistent, coloured logger that shows each pipeline stage
with timing information.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator


# ── Colour formatter ──────────────────────────────────────────────────────


class _ColourFormatter(logging.Formatter):
    """Terminal-aware formatter that adds ANSI colours and stage context."""

    _GREY = "\033[90m"
    _BLUE = "\033[94m"
    _CYAN = "\033[96m"
    _GREEN = "\033[92m"
    _YELLOW = "\033[93m"
    _RED = "\033[91m"
    _BOLD = "\033[1m"
    _RST = "\033[0m"

    LEVEL_COLOURS = {
        logging.DEBUG: _GREY,
        logging.INFO: _CYAN,
        logging.WARNING: _YELLOW,
        logging.ERROR: _RED,
        logging.CRITICAL: _RED + _BOLD,
    }

    def format(self, record: logging.LogRecord) -> str:
        colour = self.LEVEL_COLOURS.get(record.levelno, self._RST)
        timestamp = time.strftime("%H:%M:%S", time.localtime(record.created))
        millis = f"{record.created % 1:.3f}"[1:]
        header = f"{self._GREY}{timestamp}{millis}{self._RST}"
        stage = getattr(record, "stage", None)
        stage_tag = f" {self._BOLD}[{stage}]{self._RST}" if stage else ""
        return f"{header}{stage_tag} {colour}{record.getMessage()}{self._RST}"


# ── Module-level logger ───────────────────────────────────────────────────

_logger = logging.getLogger("mcp_adapter")


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure and return the pipeline logger."""
    level = logging.DEBUG if verbose else logging.INFO
    _logger.setLevel(level)

    if not _logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_ColourFormatter())
        _logger.addHandler(handler)

    _logger.propagate = False
    return _logger


def get_logger() -> logging.Logger:
    """Return the pipeline logger (call setup_logging first)."""
    if not _logger.handlers:
        setup_logging()
    return _logger


# ── Stage context manager ─────────────────────────────────────────────────


@contextmanager
def log_stage(stage_name: str) -> Generator[logging.Logger, None, None]:
    """Context manager that logs stage entry/exit with timing."""
    logger = get_logger()
    start = time.perf_counter()
    extra = {"stage": stage_name}
    logger.info("▸ %s …", stage_name, extra=extra)
    try:
        yield logger
    except Exception:
        dt = time.perf_counter() - start
        logger.error("✗ %s FAILED (%.2fs)", stage_name, dt, extra=extra)
        raise
    else:
        dt = time.perf_counter() - start
        logger.info("✓ %s done (%.2fs)", stage_name, dt, extra=extra)
