"""
Logging setup.

The original project had zero logging anywhere (audit B9: plugin failures were
swallowed silently). Vednix logs every failure with context. Stdlib logging,
one consistent format, no external dependency.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def setup_logging(level: int | str = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    # Tame noisy library loggers in dev
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
