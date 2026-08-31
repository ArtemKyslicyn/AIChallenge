"""Application logging setup.

Never log message content, request headers, or ``access_token`` values.
Log ``session_id`` / ``message_id`` / ``model_id`` and timings only.
"""

from __future__ import annotations

import logging

_LOG_FORMAT = "ts=%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging. Safe to call from every ``create_app()``."""
    logging.basicConfig(level=level.upper(), format=_LOG_FORMAT, force=True)
